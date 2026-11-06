import unittest

from trcore import lz10
from tests.synth import lz10_literal_encode


class DecodeOk(unittest.TestCase):
    def test_literal_only_roundtrip(self):
        for n in (1, 7, 8, 9, 64, 1000):
            data = bytes((i * 37 + 11) & 0xFF for i in range(n))
            out, info = lz10.decode(lz10_literal_encode(data))
            self.assertEqual(out, data)
            self.assertEqual(info.declared_size, n)
            self.assertEqual(info.backrefs, 0)
            self.assertEqual(info.trailing_bytes, 0)

    def test_backref_non_overlapping(self):
        # literals "ABCD", then copy 4 bytes from distance 4 -> "ABCDABCD"
        stream = bytes([0x10, 8, 0, 0, 0b00001000]) + b"ABCD" + bytes([(4 - 3) << 4, 4 - 1])
        out, info = lz10.decode(stream)
        self.assertEqual(out, b"ABCDABCD")
        self.assertEqual((info.literals, info.backrefs, info.overlapping_backrefs), (4, 1, 0))

    def test_backref_overlapping_run(self):
        # literal 'Z', then copy 18 bytes from distance 1 -> 19 x 'Z'
        stream = bytes([0x10, 19, 0, 0, 0b01000000]) + b"Z" + bytes([0xF0, 0x00])
        out, info = lz10.decode(stream)
        self.assertEqual(out, b"Z" * 19)
        self.assertEqual(info.overlapping_backrefs, 1)

    def test_stops_at_declared_size_mid_block(self):
        stream = bytes([0x10, 3, 0, 0, 0x00]) + b"abc"
        out, _ = lz10.decode(stream)
        self.assertEqual(out, b"abc")

    def test_trailing_bytes_reported(self):
        stream = lz10_literal_encode(b"abcdefgh") + b"\x00\x00\x00"
        _, info = lz10.decode(stream)
        self.assertEqual(info.trailing_bytes, 3)
        self.assertTrue(info.trailing_all_zero)


class DecodeErrors(unittest.TestCase):
    def assertCode(self, data, code, **kw):
        with self.assertRaises(lz10.LZ10Error) as cm:
            lz10.decode(data, **kw)
        self.assertEqual(cm.exception.code, code)

    def test_truncated_header(self):
        self.assertCode(b"\x10\x01", lz10.CODE_TRUNCATED_HEADER)

    def test_bad_tag(self):
        self.assertCode(b"\x11\x08\x00\x00" + b"\x00" * 9, lz10.CODE_BAD_TAG)

    def test_zero_size(self):
        self.assertCode(b"\x10\x00\x00\x00\x00", lz10.CODE_ZERO_SIZE)

    def test_size_cap(self):
        self.assertCode(b"\x10\xff\xff\xff", lz10.CODE_SIZE_CAP, max_output=1024)

    def test_truncated_flag(self):
        self.assertCode(b"\x10\x08\x00\x00", lz10.CODE_TRUNCATED_FLAGS)

    def test_truncated_literal(self):
        self.assertCode(b"\x10\x08\x00\x00\x00abc", lz10.CODE_TRUNCATED_LITERAL)

    def test_truncated_backref(self):
        self.assertCode(bytes([0x10, 8, 0, 0, 0b01000000]) + b"A" + b"\x10", lz10.CODE_TRUNCATED_REF)

    def test_illegal_displacement(self):
        # back-reference before any output
        self.assertCode(bytes([0x10, 8, 0, 0, 0b10000000, 0x00, 0x00]), lz10.CODE_ILLEGAL_DISP)
        # distance 2 with only 1 byte produced
        self.assertCode(bytes([0x10, 8, 0, 0, 0b01000000]) + b"A" + bytes([0x00, 0x01]), lz10.CODE_ILLEGAL_DISP)

    def test_overrun(self):
        # declared 4, literal + 18-byte copy would overrun
        self.assertCode(bytes([0x10, 4, 0, 0, 0b01000000]) + b"A" + bytes([0xF0, 0x00]), lz10.CODE_OVERRUN)

    def test_never_returns_partial_output(self):
        good = lz10_literal_encode(bytes(range(100)))
        for cut in range(4, len(good)):
            with self.assertRaises(lz10.LZ10Error):
                lz10.decode(good[:cut])


if __name__ == "__main__":
    unittest.main()
