import math
import os
import random
import struct
import unittest

from trcore.nitro import nsbmd as N
from trcore.stagemodel import floor_below
from tests.synth_nsbmd import EXPECTED_TRIANGLES, QUAD_DL, SBC, TRI_DL, build_nsbmd


def close(a, b, eps=1e-9):
    return all(abs(x - y) < eps for x, y in zip(a, b))


class Decode(unittest.TestCase):
    def test_structure(self):
        f = N.Nsbmd(build_nsbmd())
        m = f.models[0]
        self.assertEqual(m.name, "test_model")
        self.assertEqual([n["name"] for n in m.nodes], ["root", "part"])
        self.assertEqual([s["name"] for s in m.shapes], ["tri", "quad"])
        self.assertEqual(m.pos_scale, 2.0)
        self.assertEqual(m.nodes[0]["translation"], (1.0, 0.0, 0.0))
        self.assertEqual(m.nodes[1]["rotation"], ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))

    def test_triangles_match_hand_computed(self):
        g = N.model_geometry(N.Nsbmd(build_nsbmd()))
        self.assertEqual(len(g["triangles"]), len(EXPECTED_TRIANGLES))
        for got, exp in zip(g["triangles"], EXPECTED_TRIANGLES):
            for gv, ev in zip(got[:3], exp):
                self.assertTrue(close(gv, ev), (got, exp))
        self.assertEqual([t[3] for t in g["triangles"]], [0, 1, 1])     # shape index
        self.assertEqual(N.bounds(g["triangles"])["min"], [-1.0, 0.0, -2.0])

    def test_pivot_matrices_are_rotations(self):
        a, b = math.cos(0.3), math.sin(0.3)
        for sel in range(9):
            for neg in range(8):
                m = N.pivot_matrix(sel, neg, a, b)
                for i in range(3):
                    self.assertAlmostEqual(sum(x * x for x in m[i]), 1.0)
                pr, pc = divmod(sel, 3)
                self.assertEqual(abs(m[pr][pc]), 1.0)
        with self.assertRaises(N.NitroError):
            N.pivot_matrix(9, 0, a, b)

    def test_matrix_helpers(self):
        t = (((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)), (1.0, 2.0, 3.0))
        self.assertEqual(N.mat_apply(t, (1.0, 0.0, 0.0)), (1.0, 2.0, 4.0))
        both = N.mat_then(t, N.mat_scale((2.0, 2.0, 2.0)))
        self.assertEqual(N.mat_apply(both, (1.0, 0.0, 0.0)), (2.0, 4.0, 8.0))

    def test_floor_below(self):
        tris = [((0, 0, 0), (4, 0, 0), (0, 0, 4)), ((0, 2, 0), (4, 2, 0), (0, 2, 4))]
        self.assertEqual(floor_below(tris, (1, 1, 1)), 0)
        self.assertEqual(floor_below(tris, (1, 2.5, 1)), 2)
        self.assertIsNone(floor_below(tris, (5, 3, 5)))
        self.assertIsNone(floor_below(tris, (1, -1, 1)))


class Refusals(unittest.TestCase):
    def assertNitro(self, data):
        with self.assertRaises(N.NitroError):
            f = N.Nsbmd(data)
            N.model_geometry(f)

    def test_bad_inputs(self):
        self.assertNitro(b"NOPE" + bytes(60))
        self.assertNitro(build_nsbmd()[:0x40])
        self.assertNitro(build_nsbmd(sbc=bytes([0x1F, 0x01])))                        # unknown SBC op
        self.assertNitro(build_nsbmd(sbc=bytes([0x05, 7, 0x01])))                     # missing shape
        self.assertNitro(build_nsbmd(sbc=bytes([0x03, 40, 0x01])))                    # stack slot range
        self.assertNitro(build_nsbmd(sbc=bytes([0x03, 3, 0x01])))                     # empty slot
        bad_dl = bytes([0x40, 0x99, 0, 0]) + struct.pack("<I", 0)
        self.assertNitro(build_nsbmd(tri_dl=bad_dl))                                  # unknown GX op
        self.assertNitro(build_nsbmd(tri_dl=bytes([0x23, 0, 0, 0]) + bytes(4)))       # params past end

    def test_fuzz_never_crashes(self):
        base = bytearray(build_nsbmd())
        rng = random.Random(1234)
        for _ in range(3000):
            buf = bytearray(base)
            for _ in range(rng.randint(1, 6)):
                buf[rng.randrange(len(buf))] = rng.randrange(256)
            try:
                N.model_geometry(N.Nsbmd(bytes(buf)))
            except N.NitroError:
                pass


REAL_ROM = os.environ.get("TRCORE_ROM")


@unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
class RealModels(unittest.TestCase):
    def test_survey(self):
        from trcore.rom import NdsRom
        from trcore.stagemodel import survey
        rep = survey(NdsRom.from_file(REAL_ROM))
        self.assertEqual(rep["parse_errors"], [])
        self.assertEqual(rep["triangle_count_mismatches"], [])
        self.assertEqual(rep["models_checked"], 213)
        self.assertEqual(rep["stage_files_without_model_that_have_a_name"], ["smbds_009"])
        on = rep["object_height_above_model_surface"]
        self.assertGreater(on["start"]["on surface (|gap| < 0.02)"], 150)
        self.assertGreater(rep["group_transform_vs_model_node"]["node_inverse"], 350)


if __name__ == "__main__":
    unittest.main()
