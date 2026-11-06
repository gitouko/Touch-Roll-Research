import random
import struct
import unittest

from trcore.stc.document import StageDocument
from tests.synth import IDENTITY, build_stage, lz10_literal_encode


def codes(doc, severity=None):
    return {d["code"] for d in doc.diagnostics if severity is None or d["severity"] == severity}


class CommonLayout(unittest.TestCase):
    def test_parses_synthetic_stage(self):
        data = build_stage()
        doc = StageDocument(data)
        self.assertEqual(doc.container, "plain")
        self.assertEqual(doc.layout_variant, "common")
        self.assertFalse(doc.has_errors(), doc.diagnostics)
        f = doc.facts()
        self.assertEqual(f["group_names"], ["START01"])
        self.assertEqual(f["pool_totals"], {"A": 1, "B": 0, "C": 2})
        self.assertEqual(f["pool_a_u32_30"], [0])
        self.assertEqual(f["pool_c_u32_0C_counts"], {"0": 1, "1": 1})
        self.assertEqual(doc.start["records"][0]["position"], [0.0, 0.0, 10.0])
        self.assertEqual(doc.pools["A"]["records"][0]["translation"], [0.0, 0.0, -10.0])
        for name in ("magic_lcts", "descriptor_array_in_bounds", "pools_in_bounds", "pool_slices_contiguous",
                     "no_span_overlaps", "roundtrip_source_identity", "roundtrip_decoded_identity",
                     "pool_a_matrices_orthonormal", "cell_tables_in_bounds", "group_tables_in_bounds"):
            self.assertEqual(doc.checks[name], "pass", name)

    def test_coverage_accounts_for_every_byte(self):
        data = build_stage()
        cov = StageDocument(data).coverage
        self.assertEqual(cov["claimed_by_views"] + cov["zero_fill"] + cov["opaque"], len(data))
        self.assertEqual(cov["length"], len(data))

    def test_noop_export_is_byte_identical(self):
        data = build_stage()
        doc = StageDocument(data)
        self.assertEqual(doc.export_decoded(), data)
        self.assertEqual(doc.export_source(), data)

    def test_lz10_container_is_decoded_not_parsed_raw(self):
        plain = build_stage()
        comp = lz10_literal_encode(plain)
        doc = StageDocument(comp)
        self.assertEqual(doc.container, "lz10")
        self.assertEqual(doc.export_source(), comp)      # compressed passthrough
        self.assertEqual(doc.export_decoded(), plain)
        self.assertEqual(doc.facts(), StageDocument(plain).facts())

    def test_objects_owned_by_second_group(self):
        doc = StageDocument(build_stage(groups=("START", "MOT_test_b"), goal_owner=1, banana_owner=1))
        f = doc.facts()
        self.assertEqual(f["pool_owner_groups"], {"A": [1], "B": [], "C": [1]})
        self.assertEqual(f["pool_referenced"], {"A": 1, "B": 0, "C": 2})
        self.assertFalse(doc.has_errors())

    def test_unreferenced_records_are_info_not_error(self):
        doc = StageDocument(build_stage(unreferenced_bananas=1))
        self.assertIn("pool_unreferenced_records", codes(doc, "info"))
        self.assertEqual(doc.pools["C"]["unreferenced"], 1)
        self.assertEqual(doc.pools["C"]["records"][1]["group"], None)
        self.assertEqual(doc.checks["pools_fully_referenced"], "fail")
        self.assertFalse(doc.has_errors())

    def test_scaled_goal_matrix_is_reported(self):
        doc = StageDocument(build_stage(goals=((1, (1, 0, 0, 0, 1.5, 0, 0, 0, 1), (0, 0, 0)),)))
        self.assertIn("pool_A_matrix_scaled", codes(doc, "info"))
        self.assertEqual(doc.checks["pool_a_matrices_orthonormal"], "fail")
        self.assertEqual(doc.facts()["pool_a_u32_30"], [1])

    def test_variant_detected_by_rule(self):
        doc = StageDocument(build_stage(variant="no_start_slot"))
        self.assertEqual(doc.layout_variant, "no_start_slot")
        self.assertIn("layout_variant_no_start_slot", codes(doc, "info"))
        self.assertEqual(doc.facts()["pool_totals"], {"A": 1, "B": 0, "C": 2})
        self.assertEqual(doc.checks["start_slot_valid"], "fail")
        self.assertFalse(doc.has_errors())

    def test_multiple_starts_use_0x10_stride(self):
        starts = ((-4, 0, 4, 0xE000), (4, 0, 4, 0x1FFF), (4, 0, -4, 0x5FFF), (-4, 0, -4, 0xA000))
        doc = StageDocument(build_stage(starts=starts, goals=()))
        recs = doc.start["records"]
        self.assertEqual([r["offset"] for r in recs], ["0x100", "0x110", "0x120", "0x130"])
        self.assertEqual(recs[2]["position"], [4.0, 0.0, -4.0])
        self.assertEqual(recs[3]["u32_0C"], 0xA000)
        self.assertEqual(doc.checks["no_span_overlaps"], "pass")
        self.assertFalse(doc.has_errors(), doc.diagnostics)

    def test_two_goals_use_0x34_stride(self):
        goals = ((0, IDENTITY, (0, 0, -20)), (1, IDENTITY, (0, -8.5, 17)))
        doc = StageDocument(build_stage(goals=goals))
        recs = doc.pools["A"]["records"]
        self.assertEqual([r["offset"] for r in recs], ["0x100", "0x134"])
        self.assertEqual([r["u32_30"] for r in recs], [0, 1])
        self.assertEqual(recs[1]["translation"], [0.0, -8.5, 17.0])


class Malformed(unittest.TestCase):
    """Bad input must yield structured diagnostics, never an exception."""

    def mutate(self, offset, fmt, *values):
        b = bytearray(build_stage())
        struct.pack_into(fmt, b, offset, *values)
        return StageDocument(bytes(b))

    def test_not_lcts(self):
        doc = StageDocument(b"NOPE" + bytes(300))
        self.assertIn("not_lcts", codes(doc, "error"))
        self.assertIsNone(doc.export_decoded())

    def test_truncated_header(self):
        doc = StageDocument(build_stage()[:0x80])
        self.assertIn("truncated_header", codes(doc, "error"))

    def test_descriptor_base_out_of_bounds(self):
        doc = self.mutate(0x18, "<I", 0x7FFFFFF0)
        self.assertIn("descriptor_array_invalid", codes(doc, "error"))

    def test_absurd_group_count(self):
        doc = self.mutate(0x34, "<I", 0xFFFFFFFF)
        self.assertIn("descriptor_array_invalid", codes(doc, "error"))

    def test_pool_total_overflow(self):
        doc = self.mutate(0x48, "<I", 0x00FFFFFF)
        self.assertTrue(codes(doc, "error") & {"pool_out_of_bounds", "pool_unlocatable"})

    def test_bad_lz10(self):
        comp = lz10_literal_encode(build_stage())
        doc = StageDocument(comp[:-5])
        self.assertTrue(any(c.startswith("lz10_") for c in codes(doc, "error")))

    def test_random_corruption_never_raises(self):
        base = build_stage(groups=("START", "MOT_x"), goal_owner=1)
        rng = random.Random(1234)
        for _ in range(400):
            b = bytearray(base)
            for _ in range(rng.randint(1, 6)):
                pos = rng.randrange(0, min(len(b), 0x200)) if rng.random() < 0.7 else rng.randrange(len(b))
                b[pos] = rng.randrange(256)
            if rng.random() < 0.2:
                b = b[: rng.randrange(4, len(b))]
            doc = StageDocument(bytes(b))
            self.assertNotIn("internal_parse_error", codes(doc), doc.diagnostics)
            self.assertEqual(doc.export_source(), bytes(b))


if __name__ == "__main__":
    unittest.main()
