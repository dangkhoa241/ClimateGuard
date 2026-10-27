"""Monitoring agent: Muse Spark Open on Baseten with tool calling.

For one city it gathers data through tools, decides on its own whether risk
warrants an alert, writes it in English, Spanish and Vietnamese, and sends it.
Every run ends with one decision-log entry (sent / skipped / error, and why).

Guardrails enforced in code, not just in the prompt:
  - dedup: same hazard at same-or-lower severity within COOLDOWN_HOURS is rejected
  - daily cap per city (bypassed only by an alert more severe than all sent in 24h),
    required languages, message length, no medical wording
  - only the city under review can be queried or alerted
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from . import alerts_store, config, guidance, notify, risk
from .cities import TIMEZONE, get_city
from .llm import chat
from .store import get_store

log = logging.getLogger(__name__)
_TZ = ZoneInfo(TIMEZONE)

MAX_STEPS = 8
MAX_TOKENS_PER_STEP = 2500  # includes reasoning
LANGS = ("en", "es", "vi")
SEVERITIES = {"moderate": 1, "high": 2, "extreme": 3}
HAZARDS = ("heat", "smoke", "flood", "wind", "cold", "fog", "other")
COOLDOWN_HOURS = 12
MAX_ALERTS_PER_DAY = 3
MAX_MESSAGE_CHARS = 400
# Alerts give protective actions only. Reject wording that drifts into medical advice.
MEDICAL_TERMS = re.compile(r"diagnos|symptom|medicat|dosage|ibuprofen|aspirin|acetaminophen|"
                           r"s[ií]ntoma|diagn[oó]stic|medicamento|tri[eệ]u ch[uứ]ng|thu[oố]c", re.IGNORECASE)

SYSTEM_PROMPT = """You are ClimateGuard's monitoring agent for farmworkers and immigrant families in California's Central Valley.
You review ONE city at a time and decide whether people there need an alert right now.

How to work:
1. Check the data with tools: get_nws_alerts, get_forecast, get_aqi, and get_recent_alerts_sent.
2. Decide. Send an alert only for real, near-term risk, for example:
   - an active NWS warning or advisory for heat, flood, wind, smoke/air quality, fog, or freeze;
   - air temperature at or above 95F in the next 24 hours (Cal/OSHA high-heat level for outdoor work);
   - AQI at or above 151 now or forecast, or 101-150 with smoke;
   - high chance of heavy rain with flood risk.
   Do not alert for normal conditions. Do not repeat an alert already sent for the same hazard unless the
   risk got worse (higher severity) or there is important new information.
3. Before writing, call search_safety_guidance to ground the protective actions in official guidance.
4. To alert, call send_alert once per hazard. Messages in English (en), Spanish (es, natural, use "usted"),
   and Vietnamese (vi, natural). Each message: at most 2 short sentences, simple words, say WHEN
   (time window) and 1-2 concrete actions (water, shade, rest, stay indoors, avoid floodwater...).
   Write each language the way a native speaker would say it, not word-for-word from English.
   No abbreviations, slashes, or jargon (write "air conditioning"/"aire acondicionado"/"máy lạnh", full day names).
   Severity: moderate, high, or extreme.
5. Never give medical advice: no symptoms, diagnoses, or medicines. Protective actions only.
6. Finish with a plain-text explanation of 1-3 sentences that starts with "SENT:" or "SKIPPED:" and says why."""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_forecast",
        "description": "Hourly forecast for the next 24 hours (air temperature, heat index, rain chance) plus a "
                       "summary with Cal/OSHA flags. Cal/OSHA thresholds use air temperature, not heat index.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_aqi",
        "description": "Current air quality (US AQI, category, main pollutant) and daily AQI forecast.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_nws_alerts",
        "description": "Active National Weather Service alerts for the city (event, severity, timing, instructions).",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_recent_alerts_sent",
        "description": "Alerts ClimateGuard already sent to this city in the last 48 hours. Use it to avoid duplicates.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "search_safety_guidance",
        "description": "Search official safety guidance (Cal/OSHA, NWS, CDC, EPA AirNow, FEMA). "
                       "Returns short excerpts with sources.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "send_alert",
        "description": "Send one alert to all subscribers in the city. Rejected if it duplicates a recent alert.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string"},
            "hazard": {"type": "string", "enum": list(HAZARDS)},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "messages_by_language": {
                "type": "object",
                "properties": {lang: {"type": "string"} for lang in LANGS},
                "required": list(LANGS)},
            "reason": {"type": "string", "description": "One sentence: why this alert is needed now."}},
            "required": ["city", "hazard", "severity", "messages_by_language", "reason"]}}},
]


def _local_time(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(_TZ).strftime("%a %H:%M")


@dataclass
class Run:
    city: str
    snapshot: dict
    sent: list = field(default_factory=list)
    tool_log: list = field(default_factory=list)
    cost_usd: float = 0.0


# --- tools -----------------------------------------------------------------

def _check_city(run: Run, args: dict):
    asked = str(args.get("city", "")).strip().lower()
    if asked not in (run.city, run.snapshot["name"].lower()):
        return {"error": f"This run is only for {run.snapshot['name']} (city='{run.city}')."}
    return None


def tool_get_forecast(run: Run, args: dict) -> dict:
    if err := _check_city(run, args):
        return err
    s = run.snapshot["summary"]
    hours = [f"{_local_time(h['time'])} | {h['temp_f']}F | heat index {h['heat_index_f']}F | "
             f"rain {h['precip_prob']}%" + (f" | {h['short']}" if h.get("short") else "")
             for h in run.snapshot["forecast"]["hours"][:24]]
    keys = ("max_temp_f", "max_temp_time", "max_heat_index_f", "hours_ge_80f", "hours_ge_95f",
            "first_hour_ge_95f", "max_precip_prob", "flags")
    summary = {k: s.get(k) for k in keys}
    for k in ("max_temp_time", "first_hour_ge_95f"):
        if summary.get(k):
            summary[k] = _local_time(summary[k])
    return {"source": run.snapshot["forecast"]["source"], "summary": summary, "hourly_local_time": hours}


def tool_get_aqi(run: Run, args: dict) -> dict:
    if err := _check_city(run, args):
        return err
    return run.snapshot.get("aqi") or {"error": "air quality data unavailable"}


def tool_get_nws_alerts(run: Run, args: dict) -> dict:
    if err := _check_city(run, args):
        return err
    keep = ("event", "message_type", "severity", "urgency", "headline", "onset", "ends", "expires",
            "description", "instruction")
    return {"active_alerts": [{k: a.get(k) for k in keep} for a in run.snapshot.get("alerts", [])]}


def tool_get_recent_alerts_sent(run: Run, args: dict) -> dict:
    if err := _check_city(run, args):
        return err
    rows = alerts_store.recent_sent(run.city, hours=48)
    return {"alerts_sent_last_48h": [{"sent_at": _local_time(r["ts"]), "hazard": r["hazard"],
                                      "severity": r["severity"], "message_en": r["messages"].get("en")}
                                     for r in rows]}


def tool_search_safety_guidance(run: Run, args: dict) -> dict:
    return {"results": guidance.search(str(args.get("query", "")), k=3)}


def validate_alert(run: Run, args: dict) -> str | None:
    """Return a rejection reason, or None if the alert may be sent."""
    hazard, severity = args.get("hazard"), args.get("severity")
    msgs = args.get("messages_by_language") or {}
    if hazard not in HAZARDS:
        return f"hazard must be one of {HAZARDS}"
    if severity not in SEVERITIES:
        return f"severity must be one of {tuple(SEVERITIES)}"
    for lang in LANGS:
        text = (msgs.get(lang) or "").strip()
        if not text:
            return f"missing message for language '{lang}'"
        if len(text) > MAX_MESSAGE_CHARS:
            return f"message '{lang}' is {len(text)} characters; keep it under {MAX_MESSAGE_CHARS}"
        if MEDICAL_TERMS.search(text):
            return (f"message '{lang}' mentions symptoms/diagnosis/medicine. Alerts must give protective "
                    "actions only; rewrite without medical content")
    recent = alerts_store.recent_sent(run.city, hours=24)
    if len(recent) >= MAX_ALERTS_PER_DAY:
        # An alert more severe than everything sent in the last 24h always goes through.
        highest_sent = max(SEVERITIES.get(r["severity"], 0) for r in recent)
        if SEVERITIES[severity] <= highest_sent:
            return (f"daily cap reached ({MAX_ALERTS_PER_DAY} alerts in 24h for this city); only an alert more "
                    f"severe than every alert already sent today can go through")
    for r in alerts_store.recent_sent(run.city, hours=COOLDOWN_HOURS):
        if r["hazard"] == hazard and SEVERITIES.get(r["severity"], 0) >= SEVERITIES[severity]:
            return (f"duplicate: a {r['severity']} {hazard} alert was already sent at {_local_time(r['ts'])}. "
                    "Only send again if severity increases.")
    return None


def tool_send_alert(run: Run, args: dict) -> dict:
    if err := _check_city(run, args):
        return err
    if rejection := validate_alert(run, args):
        return {"sent": False, "rejected": rejection}
    msgs = {lang: args["messages_by_language"][lang].strip() for lang in LANGS}
    alerts_store.record_sent(run.city, args["hazard"], args["severity"], msgs, args.get("reason", ""))
    delivery = notify.deliver(run.city, args["hazard"], args["severity"], msgs)
    run.sent.append({"hazard": args["hazard"], "severity": args["severity"], "messages": msgs})
    return {"sent": True, "delivery": delivery}


TOOL_FUNCS = {
    "get_forecast": tool_get_forecast,
    "get_aqi": tool_get_aqi,
    "get_nws_alerts": tool_get_nws_alerts,
    "get_recent_alerts_sent": tool_get_recent_alerts_sent,
    "search_safety_guidance": tool_search_safety_guidance,
    "send_alert": tool_send_alert,
}


# --- pre-filter + agent loop -------------------------------------------------

def risk_signals(summary: dict) -> list[str]:
    """Cheap, deterministic check: is there anything worth an agent run (and model spend)?"""
    signals = []
    if summary.get("active_alerts"):
        signals.append(f"NWS alerts: {', '.join(summary['active_alerts'])}")
    if (summary.get("hours_ge_95f") or 0) > 0:
        signals.append(f"{summary['hours_ge_95f']}h at or above 95F")
    if (summary.get("max_heat_index_f") or 0) >= 100:
        signals.append(f"heat index up to {summary['max_heat_index_f']}F")
    aqi_max = max(summary.get("aqi_now") or 0, summary.get("aqi_forecast_max") or 0)
    if aqi_max >= 101:
        signals.append(f"AQI up to {aqi_max} ({risk.aqi_category(aqi_max)})")
    if (summary.get("max_precip_prob") or 0) >= 60:
        signals.append(f"rain chance {summary['max_precip_prob']}%")
    return signals


def _assistant_history_message(message: dict) -> dict:
    # Never send reasoning_content back: not needed (verified) and it would cost input tokens.
    out = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        out["tool_calls"] = [{"id": tc["id"], "type": "function",
                              "function": {"name": tc["function"]["name"],
                                           "arguments": tc["function"]["arguments"]}}
                             for tc in message["tool_calls"]]
    return out


def run_monitor(city: str, snapshot: dict | None = None, *, force: bool = False,
                reasoning_effort: str | None = None) -> dict:
    """Run the monitoring agent for one city. Returns the decision-log entry.

    `snapshot` defaults to the latest stored one (demo mode passes a seeded one).
    `force` skips the deterministic pre-filter.
    """
    get_city(city)
    snapshot = snapshot or get_store().get_latest(city)
    if snapshot is None:
        return alerts_store.log_decision(city, "error", "no snapshot available")

    signals = risk_signals(snapshot["summary"])
    if not signals and not force:
        return alerts_store.log_decision(city, "skipped", "pre-filter: no risk signals in the data, agent not called",
                                         fingerprint=snapshot.get("fingerprint"), model_calls=0, cost_usd=0.0)

    run = Run(city=city, snapshot=snapshot)
    now_local = datetime.now(_TZ).strftime("%A %Y-%m-%d %H:00")  # hour granularity: retries hit the cache
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (f"City: {snapshot['name']} (city='{city}'). Local time: {now_local}. "
                                     f"Data was refreshed and these risk signals were detected: "
                                     f"{'; '.join(signals) or 'none (forced run)'}. Review and decide.")},
    ]
    final_text, calls = "", 0
    try:
        for _ in range(MAX_STEPS):
            res = chat("baseten", config.MONITOR_MODEL, messages, max_tokens=MAX_TOKENS_PER_STEP,
                       tools=TOOLS, reasoning_effort=reasoning_effort, purpose=f"monitor:{city}")
            calls += 1
            run.cost_usd += res.cost_usd
            message = res.raw["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final_text = res.text
                break
            messages.append(_assistant_history_message(message))
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                func = TOOL_FUNCS.get(name)
                result = func(run, args) if func else {"error": f"unknown tool {name}"}
                run.tool_log.append({"tool": name, "args": {k: v for k, v in args.items()
                                                            if k != "messages_by_language"},
                                     "ok": "error" not in result and not result.get("rejected"),
                                     **({"rejected": result["rejected"]} if result.get("rejected") else {})})
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(result, ensure_ascii=False)})
        else:
            final_text = f"step limit ({MAX_STEPS}) reached before a final answer"
    except Exception as e:
        log.exception("monitor run failed for %s", city)
        return alerts_store.log_decision(city, "error", f"{type(e).__name__}: {e}", signals=signals,
                                         tools=run.tool_log, sent=run.sent, model_calls=calls,
                                         cost_usd=round(run.cost_usd, 6))

    action = "sent" if run.sent else "skipped"
    reason = re.sub(r"^\s*(SENT|SKIPPED)\s*:\s*", "", final_text).strip() or "(no explanation given)"
    return alerts_store.log_decision(city, action, reason, signals=signals, tools=run.tool_log, sent=run.sent,
                                     fingerprint=snapshot.get("fingerprint"), model_calls=calls,
                                     cost_usd=round(run.cost_usd, 6))
