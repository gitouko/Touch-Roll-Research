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

**Status:** Milestone 2 is built as editor 0.1 (`tredit/`, guide in `docs/editor_v1.md`). It is waiting
for the owner's acceptance test.

## Views
* **2D top-down map** from the first version on.
* **3D view** replaces/extends the 2D map as the last major update before the first public release, after
  collision editing works and matches the edited ROM in-game.

## Order of work
| Milestone | Content | Gate before starting |
|---|---|---|
| 2 — editor v1 | open the ROM, stage browser (world/stage map), 2D map, select/move/rotate **existing** start, goals (incl. red flag), bumpers, bananas (single/bunch); undo/redo; save as a new ROM copy + patch record | edit test 2 passed; only Level-4 fields editable, everything else read-only |
| 3 — add/remove objects | grow/shrink object pools, update totals, group slices and every offset that points past them | relocation rules derived (RAM pointer map from the gate test) and an in-game add/remove test |
| 4 — collision | decode and edit collision (descriptor tables +0x74…+0x8C, grid cells, cell lists) | collision structure decoded and an in-game collision edit verified |
| 4b — platforms | add/edit platforms with a placeholder texture compatible with the stage's `.nsbtx` | collision editing works; NITRO model/texture writing for new geometry |
| 5/6 — 3D view, release | 3D view replaces the 2D map; packaging; distribution as patches | everything above verified in-game |

## Rules carried over from the research phase
* The original ROM is never modified; every save is a new copy with a patch record.
* A field is only editable once its meaning is confirmed in-game (Level 4).
* Unknown bytes are preserved exactly.
* For sharing, edits should go out as patches rather than ROMs. The public repository still hosts the
  extracted game files; decide on that before announcing a community release.
