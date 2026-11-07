# LCTS (`.stc`) stage format — living specification

**Status:** research draft. Fields confirmed by controlled in-game edits (Level 4) are listed in §14;
everything else is Level 2 or below.
Two meanings are supported by in-game observations reported by the project owner (§9), and several
structural facts are now backed by the game's own code (§10, "code" in the evidence column).
**Corpus:** all 187 decompressed `.stc` files (183 unique contents) in `data/raw` at commit
`4ddcea8c22373730d263639433bdc59448b06060`. Each LZ10 copy in `data/decompressed` and `data/grouped`
decodes to exactly the matching `data/raw` file (SHA-256), so the three layers hold one corpus.
**ROM provenance (2026-11-06):** every one of the 596 files in `data/raw` is byte-identical (decoded
payload SHA-256) to a file of the same stage name and type in *Super Monkey Ball: Touch & Roll (USA)*,
game code `AMOE`, SHA-1 `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17` (§10). The ROM holds 235 stage
files; trcore parses all 231 unique ones without errors.
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
| 0x14 | u32 | `group_count` (N) | number of group descriptors. **Code:** the loader at ARM9 0x02041D40 loops this many times, stepping 0xCC from the address in 0x18 | E04 | 2 + code |
| 0x18 | u32 | `descriptor_base` (F) | offset of the group-descriptor array (§5); 32-byte aligned in 183/183 | E04 | 2 |
| 0x1C–0x30 | 6 × Q20.12 | `bounds_min_xyz`, `bounds_max_xyz` | min ≤ max on every axis in 183/183; "bounds" is an inference | E03 | 2 |
| 0x34 | u32 | `u32_34` | ≤ `group_count` in 183/183 (equal in 158); meaning unknown. An earlier draft wrongly treated it as the group count | E21 | 1 |
| 0x38 | u32 | `start_count` | 1 in 182/183 main-game files; 4 in 12 four-player party stages | E05 | 2 |
| 0x3C | u32 | `start_offset` | 0xE4 in 180; in `smb1_ad30` and `smbds_029` it equals `align32(F + N·0xCC)`, i.e. the start record sits right after the descriptor array | E05 | 2 |
| 0x40 | u32 | `pool_a_total` | total records in pool A ("goal" candidate) | E06 | 2 |
| 0x44 | u32 | `pool_b_total` | total records in pool B ("bumper" candidate) | E06 | 2 |
| 0x48 | u32 | `pool_c_total` | total records in pool C ("banana" candidate) | E06 | 2 |
| 0x4C–0x60 | 6 × Q20.12 | `box2_*` | (0,0,0,1,1,1) in 175 files; other values exactly in the 7 files where `u32_08 == 2` | E17 | 2 |
| 0x64–0xE3 | — | reserved | all zero in 183/183 | E18 | 2 |

The historical note that "0x58–0x60 contain 0x1000" is the default half of the `box2` block.

## 3. Start record (0x10 bytes, at `start_offset`)

| +Offset | Type | Observation | Level |
|---|---|---|---|
| +0x00 | 3 × Q20.12 | position-like xyz | 2 (structure) |
| +0x0C | u32 | 0 ×138, 0xC000 ×18, 0x3FFF ×14, 0x1FFF ×6, 0x7FFE, 0xE16C, … — 16-bit binary angle candidate (0x4000 = 90°) | 2 (structure) |

The record is **0x10** bytes, not 0x1C. In single-start files the record at 0xE4 is followed by 12 zero
bytes up to the 32-byte boundary at 0x100, which made it look like 0x1C. The 12 four-player party
stages in the ROM (`fight*`, …) pack four records at a 0x10 stride from 0x100 straight into the next
table, and padding after the last record is zero in 234/234 files. In `fight01` the four starts sit
at (±4, 0, ±4) with angle words 0xE000, 0x1FFF, 0x5FFF, 0xA000 — each 90° apart, each facing the
centre — which supports the yaw-angle reading.

## 4. Object pools

Each pool is one contiguous array. Its **total** is in the header (§2); each group descriptor
(§5) references a **slice** `(count, offset)` of it. Slices of successive groups are contiguous
and together cover the whole pool: every record belongs to exactly one group (183/183, no
overlaps). 2,454 records belong to group 0 (the static stage) and 470 to moving groups (E10).

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
  `smb1_ad25`, `smb1_be02`, `smb1_ex03`, `smb2_ad26`, `smb2_ex29` (E11). Per the project owner, the
  game has exactly two red goals; `ad25`, `ex29` and `ad26` are unused stages, so among stages that are
  played, the word is 1 only in `be02` and `ex03` — the two reported red-goal stages. The owner also
  reports that the goal itself looks/behaves the same (§9), so **whether this word is what makes a goal
  "red"** still needs the controlled edit in §8 Q1.
* **Pool C word +0x0C** is 0 in 2,173 records and 1 in 193 records across 58 files (E12).
  **Reported in-game: 1 = banana bunch worth 5 bananas** (§9).
* **Correction:** an earlier draft reported "unreferenced records" in 8 files. That was an artifact
  of reading the group count from 0x34 instead of 0x14: the missing records belong to the extra
  descriptors. Example: `smb1_ad21` (World 5-6 "Conveyor") has 21 groups — the static stage plus
  `MOT_bumper01`…`MOT_bumper20`, each owning one of its 20 bumpers.
* Pools usually start at 0x100 in A→B→C order. The pool after A starts at the next 32-byte
  boundary in 161 of the 162 files where it directly follows A (`smbds_059` packs C right after A); B→C is packed tight in 8 files and
  32-byte aligned in 4. In a few files a pool is placed elsewhere (e.g. `smb1_ad16` pool C after the
  descriptor array). The parser follows offsets and never assumes positions.

## 5. Group descriptors (0xCC bytes each, N = u32(0x14), base F = u32(0x18))

Previously called the "footer". It is an **array**: descriptor *k* is at `F + k·0xCC` (E04). The
game's loader walks it the same way (§10).
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
`GOAL`, `NOCOLI_st04a1`, …). Further groups are `MOT_…` in 387 of 403 cases, which suggests animated
parts; the rest are `REACT_…` (15) and `tes1` (1). Files have 1–25 groups (104 have one). Objects referenced by a group appear to be positioned in that group's frame
(inference from `smb2_ad26`, E13).

**Collision:** the +0x74…+0x8C tables, the +0x54 cell table and the cell lists it points to are
the leading collision candidates. Their record boundaries are partly known; **their contents are
not decoded**. Across the corpus trcore claims 40.8 % of bytes with views, 10.9 % is zero-fill and
48.4 % is opaque (mostly these regions).

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
| Start record 0x1C bytes at 0xE4 | **Rejected** — 0x10 bytes plus padding (four-start party stages) |
| Identity matrix + (0, 0, −46) at 0x100 in `smb1_ad02` | **Confirmed** (pool A record 0) |
| Q20.12 numeric encoding | **Supported** for matrices, positions and bounds; not for 0x0C/0x10 |
| Group count at 0x34 (this project's own first draft) | **Rejected** — the game loops over u32(0x14) descriptors |
| Unreferenced object records in 8 files (first draft) | **Rejected** — artifact of the wrong group count |
| IEEE-754 float candidates (old analyzer) | **Rejected** — on decoded data they are zeros and small integers misread as floats |

## 8. Open questions and the experiment that settles each

All in-game work should use a **copy** of the ROM and record: ROM SHA-1, emulator + version,
which files were swapped, and what was seen (screenshot if possible).

* **Q1 — Is pool A word +0x30 what makes a goal red?** The ad25/ad26/ex29 checks are impossible
  (unused stages). Decisive test, once re-injection works (Q5): in `smb1_be02` (World 8-1) change
  record 1's word from 1 to 0 (decoded offset 0x164) and check whether finishing through that goal
  still counts as a red goal; as a converse, set `smb1_be01`'s goal word to 1.
* **Q2 — closed.** There are no unreferenced records once the group count is read from 0x14.
  Open part: confirm that objects in a moving group move with it (hypothesis from E13).
* **Q3 — answered** (§9): word 1 = bunch. Open part: confirm with one controlled edit.
* **Q4 — Is `smbds_001` reachable in the game?**
* **Q5 — closed, PASSED (2026-11-06).** trcore's encoder reproduces the original compressed bytes
  exactly, and the in-game gate (a moved file in World 1-1, a different compression in World 1-2)
  produced in-memory stage data identical to the original ROM's and no visible difference
  (docs/research_notes/gate_2026-11-06/).
* **Edit test 1 — PASSED (2026-11-06):** banana position, bunch flag, start angle and goal
  position confirmed in-game (§14, docs/experiments/edit1_world1/).
* **Edit test 2 — PASSED (2026-11-06):** red-goal flag both ways, goal rotation (matrix convention),
  start position, bumper position, object inside a moving group (§14).
* **Q6 — Collision tables:** decode `smb1_be01` (one group, simple geometry) against its model.
  The model itself can now be read (§15), so the collision tables can be compared with real geometry.
* **Q7 — Meaning of 0x0C, 0x10, 0x34, `box2`, descriptor +0x58…+0x70.**

## 9. In-game observations reported by the project owner (2026-11-06)

These were observed in the unmodified game (BizHawk, USA ROM) by the project owner, not reproduced by
trcore. They raise the *meaning* of a field; they are not controlled byte edits.

| Observation | What it supports |
|---|---|
| `smb2_ex30` = World 12 "Mesh Mosh", stage 5 "Protuberance": all 48 banana records appear — exactly 36 singles + 12 bunches = 96 bananas, matching word +0x0C (36 × 0, 12 × 1) | E09, E12; consistent with every record being owned by a group (E10) |
| `smb1_ad21` = World 5 "Palarvar Lava", stage 6 "Conveyor": all 20 bumpers appear | consistent with E10 (each bumper is in a `MOT_bumperNN` group) |
| Banana flag: pool C word +0x0C = 1 is a banana **bunch worth 5 bananas** | E12 meaning |
| Exactly two red goals exist in the game; collecting both (after worlds 7–10) unlocks World 11 "Studio One". `smb1_be02` = World 8, stage 1 "Hollow Diamond" has one. | Context for E11 |
| Red and normal goals are the same object; the red goal differs only in colour and in counting towards Studio One | E11 remains the leading candidate for the per-goal difference |
| `smb1_ex03` = World 9 "Big Bang Boom", stage 2 "Converse" (the second red goal) | E11: the two played stages with word +0x30 = 1 are exactly the two red-goal stages |
| `smb1_ad02` = World 5 stage 2 "Sword". `smb1_ad25`, `smb2_ex29`, `smb2_ad26`, `smb1_ad16`, `smb1_ex19` are not in the game | Stage mapping |

## 10. ROM provenance and how the game names stage files

ROM: title `MONKEYBALLDS`, game code `AMOE`, maker `8P`, version 0, 64 MiB,
SHA-1 `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17`, CRC32 `ad0c8379`.

* NitroFS holds 2,661 files. Stage data is `stcoli/<stage>_stc.lz` (LZ10); stage models/textures/
  animations are `model/stage/<stage>_<type>.lz`. The repo's `data/decompressed` names are these
  original ROM names.
* All 595 compressed files in the repo are byte-identical to ROM files, and all 596 `data/raw`
  files match a ROM file of the same stage name and type after decoding.
* The ROM has **235** stage files; the repo has the 187 main-game ones. Not extracted: 48 party-game
  stages (`bowl01-02`, `fight01-03`, `golf01-25`, `race01/02/04/08/09/11`, `surv01-09`,
  `target01-03`). trcore parses all of them without errors.
* ARM9 (uncompressed; module parameter "compressed static end" = 0) contains a **250-entry** table
  of pointers to stage-name strings at RAM 0x020C4B4C (`smb1_be01` … `smbds_100`, then the party
  stages) and the format string `stcoli/%s_stc.lz` at 0x020C5370.
  * 32 names have no file (`smbds_057`, `smbds_070`–`smbds_100`).
  * 22 `smb*` stage files are not named in the table, so no stage ID can load them: `smb1_ad16`,
    `smb1_ex46/47/48/52/53/59/61/62/63/64/65/66/68/72`, `smb2_ad16/24/30`, `smb2_ex05/10/14/32`.

## 11. Stage loading in the game code (static analysis, USA ROM)

Addresses are RAM addresses for this ROM; they are recorded in `trcore/rom.py` (`PROFILES`).

| Address | What it is | How it was established |
|---|---|---|
| 0x02041774 | `name = stage_names[id]` | 3-instruction function reading the 0x020C4B4C table |
| 0x02041784 | set requested stage: stores the ID at 0x020E8FD8 | called from the main-game menu code |
| 0x02041BBC | stage loader: builds `stcoli/%s_stc.lz` from the requested ID, loads it, stores the data pointer at **0x020E9208**, loops u32(0x14) descriptors from u32(0x18) in 0xCC steps, then copies the ID to **0x020E8FC8** (loaded stage) | disassembly |
| 0x021FF284 (overlay 0) | `stage_id = worlds[w]->entries[s].id`, world table at **0x02200E70**: 12 pointers to world structs; struct +4 → entries, +8 = 10; entry = `{u32 stage_id, u32 flags}` | disassembly; all five owner-confirmed mappings match |
| 0x021FBF3C / 0x021FBF30 | current world / stage index (s8) in main-game mode | menu code before the call above |

* **Stage map:** the world table yields all 120 main-game stages, each a different file
  (docs/research_notes/stage_map.md, regenerate with `py -3 -m trcore stagemap <rom> --out …`).
  67 `smb*` stage files are used by no main-game slot, including every stage the owner listed as unused.
* **Bonus flag:** entry flag bit 0 is set on stage 5 of every world, and each of those 12 stage files
  has zero goal records (e.g. World 12-5 "Protuberance", 96 bananas). Overlay 0 at 0x021FF234 returns a
  special value 0xD for these stages (probably a theme/music selector). Level 2 + code; the in-game
  meaning "bonus stage" is not yet confirmed by an edit.

## 12. Compression and ROM writing

* trcore's LZ10 encoder (greedy longest match, nearest distance, distance 1 never used, window 4096)
  reproduces the **exact** compressed bytes of all 235 stage files and a 150-file sample of other
  types. The original compressor never uses distance 1 (10.3 M back-references in 2,626 compressed files checked).
* Files start on 0x200 boundaries with zero-filled gaps; the 0x88-byte download-play signature
  (`ac…`) sits at the used-ROM size; everything after it is zero.
* `trcore/romwrite.py` writes only new ROM copies, verifies that nothing but the target files (and,
  when a file moves, the used-ROM size and header CRC) changed, and records every write in a
  `.patch.json`. Re-inserting a recompressed unchanged `smb1_be01` yields a ROM with the same SHA-1 as
  the original.

## 13. Offsets confirmed in the running game (2026-11-06)

RAM dumps of World 1-1 and 1-2 from the unmodified ROM (BizHawk 2.11.1) show that, when a stage is
loaded, the game adds the load address to exactly these words and changes nothing else in the stage
data (docs/research_notes/gate_2026-11-06/README.md). They are therefore **file-relative offsets**
(Level 4 for "is an offset", observed in the emulator; their targets are as described in §§2–5):

* header 0x18 (`descriptor_base`) and 0x3C (`start_offset`);
* descriptor +0x04, +0x08 (names), +0x54 (cell table), +0x78/+0x80/+0x88/+0x90 (the offset halves
  of the +0x74…+0x8C pairs — confirming the `(count, offset)` reading), +0x98 (pool A slice),
  +0xA8 (pool C slice);
* the second word of every cell-table entry;
* hundreds to thousands of words inside the undecoded collision region (643 in `smb1_be01`), all
  pointing back into that region — a map for decoding collision later.

Header counts (0x14, 0x40–0x48), matrices, coordinates and flags are left unchanged at load time.

## 14. Confirmed by controlled in-game edits (Level 4)

Edit test 1 (2026-11-06, BizHawk 2.11.1, one single-field edit per stage, memory verified):

| Field | Meaning confirmed | Evidence |
|---|---|---|
| pool C record +0x00 (3 × Q20.12) | banana position | W1-1: z 0 → 2.0 moved the banana sideways |
| pool C record +0x0C (u32) | 1 = banana bunch worth 5, 0 = single banana | W1-2: flag 0 → 1 gave a bunch, counter +5 |
| start record +0x0C (u32, low 16 bits) | start facing angle, 0x10000 = 360°, increasing = turn left | W1-3: 0 → 0x4000 turned the start 90° left |
| pool A record +0x24 (3 × Q20.12) | goal position (model and trigger) | W1-4: y 0 → 2.0 made the goal float and unreachable |

**Coordinate system:** right-handed, **y up**, units as stored (Q20.12). A facing angle of 0 looks along
**−z**; with facing +x (0xC000), +z is to the right. Across the game the start faces the goal in 88 of
91 static-goal stages under this convention.

Edit test 2 (2026-11-06, same method):

| Field | Meaning confirmed | Evidence |
|---|---|---|
| pool A record +0x30 (u32) | 1 = red goal, 0 = normal goal (colour; unlock behaviour not tested) | W1-1 0 → 1 turned red; W8-1 1 → 0 no longer red |
| start record +0x00 (3 × Q20.12) | start position | W1-2: z 38 → 35 started 3 units further forward |
| pool A record +0x00 (3×3 Q20.12) | goal orientation; applied transposed (world = Mᵀ·local); goal front = local +z | W1-3: +90° turn, front faced right as predicted |
| pool B record +0x24 (3 × Q20.12) | bumper position | W5-2: x +2 moved the bumper right as predicted |
| pool slices in moving groups | objects are placed in their group's frame and move with it | W5-6: bumper raised 1 unit in group MOT_bumper01 rode higher and moved with the others |

**Matrix convention:** stored matrices are applied with row vectors (equivalently world = Mᵀ·local).
A rotation by angle a about +y (positive = turn left, as for the start angle) is stored as
`[[cos a, 0, -sin a], [0, 1, 0], [sin a, 0, cos a]]` (rows as stored).

Not yet confirmed in-game: bumper rotation (not visible on round bumpers), whether a converted red goal
counts towards Studio One, the meaning of descriptor fields other than the slices, and everything in
§5's tables (collision).

## 15. Stage models (`model/stage/<key>_nsbmd.lz`) and how they line up with the stage file

Used by the editor's 2D map. Reproduce every number below with
`py -3 -m trcore stage-models "<ROM>.nds" --out generated\trcore` (ROM required; nothing is written to it).

* **Same name as the stage file (Level 1, code):** ARM9 0x020C531C holds `model/stage/%s_nsbmd.lz`,
  next to `stcoli/%s_stc.lz` at 0x020C5370. 213 of the 235 stage files have a model. The 22 without
  one are 21 leftover files that have no entry in the game's stage-name table (never loaded) and
  `smbds_009`, which has a name but no world slot. Every stage used by the 12 worlds has a model.
* **Reader (Level 2):** `trcore/nitro/nsbmd.py` reads the NITRO model format: resource dictionaries,
  node transforms (including the compressed "pivot" rotations), the structure byte code that places
  shapes, and the GX display lists (all vertex command forms). In **all 213** models the decoded
  triangle count equals the model header's `triangles + 2 × quads`. There were no parse errors.
* **Model space = stage space (Level 2):** with no extra transform, objects sit on the model's surfaces:

  | Object | on a surface (gap < 0.02) | 0.02–2 above | more than 2 above | no surface below |
  |---|---|---|---|---|
  | start | 171 | 73 | 4 | 0 |
  | goal | 124 | 16 | 7 | 10 |
  | bumper | 139 | 27 | 0 | 0 |
  | banana | 2 | 1,909 | 183 | 149 |

  Bananas float about 0.25–0.6 above the floor by design. Starts and goals sit on it.
* **Moving parts (Level 2):** a group whose name matches a model node (for example `MOT_bumper01`)
  stores the **inverse** of that node's rest transform in 393 of 417 cases (applying the group
  transform, then the node, gives the identity). Together with the floor fit above, this means
  stored object positions are their positions at the stage's **rest pose**, in stage coordinates.
  W5-6 (edit test 2) confirmed in-game that such objects move with their part.
* **Not decoded:** materials and textures (names only), animations (`.nsbca`, `.nsbta`, …). The 2D map
  shows moving parts at their rest pose.
* **The game keeps the model file as loaded (Level 4, memory):** in the edit-test-3 dumps of 1-1 and 1-2
  the whole decoded model sits in Main RAM (at 0x0224D1E0 in both); only words in the **material block**
  differ (6 and 10 words: the texture binding). Display lists and everything else are byte-identical.
  `ramdump-compare` now reports this check for the stage's model.
* **Adding polygons (Level 2, edit test 4 pending):** `trcore/nitro/nsbmd_write.py` appends polygons to
  an existing shape. It copies that shape's display list to the end of the model with new GX commands
  after it (BEGIN_VTXS, NORMAL, TEXCOORD, VTX_16, END_VTXS), so the polygons use the shape's material and
  the stage's own `.nsbtx` texture; dictionaries and SBC are untouched. It updates the shape's display-list
  offset/size, the model size (and `ofsEvpMtx` when it pointed at the end), the MDL0 and file sizes, the
  model's counters and its bounding box. Texture coordinates continue the shape's own mapping (affine map
  of the nearest upward-facing polygon; shifted by whole 1024-texel periods). Stage materials draw **front
  faces only**, so a panel meant to be seen from below needs a second, reversed polygon.

## 16. How the game uses object pools and the collision cells (Milestone 3 research)

All addresses are ARM9 in the USA rev 0 ROM, read from the game code (Level 2: code plus corpus
agreement). Reproduce the corpus numbers with `py -3 -m trcore cells "<ROM>.nds" --main-only`.

### 16.1 Loading (0x02041BBC → 0x02046CC4)
The game decompresses the stage file into one buffer. It then turns these stored offsets into
pointers (**the complete list**):

* header `0x18` (descriptors) and `0x3C` (start records);
* per descriptor: `+0x04`, `+0x08` (names), `+0x54` (cell table), `+0x78`, `+0x80`, `+0x88`, `+0x90`
  (the four collision tables), `+0x98`, `+0xA0`, `+0xA8` (pool A/B/C slices), `+0xAC` (a tree walked
  recursively by 0x02046F04 / 0x02046F74);
* every cell entry's `+0x04` and every offset in the array it points to.

Zero offsets are left as zero. No other stored offsets exist. These are exactly the offset→pointer
words seen in every RAM dump.

### 16.2 Pools and header totals
* **Goals** (0x020ABF98): `total_A × 0x2C` bytes of runtime data, one goal model instance each.
* **Bumpers** (0x02042334): `total_B` state bytes (hit animation).
* **Bananas** (0x020ACB10): `total_C` state bytes (collected / animating). The stage's banana value
  (single = 1, bunch = 5, other values add nothing) is summed into a **byte**, so it cannot exceed 255.
  It is summed by walking `total_C` records of 0x10 bytes **from group 0's slice**.
* Per frame, each group's objects are reached through **that group's slice pointer** and local index.
  The runtime arrays are indexed by group order plus local index (the banana loop adds each group's
  `+0xA4` count).

So each pool must stay **one contiguous array in group order**, with header totals equal to the sum
of the slice counts. Where the array sits in the file does not matter.

### 16.3 Collision cells: the game only checks objects listed in the ball's cell
* Descriptor `+0x40` s16 nx, `+0x42` s16 nz, `+0x44`/`+0x48` origin x/z, `+0x4C`/`+0x50` cell size x/z
  (Q20.12), `+0x54` → nx·nz entries of 8 bytes: **u32 type mask**, **offset of an array** with one
  list offset per set bit, in bit order.
* A list is sorted u16 indices ending in `0xFFFF`. For bits 0–3, an offset of 0 means an empty list.
* Lookup 0x02044C68: bits 0–3 are always present (in every main-game cell). A higher bit exists only
  if it is set in the mask.
* Ball collision 0x020444F4: bits 1, 2 and 3 go to tables `+0x88` (0x34-byte records), `+0x80` (0x20)
  and `+0x78` (0x10). **Bit 4 → goals** (pool A slice), **bit 5 → bumpers** (pool B). Banana pickup
  0x020AC0F4: **bit 6 → bananas** (pool C). Bit 0 indexes table `+0x90` (index range = its count).
  Indices are **local to the group**.
* In the 120 main-game stages, every list is sorted, unique and in range. No bits above 6 are used.
  **Every goal, bumper and banana is listed in at least one cell of its group.** (Only leftover and
  party files have unlisted objects.)
* **Footprint rule:** an object is listed in the cells whose index range overlaps `[p − R, p + R]` in x
  and z. The index is `floor((value − origin) / size)`, clamped to the grid. Stored (rest-pose)
  coordinates are used in every group. R = 3.5 for bananas and bumpers. For goals, R is the
  axis-aligned extent of a 3.5-unit cube turned with the goal.
  * Exact for 1,911 of 1,981 main-game objects.
  * 68 more differ by one row or column of cells at the edge.
  * 2 goals on moving parts differ more.

**Confirmed in-game by edit test 3 (2026-11-07, Level 4):**
* a banana moved out of its cells without updating them cannot be collected, and the same move with its
  lists rebuilt can;
* pools rebuilt at the end of a grown stage file, with slices and totals updated, work for adding and
  removing bananas, goals and bumpers in group 0.

**Consequence for editing:** moving an object changes only its record, not its cell lists. A move
that leaves the cells listing it (roughly more than 2 units for bananas) leaves the object where
the ball never checks it. Editor 0.1.1 warns about such moves. Adding, removing or freely moving
objects needs the lists rebuilt (Milestone 3).

## 17. Collision geometry (Milestone 4 research)

From the game's ball-collision code (ARM9, USA rev 0), checked against all 120 main-game stages
(Level 2). Reproduce with `py -3 -m trcore collision "<ROM>.nds" --main-only`. Reader:
`trcore/stc/collision.py`.

### 17.1 The four tables (per group) and what the ball does with them

| Cell bit | Count / offset | Record | Kind | Game code |
|---|---|---|---|---|
| 0 | `+0x8C` / `+0x90` | 0x34 | **quad** (parallelogram) | 0x02046460 |
| 1 | `+0x84` / `+0x88` | 0x34 | **triangle** | 0x02046050 |
| 2 | `+0x7C` / `+0x80` | 0x20 | **edge** | 0x02045DE0 |
| 3 | `+0x74` / `+0x78` | 0x10 | **corner point** | 0x02045C1C |

* **Face record:** `+0x00` u32 (always 0), `+0x04` corner P, `+0x10` unit normal N, `+0x1C` E1, `+0x28` E2
  (all Q20.12). E1 and E2 are dual vectors: for a contact point Q, u = (Q−P)·E1 and v = (Q−P)·E2. The
  point is on a triangle if u ≥ 0, v ≥ 0 and u + v ≤ 1, and on a quad if 0 ≤ u, v ≤ 1. The ball must come
  from the front (the side N points to) and be within its radius of the plane.
  * The corners follow from P, N, E1, E2: P, P + A, P + B (and P + A + B for quads), where A·E1 = 1,
    A·E2 = 0, A·N = 0 and B likewise.
  * In every main-game face, N has the same sign as (P1 − P) × (P2 − P), and the stored vectors equal
    the recomputed ones to within 2/4096 (98%). `dual_vectors()` encodes new faces the same way.
* **Edge record:** `+0x00` start A, `+0x0C` unit direction D, `+0x18` length L, `+0x1C` u32 (always 0). The
  ball touches it between t = 0 and t = L along D.
* **Corner point record:** `+0x00` point, `+0x0C` u32 (always 0). It is the rounded collision at corners.
* Ball data used: position `+0x2C`, previous position `+0x38`, radius `+0x28`. The response routine is
  0x02046858 (contact point plus normal).
* Main-game totals: 29,981 quads, 63,766 triangles, 170,428 edges and 79,189 corner points. Descriptor
  `+0xAC` (the relocated tree) is 0 in every main-game group.

### 17.2 Where collision comes from: the visible model

* 96% of collision faces have every corner within 0.02 of a corner of the stage model at rest
  (28,654 / 29,981 quads, 61,932 / 63,766 triangles).
* Model quads that are parallelograms become collision quads (28,188 of 29,681). The others are split
  into two triangles. The diagonal does not follow a simple rule (probably the source mesh's own
  triangulation). Model triangles stay triangles.
* Edges: nearly every edge between two faces (convex, concave or flat) and most outer edges have an edge
  record. Corner points: 98% of corners where faces meet at an angle, and 65% of flat ones.
* Cell lists for bits 0–3 follow the object rule (§16.3) with the piece's own x/z extent plus **0.5**,
  the ball's radius:
  * exact for 28,346 quads, 61,655 triangles, 164,877 edges and 76,817 points (96–97%);
  * with extent + 0.75, every piece except one quad is within the computed cells.

**Consequence for collision editing and platforms:** collision can be generated from geometry with
these rules, and existing collision can be kept exactly for untouched geometry. A platform is model
polygons plus the collision generated from them, added to one group's tables and lists. The proposed
in-game test is in `docs/research_notes/m4_collision_platforms.md`.

### 17.3 Editing collision (Level 2; edit test 4 builds on it, in-game result pending)

Found while building edit test 4 (ARM9, USA rev 0):

* **Nothing outside the grid can be touched.** The position-to-cell lookup 0x02044CD4 computes
  `floor((x − origin) / size)` for x and z and returns **no cell** when either index is outside
  `0…nx−1` / `0…nz−1`. The grids end about 0.5 past the stage's collision, so new geometry beyond the
  stage needs a larger grid.
* **Only two routines read the grid's size and origin** (descriptor `+0x40…+0x50`): the loader 0x02046CC4
  (it walks `nx·nz` cell entries, using `smulbb`) and the lookup. Growing the grid by whole cells, with a
  new cell table and the old cells' entries kept, is therefore consistent with the code.
* For bits 0–3 the lookup reads the cell's array directly (`array[bit]`), so **every cell needs an array**.
  In all 470,676 main-game cells the array offset is non-zero and **no two cells share an array** (the loader
  relocates each cell's array entries once). Empty bit 0–3 lists are offset 0 inside the array.
* Empty collision tables keep a non-zero offset (193 of them in the main game).
* Header `0x1C–0x30` ("bounds") is read only by 0x02059BE8, which turns it into a centre and radius for a
  camera set-up (stored at +0x120… of the camera object). It is not a fall-out limit; edits leave it alone.
* Stage files may grow a lot: the largest original decoded stage is 894,672 bytes (`smb2_be04`), so the
  game's stage buffer is at least that large. Edit test 4 grows 1-1 from 85 KB to 170 KB.

How `trcore/stc/geometry_edit.py` edits a group (nothing that exists moves):

* `remove_box`: faces and edges crossing the box's x/z sides are cut there; the parts outside stay
  (re-encoded as quads or triangles), and the cut gets edges and corner points. Only pieces entirely
  within the optional y range are touched.
* `add_polygons`: convex planar polygons become quads (parallelograms) or triangle fans, plus an edge per
  side and a corner point per corner.
* Changed tables are rebuilt at the end of the file: kept records first, byte-for-byte and in order, then
  new ones. Kept records keep exactly their cells; new records get extent + 0.75. Cells get new lists and
  their own new arrays; if added geometry reaches outside the grid, the grid grows by whole cells (old cells
  keep their entries; new cells also list existing pieces and objects by the same rules).
* Corners stored through E1/E2 come back within about 1/4096 per unit of face size (as in the originals).

