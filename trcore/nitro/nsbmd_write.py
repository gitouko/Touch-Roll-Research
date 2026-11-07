"""Add polygons to a stage model (NSBMD) without moving anything that exists.

How (spec §15; checked by re-reading the result with trcore.nitro.nsbmd):
  * the polygons are drawn by an EXISTING shape, so they use that shape's material and the stage's own
    texture (the .nsbtx is not touched) and no dictionary or render command (SBC) changes;
  * the shape's display list is copied to the end of the model with the new GX commands after it
    (BEGIN_VTXS quads/triangles, and per polygon NORMAL, then TEXCOORD + VTX_16 per corner); the shape's
    display-list offset and size, the model size and the block/file sizes are updated, and the model's
    counters and bounding box are widened. The old display list stays in place, unreferenced;
  * corners are given in stage coordinates and stored divided by the model's posScale (4.12 fixed point);
    the shape must be drawn without a node transform (checked: the new polygons must read back at the
    coordinates asked for);
  * texture coordinates continue the shape's own texture mapping: the affine (x, z) -> (s, t) map of the
    nearest upward-facing polygon of the same shape, used along walls too (same texel density). Each
    polygon is shifted by a whole number of 1024-texel periods so the values stay small (textures are
    at most 1024 texels wide and repeat, so this does not change the picture).
Polygons are drawn from the side of (P1 - P0) x (P2 - P0) (front faces; the stage materials cull back
faces), with corners in order around the outline.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Dict, List, Optional, Sequence, Tuple

from ..binreader import BinReader
from .nsbmd import FX, GX_PARAMS, NitroError, Nsbmd, model_geometry

Vec = Tuple[float, float, float]
VTX16_LIMIT = 0x7FFF
TEX_PERIOD = 1024.0          # texels; a multiple of every DS texture size
POS_TOLERANCE_UNITS = 2      # in 1/4096 of model units (before posScale)


class ModelEditRefused(Exception):
    pass


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _s10(v):
    v &= 0x3FF
    return v - 0x400 if v & 0x200 else v


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    ln = math.sqrt(sum(x * x for x in a))
    return tuple(x / ln for x in a) if ln > 1e-12 else None


def _newell(poly):
    n = [0.0, 0.0, 0.0]
    for i in range(len(poly)):
        c = _cross(poly[i], poly[(i + 1) % len(poly)])
        n = [n[k] + c[k] for k in range(3)]
    return tuple(n)


def shape_polygons_with_texcoords(data: bytes, model, shape_index: int) -> List[List[Tuple[Vec, Tuple[float, float]]]]:
    """Polygons of one shape as drawn, each corner with (position x posScale, texcoord in texels).
    Positions ignore node transforms (callers check that the shape has none)."""
    r = BinReader(data)
    sh = model.shapes[shape_index]
    p, end = sh["dl_offset"], sh["dl_offset"] + sh["dl_size"]
    ps = model.pos_scale
    tc = (0.0, 0.0)
    x = y = z = 0.0
    prim, strip, polys = None, [], []
    while p + 4 <= end:
        packed = r.u32(p)
        p += 4
        for k in range(4):
            op = (packed >> (8 * k)) & 0xFF
            n = GX_PARAMS.get(op)
            if n is None:
                raise ModelEditRefused(f"unknown GX command 0x{op:02X} in shape {sh['name']}")
            if p + 4 * n > end:
                if op == 0:
                    continue
                raise ModelEditRefused(f"GX command 0x{op:02X} runs past the display list")
            a = [r.u32(p + 4 * i) for i in range(n)]
            p += 4 * n
            if op == 0x40:
                prim, strip = a[0] & 3, []
                continue
            if op == 0x41:
                strip = []
                continue
            if op == 0x22:
                tc = (_s16(a[0] & 0xFFFF) / 16.0, _s16(a[0] >> 16) / 16.0)
                continue
            if op == 0x23:
                x, y, z = _s16(a[0] & 0xFFFF) / FX, _s16(a[0] >> 16) / FX, _s16(a[1] & 0xFFFF) / FX
            elif op == 0x24:
                x, y, z = _s10(a[0]) / 64.0, _s10(a[0] >> 10) / 64.0, _s10(a[0] >> 20) / 64.0
            elif op == 0x25:
                x, y = _s16(a[0] & 0xFFFF) / FX, _s16(a[0] >> 16) / FX
            elif op == 0x26:
                x, z = _s16(a[0] & 0xFFFF) / FX, _s16(a[0] >> 16) / FX
            elif op == 0x27:
                y, z = _s16(a[0] & 0xFFFF) / FX, _s16(a[0] >> 16) / FX
            elif op == 0x28:
                x += _s10(a[0]) / FX / 8
                y += _s10(a[0] >> 10) / FX / 8
                z += _s10(a[0] >> 20) / FX / 8
            else:
                continue
            strip.append(((x * ps, y * ps, z * ps), tc))
            v = strip
            if prim == 0 and len(v) == 3:
                polys.append(list(v))
                strip = []
            elif prim == 1 and len(v) == 4:
                polys.append(list(v))
                strip = []
            elif prim == 2 and len(v) >= 3:
                m = len(v)
                polys.append([v[m - 3], v[m - 2], v[m - 1]] if m % 2 else [v[m - 2], v[m - 3], v[m - 1]])
            elif prim == 3 and len(v) >= 4 and len(v) % 2 == 0:
                m = len(v)
                polys.append([v[m - 4], v[m - 3], v[m - 1], v[m - 2]])
    return polys


def texture_map_near(polys, centre: Vec) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Affine map (x, z, 1) -> s and -> t from the nearest upward-facing polygon of the shape."""
    best = None
    for poly in polys:
        pos = [c[0] for c in poly]
        n = _norm(_newell(pos))
        if not n or n[1] < 0.95:
            continue
        cx = sum(p[0] for p in pos) / len(pos)
        cz = sum(p[2] for p in pos) / len(pos)
        d = (cx - centre[0]) ** 2 + (cz - centre[2]) ** 2
        if best is None or d < best[0]:
            best = (d, poly)
    if best is None:
        return None
    poly = best[1]
    (p0, t0), (p1, t1), (p2, t2) = poly[0], poly[1], poly[2]
    # solve [x z 1] * [a b c]^T = s for the three corners (and t)
    rows = [(p0[0], p0[2], 1.0), (p1[0], p1[2], 1.0), (p2[0], p2[2], 1.0)]
    det = (rows[0][0] * (rows[1][1] - rows[2][1]) - rows[0][1] * (rows[1][0] - rows[2][0])
           + (rows[1][0] * rows[2][1] - rows[2][0] * rows[1][1]))
    if abs(det) < 1e-9:
        return None

    def solve(vals):
        out = []
        for col in range(3):
            m = [list(r) for r in rows]
            for i in range(3):
                m[i][col] = vals[i]
            d = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                 + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
            out.append(d / det)
        return tuple(out)

    return solve([t0[0], t1[0], t2[0]]), solve([t0[1], t1[1], t2[1]])


def texcoords_for(poly: Sequence[Vec], tmap) -> List[Tuple[float, float]]:
    (sa, sb, sc), (ta, tb, tc) = tmap
    n = _norm(_newell(poly)) or (0.0, 1.0, 0.0)
    if abs(n[1]) >= 0.7:
        flat = [(p[0], p[2]) for p in poly]
    else:   # wall: run the floor mapping along the wall (horizontal) and down its height
        h = _norm((-n[2], 0.0, n[0])) or (1.0, 0.0, 0.0)
        m = _norm((n[0], 0.0, n[2])) or (0.0, 0.0, 1.0)
        flat = []
        for p in poly:
            u = p[0] * h[0] + p[2] * h[2]
            flat.append((h[0] * u - m[0] * p[1], h[2] * u - m[2] * p[1]))
    st = [(sa * x + sb * z + sc, ta * x + tb * z + tc) for x, z in flat]
    ms = sum(s for s, _ in st) / len(st)
    mt = sum(t for _, t in st) / len(st)
    ks, kt = TEX_PERIOD * round(ms / TEX_PERIOD), TEX_PERIOD * round(mt / TEX_PERIOD)
    return [(s - ks, t - kt) for s, t in st]


def _pack(cmds: List[Tuple[int, List[int]]]) -> bytes:
    out = bytearray()
    for i in range(0, len(cmds), 4):
        chunk = cmds[i:i + 4]
        out += bytes([c[0] for c in chunk] + [0] * (4 - len(chunk)))
        for _op, params in chunk:
            for prm in params:
                out += struct.pack("<I", prm & 0xFFFFFFFF)
    return bytes(out)


def _normal10(n: Vec) -> int:
    def f(v):
        return max(-512, min(511, int(round(v * 512)))) & 0x3FF
    return f(n[0]) | (f(n[1]) << 10) | (f(n[2]) << 20)


def _texcoord(s: float, t: float) -> int:
    si, ti = int(round(s * 16)), int(round(t * 16))
    if not (-0x8000 <= si <= 0x7FFF and -0x8000 <= ti <= 0x7FFF):
        raise ModelEditRefused("texture coordinate out of range")
    return (si & 0xFFFF) | ((ti & 0xFFFF) << 16)


def _vtx16(p: Vec, pos_scale: float) -> Tuple[List[int], Vec]:
    raw = [int(round(c / pos_scale * FX)) for c in p]
    if any(abs(v) > VTX16_LIMIT for v in raw):
        raise ModelEditRefused(f"corner {list(p)} is too far out for this model (|coordinate| must stay "
                               f"below {8 * pos_scale:g})")
    return [(raw[0] & 0xFFFF) | ((raw[1] & 0xFFFF) << 16), raw[2] & 0xFFFF], tuple(v / FX * pos_scale for v in raw)


def append_polygons(data: bytes, shape: str, polygons: Sequence[Sequence[Sequence[float]]],
                    name: str = "", model_index: int = 0) -> Tuple[bytes, dict]:
    """Return (new NSBMD bytes, report). Raises ModelEditRefused if anything is off."""
    try:
        nsb = Nsbmd(data, name)
    except NitroError as exc:
        raise ModelEditRefused(f"model unreadable: {exc}") from None
    if len(nsb.models) != 1 or nsb.has_textures:
        raise ModelEditRefused("only single-model files without embedded textures are supported")
    m = nsb.models[model_index]
    if m.base + m.size != len(data):
        raise ModelEditRefused("the model does not end the file; cannot append safely")
    names = [s["name"] for s in m.shapes]
    if shape not in names:
        raise ModelEditRefused(f"shape {shape!r} not in the model (shapes: {names})")
    si = names.index(shape)
    sh = m.shapes[si]
    if not polygons:
        raise ModelEditRefused("no polygons given")
    polys = []
    for i, poly in enumerate(polygons):
        pts = [tuple(float(c) for c in p) for p in poly]
        if len(pts) not in (3, 4):
            raise ModelEditRefused(f"polygon {i}: give 3 or 4 corners")
        n = _norm(_newell(pts))
        if n is None:
            raise ModelEditRefused(f"polygon {i} has no area")
        polys.append((pts, n))
    old_geo = model_geometry(nsb)
    existing = shape_polygons_with_texcoords(data, m, si)
    # build the GX commands
    cmds: List[Tuple[int, List[int]]] = []
    intended = []
    counts = {"quads": 0, "triangles": 0, "vertices": 0}
    for want in (4, 3):
        group = [(pts, n) for pts, n in polys if len(pts) == want]
        if not group:
            continue
        cmds.append((0x40, [1 if want == 4 else 0]))
        for pts, n in group:
            centre = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
            tmap = texture_map_near(existing, centre)
            if tmap is None:
                raise ModelEditRefused(f"shape {shape!r} has no upward-facing polygon to take a texture mapping from")
            tcs = texcoords_for(pts, tmap)
            cmds.append((0x21, [_normal10(n)]))
            stored = []
            for p, (s, t) in zip(pts, tcs):
                words, back = _vtx16(p, m.pos_scale)
                cmds.append((0x22, [_texcoord(s, t)]))
                cmds.append((0x23, words))
                stored.append(back)
            intended.append(stored)
            counts["quads" if want == 4 else "triangles"] += 1
            counts["vertices"] += want
        cmds.append((0x41, []))
    old_dl = data[sh["dl_offset"]:sh["dl_offset"] + sh["dl_size"]]
    new_dl = old_dl + _pack(cmds)
    out = bytearray(data)
    out += bytes((-len(out)) % 4)
    dl_at = len(out)
    out += new_dl
    delta = len(out) - len(data)
    allowed = set()

    def put(fmt, off, *vals):
        struct.pack_into(fmt, out, off, *vals)
        allowed.update(range(off, off + struct.calcsize(fmt)))

    put("<II", sh["offset"] + 8, dl_at - sh["offset"], len(new_dl))
    old_size = m.size
    put("<I", m.base, old_size + delta)
    if m.ofs_evp == old_size:
        put("<I", m.base + 0x10, old_size + delta)
    mdl0 = struct.unpack_from("<I", data, 0x10)[0]
    put("<I", mdl0 + 4, struct.unpack_from("<I", data, mdl0 + 4)[0] + delta)
    put("<I", 0x08, len(out))
    info = m.base + 0x14
    nv, npoly, ntri, nquad = struct.unpack_from("<4H", data, info + 0x10)
    put("<4H", info + 0x10, min(0xFFFF, nv + counts["vertices"]), min(0xFFFF, npoly + counts["quads"] + counts["triangles"]),
        min(0xFFFF, ntri + counts["triangles"]), min(0xFFFF, nquad + counts["quads"]))
    # bounding box (x, y, z = min x, min y, max z; w, h, d) in units of boxPosScale
    bs = m.box_pos_scale
    bx = struct.unpack_from("<6h", data, info + 0x18)
    x0, y0, z1 = bx[0] / FX * bs, bx[1] / FX * bs, bx[2] / FX * bs
    x1, y1, z0 = x0 + bx[3] / FX * bs, y0 + bx[4] / FX * bs, z1 - bx[5] / FX * bs
    outside = False
    for pts in intended:
        for p in pts:
            if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and z0 <= p[2] <= z1):
                outside = True
            x0, x1, y0, y1, z0, z1 = min(x0, p[0]), max(x1, p[0]), min(y0, p[1]), max(y1, p[1]), min(z0, p[2]), max(z1, p[2])

    def b16(v, up):
        q = v / bs * FX
        q = math.ceil(q) if up else math.floor(q)
        if not -0x8000 <= q <= 0x7FFF:
            raise ModelEditRefused("bounding box out of range")
        return q

    box = bx
    if outside:
        box = (b16(x0, False), b16(y0, False), b16(z1, True), b16(x1 - x0, True), b16(y1 - y0, True), b16(z1 - z0, True))
    if box != bx:
        put("<6h", info + 0x18, *box)
    new = bytes(out)
    report = _verify(data, new, nsb, si, old_geo, existing, intended, allowed, name)
    report.update({"shape": shape, "material_note": "drawn with the shape's own material",
                   "polygons_added": len(intended), **counts, "display_list_offset": f"0x{dl_at:X}",
                   "display_list_size_before": len(old_dl), "display_list_size_after": len(new_dl),
                   "size_before": len(data), "size_after": len(new),
                   "sha256_before": hashlib.sha256(data).hexdigest(), "sha256_after": hashlib.sha256(new).hexdigest(),
                   "bounding_box_changed": box != bx})
    return new, report


def _verify(old: bytes, new: bytes, nsb_old, si, old_geo, existing, intended, allowed, name) -> dict:
    stray = [i for i in range(len(old)) if old[i] != new[i] and i not in allowed]
    if stray:
        raise ModelEditRefused(f"internal: bytes outside the allowed fields changed (first at 0x{stray[0]:X})")
    try:
        nsb = Nsbmd(new, name)
        geo = model_geometry(nsb)
    except NitroError as exc:
        raise ModelEditRefused(f"edited model does not read back: {exc}") from None
    m_old, m = nsb_old.models[0], nsb.models[0]
    if [s["name"] for s in m.shapes] != [s["name"] for s in m_old.shapes] or m.materials != m_old.materials:
        raise ModelEditRefused("internal: shapes or materials changed")
    if m.sbc != m_old.sbc or len(m.nodes) != len(m_old.nodes):
        raise ModelEditRefused("internal: render commands or nodes changed")
    old_polys = [p for p in old_geo["polygons"]]
    new_polys = [p for p in geo["polygons"]]
    others_old = [p for p in old_polys if p[1] != si]
    others_new = [p for p in new_polys if p[1] != si]
    if others_old != others_new:
        raise ModelEditRefused("internal: other shapes' polygons changed")
    mine_old = [p for p in old_polys if p[1] == si]
    mine_new = [p for p in new_polys if p[1] == si]
    if mine_new[:len(mine_old)] != mine_old or len(mine_new) != len(mine_old) + len(intended):
        raise ModelEditRefused("internal: the shape's own polygons changed")
    tol = POS_TOLERANCE_UNITS / FX * m.pos_scale
    worst = 0.0
    for (verts, _shape, _node), want in zip(mine_new[len(mine_old):], intended):
        if len(verts) != len(want):
            raise ModelEditRefused("internal: a new polygon reads back with a different corner count")
        for a, b in zip(verts, want):
            d = max(abs(x - y) for x, y in zip(a, b))
            worst = max(worst, d)
            if d > tol:
                raise ModelEditRefused("a new polygon reads back elsewhere than asked (the shape is moved by a "
                                       "node transform?)")
    again = shape_polygons_with_texcoords(new, m, si)
    if again[:len(existing)] != existing:
        raise ModelEditRefused("internal: the shape's texture coordinates changed")
    return {"readback_max_error": worst, "triangles_after": len(geo["triangles"])}
