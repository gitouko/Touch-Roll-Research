# trcore — read-only research core

`trcore` indexes the extracted Touch & Roll assets by **content**, decodes LZ10 with a strict
decoder, parses every `.stc` stage file into a lossless, evidence-annotated document, and writes
deterministic reports. It never modifies, recompresses or injects anything.

Requirements: Python 3.8 or newer, standard library only. Run everything from the repository root.

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
```

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

## Non-goals of this version

No editing, no LZ10 encoder, no ROM injection, no GUI, no collision decoding. Field labels
("goal", "banana", …) are hypotheses; see `docs/research_notes/stc_format_spec.md` for the
evidence behind each one and the experiments that would confirm it.

## Layout

```
trcore/lz10.py          strict LZ10 decoder (no encoder)
trcore/binreader.py     bounds-checked LE reads, Q20.12
trcore/assets.py        content classification, name parsing, corpus index
trcore/stc/layout.py    layout constants + evidence registry (E01..E20)
trcore/stc/document.py  StageDocument: views, pools, groups, variants, coverage, checks
trcore/report.py        deterministic JSON/Markdown, safe output writer
trcore/cli.py           command line
tests/                  unittest suite; synthetic fixtures (no game bytes) + corpus tests
```
