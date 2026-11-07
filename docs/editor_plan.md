# Touch & Roll Stage Editor — plan

Decisions by the project owner (2026-11-06), mapped onto the contract's milestones.

## Form
* **Desktop application**, Windows first, for full control as the project grows into deeper analysis,
  adding/removing objects and collision editing.
* Engine: `trcore` (Python, standard library), which already reads/validates stages, writes verified
  ROM copies and checks results against emulator memory.
* UI toolkit (confirmed 2026-11-06): **PySide6 / Qt for Python** — native desktop widgets, LGPL-3
  licence (allows a separately distributed app), and Qt's OpenGL support for the later 3D view, so the
  2D → 3D transition does not need a rewrite.
* Map background (owner's choice, 2026-11-06): a top-down outline of the stage's own model read from
  the ROM (spec §15).
* Saving (owner's choice): both modes — "Save" replaces the editor's own previous copy (verified),
  "Save as new copy" always writes a new file.

**Status (2026-11-07):**
* Milestone 2 (editor 0.1) passed the owner's in-game acceptance test
  (`docs/experiments/editor_acceptance_v0.1/`).
* Milestone 3 research and edit test 3 passed (`docs/experiments/edit3_add_remove/`).
* Editor 0.2 adds, deletes, duplicates and freely moves goals, bumpers and bananas; its acceptance test
  passed (0.2.1 fixes repeated Delete/Duplicate).
* Milestone 4/4b: collision decoded (spec §17); collision editing and model polygons implemented in trcore;
  **edit test 4** built and waiting for the in-game test (`docs/experiments/edit4_collision/`).

## Views
* **2D top-down map** from the first version on.
* **3D view** replaces/extends the 2D map as the last major update before the first public release, after
  collision editing works and matches the edited ROM in-game.

## Order of work
| Milestone | Content | Gate before starting |
|---|---|---|
| 2 — editor v1 | open the ROM, stage browser (world/stage map), 2D map, select/move/rotate **existing** start, goals (incl. red flag), bumpers, bananas (single/bunch); undo/redo; save as a new ROM copy + patch record | edit test 2 passed; only Level-4 fields editable, everything else read-only |
| 3 — add/remove objects | grow/shrink object pools, update totals, group slices and the collision cell lists (spec §16) | **done in 0.2** for the stage's fixed part; open: objects in moving parts, red goals added from scratch |
| 4 — collision | decode and edit collision (descriptor tables +0x74…+0x8C, grid cells, cell lists) | collision structure decoded and an in-game collision edit verified |
| 4b — platforms | add/edit platforms with a placeholder texture compatible with the stage's `.nsbtx` | collision editing works; NITRO model/texture writing for new geometry |
| 5/6 — 3D view, release | 3D view replaces the 2D map; packaging; distribution as patches | everything above verified in-game |

## Rules carried over from the research phase
* The original ROM is never modified; every save is a new copy with a patch record.
* A field is only editable once its meaning is confirmed in-game (Level 4).
* Unknown bytes are preserved exactly.
* For sharing, edits should go out as patches rather than ROMs. The public repository still hosts the
  extracted game files; decide on that before announcing a community release.

## What is left before the editor is complete (updated 2026-11-07 with the owner's additions)

Done: 0.1 (move/turn/flags), 0.2 (add/delete/duplicate/free moves; acceptance passed, including a red goal
added from scratch and a deletion inside a moving part).

| # | Step | What it needs | Kind of work |
|---|---|---|---|
| 4 + 4b | **Collision editing and platforms** (done together, owner's choice) | decode the four collision tables (descriptor +0x74…+0x90: records 0x10/0x20/0x34/0x34), the cell lists for bits 0–3 and the +0xAC tree, and their link to the visual model; edit them and rebuild the lists; write new NITRO geometry (NSBMD) with a placeholder texture that works with the stage's `.nsbtx`, plus matching collision; possibly new parts (groups) | **largest research step** |
| 5 | **3D view** | textured 3D rendering (decode `.nsbtx`), 3D picking and dragging | mostly engineering |
| 6 | **Animation support** (owner's addition) | parse the stages' animations: `.nsbca` node animation (moving parts, 79 stages), `.nsbma` material (5), `.nsbta` texture SRT (17), `.nsbtp` texture pattern (1); play them in the views; a **keyframe editor** for new and existing animations. Edited animations must drive the collision of the same part (moving groups are tied to model nodes by name, spec §15), so model and collision never come apart. | research + engineering |
| 7 | **World / stage name editing** (owner's addition) | rename worlds and stages in the original ROM's text and write them to the modified ROM (name tables / text resources to locate; length limits per language) | small research + editor page |
| 8 | Release | single Windows `.exe` (PyInstaller), user guide, patch-based sharing, decision on the public repository's extracted game files | packaging |

Smaller open items: adding objects into a chosen moving part, multi-start party stages, and stage-wide values
such as the time limit (not located yet).
