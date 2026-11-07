"""Apply an edit plan (JSON) to stage files and write a NEW ROM copy.

Plan format (schema "trcore.edit_plan/1"; "trcore.edit_plan/2" additionally allows an "objects" list
per stage with add / remove / move operations, see trcore/stc/objects.py):
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
from .stc.objects import ObjectEditRefused, apply_object_ops

PLAN_SCHEMA = "trcore.edit_plan/1"          # field edits only
PLAN_SCHEMA_V2 = "trcore.edit_plan/2"       # field edits + "objects" (add / remove / move, trcore/stc/objects.py)
PLAN_SCHEMAS = (PLAN_SCHEMA, PLAN_SCHEMA_V2)


def check_plan(plan: dict) -> dict:
    if plan.get("schema") not in PLAN_SCHEMAS:
        raise EditRefused(f"plan schema must be one of {PLAN_SCHEMAS}")
    if not plan.get("stages"):
        raise EditRefused("plan has no stages")
    for st in plan["stages"]:
        if st.get("objects") and plan["schema"] != PLAN_SCHEMA_V2:
            raise EditRefused(f"object operations need schema {PLAN_SCHEMA_V2!r}")
        if not st.get("edits") and not st.get("objects"):
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
        obj_report = None
        if st.get("objects"):
            try:
                new_dec, obj_report = apply_object_ops(new_dec, st["objects"], label)
            except ObjectEditRefused as exc:
                raise EditRefused(f"{label}: {exc}") from None
        new_comp = lz10.encode(new_dec)
        if lz10.decode(new_comp)[0] != new_dec:
            raise EditRefused(f"{label}: compressed stage does not decode back to the edited bytes")
        replacements.append((path, new_comp, False))
        stage_records.append({"file": path, "stage_key": st.get("stage_key"), "where": st.get("where"),
                              "decoded_size": len(dec), "decoded_size_after": len(new_dec),
                              "decoded_sha256_before": hashlib.sha256(dec).hexdigest(),
                              "decoded_sha256_after": hashlib.sha256(new_dec).hexdigest(),
                              "edits": recs, "objects": obj_report})
    return romwrite.write_rom_copy_multi(
        rom_path, out_path, replacements, note=plan.get("title"),
        extra={"plan_schema": plan["schema"], "stage_edits": stage_records,
               "status": "generated - not yet verified in-game", "plan": plan, **(extra or {})},
        replace_own=replace_own)
