"""Offline tests for US-wide lite: hazard groups, short-fuse exclusion, national alert
matching, zone registry and monitored zones, ZIP lookup, snapshot reuse."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, geo, hazards, monitor, snapshot, zones
from climateguard.sources import nws

TZ_ZONE = {"zone": "MNZ060", "name": "Hennepin", "county": "MNC053", "fire_zone": "MNZ060", "state": "MN",
           "tz": "America/Chicago", "lat": 44.98, "lon": -93.27, "forecast_hourly": "x"}


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")


def _hours(temp=70, wind=5, n=24):
    return [{"time": f"2026-07-15T{i % 24:02d}:00:00-05:00", "temp_f": temp, "rh": 40, "heat_index_f": temp,
             "wind_mph": wind, "precip_prob": 0, "short": None} for i in range(n)]


def _aqi(now=40):
    return {"source": "t", "current": {"aqi": now, "category": "Good", "pm25_aqi": now}, "forecast": []}


def _alert(event, ugc, ends="2026-07-15T21:00:00-05:00"):
    return nws.parse_alerts({"features": [{"properties": {
        "id": f"id-{event}", "event": event, "messageType": "Alert", "status": "Actual", "severity": "Severe",
        "urgency": "Expected", "certainty": "Likely", "headline": "h", "description": "d", "instruction": "i",
        "sent": "s", "onset": None, "ends": ends, "expires": ends, "references": [], "senderName": "NWS",
        "geocode": {"UGC": ugc}}}]})[0]


# --- hazard groups and exclusion ---

@pytest.mark.parametrize("event,group", [
    ("Extreme Heat Warning", "heat"), ("Heat Advisory", "heat"), ("Extreme Cold Warning", "cold"),
    ("Wind Chill Advisory", "cold"), ("Freeze Warning", "cold"), ("Winter Storm Warning", "winter"),
    ("Blizzard Warning", "winter"), ("Flood Warning", "flood"), ("Flash Flood Watch", "flood"),
    ("Coastal Flood Advisory", "coastal"), ("Rip Current Statement", "coastal"), ("Tornado Watch", "tornado"),
    ("Severe Thunderstorm Watch", "thunderstorm"), ("Hurricane Warning", "tropical"),
    ("Tropical Storm Watch", "tropical"), ("High Wind Warning", "wind"), ("Red Flag Warning", "fire"),
    ("Air Quality Alert", "smoke"), ("Dust Storm Warning", "dust"), ("Dense Fog Advisory", "fog"),
    ("Special Weather Statement", "other"),
])
def test_every_nws_hazard_maps_to_a_group(event, group):
    assert hazards.group_for(event) == group and group in monitor.HAZARDS


@pytest.mark.parametrize("event", ["Tornado Warning", "Flash Flood Warning", "Severe Thunderstorm Warning",
                                   "Extreme Wind Warning"])
def test_short_fuse_warnings_are_excluded(event):
    assert hazards.is_excluded(event)


@pytest.mark.parametrize("event", ["Tornado Watch", "Flash Flood Watch", "Severe Thunderstorm Watch",
                                   "High Wind Warning", "Flood Warning"])
def test_longer_fuse_products_are_not_excluded(event):
    assert not hazards.is_excluded(event)


def test_national_alerts_matched_by_zone_county_or_fire_zone():
    zone = {"zone": "CAZ159", "county": "CAC077", "fire_zone": "CAZ259"}
    national = [_alert("Extreme Heat Warning", ["CAZ159", "CAZ160"]),  # forecast zone
                _alert("Flood Warning", ["CAC077"]),                   # county-based product
                _alert("Red Flag Warning", ["CAZ259"]),                # fire weather zone
                _alert("Wind Advisory", ["NVZ001"]),                   # elsewhere
                _alert("Flash Flood Warning", ["CAC077"])]             # excluded short-fuse
    handled, excluded = nws.alerts_for_zone(national, zone)
    assert [a["event"] for a in handled] == ["Extreme Heat Warning", "Flood Warning", "Red Flag Warning"]
    assert [a["event"] for a in excluded] == ["Flash Flood Warning"]


def test_excluded_warning_never_triggers_agent_or_changes_fingerprint(monkeypatch):
    monkeypatch.setattr(snapshot, "_fetch_forecast", lambda z: ("test", _hours(), None))
    monkeypatch.setattr(snapshot, "_fetch_aqi", lambda z: (_aqi(), None))
    calm = snapshot.build_snapshot(TZ_ZONE, [])
    tornado = snapshot.build_snapshot(TZ_ZONE, [_alert("Tornado Warning", ["MNC053"])])
    assert tornado["fingerprint"] == calm["fingerprint"] and tornado["alerts"] == []
    assert tornado["excluded_alerts"][0]["event"] == "Tornado Warning"
    assert monitor.risk_signals(tornado["summary"]) == []


def test_watch_for_same_hazard_does_trigger_agent(monkeypatch):
    monkeypatch.setattr(snapshot, "_fetch_forecast", lambda z: ("test", _hours(), None))
    monkeypatch.setattr(snapshot, "_fetch_aqi", lambda z: (_aqi(), None))
    watch = snapshot.build_snapshot(TZ_ZONE, [_alert("Tornado Watch", ["MNC053"])])
    assert monitor.risk_signals(watch["summary"]) == ["NWS alerts: Tornado Watch"]


def test_fresh_forecast_and_aqi_are_reused(monkeypatch):
    calls = {"fc": 0, "aqi": 0}
    monkeypatch.setattr(snapshot, "_fetch_forecast",
                        lambda z: calls.update(fc=calls["fc"] + 1) or ("t", _hours(), None))
    monkeypatch.setattr(snapshot, "_fetch_aqi", lambda z: calls.update(aqi=calls["aqi"] + 1) or (_aqi(), None))
    first = snapshot.build_snapshot(TZ_ZONE, [])
    snapshot.build_snapshot(TZ_ZONE, [], prev=first)
    assert calls == {"fc": 1, "aqi": 1}  # the second build reused both


def test_cold_and_wind_change_fingerprint_only_when_material():
    def fp(min_t, wind):
        s = snapshot.summarize(_hours(min_t, wind), _aqi(), [])
        return snapshot.fingerprint(s, [])
    assert fp(52, 10) == fp(51, 20)   # mild and breezy: no change
    assert fp(52, 10) != fp(20, 10)   # hard freeze
    assert fp(52, 10) != fp(52, 45)   # damaging wind


def test_cold_and_wind_are_risk_signals():
    assert "low of 12F" in monitor.risk_signals(snapshot.summarize(_hours(12), _aqi(), []))
    assert "wind up to 45 mph" in monitor.risk_signals(snapshot.summarize(_hours(60, 45), _aqi(), []))


# --- ZIP / coordinates / registry ---

def test_zip_lookup_and_coordinate_rounding():
    assert geo.zip_to_point("95202") == (37.9597, -121.2883)
    assert geo.coarse_point("37.95973", "-121.28829") == (37.96, -121.29)
    for bad, code in (("1234", "invalid_zip"), ("00000", "unknown_zip")):
        with pytest.raises(geo.GeoError, match=code):
            geo.zip_to_point(bad)
    with pytest.raises(geo.GeoError, match="outside_us"):
        geo.coarse_point(48.85, 2.35)  # Paris


def test_locate_registers_zone_once(monkeypatch):
    calls = []

    def fake_resolve(lat, lon):
        calls.append((lat, lon))
        return {**TZ_ZONE, "place": "Minneapolis, MN", "demo": False}
    monkeypatch.setattr(zones, "resolve_point", fake_resolve)
    a = zones.locate(zip_code="55401")
    b = zones.get("MNZ060")
    assert a["zone"] == b["zone"] == "MNZ060" and a["confirmed"] == 0 and len(calls) == 1


def test_only_confirmed_and_demo_zones_are_monitored(monkeypatch):
    monkeypatch.setattr(zones, "resolve_point", lambda lat, lon: {**TZ_ZONE, "demo": False})
    zones.locate(zip_code="55401")
    assert sorted(z["zone"] for z in zones.monitored()) == ["CAZ159", "CAZ303"]  # pending only: not monitored
    zones.put({**zones.get("MNZ060"), "confirmed": 1})
    assert "MNZ060" in [z["zone"] for z in zones.monitored()]


def test_add_language_tracks_signup_languages(monkeypatch):
    zones.add_language("CAZ159", "ko")
    zones.add_language("CAZ159", "es")
    zones.add_language("CAZ159", "ko")
    assert zones.get("CAZ159")["langs"] == ["es", "ko"]
