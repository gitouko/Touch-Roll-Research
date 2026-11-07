# Edit test 4 — removing and adding collision, adding model polygons

**Status: built and checked statically (2026-11-07); waiting for the in-game test.**

* ROM copy: `TR_edit4_collision.nds`, SHA-1 `20e046a5f3bd983afd38ba9c7be7bfe24bde89f4`, built from the
  original (SHA-1 `3b0bf7f4…`) by `py -3 -m trcore stage-edit <original> TR_edit4_collision.nds plan.json`
  (plan schema `trcore.edit_plan/3`). The build is reproducible: the same command gives the same SHA-1.
* Only `stcoli/smb1_be01_stc.lz`, `stcoli/smbds_023_stc.lz` and `model/stage/smbds_023_nsbmd.lz` differ.
  All three grew and were moved behind the ROM's last file, as before. Header, code and every other file
  are byte-identical (verified).
* Static checks: `verification.json` and `py -3 -m unittest tests.test_geometry_edit` (with `TRCORE_ROM`
  set). The verification "probes" ask, the way the game looks things up (only through the cell under the
  ball), what a ball at a given spot would touch, in the original and in the edited stage. Both stages re-parse without
  errors; every list is sorted and in range; every object and every piece of collision is listed in at
  least one cell; the box's collision faces equal its new model polygons exactly; the 1-1 model is
  unchanged.

## What changed

| # | Stage | Change | Prediction |
|---|---|---|---|
| H | 1-1 Elementary | **collision removed** in a 2-unit strip (x −1…1) across most of the width (z −5…1: floor, wall and rail on that side); the floor is still drawn. A 3-unit **lane** on the +z side (z 1…4, the side of the banana beside the goal at z +3.25) stays solid | rolling slowly straight ahead from the start, just after banana 1 the ball **falls through the visible floor**; along the lane it rolls on normally |
| I | 1-1 | **collision removed** from the middle 4 units of the far guard rail behind the goal (z −2…2), the rail is still drawn; **invisible floor added**: 4 × 4 beyond the far edge (x 10.2…14.2, z −2…2) at the height of the edge's lip | going round the goal to the far end, the ball **passes through the rail** there and **rolls on nothing visible** for 4 units; it can roll back, and falls when it leaves the square |
| J | 1-2 Sine Wave | **model only**: a 2 × 2 panel with the floor's grid texture, 2 units above the start straight (x −1…1, z 34…36), drawn from above and below, no collision | a **floating square** just ahead of the start; the ball rolls under it untouched |
| K | 1-2 | **model and collision**: a box 1.5 wide × 2 deep × 1 high on one half of the straight (x −2…−0.5, z 30…32), floor-textured | a **box** about 6–8 units ahead of the start, on the **left** half seen from the start (if our reading of the camera is right; either side is fine for the test). It is **solid**: the ball bounces off it and cannot climb it (1 unit high), and the other half of the straight stays free |
| L | both | memory dumps | the game holds exactly the new stage files; the 1-2 model in memory has the new polygons (only material fields differ, as in every earlier dump) |

H and I test collision alone, J tests the model writer alone, K tests both together.

Maps of the edited collision: `edit4_smb1_be01_map.png` (strip, lane, rail gap, invisible floor and the
grown collision grid) and `edit4_smbds_023_map.png` (the box and the panel on the start straight).

### Two things found while building it (now in spec §17.3)

* **Collision only exists inside the stage's collision grid.** The game's cell lookup (0x02044CD4)
  returns *no cell* for a ball outside the grid, so nothing there can be touched. 1-1's grid ended
  about half a unit past its rails, so the invisible floor needed the grid grown by 5 columns. Only the
  loader and the lookup read the grid's size and origin, so growing it (a new, larger cell table; old
  cells keep their lists) is safe as far as the code shows. I tests this.
* **1-1 is fenced all round** by a guard rail (y 0.5–0.8) that the ball cannot pass under. The planned
  "roll off the far edge onto air" therefore also needs a gap in the rail's collision; the rail stays
  visible there.

## How to test

1. Put `TR_edit4_collision.nds` with the other test ROMs. World 1 needs no save.
2. Optional but useful: run `trcore_dump_stage.lua` (Tools > Lua Console) so each stage is dumped when it
   loads (test L).
3. **1-1, H:** roll **slowly** straight ahead from the start. Just past banana 1, about halfway to
   banana 2, the ball should drop through the floor. (A fast ball might jump the 2-unit gap.)
4. **1-1, lane and I:** restart. Cross the strip along the **lane** (the +z side, where the banana beside
   the goal is at z +3.25; probably your right): the floor holds there. Then go **round the goal** (do not
   roll into it) to the far end behind it, and roll through the **middle** of the far rail. Past the edge,
   try rolling on the invisible square and back; then roll off its far end or side.
5. **1-2, J and K:** look ahead from the start: floating panel (J) close ahead, box (K) further on one
   side. Roll under J, then into K's side and against its front; then roll past it on the free half.
6. If a stage freezes, crashes or looks broken, note which one and what you were doing — that is a result
   too.


## Results

*(to be filled in from the owner's report)*
