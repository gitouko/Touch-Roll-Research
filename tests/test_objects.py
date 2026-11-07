import os
import struct
import unittest

from trcore import lz10
from trcore.stc import cells as CL
from trcore.stc.document import StageDocument
from trcore.stc.objects import ObjectEditRefused, apply_object_ops
from tests.synth import IDENTITY, build_stage, with_cell_lists

REAL_ROM = os.environ.get("TRCORE_ROM")


def listed_stage():
    """Synthetic stage whose bananas and goal are listed in its 2x3 grid."""
    return with_cell_lists(build_stage(goals=((0, IDENTITY, (0, 0, -10)),),
                                       bananas=((1, 0.5, 2, 0), (-1, 0.5, 2, 1), (5, 0.5, 15, 0))))


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.base = listed_stage()
        self.grid = CL.read_grids(self.base)[0]

    def test_everything_listed(self):
        for i in range(3):
            self.assertTrue(self.grid.listed(6, i))
        self.assertTrue(self.grid.listed(4, 0))

    def test_remove_keeps_other_cells_and_renumbers(self):
        before = [self.grid.listed(6, i) for i in range(3)]
        new, rep = apply_object_ops(self.base, [{"op": "remove", "kind": "banana", "index": 0,
                                                 "expect_position": [1, 0.5, 2]}])
        doc = StageDocument(new)
        self.assertEqual(doc.pool_totals["C"], 2)
        self.assertEqual([r["position"] for r in doc.pools["C"]["records"]], [[-1.0, 0.5, 2.0], [5.0, 0.5, 15.0]])
        g = CL.read_grids(new)[0]
        self.assertEqual(g.listed(6, 0), before[1])
        self.assertEqual(g.listed(6, 1), before[2])
        self.assertEqual(rep["banana_value"], 6)
        self.assertEqual(new[:0x40], self.base[:0x40])          # header untouched before the totals
        self.assertEqual(lz10.decode(lz10.encode(new))[0], new)

    def test_add_goal_and_banana(self):
        new, rep = apply_object_ops(self.base, [
            {"op": "add", "kind": "goal", "group": 0, "position": [0, 0, 5], "rotation_like": 0, "red": True},
            {"op": "add", "kind": "banana", "group": 0, "position": [-5, 0.5, -5], "bunch": True}])
        doc = StageDocument(new)
        self.assertEqual((doc.pool_totals["A"], doc.pool_totals["C"]), (2, 4))
        goal = doc.pools["A"]["records"][1]
        self.assertEqual((goal["translation"], goal["u32_30"]), ([0.0, 0.0, 5.0], 1))
        self.assertEqual(doc.pools["C"]["records"][3]["u32_0C"], 1)
        g = CL.read_grids(new)[0]
        self.assertTrue(g.listed(4, 1) and g.listed(6, 3))
        self.assertEqual(g.listed(4, 0), self.grid.listed(4, 0))
        self.assertEqual(rep["banana_value"], 12)

    def test_refusals(self):
        bad = [
            [{"op": "remove", "kind": "banana", "index": 0, "expect_position": [9, 9, 9]}],
            [{"op": "remove", "kind": "banana", "index": 7, "expect_position": [1, 0.5, 2]}],
            [{"op": "remove", "kind": "banana", "index": 0}],
            [{"op": "add", "kind": "banana", "group": 3, "position": [0, 0, 0]}],
            [{"op": "add", "kind": "banana", "group": 0, "position": [400, 0, 400]}],
            [{"op": "add", "kind": "banana", "group": 0, "position": [0, 0]}],
            [{"op": "add", "kind": "spring", "group": 0, "position": [0, 0, 0]}],
            [{"op": "explode", "kind": "banana"}],
            [{"op": "move", "kind": "banana", "index": 0, "from": [1, 0.5, 2], "to": [1, 0.5, 3]},
             {"op": "remove", "kind": "banana", "index": 0, "expect_position": [1, 0.5, 2]}],
            [{"op": "add", "kind": "goal", "group": 0, "position": [0, 0, 0], "rotation_like": 5}],
            [],
            [{"op": "add", "kind": "banana", "group": 0, "position": [0, 0.5, 0], "bunch": True}] * 50,
        ]
        for ops in bad:
            with self.assertRaises(ObjectEditRefused, msg=ops):
                apply_object_ops(self.base, ops)


class PlanV2(unittest.TestCase):
    def test_build_rom_with_object_ops(self):
        import hashlib
        import shutil
        import tempfile
        from trcore.editplan import build_edit_rom, check_plan
        from trcore.rom import NdsRom
        from trcore.stc.edit import EditRefused
        from tests.synth_rom import build_rom
        tmp = tempfile.mkdtemp(prefix="trcore_obj_")
        try:
            rom_path = os.path.join(tmp, "in.nds")
            with open(rom_path, "wb") as fh:
                fh.write(build_rom([("stcoli", "s1_stc.lz", lz10.encode(listed_stage()))]))
            with open(rom_path, "rb") as fh:
                sha1 = hashlib.sha1(fh.read()).hexdigest()
            plan = {"schema": "trcore.edit_plan/2", "title": "t", "base_rom_sha1": sha1,
                    "stages": [{"file": "stcoli/s1_stc.lz", "where": "test",
                                "objects": [{"op": "remove", "kind": "banana", "index": 2,
                                             "expect_position": [5, 0.5, 15]},
                                            {"op": "add", "kind": "banana", "group": 0, "position": [3, 0.5, -3]}]}]}
            rec = build_edit_rom(rom_path, os.path.join(tmp, "out.nds"), plan)
            self.assertEqual(rec["plan_schema"], "trcore.edit_plan/2")
            self.assertEqual(rec["stage_edits"][0]["objects"]["pools"]["banana"]["records"], 3)
            dec = lz10.decode(NdsRom.from_file(os.path.join(tmp, "out.nds")).file_bytes("stcoli/s1_stc.lz"))[0]
            self.assertEqual(StageDocument(dec).pools["C"]["records"][2]["position"], [3.0, 0.5, -3.0])
            v1 = dict(plan, schema="trcore.edit_plan/1")
            with self.assertRaises(EditRefused):
                check_plan(v1)
            bad = dict(plan)
            bad["stages"] = [dict(plan["stages"][0], objects=[{"op": "remove", "kind": "banana", "index": 2,
                                                                "expect_position": [0, 0, 0]}])]
            with self.assertRaises(EditRefused):
                build_edit_rom(rom_path, os.path.join(tmp, "out2.nds"), bad)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out2.nds")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
class RealStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from trcore.rom import NdsRom
        cls.rom = NdsRom.from_file(REAL_ROM)

    def test_unchanged_objects_keep_their_cells(self):
        d = self.rom.stage_file_decoded("smb1_ad02")
        g0 = CL.read_grids(d)[0]
        new, _ = apply_object_ops(d, [{"op": "add", "kind": "bumper", "group": 0, "position": [0, 0, -20]},
                                      {"op": "remove", "kind": "bumper", "index": 8, "expect_position": [0, 0, -35]}])
        g1 = CL.read_grids(new)[0]
        for i in range(8):
            self.assertEqual(g1.listed(5, i), g0.listed(5, i))
        for i in range(6):                                      # bananas untouched
            self.assertEqual(g1.listed(6, i), g0.listed(6, i))
        self.assertTrue(g1.listed(5, 8))
        self.assertIsNone(CL.coverage_problem(g1, "bumper", 8, (0, 0, -20)))

    def test_relisting_everything_in_place_stays_clean(self):
        """Relisting all objects of a stage in place must give a clean, fully covered stage."""
        for key in ("smb1_be01", "smb1_ad21", "smbds_043", "smb1_be06"):
            d = self.rom.stage_file_decoded(key)
            doc = StageDocument(d, key)
            ops = []
            for kind, pool, fld in (("goal", "A", "translation"), ("bumper", "B", "translation"),
                                    ("banana", "C", "position")):
                for r in doc.pools[pool]["records"]:
                    ops.append({"op": "move", "kind": kind, "index": r["index"], "from": r[fld], "to": r[fld]})
            new, rep = apply_object_ops(d, ops, key)
            self.assertFalse(StageDocument(new, key).has_errors(), key)


if __name__ == "__main__":
    unittest.main()
