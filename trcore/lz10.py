"""Strict, bounded decoder for Nintendo LZ10 (LZ77 type 0x10) streams.

Decoder only. There is deliberately no encoder in this module: re-encoding is a
separate operation that needs its own validation and in-game testing before it
can be trusted.

Stream format (as validated on this corpus):
  byte 0      : type tag 0x10
  bytes 1..3  : decompressed size, 24-bit little-endian
  then blocks : one flag byte, MSB first; bit 0 = literal byte,
                bit 1 = 2-byte back-reference:
                  length = (b1 >> 4) + 3
                  disp   = ((b1 & 0x0F) << 8 | b2) + 1
Back-references may overlap the bytes they produce (length > disp); they are
copied byte by byte so overlapping runs expand correctly.

Every failure raises LZ10Error with a stable ``code`` instead of returning
partial output.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

DEFAULT_MAX_OUTPUT = 16 * 1024 * 1024  # 16 MiB; largest stage file seen is ~0.6 MiB


class LZ10Error(Exception):
    """Decoding failure. ``code`` is one of the CODE_* constants below."""

    def __init__(self, code: str, message: str, offset: Optional[int] = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.offset = offset


CODE_TRUNCATED_HEADER = "truncated_header"
CODE_BAD_TAG = "bad_tag"
CODE_ZERO_SIZE = "zero_size"
CODE_SIZE_CAP = "size_exceeds_cap"
CODE_TRUNCATED_FLAGS = "truncated_flag_byte"
CODE_TRUNCATED_LITERAL = "truncated_literal"
CODE_TRUNCATED_REF = "truncated_backref"
CODE_ILLEGAL_DISP = "illegal_displacement"
CODE_OVERRUN = "backref_overruns_declared_size"


class LZ10Info(NamedTuple):
    declared_size: int
    consumed: int          # compressed bytes consumed, including the 4-byte header
    input_size: int
    trailing_bytes: int    # bytes after the last consumed byte
    trailing_all_zero: bool
    literals: int
    backrefs: int
    overlapping_backrefs: int

    def as_dict(self) -> dict:
        return dict(self._asdict())


def looks_like_lz10(data: bytes) -> bool:
    """Cheap pre-check only (tag byte + non-zero size). Not proof of validity."""
    return len(data) >= 4 and data[0] == 0x10 and (data[1] | data[2] << 8 | data[3] << 16) != 0


def declared_size(data: bytes) -> int:
    if len(data) < 4:
        raise LZ10Error(CODE_TRUNCATED_HEADER, f"need 4 header bytes, have {len(data)}", 0)
    if data[0] != 0x10:
        raise LZ10Error(CODE_BAD_TAG, f"type tag 0x{data[0]:02X} is not 0x10", 0)
    return data[1] | (data[2] << 8) | (data[3] << 16)


def decode(data: bytes, max_output: int = DEFAULT_MAX_OUTPUT):
    """Decode ``data`` and return ``(decoded_bytes, LZ10Info)``.

    Raises LZ10Error on any structural problem. Never returns partial output.
    """
    size = declared_size(data)
    if size == 0:
        # Some tools use size 0 to signal an extended 32-bit size field.
        # That variant has not been observed in this corpus, so it is refused.
        raise LZ10Error(CODE_ZERO_SIZE, "declared size is 0 (extended-header variant unsupported)", 1)
    if size > max_output:
        raise LZ10Error(CODE_SIZE_CAP, f"declared size {size} exceeds cap {max_output}", 1)

    src = data
    n = len(src)
    out = bytearray()
    i = 4
    literals = backrefs = overlapping = 0
    while len(out) < size:
        if i >= n:
            raise LZ10Error(CODE_TRUNCATED_FLAGS, f"flag byte expected at {i}; output {len(out)}/{size}", i)
        flags = src[i]
        i += 1
        mask = 0x80
        while mask and len(out) < size:
            if flags & mask:
                if i + 1 >= n:
                    raise LZ10Error(CODE_TRUNCATED_REF, f"back-reference needs 2 bytes at {i}", i)
                b1 = src[i]
                b2 = src[i + 1]
                length = (b1 >> 4) + 3
                disp = (((b1 & 0x0F) << 8) | b2) + 1
                cur = len(out)
                if disp > cur:
                    raise LZ10Error(CODE_ILLEGAL_DISP,
                                    f"displacement {disp} reaches before output start (output {cur})", i)
                if cur + length > size:
                    raise LZ10Error(CODE_OVERRUN,
                                    f"back-reference of {length} at output {cur} exceeds size {size}", i)
                start = cur - disp
                if length <= disp:
                    out += out[start:start + length]
                else:
                    overlapping += 1
                    for k in range(length):
                        out.append(out[start + k])
                backrefs += 1
                i += 2
            else:
                if i >= n:
                    raise LZ10Error(CODE_TRUNCATED_LITERAL, f"literal expected at {i}", i)
                out.append(src[i])
                literals += 1
                i += 1
            mask >>= 1
    trailing = src[i:]
    info = LZ10Info(
        declared_size=size,
        consumed=i,
        input_size=n,
        trailing_bytes=len(trailing),
        trailing_all_zero=not any(trailing),
        literals=literals,
        backrefs=backrefs,
        overlapping_backrefs=overlapping,
    )
    return bytes(out), info
