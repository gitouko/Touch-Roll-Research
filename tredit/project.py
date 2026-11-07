"""Editor model: everything the editor does, without any GUI code.

The GUI only calls this module. Every change becomes an edit of a known field
(trcore.stc.edit), is applied to the stage's original bytes and parsed back;
what the editor shows is read from those re-parsed bytes, so the screen always
shows exactly what a save would write. Saving goes through
trcore.editplan.build_edit_rom (verified ROM copy + patch record).

Only fields whose meaning was confirmed in-game (evidence Level 4) can be
changed: start position and facing, goal position / facing / red flag, bumper
position, banana position / bunch flag. Goals, bumpers and bananas can be added
(to the stage's fixed part), deleted and moved anywhere inside the collision grid;
those changes go through trcore.stc.objects (edit test 3).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Dict, List, Optional, Tuple

from trcore import lz10
from trcore.editplan import PLAN_SCHEMA, PLAN_SCHEMA_V2, build_edit_rom
from trcore.nitro.nsbmd import NitroError
from trcore.rom import NdsRom, RomError
from trcore.romwrite import RomWriteRefused, patch_record_path
from trcore.stagemodel import group_kinds, load_stage_model
from trcore.stc.cells import KIND_POOL, CellError, coverage_problem, read_grids
from trcore.stc.document import StageDocument
from trcore.stc.edit import EditRefused, apply_edits
from trcore.stc.objects import MAX_BANANA_VALUE, ObjectEditRefused, apply_object_ops

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
PREFIX_KIND = {v: k for k, v in TARGET_PREFIX.items()}
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

OBJECT_KINDS = ("goal", "bumper", "banana")
POS_FIELD = {"goal": "translation", "bumper": "translation", "banana": "position"}
KIND_TITLE = {"start": "Start", "goal": "Goal", "bumper": "Bumper", "banana": "Banana"}
DEFAULT_HEIGHT = {"banana": 0.5, "bumper": 0.0, "goal": 0.0}
IDENTITY_ROWS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _empty_state() -> dict:
    return {"fields": {}, "positions": {}, "deleted": [], "added": []}


def _copy_state(st: dict) -> dict:
    return {"fields": dict(st["fields"]), "positions": dict(st["positions"]), "deleted": list(st["deleted"]),
            "added": [dict(a) for a in st["added"]]}


def _split_id(oid: str) -> Tuple[str, Optional[int], Optional[str]]:
    """'banana:3' -> ('banana', 3, None); 'banana:n2' -> ('banana', None, 'banana:n2')."""
    kind, rest = oid.split(":", 1)
    if kind not in KINDS:
        raise EditorError(f"unknown object {oid!r}")
    if rest.startswith("n"):
        return kind, None, oid
    return kind, int(rest), None


class StageState:
    """One stage: original bytes, the editing state, and the bytes/document rebuilt from it.

    State (plain data, snapshotted for undo):
      fields    {target: raw}   start fields and non-position fields of original objects
      positions {id: raw xyz}   moved original goals / bumpers / bananas
      deleted   [id]            removed original objects
      added     [{id, kind, group, pos, bunch, red, matrix}]   new objects (group 0)
    A moved original object stays a plain field edit while its original collision cells still cover it,
    and is re-listed (trcore.stc.objects "move") otherwise; additions and removals always go through
    trcore.stc.objects. The current bytes are always rebuilt from the original."""

    def __init__(self, project: "Project", entry: dict):
        self.project = project
        self.entry = entry
        self.key = entry["stage_key"]
        self.original = project.rom.stage_file_decoded(self.key)
        self.original_doc = StageDocument(self.original, self.key)
        if self.original_doc.has_errors():
            raise EditorError(f"{self.key}: stage file has structural errors; it can be viewed only with trcore")
        self.state = _empty_state()
        self.current = self.original
        self.doc = self.original_doc
        self.order: Dict[str, List[str]] = {}
        self._field_edits: List[dict] = []
        self._ops: List[dict] = []
        self._model = None
        self.model_error = None
        self._kinds = None
        self._grids = None
        self._compute_order(self.state)

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

    @property
    def grids(self):
        if self._grids is None:
            try:
                self._grids = read_grids(self.original)
            except CellError:
                self._grids = []
        return self._grids

    def can_restructure(self) -> Optional[str]:
        """None if objects can be added / removed / re-listed in this stage, else the reason."""
        if self.original_doc.layout_variant != "common":
            return "this stage file uses an unusual layout"
        if not self.grids or not self.grids[0].present:
            return "this stage's collision cells could not be read"
        return None

    # ---- original records
    def _record(self, kind: str, index: int, doc: Optional[StageDocument] = None) -> dict:
        doc = doc or self.original_doc
        src, pool, _f, _t = KINDS[kind]
        recs = (doc.start or {}).get("records", []) if src == "start" else doc.pools.get(pool, {}).get("records", [])
        if not 0 <= index < len(recs):
            raise EditorError(f"{kind} {index} does not exist")
        return recs[index]

    def original_raw(self, target: str) -> Tuple[int, ...]:
        prefix, rest = target.split("[", 1)
        idx, field = rest.split("].")
        kind = PREFIX_KIND[prefix]
        rec = self._record(kind, int(idx))
        if field in ("position", "translation"):
            return tuple(_q(v) for v in rec[field])
        if field == "matrix":
            return tuple(_q(v) for row in rec["matrix"] for v in row)
        return (rec[field],)

    def original_position(self, kind: str, index: int) -> Tuple[int, int, int]:
        return tuple(_q(v) for v in self._record(kind, index)[POS_FIELD[kind]])

    def _covered(self, kind: str, index: int, pos_raw) -> bool:
        """True if the object's ORIGINAL collision cells still cover pos_raw (or nothing can be re-listed)."""
        if self.can_restructure():
            return True
        rec = self._record(kind, index)
        g = rec["group"]
        if g >= len(self.grids) or not self.grids[g].present:
            return True
        recs = self.original_doc.pools[KIND_POOL[kind]]["records"]
        local = sum(1 for r in recs[:index] if r["group"] == g)
        pos = [v / FX for v in pos_raw]
        return coverage_problem(self.grids[g], kind, local, pos, rec[POS_FIELD[kind]]) is None

    # ---- composing the state into field edits + object operations
    @staticmethod
    def _edit_entry(target: str, orig, raw) -> dict:
        field = target.rsplit(".", 1)[1]
        if field in ("position", "translation", "matrix"):
            return {"target": target, "from": [v / FX for v in orig], "to": [v / FX for v in raw]}
        return {"target": target, "from": orig[0], "to": raw[0]}

    def _compose(self, state: dict) -> Tuple[List[dict], List[dict]]:
        deleted = set(state["deleted"])
        fields: Dict[str, Tuple[int, ...]] = {}
        for t, v in state["fields"].items():
            prefix, rest = t.split("[", 1)
            kind = PREFIX_KIND[prefix]
            if f"{kind}:{int(rest.split(']')[0])}" in deleted:
                continue
            if v != self.original_raw(t):
                fields[t] = v
        ops: List[dict] = []
        for oid in sorted(deleted, key=lambda x: (x.split(":")[0], int(x.split(":")[1]))):
            kind, i, _ = _split_id(oid)
            ops.append({"op": "remove", "kind": kind, "index": i,
                        "expect_position": [v / FX for v in self.original_position(kind, i)]})
        for oid, pos in sorted(state["positions"].items()):
            kind, i, _ = _split_id(oid)
            if oid in deleted or tuple(pos) == self.original_position(kind, i):
                continue
            if self._covered(kind, i, pos):
                fields[f"{TARGET_PREFIX[kind]}[{i}].{POS_FIELD[kind]}"] = tuple(pos)
            else:
                ops.append({"op": "move", "kind": kind, "index": i,
                            "from": [v / FX for v in self.original_position(kind, i)],
                            "to": [v / FX for v in pos]})
        for a in state["added"]:
            op = {"op": "add", "kind": a["kind"], "group": a["group"], "position": [v / FX for v in a["pos"]]}
            if a["kind"] == "banana":
                op["bunch"] = bool(a.get("bunch"))
            if a["kind"] == "goal":
                op["red"] = bool(a.get("red"))
                op["matrix"] = [v / FX for v in a["matrix"]]
            ops.append(op)
        edits = [self._edit_entry(t, self.original_raw(t), v) for t, v in sorted(fields.items())]
        return edits, ops

    def _compute_order(self, state: dict):
        """Stable ids of the records in the rebuilt pools, in pool order (mirrors trcore.stc.objects)."""
        deleted = set(state["deleted"])
        ngroups = len(self.original_doc.groups)
        for kind in OBJECT_KINDS:
            recs = self.original_doc.pools[KIND_POOL[kind]]["records"]
            added = [a for a in state["added"] if a["kind"] == kind]
            order = []
            for g in range(ngroups):
                order += [f"{kind}:{r['index']}" for r in recs if r["group"] == g and f"{kind}:{r['index']}" not in deleted]
                order += [a["id"] for a in added if a["group"] == g]
            self.order[kind] = order

    def set_state(self, state: dict):
        """Rebuild the stage from `state`; raises EditorError (and changes nothing) if it is refused."""
        edits, ops = self._compose(state)
        if ops and self.can_restructure():
            raise EditorError(f"objects cannot be added, removed or moved far here: {self.can_restructure()}")
        cur = self.original
        try:
            if edits:
                cur, _ = apply_edits(cur, edits, self.key)
            if ops:
                cur, _ = apply_object_ops(cur, ops, self.key)
        except (EditRefused, ObjectEditRefused) as exc:
            raise EditorError(str(exc)) from None
        doc = StageDocument(cur, self.key) if cur is not self.original else self.original_doc
        value = banana_value(doc)
        if value > MAX_BANANA_VALUE:
            raise EditorError(f"the stage's banana value would be {value}; the game counts it in one byte "
                              f"(at most {MAX_BANANA_VALUE}; a bunch counts 5)")
        old_order = self.order
        self._compute_order(state)
        for kind in OBJECT_KINDS:
            if len(self.order[kind]) != len(doc.pools[KIND_POOL[kind]]["records"]):
                self.order = old_order
                raise EditorError("internal: object order does not match the rebuilt stage")
        self.state = _copy_state(state)
        self.current, self.doc = cur, doc
        self._field_edits, self._ops = edits, ops

    # ---- what a plan / save contains
    def plan_edits(self) -> List[dict]:
        return list(self._field_edits)

    def plan_ops(self) -> List[dict]:
        return list(self._ops)

    @property
    def changed(self) -> bool:
        return bool(self._field_edits or self._ops)

    @property
    def banana_value(self) -> int:
        return banana_value(self.doc)

    # ---- object view for the GUI
    def objects(self) -> List[dict]:
        out = []
        kinds = self.group_kinds
        names = {g["index"]: g.get("name_text_04") for g in self.doc.groups}
        st = self.state
        moved = {oid for oid, pos in st["positions"].items()
                 if tuple(pos) != self.original_position(*_split_id(oid)[:2])}
        field_objs = set()
        for t in st["fields"]:
            if st["fields"][t] != self.original_raw(t):
                prefix, rest = t.split("[", 1)
                field_objs.add(f"{PREFIX_KIND[prefix]}:{int(rest.split(']')[0])}")
        new_number = {}
        for kind in OBJECT_KINDS:
            for n, a in enumerate([a for a in st["added"] if a["kind"] == kind]):
                new_number[a["id"]] = n + 1
        for kind in ("start",) + OBJECT_KINDS:
            src, pool, pfield, _t = KINDS[kind]
            recs = (self.doc.start or {}).get("records", []) if src == "start" \
                else self.doc.pools.get(pool, {}).get("records", [])
            ids = [f"start:{r['index']}" for r in recs] if kind == "start" else self.order[kind]
            for rec, oid in zip(recs, ids):
                _k, orig_i, new_id = _split_id(oid)
                grp = 0 if kind == "start" else rec["group"]
                is_new = new_id is not None
                label = (f"New {KIND_TITLE[kind].lower()} {new_number.get(new_id, '?')}" if is_new
                         else f"{KIND_TITLE[kind]} {orig_i + 1}")
                o = {"id": oid, "kind": kind, "index": orig_i, "label": label, "new": is_new, "group": grp,
                     "group_name": names.get(grp), "group_kind": kinds.get(grp), "in_moving_group": bool(grp),
                     "position": list(rec[pfield]), "editable": {"position"}, "heading": None,
                     "offset": rec["offset"], "collision_warning": None,
                     "changed": is_new or oid in moved or oid in field_objs,
                     "deletable": kind != "start" and not self.can_restructure()}
                if kind == "start":
                    o["heading"] = angle_to_degrees(rec["u32_0C"])
                    o["editable"].add("heading")
                elif kind == "goal":
                    o["heading"] = goal_heading(rec["matrix"])
                    o["matrix"] = rec["matrix"]
                    o["red"] = rec["u32_30"] == 1
                    o["editable"].add("red")
                    base_m = IDENTITY_ROWS if is_new else self._record("goal", orig_i)["matrix"]
                    if o["heading"] is not None and goal_heading(base_m) is not None:
                        o["editable"].add("heading")
                elif kind == "bumper":
                    o["matrix"] = rec["matrix"]
                elif kind == "banana":
                    o["bunch"] = rec["u32_0C"] == 1
                    o["editable"].add("bunch")
                out.append(o)
        return out

    # ---- state changes (pure: return a new state)
    def _added(self, state: dict, new_id: str) -> dict:
        for a in state["added"]:
            if a["id"] == new_id:
                return a
        raise EditorError(f"{new_id} does not exist")

    def mutate(self, state: dict, obj_id: str, prop: str, value) -> dict:
        kind, i, new_id = _split_id(obj_id)
        st = _copy_state(state)
        if obj_id in st["deleted"]:
            raise EditorError(f"{obj_id} was deleted")
        if prop == "position":
            vals = tuple(_q(float(v)) for v in value) if isinstance(value, (list, tuple)) else ()
            if len(vals) != 3:
                raise EditorError("position needs x, y, z")
            if new_id:
                self._added(st, new_id)["pos"] = vals
            elif kind == "start":
                st["fields"][f"start[{i}].position"] = vals
            elif vals == self.original_position(kind, i):
                st["positions"].pop(obj_id, None)
            else:
                st["positions"][obj_id] = vals
            return st
        if prop == "heading" and kind == "start":
            t = f"start[{i}].u32_0C"
            st["fields"][t] = (degrees_to_angle(float(value), self.original_raw(t)[0]),)
            return st
        if prop == "heading" and kind == "goal":
            base_m = IDENTITY_ROWS if new_id else self._record("goal", i)["matrix"]
            h0 = goal_heading(base_m)
            if h0 is None:
                raise EditorError("this goal points straight up or down; its facing cannot be edited")
            d = (float(value) - h0) % 360.0
            same = abs(d) < 1e-9 or abs(d - 360.0) < 1e-9
            rows = base_m if same else rotate_matrix(base_m, d)
            raw = tuple(_q(v) for row in rows for v in row)
            if new_id:
                self._added(st, new_id)["matrix"] = raw
            else:
                st["fields"][f"pool_A[{i}].matrix"] = raw
            return st
        if (kind, prop) in FLAG_TARGET:
            if new_id:
                self._added(st, new_id)[prop] = bool(value)
            else:
                st["fields"][f"{TARGET_PREFIX[kind]}[{i}].{FLAG_TARGET[(kind, prop)]}"] = (1 if value else 0,)
            return st
        raise EditorError(f"{prop} of a {kind} cannot be edited")


def banana_value(doc: StageDocument) -> int:
    return sum(5 if r["u32_0C"] == 1 else 1 if r["u32_0C"] == 0 else 0 for r in doc.pools["C"]["records"])


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
        self._next_new = 1
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
    def _commit(self, key: str, new_state: dict, label: str) -> bool:
        st = self.stage(key)
        if new_state == st.state:
            return False
        before = _copy_state(st.state)
        st.set_state(new_state)                  # raises EditorError and leaves the stage unchanged
        self.undo_stack.append({"id": self._next_action, "key": key, "before": before,
                                "after": _copy_state(st.state), "label": label})
        self._next_action += 1
        self.redo_stack.clear()
        return True

    def change(self, key: str, obj_id: str, prop: str, value, label: Optional[str] = None) -> bool:
        st = self.stage(key)
        return self._commit(key, st.mutate(st.state, obj_id, prop, value), label or f"{prop} of {obj_id}")

    def add_object(self, key: str, kind: str, position, bunch: bool = False, red: bool = False,
                   heading: Optional[float] = None, group: int = 0) -> str:
        """Add a goal, bumper or banana (to the stage's fixed part); returns the new object's id."""
        if kind not in OBJECT_KINDS:
            raise EditorError(f"cannot add a {kind}")
        st = self.stage(key)
        why = st.can_restructure()
        if why:
            raise EditorError(f"objects cannot be added here: {why}")
        new_id = f"{kind}:n{self._next_new}"
        pos = tuple(_q(float(v)) for v in position)
        if len(pos) != 3:
            raise EditorError("position needs x, y, z")
        a = {"id": new_id, "kind": kind, "group": group, "pos": pos, "bunch": bool(bunch), "red": bool(red)}
        if kind == "goal":
            rows = IDENTITY_ROWS
            if heading is not None:
                d = (float(heading) - 180.0) % 360.0
                rows = rows if abs(d) < 1e-9 else rotate_matrix(IDENTITY_ROWS, d)
            a["matrix"] = tuple(_q(v) for row in rows for v in row)
        state = _copy_state(st.state)
        state["added"].append(a)
        self._commit(key, state, f"add {kind}")
        self._next_new += 1
        return new_id

    def default_heading_towards_start(self, key: str, position) -> Optional[float]:
        """Facing that points a new goal's front at the stage's first start."""
        starts = (self.stage(key).doc.start or {}).get("records", [])
        if not starts:
            return None
        sx, _sy, sz = starts[0]["position"]
        dx, dz = sx - position[0], sz - position[2]
        if math.hypot(dx, dz) < 1e-6:
            return None
        return math.degrees(math.atan2(-dx, -dz)) % 360.0

    def delete_object(self, key: str, obj_id: str) -> bool:
        kind, i, new_id = _split_id(obj_id)
        if kind == "start":
            raise EditorError("starts cannot be deleted")
        st = self.stage(key)
        why = st.can_restructure()
        if why:
            raise EditorError(f"objects cannot be deleted here: {why}")
        state = _copy_state(st.state)
        if new_id:
            state["added"] = [a for a in state["added"] if a["id"] != new_id]
        else:
            if obj_id in state["deleted"]:
                return False
            state["deleted"].append(obj_id)
            state["positions"].pop(obj_id, None)
            prefix = f"{TARGET_PREFIX[kind]}[{i}]."
            state["fields"] = {t: v for t, v in state["fields"].items() if not t.startswith(prefix)}
        return self._commit(key, state, f"delete {obj_id}")

    def duplicate_object(self, key: str, obj_id: str, offset=(1.0, 0.0, 0.0)) -> str:
        o = {x["id"]: x for x in self.stage(key).objects()}.get(obj_id)
        if not o or o["kind"] == "start":
            raise EditorError("select a goal, bumper or banana to duplicate")
        pos = [o["position"][k] + offset[k] for k in range(3)]
        return self.add_object(key, o["kind"], pos, bunch=bool(o.get("bunch")), red=bool(o.get("red")),
                               heading=o.get("heading"))

    def reset_object(self, key: str, obj_id: str) -> bool:
        """Undo every change of one ORIGINAL object (position, flags, facing, deletion)."""
        kind, i, new_id = _split_id(obj_id)
        if new_id:
            raise EditorError("a new object has no original to go back to; delete it instead")
        st = self.stage(key)
        state = _copy_state(st.state)
        prefix = f"{TARGET_PREFIX[kind]}[{i}]."
        state["fields"] = {t: v for t, v in state["fields"].items() if not t.startswith(prefix)}
        state["positions"].pop(obj_id, None)
        state["deleted"] = [d for d in state["deleted"] if d != obj_id]
        return self._commit(key, state, f"reset {obj_id}")

    def _restore(self, key, state):
        self.stage(key).set_state(state)

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
        return sorted(k for k, st in self.stages.items() if st.changed)

    @property
    def edit_count(self) -> int:
        return sum(len(st.plan_edits()) + len(st.plan_ops()) for st in self.stages.values())

    @property
    def dirty(self) -> bool:
        """True when the edits differ from what was last saved (or nothing was saved and there are edits)."""
        top = self.undo_stack[-1]["id"] if self.undo_stack else None
        return top != self.saved_action

    # ---- plans
    def plan(self) -> dict:
        stages = []
        uses_objects = False
        for k in self.changed_stages():
            st = self.stages[k]
            e = st.entry
            where = f"World {e['world']}-{e['stage']} {e.get('title') or ''}".strip() if e.get("world") else k
            entry = {"stage_key": k, "file": self.rom.profile()["stage_file_format"].format(k), "where": where}
            if st.plan_edits():
                entry["edits"] = st.plan_edits()
            if st.plan_ops():
                entry["objects"] = st.plan_ops()
                uses_objects = True
            stages.append(entry)
        p = {"schema": PLAN_SCHEMA_V2 if uses_objects else PLAN_SCHEMA, "title": self.title,
             "base_rom_sha1": self.rom_sha1, "stages": stages, "made_with": "tredit"}
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
        """Load edits from an edit plan or from a ROM copy's .patch.json; returns the number of changes."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise EditorError(f"cannot read {os.path.basename(path)}: {exc}") from None
        plan = data.get("plan") if isinstance(data, dict) and data.get("schema") == "trcore.rom_patch_record/1" else data
        if not isinstance(plan, dict) or plan.get("schema") not in (PLAN_SCHEMA, PLAN_SCHEMA_V2):
            raise EditorError("not an edit plan (or a patch record that contains one)")
        if plan.get("base_rom_sha1") and plan["base_rom_sha1"].lower() != self.rom_sha1:
            raise EditorError("these edits were made for a different ROM file than the one open now")
        staged = []
        next_new = self._next_new
        for s in plan.get("stages", []):
            key = s.get("stage_key")
            if key not in self.entries:
                raise EditorError(f"plan stage {key!r} is not in this ROM")
            st = self.stage(key)
            state = _copy_state(st.state)
            n = 0
            for e in s.get("edits", []):
                t = e.get("target", "")
                try:
                    orig = st.original_raw(t)
                except (EditorError, ValueError, KeyError, IndexError):
                    raise EditorError(f"{key}: unknown target {t!r}") from None
                field = t.rsplit(".", 1)[-1]
                if field in ("position", "translation", "matrix"):
                    frm, to = tuple(_q(v) for v in e["from"]), tuple(_q(v) for v in e["to"])
                else:
                    frm = (int(e["from"], 0) if isinstance(e["from"], str) else e["from"],)
                    to = (int(e["to"], 0) if isinstance(e["to"], str) else e["to"],)
                if frm != orig:
                    raise EditorError(f"{key} {t}: plan expects {e['from']}, the ROM has {[v / FX for v in orig]}")
                prefix, rest = t.split("[", 1)
                kind = PREFIX_KIND[prefix]
                if kind in OBJECT_KINDS and field == POS_FIELD[kind]:
                    state["positions"][f"{kind}:{int(rest.split(']')[0])}"] = to
                else:
                    state["fields"][t] = to
                n += 1
            for op in s.get("objects", []):
                kind = op.get("kind")
                if kind not in OBJECT_KINDS:
                    raise EditorError(f"{key}: unknown object kind {kind!r}")
                if op.get("op") in ("remove", "move"):
                    i = op.get("index")
                    try:
                        orig = st.original_position(kind, i)
                    except (EditorError, TypeError):
                        raise EditorError(f"{key}: {kind} {i!r} does not exist") from None
                    want = op.get("expect_position") if op["op"] == "remove" else op.get("from")
                    if want is None or tuple(_q(v) for v in want) != orig:
                        raise EditorError(f"{key}: {kind} {i} is not where the plan expects it")
                    if op["op"] == "remove":
                        state["deleted"].append(f"{kind}:{i}")
                    else:
                        state["positions"][f"{kind}:{i}"] = tuple(_q(v) for v in op["to"])
                elif op.get("op") == "add":
                    a = {"id": f"{kind}:n{next_new}", "kind": kind, "group": int(op.get("group", 0)),
                         "pos": tuple(_q(v) for v in op["position"]), "bunch": bool(op.get("bunch")),
                         "red": bool(op.get("red"))}
                    if kind == "goal":
                        m = op.get("matrix")
                        a["matrix"] = tuple(_q(v) for v in m) if m else tuple(_q(v) for r in IDENTITY_ROWS for v in r)
                    next_new += 1
                    state["added"].append(a)
                else:
                    raise EditorError(f"{key}: unknown object operation {op.get('op')!r}")
                n += 1
            staged.append((key, state, n))
        applied = []
        try:
            for key, state, n in staged:
                if n:
                    before = _copy_state(self.stage(key).state)
                    self.stage(key).set_state(state)
                    applied.append((key, before, n))
        except EditorError:
            for key, before, _n in applied:             # all or nothing
                self.stage(key).set_state(before)
            raise
        for key, before, _n in applied:
            self.undo_stack.append({"id": self._next_action, "key": key, "before": before,
                                    "after": _copy_state(self.stage(key).state),
                                    "label": f"import {os.path.basename(path)}"})
            self._next_action += 1
        if applied:
            self.redo_stack.clear()
        self._next_new = next_new
        if plan.get("title"):
            self.title = plan["title"]
        return sum(n for _k, _b, n in applied)

    # ---- saving
    def save(self, out_path: str, replace_own: bool = True) -> dict:
        """Write a ROM copy with all edits. replace_own allows replacing a copy this editor wrote before
        (checked against its patch record); the opened ROM itself is never replaced."""
        if not self.changed_stages():
            raise EditorError("there are no edits to save")
        out_abs = os.path.abspath(out_path)
        if out_abs == self.rom_path or (os.path.exists(out_abs) and os.path.samefile(out_abs, self.rom_path)):
            raise EditorError("that is the ROM you opened; save the edits to a new copy instead")
        base_info = None
        if self.opened_editor_output:          # edits are stacked on an earlier editor copy: keep the chain
            r = self.opened_editor_output
            base_info = {"base_rom_was_editor_copy": {
                "name": os.path.basename(self.rom_path), "sha1": self.rom_sha1,
                "made_from": r.get("input_rom"), "its_plan": r.get("plan")}}
        try:
            rec = build_edit_rom(self.rom_path, out_abs, self.plan(), replace_own=replace_own, extra=base_info)
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


def find_original_rom(copy_path: str, record: dict) -> Optional[str]:
    """Look next to an editor-made copy (and one folder up) for the ROM its record says it was made from."""
    want = ((record or {}).get("input_rom") or {}).get("sha1")
    if not want:
        return None
    size = os.path.getsize(copy_path)
    here = os.path.dirname(os.path.abspath(copy_path))
    seen = set()
    for folder in (here, os.path.dirname(here)):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for n in names:
            cand = os.path.join(folder, n)
            if not n.lower().endswith(".nds") or cand in seen or os.path.abspath(cand) == os.path.abspath(copy_path):
                continue
            seen.add(cand)
            try:
                if os.path.getsize(cand) != size:
                    continue
                h = hashlib.sha1()
                with open(cand, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
            except OSError:
                continue
            if h.hexdigest() == want:
                return cand
    return None


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
