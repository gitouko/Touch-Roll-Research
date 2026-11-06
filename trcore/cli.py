"""Command-line entry point:  py -3 -m trcore <command> [options]

Commands (all read-only with respect to the inputs):
  index      content-classify every file under data/ and pair copies across layers
  validate   index + parse every stage file + per-stage reports + validation matrix
  roundtrip  no-op export check: every LCTS source re-exports byte-identically
  inspect    human-readable summary of one .stc / .lz file (optionally full JSON)
  hexview    bounded hex/word dump of a range of a DECODED stage stream

Exit codes: 0 = no errors, 1 = errors found (or warnings with --fail-on-warning),
2 = usage or I/O problem. Output text is ASCII so it is safe in any Windows console.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from typing import Dict, List, Optional

from . import TOOL_NAME, __version__
from . import assets as A
from . import report as R
from .stc.document import StageDocument

DEFAULT_OUT = os.path.join("generated", "trcore")


def _p(msg: str = "") -> None:
    print(msg.encode("ascii", "replace").decode("ascii"))


# ------------------------------------------------------------------ helpers

def _stage_sources(index: dict) -> Dict[str, dict]:
    """stage_key -> {path, payload_sha256} for consistent .stc pairs (prefers a plain copy)."""
    by_path = {a["path"]: a for a in index["assets"]}
    out = {}
    for p in index["pairs"]:
        if p["ext"] != "stc" or p["status"] != "consistent":
            continue
        members = [by_path[x] for v in p["layers"].values() for x in v]
        members.sort(key=lambda a: (a.get("container") != "plain", a["path"]))
        out[p["stage_key"]] = {"path": members[0]["path"], "payload_sha256": p["payload_sha256"]}
    return dict(sorted(out.items()))


def run_roundtrip(root: str, index: dict) -> dict:
    """No-op preservation: every file re-exports identically; LCTS payloads match their pair hash."""
    pair_sha = {(p["stage_key"], p["ext"]): p["payload_sha256"] for p in index["pairs"]}
    res = {"lcts_sources_checked": 0, "lcts_source_identity_pass": 0, "lcts_decoded_matches_pair": 0,
           "other_sources_checked": 0, "other_source_identity_pass": 0, "failures": []}
    for a in index["assets"]:
        path = os.path.join(root, *a["path"].split("/"))
        with open(path, "rb") as fh:
            data = fh.read()
        if a.get("signature") == "LCTS":
            res["lcts_sources_checked"] += 1
            doc = StageDocument(data, a["path"])
            if doc.export_source() == data:
                res["lcts_source_identity_pass"] += 1
            else:
                res["failures"].append({"path": a["path"], "problem": "source export differs"})
            exp = doc.export_decoded()
            want = pair_sha.get((a.get("stage_key"), a.get("name_ext")))
            if exp is not None and hashlib.sha256(exp).hexdigest() == want:
                res["lcts_decoded_matches_pair"] += 1
            else:
                res["failures"].append({"path": a["path"], "problem": "decoded export does not match pair payload"})
        else:
            # Non-stage assets have no document model; the check is that classification
            # never alters the buffer it was given.
            res["other_sources_checked"] += 1
            before = hashlib.sha256(data).hexdigest()
            A.classify_bytes(data)
            if hashlib.sha256(data).hexdigest() == before == a.get("sha256"):
                res["other_source_identity_pass"] += 1
            else:
                res["failures"].append({"path": a["path"], "problem": "source bytes changed or hash mismatch"})
    return res


def _print_index_summary(s: dict) -> None:
    _p(f"files: {s['files']}  lz10: {s['lz10_files']}  lz10_invalid: {s['lz10_invalid']}  "
       f"unknown: {s['unknown_content']}")
    for layer, kinds in s["container_by_layer"].items():
        _p(f"  {layer}: " + ", ".join(f"{k}={v}" for k, v in kinds.items()))
    _p(f"pairs: {s['pairs']} {s['pairs_by_status']}  (lz10+plain copies agree: {s['pairs_with_lz10_and_plain_copies']})")
    _p(f"duplicate-content groups: {s['duplicate_content_groups']}")
    for k, v in s["issue_counts"].items():
        _p(f"  {k}: {v}")


def _require_files(index: dict, root: str) -> None:
    if not index["assets"]:
        raise R.OutputRefused(f"no input files found under {os.path.join(root, 'data')}")


# ----------------------------------------------------------------- commands

def cmd_index(args) -> int:
    index = A.build_index(args.root)
    _require_files(index, args.root)
    s = index["summary"]
    _print_index_summary(s)
    for layer, missing in index["missing_by_layer"].items():
        _p(f"missing in {layer}: {', '.join(missing)}")
    if args.out:
        w = R.OutputWriter(args.out, [os.path.join(args.root, "data")])
        p = w.write_text("corpus_index.json", R.dumps(index))
        _p(f"wrote {p}")
    warn = sum(v for k, v in s["issue_counts"].items() if k.startswith("warning:"))
    if s["error_count"]:
        return 1
    return 1 if (args.fail_on_warning and warn) else 0


def cmd_validate(args) -> int:
    root = args.root
    w = R.OutputWriter(args.out, [os.path.join(root, "data")])
    index = A.build_index(root)
    _require_files(index, root)
    _print_index_summary(index["summary"])
    sources = _stage_sources(index)
    by_payload: Dict[str, List[str]] = {}
    for key, src in sources.items():
        by_payload.setdefault(src["payload_sha256"], []).append(key)

    written = set()
    entries = []
    docs_with_errors = []
    for payload, keys in sorted(by_payload.items(), key=lambda kv: sorted(kv[1])[0]):
        keys = sorted(keys)
        canonical = None
        for key in keys:  # every key is parsed from its own file
            src = sources[key]
            doc = StageDocument.from_file(os.path.join(root, *src["path"].split("/")), src["path"])
            if doc.has_errors():
                docs_with_errors.append(key)
            rep = R.stage_report(doc, key, src["path"], [k for k in keys if k != key])
            name = "stages/" + R.report_filename(key, doc.decoded_sha256, doc.source_sha256)
            w.write_text(name, R.dumps(rep))
            written.add(name)
            if canonical is None:
                canonical = doc
        entries.append({"stage_key": keys[0], "checks": canonical.checks, "variant": canonical.layout_variant,
                        "diag_codes": sorted({d["code"] for d in canonical.diagnostics})})
    matrix = R.validation_matrix(entries)
    rt = run_roundtrip(root, index)
    matrix["roundtrip"] = {k: v for k, v in rt.items()}
    w.write_text("corpus_index.json", R.dumps(index))
    w.write_text("validation_matrix.json", R.dumps(matrix))
    w.write_text("validation_matrix.md", R.matrix_markdown(matrix, index["summary"]))

    stage_dir = os.path.join(w.out_dir, "stages")
    stale = sorted("stages/" + f for f in os.listdir(stage_dir) if "stages/" + f not in written) \
        if os.path.isdir(stage_dir) else []
    problems = []
    if index["summary"]["error_count"]:
        problems.append(f"{index['summary']['error_count']} index error(s)")
    if docs_with_errors:
        problems.append(f"error diagnostics in: {', '.join(docs_with_errors)}")
    if rt["failures"]:
        problems.append(f"{len(rt['failures'])} round-trip failure(s)")
    summary = {"tool": R.tool_id(), "stage_keys": len(sources), "unique_stage_contents": len(entries),
               "writes": w.log, "stale_files_not_written_this_run": stale, "problems": problems,
               "exit_code": 1 if problems else 0}
    w.write_text("run_summary.json", R.dumps(summary))

    _p(f"stage keys: {len(sources)}  unique contents parsed: {len(entries)}")
    for name, c in matrix["checks"].items():
        if c["fail"]:
            _p(f"  {name}: fail {c['fail']} -> {', '.join(matrix['failing_stage_keys'][name])}")
    _p(f"layout variants: " + ", ".join(f"{k}={len(v)}" for k, v in matrix["layout_variants"].items()))
    _p(f"round-trip: LCTS {rt['lcts_source_identity_pass']}/{rt['lcts_sources_checked']} source-identical, "
       f"{rt['lcts_decoded_matches_pair']}/{rt['lcts_sources_checked']} decoded==pair; "
       f"other {rt['other_source_identity_pass']}/{rt['other_sources_checked']}")
    changed = [x for x in w.log if x["status"] == "replaced"]
    _p(f"outputs: {w.out_dir}  (created {sum(1 for x in w.log if x['status'] == 'created')}, "
       f"replaced {len(changed)}, unchanged {sum(1 for x in w.log if x['status'] == 'unchanged')})")
    if stale:
        _p(f"note: {len(stale)} older file(s) in stages/ were not produced by this run (left in place)")
    for pr in problems:
        _p(f"PROBLEM: {pr}")
    return 1 if problems else 0


def cmd_roundtrip(args) -> int:
    index = A.build_index(args.root)
    _require_files(index, args.root)
    rt = run_roundtrip(args.root, index)
    _p(f"LCTS sources: {rt['lcts_sources_checked']}  source-identical: {rt['lcts_source_identity_pass']}  "
       f"decoded==pair: {rt['lcts_decoded_matches_pair']}")
    _p(f"other sources: {rt['other_sources_checked']}  identical: {rt['other_source_identity_pass']}")
    for f in rt["failures"]:
        _p(f"FAIL {f['path']}: {f['problem']}")
    return 1 if rt["failures"] or index["summary"]["error_count"] else 0


def cmd_inspect(args) -> int:
    doc = StageDocument.from_file(args.file, os.path.basename(args.file))
    _p(f"file: {args.file}")
    _p(f"container: {doc.container}  source {len(doc.source)} B sha256 {doc.source_sha256}")
    if doc.decoded is not None:
        _p(f"decoded: {len(doc.decoded)} B sha256 {doc.decoded_sha256}")
    _p(f"layout variant: {doc.layout_variant}")
    if doc.header:
        h = {k: v["value"] for k, v in doc.header.items()}
        _p(f"header: u32_04={h['u32_04']:#x} u32_08={h['u32_08']} u32_0C={h['u32_0C']:#x} u32_10={h['u32_10']:#x} "
           f"u32_14={h['u32_14']} F={h['descriptor_base']:#x} groups={h['group_count']}")
        _p("bounds (Q20.12): min (%g, %g, %g) max (%g, %g, %g)" % tuple(
            h[k] for k in ("bounds_min_x", "bounds_min_y", "bounds_min_z", "bounds_max_x", "bounds_max_y",
                           "bounds_max_z")))
    for r in doc.start.get("records", []) if doc.start else []:
        _p(f"start[{r['index']}] @{r['offset']}: pos {tuple(r['position'])} u32_0C={r['u32_0C']:#x}")
    for g in doc.groups:
        sl = ", ".join(f"{k}={v['count']}@{v['offset']:#x}" for k, v in g["slices"].items())
        _p(f"group {g['index']} @{g['offset']} {g['name_text_04']!r}: det={g['matrix_stats']['det']} "
           f"t={tuple(g['translation'])} grid={g['grid']['nx']}x{g['grid']['nz']} slices[{sl}]")
    for k, p in doc.pools.items():
        if not p["total"]:
            continue
        _p(f"pool {k} ({p['candidate_label']} candidate, stride {p['record_stride']:#x}) @{p['start']}: "
           f"total {p['total']}, referenced {p['referenced']}, unreferenced {p.get('unreferenced', 0)}")
        if k == "A":
            for r in p["records"]:
                _p(f"   A[{r['index']}] @{r['offset']} group={r['group']} t={tuple(r['translation'])} "
                   f"u32_30={r['u32_30']} det={r['matrix_stats']['det']}")
    if doc.coverage:
        c = doc.coverage
        _p(f"coverage: {c['claimed_by_views']}/{c['length']} B in views, {c['zero_fill']} zero-fill, "
           f"{c['opaque']} opaque in {len(c['opaque_ranges'])} range(s)")
    for d in doc.diagnostics:
        _p(f"[{d['severity']}] {d['code']}: {d['message']}" + (f" @{d['offset']}" if d["offset"] else ""))
    fails = [k for k, v in doc.checks.items() if v == "fail"]
    _p(f"checks failing: {', '.join(fails) if fails else 'none'}")
    if args.json:
        out = os.path.abspath(args.json)
        if out == os.path.abspath(args.file) or not out.lower().endswith(".json"):
            _p("refusing: --json must be a new .json path, never the input file")
            return 2
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(R.dumps(R.stage_report(doc, None, os.path.basename(args.file))))
        _p(f"wrote {out}")
    return 1 if doc.has_errors() else 0


def cmd_hexview(args) -> int:
    doc = StageDocument.from_file(args.file)
    if doc.decoded is None:
        _p("cannot decode this file as an LCTS stage stream")
        return 1
    data = doc.decoded
    off, length = args.offset, min(args.length, 0x1000)
    if off < 0 or off >= len(data):
        _p(f"offset {off:#x} outside decoded stream of {len(data):#x} bytes")
        return 2
    end = min(len(data), off + length)
    _p(f"decoded stream {len(data):#x} bytes; showing [{off:#x}, {end:#x})  words: u32 | Q20.12")
    for row in range(off, end, 16):
        chunk = data[row:min(end, row + 16)]
        words = []
        for k in range(0, len(chunk) - 3, 4):
            v = int.from_bytes(chunk[k:k + 4], "little")
            s = v - (1 << 32) if v & 0x80000000 else v
            words.append(f"{v:08x}|{s / 4096.0:g}")
        _p(f"{row:06x}: {chunk.hex(' '):<48}  {'  '.join(words)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="trcore", description=f"{TOOL_NAME} {__version__}: read-only "
                                 "research core for Touch & Roll stage data.")
    ap.add_argument("--version", action="version", version=f"{TOOL_NAME} {__version__}")
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("index", help="classify and pair every file under data/")
    p.add_argument("--root", default=".", help="repository root (default: current directory)")
    p.add_argument("--out", default=None, help="also write corpus_index.json into this directory")
    p.add_argument("--fail-on-warning", action="store_true")
    p.set_defaults(func=cmd_index)
    p = sub.add_parser("validate", help="index + parse all stage files + reports + matrix")
    p.add_argument("--root", default=".")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"output directory (default: {DEFAULT_OUT})")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("roundtrip", help="no-op export identity check over the whole corpus")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_roundtrip)
    p = sub.add_parser("inspect", help="summarize one .stc or LZ10-compressed stage file")
    p.add_argument("file")
    p.add_argument("--json", default=None, help="write the full stage report to this new .json path")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("hexview", help="hex + word view of a decoded range (max 0x1000 bytes)")
    p.add_argument("file")
    p.add_argument("--offset", type=lambda s: int(s, 0), default=0)
    p.add_argument("--length", type=lambda s: int(s, 0), default=0x100)
    p.set_defaults(func=cmd_hexview)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except (OSError, R.OutputRefused) as exc:
        _p(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
