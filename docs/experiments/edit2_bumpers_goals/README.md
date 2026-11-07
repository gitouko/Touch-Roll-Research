# Edit test 2 — goal flag, goal rotation, start position, bumpers, moving groups

**Status: PASSED (2026-11-06).** All six predictions were observed in-game, including both left/right
predictions, and the game's memory held exactly the edited values.

* Plan: `plan.json`; patch record: `patch_record.json` — input ROM SHA-1
  `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17`, output `TR_edit2_W1_W5_W8.nds` SHA-1
  `7ed08b0fffa0b9740c00a440167aa48f04aacc52`. Each stage differs from the original only inside the
  edited field; all six files stay in place in the ROM.
* World 5 and 8 stages were played with a completed save the owner downloaded and installed as this
  test ROM's BizHawk save (not inspected by trcore; it only affects which worlds are unlocked).

| Stage | Field | Old → new | Prediction | Tests |
|---|---|---|---|---|
| W1-1 Elementary | goal word +0x30 | 0 → 1 | the goal is red | E11: word +0x30 = red goal |
| W1-2 Sine Wave | start position | z 38 → 35 | ball starts 3 units further forward | start record +0x00 = position |
| W1-3 Curvature | goal matrix | identity → stored `[0,0,-1, 0,1,0, 1,0,0]` | goal sideways, front facing **right** while approaching | matrix convention: world = Mᵀ·local, goal front = local +z, rotation +90° = left turn of the object |
| W5-2 Sword | bumper 0 position | x 0 → 2 | front bumper of the diamond shifted **right** | pool B = bumpers, +0x24 = position |
| W5-6 Conveyor | bumper 0 position (group MOT_bumper01) | y −0.1 → 0.9 | one moving bumper rides 1 unit higher, still moving with the others | objects are placed relative to their (moving) group |
| W8-1 Hollow Diamond | goal 1 word +0x30 | 1 → 0 | the secret goal is not red | E11 (converse) |

Why "right" in W1-3 and W5-2: with the convention confirmed in edit test 1 (y up, start angle 0 faces
−z), a player facing −z has +x on the right. Turning the goal's front (+z) by +90° gives +x; moving the
bumper by +2 in x moves it right. The matrix convention is the one that makes 82 of 92 static goals face
their stage's start (the next best scores 64). If the goal's front faces LEFT instead, the convention is
the other one.

## Results

Played by the project owner in BizHawk 2.11.1 on `TR_edit2_W1_W5_W8.nds` (SHA-1 `7ed08b0f…`).

| Stage | Owner's observation | Memory check (`results/`) |
|---|---|---|
| W1-1 Elementary | goal is **red** | in-memory stage = edited file; vs original memory only 0x130 differs |
| W1-2 Sine Wave | ball starts **3 units further forward** | = edited file; vs original only 0xEC differs |
| W1-3 Curvature | goal sideways, front facing **right** (as predicted) | = edited file |
| W5-2 Sword | front bumper shifted **right** (as predicted) | = edited file |
| W5-6 Conveyor | one moving bumper ~1 unit higher, still moving with the others | = edited file |
| W8-1 Hollow Diamond | secret goal **no longer red** | = edited file |

"= edited file" means 0 unexplained differences: every word equals the edited stage file except offsets
the game converts to pointers at load time.

### Conclusions (Level 4)

* Pool A +0x30: **1 = red goal, 0 = normal goal** — shown in both directions (W1-1 0→1 red, W8-1 1→0
  not red). Only the colour was checked; whether a converted goal counts towards unlocking Studio One
  was not tested.
* Start record +0x00 = start position.
* Matrices: the stored 3×3 is applied **transposed** (world = Mᵀ · local, i.e. row-vector convention);
  a goal's front is its local **+z**; with the confirmed axes (y up, angle 0 faces −z) the predicted
  "front faces right" was observed.
* Pool B = bumpers, +0x24 = position (predicted "right" observed).
* Objects in a moving group are placed in that group's frame and move with it (W5-6).
* Bumper rotation was not tested (bumpers look round, so a turn would not be visible).
