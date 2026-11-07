"""Editor model: everything the editor does, without any GUI code.

The GUI only calls this module. Every change becomes an edit of a known field
(trcore.stc.edit), is applied to the stage's original bytes and parsed back;
what the editor shows is read from those re-parsed bytes, so the screen always
shows exactly what a save would write. Saving goes through
trcore.editplan.build_edit_rom (verified ROM copy + patch record).

Only fields whose meaning was confirmed in-game (evidence Level 4) can be
changed: start position and facing, goal position / facing / red flag, bumper
position, banana position / bunch flag.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Dict, List, Optional, Tuple

from trcore import lz10
from trcore.editplan import PLAN_SCHEMA, build_edit_rom
from trcore.nitro.nsbmd import NitroError
from trcore.rom import NdsRom, RomError
from trcore.romwrite import RomWriteRefused, patch_record_path
from trcore.stagemodel import group_kinds, load_stage_model
from trcore.stc.document import StageDocument
from trcore.stc.edit import EditRefused, apply_edits

FX = 4096
ANGLE_FULL = 0x10000

# kind -> (record source, pool key, position field, position target suffix)
KINDS = {
    "start": ("start", None, "position", "position"),
    "goal": ("pool", "A", "translation", "translation"),
    "bumper": ("pool", "B", "translation", "translation"),
    "banana": ("pool", "C", "position", "position"),
}
TARGET_PREFIX = {"start": "start", "goal": "pool_A", "bumper": "pool_B", "banana": "pool_C"}
FLAG_TARGET = {("goal", "red"): "u32_30", ("banana", "bunch"): "u32_0C"}


class EditorError(Exception):
    pass


# --------------------------------------------------------------------------- angles

def angle_to_degrees(word: int) -> float:
    return (word & 0xFFFF) * 360.0 / ANGLE_FULL


def degrees_to_angle(deg: float, old_word: int = 0) -> int:
    return (old_word & ~0xFFFF) | (int(round(deg % 360.0 * ANGLE_FULL / 360.0)) % ANGLE_FULL)


def goal_heading(matrix) -> Optional[float]:
    """Facing of a goal's front (local +z) in the start-angle convention: 0 = towards -z,
    increasing = turning left. Stored matrices are applied transposed, so the front is row 2."""
    fx, _fy, fz = matrix[2]
    if math.hypot(fx, fz) < 0.5:
        return None
    return math.degrees(math.atan2(-fx, -fz)) % 360.0


def yaw_rows(deg: float):
    """Stored-form rotation by deg about +y (positive turns left)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, -s), (0.0, 1.0, 0.0), (s, 0.0, c))


def rotate_matrix(m, deg: float):
    r = yaw_rows(deg)
    return [[sum(m[i][k] * r[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _q(v: float) -> int:
    return int(round(v * FX))


# --------------------------------------------------------------------------- stage state

class StageState:
    """One stage: original bytes, current edits (target -> raw values), and the re-parsed document."""

    def __init__(self, project: "Project", entry: dict):
        self.project = project
        self.entry = entry
        self.key = entry["stage_key"]
        self.original = project.rom.stage_file_decoded(self.key)
        self.original_doc = StageDocument(self.original, self.key)
        if self.original_doc.has_errors():
            raise EditorError(f"{self.key}: stage file has structural errors; it can be viewed only with trcore")
        self.edits: Dict[str, Tuple[int, ...]] = {}
        self.current = self.original
        self.doc = self.original_doc
        self._model = None
        self.model_error = None
        self._kinds = None

    # ---- model outline (read once)
    @property
    def model(self) -> Optional[dict]:
        if self._model is None and self.model_error is None:
            try:
                self._model = load_stage_model(self.project.rom, self.key) or {}
            except NitroError as exc:
                self.model_error = str(exc)
                self._model = {}
        return self._model or None

    @property
    def group_kinds(self) -> Dict[int, str]:
        if self._kinds is None:
            m = self.model
            self._kinds = group_kinds(self.original_doc, m["model"] if m else None)
        return self._kinds

    # ---- raw field access
    def _record(self, kind: str, index: int, doc: Optional[StageDocument] = None) -> dict:
        doc = doc or self.doc
        src, pool, _f, _t = KINDS[kind]
        recs = (doc.start or {}).get("records", []) if src == "start" else doc.pools.get(pool, {}).get("records", [])
        if not 0 <= index < len(recs):
            raise EditorError(f"{kind} {index} does not exist")
        return recs[index]

    def original_raw(self, target: str) -> Tuple[int, ...]:
        return self._raw_from_doc(target, self.original_doc)

    def current_raw(self, target: str) -> Tuple[int, ...]:
        return self.edits.get(target) or self.original_raw(target)

    def _raw_from_doc(self, target: str, doc: StageDocument) -> Tuple[int, ...]:
        prefix, rest = target.split("[", 1)
        idx, field = rest.split("].")
        kind = {v: k for k, v in TARGET_PREFIX.items()}[prefix]
        rec = self._record(kind, int(idx), doc)
        if field in ("position", "translation"):
            return tuple(_q(v) for v in rec[field])
        if field == "matrix":
            return tuple(_q(v) for row in rec["matrix"] for v in row)
        return (rec[field],)

    def plan_edits(self, edits: Optional[Dict[str, Tuple[int, ...]]] = None) -> List[dict]:
        out = []
        for target, raw in sorted((edits if edits is not None else self.edits).items()):
            orig = self.original_raw(target)
            if raw == orig:
                continue
            field = target.rsplit(".", 1)[1]
            if field in ("position", "translation", "matrix"):
                out.append({"target": target, "from": [v / FX for v in orig], "to": [v / FX for v in raw]})
            else:
                out.append({"target": target, "from": orig[0], "to": raw[0]})
        return out

    def _rebuild(self, edits: Dict[str, Tuple[int, ...]]):
        clean = {t: v for t, v in edits.items() if v != self.original_raw(t)}
        if not clean:
            return clean, self.original, self.original_doc
        try:
            new, _recs = apply_edits(self.original, self.plan_edits(clean), self.key)
        except EditRefused as exc:
            raise EditorError(str(exc)) from None
        return clean, new, StageDocument(new, self.key)

    def set_raw(self, changes: Dict[str, Tuple[int, ...]]):
        edits = dict(self.edits)
        edits.update(changes)
        self.edits, self.current, self.doc = self._rebuild(edits)

    # ---- object view for the GUI
    def objects(self) -> List[dict]:
        out = []
        kinds = self.group_kinds
        names = {g["index"]: g.get("name_text_04") for g in self.doc.groups}
        for kind in ("start", "goal", "bumper", "banana"):
            src, pool, pfield, _t = KINDS[kind]
            recs = (self.doc.start or {}).get("records", []) if src == "start" \
                else self.doc.pools.get(pool, {}).get("records", [])
            for rec in recs:
                i = rec["index"]
                grp = 0 if kind == "start" else rec["group"]
                o = {"id": f"{kind}:{i}", "kind": kind, "index": i, "group": grp,
                     "group_name": names.get(grp), "group_kind": kinds.get(grp),
                     "in_moving_group": bool(grp), "position": list(rec[pfield]),
                     "editable": {"position"}, "heading": None, "offset": rec["offset"]}
                prefix = TARGET_PREFIX[kind]
                o["changed"] = any(t.startswith(f"{prefix}[{i}].") for t in self.edits)
                if kind == "start":
                    o["heading"] = angle_to_degrees(rec["u32_0C"])
                    o["editable"].add("heading")
                elif kind == "goal":
                    o["heading"] = goal_heading(rec["matrix"])
                    o["matrix"] = rec["matrix"]
                    o["red"] = rec["u32_30"] == 1
                    o["editable"].add("red")
                    if o["heading"] is not None and goal_heading(self._record("goal", i, self.original_doc)["matrix"]) is not None:
                        o["editable"].add("heading")
                elif kind == "bumper":
                    o["matrix"] = rec["matrix"]
                elif kind == "banana":
                    o["bunch"] = rec["u32_0C"] == 1
                    o["editable"].add("bunch")
                out.append(o)
        return out

    def changes_for(self, obj_id: str, prop: str, value) -> Dict[str, Tuple[int, ...]]:
        """Translate a GUI property change into raw field values."""
        kind, idx = obj_id.split(":")
        i = int(idx)
        prefix = TARGET_PREFIX[kind]
        if prop == "position":
            field = KINDS[kind][3]
            vals = tuple(_q(float(v)) for v in value)
            if len(vals) != 3:
                raise EditorError("position needs x, y, z")
            return {f"{prefix}[{i}].{field}": vals}
        if prop == "heading" and kind == "start":
            t = f"start[{i}].u32_0C"
            return {t: (degrees_to_angle(float(value), self.original_raw(t)[0]),)}
        if prop == "heading" and kind == "goal":
            t = f"pool_A[{i}].matrix"
            orig_m = self._record("goal", i, self.original_doc)["matrix"]
            h0 = goal_heading(orig_m)
            if h0 is None:
                raise EditorError("this goal points straight up or down; its facing cannot be edited")
            d = (float(value) - h0) % 360.0
            if abs(d) < 1e-9 or abs(d - 360.0) < 1e-9:
                return {t: self.original_raw(t)}
            return {t: tuple(_q(v) for row in rotate_matrix(orig_m, d) for v in row)}
        if (kind, prop) in FLAG_TARGET:
            return {f"{prefix}[{i}].{FLAG_TARGET[(kind, prop)]}": (1 if value else 0,)}
        raise EditorError(f"{prop} of a {kind} cannot be edited")


# --------------------------------------------------------------------------- project

class Project:
    def __init__(self, rom_path: str, rom: Optional[NdsRom] = None):
        """rom_path: the ROM file (opened read-only). rom: an already loaded NdsRom for that file (tests)."""
        self.rom_path = os.path.abspath(rom_path)
        try:
            self.rom = rom if rom is not None else NdsRom.from_file(self.rom_path)
        except (OSError, RomError) as exc:
            raise EditorError(f"cannot open ROM: {exc}") from None
        self.rom_sha1 = hashlib.sha1(self.rom.data).hexdigest()
        if not self.rom.profile():
            raise EditorError("this ROM is not a supported Touch & Roll version (USA rev 0 expected)")
        self.opened_editor_output = _editor_output_record(self.rom_path, self.rom_sha1)
        try:
            sm = self.rom.stage_map()
        except RomError as exc:
            raise EditorError(f"stage map could not be read: {exc}") from None
        self.worlds = sm["worlds"]
        self.entries: Dict[str, dict] = {}
        for w in sm["worlds"]:
            for s in w["stages"]:
                label = f"{w['world']}-{s['stage']} {s['title'] or s['stage_key']}"
                self.entries.setdefault(s["stage_key"], dict(s, label=label, world_title=w["title"]))
        names = set(self.rom.stage_names())
        self.other_keys = []
        for k in sm["stage_files_not_in_main_game"]:
            self.entries[k] = {"stage_key": k, "label": k, "world": None, "stage": None, "title": None,
                               "loadable": k in names}
            self.other_keys.append(k)
        self.stages: Dict[str, StageState] = {}
        self.undo_stack: List[dict] = []
        self.redo_stack: List[dict] = []
        self._next_action = 1
        self.saved_action: Optional[int] = None       # id of the newest action included in the last save
        self.output_path: Optional[str] = None
        self.title = "Touch & Roll editor edits"

    # ---- stages
    def stage(self, key: str) -> StageState:
        if key not in self.stages:
            if key not in self.entries:
                raise EditorError(f"unknown stage {key}")
            self.stages[key] = StageState(self, self.entries[key])
        return self.stages[key]

    # ---- changes with undo
    def apply(self, key: str, changes: Dict[str, Tuple[int, ...]], label: str):
        st = self.stage(key)
        before = {t: st.edits.get(t) for t in changes}
        if all(st.current_raw(t) == v for t, v in changes.items()):
            return False
        st.set_raw(changes)                      # raises EditorError and leaves the stage unchanged
        self.undo_stack.append({"id": self._next_action, "key": key, "before": before, "after": dict(changes),
                                "label": label})
        self._next_action += 1
        self.redo_stack.clear()
        return True

    def change(self, key: str, obj_id: str, prop: str, value, label: Optional[str] = None) -> bool:
        st = self.stage(key)
        return self.apply(key, st.changes_for(obj_id, prop, value), label or f"{prop} of {obj_id}")

    def _restore(self, key, values):
        st = self.stage(key)
        edits = dict(st.edits)
        for t, v in values.items():
            if v is None:
                edits.pop(t, None)
            else:
                edits[t] = v
        st.edits, st.current, st.doc = st._rebuild(edits)

    def undo(self) -> Optional[dict]:
        if not self.undo_stack:
            return None
        a = self.undo_stack.pop()
        self._restore(a["key"], a["before"])
        self.redo_stack.append(a)
        return a

    def redo(self) -> Optional[dict]:
        if not self.redo_stack:
            return None
        a = self.redo_stack.pop()
        self._restore(a["key"], a["after"])
        self.undo_stack.append(a)
        return a

    def changed_stages(self) -> List[str]:
        return sorted(k for k, st in self.stages.items() if st.plan_edits())

    @property
    def edit_count(self) -> int:
        return sum(len(st.plan_edits()) for st in self.stages.values())

    @property
    def dirty(self) -> bool:
        """True when the edits differ from what was last saved (or nothing was saved and there are edits)."""
        top = self.undo_stack[-1]["id"] if self.undo_stack else None
        return top != self.saved_action

    # ---- plans
    def plan(self) -> dict:
        stages = []
        for k in self.changed_stages():
            st = self.stages[k]
            e = st.entry
            where = f"World {e['world']}-{e['stage']} {e.get('title') or ''}".strip() if e.get("world") else k
            stages.append({"stage_key": k, "file": self.rom.profile()["stage_file_format"].format(k),
                           "where": where, "edits": st.plan_edits()})
        p = {"schema": PLAN_SCHEMA, "title": self.title, "base_rom_sha1": self.rom_sha1, "stages": stages,
             "made_with": "tredit"}
        if self.output_path:
            p["editor_output_name"] = os.path.basename(self.output_path)
        return p

    def export_plan(self, path: str):
        if not self.changed_stages():
            raise EditorError("there are no edits to export")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.plan(), fh, indent=1)
            fh.write("\n")

    def import_plan(self, path: str) -> int:
        """Load edits from an edit plan or from a ROM copy's .patch.json; returns the number of edits."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise EditorError(f"cannot read {os.path.basename(path)}: {exc}") from None
        plan = data.get("plan") if data.get("schema") == "trcore.rom_patch_record/1" else data
        if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
            raise EditorError("not an edit plan (or a patch record that contains one)")
        if plan.get("base_rom_sha1") and plan["base_rom_sha1"].lower() != self.rom_sha1:
            raise EditorError("these edits were made for a different ROM file than the one open now")
        staged = []
        for s in plan.get("stages", []):
            key = s.get("stage_key")
            if key not in self.entries:
                raise EditorError(f"plan stage {key!r} is not in this ROM")
            st = self.stage(key)
            changes = {}
            for e in s.get("edits", []):
                t = e.get("target", "")
                try:
                    orig = st.original_raw(t)
                except (EditorError, ValueError, KeyError):
                    raise EditorError(f"{key}: unknown target {t!r}") from None
                field = t.rsplit(".", 1)[-1]
                if field in ("position", "translation", "matrix"):
                    frm, to = tuple(_q(v) for v in e["from"]), tuple(_q(v) for v in e["to"])
                else:
                    frm = (int(e["from"], 0) if isinstance(e["from"], str) else e["from"],)
                    to = (int(e["to"], 0) if isinstance(e["to"], str) else e["to"],)
                if frm != orig:
                    raise EditorError(f"{key} {t}: plan expects {e['from']}, the ROM has {[v / FX for v in orig]}")
                changes[t] = to
            staged.append((key, changes))
        n = 0
        for key, changes in staged:
            if changes:
                self.apply(key, changes, f"import {os.path.basename(path)}")
                n += len(changes)
        if plan.get("title"):
            self.title = plan["title"]
        return n

    # ---- saving
    def save(self, out_path: str, replace_own: bool = True) -> dict:
        """Write a ROM copy with all edits. replace_own allows replacing a copy this editor wrote before
        (checked against its patch record); the opened ROM itself is never replaced."""
        if not self.changed_stages():
            raise EditorError("there are no edits to save")
        out_abs = os.path.abspath(out_path)
        if out_abs == self.rom_path or (os.path.exists(out_abs) and os.path.samefile(out_abs, self.rom_path)):
            raise EditorError("that is the ROM you opened; save the edits to a new copy instead")
        try:
            rec = build_edit_rom(self.rom_path, out_abs, self.plan(), replace_own=replace_own)
        except (EditRefused, RomWriteRefused) as exc:
            raise EditorError(str(exc)) from None
        except PermissionError as exc:
            raise EditorError(f"could not write {os.path.basename(out_abs)} ({exc.strerror}); "
                              "if it is open in BizHawk, close the ROM there first") from None
        except OSError as exc:
            raise EditorError(f"could not write {os.path.basename(out_abs)}: {exc}") from None
        self.output_path = out_abs
        self.saved_action = self.undo_stack[-1]["id"] if self.undo_stack else None
        return rec


def verify_saved_rom(out_path: str, project: Project) -> List[str]:
    """Re-read a saved copy and confirm every changed stage decodes to the editor's bytes."""
    problems = []
    try:
        with open(out_path, "rb") as fh:
            rom = type(project.rom)(fh.read(), out_path)      # same ROM type/profile as the opened ROM
        fmt = project.rom.profile()["stage_file_format"]
        changed = set(project.changed_stages())
        for k in sorted(changed):
            got, _ = lz10.decode(rom.file_bytes(fmt.format(k)))
            if got != project.stages[k].current:
                problems.append(f"{k}: saved stage differs from the editor's bytes")
        for k in project.entries:
            path = fmt.format(k)
            if k not in changed and path in rom.id_by_path and rom.file_bytes(path) != project.rom.file_bytes(path):
                problems.append(f"{k}: an unedited stage changed")
    except (OSError, RomError, lz10.LZ10Error) as exc:
        problems.append(f"could not re-read the saved copy: {exc}")
    return problems


def _editor_output_record(rom_path: str, sha1: str) -> Optional[dict]:
    """The patch record next to rom_path if it says this exact file was written by trcore."""
    try:
        with open(patch_record_path(rom_path), "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(rec, dict) and rec.get("schema") == "trcore.rom_patch_record/1" \
            and (rec.get("output_rom") or {}).get("sha1") == sha1:
        return rec
    return None
