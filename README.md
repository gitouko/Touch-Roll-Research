# Touch & Roll Reverse Engineering Repo

This repo layout is meant to support bulk asset tracking, stage grouping, binary analysis, and later editor development for **Super Monkey Ball: Touch & Roll / Super Monkey Ball DS**.

## Stage editor (desktop, 0.1)
Double-click `run_editor.bat` (Python 3.10+; it offers to install PySide6), open your original
Touch & Roll (USA) ROM, and edit starts, goals, bumpers and bananas on a map of the stage's own model.
Your ROM is only read; saving writes a separate copy plus a `.patch.json` record.
Guide: `docs/editor_v1.md`. Research core and command-line tools: `trcore/README.md`.

## Suggested flow
1. Place raw extracted files in `data/raw/`
2. Decompress `.lz` files into `data/decompressed/`
3. Group files by stage into `data/grouped/`
4. Generate or update `manifest.json`
5. Run the `.stc` analysis tools on candidate stage files
6. Use the pattern detector to compare similar stages

## Notes
- The stage format is still under investigation.
- Treat all binary structure claims as hypotheses until verified in-game.
- The manifest should be the source of truth for what is known, suspected, and unconfirmed.
