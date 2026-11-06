# Round-trip gate — result: PASSED (2026-11-06)

Procedure: `docs/round_trip_gate.md`. Played by the project owner in **BizHawk 2.11.1** (NDS core,
memory domain "Main RAM"); memory dumps taken with `tools/bizhawk/trcore_dump_stage.lua`; compared
by Claude with `py -3 -m trcore ramdump-compare`. The 4 MiB RAM dumps are not committed (they contain
game memory); the JSON files here are the comparison summaries.

| ROM | SHA-1 |
|---|---|
| original (USA) | `3b0bf7f4e35112cd2d91ffbf2a874aec300d7a17` |
| gate copy `TR_gate_W1-1_W1-2.nds` | `256ab7368effbdfe4d3aa8328c7938df42365626` |

| Stage | Change in the gate ROM | Owner saw a difference? | In-memory stage data, gate vs original |
|---|---|---|---|
| World 1-1 "Elementary" — ID 0, `smb1_be01` | same compressed bytes, moved to the end of the ROM | none | **identical** (0 of 21,324 words differ) |
| World 1-2 "Sine Wave" — ID 119, `smbds_023` | different, 440-byte-larger compression of the same data, moved | none | **identical** (0 of 46,248 words differ) |

Both stages loaded at the same RAM address in both ROMs (0x02250730 and 0x02251730), and the stage
pointer read by the script pointed at `LCTS` data, so the RAM addresses in `trcore/rom.py` are confirmed
in the running game.

## What the dumps show about the format (unmodified original ROM)

In both stages every word of the in-memory copy equals the file **except** words the game converts from
a file offset into a memory pointer (`ram == file + load address`); there were **0** other
differences. The converted words are therefore offsets, observed in the running game:

| Field | World 1-1 | World 1-2 |
|---|---:|---:|
| header 0x18 `descriptor_base` | 1 | 1 |
| header 0x3C `start_offset` | 1 | 1 |
| descriptor +0x04, +0x08 (name offsets) | 1 + 1 | 1 + 1 |
| descriptor +0x54 (cell table) | 1 | 1 |
| descriptor +0x78, +0x80, +0x88, +0x90 (offset half of the +0x74/+0x7C/+0x84/+0x8C pairs) | 1 each | 1 each |
| descriptor +0x98 (pool A / goal slice) | 1 | 1 |
| descriptor +0xA8 (pool C / banana slice) | 1 | 1 |
| cell-table entry +0x04 (one per grid cell) | 189 (= 21 × 9) | 2,268 |
| inside the undecoded collision region | 643 | 3,818 |

Zero-valued offsets are left at zero by the game, so fields that are 0 in these stages (e.g. the empty
pool-B slice at +0xA0) cannot be checked here. Counts, matrices, coordinates and flags are not touched
at load time.
