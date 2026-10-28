"""Offline tests: °F/°C formatting in code, and the "warning ending with no hazard left" guardrail."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import pytest

from climateguard import alerts_store, config, monitor, notify, replays, scenarios as sc, units, zones


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")


# --- temperatures ---

@pytest.mark.parametrize("lang,text,expected", [
    ("en", "up to 114F today", "up to 114°F today"),
    ("en", "up to 114 °F", "up to 114°F"),
    ("vi", "lên đến 114F.", "lên đến 114°F (46°C)."),
    ("vi", "lên đến 114 độ F, rất nóng", "lên đến 114°F (46°C), rất nóng"),
    ("es", "hasta 95 grados F", "hasta 95°F (35°C)"),
    ("vi", "lạnh -5F", "lạnh -5°F (-21°C)"),
    ("vi", "đeo khẩu trang N95", "đeo khẩu trang N95"),
    ("es", "a las 5 PM", "a las 5 PM"),
])
def test_temperature_formatting(lang, text, expected):
    assert units.format_temps(text, lang) == expected
    assert units.format_temps(expected, lang) == expected  # idempotent


def test_send_alert_stores_both_units_for_non_english():
    run = monitor.Run(zone="CAZ159", snapshot=sc.build("heatwave"), namespace="EVAL-units")
    r = monitor.tool_send_alert(run, {"zone": "CAZ159", "hazard": "heat", "severity": "extreme", "reason": "r",
                                      "messages_by_language": {"en": "Highs up to 108F today.",
                                                               "es": "Máxima de 108F hoy.",
                                                               "vi": "Hôm nay (thứ Ba), nhiệt độ lên đến 108F."}})
    assert r["sent"]
    [row] = alerts_store.recent_sent("EVAL-units")
    assert row["messages"]["en"] == "Highs up to 108°F today."
    assert "108°F (42°C)" in row["messages"]["es"] and "108°F (42°C)" in row["messages"]["vi"]


def test_translated_alerts_get_both_units(monkeypatch):
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: ("最高 108F。", True))
    zone = dict(zones.DEMO_ZONES["CAZ159"], langs=["zh"])
    notify.deliver(zone, "heat", "extreme", {"en": "Highs 108F.", "es": "x", "vi": "y"})
    outbox = (config.LOCAL_DIR / "outbox.jsonl").read_text(encoding="utf-8")
    assert "108°F (42°C)" in outbox


# --- warning ending with no hazard left ---

def _snap(temp_peak, rh, hours_left, event="Extreme Heat Warning", aqi_now=45):
    def parts(tz):
        curve = sc.heat_curve(temp_peak) if temp_peak >= 90 else (lambda h: temp_peak)
        return {"hours": sc.hours(tz, curve, lambda h: rh), "aqi": sc.aqi(tz, aqi_now, [aqi_now, aqi_now]),
                "alerts": [sc.nws_alert(tz, event, "Severe", hours_left, event, "d", "i")]}
    return sc.assemble("CAZ159", parts(ZoneInfo("America/Los_Angeles")), "t")


def _try(snap, hazard="heat"):
    run = monitor.Run(zone="CAZ159", snapshot=snap, namespace="EVAL-g")
    return monitor.validate_alert(run, {"zone": "CAZ159", "hazard": hazard, "severity": "extreme", "reason": "r",
                                        "messages_by_language": {"en": "Heat.", "es": "Calor.",
                                                                 "vi": "Nắng nóng."}})


def test_warning_ending_with_mild_weather_is_rejected():
    reason = _try(_snap(76, 40, hours_left=2))
    assert reason and "danger is over" in reason and "76°F" in reason


def test_warning_ending_but_heat_returns_is_allowed():
    assert _try(_snap(104, 20, hours_left=2)) is None


def test_long_warning_with_mild_data_is_allowed():
    # "trust the official warning" case: plenty of time left, so the data mismatch doesn't block it
    assert _try(_snap(82, 40, hours_left=30)) is None


def test_air_alert_ending_with_clean_air_is_rejected_but_dirty_air_is_not():
    assert "danger is over" in _try(_snap(80, 35, 1, event="Air Quality Alert", aqi_now=42), hazard="smoke")
    assert _try(_snap(80, 35, 1, event="Air Quality Alert", aqi_now=160), hazard="smoke") is None


def test_hours_left_uses_the_replay_time():
    snap = replays.snapshot_for("heat_2022", "record_day_morning")  # Sept 6 2022, 07:00; warning ends Sept 9 20:00
    run = monitor.Run(zone="CAZ159", snapshot=snap)
    assert run.now == datetime.fromisoformat("2022-09-06T07:00:00-07:00")
    assert run.hours_left(snap["alerts"][0]) == 85.0
