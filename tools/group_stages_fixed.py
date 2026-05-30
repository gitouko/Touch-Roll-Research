from __future__ import annotations

from pathlib import Path
import argparse
import shutil
from typing import Optional, Tuple

ROLE_BY_EXT = {
    ".nsbmd": "model.nsbmd",
    ".nsbtx": "texture.nsbtx",
    ".nsbca": "animation.nsbca",
    ".stc": "stage.stc",
}

KNOWN_EXTS = set(ROLE_BY_EXT.keys())

def strip_lz(name: str) -> str:
    return name[:-3] if name.lower().endswith(".lz") else name

def parse_stage_and_ext(name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Handles:
      smb1_ad01.nsbmd
      smb1_ad01.nsbmd.lz
      smb1_ad01_nsbmd
      smb1_ad01_nsbmd.lz
      smb1_ad01.stc
      smb1_ad01_stc
    Returns: (stage_key, ext) where ext is one of .nsbmd/.nsbtx/.nsbca/.stc
    """
    base = strip_lz(name)
    lower = base.lower()

    p = Path(lower)
    if p.suffix in KNOWN_EXTS:
        ext = p.suffix
        stage_key = p.name[: -len(ext)]
        return stage_key, ext

    for ext in KNOWN_EXTS:
        suffix = "_" + ext.lstrip(".")
        if lower.endswith(suffix):
            stage_key = base[: -len(suffix)]
            return stage_key, ext

    return None, None

def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

def main() -> None:
    parser = argparse.ArgumentParser(description="Group Touch & Roll files into per-stage folders.")
    parser.add_argument("input_root", type=Path, help="Folder containing decompressed files")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/grouped"), help="Grouped output root")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying them")
    args = parser.parse_args()

    files = [p for p in args.input_root.rglob("*") if p.is_file()]
    grouped = 0

    for src in files:
        stage_key, ext = parse_stage_and_ext(src.name)
        if stage_key is None or ext is None:
            continue

        dst_name = ROLE_BY_EXT[ext]
        dst = args.output / stage_key / dst_name

        dst.parent.mkdir(parents=True, exist_ok=True)
        if args.move:
            shutil.move(str(src), str(dst))
        else:
            copy_file(src, dst)

        print(f"{src} -> {dst}")
        grouped += 1

    print(f"\nGrouped {grouped} file(s).")

if __name__ == "__main__":
    main()
