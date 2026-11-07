"""Fabricated minimal NSBMD (BMD0) files for tests. No game data.

build_nsbmd() makes one model with two nodes:
  node 0 'root': translation (1, 0, 0)
  node 1 'part': pivot-compressed rotation rows [[0,0,1],[0,1,0],[-1,0,0]]
posScale 2. SBC: NODEDESC 0, NODE 0 visible, SHP 0 (a triangle), NODEDESC 1 -> stack 1, SHP 1 (a quad).
"""
import struct

FX = 4096


def make_dict(names, entries, unit=4):
    """NNS resource dictionary: header, (n + 1) zero tree nodes, entry block, 16-byte names."""
    n = len(entries)
    ofs_entry = 8 + 4 * (n + 1)
    body = struct.pack("<HH", unit, 4 + unit * n) + b"".join(entries) + b"".join(
        nm.encode().ljust(16, b"\0") for nm in names)
    return struct.pack("<BBHHH", 0, n, ofs_entry + len(body), 8, ofs_entry) + bytes(4 * (n + 1)) + body


def _cmds(*groups):
    """groups: [(op, [params...]), ...] packed four ops per word."""
    out = bytearray()
    for i in range(0, len(groups), 4):
        chunk = groups[i:i + 4]
        ops = [c[0] for c in chunk] + [0] * (4 - len(chunk))
        out += bytes(ops)
        for _op, params in chunk:
            for p in params:
                out += struct.pack("<I", p & 0xFFFFFFFF)
    return bytes(out)


def s16pair(a, b):
    return (int(round(a * FX)) & 0xFFFF) | ((int(round(b * FX)) & 0xFFFF) << 16)


def v10(x, y, z):
    return ((int(round(x * 64)) & 0x3FF) | ((int(round(y * 64)) & 0x3FF) << 10)
            | ((int(round(z * 64)) & 0x3FF) << 20))


def d10(x, y, z):
    return ((int(round(x * FX)) & 0x3FF) | ((int(round(y * FX)) & 0x3FF) << 10)
            | ((int(round(z * FX)) & 0x3FF) << 20))


TRI_DL = _cmds((0x40, [0]), (0x23, [s16pair(0, 0), 0]), (0x26, [s16pair(0.5, 0.25)]),
               (0x28, [d10(-0.03125, 0.0625, 0)]), (0x41, []))
QUAD_DL = _cmds((0x40, [1]), (0x24, [v10(1, 0, 0)]), (0x24, [v10(0, 0, 1)]), (0x24, [v10(-1, 0, 0)]),
                (0x24, [v10(0, 0, -1)]), (0x41, []))
SBC = bytes([0x06, 0, 0, 0, 0x02, 0, 1, 0x05, 0, 0x26, 1, 0, 0, 1, 0x05, 1, 0x01])

EXPECTED_TRIANGLES = [
    ((1.0, 0.0, 0.0), (2.0, 0.0, 0.5), (1.9375, 0.125, 0.5)),
    ((1.0, 0.0, 2.0), (-1.0, 0.0, 0.0), (1.0, 0.0, -2.0)),
    ((1.0, 0.0, 2.0), (1.0, 0.0, -2.0), (3.0, 0.0, 0.0)),
]


def build_nsbmd(sbc=SBC, tri_dl=TRI_DL, quad_dl=QUAD_DL, pos_scale=2.0, header_counts=(1, 1)):
    # nodes
    node0 = struct.pack("<Hh3i", 0x0006, 0, FX, 0, 0)                      # rot zero, scale one, T
    flag1 = 0x0001 | 0x0004 | 0x0008 | (4 << 4) | (2 << 8)                 # T zero, scale one, pivot 4, c=-b
    node1 = struct.pack("<Hhhh", flag1, 0, 0, FX)                          # a = 0, b = 1
    nd_names = ["root", "part"]
    nd_head_len = len(make_dict(nd_names, [bytes(4)] * 2))
    n0_off = nd_head_len
    n1_off = n0_off + len(node0)
    node_block = make_dict(nd_names, [struct.pack("<I", n0_off), struct.pack("<I", n1_off)]) + node0 + node1
    info_end = 0x40
    ofs_sbc = info_end + len(node_block)
    ofs_mat = ofs_sbc + len(sbc)
    ofs_mat += (-ofs_mat) % 4
    mat_block = struct.pack("<HH", 0, 0) + make_dict([], [])
    ofs_shp = ofs_mat + len(mat_block)
    sh_names = ["tri", "quad"]
    sh_head = len(make_dict(sh_names, [bytes(4)] * 2))
    sd0 = sh_head
    sd1 = sd0 + 16
    dl0 = sd1 + 16
    dl1 = dl0 + len(tri_dl)
    shp_block = make_dict(sh_names, [struct.pack("<I", sd0), struct.pack("<I", sd1)])
    shp_block += struct.pack("<HHIII", 0, 16, 0, dl0 - sd0, len(tri_dl))
    shp_block += struct.pack("<HHIII", 0, 16, 0, dl1 - sd1, len(quad_dl))
    shp_block += tri_dl + quad_dl
    size = ofs_shp + len(shp_block)
    model = bytearray(size)
    struct.pack_into("<5I", model, 0, size, ofs_sbc, ofs_mat, ofs_shp, size)
    struct.pack_into("<8B", model, 0x14, 0, 0, 0, 2, 0, 2, 2, 0)
    struct.pack_into("<ii", model, 0x1C, int(pos_scale * FX), int(FX / pos_scale))
    struct.pack_into("<4H", model, 0x24, 7, sum(header_counts), header_counts[0], header_counts[1])
    struct.pack_into("<ii", model, 0x38, FX, FX)
    model[info_end:info_end + len(node_block)] = node_block
    model[ofs_sbc:ofs_sbc + len(sbc)] = sbc
    model[ofs_mat:ofs_mat + len(mat_block)] = mat_block
    model[ofs_shp:ofs_shp + len(shp_block)] = shp_block
    mdl_dict = make_dict(["test_model"], [bytes(4)])
    model_off = 8 + len(mdl_dict)
    mdl_dict = make_dict(["test_model"], [struct.pack("<I", model_off)])
    mdl0 = b"MDL0" + struct.pack("<I", 8 + len(mdl_dict) + len(model)) + mdl_dict + bytes(model)
    total = 0x14 + len(mdl0)
    return b"BMD0" + struct.pack("<HHIHHI", 0xFEFF, 2, total, 16, 1, 0x14) + mdl0
