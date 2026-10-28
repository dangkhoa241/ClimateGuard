"""Live SAM 3.1 check on one photo: segments each concept, decodes the masks and writes the overlay PNG.

Usage: python scripts/smoke_sam.py photo.jpg "debris" "damaged drywall" [--out overlay.png] [--save-fixture]
Cost: $0.0025 per concept. --save-fixture keeps the raw output for the offline tests.
"""
import argparse
import json
import time
from pathlib import Path

import _path  # noqa: F401

from climateguard import config, sam

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sam_output.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("photo")
    p.add_argument("concepts", nargs="+")
    p.add_argument("--out", default="overlay.png")
    p.add_argument("--save-fixture", action="store_true")
    a = p.parse_args()
    jpeg = Path(a.photo).read_bytes()
    raw_texts, layers, frame = {}, [], (0, 0)
    orig_parse = sam.parse

    def keep(text):  # record the raw text for the fixture
        raw_texts[current] = text
        return orig_parse(text)
    sam.parse = keep
    for slot, current in enumerate(a.concepts):
        t0 = time.monotonic()
        recs = sam.segment(jpeg, current, purpose="smoke-sam")
        print(f"{current!r}: {len(recs)} records in {time.monotonic() - t0:.1f}s "
              f"(raw {len(raw_texts.get(current, ''))} chars)")
        for r in recs:
            print(f"  id={r['id']} box={r['box']} frame={r['w']}x{r['h']} conf={r['conf']:.2f} mask={r['mask'][:2]}")
            frame = (r["w"], r["h"])
        layers.append((slot, recs))
    t0 = time.monotonic()
    png = sam.overlay_png(layers, *frame)
    print(f"overlay decode+render {time.monotonic() - t0:.2f}s, {len(png or b'')} bytes")
    if png:
        Path(a.out).write_bytes(png)
    if a.save_fixture:
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(json.dumps({"model": config.SAM_MODEL, "frame": frame, "raw": raw_texts}, indent=1))
        print("fixture saved:", FIXTURE)


if __name__ == "__main__":
    main()
