from __future__ import annotations

from pathlib import Path
import argparse
import json
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

def ascii_preview(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in data)

def utf16le_strings(data: bytes, min_chars: int = 4) -> List[Tuple[int, str]]:
    out = []
    i = 0
    n = len(data)
    while i + 1 < n:
        if 32 <= data[i] <= 126 and data[i + 1] == 0:
            start = i
            chars = []
            while i + 1 < n and 32 <= data[i] <= 126 and data[i + 1] == 0:
                chars.append(chr(data[i]))
                i += 2
            if len(chars) >= min_chars:
                out.append((start, "".join(chars)))
        else:
            i += 2 if i % 2 else 1
    return out

def ascii_strings(data: bytes, min_len: int = 4) -> List[Tuple[int, str]]:
    out = []
    current = []
    start = None
    for idx, b in enumerate(data):
        if 32 <= b <= 126:
            if start is None:
                start = idx
            current.append(chr(b))
        else:
            if start is not None and len(current) >= min_len:
                out.append((start, "".join(current)))
            current = []
            start = None
    if start is not None and len(current) >= min_len:
        out.append((start, "".join(current)))
    return out

def find_repeated_chunks(data: bytes, chunk_size: int) -> Dict[str, List[int]]:
    locs = defaultdict(list)
    for off in range(0, len(data) - chunk_size + 1):
        chunk = data[off:off + chunk_size]
        locs[chunk.hex()].append(off)
    return {k: v for k, v in locs.items() if len(v) > 1}

def likely_little_endian_u16(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8)

def likely_little_endian_u32(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8) | (data[off + 2] << 16) | (data[off + 3] << 24)

def scan_u16_runs(data: bytes, min_run: int = 6) -> List[Dict[str, object]]:
    runs = []
    i = 0
    n = len(data)
    while i + 1 < n:
        start = i
        values = [likely_little_endian_u16(data, i)]
        i += 2
        while i + 1 < n:
            cur = likely_little_endian_u16(data, i)
            prev = values[-1]
            if cur == prev + 1:
                values.append(cur)
                i += 2
            else:
                break
        if len(values) >= min_run:
            runs.append({
                "offset": start,
                "count": len(values),
                "first": values[0],
                "last": values[-1],
            })
        i = start + 2 if len(values) < min_run else i
    return runs

def scan_aligned_float_candidates(data: bytes) -> List[Dict[str, object]]:
    # Pure heuristic: report values whose bit pattern looks like a sane float.
    import struct
    vals = []
    for off in range(0, len(data) - 3, 4):
        raw = data[off:off + 4]
        f = struct.unpack("<f", raw)[0]
        if f != f:
            continue
        if abs(f) in (0.0, 1.0, 2.0, 10.0, 100.0):
            vals.append({"offset": off, "value": f, "hex": raw.hex(" ")})
        elif -100000.0 < f < 100000.0 and abs(f) < 10000.0:
            # Keep a modest number of plausible candidates.
            if float(int(f)) != f or abs(f) >= 0.5:
                vals.append({"offset": off, "value": f, "hex": raw.hex(" ")})
    return vals[:2000]

def analyze(path: Path) -> Dict[str, object]:
    data = path.read_bytes()
    report: Dict[str, object] = {
        "file": path.name,
        "path": str(path.as_posix()),
        "size": len(data),
        "header_hex": data[:32].hex(" "),
        "header_ascii": ascii_preview(data[:32]),
        "trailer_hex": data[-32:].hex(" ") if len(data) >= 32 else data.hex(" "),
        "trailer_ascii": ascii_preview(data[-32:]) if len(data) >= 32 else ascii_preview(data),
        "ascii_strings": ascii_strings(data),
        "utf16le_strings": utf16le_strings(data),
        "u16_increment_runs": scan_u16_runs(data),
        "float_candidates": scan_aligned_float_candidates(data),
        "repeated_16_byte_chunks": [
            {"chunk_hex": k, "offsets": v}
            for k, v in list(find_repeated_chunks(data, 16).items())[:100]
        ],
        "repeated_8_byte_chunks": [
            {"chunk_hex": k, "offsets": v}
            for k, v in list(find_repeated_chunks(data, 8).items())[:100]
        ],
    }
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic .stc binary analyzer.")
    parser.add_argument("file", type=Path, help="Path to an .stc file")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write JSON report to file")
    args = parser.parse_args()

    report = analyze(args.file)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)

if __name__ == "__main__":
    main()
