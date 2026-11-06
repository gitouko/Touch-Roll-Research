"""Integration tests over the repository's own data/ tree.

Skipped entirely when data/ is absent (e.g. a code-only checkout).
Invariant tests run on ANY corpus. Baseline-count tests are pinned to the
corpus at commit 4ddcea8 and are skipped (with a message) if data/ differs,
so adding files never makes the suite fail spuriously - update BASELINE instead.
"""
import hashlib
import os
import unittest

from trcore import assets as A
from trcore.cli import run_roundtrip
from trcore.stc.document import StageDocument

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
HAS_DATA = os.path.isdir(os.path.join(ROOT, "data"))
BASELINE_DIGEST = "526b427f3e8a69587aab497d843ba54eaaef019bc58c118bcd9017eac18b2e0e"  # data/ @ 4ddcea8


@unittest.skipUnless(HAS_DATA, "no data/ directory in this checkout")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = A.build_index(ROOT)
        h = hashlib.sha256()
        for a in cls.index["assets"]:
            h.update((a["path"] + "\0" + a.get("sha256", "") + "\n").encode())
        cls.digest = h.hexdigest()
        cls.docs = {}
        by_path = {a["path"]: a for a in cls.index["assets"]}
        for p in cls.index["pairs"]:
            if p["ext"] != "stc" or p["status"] != "consistent":
                continue
            members = sorted((by_path[x] for v in p["layers"].values() for x in v),
                             key=lambda a: (a["container"] != "plain", a["path"]))
            cls.docs[p["stage_key"]] = StageDocument.from_file(
                os.path.join(ROOT, *members[0]["path"].split("/")), members[0]["path"])

    def baseline(self):
        if self.digest != BASELINE_DIGEST:
            self.skipTest("data/ differs from the 4ddcea8 baseline; baseline counts not applicable")

    # ---------------------------------------------------------- invariants
    def test_no_parse_crashes_or_errors(self):
        for key, doc in self.docs.items():
            self.assertNotIn("internal_parse_error", {d["code"] for d in doc.diagnostics}, key)
            self.assertFalse(doc.has_errors(), (key, doc.diagnostics))

    def test_noop_roundtrip_everything(self):
        rt = run_roundtrip(ROOT, self.index)
        self.assertEqual(rt["failures"], [])
        self.assertEqual(rt["lcts_source_identity_pass"], rt["lcts_sources_checked"])
        self.assertEqual(rt["lcts_decoded_matches_pair"], rt["lcts_sources_checked"])

    def test_compressed_inputs_are_decoded_never_parsed_raw(self):
        for a in self.index["assets"]:
            if a.get("container") == "lz10" and a.get("signature") == "LCTS" and a["path"].endswith("stage.stc"):
                doc = StageDocument.from_file(os.path.join(ROOT, *a["path"].split("/")))
                self.assertEqual(doc.container, "lz10")
                self.assertEqual(doc.decoded_sha256, a["payload_sha256"])
                break
        else:
            self.skipTest("no compressed stage.stc in this corpus")

    # ------------------------------------------------- baseline @ 4ddcea8
    def test_baseline_index(self):
        self.baseline()
        s = self.index["summary"]
        self.assertEqual(s["files"], 1779)
        self.assertEqual(s["unknown_content"] + s["lz10_invalid"], 0)
        self.assertEqual(s["pairs_by_status"], {"consistent": 596})
        self.assertEqual(s["pairs_with_lz10_and_plain_copies"], 595)
        self.assertEqual(s["error_count"], 0)
        lay = s["container_by_layer"]
        self.assertEqual(sum(lay["data/grouped"].values()), 588)
        self.assertTrue(all(k.startswith("lz10|") for k in lay["data/grouped"]))
        self.assertTrue(all(k.startswith("lz10|") for k in lay["data/decompressed"]))
        self.assertTrue(all(k.startswith("plain|") for k in lay["data/raw"]))
        self.assertEqual(self.index["missing_by_layer"], {
            "data/decompressed": ["smb2_ex14.nsbmd"],
            "data/grouped": ["smb1_ad06.nsbma", "smb2_ex14.nsbmd", "smb2_ex14.stc", "smbds_019.nsbma",
                             "smbds_037.nsbta", "smbds_045.nsbma", "smbds_046.nsbtp", "smbds_052.nsbta"]})
        stc_dups = [d["stage_keys"] for d in self.index["duplicates"] if d["ext"] == "stc"]
        self.assertEqual(stc_dups, [["smb1_ex07", "smb1_ex46"], ["smb1_ex09", "smb1_ex48"],
                                    ["smb1_ex19", "smb1_ex59"], ["smb1_ex22", "smb1_ex62"]])

    def test_baseline_layout(self):
        self.baseline()
        self.assertEqual(len(self.docs), 187)
        unique = {d.decoded_sha256 for d in self.docs.values()}
        self.assertEqual(len(unique), 183)
        variants = {k: d.layout_variant for k, d in self.docs.items() if d.layout_variant != "common"}
        self.assertEqual(variants, {"smbds_001": "no_start_slot"})
        # smb1_ex03: both goals and all bananas belong to group 1; header totals = slice sums
        ex03 = self.docs["smb1_ex03"].facts()
        self.assertEqual(ex03["group_names"], ["START", "MOT_smb1_ex03b"])
        self.assertEqual(ex03["pool_owner_groups"], {"A": [1], "B": [], "C": [1]})
        self.assertEqual(ex03["pool_totals"], {"A": 2, "B": 0, "C": 3})
        # pool A word +0x30 == 1 appears in exactly these stages, once each
        flagged = sorted(k for k, d in self.docs.items() if 1 in d.facts()["pool_a_u32_30"])
        self.assertEqual(flagged, ["smb1_ad25", "smb1_be02", "smb1_ex03", "smb2_ad26", "smb2_ex29"])
        for k in flagged:
            self.assertEqual(self.docs[k].facts()["pool_a_u32_30"].count(1), 1, k)
        unref = sorted(k for k, d in self.docs.items() if any(d.facts()["pool_unreferenced"].values()))
        self.assertEqual(unref, ["smb1_ad21", "smb1_ex19", "smb1_ex38", "smb1_ex59", "smb2_ad10",
                                 "smb2_ex30", "smb2_ex33", "smbds_043", "smbds_054"])
        sm = self.docs["smbds_001"].facts()
        self.assertEqual(sm["pool_totals"], {"A": 1, "B": 0, "C": 11})


if __name__ == "__main__":
    unittest.main()
