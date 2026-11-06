import contextlib
import io
import json
import os
import shutil
import struct
import tempfile
import unittest

from trcore import assets as A
from trcore import cli
from tests.synth import build_stage, lz10_literal_encode


def nitro(magic: bytes, body: bytes = b"\x00" * 16) -> bytes:
    size = 16 + len(body)
    return magic + struct.pack("<HHIHH", 0xFEFF, 1, size, 16, 1) + body


class NameParsing(unittest.TestCase):
    def test_forms(self):
        cases = {
            "data/raw/smb1_be01.stc": ("smb1_be01", "stc", "dotted"),
            "data/x/smb1_be01_stc.lz": ("smb1_be01", "stc", "flattened_lz"),
            "data/x/smb1_be01.nsbmd.lz": ("smb1_be01", "nsbmd", "dotted_lz"),
            "data/grouped/smb1_ad02/stage.stc": ("smb1_ad02", "stc", "grouped_role_file"),
            "data/raw/SMB1_AD02.STC": ("smb1_ad02", "stc", "dotted"),
            "data/raw/smbds_046.nsbtp": ("smbds_046", "nsbtp", "dotted"),
        }
        for path, (key, ext, form) in cases.items():
            n = A.parse_name(path)
            self.assertEqual((n["stage_key"], n["ext"], n["form"]), (key, ext, form), path)
        self.assertEqual(A.parse_name("data/raw/SMB1_AD02.STC")["stage_key_original"], "SMB1_AD02")

    def test_role_words_never_become_stage_keys(self):
        for path in ("stage.stc", "data/grouped/texture/texture.nsbtx", "x/stage_stc.lz", "data/raw/model_nsbmd"):
            n = A.parse_name(path)
            self.assertIsNone(n["stage_key"], path)
            self.assertTrue(any(i["code"] == "ambiguous_stage_key" for i in n["issues"]), path)

    def test_unrecognized(self):
        self.assertEqual(A.parse_name("data/raw/readme.txt")["form"], "unrecognized")


class Classification(unittest.TestCase):
    def test_by_content_not_name(self):
        stage = build_stage()
        info, payload = A.classify_bytes(lz10_literal_encode(stage))
        self.assertEqual((info["container"], info["signature"]), ("lz10", "LCTS"))
        self.assertEqual(payload, stage)
        info, _ = A.classify_bytes(stage)
        self.assertEqual((info["container"], info["signature"]), ("plain", "LCTS"))

    def test_nitro_header_checked(self):
        info, _ = A.classify_bytes(nitro(b"BMD0"))
        self.assertTrue(info["nitro"]["ok"])
        bad = bytearray(nitro(b"BTX0"))
        struct.pack_into("<I", bad, 8, 999)
        info, _ = A.classify_bytes(bytes(bad))
        self.assertFalse(info["nitro"]["ok"])

    def test_invalid_and_unknown(self):
        info, payload = A.classify_bytes(b"\x10\x40\x00\x00\x00abc")
        self.assertEqual(info["container"], "lz10_invalid")
        self.assertIsNone(payload)
        info, _ = A.classify_bytes(b"\x00\x01\x02\x03")
        self.assertEqual(info["container"], "unknown")


class TempCorpus(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="trcore_test_")
        self.stage = build_stage()
        self.write("data/raw/smbx_001.stc", self.stage)
        self.write("data/decompressed/smbx_001_stc.lz", lz10_literal_encode(self.stage))
        self.write("data/grouped/smbx_001/stage.stc", lz10_literal_encode(self.stage))
        self.write("data/raw/smbx_002.stc", self.stage)  # identical content under another key
        self.write("data/raw/smbx_001.nsbmd", nitro(b"BMD0"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, data):
        p = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_index_pairs_and_warnings(self):
        ix = A.build_index(self.root)
        s = ix["summary"]
        self.assertEqual(s["files"], 5)
        self.assertEqual(s["pairs_by_status"], {"consistent": 3})
        self.assertEqual(s["error_count"], 0)
        self.assertEqual(s["issue_counts"]["warning:folder_name_contradicts_content"], 1)
        self.assertEqual(s["issue_counts"]["warning:compressed_content_without_lz_suffix"], 1)
        self.assertEqual(ix["missing_by_layer"]["data/decompressed"], ["smbx_001.nsbmd", "smbx_002.stc"])
        self.assertEqual(ix["duplicates"][0]["stage_keys"], ["smbx_001", "smbx_002"])
        self.assertTrue(all(not os.path.isabs(a["path"]) for a in ix["assets"]))

    def test_grouped_key_needs_corroboration(self):
        self.write("data/grouped/orphan/stage.stc", lz10_literal_encode(build_stage(groups=("X",))))
        ix = A.build_index(self.root)
        orphan = [a for a in ix["assets"] if a["path"] == "data/grouped/orphan/stage.stc"][0]
        self.assertIn("grouped_stage_key_unconfirmed", [i["code"] for i in orphan["issues"]])
        ok = [a for a in ix["assets"] if a["path"] == "data/grouped/smbx_001/stage.stc"][0]
        self.assertNotIn("grouped_stage_key_unconfirmed", [i["code"] for i in ok["issues"]])

    def test_payload_mismatch_is_an_error(self):
        other = bytearray(self.stage)
        other[0x20] ^= 0xFF
        self.write("data/grouped/smbx_001/stage.stc", lz10_literal_encode(bytes(other)))
        ix = A.build_index(self.root)
        self.assertEqual(ix["summary"]["pairs_by_status"].get("payload_mismatch"), 1)
        self.assertGreater(ix["summary"]["error_count"], 0)

    def test_validate_exit_codes_and_determinism(self):
        out1 = os.path.join(self.root, "gen1")
        out2 = os.path.join(self.root, "gen2")
        code, text = self.run_cli("validate", "--root", self.root, "--out", out1)
        self.assertEqual(code, 0, text)
        code, _ = self.run_cli("validate", "--root", self.root, "--out", out2)
        self.assertEqual(code, 0)
        for dirpath, _, files in os.walk(out1):
            for fn in files:
                if fn == "run_summary.json":
                    continue
                a = os.path.join(dirpath, fn)
                b = os.path.join(out2, os.path.relpath(a, out1))
                with open(a, "rb") as fa, open(b, "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), fn)
        stages = sorted(os.listdir(os.path.join(out1, "stages")))
        self.assertEqual(len(stages), 2)
        self.assertTrue(all(name.startswith(("smbx_001.", "smbx_002.")) for name in stages))
        with open(os.path.join(out1, "validation_matrix.json"), encoding="utf-8") as fh:
            matrix = json.load(fh)
        self.assertEqual(matrix["unique_stage_contents"], 1)
        self.assertEqual(matrix["roundtrip"]["failures"], [])

    def test_validate_fails_on_corrupt_compressed_file(self):
        self.write("data/decompressed/smbx_003_stc.lz", b"\x10\xff\x00\x00\x00")
        code, text = self.run_cli("validate", "--root", self.root, "--out", os.path.join(self.root, "gen"))
        self.assertEqual(code, 1, text)
        self.assertIn("PROBLEM", text)

    def test_empty_corpus_is_a_usage_error(self):
        empty = tempfile.mkdtemp(prefix="trcore_empty_")
        try:
            code, text = self.run_cli("validate", "--root", empty, "--out", os.path.join(empty, "gen"))
            self.assertEqual(code, 2)
            self.assertIn("no input files", text)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_refuses_output_inside_data(self):
        code, text = self.run_cli("validate", "--root", self.root, "--out", os.path.join(self.root, "data", "out"))
        self.assertEqual(code, 2)
        self.assertIn("refusing", text)

    def test_inputs_untouched(self):
        before = {a["path"]: a["sha256"] for a in A.build_index(self.root)["assets"]}
        self.run_cli("validate", "--root", self.root, "--out", os.path.join(self.root, "gen"))
        self.run_cli("roundtrip", "--root", self.root)
        after = {a["path"]: a["sha256"] for a in A.build_index(self.root)["assets"]}
        self.assertEqual(before, after)

    def test_inspect_json_refuses_input_path(self):
        p = os.path.join(self.root, "data", "raw", "smbx_001.stc")
        code, _ = self.run_cli("inspect", p, "--json", p)
        self.assertEqual(code, 2)
        with open(p, "rb") as fh:
            self.assertEqual(fh.read(), self.stage)


if __name__ == "__main__":
    unittest.main()
