import hashlib
import json
import os
import shutil
import tempfile
import unittest

from trcore import lz10
from trcore.editplan import load_plan
from trcore.rom import NdsRom
from trcore.stc.edit import apply_edits
from tests.synth import IDENTITY, build_stage, with_cell_lists
from tests.synth_nsbmd import build_nsbmd
from tests.synth_rom import build_rom
from tredit.project import (EditorError, Project, angle_to_degrees, find_original_rom, goal_heading,
                            verify_saved_rom)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_ROM = os.environ.get("TRCORE_ROM")


class SynthProfiledRom(NdsRom):
    """A fabricated ROM given a minimal 'profile' and stage map so the editor can open it."""
    PROFILE = {"label": "synthetic", "stage_file_format": "stcoli/{}_stc.lz",
               "stage_model_format": "model/stage/{}_nsbmd.lz"}

    def profile(self):
        return self.PROFILE

    def stage_names(self):
        return ["s1", "s2"]

    def stage_map(self):
        return {"worlds": [{"world": 1, "title": "Test World", "stages": [
            {"world": 1, "stage": 1, "title": "One", "stage_id": 0, "stage_key": "s1",
             "file": "stcoli/s1_stc.lz", "flags": 0}]}],
            "stage_files_not_in_main_game": ["s2"]}


def make_synth(tmp):
    stage = with_cell_lists(build_stage(goals=((0, IDENTITY, (0, 0, -10)),),
                                        bananas=((1, 0.5, 2, 0), (-1, 0.5, 2, 1))))
    rom_bytes = build_rom([("stcoli", "s1_stc.lz", lz10.encode(stage)),
                           ("stcoli", "s2_stc.lz", lz10.encode(build_stage(groups=("A", "B")))),
                           ("model/stage", "s1_nsbmd.lz", lz10.encode(build_nsbmd()))])
    path = os.path.join(tmp, "base.nds")
    with open(path, "wb") as fh:
        fh.write(rom_bytes)
    return path


def open_synth(path):
    with open(path, "rb") as fh:
        return Project(path, SynthProfiledRom(fh.read(), path))


class ProjectBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tredit_")
        self.base = make_synth(self.tmp)
        with open(self.base, "rb") as fh:
            self.base_sha1 = hashlib.sha1(fh.read()).hexdigest()
        self.p = open_synth(self.base)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def objs(self, key="s1"):
        return {o["id"]: o for o in self.p.stage(key).objects()}

    def test_objects_and_model(self):
        o = self.objs()
        self.assertEqual(sorted(o), ["banana:0", "banana:1", "goal:0", "start:0"])
        self.assertEqual(o["start:0"]["heading"], 90.0)              # 0x4000
        self.assertEqual(o["goal:0"]["heading"], 180.0)              # identity: front = +z, faces the start
        self.assertFalse(o["goal:0"]["red"])
        self.assertTrue(o["banana:1"]["bunch"])
        self.assertEqual(o["banana:0"]["editable"], {"position", "bunch"})
        st = self.p.stage("s1")
        self.assertEqual(len(st.model["triangles"]), 3)
        self.assertIsNone(self.p.stage("s2").model)                 # no model file for s2
        self.assertFalse(self.p.changed_stages())

    def test_changes_are_reparsed_and_planned(self):
        p = self.p
        self.assertTrue(p.change("s1", "banana:0", "position", [1, 0.5, 4.00001]))
        self.assertEqual(self.objs()["banana:0"]["position"], [1.0, 0.5, 4.0])     # stored in 1/4096 steps
        p.change("s1", "goal:0", "heading", 270)
        self.assertEqual(self.objs()["goal:0"]["matrix"], [[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        p.change("s1", "goal:0", "red", True)
        p.change("s1", "start:0", "heading", 180)
        p.change("s1", "banana:1", "bunch", False)
        plan = p.plan()
        self.assertEqual(plan["base_rom_sha1"], self.base_sha1)
        edits = {e["target"]: e for e in plan["stages"][0]["edits"]}
        self.assertEqual(edits["start[0].u32_0C"]["to"], 0x8000)
        self.assertEqual(edits["pool_A[0].u32_30"]["to"], 1)
        self.assertEqual(edits["pool_C[1].u32_0C"]["to"], 0)
        self.assertEqual(edits["pool_A[0].matrix"]["to"], [0, 0, -1, 0, 1, 0, 1, 0, 0])
        st = p.stage("s1")
        self.assertEqual(st.current, apply_edits(st.original, plan["stages"][0]["edits"])[0])

    def test_turning_back_restores_original_bytes(self):
        p = self.p
        p.change("s1", "goal:0", "heading", 207.5)
        self.assertTrue(p.changed_stages())
        p.change("s1", "goal:0", "heading", 180)
        self.assertFalse(p.changed_stages())
        self.assertEqual(p.stage("s1").current, p.stage("s1").original)

    def test_undo_redo_dirty(self):
        p = self.p
        self.assertFalse(p.dirty)
        p.change("s1", "banana:0", "bunch", True)
        p.change("s1", "banana:0", "position", [2, 0.5, 2])
        self.assertTrue(p.dirty)
        p.undo()
        self.assertEqual(self.objs()["banana:0"]["position"], [1.0, 0.5, 2.0])
        self.assertTrue(self.objs()["banana:0"]["bunch"])
        p.undo()
        self.assertFalse(p.changed_stages())
        self.assertFalse(p.dirty)
        self.assertIsNone(p.undo())
        p.redo()
        p.redo()
        self.assertEqual(self.objs()["banana:0"]["position"], [2.0, 0.5, 2.0])
        self.assertFalse(p.change("s1", "banana:0", "position", [2, 0.5, 2]))   # no-op is not recorded

    def test_refusals(self):
        p = self.p
        for args in (("goal:9", "position", [0, 0, 0]), ("banana:0", "heading", 10), ("banana:0", "red", True),
                     ("start:0", "position", [0, 0]), ("goal:0", "position", [1e9, 0, 0])):
            with self.assertRaises(EditorError, msg=args):
                p.change("s1", *args)
        self.assertFalse(p.changed_stages())
        with self.assertRaises(EditorError):
            p.save(os.path.join(self.tmp, "nothing.nds"))

    def test_save_modes(self):
        p = self.p
        out = os.path.join(self.tmp, "hack.nds")
        p.change("s1", "goal:0", "red", True)
        rec = p.save(out)
        self.assertFalse(rec["replaced_previous_output"])
        self.assertEqual(rec["plan"]["stages"][0]["stage_key"], "s1")
        self.assertEqual(verify_saved_rom(out, p), [])
        self.assertFalse(p.dirty)
        p.change("s1", "banana:0", "bunch", True)
        rec2 = p.save(out)                                     # replace own copy
        self.assertTrue(rec2["replaced_previous_output"])
        self.assertEqual(verify_saved_rom(out, p), [])
        with open(out, "ab") as fh:                             # changed outside the editor
            fh.write(b"x")
        p.change("s1", "banana:1", "bunch", False)
        with self.assertRaises(EditorError):
            p.save(out)
        foreign = os.path.join(self.tmp, "foreign.nds")
        with open(foreign, "wb") as fh:
            fh.write(b"not ours")
        with self.assertRaises(EditorError):
            p.save(foreign)
        with self.assertRaises(EditorError):
            p.save(self.base)
        with self.assertRaises(EditorError):
            p.save(foreign, replace_own=False)
        new = os.path.join(self.tmp, "second.nds")
        p.save(new)
        with open(self.base, "rb") as fh:
            self.assertEqual(hashlib.sha1(fh.read()).hexdigest(), self.base_sha1)
        with open(foreign, "rb") as fh:
            self.assertEqual(fh.read(), b"not ours")

    def test_export_import(self):
        p = self.p
        p.change("s1", "goal:0", "heading", 90)
        p.change("s1", "banana:0", "position", [1, 0.5, 3])
        plan_path = os.path.join(self.tmp, "edits.plan.json")
        p.export_plan(plan_path)
        self.assertEqual(load_plan(plan_path)["stages"][0]["stage_key"], "s1")
        q = open_synth(self.base)
        self.assertEqual(q.import_plan(plan_path), 2)
        self.assertEqual(q.stage("s1").current, p.stage("s1").current)
        out = os.path.join(self.tmp, "h.nds")
        p.save(out)
        r = open_synth(self.base)
        self.assertEqual(r.import_plan(os.path.splitext(out)[0] + ".patch.json"), 2)
        bad = json.load(open(plan_path))
        bad["base_rom_sha1"] = "0" * 40
        with open(plan_path, "w") as fh:
            json.dump(bad, fh)
        with self.assertRaises(EditorError):
            open_synth(self.base).import_plan(plan_path)
        bad["base_rom_sha1"] = self.base_sha1
        bad["stages"][0]["edits"][1]["from"] = [9, 9, 9]
        with open(plan_path, "w") as fh:
            json.dump(bad, fh)
        s = open_synth(self.base)
        with self.assertRaises(EditorError):
            s.import_plan(plan_path)
        self.assertFalse(s.changed_stages())                   # all-or-nothing

    def test_opening_an_editor_copy_is_detected(self):
        p = self.p
        p.change("s1", "goal:0", "red", True)
        sub = os.path.join(self.tmp, "hacks")
        os.mkdir(sub)
        out = os.path.join(sub, "copy.nds")
        p.save(out)
        q = open_synth(out)
        self.assertIsNotNone(q.opened_editor_output)
        self.assertIsNone(self.p.opened_editor_output)
        self.assertEqual(find_original_rom(out, q.opened_editor_output), self.base)   # one folder up
        q.change("s1", "banana:0", "bunch", True)                                      # stacked edit
        rec = q.save(os.path.join(self.tmp, "stacked.nds"))
        chain = rec["base_rom_was_editor_copy"]
        self.assertEqual(chain["made_from"]["sha1"], self.base_sha1)
        self.assertEqual(chain["its_plan"]["stages"][0]["edits"][0]["target"], "pool_A[0].u32_30")


class ObjectsInTheEditor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tredit_obj_")
        self.base = make_synth(self.tmp)
        self.p = open_synth(self.base)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ids(self):
        return [o["id"] for o in self.p.stage("s1").objects()]

    def test_add_delete_duplicate_reset_undo(self):
        p = self.p
        nb = p.add_object("s1", "banana", [3, 0.5, -3], bunch=True)
        ng = p.add_object("s1", "goal", [0, 0, 5], heading=p.default_heading_towards_start("s1", (0, 0, 5)))
        objs = {o["id"]: o for o in p.stage("s1").objects()}
        self.assertTrue(objs[nb]["new"] and objs[nb]["bunch"])
        self.assertEqual(objs[ng]["label"], "New goal 1")
        self.assertAlmostEqual(objs[ng]["heading"], 180.0)               # start (0, 0, 10) is towards +z
        p.change("s1", ng, "heading", 90)
        p.change("s1", ng, "red", True)
        p.delete_object("s1", "banana:0")
        self.assertNotIn("banana:0", self.ids())
        dup = p.duplicate_object("s1", "banana:1")
        self.assertEqual({o["id"]: o for o in p.stage("s1").objects()}[dup]["position"], [0.0, 0.5, 2.0])
        self.assertEqual(p.plan()["schema"], "trcore.edit_plan/2")
        self.assertEqual(p.stage("s1").banana_value, 5 + 5 + 5)          # bunch kept, new bunch, duplicate of a bunch
        p.reset_object("s1", "banana:0")                                  # undelete
        self.assertIn("banana:0", self.ids())
        for _ in range(7):
            p.undo()
        self.assertFalse(p.changed_stages())
        for _ in range(7):
            p.redo()
        self.assertIn(ng, self.ids())
        with self.assertRaises(EditorError):
            p.delete_object("s1", "start:0")
        with self.assertRaises(EditorError):
            p.add_object("s1", "banana", [500, 0.5, 500])

    def test_banana_value_limit(self):
        p = self.p
        for i in range(49):
            p.add_object("s1", "banana", [i * 0.1 - 2, 0.5, 0], bunch=True)   # 6 + 245 = 251
        with self.assertRaises(EditorError):
            p.add_object("s1", "banana", [3, 0.5, 3], bunch=True)          # would be 256
        p.add_object("s1", "banana", [3, 0.5, 3])                            # 252 is fine
        self.assertEqual(p.stage("s1").banana_value, 252)

    def test_save_import_round_trip_with_objects(self):
        p = self.p
        p.delete_object("s1", "banana:1")
        p.add_object("s1", "goal", [2, 0, -2])
        p.change("s1", "banana:0", "position", [1, 0.5, 2.5])
        out = os.path.join(self.tmp, "objs.nds")
        rec = p.save(out)
        self.assertEqual(rec["plan_schema"], "trcore.edit_plan/2")
        self.assertEqual(verify_saved_rom(out, p), [])
        q = open_synth(self.base)
        self.assertEqual(q.import_plan(os.path.splitext(out)[0] + ".patch.json"), 3)
        self.assertEqual(q.stage("s1").current, p.stage("s1").current)


class Angles(unittest.TestCase):
    def test_conventions(self):
        self.assertEqual(angle_to_degrees(0x4000), 90.0)
        self.assertEqual(goal_heading([[1, 0, 0], [0, 1, 0], [0, 0, 1]]), 180.0)
        self.assertEqual(goal_heading([[0, 0, -1], [0, 1, 0], [1, 0, 0]]), 270.0)   # edit test 2, W1-3
        self.assertIsNone(goal_heading([[1, 0, 0], [0, 0, 1], [0, -1, 0]]))         # front points up


@unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
class ReproduceVerifiedEdits(unittest.TestCase):
    """The editor's own operations must produce exactly the bytes of the plans confirmed in-game."""

    @classmethod
    def setUpClass(cls):
        cls.rom = NdsRom.from_file(REAL_ROM)

    def reproduce(self, plan_rel):
        plan = load_plan(os.path.join(ROOT, plan_rel))
        p = Project(REAL_ROM, self.rom)
        for s in plan["stages"]:
            key = s.get("stage_key") or s["file"][len("stcoli/"):-len("_stc.lz")]
            for e in s["edits"]:
                head, field = e["target"].split(".")
                pool, idx = head.rstrip("]").split("[")
                kind = {"start": "start", "pool_A": "goal", "pool_B": "bumper", "pool_C": "banana"}[pool]
                oid = f"{kind}:{idx}"
                to = e["to"]
                if field in ("position", "translation"):
                    p.change(key, oid, "position", to)
                elif field == "u32_0C" and kind == "start":
                    p.change(key, oid, "heading", angle_to_degrees(int(to, 0) if isinstance(to, str) else to))
                elif field == "matrix":
                    p.change(key, oid, "heading", goal_heading([to[0:3], to[3:6], to[6:9]]))
                elif field == "u32_30":
                    p.change(key, oid, "red", bool(to))
                elif field == "u32_0C":
                    p.change(key, oid, "bunch", bool(to))
                else:
                    self.fail(f"unexpected field {field}")
            st = p.stage(key)
            expect = apply_edits(st.original, s["edits"])[0]
            self.assertEqual(st.current, expect, f"{plan_rel} {key}")

    def test_edit_test_1(self):
        self.reproduce("docs/experiments/edit1_world1/plan.json")

    def test_edit_test_2(self):
        self.reproduce("docs/experiments/edit2_bumpers_goals/plan.json")

    def test_far_moves_are_relisted_small_moves_stay_field_edits(self):
        p = Project(REAL_ROM, self.rom)
        objs = {o["id"]: o for o in p.stage("smb1_be01").objects()}
        x, y, z = objs["banana:0"]["position"]
        p.change("smb1_be01", "banana:0", "position", [x + 1.0, y, z])          # still in its cells
        st = p.stage("smb1_be01")
        self.assertEqual([e["target"] for e in st.plan_edits()], ["pool_C[0].position"])
        self.assertEqual(st.plan_ops(), [])
        p.change("smb1_be01", "banana:0", "position", [x + 9.0, y, z])          # leaves its cells
        self.assertEqual(st.plan_edits(), [])
        self.assertEqual([o["op"] for o in st.plan_ops()], ["move"])
        from trcore.stc import cells as CL
        g = CL.read_grids(st.current)[0]
        self.assertIsNone(CL.coverage_problem(g, "banana", 0, (x + 9.0, y, z)))
        with self.assertRaises(EditorError):                                      # off the grid: refused
            p.change("smb1_be01", "banana:1", "position", [3.45, 0.5, 40.0])

    def test_edit_test_3_through_editor_operations(self):
        """Adds, deletes and a far move made with the editor give the bytes of edit test 3 (seen in-game)."""
        from trcore.stc.objects import apply_object_ops
        plan = load_plan(os.path.join(ROOT, "docs/experiments/edit3_add_remove/plan.json"))
        by_key = {s["stage_key"]: s for s in plan["stages"]}
        p = Project(REAL_ROM, self.rom)
        p.delete_object("smb1_be01", "banana:4")
        p.add_object("smb1_be01", "banana", [-5.0, 0.5, -2.0])
        p.add_object("smb1_be01", "goal", [-3.5, 0.0, 0.0],
                     heading=p.default_heading_towards_start("smb1_be01", (-3.5, 0.0, 0.0)))
        p.add_object("smb1_ad02", "bumper", [0.0, 0.0, -20.0])
        p.delete_object("smb1_ad02", "bumper:8")
        p.change("smbds_023", "banana:11", "position", [0.0, 0.5, 30.5])
        for key in ("smb1_be01", "smb1_ad02"):
            st = p.stage(key)
            expect = apply_object_ops(st.original, by_key[key]["objects"], key)[0]
            self.assertEqual(st.current, expect, key)
        st = p.stage("smbds_023")
        self.assertEqual(st.current, apply_object_ops(st.original, by_key["smbds_023"]["objects"], "x")[0])
        self.assertEqual(p.plan()["schema"], "trcore.edit_plan/2")

    def test_every_main_stage_opens_with_a_model(self):
        p = Project(REAL_ROM, self.rom)
        for w in p.worlds:
            for s in w["stages"]:
                st = p.stage(s["stage_key"])
                self.assertTrue(st.model and st.model["triangles"], s["stage_key"])
                self.assertTrue(st.objects())


if __name__ == "__main__":
    unittest.main()
