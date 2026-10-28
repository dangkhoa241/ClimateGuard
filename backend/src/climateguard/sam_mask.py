"""Decode SAM 3.1 `one_bit` mask payloads to a 0/1 raster.

A port of the one_bit codec in Meta's `meta-sam-parser` 0.1.0 (`_mask_codec.py`), cut down to what
ClimateGuard needs. Distributed under the SAM License (LICENSE-SAM in the repo root). The format isn't
documented byte by byte (https://dev.meta.ai/docs/sam/reading-segmentation), so this follows the reference.

Wire format: `!` + base85 over an alphabet of the printable ASCII characters minus `"\\,;<>|` (5-digit
length prefix, then 5 digits per 4 bytes), and the bytes are a binary range coder with a 12-pixel context
model, row-major. ClimateGuard requests one_bit (not the default lossless `~`): smaller payloads and a much
simpler decoder. The encoder is here only so tests can round-trip.
"""
from array import array

_EXCLUDED = frozenset('"\\,;<>|')
_ALPHABET = "".join(c for c in map(chr, range(0x21, 0x7F)) if c not in _EXCLUDED)
_VALUES = {c: i for i, c in enumerate(_ALPHABET)}
_PREFIX = 5
_M32 = 0xFFFFFFFF
_TOP, _BOTTOM = 1 << 24, 1 << 16
_INCREMENT, _COUNT_LIMIT, _CONTEXTS, _PAD = 14, 4096, 1 << 12, 2


class MaskError(ValueError):
    pass


def _digit(c: str) -> int:
    v = _VALUES.get(c)
    if v is None:
        raise MaskError("invalid character in mask payload")
    return v


def b85_encode(data: bytes) -> str:
    n = len(data)
    out, rem = [], n
    for _ in range(_PREFIX):
        out.append(_ALPHABET[rem % 85])
        rem //= 85
    out.reverse()
    for off in range(0, n - n % 4, 4):
        v = int.from_bytes(data[off:off + 4], "big")
        digits = []
        for _ in range(5):
            digits.append(v % 85)
            v //= 85
        out += [_ALPHABET[d] for d in reversed(digits)]
    tail = n % 4
    if tail:
        v = int.from_bytes(data[n - tail:] + b"\0" * (4 - tail), "big")
        digits = []
        for _ in range(5):
            digits.append(v % 85)
            v //= 85
        out += [_ALPHABET[d] for d in reversed(digits)][:tail + 1]
    return "".join(out)


def b85_decode(payload: str) -> bytes:
    if len(payload) < _PREFIX:
        raise MaskError("mask payload is missing its length prefix")
    n = 0
    for c in payload[:_PREFIX]:
        n = n * 85 + _digit(c)
    tail = n % 4
    if len(payload) != _PREFIX + (n // 4) * 5 + (tail + 1 if tail else 0):
        raise MaskError("mask payload length does not match its prefix")
    out, src = bytearray(), _PREFIX
    for _ in range(n // 4):
        v = 0
        for c in payload[src:src + 5]:
            v = v * 85 + _digit(c)
        if v > _M32:
            raise MaskError("mask payload group out of range")
        out += v.to_bytes(4, "big")
        src += 5
    if tail:
        v = 0
        for i in range(5):
            v = v * 85 + (_digit(payload[src + i]) if i < tail + 1 else 84)
        out += (v & _M32).to_bytes(4, "big")[:tail]
    return bytes(out)


def _context(p: bytearray, pos: int, prior: int, earlier: int) -> int:
    return (p[pos - 1] | (p[pos - 2] << 1) | (p[prior - 2] << 2) | (p[prior - 1] << 3) | (p[prior] << 4)
            | (p[prior + 1] << 5) | (p[prior + 2] << 6) | (p[earlier - 2] << 7) | (p[earlier - 1] << 8)
            | (p[earlier] << 9) | (p[earlier + 1] << 10) | (p[earlier + 2] << 11))


def _update(counts, off: int, bit: int) -> None:
    counts[off + bit] = (counts[off + bit] + _INCREMENT) & 0xFFFF
    if counts[off] + counts[off + 1] >= _COUNT_LIMIT:
        counts[off] = (counts[off] >> 1) or 1
        counts[off + 1] = (counts[off + 1] >> 1) or 1


def decode_one_bit(payload: str, width: int, height: int) -> bytearray:
    """`payload` starts with "!". Returns width*height bytes of 0/1, row-major."""
    if not payload.startswith("!"):
        raise MaskError("not a one_bit mask (request metadata.mask_encoding=one_bit)")
    if width <= 0 or height <= 0 or width * height > 4096 * 4096:
        raise MaskError("bad mask size")
    data = b85_decode(payload[1:])
    if len(data) < 4:
        raise MaskError("mask payload is missing its finalization")
    pos_in = 4
    code = int.from_bytes(data[:4], "big")
    low, rng = 0, _M32
    counts = array("H", [1]) * (_CONTEXTS * 2)
    pw = width + 2 * _PAD
    padded = bytearray(pw * (height + _PAD))
    out = bytearray(width * height)
    n = len(data)
    for y in range(height):
        row = (y + _PAD) * pw + _PAD
        for x in range(width):
            pos = row + x
            off = _context(padded, pos, pos - pw, pos - 2 * pw) << 1
            zero, one = counts[off], counts[off + 1]
            scaled = rng // (zero + one)
            if scaled == 0:
                raise MaskError("invalid coding state")
            value = ((code - low) & _M32) // scaled
            bit = 0 if min(value, zero + one - 1) < zero else 1
            cum, freq = (0, zero) if bit == 0 else (zero, one)
            low = (low + scaled * cum) & _M32
            rng = scaled * freq
            while True:
                if (low ^ ((low + rng) & _M32)) < _TOP:
                    pass
                elif rng < _BOTTOM:
                    rng = (-low) & (_BOTTOM - 1)
                else:
                    break
                if pos_in >= n:
                    raise MaskError("mask payload ended early")
                code = ((code << 8) | data[pos_in]) & _M32
                pos_in += 1
                low = (low << 8) & _M32
                rng = (rng << 8) & _M32
            padded[pos] = bit
            out[y * width + x] = bit
            _update(counts, off, bit)
    return out


def encode_one_bit(raster: bytes, width: int, height: int) -> str:
    """Inverse of decode_one_bit (tests only)."""
    low, rng, out = 0, _M32, bytearray()
    counts = array("H", [1]) * (_CONTEXTS * 2)
    pw = width + 2 * _PAD
    padded = bytearray(pw * (height + _PAD))
    for y in range(height):
        row = (y + _PAD) * pw + _PAD
        for x in range(width):
            pos = row + x
            off = _context(padded, pos, pos - pw, pos - 2 * pw) << 1
            zero, one = counts[off], counts[off + 1]
            bit = raster[y * width + x]
            cum, freq = (0, zero) if bit == 0 else (zero, one)
            scaled = rng // (zero + one)
            low = (low + scaled * cum) & _M32
            rng = scaled * freq
            while True:
                if (low ^ ((low + rng) & _M32)) < _TOP:
                    pass
                elif rng < _BOTTOM:
                    rng = (-low) & (_BOTTOM - 1)
                else:
                    break
                out.append(low >> 24)
                low = (low << 8) & _M32
                rng = (rng << 8) & _M32
            padded[pos] = bit
            _update(counts, off, bit)
    for _ in range(4):
        out.append(low >> 24)
        low = (low << 8) & _M32
    return "!" + b85_encode(bytes(out))
