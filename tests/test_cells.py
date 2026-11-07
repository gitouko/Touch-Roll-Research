import os
import struct
import unittest

from trcore.stc import cells as CL

FX = 4096
REAL_ROM = os.environ.get("TRCORE_ROM")


def build_grid_stage(nx=8, nz=6, origin=(-4.0, -3.0), step=(1.0, 1.0), banana_cells=(), unterminated=False):
    """Minimal fabricated buffer: header with one descriptor, its grid, a cell table and lists."""
    base = 0x40
    table = base + 0xCC
    buf = bytearray(table + 8 * nx * nz)
    struct.pack_into("<II", buf, 0x14, 1, base)
    struct.pack_into("<hhiiii", buf, base + 0x40, nx, nz, int(origin[0] * FX), int(origin[1] * FX),
                     int(step[0] * FX), int(step[1] * FX))
    struct.pack_into("<I", buf, base + 0x54, table)
    struct.pack_into("<I", buf, base + 0xA4, 1)                  # one banana in the group's slice
    banana_list = len(buf)
    buf += struct.pack("<H", 0) + (b"" if unterminated else struct.pack("<H", 0xFFFF))
    buf += bytes((-len(buf)) % 4)
    for c in range(nx * nz):
        if c in banana_cells:
            arr = len(buf)
            buf += struct.pack("<5I", 0, 0, 0, 0, banana_list)   # bits 0-3 empty, bit 6 -> list
            struct.pack_into("<II", buf, table + 8 * c, 0x4F, arr)
        else:
            struct.pack_into("<II", buf, table + 8 * c, 0x0F, 0)
    return bytes(buf)


class GridReading(unittest.TestCase):
    def test_read_and_footprint(self):
        g0 = CL.read_grids(build_grid_stage())[0]
        x, z = int(0.25 * FX), int(0.25 * FX)
        fp = g0.footprint(x, z)                  # [-3.25, 3.75] -> columns 0..7, rows 0..5 (clamped)
        self.assertEqual(len(fp), 8 * 6)
        fp_small = g0.footprint(x, z, FX // 2, FX // 2)          # [-0.25, 0.75] -> cols 3..4, rows 2..3
        self.assertEqual(fp_small, {2 * 8 + 3, 2 * 8 + 4, 3 * 8 + 3, 3 * 8 + 4})
        self.assertEqual(g0.cell_rect(2 * 8 + 3), (-1.0, 0.0, -1.0, 0.0))
        self.assertEqual(g0.within(0.5, 0.5, 0.0), {3 * 8 + 4})

    def test_listed_and_coverage(self):
        cells = {r * 8 + c for r in range(1, 5) for c in range(2, 7)}   # x -2..3, z -2..2
        g0 = CL.read_grids(build_grid_stage(banana_cells=cells))[0]
        self.assertEqual(g0.listed(6, 0), cells)
        self.assertIsNone(CL.coverage_problem(g0, "banana", 0, (0.5, 0.5, 0.0), (0.5, 0.5, 0.0)))
        self.assertIsNone(CL.coverage_problem(g0, "banana", 0, (1.0, 0.5, 0.0), (0.5, 0.5, 0.0)))
        self.assertIn("do not list", CL.coverage_problem(g0, "banana", 0, (3.5, 0.5, 2.5), (0.5, 0.5, 0.0)))
        self.assertIn("outside", CL.coverage_problem(g0, "banana", 0, (40.0, 0.5, 40.0), (0.5, 0.5, 0.0)))

    def test_goal_extent(self):
        ident = [FX, 0, 0, 0, FX, 0, 0, 0, FX]
        self.assertEqual(CL.goal_extent(ident), (CL.MARGIN, CL.MARGIN))
        c = int(round(0.70710678 * FX))
        turned = [c, 0, -c, 0, FX, 0, c, 0, c]
        rx, rz = CL.goal_extent(turned)
        self.assertAlmostEqual(rx / FX, 3.5 * 1.414, places=2)

    def test_errors(self):
        with self.assertRaises(CL.CellError):
            CL.read_grids(build_grid_stage(banana_cells={0}, unterminated=True))
        bad = bytearray(build_grid_stage())
        struct.pack_into("<I", bad, 0x40 + 0x54, len(bad) - 4)     # table runs past the end
        with self.assertRaises(CL.CellError):
            CL.read_grids(bytes(bad))


@unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
class RealCells(unittest.TestCase):
    def test_main_game_rules(self):
        from collections import Counter
        from trcore.rom import NdsRom
        from trcore.stc.document import StageDocument
        rom = NdsRom.from_file(REAL_ROM)
        total = Counter()
        for w in rom.stage_map()["worlds"]:
            for s in w["stages"]:
                data = rom.stage_file_decoded(s["stage_key"])
                total.update(CL.survey_stage(data, StageDocument(data, s["stage_key"])))
        for bad in ("cells without bits 0-3", "cells with bits above 6", "lists not sorted / with repeats",
                    "list index out of range", "bananas in no cell", "bumpers in no cell", "goals in no cell"):
            self.assertEqual(total.get(bad, 0), 0, bad)
        self.assertEqual(total["bananas"], 1718)
        self.assertGreater(total["bananas exactly reproduced"] / total["bananas"], 0.97)
        self.assertGreater(total["bumpers exactly reproduced"] / total["bumpers"], 0.9)
        self.assertGreater(total["goals exactly reproduced"] / total["goals"], 0.85)


if __name__ == "__main__":
    unittest.main()


class CollisionReader(unittest.TestCase):
    def test_face_round_trip(self):
        from trcore.stc.collision import dual_vectors, face_corners
        p, v1, v2 = (1.0, 2.0, 3.0), (4.0, 2.0, 3.0), (1.0, 2.5, 1.0)
        n, e1, e2 = dual_vectors(p, v1, v2)
        got = face_corners(p, n, e1, e2, quad=False)
        for a, b in zip(got, (p, v1, v2)):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y)
        quad = face_corners(p, n, e1, e2, quad=True)
        self.assertAlmostEqual(quad[2][0], 4.0)
        self.assertAlmostEqual(quad[2][2], 1.0)

    @unittest.skipUnless(REAL_ROM and os.path.exists(REAL_ROM), "set TRCORE_ROM to the Touch & Roll ROM")
    def test_real_collision_rules(self):
        from collections import Counter
        from trcore.rom import NdsRom
        from trcore.stagemodel import load_stage_model
        from trcore.stc.collision import survey_stage
        rom = NdsRom.from_file(REAL_ROM)
        total = Counter()
        for key in ("smb1_be01", "smb1_ad02", "smb1_ad21", "smbds_023"):
            sm = load_stage_model(rom, key)
            total.update(survey_stage(rom.stage_file_decoded(key), sm["triangles"]))
        for kind in ("quads", "triangles", "edges", "points"):
            self.assertGreater(total[kind], 0)
            self.assertEqual(total.get(f"{kind} in no cell", 0), 0)
            self.assertGreaterEqual(total[f"{kind}: cells within the 0.75 rule"], total[kind] - 1)
            self.assertFalse(total.get(f"{kind} with a nonzero spare word"))
        self.assertGreater(total["quads with every corner within 0.02 of a model corner"] / total["quads"], 0.9)
