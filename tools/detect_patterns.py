from __future__ import annotations

from pathlib import Path
import argparse
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

def iter_files(paths: List[Path]) -> List[Path]:
    out = []
    for p in paths:
        if p.is_dir():
            out.extend([x for x in p.rglob("*") if x.is_file()])
        elif p.is_file():
            out.append(p)
    return out

def chunk_counts(data: bytes, chunk_size: int) -> Counter:
    c = Counter()
    for off in range(0, len(data) - chunk_size + 1):
        c[data[off:off + chunk_size]] += 1
    return c

def common_chunks(files: List[Path], chunk_size: int, top_n: int = 25) -> List[Tuple[str, int]]:
    per_file = []
    for f in files:
        data = f.read_bytes()
        per_file.append(set(chunk for chunk, cnt in chunk_counts(data, chunk_size).items() if cnt > 1))

    if not per_file:
        return []

    common = set.intersection(*per_file)
    scored = []
    for chunk in common:
        score = sum(1 for f in files if chunk in f.read_bytes())
        scored.append((chunk.hex(" "), score))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:top_n]

def repeated_chunks_in_file(path: Path, chunk_size: int, top_n: int = 20) -> List[Tuple[str, int]]:
    data = path.read_bytes()
    counts = chunk_counts(data, chunk_size)
    items = [(chunk.hex(" "), cnt) for chunk, cnt in counts.items() if cnt > 1]
    items.sort(key=lambda x: (-x[1], x[0]))
    return items[:top_n]

def main() -> None:
    parser = argparse.ArgumentParser(description="Detect repeated byte patterns across Touch & Roll files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Files or folders to analyze")
    parser.add_argument("--chunk", type=int, default=16, help="Chunk size in bytes (default: 16)")
    parser.add_argument("--top", type=int, default=20, help="Top results to print")
    parser.add_argument("--across-files", action="store_true", help="Show chunks common across all inputs")
    args = parser.parse_args()

    files = iter_files(args.paths)
    if not files:
        print("No files found.")
        return

    print(f"Files: {len(files)}")
    print(f"Chunk size: {args.chunk}")
    print()

    if args.across_files and len(files) > 1:
        print("Common repeated chunks across all inputs:")
        for chunk_hex, score in common_chunks(files, args.chunk, args.top):
            print(f"{score:>3}  {chunk_hex}")
        print()

    for f in files:
        print(f"== {f} ==")
        for chunk_hex, cnt in repeated_chunks_in_file(f, args.chunk, args.top):
            print(f"{cnt:>3}  {chunk_hex}")
        print()

if __name__ == "__main__":
    main()
