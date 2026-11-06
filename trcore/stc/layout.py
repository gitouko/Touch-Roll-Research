"""Evidence-annotated layout constants for decompressed LCTS (.stc) streams.

Every structural constant used by the parser is defined here together with the
evidence record that justifies it. Levels follow the project contract:
  0 historical lead, 1 directly observed bytes, 2 cross-sample structural
  corroboration, 3 controlled mutation, 4 confirmed in-game.
No entry below is above level 2. "candidate_label" values (goal, bumper,
banana, grid ...) are hypothesis names only.

Basis for every level-2 entry: all 183 unique decompressed .stc files in
gitouko/touch-roll-research @ 4ddcea8c22373730d263639433bdc59448b06060.
See docs/research_notes/stc_format_spec.md for the full write-up.
"""
from __future__ import annotations

EVIDENCE = {
    "E01": {"level": 2, "claim": "Bytes 'LCTS' at 0x00", "basis": "183/183"},
    "E02": {"level": 2, "claim": "u32 at 0x04 == 0x12 (meaning unknown)", "basis": "183/183"},
    "E03": {"level": 2, "claim": "0x1C..0x33 = six Q20.12 values, min<=max per axis (bounds-like)",
            "basis": "min<=max 183/183; semantics inferred"},
    "E04": {"level": 2, "claim": "u32(0x18) = base F of an array of u32(0x34) group descriptors, 0xCC bytes each",
            "basis": "array fits 183/183; descriptor tails zero 183/183; names resolve 183/183"},
    "E05": {"level": 2, "claim": "u32(0x38) start-record count, u32(0x3C) start-record offset; record 0x10 bytes: "
                                 "xyz Q20.12 + u32 angle-like word (16-bit binary angle candidate)",
            "basis": "182/183 main-game files (exception: variant E20); 12 four-player party stages in the ROM pack 4 "
                     "records at a 0x10 stride. The historical 0x1C size was 0x10 plus padding to a 32-byte boundary"},
    "E06": {"level": 2, "claim": "u32(0x40/0x44/0x48) = total records in pools A/B/C",
            "basis": "total >= referenced 181/183 per pool; exception is variant E20"},
    "E07": {"level": 2, "claim": "Pool A record 0x34: 3x3 Q20.12 + xyz Q20.12 + u32 word (goal candidate)",
            "basis": "orthonormal 166/167 files; one scaled case compensated by its group scale. "
                     "Historical 0x40 stride refuted (0x34 padded to 32-byte alignment)"},
    "E08": {"level": 2, "claim": "Pool B record 0x30: 3x3 Q20.12 + xyz Q20.12 (bumper candidate)",
            "basis": "11/11 files orthonormal, pools contiguous"},
    "E09": {"level": 2, "claim": "Pool C record 0x10: xyz Q20.12 + u32 word (banana candidate)",
            "basis": "pools contiguous 183/183"},
    "E10": {"level": 2, "claim": "Descriptor (count, offset) slices at +0x94/+0x9C/+0xA4 are contiguous "
                                 "prefixes of pools A/B/C; records past the slices are unreferenced",
            "basis": "contiguous 183/183, no overlaps; 8 files have unreferenced records"},
    "E11": {"level": 2, "claim": "Pool A word +0x30 in {0,1} (red-goal candidate; meaning NOT confirmed)",
            "basis": "value 1 in exactly 5 stages, one record each, incl. both user-reported red-goal stages"},
    "E12": {"level": 2, "claim": "Pool C word +0x0C in {0,1} (meaning unknown; bunch hypothesis untested)",
            "basis": "0: 2173 records, 1: 193 records in 58 files"},
    "E13": {"level": 2, "claim": "Descriptor +0x10 3x3 Q20.12 linear map (rotation*scale, det>0), +0x34 xyz",
            "basis": "det>0 in all groups; objects appear to be expressed in their group's frame"},
    "E14": {"level": 2, "claim": "Descriptor +0x40 u16 nx, +0x42 u16 nz, +0x44/+0x48 Q20.12 origin x/z, "
                                 "+0x4C/+0x50 Q20.12 step x/z (grid candidate)",
            "basis": "static-group grid covers header bounds in 151/183"},
    "E15": {"level": 2, "claim": "Descriptor +0x54 = offset of an nx*nz table of 8-byte entries",
            "basis": "table end aligns with next known region in 404/428 groups"},
    "E16": {"level": 2, "claim": "Descriptor (count, offset) tables: +0x7C stride 0x20, +0x84 stride 0x34, "
                                 "+0x8C stride 0x34; +0x74 stride unknown. Contents unknown (collision candidates)",
            "basis": "stride fits 183/183 (+0x7C, +0x8C), 181/181 (+0x84)"},
    "E17": {"level": 2, "claim": "0x4C..0x63 = six Q20.12 values, default (0,0,0,1,1,1); non-default iff u32(0x08)==2",
            "basis": "7/7 non-default files have u32(0x08)==2"},
    "E18": {"level": 2, "claim": "0x64..0xE3 all zero", "basis": "183/183"},
    "E19": {"level": 2, "claim": "Descriptor +0x04/+0x08 = offsets of NUL-terminated ASCII names (usually equal)",
            "basis": "182/183 equal; names like START01, MOT_<stage>b"},
    "E20": {"level": 1, "claim": "Variant 'no_start_slot': no valid start pair; pool totals at 0x3C/0x40/0x44",
            "basis": "single file in corpus; totals equal its group slice sums exactly"},
}

HEADER_SIZE = 0xE4          # 0x00..0xE3 (fixed fields + reserved zero block)
HEADER_FIELDS_END = 0x64
DESCRIPTOR_SIZE = 0xCC
START_RECORD_SIZE = 0x10

MAX_GROUPS = 4096           # sanity caps: far above anything observed (max 22)
MAX_START_RECORDS = 64
MAX_POOL_RECORDS = 1 << 16
MAX_TABLE_RECORDS = 1 << 20

# (offset, name, type, evidence)  type in {"magic", "u32", "q12"}
HEADER_FIELDS = [
    (0x00, "magic", "magic", "E01"),
    (0x04, "u32_04", "u32", "E02"),
    (0x08, "u32_08", "u32", "E17"),
    (0x0C, "u32_0C", "u32", None),
    (0x10, "u32_10", "u32", None),
    (0x14, "u32_14", "u32", None),
    (0x18, "descriptor_base", "u32", "E04"),
    (0x1C, "bounds_min_x", "q12", "E03"),
    (0x20, "bounds_min_y", "q12", "E03"),
    (0x24, "bounds_min_z", "q12", "E03"),
    (0x28, "bounds_max_x", "q12", "E03"),
    (0x2C, "bounds_max_y", "q12", "E03"),
    (0x30, "bounds_max_z", "q12", "E03"),
    (0x34, "group_count", "u32", "E04"),
    (0x38, "start_count", "u32", "E05"),
    (0x3C, "start_offset", "u32", "E05"),
    (0x40, "pool_a_total", "u32", "E06"),
    (0x44, "pool_b_total", "u32", "E06"),
    (0x48, "pool_c_total", "u32", "E06"),
    (0x4C, "box2_a_x", "q12", "E17"),
    (0x50, "box2_a_y", "q12", "E17"),
    (0x54, "box2_a_z", "q12", "E17"),
    (0x58, "box2_b_x", "q12", "E17"),
    (0x5C, "box2_b_y", "q12", "E17"),
    (0x60, "box2_b_z", "q12", "E17"),
]
BOX2_DEFAULT = (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)

# Object pools: key, header-total field, descriptor slice offset, stride, candidate label, evidence
POOLS = [
    ("A", "pool_a_total", 0x94, 0x34, "goal", "E07"),
    ("B", "pool_b_total", 0x9C, 0x30, "bumper", "E08"),
    ("C", "pool_c_total", 0xA4, 0x10, "banana", "E09"),
]
# Variant E20 stores the three totals one word earlier.
NO_START_SLOT_TOTAL_OFFSETS = {"A": 0x3C, "B": 0x40, "C": 0x44}

# Descriptor (count, offset) tables with known record stride (contents opaque).
GROUP_TABLES = [
    ("table_74", 0x74, None),
    ("table_7C", 0x7C, 0x20),
    ("table_84", 0x84, 0x34),
    ("table_8C", 0x8C, 0x34),
]
CELL_ENTRY_SIZE = 8
