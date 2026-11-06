"""Replace one NitroFS file in a COPY of a DS ROM, with full verification.

Safety rules:
  * the input ROM is opened read-only and never written;
  * the output path must not exist yet and must not be the input;
  * the new ROM is built in memory and verified BEFORE anything is written:
    every other file, ARM9/ARM7, overlays, FNT and banner stay byte-identical,
    the FAT changes only for the target file, the header changes only where
    relocation requires it (used-ROM size + header CRC);
  * the file is written to a temporary name and renamed into place, then
    re-read and hashed;
  * every write produces a JSON patch record (hashes, offsets, placement).

Placement:
  * in place when the new data fits before the next file (files start on
    0x200 boundaries; the gap is zero-filled as in the original ROM);
  * otherwise appended after the last file, the download-play signature block
    (0x88 bytes starting with 'ac') is moved after it, and the used-ROM-size
    field and header CRC are updated.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Optional

from . import TOOL_NAME, __version__, lz10
from .rom import NdsRom, RomError, crc16

FILE_ALIGN = 0x200
SIG_SIZE = 0x88


class RomWriteRefused(Exception):
    pass


def _align(x: int, a: int) -> int:
    return (x + a - 1) & ~(a - 1)


def build_replaced(rom: NdsRom, nitro_path: str, new_data: bytes, force_relocate: bool = False):
    """Return (new_rom_bytes, record). Pure function: nothing is written."""
    if not new_data:
        raise RomWriteRefused("refusing to write an empty file")
    fid, old_s, old_e = rom.file_range(nitro_path)
    out = bytearray(rom.data)
    starts_after = sorted(s for s, e in rom.fat if s >= old_e)
    slot_end = starts_after[0] if starts_after else rom.used_rom_size
    header_changes = []
    gap_is_zero = not any(rom.data[old_e:slot_end])
    if len(new_data) <= slot_end - old_s and gap_is_zero and not force_relocate:
        placement = "in_place"
        new_s = old_s
        out[old_s:old_e] = bytes(old_e - old_s)                # old bytes -> zero fill, like original gaps
        out[new_s:new_s + len(new_data)] = new_data
    else:
        placement = "relocated"
        last_end = max(e for s, e in rom.fat)
        if last_end != rom.used_rom_size:
            raise RomWriteRefused("files do not end at the header's used-ROM size; layout not understood")
        sig = rom.data[rom.used_rom_size:rom.used_rom_size + SIG_SIZE]
        has_sig = sig[:2] == b"ac"
        new_s = _align(rom.used_rom_size + (SIG_SIZE if has_sig else 0), FILE_ALIGN)
        new_used = new_s + len(new_data)
        need = new_used + (SIG_SIZE if has_sig else 0)
        if need > len(out):
            raise RomWriteRefused(f"not enough free space in the ROM image ({need:#x} > {len(out):#x})")
        tail = rom.data[rom.used_rom_size:]
        if any(tail[SIG_SIZE if has_sig else 0:]):
            raise RomWriteRefused("space after the used ROM area is not empty; refusing to overwrite it")
        out[old_s:old_e] = bytes(old_e - old_s)                # old slot becomes zero fill
        out[rom.used_rom_size:rom.used_rom_size + (SIG_SIZE if has_sig else 0)] = bytes(SIG_SIZE if has_sig else 0)
        out[new_s:new_used] = new_data
        if has_sig:
            out[new_used:new_used + SIG_SIZE] = sig
        struct.pack_into("<I", out, 0x80, new_used)
        header_changes.append({"field": "used_rom_size", "offset": "0x80",
                               "old": f"0x{rom.used_rom_size:X}", "new": f"0x{new_used:X}"})
    struct.pack_into("<II", out, rom.fat_off + 8 * fid, new_s, new_s + len(new_data))
    if header_changes:
        new_crc = crc16(bytes(out[:0x15E]))
        struct.pack_into("<H", out, 0x15E, new_crc)
        header_changes.append({"field": "header_crc16", "offset": "0x15E",
                               "old": f"0x{rom.header_crc_stored:04X}", "new": f"0x{new_crc:04X}"})
    new = bytes(out)
    record = {
        "tool": f"{TOOL_NAME} {__version__}",
        "file": nitro_path, "file_id": fid, "placement": placement,
        "old": {"start": f"0x{old_s:X}", "end": f"0x{old_e:X}", "size": old_e - old_s,
                "sha256": hashlib.sha256(rom.data[old_s:old_e]).hexdigest()},
        "new": {"start": f"0x{new_s:X}", "end": f"0x{new_s + len(new_data):X}", "size": len(new_data),
                "sha256": hashlib.sha256(new_data).hexdigest()},
        "header_changes": header_changes,
    }
    for side, blob in (("old", rom.data[old_s:old_e]), ("new", new_data)):
        if blob[:1] == b"\x10":
            try:
                dec, _ = lz10.decode(blob)
                record[side]["decoded_sha256"] = hashlib.sha256(dec).hexdigest()
                record[side]["decoded_size"] = len(dec)
            except lz10.LZ10Error as exc:
                if side == "new":
                    raise RomWriteRefused(f"new data starts like LZ10 but does not decode: {exc}")
    verify(rom, new, {fid: new_data})
    return new, record


def verify(old: NdsRom, new_bytes: bytes, targets: dict) -> None:
    """Raise RomWriteRefused unless ONLY the target files {file_id: bytes} (and allowed header fields) changed."""
    new = NdsRom(new_bytes, "verify")
    if len(new_bytes) != len(old.data):
        raise RomWriteRefused("ROM size changed")
    allowed_header = set(range(0x80, 0x84)) | {0x15E, 0x15F}
    for i in range(0x200):
        if old.data[i] != new_bytes[i] and i not in allowed_header:
            raise RomWriteRefused(f"header byte 0x{i:X} changed")
    if new.header_crc_stored != new.header_crc_computed:
        raise RomWriteRefused("header CRC does not match after the edit")
    if new.paths != old.paths:
        raise RomWriteRefused("file names changed")
    for i, ((os_, oe), (ns, ne)) in enumerate(zip(old.fat, new.fat)):
        if i in targets:
            if new_bytes[ns:ne] != targets[i]:
                raise RomWriteRefused(f"target file {i} content mismatch after build")
            continue
        if (os_, oe) != (ns, ne) or old.data[os_:oe] != new_bytes[ns:ne]:
            raise RomWriteRefused(f"file {i} ({old.paths.get(i)}) changed")
    regions = [(old.arm9_off, old.arm9_size, "ARM9"), (old.arm7_off, old.arm7_size, "ARM7"),
               (old.fnt_off, old.fnt_size, "FNT"), (old.ov9_off, old.ov9_size, "overlay table")]
    if old.banner_off:
        regions.append((old.banner_off, 0x840, "banner"))
    for off, size, what in regions:
        if size and old.data[off:off + size] != new_bytes[off:off + size]:
            raise RomWriteRefused(f"{what} changed")
    ranges = sorted(new.fat)
    for (s1, e1), (s2, e2) in zip(ranges, ranges[1:]):
        if s2 < e1:
            raise RomWriteRefused("files overlap after the edit")


def write_rom_copy(input_path: str, output_path: str, nitro_path: str, new_data: bytes,
                   force_relocate: bool = False, record_path: Optional[str] = None) -> dict:
    return write_rom_copy_multi(input_path, output_path, [(nitro_path, new_data, force_relocate)], record_path)


def write_rom_copy_multi(input_path: str, output_path: str, replacements, record_path: Optional[str] = None,
                         note: Optional[str] = None) -> dict:
    """replacements: [(nitro_path, new_bytes, force_relocate), ...] applied in order to a copy."""
    in_abs, out_abs = os.path.abspath(input_path), os.path.abspath(output_path)
    if in_abs == out_abs:
        raise RomWriteRefused("output path is the input ROM; refusing to overwrite the original")
    if os.path.exists(out_abs):
        if os.path.samefile(in_abs, out_abs):
            raise RomWriteRefused("output path is the input ROM; refusing to overwrite the original")
        raise RomWriteRefused(f"output {output_path} already exists; choose a new name")
    if not out_abs.lower().endswith(".nds"):
        raise RomWriteRefused("output name must end in .nds")
    if not replacements:
        raise RomWriteRefused("nothing to replace")
    rom = NdsRom.from_file(in_abs)
    cur = rom
    steps = []
    targets = {}
    for nitro_path, new_data, force_relocate in replacements:
        new_bytes, rec = build_replaced(cur, nitro_path, new_data, force_relocate)
        steps.append(rec)
        targets[rec["file_id"]] = bytes(new_data)
        cur = NdsRom(new_bytes, "step")
    verify(rom, new_bytes, targets)          # final check against the untouched original
    tmp = out_abs + ".partial"
    with open(tmp, "xb") as fh:
        fh.write(new_bytes)
    os.replace(tmp, out_abs)
    with open(out_abs, "rb") as fh:
        written = fh.read()
    if written != new_bytes:
        raise RomWriteRefused("re-read of the written ROM does not match what was built")
    record = {
        "schema": "trcore.rom_patch_record/1",
        "tool": f"{TOOL_NAME} {__version__}",
        "note": note,
        "input_rom": {"name": os.path.basename(in_abs), "sha1": hashlib.sha1(rom.data).hexdigest()},
        "output_rom": {"name": os.path.basename(out_abs), "sha1": hashlib.sha1(written).hexdigest()},
        "output_identical_to_input": written == rom.data,
        "replacements": steps,
    }
    rp = record_path or (os.path.splitext(out_abs)[0] + ".patch.json")
    with open(rp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=1)
        fh.write("\n")
    record["record_path"] = rp
    return record
