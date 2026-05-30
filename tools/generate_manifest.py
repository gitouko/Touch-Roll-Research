from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
from typing import Dict, List, Optional, Tuple

ROLE_BY_EXT = {
    ".nsbmd": "model",
    ".nsbtx": "texture",
    ".nsbca": "animation",
    ".stc": "stage_data",
}

def sha1_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def extract_stage_key(name: str) -> Tuple[str, Optional[str]]:
    """
    Examples:
      smb1_ad01.nsbmd      -> ("smb1_ad01", ".nsbmd")
      smb1_ad01.nsbmd.lz    -> ("smb1_ad01", ".nsbmd")
      smb1_ad01.stc         -> ("smb1_ad01", ".stc")
      smb1_ad01.stc.lz      -> ("smb1_ad01", ".stc")
    """
    lower = name.lower()
    if lower.endswith(".lz"):
        lower = lower[:-3]

    p = Path(lower)
    suffixes = p.suffixes
    if not suffixes:
        return p.stem, None

    last_ext = suffixes[-1]
    stem = p.name[: -len(last_ext)]
    return stem, last_ext

def infer_role(path: Path) -> Optional[str]:
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes and suffixes[-1] == ".lz" and len(suffixes) >= 2:
        return ROLE_BY_EXT.get(suffixes[-2])
    return ROLE_BY_EXT.get(path.suffix.lower())

def file_info(path: Path) -> Dict[str, object]:
    info: Dict[str, object] = {
        "name": path.name,
        "path": str(path.as_posix()),
        "size": path.stat().st_size,
        "sha1": sha1_file(path),
        "role": infer_role(path),
    }
    try:
        with path.open("rb") as f:
            header = f.read(16)
        info["header_hex"] = header.hex(" ")
        info["magic_ascii"] = "".join(chr(b) if 32 <= b <= 126 else "." for b in header[:8])
    except Exception:
        pass
    return info

def build_manifest(input_root: Path) -> Dict[str, object]:
    stages: Dict[str, Dict[str, object]] = {}

    for path in sorted(input_root.rglob("*")):
        if not path.is_file():
            continue

        role = infer_role(path)
        if role is None:
            continue

        stage_key, _ = extract_stage_key(path.name)
        stage = stages.setdefault(
            stage_key,
            {
                "stage_id": stage_key,
                "files": {},
                "raw_files": {},
                "metadata": {
                    "world": None,
                    "difficulty": None,
                    "objects_count": None,
                    "collision_type": None,
                    "notes": "",
                    "verified": False,
                },
            },
        )

        rel = path.relative_to(input_root).as_posix()
        stage["files"][role] = rel
        stage["raw_files"][path.suffixes[-1].lstrip(".").lower() if path.suffixes else path.suffix.lower()] = rel

        # Preserve a small per-file info block for later verification.
        stage.setdefault("file_info", {})[path.name] = file_info(path)

    return {
        "game": "Super Monkey Ball: Touch & Roll / Super Monkey Ball DS",
        "platform": "Nintendo DS",
        "region": "USA",
        "source_root": str(input_root.as_posix()),
        "total_stages": len(stages),
        "stages": [stages[k] for k in sorted(stages.keys())],
        "notes": [
            "Do not treat inferred fields as confirmed until in-game testing verifies them.",
            "The .stc format is still under reverse engineering.",
        ],
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a manifest for Touch & Roll assets.")
    parser.add_argument("input_root", type=Path, help="Root folder containing extracted assets")
    parser.add_argument("-o", "--output", type=Path, default=Path("manifest.json"), help="Output manifest path")
    args = parser.parse_args()

    manifest = build_manifest(args.input_root)
    args.output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")

if __name__ == "__main__":
    main()
