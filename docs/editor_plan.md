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
* Editor 0.2 adds, deletes, duplicates and freely moves goals, bumpers and bananas. It is waiting for its
  acceptance test (`docs/editor_v1.md`).

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

## What is left before the editor is complete (2026-11-07)

| Step | What it needs | Kind of work |
|---|---|---|
| 0.2 acceptance | the owner's in-game test of adding, deleting and free moves made with the editor | testing only |
| Moving-part objects | confirm delete / far move / add inside moving parts in-game; then allow adding to a chosen part | small test, then a group choice in the editor |
| **4 — collision editing** | decode the four collision tables (descriptor +0x74…+0x90: records 0x10/0x20/0x34/0x34), the cell lists for bits 0–3 and the +0xAC tree; relate them to the visual model; edit them; rebuild the lists | **largest research step** |
| **4b — platforms** | write new NITRO model geometry (NSBMD) with a placeholder texture that works with the stage's `.nsbtx`, plus matching collision; possibly new parts (groups) | research + writing a model encoder |
| **5 — 3D view** | textured 3D rendering (decode `.nsbtx` textures), 3D picking and dragging | mostly engineering |
| 6 — release | Windows build (single `.exe` via PyInstaller), user guide, patch-based sharing, decision on the public repository's extracted game files | packaging |

Possible extras, if wanted: moving-part motion preview (`.nsbca` animations), stage-wide values such as
time limit or background (not located yet), multi-start party stages, a stage overview.

