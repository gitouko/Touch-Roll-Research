# Touch & Roll Stage Editor — version 0.1.1 (Milestone 2)

**Status: accepted in-game on 2026-11-07** (`docs/experiments/editor_acceptance_v0.1/`).

A desktop editor for *Super Monkey Ball: Touch & Roll* (USA) stages, written in Python on top of
`trcore`. It shows each stage's own model as a top-down map, plus a side view, and lets you move and
turn the objects whose meaning has been confirmed in-game.

## Start it

1. Python **3.10 or newer** is needed, because PySide6 requires it. Check with `py -3 --version`.
2. Double-click **`run_editor.bat`** in the repository folder. The first time, it offers to install
   PySide6 (Qt for Python) with pip. You can also install it yourself: `py -3 -m pip install PySide6`.
3. **File > Open ROM…** and choose your original Touch & Roll ROM. The editor only reads this file.
   It never writes to it.

From a command prompt you can also run `py -3 -m tredit "path\to\rom.nds"`.

## What you can change

| Object | Editable | Locked (shown only) |
|---|---|---|
| Start | position, facing | — |
| Goal | position, facing (turn about the vertical axis), red / normal | tilt |
| Bumper | position | rotation (not testable: bumpers are round) |
| Banana | position, single / bunch | — |

Everything else is read-only in this version: stage groups (parts), motion, collision, and any field
not confirmed in-game. *Stage info (read-only)* lists them. Adding and removing objects comes in
Milestone 3.

## Using it

* **Stages panel:** the 12 worlds with the stage titles. Party modes and unused stage files are under
  *Other stage files*. A `●` marks a stage with edits.
* **Top view:** x runs to the right and forward is up (the direction a start at facing 0° looks).
  Lighter floor is higher. Brownish faces are walls. The dashed box is the stage file's
  bounds-like header values.
* **Side view:** heights. *Automatic* looks along the longer side of the stage. Dragging here changes
  only the height.
* **Mouse:** drag an object to move it. The wheel zooms. Right-drag pans. **F** fits the stage in view.
* **Keys:** arrows move the selected object (Up = forward). PgUp / PgDn change its height.
  **Q / E** turn it 15° left / right (with Shift: 1°). **Ctrl+Z / Ctrl+Y** undo and redo, across
  stages.
* **Properties panel:** exact numbers. Values are always shown as they will be stored (1/4096 steps).
  The map and panel are re-read from the edited stage bytes after every change, so what you see is
  exactly what will be written.
* **View menu:** snap step for dragging (default 0.25). *Keep height above the floor while dragging*
  (on by default) keeps an object at the same height above the floor when you drag it over higher or
  lower ground.
* **Collision warning (0.1.1):** the game only checks an object from the collision cells listed for it
  (spec §16). Moving a goal, bumper or banana changes its record but not those lists. If a move takes
  it out of its cells (roughly more than 2 units for a banana), it gets an **orange dashed ring** and a
  warning in the panel: in-game it may not be collectable or solid there. Small moves are fine. The
  next version rebuilds the lists so any move is safe.
* Objects in a moving part have a **dashed outline**. They are shown where they are when the stage
  starts, and they move with their part in-game.
* Facing: **0° = towards −z** (up on the top view), and larger angles turn **left**. A goal's facing is
  the direction its front (the side you roll through) points. Untouched goals face 180°, back towards
  the start.

## Saving

* **Save as new copy… (Ctrl+Shift+S):** writes a new `.nds` plus a `.patch.json` record next to it.
* **Save (Ctrl+S):** writes to the copy you saved last, replacing it. This is allowed only when the
  file is a copy the editor wrote from the same original ROM and it has not changed since (checked
  against its `.patch.json`). The original ROM can never be the target. Keeping one file name means
  BizHawk keeps using the same save file.
* Every save is built from the **original** ROM plus all your edits. It is verified before it is
  written (only the edited stage files may differ) and re-read afterwards.
* **Export edits as plan (.json):** your edits only, with no game data. The file is small enough to
  share, and anyone with the same original ROM can apply it.
* **Import edits:** loads a plan, or the `.patch.json` of a copy the editor saved. Use it to continue
  working on a hack: open the original ROM, import, then Save over the copy.
* **Opening a copy the editor saved** offers to do that for you: it finds the original next to the copy
  (or one folder up), loads the copy's edits onto it, and Save keeps replacing the copy.
* If you rename a copy, rename its `.patch.json` to the same name (`<name>.patch.json`).
* **Play saved copy in BizHawk (F5):** starts EmuHawk with the saved copy. It asks for EmuHawk.exe
  once.

BizHawk keeps saves per ROM file name. For a new copy name, copy your existing `.SaveRAM` in
`BizHawk\NDS\SaveRAM\` to the new name (spaces instead of underscores) if you need unlocked worlds.

## Acceptance test for this version (please do this one)

Use **only the editor** for steps 1–4.

1. Open the original ROM. Go to **1-1 Elementary**.
   * Select *Start 1* and press **Q** three times. Facing goes 270° → 315°.
     *Prediction:* the ball starts turned 45° to the left of the goal direction.
   * Select *Banana 2*, the second banana from the start, and tick **Bunch**.
   * Drag *Banana 3*, the one just past the goal, to just in front of the start.
2. Go to **1-2 Sine Wave**. Select *Goal 1* and press **E** three times (180° → 135°), then tick
   **Red goal**. *Prediction:* the goal is red and turned 45°. Its front faces the approaching ball
   but is angled to the ball's left, as the arrow on the map shows.
   This is the first goal turn that is not a multiple of 90°.
3. Go to **5-2 Sword**. Select *Bumper 5*, the one in the middle of the diamond (x 0, z −30), and press
   **Right** four times (x 0 → 1.0). *Prediction:* that bumper sits 1 unit to the right of the
   diamond's centre.
4. **Save as new copy…** → `TR editor test.nds`. Then press **F5** (or open the copy in BizHawk) and check
   1–3 against the map.
5. Back in the editor, in 1-1 tick **Bunch** on *Banana 4* and press **Ctrl+S**. The copy is replaced
   without a question. Reload it in BizHawk: banana 4 should now be a bunch too.
6. Optional: run `tools/bizhawk/trcore_dump_stage.lua` while visiting 1-1, 1-2 and 5-2 and send the
   dumps. I'll confirm that memory matches the editor's bytes, as in the edit tests.

Please also note anything on the map that does not match what the game shows: a missing floor piece,
a mirrored layout, an object in the wrong place, or a facing arrow pointing the wrong way.

## How the editor stays accurate

* The GUI never writes bytes. Every change becomes a field edit
  (`trcore/stc/edit.py`, the same code that built both in-game edit tests). That code refuses anything
  outside the confirmed fields and checks the stage's structure after every edit.
* Tests replay edit tests 1 and 2 through the editor's own operations and check that the resulting
  stage bytes are identical to the in-game-verified ones (`tests/test_editor_project.py`).
* The map comes from `trcore/nitro/nsbmd.py`. Its decoded triangle counts equal the model headers in
  all 213 stage models, and objects sit on the decoded floors (spec §15).
