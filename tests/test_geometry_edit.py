"""Collision editing (trcore/stc/geometry_edit.py) and model polygons (trcore/nitro/nsbmd_write.py)."""
import hashlib
import math
import os
import shutil
import struct
import tempfile
import unittest

from trcore import lz10
from trcore.nitro.nsbmd import Nsbmd, model_geometry
from trcore.nitro.nsbmd_write import ModelEditRefused, append_polygons, shape_polygons_with_texcoords
from trcore.stc import cells as CL
from trcore.stc.collision import probe, read_collision
from trcore.stc.document import StageDocument
from trcore.stc.geometry_edit import (CollisionEditRefused, apply_collision_ops, box_polygons, clip,
                                      faces_of_polygon, floor_polygon)
from tests.synth import IDENTITY, build_stage, with_cell_lists
from tests.synth_nsbmd import FX, _cmds, build_nsbmd, s16pair

REAL_ROM = os.environ.get("TRCORE_ROM")


def empty_collision_stage() -> bytes:
    """Synthetic stage (grid 2 x 3, cells 10 x 10 from (-10.5, -12.5)) with no collision geometry yet."""
    st = bytearray(with_cell_lists(build_stage(goals=((0, IDENTITY, (0, 0, -10)),),
                                               bananas=((1, 0.5, 2, 0), (-1, 0.5, 2, 1)))))
    desc = struct.unpack_from("<I", st, 0x18)[0]
    struct.pack_into("<I", st, desc + 0x8C, 0)            # drop the two placeholder quads
    return bytes(st)


def floor_stage() -> bytes:
    new, _ = apply_collision_ops(empty_collision_stage(),
                                 [{"op": "add_polygons", "polygons": [floor_polygon([-8, 8], [-10, 10], 0.0)]}])
    return new


class Geometry(unittest.TestCase):
    def test_clip_and_faces(self):
        sq = [(0.0, 0, 0.0), (0.0, 0, 4.0), (4.0, 0, 4.0), (4.0, 0, 0.0)]
        left = clip(sq, 0, 1.0, "le")
        self.assertEqual(sorted({p[0] for p in left}), [0.0, 1.0])
        self.assertEqual(len(faces_of_polygon(left)), 1)                  # still a parallelogram -> one quad
        tri = clip(sq, 0, 1.0, "ge")
        tri = clip(tri, 2, 3.0, "le")
        self.assertEqual(len(tri), 4)
        pent = [(0.0, 0, 0.0), (0.0, 0, 2.0), (1.0, 0, 3.0), (2.0, 0, 2.0), (2.0, 0, 0.0)]
        self.assertEqual(len(faces_of_polygon(pent)), 3)                  # fan of triangles
        for f in faces_of_polygon(pent):
            n = [0, 0, 0]
            a, b, c = f
            u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
            self.assertGreater(u[2] * v[0] - u[0] * v[2], 0)              # all keep the upward winding

    def test_box_polygons_face_outwards(self):
        polys = box_polygons([0, 1], [0, 1], [0, 1])
        centre = (0.5, 0.5, 0.5)
        for p in polys:
            a, b, c = p[0], p[1], p[2]
            u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            mid = [sum(q[k] for q in p) / 4 for k in range(3)]
            self.assertGreater(sum(n[k] * (mid[k] - centre[k]) for k in range(3)), 0)


class CollisionEdits(unittest.TestCase):
    def test_add_floor_then_ball_touches_it(self):
        st = floor_stage()
        col = read_collision(st)[0]
        self.assertEqual((len(col["quad"]), len(col["edge"]), len(col["point"])), (1, 4, 4))
        self.assertEqual(col["quad"][0]["normal"], (0.0, 1.0, 0.0))
        self.assertTrue(probe(st, (0.0, 0.5, 0.0))["quad"])
        self.assertFalse(probe(st, (0.0, 1.5, 0.0))["touching"])
        self.assertTrue(probe(st, (8.2, 0.4, 0.0))["edge"])                 # dipping over the edge
        self.assertFalse(StageDocument(st).has_errors())

    def test_remove_strip_cuts_and_adds_cut_edges(self):
        st = floor_stage()
        new, rep = apply_collision_ops(st, [{"op": "remove_box", "x": [-1, 1]}])
        op = rep["ops"][0]
        self.assertEqual((op["faces_cut"], op["face_pieces_added"]), (1, 2))
        self.assertEqual(op["cut_edges_added"], 2)
        self.assertFalse(probe(new, (0.0, 0.5, 0.0))["touching"])
        self.assertTrue(probe(new, (-3.0, 0.5, 0.0))["quad"])
        self.assertTrue(probe(new, (3.0, 0.5, 5.0))["quad"])
        self.assertTrue(probe(new, (-1.2, 0.4, 0.0))["edge"])               # the new edge at x = -1
        col = read_collision(new)[0]
        xs = sorted({round(c[0], 2) for f in col["quad"] for c in f["corners"]})   # dual vectors: ~1/4096 per unit
        self.assertEqual(xs, [-8.0, -1.0, 1.0, 8.0])
        # only the group's count/offset fields and cell entries changed inside the original bytes
        desc = struct.unpack_from("<I", st, 0x18)[0]
        g = CL.read_grids(st)[0]
        allowed = set(range(desc + 0x74, desc + 0x94)) | set(range(g.table, g.table + 8 * g.nx * g.nz))
        self.assertTrue(all(i in allowed for i in range(len(st)) if st[i] != new[i]))

    def test_height_range_limits_removal(self):
        st = floor_stage()
        new, rep = apply_collision_ops(st, [{"op": "remove_box", "x": [-1, 1], "y": [0.5, 2]}])
        self.assertEqual(rep["ops"][0]["faces_cut"], 0)
        self.assertTrue(probe(new, (0.0, 0.5, 0.0))["quad"])

    def test_floor_outside_the_grid_grows_it(self):
        st = floor_stage()
        g0 = CL.read_grids(st)[0]
        new, rep = apply_collision_ops(st, [{"op": "add_polygons",
                                             "polygons": [floor_polygon([12, 16], [-2, 2], 0.0)]}])
        self.assertIsNone(probe(st, (14.0, 0.5, 0.0)))                     # outside the old grid
        self.assertTrue(probe(new, (14.0, 0.5, 0.0))["quad"])
        g1 = CL.read_grids(new)[0]
        self.assertTrue(rep["groups"]["0"]["grid"]["grown"])
        self.assertEqual((g1.ox, g1.oz, g1.sx, g1.sz, g1.nz), (g0.ox, g0.oz, g0.sx, g0.sz, g0.nz))
        self.assertEqual(g1.nx, 3)
        for c in range(g0.nx * g0.nz):                                     # old cells keep their object lists
            i, j = c % g0.nx, c // g0.nx
            for b in (4, 6):
                self.assertEqual(g0.cells[c][2].get(b, (0, None))[1], g1.cells[j * g1.nx + i][2].get(b, (0, None))[1])
        stats = CL.survey_stage(new, StageDocument(new))
        self.assertEqual(stats.get("bananas in no cell", 0), 0)
        self.assertTrue(probe(new, (0.0, 0.5, 0.0))["quad"])                # the old floor still works

    def test_refusals(self):
        st = floor_stage()
        bad = [
            [{"op": "remove_box"}],
            [{"op": "remove_box", "x": [1, -1]}],
            [{"op": "add_polygons", "polygons": [[[0, 0, 0], [1, 0, 0]]]}],
            [{"op": "add_polygons", "polygons": [[[0, 0, 0], [0, 0, 2], [1, 0, 1], [2, 0, 2], [2, 0, 0]]]}],  # concave
            [{"op": "add_polygons", "polygons": [[[0, 0, 0], [0, 0, 2], [2, 1, 2], [2, 0, 0]]]}],             # not flat
            [{"op": "add_polygons", "polygons": [floor_polygon([0, 1], [0, 1], 0)], "group": 3}],
            [{"op": "explode"}],
            [{"op": "add_polygons", "polygons": [floor_polygon([0, 1e9], [0, 1], 0)]}],
        ]
        for ops in bad:
            with self.assertRaises(CollisionEditRefused, msg=str(ops)):
                apply_collision_ops(st, ops)


def flat_textured_dl():
    """One upward-facing quad (corners (0,0,0)..(2,0,2) after posScale 2) with s = 16 x, t = 16 z."""
    def tc(s, t):
        return (int(s * 16) & 0xFFFF) | ((int(t * 16) & 0xFFFF) << 16)
    corners = [(0, 0), (0, 1), (1, 1), (1, 0)]                  # raw (x, z); stage = raw x 2
    cmds = [(0x40, [1]), (0x21, [0x1FF << 10])]
    for x, z in corners:
        cmds += [(0x22, [tc(32 * x, 32 * z)]), (0x23, [s16pair(x, 0), s16pair(z, 0) & 0xFFFF])]
    cmds.append((0x41, []))
    return _cmds(*cmds)


class ModelEdits(unittest.TestCase):
    def setUp(self):
        self.model = build_nsbmd(tri_dl=flat_textured_dl(), node0_t=(0, 0, 0))

    def test_append_reads_back_and_keeps_old(self):
        old_geo = model_geometry(Nsbmd(self.model))
        polys = box_polygons([1, 1.5], [0, 0.5], [1, 1.5])
        new, rep = append_polygons(self.model, "tri", polys)
        self.assertEqual(rep["polygons_added"], 5)
        self.assertEqual(rep["readback_max_error"], 0.0)
        m = Nsbmd(new).models[0]
        self.assertEqual(m.base + m.size, len(new))
        self.assertEqual(struct.unpack_from("<I", new, 8)[0], len(new))
        geo = model_geometry(Nsbmd(new))
        others = [p for p in geo["polygons"] if p[1] != 0]
        self.assertEqual(others, [p for p in old_geo["polygons"] if p[1] != 0])
        mine = [p[0] for p in geo["polygons"] if p[1] == 0]
        self.assertEqual(len(mine), 6)
        for got, want in zip(mine[1:], polys):
            for a, b in zip(got, want):
                self.assertLess(max(abs(x - y) for x, y in zip(a, b)), 1e-6)
        self.assertEqual(m.num_quad, Nsbmd(self.model).models[0].num_quad + 5)
        # texture coordinates continue s = 16 x, t = 16 z on the top face (modulo whole 1024-texel periods)
        top = shape_polygons_with_texcoords(new, m, 0)[1]
        for (pos, (s, t)) in top:
            self.assertAlmostEqual((s - 16 * pos[0]) % 1024, 0.0, places=3)
            self.assertAlmostEqual((t - 16 * pos[2]) % 1024, 0.0, places=3)
        self.assertGreaterEqual(m.box["h"] * m.box_pos_scale, 0.5 - 1e-3)

    def test_refusals(self):
        with self.assertRaises(ModelEditRefused):
            append_polygons(self.model, "nope", [floor_polygon([0, 1], [0, 1], 0)])
        with self.assertRaises(ModelEditRefused):                         # drawn under a rotated node
            append_polygons(self.model, "quad", [floor_polygon([0, 1], [0, 1], 0)])
        with self.assertRaises(ModelEditRefused):                         # beyond 8 x posScale
            append_polygons(self.model, "tri", [floor_polygon([0, 20], [0, 1], 0)])
        with self.assertRaises(ModelEditRefused):
            append_polygons(self.model, "tri", [[[0, 0, 0], [1, 0, 0]]])
        with self.assertRaises(ModelEditRefused):
            append_polygons(self.model + b"\0\0\0\0", "tri", [floor_polygon([0, 1], [0, 1], 0)])


class PlanV3(unittest.TestCase):
    def test_build_rom_with_collision_and_model(self):
        from trcore.editplan import build_edit_rom, check_plan
        from trcore.rom import NdsRom
        from trcore.stc.edit import EditRefused
        from tests.synth_rom import build_rom
        tmp = tempfile.mkdtemp(prefix="trcore_geo_")
        try:
            model = build_nsbmd(tri_dl=flat_textured_dl(), node0_t=(0, 0, 0))
            rom_path = os.path.join(tmp, "in.nds")
            with open(rom_path, "wb") as fh:
                fh.write(build_rom([("stcoli", "s1_stc.lz", lz10.encode(floor_stage())),
                                    ("model/stage", "s1_nsbmd.lz", lz10.encode(model))]))
            with open(rom_path, "rb") as fh:
                sha1 = hashlib.sha1(fh.read()).hexdigest()
            box = box_polygons([1, 1.5], [0, 0.5], [1, 1.5])
            plan = {"schema": "trcore.edit_plan/3", "title": "t", "base_rom_sha1": sha1,
                    "stages": [{"file": "stcoli/s1_stc.lz", "model_file": "model/stage/s1_nsbmd.lz",
                                "collision": [{"op": "remove_box", "x": [-1, 0.5]},
                                              {"op": "add_polygons", "polygons": box}],
                                "model": [{"op": "add_polygons", "shape": "tri", "polygons": box[:2]},
                                          {"op": "add_polygons", "shape": "tri", "polygons": box[2:]}]}]}
            out = os.path.join(tmp, "out.nds")
            rec = build_edit_rom(rom_path, out, plan)
            self.assertEqual(rec["plan_schema"], "trcore.edit_plan/3")
            self.assertEqual(len(rec["stage_edits"][0]["model"]["ops"]), 1)          # one append per shape
            rom = NdsRom.from_file(out)
            st = lz10.decode(rom.file_bytes("stcoli/s1_stc.lz"))[0]
            self.assertTrue(probe(st, (1.25, 1.0, 1.25))["quad"])                     # box top
            self.assertFalse(probe(st, (-0.5, 0.5, 0.0))["touching"])                 # removed
            md = lz10.decode(rom.file_bytes("model/stage/s1_nsbmd.lz"))[0]
            self.assertEqual(len([p for p in model_geometry(Nsbmd(md))["polygons"] if p[1] == 0]), 6)
            for schema in ("trcore.edit_plan/1", "trcore.edit_plan/2"):
                with self.assertRaises(EditRefused):
                    check_plan(dict(plan, schema=schema))
            nomodel = dict(plan, stages=[{k: v for k, v in plan["stages"][0].items() if k != "model_file"}])
            with self.assertRaises(EditRefused):
                build_edit_rom(rom_path, os.path.join(tmp, "out2.nds"), nomodel)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out2.nds")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ModelInDump(unittest.TestCase):
    def test_finds_model_and_tolerates_material_changes(self):
        from trcore.ramdump import analyze_model
        model = build_nsbmd(tri_dl=flat_textured_dl(), node0_t=(0, 0, 0))

        class FakeRom:
            def stage_model_decoded(self, key):
                return model
        dump = bytearray(4 * 1024 * 1024)
        at = 0x123400
        dump[at:at + len(model)] = model
        m = Nsbmd(model).models[0]
        mat = m.base + m.ofs_mat
        dump[at + mat + 4] ^= 0xFF                                   # NNS texture setup touches materials
        r = analyze_model(bytes(dump), FakeRom(), "s1")
        self.assertTrue(r["found"])
        self.assertEqual(r["address"], f"0x{0x02000000 + at:08X}")
        self.assertEqual((r["different_in_material_block"], r["different_elsewhere"]), (1, 0))
        self.assertTrue(r["display_lists_equal"])
        sh = m.shapes[0]
        dump[at + sh["dl_offset"] + 4] ^= 0xFF
        r = analyze_model(bytes(dump), FakeRom(), "s1")
        self.assertFalse(r["display_lists_equal"])


@unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
class RealEditTest4(unittest.TestCase):
    """Edit test 4's plan, built from the original ROM, checked statically (the in-game test is separate)."""

    @classmethod
    def setUpClass(cls):
        import json
        from trcore.editplan import build_edit_rom
        from trcore.rom import NdsRom
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "docs", "experiments", "edit4_collision", "plan.json")) as fh:
            plan = json.load(fh)
        plan.pop("base_rom_sha1", None)
        cls.tmp = tempfile.mkdtemp(prefix="trcore_edit4_")
        out = os.path.join(cls.tmp, "edit4.nds")
        cls.rec = build_edit_rom(REAL_ROM, out, plan)
        cls.orig = NdsRom.from_file(REAL_ROM)
        cls.new = NdsRom.from_file(out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def touch(self, rom, key, pos):
        return probe(rom.stage_file_decoded(key), pos)

    def test_only_three_files_change(self):
        changed = sorted(p for p in self.orig.id_by_path if self.orig.file_bytes(p) != self.new.file_bytes(p))
        self.assertEqual(changed, ["model/stage/smbds_023_nsbmd.lz", "stcoli/smb1_be01_stc.lz",
                                   "stcoli/smbds_023_stc.lz"])

    def test_h_strip(self):
        self.assertTrue(self.touch(self.orig, "smb1_be01", (0.0, 0.5, 0.0))["touching"])
        self.assertFalse(self.touch(self.new, "smb1_be01", (0.0, 0.5, 0.0))["touching"])
        self.assertTrue(self.touch(self.new, "smb1_be01", (-2.0, 0.5, 0.0))["quad"])
        self.assertTrue(self.touch(self.new, "smb1_be01", (2.0, 0.5, 0.0))["quad"])
        self.assertTrue(self.touch(self.new, "smb1_be01", (0.0, 0.5, 2.5))["quad"])          # the lane

    def test_i_gap_and_invisible_floor(self):
        self.assertTrue(self.touch(self.orig, "smb1_be01", (9.6, 0.6, 0.0))["touching"])
        self.assertFalse(self.touch(self.new, "smb1_be01", (9.6, 0.6, 0.0))["touching"])
        self.assertTrue(self.touch(self.new, "smb1_be01", (9.6, 0.6, 2.5))["touching"])
        self.assertIsNone(self.touch(self.orig, "smb1_be01", (12.0, 0.6, 0.0)))
        self.assertTrue(self.touch(self.new, "smb1_be01", (12.0, 0.6, 0.0))["quad"])
        self.assertFalse(self.touch(self.new, "smb1_be01", (15.0, 0.6, 0.0))["touching"])

    def test_k_box_matches_model_and_j_has_no_collision(self):
        self.assertTrue(self.touch(self.new, "smbds_023", (-1.25, 1.5, 31.0))["quad"])
        self.assertTrue(self.touch(self.new, "smbds_023", (0.0, 0.5, 31.0))["quad"])
        self.assertFalse(self.touch(self.new, "smbds_023", (0.0, 2.4, 35.0))["touching"])
        faces = read_collision(self.new.stage_file_decoded("smbds_023"))[0]["quad"][-5:]
        polys = [p[0] for p in model_geometry(Nsbmd(self.new.stage_model_decoded("smbds_023")))["polygons"]
                 if p[1] == 0][-5:]
        for f, poly in zip(faces, polys):
            for a, b in zip(f["corners"], poly):
                self.assertLess(math.dist(a, b), 0.003)

    def test_stages_still_clean(self):
        for key in ("smb1_be01", "smbds_023"):
            d = self.new.stage_file_decoded(key)
            doc = StageDocument(d, key)
            self.assertFalse(doc.has_errors(), key)
            stats = CL.survey_stage(d, doc)
            for bad in ("lists not sorted / with repeats", "list index out of range", "bananas in no cell",
                        "goals in no cell"):
                self.assertEqual(stats.get(bad, 0), 0, (key, bad))


if __name__ == "__main__":
    unittest.main()
