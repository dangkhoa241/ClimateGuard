"""Daily counters for the public decision history: what the live system did each day,
including the many runs where nothing changed (those write no decision entry).

dynamodb -> RATELIMIT_TABLE item k="stats#<YYYY-MM-DD>" (atomic ADD per counter)
local    -> backend/.local/stats.json
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import config

COUNTERS = ("collector_runs", "zone_checks", "data_changes", "prefilter_skips", "agent_runs",
            "budget_skips", "alerts_sent", "errors")


def _day(d: datetime | None = None) -> str:
    return (d or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.RATELIMIT_TABLE)


def summarize_run(result: dict) -> dict:
    """Counters for one collector run (collect() result with "decisions")."""
    c = {"collector_runs": 1, "zone_checks": result.get("zones", 0), "data_changes": len(result.get("changed", [])),
         "errors": len(result.get("failed", {})), "model_cost_usd": 0.0}
    for d in (result.get("decisions") or {}).values():
        reason = d.get("reason") or ""
        if d.get("action") == "error":
            c["errors"] += 1
        elif reason.startswith("pre-filter"):
            c["prefilter_skips"] = c.get("prefilter_skips", 0) + 1
        elif "budget" in reason:
            c["budget_skips"] = c.get("budget_skips", 0) + 1
        else:
            c["agent_runs"] = c.get("agent_runs", 0) + 1
        c["alerts_sent"] = c.get("alerts_sent", 0) + int(d.get("alerts_sent") or 0)
        c["model_cost_usd"] += float(d.get("cost_usd") or 0)
    return c


def record(counts: dict) -> None:
    day = _day()
    if config.STORAGE == "dynamodb":
        names, values, parts = {}, {}, []
        for i, (k, v) in enumerate(counts.items()):
            if v:
                names[f"#c{i}"], values[f":v{i}"] = k, Decimal(str(round(v, 6)))
                parts.append(f"#c{i} :v{i}")
        if parts:
            _table().update_item(Key={"k": f"stats#{day}"}, UpdateExpression="ADD " + ", ".join(parts),
                                 ExpressionAttributeNames=names, ExpressionAttributeValues=values)
        return
    path = config.LOCAL_DIR / "stats.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = data.setdefault(day, {})
    for k, v in counts.items():
        today[k] = round(today.get(k, 0) + v, 6)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def recent(days: int = 7) -> list[dict]:
    wanted = [_day(datetime.now(timezone.utc) - timedelta(days=i)) for i in range(days)]
    if config.STORAGE == "dynamodb":
        out = []
        for d in wanted:
            item = _table().get_item(Key={"k": f"stats#{d}"}).get("Item")
            if item:
                out.append({"day": d, **{k: float(v) for k, v in item.items() if k != "k"}})
        return out
    path = config.LOCAL_DIR / "stats.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return [{"day": d, **data[d]} for d in wanted if d in data]


def totals(rows: list[dict]) -> dict:
    t = {k: 0 for k in COUNTERS} | {"model_cost_usd": 0.0}
    for r in rows:
        for k in t:
            t[k] += r.get(k, 0)
    t["model_cost_usd"] = round(t["model_cost_usd"], 4)
    return {k: (int(v) if k != "model_cost_usd" else v) for k, v in t.items()}
