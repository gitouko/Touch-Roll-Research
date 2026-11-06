import unittest

from trcore.binreader import BinReader, ReadOutOfBounds, align_up


class BinReaderTests(unittest.TestCase):
    def setUp(self):
        self.r = BinReader(bytes([0x00, 0x10, 0x00, 0x00, 0x00, 0xF0, 0xFF, 0xFF, 0x41, 0x42, 0x00, 0x7F]))

    def test_values(self):
        self.assertEqual(self.r.u32(0), 0x1000)
        self.assertEqual(self.r.q12(0), 1.0)
        self.assertEqual(self.r.s32(4), -4096)
        self.assertEqual(self.r.q12(4), -1.0)
        self.assertEqual(self.r.u16(8), 0x4241)
        self.assertEqual(self.r.cstring(8), "AB")

    def test_bounds(self):
        for fn, off in ((self.r.u32, 9), (self.r.u32, -1), (self.r.u16, 11), (self.r.u8, 12)):
            with self.assertRaises(ReadOutOfBounds):
                fn(off)
        with self.assertRaises(ReadOutOfBounds):
            self.r.slice(10, 3)
        self.assertIsNone(self.r.cstring(11))   # 0x7F is not printable / no terminator
        self.assertIsNone(self.r.cstring(100))

    def test_immutable_copy(self):
        src = bytearray(b"LCTS")
        r = BinReader(src)
        src[0] = 0
        self.assertEqual(r.data, b"LCTS")

    def test_align(self):
        self.assertEqual(align_up(0x134, 0x20), 0x140)
        self.assertEqual(align_up(0x140, 0x20), 0x140)
        with self.assertRaises(ValueError):
            align_up(5, 3)


if __name__ == "__main__":
    unittest.main()
