"""Uploaded damage photos: check they are JPEGs and strip every metadata segment (EXIF, GPS, XMP, comments).

The app already re-draws each photo on a canvas before upload (upright, at most 1600 px, no EXIF); this is
the server-side guarantee for anything else that reaches the API. Pure Python: no image library in Lambda.
"""
import struct

MAX_PHOTO_BYTES = 1_500_000
MAX_SIDE = 4096
# Kept: APP0 (JFIF, no personal data) and APP14 (Adobe color transform; some JPEGs decode wrong without it).
# Dropped: APP1 (EXIF with GPS, XMP), APP2-APP13 and APP15 (ICC, maker notes, IPTC...), COM (comments).
_KEEP_APP = {0xE0, 0xEE}
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class PhotoError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def clean_jpeg(data: bytes) -> tuple[bytes, int, int]:
    """(JPEG without metadata, width, height). Raises PhotoError for anything that isn't a usable JPEG."""
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoError("photo_too_large", 413)
    if data[:2] != b"\xff\xd8":
        raise PhotoError("not_jpeg")
    out, i, width, height = bytearray(b"\xff\xd8"), 2, 0, 0
    while True:
        while i < len(data) and data[i] == 0xFF and i + 1 < len(data) and data[i + 1] == 0xFF:
            i += 1  # fill bytes
        if i + 4 > len(data) or data[i] != 0xFF:
            raise PhotoError("not_jpeg")
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: the image data runs to the end, copied as is
            out += data[i:]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers without a length
            out += data[i:i + 2]
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        end = i + 2 + length
        if length < 2 or end > len(data):
            raise PhotoError("not_jpeg")
        if marker in _SOF and length >= 7:
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
        if not ((0xE1 <= marker <= 0xEF and marker not in _KEEP_APP) or marker == 0xFE):
            out += data[i:end]
        i = end
    if not width or not height:
        raise PhotoError("not_jpeg")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise PhotoError("photo_too_large", 413)
    return bytes(out), width, height
