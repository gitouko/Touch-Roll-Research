# Editor 0.2 acceptance test (2026-11-07)

The project owner made every edit with editor 0.2 and played `test 0.2.nds` (SHA-1 `bb954f4d…`) in
BizHawk 2.11.1. **Result: PASSED.**

Only the four edited stage files differ from the original ROM; nothing else changed (verified).

| Stage | Edits (from `played_rom_patch_record.json`) | Owner's observation | Memory (`results/`) |
|---|---|---|---|
| 1-1 Elementary | banana 1 deleted; banana 3 moved from (8.45, 0.5, 0) to (−5, 0.5, 0) **with lists rebuilt**; bunch added at (−2.25, 0.5, 2.25) | all working | 0 other words |
| 1-2 Sine Wave | **red goal added** at (0, 0, 31.25), front towards the start | works | 0 other words |
| 5-2 Sword | bumpers 4 and 6 (diamond's sides) deleted; two bumpers added at z 26; banana 4 duplicated | all working | 0 other words |
| 5-6 Conveyor | bumper 15 deleted; it was the only bumper of moving part `MOT_bumper015` | stage works (the bumper itself was out of view) | 0 other words; **in memory the bumper total is 19 and MOT_bumper015 has 0 bumpers**, so the deletion is in effect |

Conclusions (Level 4):
* A red goal added from scratch works.
* Deleting an object that belongs to a moving part works: the game loads and runs the stage with that part
  emptied.
* Editor-made adds, deletes, duplicates and far moves behave like the trcore operations confirmed by edit
  test 3.

Issue found: Delete and Duplicate stayed disabled after their first use, until another edit refreshed them.
Fixed in 0.2.1.
