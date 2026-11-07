# Milestone 3 — adding and removing objects: findings and plan

Status: research done (spec §16, Level 2 from game code plus corpus). Implemented in
`trcore/stc/objects.py` (plan schema `trcore.edit_plan/2`). **Edit test 3 PASSED on 2026-11-07** (`docs/experiments/edit3_add_remove/`).

Robustness check: relisting every goal, bumper and banana in place, in all 120 main-game stages at
once, passes every check below.

## What has to change when an object is added, removed or moved far

| Piece | Why | Evidence |
|---|---|---|
| The pool array (A goals 0x34, B bumpers 0x30, C bananas 0x10 bytes per record) | the object's own record | E07–E09 |
| The group's slice (count, offset) at descriptor +0x94/+0x9C/+0xA4, and the slices of every later group | the game reaches objects through each group's slice | E10, E22 |
| Header pool total 0x40/0x44/0x48 | sizes the runtime arrays (goal models, bumper and banana state) | E24 |
| Pool order | banana value is summed by walking `total` records from group 0's slice, so the pool must stay contiguous in group order | E24 |
| The group's collision cell lists for that type (bit 4 goals, bit 5 bumpers, bit 6 bananas) | the ball only tests objects listed in the cell it is in | E23 |

Nothing else refers to objects. The loader's relocation list is complete (E22), and no table holds
pointers into the pools apart from the slices.

## How trcore will do it (no shifting of existing data)

1. Rebuild the changed pool as one contiguous array in group order, append it at the end of the
   decoded stage file (4-byte aligned), and point every group's slice at its run in the new array.
   Then update the header total. The old pool bytes stay in place, unreferenced.
2. Rebuild the changed group's lists for that type:
   * unchanged objects keep exactly the cells they had;
   * added or moved objects get the cells of the footprint rule (spec §16.3) plus one cell of margin;
   * a removed object drops out, and higher indices in that group shift down by one.

   New lists and per-cell arrays are appended at the end. Each changed cell's mask and array offset
   is updated in place (8 bytes per cell; the table itself never moves). Shared lists are never
   modified in place.
3. Check before writing:
   * the stage re-parses without errors;
   * pools are contiguous and totals equal the slice sums;
   * every list is sorted, unique and in range;
   * every object is listed in at least one cell, and its footprint is covered;
   * every relocated offset points inside the file;
   * the banana value is at most 255;
   * bytes outside the rebuilt areas, the header totals, the slices and the changed cell entries are
     unchanged.
4. The ROM copy is written by the existing verified writer. The stage file grows, so it is usually
   relocated in the ROM, as in the gate test.

Starts are not part of the cell lists. Adding starts is only useful for party modes and is out of scope.

## Edit test 3 — one ROM copy, three stages, original ROM as the base

| # | Stage | Edit | Prediction |
|---|---|---|---|
| A | 1-1 Elementary | remove banana 5 (6, 0.5, 3.25), beside the goal | it is gone; the other four can still be collected |
| B | 1-1 | add a single banana at (−5.0, 0.5, −2.0), lists updated | it appears between the start and banana 1 and can be collected |
| G | 1-1 | add a second normal goal at (−3.5, 0, 0), turned like the original (front towards the start) | rolling straight from the start into it clears the stage |
| C | 1-2 Sine Wave | **control:** move banana 1 to (0, 0.5, 33.0), straight ahead of the start, **without** updating its lists (what editor 0.1 does) | it is drawn there, but the ball rolls through it without collecting it |
| D | 1-2 | move banana 12 (near the goal) to (0, 0.5, 30.5), just after C, **with** its lists updated | rolling straight ahead collects D but not C (counter +1) |
| E | 5-2 Sword | add a bumper at (0, 0, −20.0), in front of the diamond | a new bumper is there and bounces the ball |
| F | 5-2 | remove bumper 9 (0, 0, −35), the back tip of the diamond | it is gone; the ball passes freely |

C and D side by side test the collision-list theory directly. A crash or freeze when a stage loads would
also be a result: please note the stage.

As before, a memory dump of each of the three stages (Lua script) lets me confirm that the game loaded
exactly the bytes trcore wrote.

## After edit test 3

Editor 0.2:
* **Add** (banana, bunch, bumper, goal) and **Delete** for the selected object, with undo;
* free moves that rebuild the lists;
* the collision warning removed, because moves become safe;
* a cap that keeps the stage's banana value at 255 or less.

Moving-part objects and goal colour/type combinations get their own follow-up test.
