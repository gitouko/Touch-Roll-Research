# Editor 0.1 acceptance test (2026-11-07)

The project owner made every edit with the editor (`docs/editor_v1.md`, acceptance test) and played the
saved copy `TR editor test.nds` (SHA-1 `4eb282dd…`) in BizHawk 2.11.1.

**Result: PASSED.** Each edit appeared in-game as it did on the map. In all three visited stages the
game's memory held exactly the stage files of the played ROM.

## What the played ROM contains (field-level diff against the original ROM, SHA-1 `3b0bf7f4…`)

Only three stage files differ from the original. Header, ARM9/ARM7, overlays and every other file
are byte-identical (checked with `trcore.romwrite.verify`).

| Stage | Change (original → played) | Owner's observation |
|---|---|---|
| W1-1 Elementary | start facing 270° → **315°** (turned 45° left) | "turns 45 deg left" (reported as the goal; the file shows the start was turned, which was the test step) |
| W1-1 | banana 2 single → **bunch** | bunch |
| W1-1 | banana 3 (8.45, 0.5, 0) → (8.25, 0.5, −1.75) | "actually shifts" |
| W1-2 Sine Wave | goal facing 180° → **225°** (matrix rows ±0.70703125, i.e. ±2896/4096) | turned 45° |
| W1-2 | goal flag 0 → **1** | red goal |
| W5-2 Sword | bumper 1 x 0 → **1.0** | moved 1 unit right |

The guide asked for 135° (E ×3); 225° is the same 45° turn the other way (Q ×3). Either way, this is
the first goal turn that is not a multiple of 90° to be seen in-game, so arbitrary goal facings
work. Steps 3 (bumper 5) and 5 (Save replacing the copy) were done differently or skipped. Save's
file handling is covered by automated tests and does not change what the game sees.

## Memory check (`results/`)

| Dump | Stage | Result |
|---|---|---|
| stage 0, frame 2582 | smb1_be01 (W1-1) | 20,481 words equal, 843 offset→pointer, **0 other** |
| stage 119, frame 4513 | smbds_023 (W1-2) | 40,151 equal, 6,097 offset→pointer, **0 other** |
| stage 11, frame 6827 | smb1_ad02 (W5-2) | 60,327 equal, 5,101 offset→pointer, **0 other** |

## Workflow observation (led to an editor change)

`played_rom_last_save_record.json` shows the copy was made in two sessions. First, a copy was saved
from the original. Then that copy was opened as the base, bumper 1 was moved again (2.5 → 1.0), and the
result was saved as a new file and renamed. The record next to a copy only describes its last step,
so the editor now:

* offers, when an editor-made copy is opened, to open the original it came from instead and load the
  copy's edits (found by SHA-1 next to the copy or one folder up), with Save set to keep replacing
  that copy;
* records the chain (`base_rom_was_editor_copy`) when edits are still stacked on a copy.

Renaming a copy also needs its `.patch.json` renamed to match (`<name>.patch.json`), otherwise Save
cannot prove the copy is its own and asks for a new name.
