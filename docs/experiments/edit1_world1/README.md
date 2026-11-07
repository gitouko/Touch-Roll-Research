# Edit test 1 — World 1, stages 1–4 (first controlled byte edits)

**Status: PASSED (2026-11-06).** All four predictions were observed in-game and the game's memory held
exactly the edited values. Results at the end.

* Plan: `plan.json` (built with `py -3 -m trcore stage-edit <original ROM> TR_edit1_World1.nds plan.json`)
* Patch record: `patch_record.json` — input ROM SHA-1 `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17`,
  output ROM SHA-1 `5c20111da8c0734b3ade1bfedb9ecc3e92e9ad0e`.
* Each stage changes exactly one field, and in each decoded stage file exactly **one byte** differs
  from the original. All four files stay in place in the ROM (compressed sizes +1 to +7 bytes).

| Stage | Field (decoded offset) | Old → new | Prediction | Hypothesis tested |
|---|---|---|---|---|
| W1-1 Elementary (`smb1_be01`) | pool C record 1 position z (0x158) | 0.0 → 2.0 | the 2nd banana on the path sits 2 units off the straight line, toward one of the two bananas beside the goal | pool C = bananas; xyz = position; Q20.12 units |
| W1-2 Sine Wave (`smbds_023`) | pool C record 0 word +0x0C (0x14C) | 0 → 1 | the first banana ahead of the start is a bunch worth 5 | word +0x0C = bunch flag (owner-reported meaning) |
| W1-3 Curvature (`smb1_be06`) | start record 0 word +0x0C (0xF0) | 0x0000 → 0x4000 | ball/camera start facing 90° to one side; same position | start word = yaw, 16-bit binary angle |
| W1-4 Progenitor (`smbds_015`) | pool A record 0 translation y (0x128) | 0.0 → 2.0 | the goal floats about 2 units above its platform | pool A = goals; +0x24 = position; y is up |

## How results are judged

1. **What the tester sees**, per stage, against the prediction (including the left/right direction
   for W1-1 and W1-3, which tells us the axis and angle conventions).
2. **Memory check:** `trcore_dump_stage.lua` dumps each stage; `ramdump-compare <dump> --rom
   TR_edit1_World1.nds` must show the in-memory stage equal to the *edited* file (0 "other"
   differences), which proves the game loaded the edited bytes. For W1-1 and W1-2, a comparison
   against the gate-test dumps of the original must differ only in the edited word.

A field is promoted to **Level 4** for the tested meaning only when both hold and nothing unexpected
happens elsewhere in the stage.

## Results

Played by the project owner in BizHawk 2.11.1 on `TR_edit1_World1.nds` (SHA-1 `5c20111d…`). Memory
dumps compared by Claude (`results/`; the RAM dumps themselves are not committed).

| Stage | Owner's observation | Memory check |
|---|---|---|
| W1-1 Elementary | the 2nd banana moved to the **right** (seen from the start) | in-memory stage = edited file (0 unexplained differences); vs the original ROM's memory exactly **1 word** differs, at 0x158 |
| W1-2 Sine Wave | the 1st banana is a **bunch**, behaves like one, counter **+5** | = edited file; vs original exactly **1 word** differs, at 0x14C |
| W1-3 Curvature | start faces **90° to the left**, same position | = edited file (0 unexplained differences) |
| W1-4 Progenitor | goal **floats** in the air; stage could not be finished | = edited file (0 unexplained differences) |

No other differences, crashes or physics changes were seen.

### Conclusions

* Confirmed in-game (Level 4): pool C = bananas, +0x00 = position (Q20.12); pool C +0x0C = bunch
  flag (1 = bunch worth 5); start record +0x0C = facing angle; pool A = goals, +0x24 = position.
* Coordinate convention, consistent with both observations: **right-handed, y up**; at yaw angle 0 the
  start faces **−z**; increasing the angle turns **left** (counter-clockwise seen from above);
  0x10000 = 360°, so 0x4000 = 90°. In World 1-1 the start faces +x (0xC000) and +z is on the right,
  as this convention predicts. Across the game, the start points toward the goal in 88 of 91 stages
  whose goal is static (median alignment ≈ 1.0).
* The goal's trigger moves with the model: with the goal raised by 2.0 the stage cannot be finished.
