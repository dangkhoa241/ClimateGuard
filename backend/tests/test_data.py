"""Offline tests for the data layer (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, risk, snapshot
from climateguard.handlers import api, collect as collect_mod
from climateguard.sources import nws


# --- risk math ---

@pytest.mark.parametrize("t,rh,expected", [(90, 70, 106), (100, 40, 109), (96, 65, 121), (80, 40, 80)])
def test_heat_index_matches_nws_chart(t, rh, expected):
    assert abs(risk.heat_index_f(t, rh) - expected) <= 1


@pytest.mark.parametrize("aqi,cat", [(50, "Good"), (51, "Moderate"), (151, "Unhealthy"), (301, "Hazardous"),
                                     (-1, None), (None, None)])
def test_aqi_category(aqi, cat):
    assert risk.aqi_category(aqi) == cat


# --- NWS parsing ---

def _period(temp=100, rh=30, wind="5 to 10 mph", unit="F"):
    return {"startTime": "2026-07-15T15:00:00-07:00", "temperature": temp, "temperatureUnit": unit,
            "relativeHumidity": {"value": rh}, "windSpeed": wind,
            "probabilityOfPrecipitation": {"value": None}, "shortForecast": "Sunny"}


def test_parse_hourly():
    [h] = nws.parse_hourly({"properties": {"periods": [_period()]}})
    assert h["temp_f"] == 100 and h["wind_mph"] == 10 and h["precip_prob"] == 0
    assert h["heat_index_f"] == round(risk.heat_index_f(100, 30))
    [c] = nws.parse_hourly({"properties": {"periods": [_period(temp=40, unit="C")]}})
    assert c["temp_f"] == 104


def _alert(id_="a1", event="Excessive Heat Warning", msg="Alert", status="Actual", ends="2026-07-15T21:00:00-07:00",
           sent="2026-07-15T07:00:00-07:00"):
    return {"properties": {"id": id_, "event": event, "messageType": msg, "status": status, "severity": "Severe",
                           "urgency": "Expected", "certainty": "Likely", "headline": "h", "description": "d",
                           "instruction": "i", "sent": sent, "onset": None, "ends": ends, "expires": ends,
                           "references": [], "senderName": "NWS Sacramento CA"}}


def test_parse_alerts_skips_cancel_and_tests():
    alerts = nws.parse_alerts({"features": [_alert(), _alert("a2", msg="Cancel"), _alert("a3", status="Test")]})
    assert [a["id"] for a in alerts] == ["a1"]


# --- summary + fingerprint ---

def _hours(temps):
    return [{"time": f"2026-07-15T{i % 24:02d}:00:00-07:00", "temp_f": t, "rh": 20,
             "heat_index_f": t, "wind_mph": 5, "precip_prob": 0, "short": None} for i, t in enumerate(temps)]


def _aqi(now=40, fc=45):
    return {"source": "test", "current": {"aqi": now, "category": risk.aqi_category(now), "pm25_aqi": now},
            "forecast": [{"date": "2026-07-15", "aqi": fc}]}


def _fp(temps, aqi, alerts):
    return snapshot.fingerprint(snapshot.summarize(_hours(temps), aqi, alerts), alerts)


def test_summary_flags():
    s = snapshot.summarize(_hours([85, 96, 99, 70]), _aqi(160, 170), nws.parse_alerts({"features": [_alert()]}))
    assert s["max_temp_f"] == 99 and s["hours_ge_95f"] == 2 and s["hours_ge_80f"] == 3
    assert set(s["flags"]) == {"calosha_shade_80f", "calosha_high_heat_95f", "calosha_smoke_aqi_151",
                               "nws_alert_active"}


def test_fingerprint_ignores_reissued_alert():
    a1 = nws.parse_alerts({"features": [_alert("id-1", sent="2026-07-15T07:00:00-07:00")]})
    a2 = nws.parse_alerts({"features": [_alert("id-2", msg="Update", sent="2026-07-15T10:00:00-07:00")]})
    assert _fp([100], _aqi(), a1) == _fp([100], _aqi(), a2)


def test_fingerprint_ignores_small_temp_change():
    assert _fp([101], _aqi(), []) == _fp([102], _aqi(), [])


def test_fingerprint_changes_on_material_change():
    base = _fp([100], _aqi(), [])
    assert _fp([106], _aqi(), []) != base  # hotter bucket
    assert _fp([100], _aqi(120), []) != base  # AQI category jump
    assert _fp([100], _aqi(), nws.parse_alerts({"features": [_alert()]})) != base  # new alert
    extended = nws.parse_alerts({"features": [_alert(ends="2026-07-16T21:00:00-07:00")]})
    assert _fp([100], _aqi(), extended) != _fp([100], _aqi(), nws.parse_alerts({"features": [_alert()]}))


# --- collector + API (fake snapshots, local store in tmp dir) ---

@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    state = {"temps": [90], "errors": {}}

    def fake_build(slug):
        s = snapshot.summarize(_hours(state["temps"]), _aqi(), [])
        return {"city": slug, "name": slug.title(), "generated_at": "t", "forecast": {"source": "test", "hours": []},
                "aqi": _aqi(), "alerts": [], "summary": s, "errors": dict(state["errors"]),
                "fingerprint": snapshot.fingerprint(s, [])}

    monkeypatch.setattr(collect_mod, "build_snapshot", fake_build)
    return state


def test_collect_reports_changes_only_when_material(local):
    assert collect_mod.collect(["stockton"])["changed"] == ["stockton"]
    assert collect_mod.collect(["stockton"])["unchanged"] == ["stockton"]
    local["temps"] = [101]
    assert collect_mod.collect(["stockton"])["changed"] == ["stockton"]


def test_collect_keeps_last_good_snapshot_on_outage(local):
    collect_mod.collect(["stockton"])
    local["errors"] = {"alerts": "503 from api.weather.gov"}
    local["temps"] = [110]
    r = collect_mod.collect(["stockton"])
    assert "stockton" in r["failed"] and not r["changed"]


def test_api_routes(local):
    assert api.handler({"routeKey": "GET /cities"}, None)["statusCode"] == 200
    assert api.handler({"routeKey": "GET /cities/{city}", "pathParameters": {"city": "atlantis"}}, None)[
        "statusCode"] == 404
    assert api.handler({"routeKey": "GET /cities/{city}", "pathParameters": {"city": "lodi"}}, None)[
        "statusCode"] == 503
    collect_mod.collect(["lodi"])
    r = api.handler({"routeKey": "GET /cities/{city}", "pathParameters": {"city": "lodi"}}, None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["city"] == "lodi"


def test_calosha_flags_use_air_temperature_not_heat_index():
    # Humid 90F hour: heat index ~106F, but Cal/OSHA §3395 high-heat (95F) is based on air temperature.
    hour = {"time": "2026-07-15T15:00:00-07:00", "temp_f": 90, "rh": 70,
            "heat_index_f": round(risk.heat_index_f(90, 70)), "wind_mph": 5, "precip_prob": 0, "short": None}
    s = snapshot.summarize([hour], _aqi(), [])
    assert s["max_heat_index_f"] >= 105  # reported separately as info
    assert s["hours_ge_95f"] == 0 and s["first_hour_ge_95f"] is None
    assert "calosha_high_heat_95f" not in s["flags"] and "calosha_shade_80f" in s["flags"]


def test_handler_runs_agent_only_for_changed_cities(local, monkeypatch):
    from climateguard import monitor
    calls = []
    monkeypatch.setattr(monitor, "run_monitor", lambda slug: calls.append(slug) or
                        {"action": "skipped", "reason": "test", "cost_usd": 0})
    monkeypatch.setattr(collect_mod, "CITIES", {"stockton": {}, "lodi": {}})
    collect_mod.handler({}, None)
    assert sorted(calls) == ["lodi", "stockton"]  # first run: both new
    calls.clear()
    r = collect_mod.handler({}, None)
    assert calls == [] and r["decisions"] == {}  # nothing changed: no agent, no spend


def test_source_errors_never_contain_query_params(monkeypatch):
    import requests
    from climateguard.sources import http

    class Resp:
        status_code, reason = 410, "Gone"

        def raise_for_status(self):
            raise requests.HTTPError("410 Client Error for url: https://x.example/aq?API_KEY=SECRET-123")

    monkeypatch.setattr(http._session, "get", lambda *a, **k: Resp())
    with pytest.raises(http.SourceError) as exc:
        http.get_json("https://x.example/aq", params={"API_KEY": "SECRET-123"})
    assert "SECRET" not in str(exc.value) and "410" in str(exc.value)


# --- AirNow replacement services (shapes captured from live responses, 2026-10-27) ---

def test_airnow_parsing_new_format():
    from climateguard.sources import airnow

    obs = [{"dateObserved": "2026-10-27", "hourObserved": "14:00", "reportingAreaName": "Stockton",
            "parameterName": "PM2.5", "nowcastAQI": 162, "aqiCategoryName": "Unhealthy"},
           {"dateObserved": "2026-10-27", "hourObserved": "14:00", "reportingAreaName": "Stockton",
            "parameterName": "OZONE", "nowcastAQI": 40, "aqiCategoryName": "Good"},
           {"parameterName": "PM10", "nowcastAQI": -1}]
    cur = airnow.parse_observations(obs)
    assert (cur["aqi"], cur["category"], cur["pollutant"], cur["pm25_aqi"]) == (162, "Unhealthy", "PM2.5", 162)
    assert cur["observed_at"].startswith("2026-10-27T14:00")

    fc = airnow.parse_forecast([
        {"dateValid": "2026-10-27", "parameterName": "PM2.5", "aqi": 62, "categoryNumber": 2,
         "categoryName": "Moderate", "actionDay": False},
        {"dateValid": "2026-10-27", "parameterName": "OZONE", "aqi": -1, "categoryNumber": 1,
         "categoryName": "Good", "actionDay": False},
        {"dateValid": "2026-10-28", "parameterName": "PM2.5", "aqi": -1, "categoryNumber": 4,
         "categoryName": "Unhealthy", "actionDay": True},
    ])
    assert fc == [
        {"date": "2026-10-27", "aqi": 62, "category": "Moderate", "pollutant": "PM2.5", "action_day": False},
        {"date": "2026-10-28", "aqi": None, "category": "Unhealthy", "pollutant": "PM2.5", "action_day": True},
    ]


def test_airnow_key_from_ssm_when_env_missing(monkeypatch):
    from climateguard import ssm
    from climateguard.sources import airnow

    monkeypatch.setattr(config, "AIRNOW_API_KEY", "")
    monkeypatch.setattr(config, "AIRNOW_API_KEY_PARAM", "")
    assert not airnow.enabled()  # no key anywhere -> Open-Meteo fallback
    monkeypatch.setattr(config, "AIRNOW_API_KEY_PARAM", "/climateguard/airnow-api-key")
    monkeypatch.setattr(ssm, "get_secret", lambda name: "KEY-FROM-SSM")
    assert airnow.enabled() and airnow._params(1, 2)["API_KEY"] == "KEY-FROM-SSM"
