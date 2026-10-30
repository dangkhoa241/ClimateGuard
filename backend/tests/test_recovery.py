"""Offline tests for the recovery agent: SAM mask decoding and overlays, photo metadata stripping,
the fixed per-disaster lists, the job flow (vision and SAM mocked), guardrails and the HTTP routes."""
import base64
import json
import random
import re
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


def _record(rid, box, mask_w, mask_h, ones, frame=(1280, 855)):
    raster = bytes(1 if i < ones else 0 for i in range(mask_w * mask_h))
    x1, y1, x2, y2 = box
    return (f"{rid}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={frame[0]};h={frame[1]};c=0.9|>"
            f"<|mask;x=0;y=0;c=0.9;data={mask_h},{mask_w},{sam_mask.encode_one_bit(raster, mask_w, mask_h)}|>")


# a 640x400 px piece of damage (23% of the photo) and a 20x10 px speck
BIG_AND_SPECK = "<0f>" + _record(0, (100, 100, 739, 499), 64, 40, 64 * 40) + "," + _record(1, (10, 10, 29, 19), 20, 10, 200)


def test_masks_under_the_minimum_dropped():
    big, speck = sam.parse(BIG_AND_SPECK)
    assert sam.area_fraction(big) == pytest.approx(640 * 400 / (1280 * 855))
    assert sam.drop_small([big, speck]) == [big] and sam.drop_small([big, speck], 0.015) == [big]
    # a big box with a mostly empty mask counts its mask pixels, not the box: 2% of 640x400 is 0.47% of the photo
    sparse = sam.parse("<0f>" + _record(2, (100, 100, 739, 499), 64, 40, 51))[0]
    assert sam.drop_small([sparse], 0.015) == [] and sam.drop_small([sparse], 0.003) == [sparse]
    # just above / below 1.5% (16,416 px of 1280x855) and 0.3% (3,283 px)
    assert sam.drop_small(sam.parse("<0f>" + _record(3, (0, 0, 164, 99), 165, 100, 16500)), 0.015)
    assert not sam.drop_small(sam.parse("<0f>" + _record(4, (0, 0, 164, 99), 165, 100, 16300)), 0.015)
    assert sam.drop_small(sam.parse("<0f>" + _record(5, (0, 0, 99, 39), 100, 40, 3300)))
    assert not sam.drop_small(sam.parse("<0f>" + _record(6, (0, 0, 99, 39), 100, 40, 3250)))
    # the live "debris" specks on the Kentucky photo are all under 1.5%: no outline, no legend entry
    assert sam.drop_small(sam.parse(FIXTURE["raw"]["debris"]), data.min_area("debris")) == []


def test_minimum_area_per_label():
    assert data.min_area("debris") == data.min_area("furniture") == 0.015
    for concept in ("water_line", "mold", "mud", "crack"):  # thin by nature: 0.05%
        assert data.min_area(concept) == 0.0005, concept
    for concept in set(data.CONCEPTS) - {"debris", "furniture", "water_line", "mold", "mud", "crack"}:
        assert data.min_area(concept) == 0.003, concept


def test_thin_water_line_and_crack_masks_kept_specks_dropped():
    # live on the demo flood photo (1200x797 = 956,400 px): water-line masks of 0.61% and 0.19%, crack masks of
    # 0.18% and 0.07% are outlined; a 0.03% speck is not; the same 0.19% as "debris" would be dropped
    def mask(px):  # a full box of `px` pixels, mask all ones
        return sam.parse("<0f>" + _record(9, (0, 0, px - 1, 0), px, 1, px))[0]
    total = 1200 * 797
    wide = [dict(mask(round(total * f)), w=1200, h=797) for f in (0.0061, 0.0019, 0.0007, 0.0003)]
    kept = sam.drop_small(wide, data.min_area("water_line"))
    assert [round(sam.area_fraction(r) * 100, 2) for r in kept] == [0.61, 0.19, 0.07]
    assert sam.drop_small(wide[:2], data.min_area("debris")) == []


def test_flood_photos_can_ask_sam_for_cracks_and_the_water_line_prompt():
    assert "crack" in data.CONCEPTS_BY_DISASTER["flood"]
    assert data.CONCEPTS["water_line"]["sam"] == "water stain line on wall"  # plain "water stain" found nothing


def test_small_crack_kept_small_debris_dropped(monkeypatch):
    # the same 0.47% mask: a crack (0.3% minimum) is outlined and listed, debris (1.5%) is not
    small = "<0f>" + _record(0, (100, 100, 739, 499), 64, 40, 51)
    _vision_says(monkeypatch, {"photos": [{"photo": 1, "concepts": ["crack", "debris"]}], "disaster": "earthquake"})
    _sam_finds(monkeypatch, {"crack": small, "debris": small})
    job = _job_with_photos(1, "en", "earthquake")
    recovery.start_analysis(job)
    p = recovery.analyze(job)["analysis"]["photos"][0]
    assert [f["concept"] for f in p["found"]] == ["crack"] and p["overlay"]


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


@pytest.mark.parametrize("text", [
    "A storm damaged the owned home.", "The house you own has a fallen tree.", "Water entered the rented home.",
    "Since you own the house, call your insurer.", "La casa propia tiene daños en el techo.",
    "Su vivienda alquilada tiene agua.", "Nhà riêng của bạn bị cây đổ.", "Nhà bạn thuê bị ngập nước."])
def test_guard_blocks_owned_or_rented_wording(text):
    assert "ownership" in recovery_guard.issues(text)


@pytest.mark.parametrize("text", [
    "A storm damaged your home.", "La tormenta dañó su casa.", "Cơn bão làm hư hại nhà của bạn.",
    "Tell your landlord in writing about the roof.", "Do you have home or renters insurance?",
    "Hãy báo cho chủ nhà về mái nhà bị hư."])
def test_guard_allows_your_home(text):
    assert recovery_guard.issues(text) == []


def test_landlord_detail_may_mention_renting():
    text = "Since you rent, send your landlord the photos of the roof."
    assert recovery_guard.issues(text) == ["ownership"]
    assert recovery_guard.issues(text, ownership_ok=True) == []
    assert recovery_guard.OWNERSHIP_OK_ITEMS == {"landlord", "flood_policy"}


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
                    "concepts": ["debris", "burned", "mud", "debris"], "danger": ["water_power", "aliens"]},
                   {"photo": 2, "area": "kitchen", "damage": [], "concepts": [], "danger": []}],
        "disaster": "storm", "questions": ["water_height", "outage", "flood_insurance"]})
    _sam_finds(monkeypatch, {"debris": BIG_AND_SPECK})
    job = _job_with_photos()
    recovery.start_analysis(job)
    rec = recovery.analyze(job)
    assert calls == [("flood", 2)] and rec["status"] == "questions"
    a = rec["analysis"]
    assert a["disaster"] == "flood" and a["inferred"] == "storm"  # the person's choice wins
    p1 = a["photos"][0]
    assert p1["concepts"] == ["debris", "mud"]                   # "burned" isn't a flood concept; deduped
    assert p1["damage"] == ["water line on wall"]                # the cost phrase was dropped
    assert a["guard_removed"] == ["repair_cost"] and a["dangers"] == ["water_power"]
    assert p1["found"] == [{"concept": "debris", "count": 1, "color": "#0072b2"}]  # speck dropped; mud: none
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
    _sam_finds(monkeypatch, {"debris": BIG_AND_SPECK})
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
    assert r["statusCode"] == 429 and json.loads(r["body"])["error"] == "demo_busy"


# --- checklist and report (model mocked) ------------------------------------------------------------

from climateguard import recovery_checklist as checklist, recovery_report  # noqa: E402
from climateguard.llm import ChatResult  # noqa: E402


def test_checklist_items_have_reviewed_languages_and_known_ids():
    for i, item in checklist.ITEMS.items():
        assert set(checklist.REVIEWED) <= set(item), i
    for ids in checklist.CLEANUP.values():
        assert set(ids) <= set(checklist.ITEMS)


@pytest.mark.parametrize("disaster,answers,first,has,lacks", [
    ("flood", {}, "document", {"insurer", "flood_policy", "fema", "call211", "flood_dry"}, {"landlord", "shelter", "gas"}),
    ("earthquake", {"gas_smell": "yes"}, "gas", {"quake_aftershocks", "inspect"}, {"flood_policy"}),
    ("storm", {"utilities": "none_off", "own_rent": "rent", "stay": "no", "insurance": "no"}, "utilities",
     {"landlord", "shelter", "tarp"}, {"insurer"}),
    ("heat_outage", {"utilities": "none_off"}, "document", {"outage_food", "generator"}, {"utilities"}),
])
def test_checklist_picked_by_disaster_and_answers(disaster, answers, first, has, lacks):
    ids = checklist.pick(disaster, answers)
    assert ids[0] == first and has <= set(ids) and not lacks & set(ids) and len(ids) == len(set(ids))


def test_checklist_languages():
    vi = checklist.render(["document", "call211"], "vi", {"document": "Chụp vệt nước ở phòng khách.", "call211": "x"})
    assert vi[0]["detail"] == "Chụp vệt nước ở phòng khách." and vi[1]["detail"] is None  # 211 takes no detail
    assert checklist.render(["call211"], "ko")[0]["text"] == checklist.ITEMS["call211"]["en"]


ANALYSIS_PHOTOS = [{"index": 0, "area": "living room", "damage": ["water line on wall"], "concepts": ["water_line"],
                    "danger": [], "found": [{"concept": "water_line", "count": 1, "color": "#0072b2"}], "overlay": None},
                   {"index": 1, "area": "kitchen", "damage": ["mud on floor"], "concepts": [], "danger": [],
                    "found": [], "overlay": None}]


def _report_json(en_extra="", vi_extra=""):
    return json.dumps({
        "en": {"summary": "Flood water entered the home. A water line shows on the living room wall." + en_extra,
               "areas": [{"area": "Living room", "photos": [1, 9], "damage": ["Water line on the wall"]},
                         {"area": "Kitchen", "photos": [2], "damage": ["Mud on the floor"]}],
               "details": {"document": "Photograph the water line in the living room.", "call211": "ignored"}},
        "vi": {"summary": "Nước lũ đã vào nhà. Có vệt nước trên tường phòng khách." + vi_extra,
               "areas": [{"area": "Phòng khách", "photos": [1], "damage": ["Vệt nước trên tường"]}],
               "details": {"document": "Bạn nên chụp vệt nước ở phòng khách."}}})


def _chat_returns(monkeypatch, *texts):
    calls = []

    def fake(provider, model, messages, **kw):
        calls.append(messages)
        return ChatResult(text=texts[min(len(calls), len(texts)) - 1], model=model, prompt_tokens=1,
                          completion_tokens=1, reasoning_tokens=0, cost_usd=0.004, cache_hit=False, raw={})
    monkeypatch.setattr(recovery_report.llm, "chat", fake)
    return calls


def test_report_written_checked_and_bilingual(monkeypatch):
    calls = _chat_returns(monkeypatch, _report_json())
    out = recovery_report.write("flood", ANALYSIS_PHOTOS, {"when": "today", "hurt": "no"}, "vi")
    assert len(calls) == 1 and out["attempts"] == 1 and out["guard_removed"] == []
    prompt = calls[0][0]["content"]
    assert "Photo 1: area: living room; damage: water line on wall; outlined: water line or stain x1" in prompt
    assert "When did the damage happen? Today" in prompt and "Is anyone hurt" not in prompt
    assert '"vi"' in prompt and "Hãy" in prompt
    assert out["en"]["areas"][0]["photos"] == [1]                       # photo 9 doesn't exist
    assert out["en"]["details"] == {"document": "Photograph the water line in the living room."}
    assert out["vi"]["details"]["document"].startswith("Hãy chụp")      # "Bạn nên" -> "Hãy"
    assert out["checklist_ids"][0] == "document" and out["cost_usd"] == pytest.approx(0.004)


def test_report_retries_once_then_drops_broken_lines(monkeypatch):
    bad = _report_json(en_extra=" The house is safe to enter.", vi_extra=" Chi phí sửa khoảng 3.000 đô la.")
    calls = _chat_returns(monkeypatch, bad, bad)
    out = recovery_report.write("flood", ANALYSIS_PHOTOS, {}, "vi")
    assert len(calls) == 2 and "safety_verdict" in calls[1][-1]["content"]
    assert out["guard_removed"] == ["repair_cost", "safety_verdict"]
    assert "safe" not in out["en"]["summary"] and "đô la" not in out["vi"]["summary"]
    assert out["en"]["summary"].startswith("Flood water entered the home.")

    calls = _chat_returns(monkeypatch, bad, _report_json())
    assert recovery_report.write("flood", ANALYSIS_PHOTOS, {}, "vi")["guard_removed"] == []  # fixed on retry


def _analyzed_job(monkeypatch, lang="vi"):
    _vision_says(monkeypatch, {"photos": [{"photo": 1, "area": "living room", "damage": ["water line on wall"],
                                           "concepts": []}], "disaster": "flood", "questions": ["when"]})
    job = _job_with_photos(1, lang)
    recovery.start_analysis(job)
    recovery.analyze(job)
    return job


def test_answers_validated_then_report_view(monkeypatch):
    job = _analyzed_job(monkeypatch)
    for bad in ({"when": "yesterday"}, {"outage": "h_4_24"}, ["when"]):
        with pytest.raises(recovery.JobError):
            recovery.submit_answers(job, bad)
    _chat_returns(monkeypatch, _report_json())
    recovery.submit_answers(job, {"hurt": "yes", "when": "today"})
    rec = recovery.report(job)
    assert rec["status"] == "done"
    v = recovery.view(rec)
    vi, en = v["report"]["sides"]
    assert (vi["lang"], en["lang"]) == ("vi", "en")
    assert vi["danger_lines"] == [data.HURT_CALL["vi"]] and en["danger_lines"] == [data.HURT_CALL["en"]]
    assert vi["answers"] == [{"q": "Có ai bị thương không?", "a": "Có"},
                             {"q": "Thiệt hại xảy ra khi nào?", "a": "Hôm nay"}]
    assert vi["checklist"][0]["text"] == checklist.ITEMS["document"]["vi"] and vi["disaster_label"] == "Lũ lụt"
    assert v["danger_lines"] == [data.HURT_CALL["vi"]]


def test_empty_translation_falls_back_to_english(monkeypatch):
    job = _analyzed_job(monkeypatch, "ko")
    _chat_returns(monkeypatch, json.dumps({"en": json.loads(_report_json())["en"], "ko": {"summary": "안전합니다."}}))
    recovery.submit_answers(job, {})
    side = recovery.view(recovery.report(job))["report"]["sides"][0]
    assert side["fallback_en"] and side["summary"].startswith("Flood water") and side["checklist_lang"] == "en"


def test_gas_answer_adds_danger_first(monkeypatch):
    job = _analyzed_job(monkeypatch, "es")
    rec = recovery.load(job)
    rec["analysis"]["questions"] = ["hurt", "gas_smell"]
    recovery_store.put_job(rec)
    v = recovery.view(recovery.submit_answers(job, {"gas_smell": "yes"}))
    assert v["danger_lines"][0] == data.LEAVE_AND_CALL["es"] and "gas" in v["danger_lines"][1]


def test_answers_route_starts_report_worker(monkeypatch):
    job = _analyzed_job(monkeypatch, "en")
    started = []
    monkeypatch.setattr(handler, "_start_worker", lambda task, j: started.append((task, j)))
    r = handler.handler(_event("POST /recovery/{job}/answers", job, body={"answers": {"hurt": "no"}}), None)
    assert r["statusCode"] == 202 and started == [("report", job)]
    bad = handler.handler(_event("POST /recovery/{job}/answers", job, body={"answers": {"hurt": "maybe"}}), None)
    assert bad["statusCode"] == 409  # already reporting
    _chat_returns(monkeypatch, _report_json())
    assert handler.handler({"recovery_task": "report", "job": job}, None) == {"status": "done"}
    v = json.loads(handler.handler(_event("GET /recovery/{job}", job), None)["body"])
    assert len(v["report"]["sides"]) == 1 and v["report"]["sides"][0]["checklist"][0]["id"] == "document"


# Phone test: the tarp item sent people onto a damaged roof. No item may tell anyone to go on a roof or into a
# damaged building; any mention must be a "never" / "do not" / "only from the ground".
_GO_UP_OR_IN = re.compile(r"\b(climb|go up|get up|get on|go on|walk on|step on)\b[^.;]*\broof|"
                          r"\b(enter|go inside|go into|go back inside|go back in)\b[^.;]*\b(building|home|house)\b",
                          re.IGNORECASE)
_NEGATED = re.compile(r"\b(never|do not|don't|not)\b", re.IGNORECASE)
# work on a roof ("cover holes in the roof") implies going up there unless the item says otherwise
_ROOF_WORK = re.compile(r"\b(cover|patch|repair|fix|tarp|seal)\b[^.;]*\broof", re.IGNORECASE)


def _unsafe_roof_or_building(text: str) -> list[str]:
    bad = [c for c in re.split(r"[.;:]", text) if _GO_UP_OR_IN.search(c) and not _NEGATED.search(c)]
    if _ROOF_WORK.search(text) and not ("from the ground" in text and "never climb" in text):
        bad.append("roof work without 'from the ground' and 'never climb'")
    return bad


def test_roof_rule_catches_the_old_tarp_text():
    old = ("Cover holes in the roof or windows with a tarp or plywood to stop more damage, "
           "and keep the receipts: insurers expect this.")
    assert _unsafe_roof_or_building(old)
    assert _unsafe_roof_or_building("Climb onto the roof to check the shingles.")
    assert _unsafe_roof_or_building("Go back inside the house to get your papers.")
    assert not _unsafe_roof_or_building("Never go back inside a damaged house.")


def test_no_checklist_item_sends_anyone_onto_a_roof_or_into_a_damaged_building():
    for item_id, item in checklist.ITEMS.items():
        assert not _unsafe_roof_or_building(item["en"]), item_id
    tarp = checklist.ITEMS["tarp"]
    assert set(LANGS) <= set(tarp)
    never_climb = {"en": "never climb on a damaged roof", "es": "nunca se suba a un techo dañado",
                   "vi": "tuyệt đối không trèo lên mái nhà bị hư", "zh": "切勿爬上受损的屋顶",
                   "tl": "huwag kailanman umakyat sa sirang bubong", "ko": "손상된 지붕에는 절대 올라가지 마세요",
                   "ar": "لا تصعد أبدًا إلى سقف متضرر"}
    from_ground = {"en": "from the ground", "es": "desde el suelo", "vi": "từ dưới đất", "zh": "从地面",
                   "tl": "mula sa lupa", "ko": "땅에서", "ar": "من على الأرض"}
    for lang in LANGS:
        assert never_climb[lang] in tarp[lang] and from_ground[lang] in tarp[lang], lang


@pytest.mark.parametrize("disaster", ["storm", "earthquake", "flood"])
def test_tarp_item_in_storm_quake_flood_and_shown_in_every_language(disaster):
    assert "tarp" in checklist.pick(disaster, {})
    ko = {c["id"]: c for c in checklist.render(checklist.pick(disaster, {}), "ko")}
    assert ko["tarp"]["lang"] == "ko" and ko["document"]["lang"] == "en"


def test_report_prompt_says_your_home_and_hides_own_rent(monkeypatch):
    calls = _chat_returns(monkeypatch, _report_json())
    recovery_report.write("flood", ANALYSIS_PHOTOS, {"own_rent": "own", "when": "today"}, "es")
    prompt = calls[0][0]["content"]
    assert '"your home"' in prompt and '"su casa"' in prompt and '"nhà của bạn"' in prompt
    assert "never \"the owned home\"" in prompt and "except in a detail for the landlord item" in prompt
    assert "own or rent" not in prompt and "I own it" not in prompt  # the answer only picks checklist items


def test_owned_home_lines_dropped_but_landlord_detail_kept(monkeypatch):
    raw = json.loads(_report_json())
    raw["en"]["summary"] = "Flood water entered the owned home. A water line shows on the living room wall."
    raw["en"]["details"]["landlord"] = "Since you rent, send your landlord the living room photos."
    raw["en"]["details"]["fema"] = "Tell FEMA the house you own was flooded."
    _chat_returns(monkeypatch, json.dumps(raw), json.dumps(raw))
    out = recovery_report.write("flood", ANALYSIS_PHOTOS, {"own_rent": "rent"}, "en")
    assert out["guard_removed"] == ["ownership"] and out["attempts"] == 2
    assert out["en"]["summary"] == "A water line shows on the living room wall."
    assert out["en"]["details"]["landlord"].startswith("Since you rent") and "fema" not in out["en"]["details"]
