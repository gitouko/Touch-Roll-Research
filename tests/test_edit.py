import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest

from trcore import cli, lz10
from trcore.editplan import build_edit_rom
from trcore.rom import NdsRom
from trcore.stc.document import StageDocument
from trcore.stc.edit import EditRefused, apply_edits
from tests.synth import IDENTITY, build_stage, lz10_literal_encode
from tests.synth_rom import build_rom


class ApplyEdits(unittest.TestCase):
    def setUp(self):
        self.stage = build_stage(goals=((0, IDENTITY, (0, 0, -10)),),
                                 bananas=((1, 0.5, 2, 0), (-1, 0.5, 2, 1)))

    def changed(self, new):
        return [i for i in range(len(new)) if new[i] != self.stage[i]]

    def test_banana_position(self):
        new, recs = apply_edits(self.stage, [{"target": "pool_C[0].position", "from": [1, 0.5, 2], "to": [1, 0.5, 4]}])
        self.assertEqual(StageDocument(new).pools["C"]["records"][0]["position"], [1.0, 0.5, 4.0])
        self.assertTrue(all(int(recs[0]["offset"], 16) <= i < int(recs[0]["offset"], 16) + 12 for i in self.changed(new)))
        self.assertEqual(recs[0]["old_value"], [1.0, 0.5, 2.0])

    def test_flag_start_goal(self):
        new, recs = apply_edits(self.stage, [
            {"target": "pool_C[0].u32_0C", "from": 0, "to": 1},
            {"target": "start[0].u32_0C", "from": "0x4000", "to": "0x8000"},
            {"target": "pool_A[0].translation", "from": [0, 0, -10], "to": [0, 2, -10]}])
        d = StageDocument(new)
        self.assertEqual(d.pools["C"]["records"][0]["u32_0C"], 1)
        self.assertEqual(d.start["records"][0]["u32_0C"], 0x8000)
        self.assertEqual(d.pools["A"]["records"][0]["translation"], [0.0, 2.0, -10.0])
        self.assertEqual(len(recs), 3)
        self.assertEqual(len(self.changed(new)), 3)   # one byte each in this case

    def test_q12_rounding_is_reported(self):
        new, recs = apply_edits(self.stage, [{"target": "pool_C[1].position", "from": [-1, 0.5, 2],
                                              "to": [-1, 0.5, 2.0001]}])
        self.assertEqual(recs[0]["new_value"][2], round(2.0001 * 4096) / 4096)

    def test_refusals(self):
        bad = [
            {"target": "pool_C[0].position", "from": [9, 9, 9], "to": [0, 0, 0]},    # wrong 'from'
            {"target": "pool_C[9].position", "from": [0, 0, 0], "to": [0, 0, 0]},    # no such record
            {"target": "header.group_count", "from": 1, "to": 2},                    # not editable
            {"target": "pool_C[0].offset", "from": 0, "to": 0},                      # not editable
            {"target": "pool_C[0].position", "to": [0, 0, 0]},                       # missing 'from'
            {"target": "pool_C[0].position", "from": [1, 0.5], "to": [1, 0.5]},      # wrong count
            {"target": "pool_C[0].position", "from": [1, 0.5, 2], "to": [1e9, 0, 0]},  # out of range
            {"target": "pool_C[0].u32_0C", "from": 0, "to": True},                   # bool is not a u32
            {"target": "pool_C[0].u32_0C", "from": 0, "to": -1},                     # negative u32
        ]
        for e in bad:
            with self.assertRaises(EditRefused, msg=e):
                apply_edits(self.stage, [e])
        with self.assertRaises(EditRefused):
            apply_edits(self.stage, [{"target": "pool_C[0].u32_0C", "from": 0, "to": 1},
                                     {"target": "pool_C[0].u32_0C", "from": 0, "to": 1}])
        with self.assertRaises(EditRefused):
            apply_edits(self.stage, [])
        with self.assertRaises(EditRefused):
            apply_edits(lz10_literal_encode(self.stage), [{"target": "pool_C[0].u32_0C", "from": 0, "to": 1}])
        with self.assertRaises(EditRefused):
            apply_edits(b"NOPE" + bytes(300), [{"target": "pool_C[0].u32_0C", "from": 0, "to": 1}])


class PlanToRom(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trcore_edit_")
        self.stage = build_stage()
        self.rom_path = os.path.join(self.tmp, "in.nds")
        with open(self.rom_path, "wb") as fh:
            fh.write(build_rom([("stcoli", "s1_stc.lz", lz10.encode(self.stage)),
                                ("stcoli", "s2_stc.lz", lz10.encode(build_stage(groups=("A", "B"))))]))
        with open(self.rom_path, "rb") as fh:
            self.sha1 = hashlib.sha1(fh.read()).hexdigest()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plan(self, **kw):
        p = {"schema": "trcore.edit_plan/1", "title": "t", "base_rom_sha1": self.sha1,
             "stages": [{"file": "stcoli/s1_stc.lz", "where": "test",
                         "edits": [{"target": "pool_C[0].u32_0C", "from": 0, "to": 1, "prediction": "bunch"}]}]}
        p.update(kw)
        return p

    def test_build_and_verify(self):
        out = os.path.join(self.tmp, "out.nds")
        rec = build_edit_rom(self.rom_path, out, self.plan())
        self.assertEqual(rec["status"], "generated - not yet verified in-game")
        self.assertEqual(rec["stage_edits"][0]["edits"][0]["prediction"], "bunch")
        r2 = NdsRom.from_file(out)
        dec = lz10.decode(r2.file_bytes("stcoli/s1_stc.lz"))[0]
        self.assertEqual(StageDocument(dec).pools["C"]["records"][0]["u32_0C"], 1)
        self.assertEqual(r2.file_bytes("stcoli/s2_stc.lz"), NdsRom.from_file(self.rom_path).file_bytes("stcoli/s2_stc.lz"))
        with open(self.rom_path, "rb") as fh:
            self.assertEqual(hashlib.sha1(fh.read()).hexdigest(), self.sha1)

    def test_plan_refusals(self):
        out = os.path.join(self.tmp, "x.nds")
        with self.assertRaises(EditRefused):
            build_edit_rom(self.rom_path, out, self.plan(base_rom_sha1="0" * 40))
        dup = self.plan()
        dup["stages"] = dup["stages"] * 2
        with self.assertRaises(EditRefused):
            build_edit_rom(self.rom_path, out, dup)
        with self.assertRaises(EditRefused):   # no profile -> stage_key alone is not enough
            build_edit_rom(self.rom_path, out, self.plan(stages=[{"stage_key": "s1", "edits": []}]))
        self.assertFalse(os.path.exists(out))

    def test_cli(self):
        plan_path = os.path.join(self.tmp, "plan.json")
        with open(plan_path, "w") as fh:
            json.dump(self.plan(), fh)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["stage-edit", self.rom_path, os.path.join(self.tmp, "o.nds"), plan_path])
        self.assertEqual(code, 0, buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["stage-edit", self.rom_path, self.rom_path, plan_path]), 1)


if __name__ == "__main__":
    unittest.main()
