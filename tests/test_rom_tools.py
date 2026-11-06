"""Tests for the LZ10 encoder, ROM reader, ROM-copy writer and RAM-dump comparison.

Synthetic data only, except the optional RealRom class, which runs when the
environment variable TRCORE_ROM points to the USA ROM (SHA-1 3b0bf7f4...).
"""
import hashlib
import os
import random
import shutil
import struct
import tempfile
import unittest

from trcore import lz10, romwrite
from trcore.rom import NdsRom, RomError
from tests.synth import build_stage
from tests.synth_rom import build_rom


def backref_displacements(stream: bytes):
    size = stream[1] | stream[2] << 8 | stream[3] << 16
    i, out, disps = 4, 0, []
    while out < size:
        flags = stream[i]
        i += 1
        for bit in range(7, -1, -1):
            if out >= size:
                break
            if flags >> bit & 1:
                b1, b2 = stream[i], stream[i + 1]
                i += 2
                disps.append(((b1 & 15) << 8 | b2) + 1)
                out += (b1 >> 4) + 3
            else:
                i += 1
                out += 1
    return disps


class Encoder(unittest.TestCase):
    def test_roundtrip_varied_inputs(self):
        rng = random.Random(5)
        samples = [b"A", b"AB", b"\0" * 5000, bytes(range(256)) * 40, build_stage(),
                   bytes(rng.randrange(256) for _ in range(3000)),
                   b"".join(rng.choice([b"LCTS", b"\0\0\0\0", b"\x00\x10\x00\x00"]) for _ in range(2000))]
        for data in samples:
            enc = lz10.encode(data)
            self.assertEqual(lz10.decode(enc)[0], data)

    def test_never_uses_displacement_1(self):
        enc = lz10.encode(b"\0" * 4000 + b"ab" * 500)
        self.assertGreater(len(backref_displacements(enc)), 0)
        self.assertNotIn(1, backref_displacements(enc))

    def test_alternative_parse_differs_but_decodes_same(self):
        data = build_stage() * 3
        a, b = lz10.encode(data), lz10.encode(data, max_len=17)
        self.assertNotEqual(a, b)
        self.assertEqual(lz10.decode(b)[0], data)

    def test_refusals(self):
        with self.assertRaises(lz10.LZ10EncodeError):
            lz10.encode(b"")
        with self.assertRaises(lz10.LZ10EncodeError):
            lz10.encode(bytes(lz10.MAX_DECLARED_SIZE + 1))
        with self.assertRaises(lz10.LZ10EncodeError):
            lz10.encode(b"abc", max_len=19)


class RomReader(unittest.TestCase):
    def setUp(self):
        self.files = [("stcoli", "a_stc.lz", lz10.encode(build_stage())),
                      ("stcoli", "b_stc.lz", lz10.encode(build_stage(groups=("X", "Y")))),
                      ("", "readme.bin", b"hello world")]
        self.rom = NdsRom(build_rom(self.files))

    def test_header_and_files(self):
        i = self.rom.identity()
        self.assertTrue(i["header_crc_ok"])
        self.assertEqual(i["game_code"], "TEST")
        self.assertEqual(self.rom.paths, {0: "readme.bin", 1: "stcoli/a_stc.lz", 2: "stcoli/b_stc.lz"})
        self.assertEqual(self.rom.file_bytes("stcoli/b_stc.lz"), self.files[1][2])

    def test_no_profile_means_no_stage_map(self):
        self.assertIsNone(self.rom.profile())
        with self.assertRaises(RomError):
            self.rom.stage_map()

    def test_rejects_broken_images(self):
        with self.assertRaises(RomError):
            NdsRom(b"\0" * 100)
        bad = bytearray(build_rom(self.files))
        struct.pack_into("<I", bad, 0x48, len(bad) + 10)   # FAT outside the file
        with self.assertRaises(RomError):
            NdsRom(bytes(bad))


class RomWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trcore_rom_")
        self.small = lz10.encode(build_stage())
        self.files = [("stcoli", "a_stc.lz", self.small), ("stcoli", "b_stc.lz", b"\x10" + bytes(7)),
                      ("", "z.bin", b"z" * 100)]
        self.files[1] = ("stcoli", "b_stc.lz", lz10.encode(b"B" * 600))
        self.src = os.path.join(self.tmp, "in.nds")
        with open(self.src, "wb") as fh:
            fh.write(build_rom(self.files))
        self.rom = NdsRom.from_file(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_identical_replacement_gives_identical_rom(self):
        rec = romwrite.write_rom_copy(self.src, self.out("same.nds"), "stcoli/a_stc.lz", self.small)
        self.assertTrue(rec["output_identical_to_input"])
        self.assertTrue(os.path.exists(rec["record_path"]))

    def test_smaller_in_place(self):
        new = lz10.encode(b"tiny stage")
        new_bytes, rec = romwrite.build_replaced(self.rom, "stcoli/a_stc.lz", new)
        self.assertEqual(rec["placement"], "in_place")
        r2 = NdsRom(new_bytes)
        self.assertEqual(r2.file_bytes("stcoli/a_stc.lz"), new)
        self.assertEqual(r2.file_bytes("stcoli/b_stc.lz"), self.rom.file_bytes("stcoli/b_stc.lz"))
        self.assertEqual(r2.used_rom_size, self.rom.used_rom_size)

    def test_growth_relocates_and_moves_signature(self):
        big = bytes(random.Random(1).randrange(256) for _ in range(5000))
        new_bytes, rec = romwrite.build_replaced(self.rom, "stcoli/a_stc.lz", big)
        self.assertEqual(rec["placement"], "relocated")
        r2 = NdsRom(new_bytes)
        _, s, e = r2.file_range("stcoli/a_stc.lz")
        self.assertEqual(s % 0x200, 0)
        self.assertEqual(r2.used_rom_size, e)
        self.assertEqual(new_bytes[e:e + 2], b"ac")
        self.assertTrue(r2.header_crc_stored == r2.header_crc_computed)
        self.assertEqual(r2.file_bytes("z.bin"), b"z" * 100)
        # old slot zero-filled
        _, os_, oe = self.rom.file_range("stcoli/a_stc.lz")
        self.assertFalse(any(new_bytes[os_:oe]))

    def test_forced_relocation_keeps_bytes(self):
        new_bytes, rec = romwrite.build_replaced(self.rom, "stcoli/b_stc.lz",
                                                 self.rom.file_bytes("stcoli/b_stc.lz"), force_relocate=True)
        self.assertEqual(rec["placement"], "relocated")
        self.assertEqual(NdsRom(new_bytes).file_bytes("stcoli/b_stc.lz"), self.rom.file_bytes("stcoli/b_stc.lz"))

    def test_multi_replacement_and_final_verification(self):
        rec = romwrite.write_rom_copy_multi(self.src, self.out("multi.nds"), [
            ("stcoli/a_stc.lz", self.small, True),
            ("stcoli/b_stc.lz", lz10.encode(b"B" * 600, max_len=17), False)])
        self.assertEqual([r["placement"] for r in rec["replacements"]], ["relocated", "in_place"])
        r2 = NdsRom.from_file(self.out("multi.nds"))
        self.assertEqual(lz10.decode(r2.file_bytes("stcoli/b_stc.lz"))[0], b"B" * 600)

    def test_refusals(self):
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.write_rom_copy(self.src, self.src, "stcoli/a_stc.lz", self.small)
        open(self.out("exists.nds"), "wb").close()
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.write_rom_copy(self.src, self.out("exists.nds"), "stcoli/a_stc.lz", self.small)
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.write_rom_copy(self.src, self.out("x.bin"), "stcoli/a_stc.lz", self.small)
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.build_replaced(self.rom, "stcoli/a_stc.lz", b"")
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.build_replaced(self.rom, "stcoli/a_stc.lz", b"\x10\xff\xff\x00\x00")
        with self.assertRaises(RomError):
            romwrite.build_replaced(self.rom, "stcoli/missing_stc.lz", self.small)
        with open(self.src, "rb") as fh:
            self.assertEqual(hashlib.sha1(fh.read()).hexdigest(), hashlib.sha1(self.rom.data).hexdigest())

    def test_verify_catches_collateral_changes(self):
        new_bytes, rec = romwrite.build_replaced(self.rom, "stcoli/a_stc.lz", lz10.encode(b"tiny"))
        tampered = bytearray(new_bytes)
        _, s, _ = self.rom.file_range("z.bin")
        tampered[s] ^= 0xFF
        with self.assertRaises(romwrite.RomWriteRefused):
            romwrite.verify(self.rom, bytes(tampered), {rec["file_id"]: lz10.encode(b"tiny")})


ROM_PATH = os.environ.get("TRCORE_ROM")


@unittest.skipUnless(ROM_PATH and os.path.isfile(ROM_PATH), "set TRCORE_ROM to the USA ROM to run")
class RealRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = NdsRom.from_file(ROM_PATH)
        if cls.rom.profile() is None:
            raise unittest.SkipTest("TRCORE_ROM is not the profiled USA ROM")
        cls.map = cls.rom.stage_map()

    def test_stage_map(self):
        m = self.map
        self.assertEqual(m["problems"], [])
        self.assertTrue(all(a["ok"] for a in m["anchors"].values()))
        keys = [s["stage_key"] for w in m["worlds"] for s in w["stages"]]
        self.assertEqual(len(keys), 120)
        self.assertEqual(len(set(keys)), 120)
        for unused in ("smb1_ad25", "smb2_ex29", "smb2_ad26", "smb1_ad16", "smb1_ex19"):
            self.assertNotIn(unused, keys)

    def test_bonus_flag_stages_have_no_goals(self):
        from trcore.stc.document import StageDocument
        for w in self.map["worlds"]:
            for s in w["stages"]:
                if s["flags"] & 1:
                    self.assertEqual(s["stage"], 5)
                    doc = StageDocument(self.rom.stage_file_decoded(s["stage_key"]))
                    self.assertEqual(doc.pools["A"]["total"], 0, s["stage_key"])

    def test_encoder_reproduces_original_stage_files(self):
        paths = sorted(p for p in self.rom.id_by_path if p.startswith("stcoli/"))
        sample = paths if os.environ.get("TRCORE_SLOW") else paths[::12]
        for p in sample:
            comp = self.rom.file_bytes(p)
            self.assertEqual(lz10.encode(lz10.decode(comp)[0]), comp, p)

    def test_identity_rebuild(self):
        dec = self.rom.stage_file_decoded("smb1_be01")
        new_bytes, rec = romwrite.build_replaced(self.rom, "stcoli/smb1_be01_stc.lz", lz10.encode(dec))
        self.assertEqual(new_bytes, self.rom.data)


try:
    import lupa  # noqa: F401
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False


@unittest.skipUnless(HAS_LUPA, "optional: pip install lupa to run the BizHawk script under real Lua")
class BizHawkScript(unittest.TestCase):
    def test_dump_script_with_mocked_emulator(self):
        from lupa import LuaRuntime
        here = os.path.dirname(os.path.abspath(__file__))
        tmp = tempfile.mkdtemp(prefix="trcore_lua_")
        try:
            script = os.path.join(tmp, "trcore_dump_stage.lua")
            shutil.copy(os.path.join(here, os.pardir, "tools", "bizhawk", "trcore_dump_stage.lua"), script)
            stage = build_stage()
            ram = bytearray(0x400000)
            ptr, ptr2 = 0x02200000, 0x02280000
            ram[ptr - 0x02000000:ptr - 0x02000000 + len(stage)] = stage
            ram[ptr2 - 0x02000000:ptr2 - 0x02000000 + len(stage)] = stage
            frame = {"n": 0}

            class StopScript(Exception):
                pass

            def setvars():   # stage 7 from frame 3, then stage 9 from frame 100 (like playing W1-1 then W1-2)
                sid, p = (7, ptr) if frame["n"] < 100 else (9, ptr2)
                struct.pack_into("<I", ram, 0x0E8FC8, sid)
                struct.pack_into("<I", ram, 0x0E8FD8, sid)
                struct.pack_into("<I", ram, 0x0E9208, p if frame["n"] >= 3 else 0)
            setvars()
            lua = LuaRuntime(encoding=None, unpack_returned_tuples=True)
            g = lua.globals()

            def adv():
                frame["n"] += 1
                if frame["n"] > 250:
                    raise StopScript()   # the user pressing Stop in the Lua Console
                setvars()
            g.memory = lua.table_from({
                b"getmemorydomainlist": lambda: lua.table_from({0: b"ARM9 System Bus", 1: b"Main RAM"}),
                b"getmemorydomainsize": lambda name=None: 0x400000 if name == b"Main RAM" else 0x1000,
                b"read_u32_le": lambda a, d=None: struct.unpack_from("<I", ram, a)[0],
                b"read_bytes_as_binary_string": lambda a, n, d=None: bytes(ram[a:a + n])})
            g.emu = lua.table_from({b"frameadvance": adv, b"framecount": lambda: frame["n"],
                                    b"getsystemid": lambda: b"NDS"})
            g.console = lua.table_from({b"log": lambda *a: None})
            g.gameinfo = lua.table_from({b"getromhash": lambda: b"ABCDEF0123", b"getromname": lambda: b"t"})
            g.client = lua.table_from({b"getversion": lambda: b"mock", b"screenshot": lambda p: None})
            try:
                lua.execute(b"dofile(...)", script.encode())
            except Exception as exc:          # StopScript surfaces through Lua
                self.assertIn("StopScript", repr(exc) + str(type(exc)) + str(exc.__cause__ or ""))
            dumps = sorted(f for f in os.listdir(tmp) if f.endswith(".bin"))
            self.assertEqual(len(dumps), 2, dumps)
            metas = []
            for d in dumps:
                with open(os.path.join(tmp, d), "rb") as fh:
                    self.assertEqual(len(fh.read()), 0x400000)
                with open(os.path.join(tmp, d[:-4] + ".txt")) as fh:
                    metas.append(fh.read())
            self.assertTrue(any("loaded_stage_id=7" in m and "stage_data_ptr=0x02200000" in m for m in metas))
            self.assertTrue(any("loaded_stage_id=9" in m and "stage_data_ptr=0x02280000" in m for m in metas))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
