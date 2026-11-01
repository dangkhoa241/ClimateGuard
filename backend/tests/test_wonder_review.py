"""Offline tests for the eval-only Muse Wonder reviewer (scripts/wonder_review.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import wonder_review as wr  # noqa: E402
from climateguard import scenarios as sc  # noqa: E402

FLOOD_OK = {"en": "Flood Warning until tonight. Never walk or drive through floodwater.",
            "es": "Aviso de inundación. Nunca camine ni maneje por agua de inundación.",
            "vi": "Cảnh báo lũ lụt. Tuyệt đối không đi bộ hoặc lái xe qua vùng nước ngập."}


def test_cost_matches_published_rates():
    assert wr.cost_usd(1_000_000, 0, 0) == 4.0
    assert wr.cost_usd(0, 0, 1_000_000) == 20.0
    assert round(wr.cost_usd(1_000_000, 1_000_000, 0), 2) == 0.20  # all cached


def test_reviewer_refuses_a_call_that_could_pass_the_cap(monkeypatch):
    r = wr.Reviewer(cap_usd=0.05)  # one worst-case call (6000 output tokens) is already $0.12
    monkeypatch.setattr(r, "_openai", lambda: (_ for _ in ()).throw(AssertionError("must not call the API")))
    out = wr.review(r, sc.build("flood"), "flood", "high", FLOOD_OK)
    assert out.get("_cap") and r.calls == 0 and r.spent_usd == 0


def test_our_checks_pass_for_a_clean_flood_alert():
    assert all(wr.our_checks(sc.build("flood"), "flood", FLOOD_OK).values())


def test_our_checks_catch_each_rule():
    snap = sc.build("flood")
    weak = {**FLOOD_OK, "en": "Flood Warning. Avoid floodwater."}
    assert wr.our_checks(snap, "flood", weak)["flood_wording"] is False
    assert wr.our_checks(snap, "flood", {**FLOOD_OK, "en": FLOOD_OK["en"] + " Wear an N95 mask."})["n95_only_smoke"] is False
    assert wr.our_checks(snap, "flood", {**FLOOD_OK, "en": FLOOD_OK["en"] + " A Flood Watch is also out."})["no_watch_with_warning"] is False
    assert wr.our_checks(snap, "flood", {**FLOOD_OK, "en": FLOOD_OK["en"] + " Take ibuprofen."})["no_medical_advice"] is False
    assert wr.our_checks(snap, "flood", {**FLOOD_OK, "en": FLOOD_OK["en"] + " Your home is safe to re-enter."})["no_building_safe_verdict"] is False
    assert wr.our_checks(snap, "flood", {**FLOOD_OK, "en": FLOOD_OK["en"] + " Repairs cost $5,000."})["no_repair_costs"] is False


def test_disagreements_list_checks_and_meaning():
    alert = {"hazard": "flood", "our_checks": {"flood_wording": True, "no_repair_costs": True},
             "wonder": {"checks": {"flood_wording": {"pass": False, "reason": "says avoid"},
                                   "no_repair_costs": {"pass": True, "reason": "ok"}},
                        "backtranslation": {"es": {"match": False, "issues": ["time changed"], "back_translation": ""},
                                            "vi": {"match": True, "issues": [], "back_translation": ""}}},
             "backcheck": {"es": {"match": True, "issues": []}, "vi": {"match": True, "issues": []}}}
    got = {(d["check"], d["ours"], d["wonder"]) for d in wr.disagreements("case", alert)}
    assert got == {("flood_wording", "pass", "fail"), ("meaning (es)", "match", "mismatch")}
