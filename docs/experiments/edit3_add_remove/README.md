# Edit test 3 — adding, removing and relisting objects

**Status: PASSED (2026-11-07).** All seven predictions were observed in-game, including the control (C), and the game's memory held exactly the edited stage files.

* ROM copy: `TR_edit3_add_remove.nds`, SHA-1 `ebddb91593acc12c39cab9e040bd64d0372629ff`, built from the
  original (SHA-1 `3b0bf7f4…`) by `py -3 -m trcore stage-edit <original> TR_edit3_add_remove.nds plan.json`.
* Only `stcoli/smb1_be01_stc.lz`, `stcoli/smbds_023_stc.lz` and `stcoli/smb1_ad02_stc.lz` differ. The
  three files grew and were moved behind the ROM's last file, as in the gate test. Header, code and
  every other file are byte-identical (verified).
* Each edited stage re-parses without errors. Every collision list is sorted and in range. Every
  object is listed in at least one cell, and every object's neighbourhood is covered, **except banana
  1 in 1-2, deliberately** (test C).

| # | Stage | Change | Prediction |
|---|---|---|---|
| A | 1-1 Elementary | removed banana 5 (6, 0.5, 3.25), beside the goal | it is gone; the other four can still be collected |
| B | 1-1 | added a single banana at (−5.0, 0.5, −2.0) | between the start and banana 1, 2 units to the side; it can be collected |
| G | 1-1 | added a second normal goal at (−3.5, 0, 0), turned like the original goal | 4.5 units ahead of the start, front towards the ball; rolling straight into it clears the stage |
| C | 1-2 Sine Wave | **control:** banana 1 moved to (0, 0.5, 33.0) as a plain field edit, cell lists **not** updated | drawn 5 units straight ahead of the start, but the ball rolls through it without collecting it |
| D | 1-2 | banana 12 moved from near the goal to (0, 0.5, 30.5), lists updated | just past C; rolling straight collects D (counter +1) but not C |
| E | 5-2 Sword | added a bumper at (0, 0, −20) | on the blade, 5 units in front of the diamond; it bounces the ball |
| F | 5-2 | removed bumper 9 (0, 0, −35) | the diamond's back tip is gone; the ball passes freely |

Maps of the three stages as the editor reads them from this ROM: `edit3_smb1_be01_map.png` (new goal
selected), `edit3_smbds_023_map.png` (banana D selected, C just below it), `edit3_smb1_ad02_map.png`
(new bumper selected).

## How to test

1. Put `TR_edit3_add_remove.nds` next to the other test ROMs. For World 5, copy your completed save to
   `BizHawk ~ TEST EMU\NDS\SaveRAM\TR edit3 add remove.SaveRAM`.
2. Optional but useful: run `tools/bizhawk/trcore_dump_stage.lua` so each stage is dumped when it loads.
3. **1-1:** check A and B, then roll straight from the start into the new goal (G).
4. **1-2:** roll straight ahead from the start, through C and then D. Watch the banana counter.
5. **5-2:** check E (bounce off the new bumper) and F (back tip missing).
6. If a stage freezes, crashes or looks broken, note which one. That is a result too.

## Results

Played by the project owner in BizHawk 2.11.1 on `TR_edit3_add_remove.nds` (SHA-1 `ebddb915…`).

| # | Owner's observation |
|---|---|
| A | banana 5 beside the goal is gone; the other four can still be collected |
| B | the new banana between the start and banana 1 can be collected |
| G | the second goal 4.5 units ahead of the start clears the stage when rolled into |
| C | the ball rolls through the banana 5 units ahead of the start without collecting it |
| D | the banana just past C is collected (counter +1 for the pair) |
| E | the new bumper in front of the diamond bounces the ball |
| F | the diamond's back tip bumper is gone |

Memory (`results/`): every word of the in-memory stage equals the edited file, apart from the offsets
the game turns into pointers. Those now include the newly appended cell arrays and lists, so the game
walked the new data.

| Dump | Stage | Size | Result |
|---|---|---|---|
| stage 0, frame 4407 | smb1_be01 (W1-1) | 88,688 bytes (was 85,296) | 21,213 equal, 959 offset→pointer (was 843), **0 other** |
| stage 119, frame 7915 | smbds_023 (W1-2) | 187,832 (was 184,992) | 40,875 equal, 6,083 offset→pointer, **0 other** |
| stage 11, frame 10243 | smb1_ad02 (W5-2) | 265,472 (was 261,712) | 61,227 equal, 5,141 offset→pointer, **0 other** |

### Conclusions (Level 4)

* Pools may be rebuilt **at the end of the stage file**: with slices and header totals updated, the game
  uses the new array. The old bytes are simply ignored. Stage files may grow (≥ 3.7 KB tested).
* Adding a banana, a goal and a bumper, and removing a banana and a bumper, all work in group 0.
* **The collision cell lists decide what the ball can touch.** A banana moved out of its cells without
  updating them (C) cannot be collected. One moved the same way with its lists rebuilt (D) can.
* A second normal goal works as a goal.
* Not tested yet: objects in moving parts (add, remove, far moves) and red goals added from scratch.
