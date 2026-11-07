# Milestones 4 + 4b — collision editing and platforms: findings and plan

Status (2026-11-07): **collision decoded** (spec §17, Level 2). **Collision editing and model polygons are
implemented in trcore** (`trcore/stc/geometry_edit.py`, `trcore/nitro/nsbmd_write.py`, plan schema
`trcore.edit_plan/3`; spec §15, §17.3). **Edit test 4 is built** and waiting for the in-game test:
`docs/experiments/edit4_collision/`. The editor UI for collision and platforms follows once it passes.

Changes to the test as proposed, found while building it:
* 1-1 is fenced all round by a guard rail the ball cannot pass under, so **I** also opens a 4-unit gap in
  the far rail's collision (the rail stays drawn), and the invisible floor sits level with the edge's lip.
* The collision grid ended 0.5 past the rail, and nothing outside the grid can be touched (spec §17.3), so
  the 1-1 grid grows by 5 columns for **I**.
* **H** leaves a 3-unit lane solid on one side so the far end (I) can still be reached.
* **J** is drawn from both sides (stage materials cull back faces).

## What we know now

* The four collision tables (quads, triangles, edges, corner points), their record layouts, how the ball
  uses them, and which cells list them (spec §17).
* Collision is generated from the stage model's own polygons at rest. Faces, edges and corner points can
  be generated the same way for new geometry, and existing collision can be kept byte-for-byte.
* Moving parts each have their own tables and grid, in rest-pose coordinates. A platform on a moving part
  goes into that part's tables and that model node's shapes, and then moves with the part.

## How editing will work (no existing data moves, as in Milestone 3)

1. **Collision tables:** for the changed group, rebuild a table with the old records in their order plus
   the new ones appended. Write it at the end of the stage file and update that group's count/offset.
   Existing indices do not change, so existing cell lists only gain new indices (appended, so they stay
   sorted). Removing collision renumbers that group's lists, as for objects.
2. **Generating collision from polygons:**
   * each polygon gives a quad (if it is a planar parallelogram) or triangles, encoded with
     `dual_vectors()`;
   * every unique edge gives an edge record and every unique corner a corner point;
   * cells come from the 0.5 rule plus a safety margin.
3. **Visible geometry (NSBMD):** add the polygons to an **existing shape** (its display list is copied to
   the end of the model with the new GX commands after it), so they are drawn with that shape's
   **existing material and texture** as the placeholder and the stage's `.nsbtx` stays untouched. No
   dictionary or SBC change is needed. Update sizes, counts and the bounding box, then compress and write
   the model file like a stage file.
4. **Platform = both:** the editor's "Add platform" (a box or ramp first) creates the model polygons and
   their collision together in one group, so the two can never disagree.
5. **Checks:**
   * the stage and the model re-parse;
   * the collision survey rules hold for the edited group;
   * the new collision coincides with the new model polygons;
   * every relocated offset stays inside the file;
   * memory dumps from the in-game test match.

## Edit test 4 (proposed)

One ROM copy, original ROM as the base, all in stages you know:

| # | Stage | Change | Prediction |
|---|---|---|---|
| H | 1-1 Elementary | **remove the collision** of a 2-unit strip across the floor between banana 1 and banana 2 (the floor stays visible) | the ball falls through the visible floor at that strip |
| I | 1-1 | **add invisible collision**: a 4 × 4 floor beyond the far edge behind the goal, at floor height | the ball can roll off the visible floor onto "air" there and back |
| J | 1-2 Sine Wave | **add a visible-only quad** (the stage's floor texture) hovering 2 units above the start straight, no collision | it is drawn, but the ball passes under or through it |
| K | 1-2 | **add a real platform**: a low box (about 1.5 wide, 2 deep, 1 high) on one side of the start straight, with model **and** collision | it is drawn and solid: the ball cannot roll through it and bounces off its side, while the other half of the straight stays free |
| L | 1-1 | memory dumps of both stages | the game loaded exactly the new tables, lists and model |

H and I test collision alone, J tests the model writer alone, and K tests both together. That separates
any problem cleanly.
