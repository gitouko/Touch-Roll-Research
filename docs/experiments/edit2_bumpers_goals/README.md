# Edit test 2 — goal flag, goal rotation, start position, bumpers, moving groups

**Status:** generated, waiting for the in-game test.

* Plan: `plan.json`; patch record: `patch_record.json` — input ROM SHA-1
  `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17`, output `TR_edit2_W1_W5_W8.nds` SHA-1
  `7ed08b0fffa0b9740c00a440167aa48f04aacc52`. Each stage differs from the original only inside the
  edited field; all six files stay in place in the ROM.
* World 5 and 8 stages need a save with those worlds unlocked (the project's BizHawk save is empty).

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

_Pending._
