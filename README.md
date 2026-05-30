# Touch & Roll Reverse Engineering Repo

This repo layout is meant to support bulk asset tracking, stage grouping, binary analysis, and later editor development for **Super Monkey Ball: Touch & Roll / Super Monkey Ball DS**.

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
