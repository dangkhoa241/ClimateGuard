# ClimateGuard

A multilingual climate-disaster agent for California's Central Valley (Stockton first). It is built for farmworkers and immigrant families who often miss English-only warnings.

- **Alerts (before and during a disaster):** a monitoring agent watches heat, wildfire smoke and NWS alerts. It decides when risk is high, writes short alerts in English, Spanish and Vietnamese, skips duplicates, and emails subscribers by city.
- **Ask:** people ask by text or voice in their own language and get answers based on live data for their city.
- **Recovery (after a disaster):** people photograph home damage. A recovery agent highlights the damage with SAM 3.1, asks follow-up questions, and produces a damage report and document checklist for insurance or FEMA. The report is in English plus the user's language and states "Not an official damage estimate."

ClimateGuard gives environmental-risk and protective-action guidance only. It never gives medical advice.

Built for the Meta Global AI Developer Hackathon (Indie Developer track).

## Models

| Job | Model | Provider |
|---|---|---|
| Monitoring agent | `meta-models/muse-spark-open-1026` | Baseten (open weights) |
| Chat, recovery agent, reports | `muse-spark-1.3` (`-contributor` in dev) | Meta Model API |
| Damage segmentation | `sam-3.1` | Meta Model API |
| Speech to text | `muse-voice-transcribe-1.0` | Meta Model API |
| Safety cards (stretch) | `muse-image-1.0` | Meta Model API |

## Repo layout

```
template.yaml          AWS SAM: DynamoDB tables, collector + agent Lambda (every 15 min), read API
backend/src/           Lambda code (packaged by `sam build`)
  climateguard/
    sources/           nws.py, openmeteo.py, airnow.py (one module per data source)
    handlers/          collect.py (EventBridge), api.py (HTTP API)
    snapshot.py        one normalized risk snapshot per city, plus a change fingerprint
    risk.py            heat index, AQI categories, Cal/OSHA thresholds
    monitor.py         monitoring agent (Muse Spark Open on Baseten, tool calling)
    guidance.py        BM25 search over data/guidance.json (official safety guidance)
    alerts_store.py    sent alerts (for dedup) + agent decision log
    scenarios.py       synthetic heatwave / smoke / flood / calm snapshots
    notify.py          alert delivery (dry run until Phase 3 adds SNS email)
    llm.py, cache.py, usage.py   model calls, response cache, usage and cost log
backend/scripts/       smoke tests, collect_local.py, run_monitor.py, spend.py, compare_effort.py
backend/tests/         offline tests (pytest)
frontend/              React + Vite, mobile-first, deployed on Vercel
```

## Data layer

Cities: Stockton, Lodi, Manteca, Tracy, Modesto and Merced (`cities.py`).

| Data | Primary source | Fallback |
|---|---|---|
| Hourly forecast (48 h) | NWS `forecastHourly` | Open-Meteo |
| Heat index | Computed with the NWS Rothfusz formula from temperature and humidity | — |
| Air quality (current and daily forecast) | EPA AirNow, used if `AIRNOW_API_KEY` is set | Open-Meteo (modeled US AQI) |
| Alerts | NWS `alerts/active?point=` | — |

**Every 15 minutes**, the collector builds a snapshot for each city and saves it to DynamoDB. A snapshot holds the hourly data, AQI, alerts and a summary. The summary includes max temperature and heat index, hours at or above 80°F and 95°F, AQI, and Cal/OSHA flags.

**The agent only runs on material changes.** Each snapshot gets a fingerprint built from coarse values only: 5°F temperature buckets, AQI category, and alert event, severity and end time. The monitoring agent runs only for cities whose fingerprint changed. When NWS re-issues the same warning with a new ID, the fingerprint stays the same.

**Cal/OSHA flags use air temperature.** The 80°F (shade) and 95°F (high-heat procedures) flags follow T8 §3395, which is based on air temperature. Heat index is computed and reported separately for information.

**Outages are handled conservatively.** If a source is down, the collector keeps the last good snapshot instead of overwriting it with missing data.

Old pipeline note: `us-weather-pipeline` serves its data from a local Docker stack, and its live site's JSON URLs return the dashboard page, so ClimateGuard fetches NWS and air quality directly.

## Monitoring agent

`monitor.py` runs Muse Spark Open (`meta-models/muse-spark-open-1026`) on Baseten with real tool calling. For each city whose data changed, the flow is:

1. **Pre-filter (no model call).** If there's no NWS alert, no hour at or above 95°F, heat index below 100°F, AQI at or below 100 and rain chance below 60%, the run is logged as skipped and costs nothing.
2. **Gather data.** The agent calls `get_nws_alerts`, `get_forecast`, `get_aqi` and `get_recent_alerts_sent` for the city.
3. **Ground the advice.** It calls `search_safety_guidance`, which searches 17 official excerpts from Cal/OSHA, NWS, CDC, EPA AirNow and FEMA. These cover protective actions only, with no symptom content.
4. **Decide and send.** The agent decides on its own. To alert, it calls `send_alert(city, hazard, severity, messages_by_language, reason)` with English, Spanish and Vietnamese messages.
5. **Log the decision.** Every run writes one decision-log entry: `sent`, `skipped` or `error`, why, which tools it called, how many model calls, and the cost.

**Guardrails in code** (`send_alert` rejects the alert and tells the agent why):
- **Duplicates:** the same hazard at the same or lower severity within 12 h is rejected. Escalations and different hazards are allowed.
- **Daily cap:** at most 3 alerts per city in 24 h.
- **Messages:** all three languages are required, each at most 400 characters.
- **No medical wording:** symptoms, diagnoses and medicines are blocked in English, Spanish and Vietnamese.
- **One city per run:** the agent can only query or alert the city under review.
- **Bounded runs:** at most 8 model calls per run. Reasoning text is never fed back into the conversation; tested live, Baseten tool calling works without it.

Live results with the synthetic scenarios (`scripts/run_monitor.py`):

| Scenario | Result | Model calls | Cost |
|---|---|---|---|
| Heat wave (108°F, Extreme Heat Warning) | Sent an extreme heat alert in EN/ES/VI | 4 | $0.011 |
| Same heat wave again | Skipped: same hazard already alerted, severity unchanged | 3 | $0.007 |
| Wildfire smoke (AQI 178) after the heat alert | Sent a high smoke alert (different hazard) | 4 | $0.011 |
| Calm day, and today's real Stockton data | Skipped by the pre-filter | 0 | $0 |

```bash
python scripts/run_monitor.py stockton --scenario heatwave --reset   # heatwave|smoke|flood|calm
python scripts/collect_local.py --monitor                            # real data, agent only where changed
```

## Deploy (AWS SAM)

Prerequisites: install the [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), then run `aws configure` (or `aws login`).

```bash
sam build
sam deploy --guided     # first time; afterwards just `sam deploy`
curl "$(aws cloudformation describe-stacks --stack-name climateguard \
  --query 'Stacks[0].Outputs[0].OutputValue' --output text)/cities/stockton"
```

## Setup

```bash
cp .env.example .env          # then fill in BASETEN_API_KEY and MODEL_API_KEY

cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m pytest -q tests             # offline tests
.venv/Scripts/python scripts/smoke_baseten.py       # 1 live call to Baseten
.venv/Scripts/python scripts/smoke_meta.py          # 1 live call to Meta Model API
.venv/Scripts/python scripts/spend.py               # total estimated spend so far
.venv/Scripts/python scripts/collect_local.py       # live data for all cities (free, no model calls)

cd ../frontend
npm install
npm run dev
```

## Cost controls

- **`USE_CONTRIBUTOR=true`** (in `.env`) switches to the cheaper `muse-spark-1.3-contributor`. Meta may train on contributor-mode data, so use it with fake data only. Set it to `false` for real photos and the demo.
- **One wrapper for every chat call:** all calls go through `climateguard.llm.chat()`. It requires `max_tokens`, caches identical requests, strips reasoning text, and logs tokens and estimated cost.
- **Storage location:** with `STORAGE=local`, the usage log and cache are files under `backend/.local/`. With `STORAGE=dynamodb` (always the case in Lambda), they go to the `climateguard-usage` and `climateguard-cache` tables. To see deployed spend, run `STORAGE=dynamodb python scripts/spend.py`.
- **Reasoning counts toward `max_tokens`:** Muse Spark Open always reasons first, so set generous limits.
- **`reasoning_effort` defaults to `low`** for both providers. Change the defaults with `BASETEN_REASONING_EFFORT` / `META_REASONING_EFFORT`, or pass `chat(reasoning_effort=...)` for one call. Baseten's own default for Muse Spark Open is `xhigh`. Rerun `scripts/compare_effort.py` before raising the default.

  Results from `scripts/compare_effort.py` on two alert decisions (one real heat alert, one duplicate NWS re-issue):

  | Effort | Reasoning tokens | Latency | Cost per call | Decisions correct |
  |---|---|---|---|---|
  | low | 180–250 | 1.5–2.4 s | ~$0.002 | 2/2 |
  | medium | 420–555 | 1.8–2.9 s | ~$0.003 | 2/2 |
  | high | 940–1675 | 3.7–6.9 s | ~$0.006 | 2/2 |
- **Cache TTL:** cached responses expire after 1 hour. Change this with `CACHE_TTL_SECONDS`, or pass `chat(cache_ttl=...)` for one call.

## Known concerns

### Timeouts for slow reasoning calls (handle in Phase 4)

| Limit | Value |
|---|---|
| Lambda | 15 min max (900 s). The default is 3 s, so always set `Timeout` in the SAM template. |
| API Gateway HTTP API | 30 s hard limit |
| API Gateway REST API | 29 s by default. Regional APIs can request a higher quota. |
| Lambda Function URL | Up to the Lambda timeout (15 min), and supports response streaming |

**Why it matters:** single chat answers at `low` effort take about 2–5 s, which is fine. The recovery agent is different: it runs several model calls (SAM 3.1, vision descriptions, report writing, PDF export) and can easily pass 30 s, and higher reasoning effort adds 2–5× latency.

**Plan:**
- Serve chat through API Gateway with a 25 s client timeout and a friendly "try again" message.
- Run the recovery agent as an async job: `POST` starts it and returns a job ID, the work runs in a Lambda, and the frontend polls `GET /jobs/{id}` (or uses a Function URL with streaming).
- Voice transcription of short clips is fast enough to call synchronously.

## Future work

- SMS alerts (US carrier registration takes weeks)
