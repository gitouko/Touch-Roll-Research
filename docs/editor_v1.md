# Touch & Roll Stage Editor — version 0.2

**Status:** 0.1 was accepted in-game on 2026-11-07 (`docs/experiments/editor_acceptance_v0.1/`). 0.2
adds adding, deleting, duplicating and free moves, all built on edit test 3, which passed in-game. 0.2's
own acceptance test is below.

A desktop editor for *Super Monkey Ball: Touch & Roll* (USA) stages, written in Python on top of
`trcore`. It shows each stage's own model as a top-down map, plus a side view. You can add, delete,
move and turn the objects whose meaning has been confirmed in-game.

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
| Start | position, facing | adding / deleting starts |
| Goal | **add, delete, duplicate**, position, facing (turn about the vertical axis), red / normal | tilt |
| Bumper | **add, delete, duplicate**, position | rotation (not testable: bumpers are round) |
| Banana | **add, delete, duplicate**, position, single / bunch | — |

* New objects go into the stage's **fixed part** (group 0).
* Objects can be moved **anywhere inside the stage's collision grid**. When a move takes an object out of
  the collision cells the game checks it in, the editor rebuilds those lists (spec §16, confirmed by edit
  test 3). Small moves stay simple field edits, exactly as in 0.1.
* A stage's **banana value** (single = 1, bunch = 5) must stay at **255 or less**, because the game counts
  it in one byte. The status bar shows it, and the editor refuses changes that would go over.
* Everything else is read-only: stage groups (parts), motion, collision and any field not confirmed
  in-game. *Stage info (read-only)* lists them.
* Objects in **moving parts** can be moved, and in 0.2 also deleted. Deleting them or moving them far has
  not been confirmed in-game yet; the panel says so.

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
* **Adding:** pick *Add banana* (key **1**), *Add banana bunch* (**2**), *Add bumper* (**3**) or *Add goal*
  (**4**) from the toolbar or the *Object* menu, then click on the top view. **Esc** cancels.
  * New objects sit on the floor under the click: bananas 0.5 above it, bumpers and goals on it.
  * A new goal turns its front towards the stage's start.
  * If there is no floor under the click, the status bar says so; set the height in the panel.
* **Delete** removes the selected goal, bumper or banana. **Ctrl+D** duplicates it 1 unit to the right.
  *Edit > Reset selected object to original* brings back a deleted or changed original object.
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

## Acceptance test for 0.2 (please do this one)

Use **only the editor** for steps 1–5. Start from your original ROM.

1. **1-1 Elementary**
   * Add a **banana bunch** (key 2) on the floor between the start and the goal, about 3 units to the side.
   * Select *Banana 1* and press **Del**.
   * Drag *Banana 3* (just past the goal) all the way back to about 2 units in front of the start. In 0.1
     this would have left it uncollectable.

   *Predictions:* the bunch is there and gives +5; banana 1 is gone; banana 3 is collected at its new place.
2. **1-2 Sine Wave**
   * Add a **goal** (key 4) on the straight about 6 units ahead of the start. It turns towards the start.
   * Tick **Red goal**.

   *Prediction:* a red goal ahead of the start, and rolling into it clears the stage. Please note what
   happens next, because this is the first red goal added from scratch.
3. **5-2 Sword**
   * Add **two bumpers** (key 3) on the blade.
   * Delete **two** of the diamond's bumpers.
   * Select a banana and press **Ctrl+D**.

   *Predictions:* the new bumpers bounce the ball; the deleted ones are gone; the copy can be collected.
4. **Save as new copy…** → `TR editor test 2.nds` (copy your `.SaveRAM` to `TR editor test 2.SaveRAM`
   first). Play it and check 1–3.
5. Back in the editor, press **Ctrl+Z** once (it undoes the duplicate), then **Ctrl+S**. The copy is
   replaced; reload it and the duplicated banana is gone.
6. Optional, moving parts: in **5-6 Conveyor**, delete one of the moving bumpers. *Prediction:* it is
   gone and the others still move.
7. Optional: run `trcore_dump_stage.lua` in the stages you edited and send the dumps.

Please also note anything on the map that does not match what the game shows.

## How the editor stays accurate

* The GUI never writes bytes. Every change becomes either a field edit (`trcore/stc/edit.py`) or an object
  operation (`trcore/stc/objects.py`). Those are the same code paths that built the in-game edit tests,
  and they refuse anything outside the confirmed fields. After every change, the stage is rebuilt from
  the original bytes and fully checked: structure, pools and totals, collision lists, coverage and the
  banana value.
* Tests replay **edit tests 1, 2 and 3** through the editor's own operations: moves, turns, flags, adds,
  deletes and a far move. The resulting stage bytes are identical to the in-game-verified ones
  (`tests/test_editor_project.py`).
* The map comes from `trcore/nitro/nsbmd.py`. Its decoded triangle counts equal the model headers in
  all 213 stage models, and objects sit on the decoded floors (spec §15).
