# LCTS (`.stc`) stage format — living specification

**Status:** research draft. Nothing in this document is confirmed in-game (no field is above Level 2).
**Corpus:** all 187 decompressed `.stc` files (183 unique contents) in `data/raw` at commit
`4ddcea8c22373730d263639433bdc59448b06060`. Each LZ10 copy in `data/decompressed` and `data/grouped`
decodes to exactly the matching `data/raw` file (SHA-256), so the three layers hold one corpus.
**Executable form:** `trcore/stc/layout.py` (constants + evidence IDs) and `trcore/stc/document.py`
(parser). `py -3 -m trcore validate` re-runs every count quoted here.

Confidence levels: **0** historical lead · **1** observed bytes · **2** holds across the corpus ·
**3** controlled byte mutation · **4** confirmed in-game. A byte layout can be Level 2 while its
*meaning* is still unknown; labels such as "goal" or "banana" below are hypothesis names.

All offsets are absolute byte offsets into the **decompressed** stream. All values are little-endian.
"Q20.12" means `signed_int32 / 4096`.

---

## 1. Container

| Item | Finding | Level |
|---|---|---|
| Compression | ROM-extracted stage files are LZ10 (`0x10` tag, 24-bit size). 595/595 decode with zero trailing bytes. | 2 |
| Folder names | `data/decompressed` holds the **compressed** files; `data/raw` holds the **decompressed** ones; `data/grouped/*/stage.stc` are compressed copies. | 2 |
| Duplicates | `smb1_ex07`=`ex46`, `ex09`=`ex48`, `ex19`=`ex59`, `ex22`=`ex62` are byte-identical, so they are not independent samples. | 1 |

## 2. Header (0x00–0xE3)

| Offset | Type | Name in trcore | Observation | Evidence | Level |
|---|---|---|---|---|---|
| 0x00 | 4 bytes | `magic` | `LCTS` in 183/183 | E01 | 2 |
| 0x04 | u32 | `u32_04` | `0x12` in 183/183; meaning unknown (not proven to be a version) | E02 | 2 |
| 0x08 | u32 | `u32_08` | 0 ×175, 2 ×7, 1 ×1 (`smbds_001`) | E17 | 2 |
| 0x0C | u32 | `u32_0C` | 0 ×155, 0xA0 ×15, 0x1F40 ×11, 0x12C0 ×2; meaning unknown | — | 1 |
| 0x10 | u32 | `u32_10` | 28 distinct values (most common 0x3E80, 0x493E00, 0xBB80); meaning unknown | — | 1 |
| 0x14 | u32 | `u32_14` | always ≥ `group_count` (equal in 158/183); meaning unknown | — | 2 |
| 0x18 | u32 | `descriptor_base` (F) | offset of the group-descriptor array (§5); 32-byte aligned in 183/183 | E04 | 2 |
| 0x1C–0x30 | 6 × Q20.12 | `bounds_min_xyz`, `bounds_max_xyz` | min ≤ max on every axis in 183/183; "bounds" is an inference | E03 | 2 |
| 0x34 | u32 | `group_count` (N) | 1 ×123, 2 ×24, up to 22 | E04 | 2 |
| 0x38 | u32 | `start_count` | 1 in 182/183 | E05 | 2 |
| 0x3C | u32 | `start_offset` | 0xE4 in 180; in `smb1_ad30` and `smbds_029` it equals `align32(F + N·0xCC)`, i.e. the start record sits right after the descriptor array | E05 | 2 |
| 0x40 | u32 | `pool_a_total` | total records in pool A ("goal" candidate) | E06 | 2 |
| 0x44 | u32 | `pool_b_total` | total records in pool B ("bumper" candidate) | E06 | 2 |
| 0x48 | u32 | `pool_c_total` | total records in pool C ("banana" candidate) | E06 | 2 |
| 0x4C–0x60 | 6 × Q20.12 | `box2_*` | (0,0,0,1,1,1) in 175 files; other values exactly in the 7 files where `u32_08 == 2` | E17 | 2 |
| 0x64–0xE3 | — | reserved | all zero in 183/183 | E18 | 2 |

The historical note that "0x58–0x60 contain 0x1000" is the default half of the `box2` block.

## 3. Start record (0x1C bytes, at `start_offset`)

| +Offset | Type | Observation | Level |
|---|---|---|---|
| +0x00 | 3 × Q20.12 | position-like xyz | 2 (structure) |
| +0x0C | u32 | 0 ×138, 0xC000 ×18, 0x3FFF ×14, 0x1FFF ×6, 0x7FFE, 0xE16C, … — consistent with a 16-bit binary angle (0x4000 = 90°) but **unverified** | 1 |
| +0x10 | 12 bytes | zero in every observed record | 2 |

## 4. Object pools

Each pool is one contiguous array. Its **total** is in the header (§2); each group descriptor
(§5) references a **slice** `(count, offset)` of it. Slices of different groups are contiguous
prefixes of the pool in group order (183/183, no overlaps). Records after the last slice are
**unreferenced** (E10).

| Pool | Stride | Layout | Candidate label | Evidence | Level |
|---|---|---|---|---|---|
| A | **0x34** | 3×3 Q20.12 matrix (+0x00), xyz Q20.12 (+0x24), u32 word (+0x30) | goal | E07 | 2 |
| B | 0x30 | 3×3 Q20.12 matrix, xyz Q20.12 | bumper | E08 | 2 |
| C | 0x10 | xyz Q20.12, u32 word (+0x0C) | banana | E09 | 2 |

* **Pool A stride is 0x34, not 0x40.** With a single record, 0x34 padded to the next 32-byte
  boundary looks like 0x40; with two records the second one starts at 0x134 (`smb1_be02`,
  `smb1_ex03`, …). Matrices are orthonormal at stride 0x34 in 168/169 files. The exception,
  `smb2_ad26`, has a 1.5 y-scale that cancels its group's 0.667 y-scale (E13).
* **Pool A word +0x30** is 0 in 172 records and 1 in exactly five stages, once each:
  `smb1_ad25`, `smb1_be02`, `smb1_ex03`, `smb2_ad26`, `smb2_ex29` (E11). Both user-reported
  red-goal stages are in this set; `smb1_ad16` (two records, both 0) is a control. **Red-goal meaning is a
  hypothesis** until tested.
* **Pool C word +0x0C** is 0 in 2,173 records and 1 in 193 records across 58 files (E12). Meaning
  unknown (a "bunch" flag is one untested hypothesis).
* **Unreferenced records** (header total > referenced): `smb1_ad21` (20/20 B), `smb1_ex19` and its
  duplicate `ex59` (13/13 C), `smb1_ex38` (6/8 C), `smb2_ad10` (1/1 A), `smb2_ex30` (48/48 C),
  `smb2_ex33` (8/8 C), `smbds_043` (4/10 B), `smbds_054` (1/1 A, 4/12 C). Whether the game shows
  them is open (§8, Q2).
* Pools usually start at 0x100 in A→B→C order. The pool after A starts at the next 32-byte
  boundary in 161 of the 162 files where it directly follows A (`smbds_059` packs C right after A); B→C is packed tight in 8 files and
  32-byte aligned in 4. In a few files a pool is placed elsewhere (e.g. `smb1_ad16` pool C after the
  descriptor array). The parser follows offsets and never assumes positions.

## 5. Group descriptors (0xCC bytes each, `N` at F)

Previously called the "footer". It is an **array**: descriptor *k* is at `F + k·0xCC` (E04).
What older notes called `F+0x90 … F+0xA8` are fields of descriptor 0 only.

| +Offset | Type | Observation | Evidence | Level |
|---|---|---|---|---|
| +0x00 | u32 | 0 in most groups | — | 1 |
| +0x04, +0x08 | u32, u32 | offsets of NUL-terminated ASCII names (e.g. `START01`, `MOT_smb1_ex03b`); equal in 182/183 files (`smb2_ex14` group 1: `tes1` vs `MOT_KNIFE_SDWg`) | E19 | 2 |
| +0x10 | 3×3 Q20.12 | linear transform; det > 0 in every group; may include scale (e.g. 0.198, 2.0, y×12.5) | E13 | 2 |
| +0x34 | 3 × Q20.12 | translation | E13 | 2 |
| +0x40 / +0x42 | u16, u16 | `nx`, `nz` (grid candidate) | E14 | 2 |
| +0x44 / +0x48 | Q20.12 | grid origin x / z | E14 | 2 |
| +0x4C / +0x50 | Q20.12 | grid step x / z | E14 | 2 |
| +0x54 | u32 | offset of an `nx·nz` table of 8-byte entries; table end aligns with the next known region in 404/428 groups | E15 | 2 |
| +0x58 | u32 | mostly 0 | — | 1 |
| +0x5C–0x64 | 3 × Q20.12 | unknown | — | 1 |
| +0x68–0x70 | 3 × u32 | unknown | — | 1 |
| +0x74 | (count, offset) | table, stride **unknown** | E16 | 1 |
| +0x7C | (count, offset) | table, stride 0x20 (183/183) | E16 | 2 |
| +0x84 | (count, offset) | table, stride 0x34 (181/181) | E16 | 2 |
| +0x8C | (count, offset) | table, stride 0x34 (183/183) | E16 | 2 |
| +0x94 | (count, offset) | slice of pool A | E10 | 2 |
| +0x9C | (count, offset) | slice of pool B (offset 0 when empty) | E10 | 2 |
| +0xA4 | (count, offset) | slice of pool C | E10 | 2 |
| +0xAC–0xCB | — | zero in 183/183 | E04 | 2 |

Group 0 is named `START…` in 86/183 files and after the stage or model otherwise (`smb1_be02a1`,
`GOAL`, `NOCOLI_st04a1`, …). Further groups are `MOT_…` in 235 of 245 cases, which suggests animated
parts; the other 10 are `REACT_…` (9) and `tes1` (1). Objects referenced by a group appear to be positioned in that group's frame
(inference from `smb2_ad26`, E13).

**Collision:** the +0x74…+0x8C tables, the +0x54 cell table and the cell lists it points to are
the leading collision candidates. Their record boundaries are partly known; **their contents are
not decoded**. Across the corpus trcore claims 39.6 % of bytes with views, 9.5 % is zero-fill and
50.9 % is opaque (mostly these regions).

## 6. Layout variants

| Variant | Rule (not a filename) | Files |
|---|---|---|
| `common` | valid start pair at 0x38/0x3C | 182 |
| `no_start_slot` | start pair invalid **and** u32 at 0x3C/0x40/0x44 equal the A/B/C slice sums | `smbds_001` |

`smbds_001` also has `u32_08 == 1` (unique), an all-zero 0xE4–0xFF area, an odd value
0x18089 at 0x38, group 0 named `GOAL`, and an all-zero `box2`. Most likely an unused or older-format
stage (E20, Level 1).

## 7. Revised or rejected historical hypotheses

| Historical claim | Status now |
|---|---|
| Goal table at 0x100 with 0x40-byte records | **Rejected** — stride 0x34; 0x40 was alignment padding |
| `F` is a footer / secondary metadata block | **Revised** — F is the base of an N × 0xCC descriptor array |
| `F+0x90` = end of object records | **Revised** — it is the offset of descriptor 0's +0x8C table, which happens to follow the pools |
| `smb1_ex03` header/footer count conflict | **Resolved** — its objects belong to group 1 (`MOT_smb1_ex03b`); group 0's slices are empty |
| `smbds_001` has 0x3C == 1 | **Confirmed**, explained as variant `no_start_slot` |
| Identity matrix + (0, 0, −46) at 0x100 in `smb1_ad02` | **Confirmed** (pool A record 0) |
| Q20.12 numeric encoding | **Supported** for matrices, positions and bounds; not for 0x0C/0x10/0x14 |
| IEEE-754 float candidates (old analyzer) | **Rejected** — on decoded data they are zeros and small integers misread as floats |

## 8. Open questions and the experiment that settles each

All in-game work should use a **copy** of the ROM and record: ROM SHA-1, emulator + version,
which files were swapped, and what was seen (screenshot if possible).

* **Q1 — Pool A word +0x30 = red goal?** No edits: play `smb1_ad25`, `smb2_ad26`, `smb2_ex29`
  (prediction: one red goal each) and `smb1_ad16` (prediction: two non-red goals).
  Then, once re-injection works (Q5): flip `smb1_be02` record 1's word from 1 to 0 (offset 0x164)
  and predict a normal goal at the same place.
* **Q2 — Are unreferenced records used?** No edits: count bananas in `smb1_ex19`
  (13 unreferenced), `smb2_ex30` (48) and bumpers in `smb1_ad21` (20). Visible ⇒ the game reads
  header pools; absent ⇒ only group slices matter.
* **Q3 — Pool C word +0x0C = banana bunch?** No edits: in a stage with both values (e.g.
  `smb1_ad02`) compare singles/bunches with the file (`py -3 -m trcore inspect`).
* **Q4 — Is `smbds_001` reachable in the game?**
* **Q5 — Will the game accept a different valid LZ10 encoding of an unchanged file?** Required
  before any byte edit can be tested. Needs an LZ10 encoder (not yet written).
* **Q6 — Collision tables:** decode `smb1_be01` (one group, simple geometry) against its model.
* **Q7 — Meaning of 0x0C, 0x10, 0x14, `box2`, descriptor +0x58…+0x70.**
