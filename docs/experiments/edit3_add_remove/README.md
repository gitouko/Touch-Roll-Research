# Edit test 3 — adding, removing and relisting objects

**Status:** generated 2026-11-07, waiting for the in-game test.

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

_Pending._
