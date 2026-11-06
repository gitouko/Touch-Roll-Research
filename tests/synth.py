"""Synthetic test fixtures. These bytes are fabricated for tests, not game data.

``build_stage`` assembles a small LCTS stream that follows the candidate
layout in trcore/stc/layout.py, so parser behaviour can be tested without
copyrighted files. ``lz10_literal_encode`` wraps bytes in a valid LZ10 stream
made only of literals (test helper, not a general encoder).
"""
from __future__ import annotations

import struct

Q = 4096


def q12(v: float) -> int:
    return int(round(v * Q))


def lz10_literal_encode(data: bytes) -> bytes:
    n = len(data)
    out = bytearray([0x10, n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF])
    for i in range(0, n, 8):
        out.append(0x00)
        out += data[i:i + 8]
    return bytes(out)


def _align(x: int, a: int = 0x20) -> int:
    return (x + a - 1) & ~(a - 1)


IDENTITY = (1, 0, 0, 0, 1, 0, 0, 0, 1)


def build_stage(goals=((0, IDENTITY, (0, 0, -10)),), bananas=((1, 0.5, 2, 0), (-1, 0.5, 2, 1)),
                groups=("START01",), goal_owner=0, banana_owner=0, unreferenced_bananas=0,
                variant="common", u32_08=0) -> bytes:
    """goals: (word30, 3x3 tuple, xyz); bananas: (x, y, z, word0C).

    goal_owner / banana_owner: index of the group whose slice references the
    objects (other groups get empty slices). ``unreferenced_bananas`` of the
    bananas are left out of every slice. variant 'no_start_slot' omits the
    start pair and stores totals at 0x3C/0x40/0x44.
    """
    G = len(groups)
    buf = bytearray(0x4000)
    pa = 0x100
    pc = _align(pa + len(goals) * 0x34)
    t8c = _align(pc + len(bananas) * 0x10)
    t8c_n = 2
    cell = _align(t8c + t8c_n * 0x34)
    nx, nz = 2, 3
    F = _align(cell + nx * nz * 8)
    strings_at = F + G * 0xCC
    names = {}
    cur = strings_at
    for nm in groups:
        names[nm] = cur
        buf[cur:cur + len(nm)] = nm.encode("ascii")
        cur += len(nm) + 1
    total_len = _align(cur, 0x10)

    buf[0:4] = b"LCTS"
    struct.pack_into("<IIIII", buf, 4, 0x12, u32_08, 0, 0x3E80, G)
    struct.pack_into("<I", buf, 0x18, F)
    struct.pack_into("<6i", buf, 0x1C, q12(-10), q12(-1), q12(-12), q12(10), q12(1), q12(12))
    struct.pack_into("<I", buf, 0x34, G)
    totals = (len(goals), 0, len(bananas))
    if variant == "common":
        struct.pack_into("<II", buf, 0x38, 1, 0xE4)
        struct.pack_into("<III", buf, 0x40, *totals)
        struct.pack_into("<6i", buf, 0x4C, 0, 0, 0, Q, Q, Q)
        struct.pack_into("<3iI", buf, 0xE4, q12(0), q12(0), q12(10), 0x4000)
    elif variant == "no_start_slot":
        struct.pack_into("<I", buf, 0x38, 0x12345)  # odd, not a valid offset
        struct.pack_into("<III", buf, 0x3C, *totals)
    else:
        raise ValueError(variant)
    for i, (w30, m, t) in enumerate(goals):
        o = pa + i * 0x34
        struct.pack_into("<9i", buf, o, *(q12(v) for v in m))
        struct.pack_into("<3iI", buf, o + 0x24, *(q12(v) for v in t), w30)
    for i, (x, y, z, w) in enumerate(bananas):
        struct.pack_into("<3iI", buf, pc + i * 0x10, q12(x), q12(y), q12(z), w)
    for i in range(t8c_n):
        struct.pack_into("<3i", buf, t8c + i * 0x34, q12(i), q12(0.5), q12(-i))
    for i in range(nx * nz):
        struct.pack_into("<II", buf, cell + i * 8, 0xF, t8c)
    referenced_bananas = len(bananas) - unreferenced_bananas
    for k, nm in enumerate(groups):
        D = F + k * 0xCC
        struct.pack_into("<IIII", buf, D, 0, names[nm], names[nm], 0)
        struct.pack_into("<9i", buf, D + 0x10, *(q12(v) for v in IDENTITY))
        struct.pack_into("<3i", buf, D + 0x34, 0, 0, q12(-5) if k == 0 else 0)
        struct.pack_into("<HH4iI", buf, D + 0x40, nx, nz, q12(-10.5), q12(-12.5), q12(10), q12(10), cell if k == 0 else 0)
        if k == 0:
            struct.pack_into("<II", buf, D + 0x8C, t8c_n, t8c)
        gcount = len(goals) if k == goal_owner else 0
        ccount = referenced_bananas if k == banana_owner else 0
        # empty slices point at the pool head (as observed), owners point at their records
        struct.pack_into("<II", buf, D + 0x94, gcount, pa)
        struct.pack_into("<II", buf, D + 0x9C, 0, 0)
        struct.pack_into("<II", buf, D + 0xA4, ccount, pc)
    # with several groups, an owner after group 0 must still start at the pool head
    return bytes(buf[:total_len])
