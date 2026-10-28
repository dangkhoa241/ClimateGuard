"""SAM 3.1 damage outlines for the recovery agent (Meta Model API).

Endpoint (https://dev.meta.ai/docs/sam/segmenting): POST /v1/responses, model "sam-3.1", one user message
with the concept as `input_text` (one short noun phrase per request) and the photo as an `input_image`
data URL. Output: one line of records `id<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..;c=..|><|mask;x=0;y=0;
c=..;data=H,W,!payload|>`, comma-separated, empty when nothing matches. Price: $2.50 per 1,000 images,
so $0.0025 per request (https://dev.meta.ai/docs/pricing-rate-limits); logged like every model call.

The overlay is one small RGBA PNG per photo at the mask raster's size, stretched over the photo by the
app: no image library needed in Lambda.
"""
import base64
import logging
import re
import struct
import zlib

from . import config, llm, sam_mask, usage

log = logging.getLogger(__name__)

SAM_USD_PER_IMAGE = 0.0025
CALL_DEADLINE_S = 25
MIN_CONFIDENCE = 0.4

_RECORD = re.compile(r"(\d+)<\|box;([^|]*)\|><\|mask;([^|]*)\|>")


def _fields(spec: str) -> dict:
    out = {}
    for part in spec.split(";"):
        k, _, v = part.partition("=")
        out[k] = v
    return out


def parse(text: str) -> list[dict]:
    """Records from SAM's output text: {id, box: [x1, y1, x2, y2], w, h, conf, mask: (H, W, payload)}."""
    out = []
    for m in _RECORD.finditer(text or ""):
        box, mask = _fields(m.group(2)), _fields(m.group(3))
        data = mask.get("data", "")
        try:
            mh, mw, payload = data.split(",", 2)
            out.append({"id": m.group(1),
                        "box": [int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"])],
                        "w": int(box["w"]), "h": int(box["h"]),
                        "conf": float(box.get("c") or mask.get("c") or 1.0),
                        "mask": (int(mh), int(mw), payload)})
        except (KeyError, ValueError):
            log.warning("unreadable SAM record skipped")
    return out


def segment(jpeg: bytes, concept: str, purpose: str = "recovery-sam") -> list[dict]:
    """One SAM request for one concept. Raises on API failure (the caller keeps the photo without it)."""
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    params = {"model": config.SAM_MODEL,
              "input": [{"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": concept},
                                     {"type": "input_image", "image_url": url}]}],
              "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"}}
    client = llm._client("meta")
    raw = llm._with_deadline(lambda: client.responses.create(**params).model_dump(), CALL_DEADLINE_S)
    usage.log_extra("meta", config.SAM_MODEL, SAM_USD_PER_IMAGE, purpose=purpose)
    text = "".join(part.get("text") or "" for o in raw.get("output") or [] if o.get("type") == "message"
                   for part in o.get("content") or [])
    return [r for r in parse(text) if r["conf"] >= MIN_CONFIDENCE]


# --- overlay -------------------------------------------------------------------------------------

# Colors per concept slot in a photo (colorblind-friendly: blue, orange, magenta), RGB.
COLORS = [(0, 114, 178), (230, 159, 0), (204, 121, 167)]
FILL_ALPHA, EDGE_ALPHA = 105, 235
MAX_OVERLAY_SIDE = 640  # stretched over the photo by the app; small debris needs a few pixels to show


def _png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    stride = width * 4
    raw = b"".join(b"\0" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def overlay_png(layers: list[tuple[int, list[dict]]], frame_w: int, frame_h: int) -> bytes | None:
    """`layers`: (color slot, records) per concept. Returns a PNG with the frame's aspect ratio, or None if
    empty. Each mask raster covers its own box (origin 0,0 = the box's top-left corner), as measured live:
    a 25x37 px box came with a 26x38 mask."""
    if frame_w <= 0 or frame_h <= 0:
        return None
    scale = min(1.0, MAX_OVERLAY_SIDE / max(frame_w, frame_h))
    tw, th = max(1, round(frame_w * scale)), max(1, round(frame_h * scale))
    slot_of = bytearray(tw * th)  # 0 = none, else color slot + 1 (later concepts on top)
    any_mask = False
    for slot, records in layers:
        for r in records:
            mh, mw, payload = r["mask"]
            try:
                raster = sam_mask.decode_one_bit(payload, mw, mh)
            except sam_mask.MaskError as e:
                log.warning("mask skipped: %s", e)
                continue
            x1, y1, x2, y2 = r["box"]
            bw, bh = max(x2 - x1 + 1, 1), max(y2 - y1 + 1, 1)
            # overlay pixels whose centers fall inside the box, sampled from the box-sized mask
            ox1, ox2 = max(int(x1 * scale), 0), min(int((x2 + 1) * scale) + 1, tw)
            oy1, oy2 = max(int(y1 * scale), 0), min(int((y2 + 1) * scale) + 1, th)
            for oy in range(oy1, oy2):
                fy = (oy + 0.5) / scale - y1
                if not 0 <= fy < bh:
                    continue
                row = int(fy * mh / bh) * mw
                for ox in range(ox1, ox2):
                    fx = (ox + 0.5) / scale - x1
                    if 0 <= fx < bw and raster[row + int(fx * mw / bw)]:
                        slot_of[oy * tw + ox] = slot + 1
                        any_mask = True
    if not any_mask:
        return None
    rgba = bytearray(tw * th * 4)
    for i, s in enumerate(slot_of):
        if not s:
            continue
        y, x = divmod(i, tw)
        edge = (x == 0 or y == 0 or x == tw - 1 or y == th - 1 or slot_of[i - 1] != s or slot_of[i + 1] != s
                or slot_of[i - tw] != s or slot_of[i + tw] != s)
        r, g, b = COLORS[(s - 1) % len(COLORS)]
        rgba[i * 4:i * 4 + 4] = bytes((r, g, b, EDGE_ALPHA if edge else FILL_ALPHA))
    return _png(tw, th, bytes(rgba))
