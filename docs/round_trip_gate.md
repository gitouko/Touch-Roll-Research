# Round-trip gate: can the game load stage files that trcore wrote?

**Why:** every future edit means re-compressing a stage file and putting it back into a ROM copy.
Before trusting any edit, we check that the game accepts files written by trcore, using stages that
have *not* been edited.

**Already proven without the game:** trcore's LZ10 encoder reproduces the original compressed bytes
of all 235 stage files, so decompressing and recompressing an unchanged stage gives back a ROM with
the **same SHA-1** as the original. That part needs no in-game test.

**What still needs the game** — two things real edits will need:

| Stage | What the gate ROM changes | What it tests |
|---|---|---|
| World 1-1 "Elementary" (`smb1_be01`) | identical compressed bytes, **moved** to the end of the ROM | the game finds a file at a new location |
| World 1-2 "Sine Wave" (`smbds_023`) | **different** but equivalent compression (440 bytes larger, so also moved) | the game accepts a different compressed stream and size |

## Files

* `TR_gate_W1-1_W1-2.nds` — made with `py -3 -m trcore make-gate <original ROM> TR_gate_W1-1_W1-2.nds`;
  its `.patch.json` lists every change and both SHA-1s.
* `tools/bizhawk/trcore_dump_stage.lua` — BizHawk script that saves the game's memory each time a
  stage loads (read-only; about 4 MiB per stage).

## Steps (about 10 minutes)

1. **Original ROM, baseline.** Open your original ROM in BizHawk. Open **Tools → Lua Console**, then
   **Script → Open Script…** and pick `trcore_dump_stage.lua`. Start a game and play **World 1-1**,
   then continue into **World 1-2**. The Lua Console prints a "Saved …" line for each stage. Stop the
   script when both are saved.
2. **Gate ROM.** Open `TR_gate_W1-1_W1-2.nds` (it has its own empty save, so start a new game). Run the
   script again and play World 1-1 and World 1-2 the same way.
3. **Watch for differences** while playing the gate ROM: crash or freeze, missing or moved floor,
   bananas, goal or start position, ball falling through the floor, wrong music or visuals.
4. **Tell Claude you're done.** The dumps (`trcore_ram_*.bin/.txt/.png`) are in the script's folder;
   Claude can read them from there, or you can run:

   ```bat
   py -3 -m trcore ramdump-compare <gate dump>.bin --rom TR_gate_W1-1_W1-2.nds --against <original dump>.bin --against-rom "<original ROM>.nds"
   ```

## Pass criteria

* Both stages load and play exactly like the original (step 3), and
* for each stage, the in-memory stage data from the gate ROM equals the original's after converting
  pointers back to offsets (`identical after pointer normalisation: True`).

The comparison also shows which file offsets the game turns into pointers when it loads a stage
("offset->pointer" lines) — useful evidence about which fields are offsets.

If the gate fails, nothing else is affected: your original ROM and save are never modified.
