# trcore — research core and ROM-copy tools

`trcore` indexes the extracted Touch & Roll assets by **content**, decodes and encodes LZ10, parses
every `.stc` stage file into a lossless, evidence-annotated document, reads the stage map from the
ROM, and can write **new ROM copies** with replaced files. It never modifies your original ROM, the
repository's `data/`, or anything it did not create.

Requirements: Python 3.8 or newer, standard library only (the editor in `tredit/` additionally needs
Python 3.10+ and PySide6). Run everything from the repository root.

## Commands

```bat
:: one click: index + parse all stages + reports into generated\trcore\
run_trcore_validate.bat

py -3 -m trcore index                       :: classify and pair every file under data\
py -3 -m trcore validate --out generated\trcore
py -3 -m trcore roundtrip                   :: no-op export identity check, whole corpus
py -3 -m trcore inspect data\raw\smb1_ex03.stc
py -3 -m trcore inspect data\grouped\smb1_ex03\stage.stc --json ex03.json
py -3 -m trcore hexview data\raw\smb1_be02.stc --offset 0x100 --length 0x70
py -3 -m unittest discover -s tests -t . -v :: test suite (about 25 s with data\, under 1 s without)

:: ROM tools (read the ROM; write only NEW copies)
py -3 -m trcore rom-info  "Touch & Roll (USA).nds"
py -3 -m trcore stagemap  "Touch & Roll (USA).nds" --out generated\trcore
py -3 -m trcore rom-replace "Touch & Roll (USA).nds" my_copy.nds stcoli/smb1_be01_stc.lz edited_be01.stc
py -3 -m trcore make-gate "Touch & Roll (USA).nds" TR_gate_W1-1_W1-2.nds
py -3 -m trcore stage-edit "Touch & Roll (USA).nds" TR_edit1_World1.nds docs\experiments\edit1_world1\plan.json
py -3 -m trcore ramdump-compare dump.bin --rom "Touch & Roll (USA).nds"
py -3 -m trcore stage-models "Touch & Roll (USA).nds" --out generated\trcore   :: model reader + floor-fit check
py -3 -m trcore cells "Touch & Roll (USA).nds" --main-only                     :: collision cell list rules
```

The desktop editor built on trcore lives in `tredit/`; start it with `run_editor.bat` (see
`docs/editor_v1.md`).

Set `TRCORE_ROM` to your ROM path to also run the ROM tests (and `pip install lupa` to run the
BizHawk script test under real Lua). See `docs/round_trip_gate.md` for the in-game gate and
`tools/bizhawk/trcore_dump_stage.lua` for the memory-dump script.

Exit codes: `0` no errors · `1` errors found · `2` usage or I/O problem (for example an output
directory inside `data\`).

## What `validate` writes (all under `--out`, default `generated\trcore\`)

| File | Contents |
|---|---|
| `corpus_index.json` | every file: layer, stage key, container (from bytes), signature, size, SHA-256, Git blob id, LZ10 stats, issues; cross-layer pairs, duplicates, missing copies |
| `stages\<stage_key>.<sha8>.json` | one report per stage key, named by key **and** decoded-content hash, so reports never overwrite each other |
| `validation_matrix.json` / `.md` | pass/fail/n.a. of every structural check over the unique stage contents, failing stage keys, layout variants, round-trip totals |
| `run_summary.json` | which files were created / replaced / unchanged, older files not produced by this run, problems, exit code |

Reports contain no timestamps or absolute paths: two runs over the same data are byte-identical
(apart from `run_summary.json`). `generated/` is git-ignored; reports are derived artifacts, not
sources of truth.

## Guarantees

* Compression state and file type come from the bytes, never from the name or folder.
* A stage key comes from the original asset name, or from a grouped directory name **only** when an
  originally-named copy with the same content exists; `stage`, `model`, … are never stage keys.
* Every read is bounds-checked; malformed input yields diagnostics, not crashes (fuzz-tested).
* `StageDocument` keeps the original bytes; parsed values are views with their offsets;
  unclaimed bytes are reported as zero-fill or opaque ranges, never dropped.
* No-op export is byte-identical for every stage source (plain and compressed).

## ROM writing rules

`rom-replace` / `make-gate` refuse to write over the input ROM or any existing file, build the new ROM
in memory, verify that nothing but the target files changed (plus the used-ROM size and header CRC
when a file has to move), and write a `.patch.json` record next to the output. A decoded `.stc` given
as the source is compressed exactly the way the game's own compressor does it.

## Editing stage fields

`stage-edit` applies a JSON edit plan (format in `trcore/editplan.py`). Only fields of start records
and object-pool records can be edited (position, matrix, translation and the flag words); every edit
must state the field's current value, and the edit is refused if any byte outside the edited fields
would change or the stage's parsed structure would differ. Each run writes a new ROM copy plus a
`.patch.json` with old/new bytes, offsets, hashes and the stated prediction.

## Adding, removing and moving objects (plan schema `trcore.edit_plan/2`)

A stage entry can also carry `"objects": [...]` with `add`, `remove` and `move` operations (format in
`trcore/stc/objects.py`). The changed pool is rebuilt as one contiguous array at the end of the stage
file, slices and header totals are updated, and that object type's collision cell lists are rebuilt
for the affected groups. Nothing that already exists is moved. Every result is checked before
writing (structure, lists, coverage, offsets, the 255 banana-value limit). Status: built, in-game
test pending (edit test 3).

## Non-goals of this version

No adding/removing objects, no GUI, no collision decoding. Field meanings are confirmed only where
the spec's §14 lists an in-game test (start, goals incl. red flag, bumper position, bananas incl. bunch);
see
`docs/research_notes/stc_format_spec.md` for the evidence and the experiments that confirm them.

## Layout

```
trcore/lz10.py          strict LZ10 decoder + verified encoder matching the game's compressor
trcore/rom.py           read-only DS ROM access, ROM profile, stage map
trcore/romwrite.py      verified "replace a file in a NEW ROM copy"
trcore/stc/edit.py      same-size field edits of known record fields, with structure checks
trcore/stc/objects.py   add / remove / move goals, bumpers, bananas (pools + collision cell lists)
trcore/stc/cells.py     per-group collision cell grid: reader, footprint rule, coverage check
trcore/editplan.py      JSON edit plan -> new ROM copy + patch record
trcore/ramdump.py       compare a BizHawk Main RAM dump with the expected stage file
trcore/nitro/nsbmd.py   read-only NITRO model reader (nodes, structure code, display lists -> triangles)
trcore/stagemodel.py    a stage's own model in stage coordinates + the whole-ROM floor-fit survey
trcore/binreader.py     bounds-checked LE reads, Q20.12
trcore/assets.py        content classification, name parsing, corpus index
trcore/stc/layout.py    layout constants + evidence registry (E01..E21, in-game confirmations)
trcore/stc/document.py  StageDocument: views, pools, groups, variants, coverage, checks
trcore/report.py        deterministic JSON/Markdown, safe output writer
trcore/cli.py           command line
tests/                  unittest suite; synthetic fixtures (no game bytes) + corpus tests
tools/bizhawk/          BizHawk Lua script that dumps memory when a stage loads
```
