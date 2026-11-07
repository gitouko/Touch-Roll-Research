"""Apply an edit plan (JSON) to stage files and write a NEW ROM copy.

Plan format (schema "trcore.edit_plan/1"; "trcore.edit_plan/2" additionally allows an "objects" list
per stage with add / remove / move operations, see trcore/stc/objects.py; "trcore.edit_plan/3" also
allows "collision" (remove_box / add_polygons, trcore/stc/geometry_edit.py) and "model"
({"op": "add_polygons", "shape": name, "polygons": [...]}, trcore/nitro/nsbmd_write.py), which
replaces the stage's model file as well):
{
  "schema": "trcore.edit_plan/1",
  "title": "short description",
  "base_rom_sha1": "<sha1 of the ROM the plan was written for>",   (optional but recommended)
  "stages": [
    {"stage_key": "smb1_be01",               (or "file": "stcoli/smb1_be01_stc.lz")
     "where": "World 1-1 Elementary",        (free text)
     "edits": [{"target": "pool_C[1].position", "from": [3.45, 0.5, 0], "to": [3.45, 0.5, 2],
                "prediction": "what should be seen in-game"}]}
  ]
}
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from . import lz10, romwrite
from .rom import NdsRom
from .stc.edit import EditRefused, apply_edits
from .nitro.nsbmd_write import ModelEditRefused, append_polygons
from .stc.geometry_edit import CollisionEditRefused, apply_collision_ops
from .stc.objects import ObjectEditRefused, apply_object_ops

PLAN_SCHEMA = "trcore.edit_plan/1"          # field edits only
PLAN_SCHEMA_V2 = "trcore.edit_plan/2"       # field edits + "objects" (add / remove / move, trcore/stc/objects.py)
PLAN_SCHEMA_V3 = "trcore.edit_plan/3"       # + "collision" and "model" (geometry, Milestone 4)
PLAN_SCHEMAS = (PLAN_SCHEMA, PLAN_SCHEMA_V2, PLAN_SCHEMA_V3)


def check_plan(plan: dict) -> dict:
    if plan.get("schema") not in PLAN_SCHEMAS:
        raise EditRefused(f"plan schema must be one of {PLAN_SCHEMAS}")
    if not plan.get("stages"):
        raise EditRefused("plan has no stages")
    level = PLAN_SCHEMAS.index(plan["schema"])
    for st in plan["stages"]:
        if st.get("objects") and level < 1:
            raise EditRefused(f"object operations need schema {PLAN_SCHEMA_V2!r} or later")
        if (st.get("collision") or st.get("model")) and level < 2:
            raise EditRefused(f"collision and model operations need schema {PLAN_SCHEMA_V3!r}")
        if st.get("model") and not (st.get("stage_key") or st.get("model_file")):
            raise EditRefused("model operations need 'stage_key' (the model file is found from it) or 'model_file'")
        if not any(st.get(k) for k in ("edits", "objects", "collision", "model")):
            raise EditRefused(f"{st.get('stage_key') or st.get('file')}: nothing to do")
    return plan


def load_plan(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        plan = json.load(fh)
    return check_plan(plan)


def build_edit_rom(rom_path: str, out_path: str, plan: dict, replace_own: bool = False,
                   extra: Optional[dict] = None) -> dict:
    check_plan(plan)
    rom = NdsRom.from_file(rom_path)
    sha1 = hashlib.sha1(rom.data).hexdigest()
    if plan.get("base_rom_sha1") and plan["base_rom_sha1"].lower() != sha1:
        raise EditRefused(f"plan was written for ROM {plan['base_rom_sha1']}, this ROM is {sha1}")
    prof = rom.profile()
    replacements, stage_records, seen = [], [], set()
    for st in plan["stages"]:
        path = st.get("file")
        if not path:
            if not prof or not st.get("stage_key"):
                raise EditRefused("each stage needs 'file', or 'stage_key' on a profiled ROM")
            path = prof["stage_file_format"].format(st["stage_key"])
        if path in seen:
            raise EditRefused(f"{path} appears twice in the plan; put all its edits in one entry")
        seen.add(path)
        comp = rom.file_bytes(path)
        dec, _ = lz10.decode(comp)
        label = st.get("stage_key") or path
        new_dec, recs = apply_edits(dec, st["edits"], label) if st.get("edits") else (dec, [])
        obj_report = coll_report = None
        model_record = None
        if st.get("objects"):
            try:
                new_dec, obj_report = apply_object_ops(new_dec, st["objects"], label)
            except ObjectEditRefused as exc:
                raise EditRefused(f"{label}: {exc}") from None
        if st.get("collision"):
            try:
                new_dec, coll_report = apply_collision_ops(new_dec, st["collision"], label)
            except CollisionEditRefused as exc:
                raise EditRefused(f"{label} collision: {exc}") from None
        if new_dec != dec:
            new_comp = lz10.encode(new_dec)
            if lz10.decode(new_comp)[0] != new_dec:
                raise EditRefused(f"{label}: compressed stage does not decode back to the edited bytes")
            replacements.append((path, new_comp, False))
        if st.get("model"):
            mpath = st.get("model_file")
            if not mpath:
                if not prof or "stage_model_format" not in prof or not st.get("stage_key"):
                    raise EditRefused("model operations need 'model_file', or 'stage_key' on a recognised ROM")
                mpath = prof["stage_model_format"].format(st["stage_key"])
            if mpath in seen:
                raise EditRefused(f"{mpath} appears twice in the plan")
            seen.add(mpath)
            mcomp = rom.file_bytes(mpath)
            compressed = mcomp[:1] == b"\x10"
            mdec = lz10.decode(mcomp)[0] if compressed else mcomp
            new_m, mreps = mdec, []
            by_shape: dict = {}                 # one append per shape: its display list is copied once
            for k, mop in enumerate(st["model"]):
                if mop.get("op") != "add_polygons":
                    raise EditRefused(f"{label} model op {k}: only add_polygons is supported")
                if not mop.get("polygons"):
                    raise EditRefused(f"{label} model op {k}: no polygons")
                by_shape.setdefault(mop.get("shape"), []).append(mop)
            for shape, mops in by_shape.items():
                polys = [p for mop in mops for p in mop["polygons"]]
                try:
                    new_m, mrep = append_polygons(new_m, shape, polys, label)
                except ModelEditRefused as exc:
                    raise EditRefused(f"{label} model: {exc}") from None
                mrep["ops"] = [{"label": mop.get("label"), "test": mop.get("test"),
                                "polygons": len(mop["polygons"])} for mop in mops]
                mreps.append(mrep)
            mout = lz10.encode(new_m) if compressed else new_m
            if compressed and lz10.decode(mout)[0] != new_m:
                raise EditRefused(f"{label}: compressed model does not decode back to the edited bytes")
            replacements.append((mpath, mout, False))
            model_record = {"file": mpath, "size_before": len(mdec), "size_after": len(new_m),
                            "sha256_before": hashlib.sha256(mdec).hexdigest(),
                            "sha256_after": hashlib.sha256(new_m).hexdigest(), "ops": mreps}
        stage_records.append({"file": path, "stage_key": st.get("stage_key"), "where": st.get("where"),
                              "decoded_size": len(dec), "decoded_size_after": len(new_dec),
                              "decoded_sha256_before": hashlib.sha256(dec).hexdigest(),
                              "decoded_sha256_after": hashlib.sha256(new_dec).hexdigest(),
                              "edits": recs, "objects": obj_report, "collision": coll_report,
                              "model": model_record})
    return romwrite.write_rom_copy_multi(
        rom_path, out_path, replacements, note=plan.get("title"),
        extra={"plan_schema": plan["schema"], "stage_edits": stage_records,
               "status": "generated - not yet verified in-game", "plan": plan, **(extra or {})},
        replace_own=replace_own)
