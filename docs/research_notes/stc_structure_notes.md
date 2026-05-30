# STC notes

Status: under reverse engineering.

## Known / suspected contents
- start_position
- banana
- bumper
- goal
- red_goal
- collision_data
- animated_collision
- animated_object

## Current clues
- `LCTS` magic at the start of file
- no obvious readable object names in the binary
- likely numeric records / offsets / tables
- likely stage-specific layouts and counts

## Verification rule
Do not mark any field as confirmed until a controlled edit is tested in-game.
