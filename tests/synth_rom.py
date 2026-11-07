"""Fabricated minimal Nintendo DS ROM images for tests (no game data).

Layout: header (0x200) | ARM9 | ARM7 | FNT | FAT | files (0x200-aligned,
zero gaps) | 0x88-byte 'ac' signature at the used-ROM size | zero padding.
"""
import struct

from trcore.rom import crc16


def _align(x, a=0x200):
    return (x + a - 1) & ~(a - 1)


def _parent(d):
    return d.rsplit("/", 1)[0] if "/" in d else ""


def build_rom(files, size=0x40000, game_code=b"TEST", signature=True):
    """files: list of (dir, name, bytes); dir may be '' or nested like 'model/stage'."""
    dirs = set()
    for d, _, _ in files:
        parts = d.split("/") if d else []
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    dirs = [""] + sorted(dirs)
    index = {d: i for i, d in enumerate(dirs)}
    files_in = {d: [(n, b) for dd, n, b in files if dd == d] for d in dirs}
    ordered = [x for d in dirs for x in files_in[d]]
    subs, first_ids, fid = [], [], 0
    for d in dirs:
        sub = bytearray()
        for n, _ in files_in[d]:
            sub += bytes([len(n)]) + n.encode()
        for c in dirs:
            if c and _parent(c) == d:
                name = c.rsplit("/", 1)[-1]
                sub += bytes([0x80 | len(name)]) + name.encode() + struct.pack("<H", 0xF000 + index[c])
        sub += b"\0"
        subs.append(sub)
        first_ids.append(fid)
        fid += len(files_in[d])
    ndirs = len(dirs)
    main = bytearray()
    off = 8 * ndirs
    for i, sub in enumerate(subs):
        d = dirs[i]
        parent = ndirs if i == 0 else 0xF000 + index[_parent(d)]
        main += struct.pack("<IHH", off, first_ids[i], parent)
        off += len(sub)
    fnt = bytes(main) + b"".join(bytes(s) for s in subs)
    arm9 = bytes(range(256)) * 4
    arm7 = bytes(256)
    rom = bytearray(size)
    pos = 0x200
    arm9_off = pos; rom[pos:pos + len(arm9)] = arm9; pos = _align(pos + len(arm9))
    arm7_off = pos; rom[pos:pos + len(arm7)] = arm7; pos = _align(pos + len(arm7))
    fnt_off = pos; rom[pos:pos + len(fnt)] = fnt; pos = _align(pos + len(fnt))
    fat_off = pos; fat_size = 8 * len(ordered); pos = _align(pos + fat_size)
    fat = []
    for _, data in ordered:
        rom[pos:pos + len(data)] = data
        fat.append((pos, pos + len(data)))
        pos = _align(pos + len(data))
    used = fat[-1][1]
    for i, (s, e) in enumerate(fat):
        struct.pack_into("<II", rom, fat_off + 8 * i, s, e)
    rom[0:12] = b"TRCORETEST\0\0"
    rom[0x0C:0x10] = game_code
    rom[0x10:0x12] = b"00"
    struct.pack_into("<16I", rom, 0x20, arm9_off, 0x02000000, 0x02000000, len(arm9),
                     arm7_off, 0x02380000, 0x02380000, len(arm7),
                     fnt_off, len(fnt), fat_off, fat_size, 0, 0, 0, 0)
    struct.pack_into("<I", rom, 0x80, used)
    if signature:
        rom[used:used + 0x88] = b"ac" + bytes(range(0x86))
    struct.pack_into("<H", rom, 0x15E, crc16(bytes(rom[:0x15E])))
    return bytes(rom)
