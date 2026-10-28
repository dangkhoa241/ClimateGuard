"""Offline tests for the recovery agent: SAM mask decoding and overlays, photo metadata stripping,
the fixed per-disaster lists, the job flow (vision and SAM mocked), guardrails and the HTTP routes."""
import base64
import json
import random
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, photos, recovery, recovery_data as data, recovery_guard, recovery_store, sam, sam_mask
from climateguard.handlers import recovery as handler
from climateguard.languages import LANGS

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sam_output.json").read_text())


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(handler.ratelimit, "_local", {})


# --- SAM masks and overlay --------------------------------------------------------------------------

@pytest.mark.parametrize("w,h,density", [(1, 1, 1), (19, 9, 0.3), (64, 40, 0.0), (64, 40, 1.0), (57, 33, 0.5)])
def test_one_bit_round_trip(w, h, density):
    rnd = random.Random(w * h)
    raster = bytes(int(rnd.random() < density) for _ in range(w * h))
    assert bytes(sam_mask.decode_one_bit(sam_mask.encode_one_bit(raster, w, h), w, h)) == raster


def test_base85_round_trip_all_lengths():
    for n in range(0, 13):
        blob = bytes(range(200, 200 + n))
        assert sam_mask.b85_decode(sam_mask.b85_encode(blob)) == blob


def test_live_sam_output_parses_and_decodes():
    # recorded from sam-3.1 (scripts/smoke_sam.py): "debris" found 29 pieces, "damaged drywall" none
    recs = sam.parse(FIXTURE["raw"]["debris"])
    assert len(recs) == 29 and sam.parse(FIXTURE["raw"]["damaged drywall"]) == []
    for r in recs:
        mh, mw, payload = r["mask"]
        raster = sam_mask.decode_one_bit(payload, mw, mh)
        x1, y1, x2, y2 = r["box"]
        assert (mh, mw) == (y2 - y1 + 1, x2 - x1 + 1)  # masks cover their box, not the frame
        assert 0 < sum(raster) <= mw * mh
        assert (r["w"], r["h"]) == tuple(FIXTURE["frame"]) and 0 < r["conf"] <= 1


def test_corrupt_mask_is_rejected():
    payload = sam.parse(FIXTURE["raw"]["debris"])[0]["mask"][2]
    with pytest.raises(sam_mask.MaskError):
        sam_mask.decode_one_bit(payload[:-3], 20, 10)
    with pytest.raises(sam_mask.MaskError):
        sam_mask.decode_one_bit("~" + payload[1:], 20, 10)  # lossless isn't requested


def _png_size(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


def test_overlay_png_has_frame_aspect_and_marks_the_box():
    recs = sam.parse(FIXTURE["raw"]["debris"])
    png = sam.overlay_png([(0, recs)], *FIXTURE["frame"])
    assert _png_size(png) == (640, 428)
    one = {"box": [100, 100, 199, 149], "w": 400, "h": 200, "conf": 1, "id": "0",
           "mask": (50, 100, sam_mask.encode_one_bit(b"\x01" * 5000, 100, 50))}
    import zlib
    png = sam.overlay_png([(1, [one])], 400, 200)
    w, h = _png_size(png)
    idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
    rows = zlib.decompress(idat)
    alpha = lambda x, y: rows[y * (w * 4 + 1) + 1 + x * 4 + 3]  # noqa: E731
    assert alpha(150, 125) > 0 and alpha(50, 50) == 0 and alpha(250, 125) == 0


def test_no_masks_no_overlay():
    assert sam.overlay_png([(0, [])], 1280, 855) is None


# --- photos -----------------------------------------------------------------------------------------

def _jpeg(w=800, h=600, extra=b""):
    seg = lambda m, body: b"\xff" + bytes([m]) + struct.pack(">H", len(body) + 2) + body  # noqa: E731
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0")
            + seg(0xE1, b"Exif\0\0GPSLatitude 37.95 -121.29") + seg(0xE1, b"http://ns.adobe.com/xap/1.0/\0<x/>")
            + seg(0xE2, b"ICC_PROFILE\0") + seg(0xFE, b"taken at 123 Main St") + extra
            + seg(0xC0, b"\x08" + struct.pack(">HH", h, w) + b"\x03\x01\x22\0\x02\x11\x01\x03\x11\x01")
            + seg(0xDA, b"\x03\x01\0\x02\x11\x03\x11\0\x3f\0") + b"\x12\x34\xff\x00\x56" + b"\xff\xd9")


def test_metadata_stripped_and_size_read():
    clean, w, h = photos.clean_jpeg(_jpeg())
    assert (w, h) == (800, 600)
    for leaked in (b"GPS", b"Exif", b"Main St", b"adobe", b"ICC"):
        assert leaked not in clean
    assert b"JFIF" in clean and clean.endswith(b"\x12\x34\xff\x00\x56\xff\xd9")


@pytest.mark.parametrize("blob,code", [(b"\x89PNG\r\n\x1a\n" + b"0" * 50, "not_jpeg"), (b"\xff\xd8\xff", "not_jpeg"),
                                       (b"\xff\xd8" + b"\0" * 1_600_000, "photo_too_large")],
                         ids=["png", "truncated", "too_big"])
def test_bad_photos_rejected(blob, code):
    with pytest.raises(photos.PhotoError) as e:
        photos.clean_jpeg(blob)
    assert e.value.code == code


def test_huge_dimensions_rejected():
    with pytest.raises(photos.PhotoError):
        photos.clean_jpeg(_jpeg(w=9000, h=6000))


# --- fixed lists -----------------------------------------------------------------------------------

def test_every_fixed_text_has_all_languages():
    tables = [data.DISASTER_LABELS, data.OPTIONS, data.DANGER_WORDS,
              {k: {**v, "sam": None} for k, v in data.CONCEPTS.items()},
              {k: {**v, "options": None} for k, v in data.QUESTIONS.items()}]
    for table in tables:
        for key, texts in table.items():
            assert set(LANGS) <= set(texts), key
    for d in (data.LEAVE_AND_CALL, data.DANGER_SEEN, data.HURT_CALL):
        assert set(LANGS) <= set(d)


def test_lists_are_disaster_agnostic_and_consistent():
    assert set(data.CONCEPTS_BY_DISASTER) == set(data.QUESTIONS_BY_DISASTER) == set(data.DISASTERS)
    for d in data.DISASTERS:
        assert set(data.CONCEPTS_BY_DISASTER[d]) <= set(data.CONCEPTS)
        assert set(data.QUESTIONS_BY_DISASTER[d]) <= set(data.QUESTIONS) - {"hurt"}
    for q in data.QUESTIONS.values():
        assert set(q["options"]) <= set(data.OPTIONS)
    assert sum("flood" in str(v) for v in data.CONCEPTS_BY_DISASTER.values()) == 0


def test_pick_questions_two_to_four_and_hurt_first():
    assert data.pick_questions("flood", ["water_height", "outage", "when", "stay", "own_rent"]) == \
        ["hurt", "water_height", "when", "stay"]  # "outage" isn't a flood question
    assert data.pick_questions("earthquake", []) == ["hurt", "gas_smell", "when"]
    assert data.pick_questions("storm", ["hurt", "hurt"]) == ["hurt", "when", "insurance"]


def test_danger_lines_first_leave_and_call():
    lines = data.danger_lines(["water_power", "gas"], hurt=True, lang="es")
    assert lines[0] == data.LEAVE_AND_CALL["es"] and "911" in lines[0]
    assert "gas" in lines[1] and "enchufes" in lines[1] and " y " in lines[1]
    assert lines[2] == data.HURT_CALL["es"]
    assert data.danger_lines([], hurt=False, lang="vi") == []
    assert data.danger_lines([], hurt=True, lang="vi") == [data.HURT_CALL["vi"]]


# --- guardrails -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,rule", [
    ("The house looks safe to enter.", "safety_verdict"),
    ("This room is unsafe.", "safety_verdict"),
    ("The structure appears structurally sound.", "safety_verdict"),
    ("La casa es segura para vivir.", "safety_verdict"),
    ("Ngôi nhà vẫn an toàn để ở.", "safety_verdict"),
    ("房子可以安全进入。", "safety_verdict"),
    ("Repairs will cost about $4,000.", "repair_cost"),
    ("La reparación cuesta unos 3000 dólares.", "repair_cost"),
    ("Chi phí sửa chữa khoảng 2.000 đô la.", "repair_cost"),
    ("Clean the wound and take ibuprofen.", "medical"),
    ("Aplique primeros auxilios.", "medical"),
    ("Hãy băng bó vết thương.", "medical"),
])
def test_guard_blocks(text, rule):
    assert rule in recovery_guard.issues(text)


@pytest.mark.parametrize("text", [
    "Water line about 2 feet up the living room wall.", "Soaked carpet and mud on the floor.",
    "Tiene seguro de inundación.", "Vệt nước cao khoảng 60 cm trên tường phòng khách.", "Broken window glass."])
def test_guard_allows_plain_damage(text):
    assert recovery_guard.issues(text) == []


# --- job flow (vision and SAM mocked) ---------------------------------------------------------------

def _vision_says(monkeypatch, parsed, cost=0.01):
    calls = []

    def fake(choice, images):
        calls.append((choice, len(images)))
        return parsed, cost
    monkeypatch.setattr(recovery, "_vision", fake)
    return calls


def _sam_finds(monkeypatch, by_concept):
    def fake(jpeg, concept, purpose=""):
        if concept == "boom":
            raise RuntimeError("SAM down")
        return sam.parse(by_concept.get(concept, ""))
    monkeypatch.setattr(sam, "segment", fake)


def _job_with_photos(n=2, lang="vi", disaster="flood"):
    rec = recovery.new_job(lang, disaster)
    for i in range(n):
        recovery.add_photo(rec["id"], i, _jpeg())
    return rec["id"]


def test_full_analysis_flow(monkeypatch):
    calls = _vision_says(monkeypatch, {
        "photos": [{"photo": 1, "area": "living room", "damage": ["water line on wall", "repair will cost $900"],
                    "concepts": ["debris", "crack", "mud", "debris"], "danger": ["water_power", "aliens"]},
                   {"photo": 2, "area": "kitchen", "damage": [], "concepts": [], "danger": []}],
        "disaster": "storm", "questions": ["water_height", "outage", "flood_insurance"]})
    _sam_finds(monkeypatch, {"debris": FIXTURE["raw"]["debris"]})
    job = _job_with_photos()
    recovery.start_analysis(job)
    rec = recovery.analyze(job)
    assert calls == [("flood", 2)] and rec["status"] == "questions"
    a = rec["analysis"]
    assert a["disaster"] == "flood" and a["inferred"] == "storm"  # the person's choice wins
    p1 = a["photos"][0]
    assert p1["concepts"] == ["debris", "mud"]                   # "crack" isn't a flood concept; deduped
    assert p1["damage"] == ["water line on wall"]                # the cost phrase was dropped
    assert a["guard_removed"] == ["repair_cost"] and a["dangers"] == ["water_power"]
    assert p1["found"] == [{"concept": "debris", "count": 29, "color": "#0072b2"}]  # mud: nothing found
    assert p1["overlay"].startswith("data:image/png;base64,") and a["photos"][1]["overlay"] is None
    assert a["questions"] == ["hurt", "water_height", "flood_insurance"]
    assert rec["cost_usd"] == pytest.approx(0.01 + 2 * sam.SAM_USD_PER_IMAGE)

    v = recovery.view(rec)
    assert v["danger_lines"][0] == data.LEAVE_AND_CALL["vi"]
    assert v["disaster_label"] == "Lũ lụt" and v["inferred_label"] == data.DISASTER_LABELS["storm"]["vi"]
    assert v["questions"][0] == {"id": "hurt", "text": "Có ai bị thương không?",
                                 "options": [{"id": "yes", "text": "Có"}, {"id": "no", "text": "Không"}]}
    assert v["photos"][0]["found"][0]["label"] == "Mảnh vụn"
    assert "area" not in json.dumps(v["photos"]) and "Main St" not in json.dumps(v)


def test_auto_uses_inferred_disaster_and_any_concept(monkeypatch):
    _vision_says(monkeypatch, {"photos": [{"photo": 1, "concepts": ["crack", "burned"]}], "disaster": "earthquake",
                               "questions": []})
    _sam_finds(monkeypatch, {})
    job = _job_with_photos(1, "en", "auto")
    recovery.start_analysis(job)
    a = recovery.analyze(job)["analysis"]
    assert a["disaster"] == "earthquake" and a["photos"][0]["concepts"] == ["crack", "burned"]
    assert a["questions"] == ["hurt", "gas_smell", "when"]


def test_sam_failure_keeps_the_photo(monkeypatch):
    _vision_says(monkeypatch, {"photos": [{"photo": 1, "concepts": ["debris"]}], "disaster": "flood"})
    monkeypatch.setitem(data.CONCEPTS["debris"], "sam", "boom")
    _sam_finds(monkeypatch, {})
    job = _job_with_photos(1)
    recovery.start_analysis(job)
    rec = recovery.analyze(job)
    assert rec["status"] == "questions" and rec["analysis"]["photos"][0]["overlay"] is None
    assert rec["cost_usd"] == pytest.approx(0.01)  # a failed SAM call isn't counted


def test_vision_failure_is_an_error_that_can_be_retried(monkeypatch):
    def broken(choice, images):
        raise ValueError("no JSON object in the answer")
    monkeypatch.setattr(recovery, "_vision", broken)
    job = _job_with_photos(1)
    recovery.start_analysis(job)
    assert recovery.analyze(job)["status"] == "error"
    assert recovery.start_analysis(job)["status"] == "analyzing"


def test_job_rules():
    with pytest.raises(recovery.JobError):
        recovery.new_job("fr", "flood")
    with pytest.raises(recovery.JobError):
        recovery.new_job("en", "volcano")
    job = recovery.new_job("en", "auto")["id"]
    with pytest.raises(recovery.JobError) as e:
        recovery.start_analysis(job)
    assert e.value.code == "no_photos"
    with pytest.raises(recovery.JobError):
        recovery.add_photo(job, 6, _jpeg())
    recovery.add_photo(job, 0, _jpeg())
    recovery.start_analysis(job)
    with pytest.raises(recovery.JobError) as e:
        recovery.add_photo(job, 1, _jpeg())
    assert e.value.code == "already_started"
    with pytest.raises(recovery.JobError) as e:
        recovery.load("../../etc/passwd")
    assert e.value.status == 404


def test_stale_analysis_shows_as_error():
    job = _job_with_photos(1)
    rec = recovery.start_analysis(job)
    rec["started"] = time.time() - 600
    assert recovery.view(rec)["status"] == "error"


def test_photos_gone_after_24_hours(monkeypatch):
    job = _job_with_photos(1)
    rec = recovery_store.get_job(job)
    rec["created"] -= 25 * 3600
    recovery_store.put_job(rec)
    assert recovery_store.get_job(job) is None  # never served after 24 h
    assert recovery_store.delete_expired(now=time.time() + 25 * 3600) == 1
    assert recovery_store.names(job) == []


# --- HTTP routes ------------------------------------------------------------------------------------

def _event(route, job="", body=None, binary=None, query=None, ip="1.2.3.4"):
    if binary is not None:
        raw, b64 = base64.b64encode(binary).decode(), True
    else:
        raw, b64 = json.dumps(body) if body is not None else None, False
    return {"routeKey": route, "pathParameters": {"job": job} if job else None, "body": raw, "isBase64Encoded": b64,
            "queryStringParameters": query, "requestContext": {"http": {"sourceIp": ip}}}


def test_routes_end_to_end(monkeypatch):
    _vision_says(monkeypatch, {"photos": [{"photo": 1, "concepts": ["debris"]}], "disaster": "flood"})
    _sam_finds(monkeypatch, {"debris": FIXTURE["raw"]["debris"]})
    started = []
    monkeypatch.setattr(handler, "_start_worker", lambda task, job: started.append(job))
    r = handler.handler(_event("POST /recovery", body={"lang": "es", "disaster": "flood"}), None)
    assert r["statusCode"] == 201
    job = json.loads(r["body"])["job"]
    r = handler.handler(_event("POST /recovery/{job}/photos", job, binary=_jpeg(), query={"i": "0"}), None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["width"] == 800
    bad = handler.handler(_event("POST /recovery/{job}/photos", job, binary=b"GIF89a", query={"i": "1"}), None)
    assert bad["statusCode"] == 400 and json.loads(bad["body"])["error"] == "not_jpeg"
    assert json.loads(handler.handler(_event("GET /recovery/{job}", job), None)["body"])["photo_count"] == 1
    r = handler.handler(_event("POST /recovery/{job}/analyze", job), None)
    assert r["statusCode"] == 202 and started == [job]
    assert handler.handler({"recovery_task": "analyze", "job": job}, None) == {"status": "questions"}
    v = json.loads(handler.handler(_event("GET /recovery/{job}", job), None)["body"])
    assert v["status"] == "questions" and v["questions"][0]["text"] == "¿Hay alguien herido?"
    assert handler.handler(_event("DELETE /recovery/{job}", job), None)["statusCode"] == 200
    assert handler.handler(_event("GET /recovery/{job}", job), None)["statusCode"] == 404


def test_rate_limit_and_budget(monkeypatch):
    for _ in range(handler.JOBS_PER_IP_PER_HOUR):
        assert handler.handler(_event("POST /recovery", body={"lang": "en"}), None)["statusCode"] == 201
    assert handler.handler(_event("POST /recovery", body={"lang": "en"}), None)["statusCode"] == 429
    monkeypatch.setattr(handler.budget, "over_budget", lambda: True)
    monkeypatch.setattr(handler.ratelimit, "hit", lambda *a: True)
    r = handler.handler(_event("POST /recovery", body={"lang": "en"}), None)
    assert r["statusCode"] == 503 and json.loads(r["body"])["error"] == "over_budget"
