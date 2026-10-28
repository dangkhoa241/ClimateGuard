# ClimateGuard

A multilingual climate-disaster agent for the United States, with California's Central Valley (Stockton first) as the demo focus. It is built for farmworkers, outdoor workers and immigrant families who often miss English-only warnings.

- **Alerts (before and during a disaster):** people sign up with a ZIP code or their phone's location. A monitoring agent watches NWS alerts, the forecast and air quality for their NWS forecast zone. It decides when risk is high and writes short alerts in English, Spanish and Vietnamese (human-reviewed), and in Chinese, Tagalog, Korean and Arabic (automatic translation, always labeled). It skips duplicates and emails subscribers.
- **Ask:** people ask by text or voice in their own language and get answers based on live data for their area.
- **Recovery (after a disaster):** people photograph home damage. A recovery agent highlights the damage with SAM 3.1, asks follow-up questions, and produces a damage report and document checklist for insurance or FEMA. The report is in English plus the user's language and states "Not an official damage estimate."

ClimateGuard gives environmental-risk and protective-action guidance only. It never gives medical advice.

> **Not covered: Tornado, Flash Flood, Severe Thunderstorm and Extreme Wind warnings.** These can give only minutes of warning. ClimateGuard checks every 15 minutes and delivers by email, which is far too slow, so it never sends them and never claims to. Keep **Wireless Emergency Alerts** turned on in your phone settings and use a **NOAA Weather Radio**. Watches for these hazards, which come hours ahead, are still covered.

Built for the Meta Global AI Developer Hackathon (Indie Developer track).

## Models

| Job | Model | Provider |
|---|---|---|
| Monitoring agent | `meta-models/muse-spark-open-1026` | Baseten (open weights) |
| Alert translation (zh, tl, ko, ar) | `muse-spark-1.3` | Meta Model API |
| Chat, recovery agent, reports | `muse-spark-1.3` (`-contributor` in dev) | Meta Model API |
| Damage segmentation | `sam-3.1` | Meta Model API |
| Speech to text | `muse-voice-transcribe-1.0` | Meta Model API |
| Safety cards (stretch) | `muse-image-1.0` | Meta Model API |

## Repo layout

```
deploy.ps1             permission + free-tier preflight, then sam deploy (us-east-2)
template.yaml          AWS SAM: DynamoDB tables, collector + agent Lambda (every 15 min), public API
backend/src/           Lambda code (packaged by `sam build`)
  climateguard/
    sources/           nws.py (incl. one national alerts call), openmeteo.py, airnow.py
    handlers/          collect.py (EventBridge), api.py (HTTP API)
    geo.py             ZIP -> coordinates (bundled Census file), coordinate rounding
    zones.py           NWS forecast zones: lookup, registry, which zones are monitored
    hazards.py         NWS events -> hazard groups; short-fuse warnings excluded
    snapshot.py        one normalized risk snapshot per zone, plus a change fingerprint
    risk.py            heat index, AQI categories, Cal/OSHA thresholds
    monitor.py         monitoring agent (Muse Spark Open on Baseten, tool calling)
    guidance.py        BM25 search over data/guidance.json (official safety guidance)
    alerts_store.py    sent alerts (for dedup) + agent decision log
    budget.py          daily model budget ($5/day)
    languages.py, translate.py   alert languages; automatic translation of the English alert
    scenarios.py       synthetic heatwave / smoke / flood / calm / tornado_warning / winter_storm
    replays.py         real past events (data/replays/*.json) as snapshots, labeled REPLAY
    stats.py           daily counters for the public decision history
    subscriptions.py   sign-up by zone + language via SNS (double opt-in), abuse limits, confirmed counts
    notify.py          alert delivery: one SNS publish per zone + language topic
    ratelimit.py       per-IP / per-email counters, subscriber cap
    ssm.py             read API keys from SSM Parameter Store (Lambda)
    llm.py, cache.py, usage.py   model calls, response cache, usage and cost log
backend/scripts/       smoke tests, collect_local.py, run_monitor.py, local_api.py, spend.py, compare_effort.py,
                       build_replays.py, replay.py, run_eval.py + eval_cases.py
backend/eval/results/  evaluation reports (.md + .json)
backend/tests/         offline tests (pytest)
frontend/              React + Vite, mobile-first, deployed on Vercel
```

## Where ClimateGuard works: NWS forecast zones

- **Locations:** a ZIP code (bundled 2024 Census ZIP file, no API call) or browser coordinates. Coordinates are rounded to about 1 km on the phone and again on the server, and only the zone is stored.
- **Zone lookup:** the NWS points API maps the location to its **forecast zone**, for example Stockton → `CAZ159` "Central San Joaquin County Including Stockton Metro". It also gives the county, fire-weather zone and timezone.
- **Coverage:** checked live in New York, Minneapolis, Miami, Anchorage, Honolulu and San Juan.
- **Monitored zones:** only zones with at least one **confirmed** subscriber, plus the two demo zones, Stockton (`CAZ159`) and Planada/Merced (`CAZ303`). Confirmed counts are refreshed hourly from SNS. One agent run per zone covers everyone in it.
- **Zone numbers changed in 2025:** Stockton was `CAZ019` in the 2022 archive and is `CAZ159` today, so replays are keyed by place.

## Data layer

| Data | Primary source | Fallback |
|---|---|---|
| Hourly forecast (48 h) | NWS `forecastHourly` for the zone | Open-Meteo |
| Heat index | Computed with the NWS Rothfusz formula from temperature and humidity | — |
| Air quality (current and daily forecast) | EPA AirNow monitors, used if an AirNow key is set | Open-Meteo (modeled US AQI) |
| Alerts | **One** NWS `alerts/active` call for the whole country per run, matched to each zone by UGC code (forecast zone, county or fire zone) | — |

**Every 15 minutes**, the collector does three things:
1. Builds a snapshot for each monitored zone, in parallel and in the zone's own timezone.
2. Reuses forecasts and AirNow readings younger than 45 minutes, since both update hourly.
3. Saves the snapshot to DynamoDB, writing a history copy only when the fingerprint changed.

A snapshot holds the hourly data, AQI, alerts and a summary. The summary includes max/min temperature, heat index, peak wind, hours at or above 80°F and 95°F, AQI, and threshold flags.

**Short-fuse warnings are excluded.** Tornado, Flash Flood, Severe Thunderstorm and Extreme Wind warnings are kept in the snapshot under `excluded_alerts` for transparency, but they never count as a risk signal, never change the fingerprint, and never reach the agent.

**All other NWS hazards** map to groups: heat, cold, winter, flood, coastal, tornado (watch), thunderstorm (watch), tropical, wind, fire, smoke, dust, fog, other.

**The agent only runs on material changes.** Each snapshot gets a fingerprint built from coarse values only:
- 5°F temperature buckets, plus cold and wind buckets
- AQI category
- each alert's event, severity and end time

The agent runs only for zones whose fingerprint changed. When NWS re-issues the same warning with a new ID, the fingerprint stays the same.

**Cal/OSHA flags use air temperature.** The 80°F (shade) and 95°F (high-heat procedures) flags follow T8 §3395, which is based on air temperature. Heat index is computed and reported separately for information. Cal/OSHA rules apply in California only. Elsewhere the same thresholds just mark conditions, and the guidance falls back to federal OSHA's "Water, Rest, Shade".

**Outages are handled conservatively.** If a source is down, the collector keeps the last good snapshot instead of overwriting it with missing data.

**AirNow moved to new endpoints.** It retired its old lat/long web services on 2026-10-01 (they now return `410 Gone`). ClimateGuard uses the replacements, `/aq/observation/current/ziplatlong/` and `/aq/forecast/current/`. Their field names were checked against live responses, because AirNow's docs require a login.

**Error messages never include API keys.** Error text is stored in snapshots, and the public API serves snapshots, so source errors never contain the request URL's query string. A test covers this.

## Monitoring agent

`monitor.py` runs Muse Spark Open (`meta-models/muse-spark-open-1026`) on Baseten with real tool calling. For each zone whose data changed, the flow is:

1. **Pre-filter (no model call).** The agent runs if there is any risk signal:
   - any active NWS alert (excluded short-fuse warnings don't count);
   - AQI of 101 or more, now or forecast;
   - an hour at or above 95°F;
   - heat index of 100°F or more;
   - rain chance of 60% or more;
   - a low of 20°F or less;
   - wind of 40 mph or more.

   With no signal, the run is logged as skipped and costs nothing.
2. **Budget check.** Over the **$5/day** model budget, only zones with an active NWS *Warning* run the agent; the rest are logged as skipped for budget.
3. **Gather data.** The agent calls `get_nws_alerts`, `get_forecast` (in the zone's local time), `get_aqi` and `get_recent_alerts_sent`.
4. **Ground the advice.** It calls `search_safety_guidance`, which searches 26 official excerpts from NWS, Ready.gov, CDC, EPA AirNow, FEMA, Cal/OSHA and OSHA. These cover protective actions only, with no symptom content.
5. **Decide and send.** The agent decides on its own. To alert, it calls `send_alert(zone, hazard, severity, messages_by_language, reason)` with English, Spanish and Vietnamese messages.
6. **Log the decision.** Every run writes one decision-log entry: `sent`, `skipped` or `error`, why, which tools it called, how many model calls, and the cost.

**Guardrails in code** (`send_alert` rejects the alert and tells the agent why):
- **Duplicates:** the same hazard at the same or lower severity within 12 h is rejected. Escalations and different hazards are allowed.
- **Daily cap:** at most 3 alerts per zone in 24 h. The one exception is an alert more severe than every alert already sent to that zone in the last 24 h, which always goes through.
- **Messages:** all three reviewed languages are required, each at most 400 characters.
- **No medical wording:** symptoms, diagnoses and medicines are blocked in English, Spanish and Vietnamese. Other languages are translated from the already-checked English.
- **Masks only for particles (safety):** N95 masks filter smoke, dust and ash (PM2.5/PM10), not ozone. Mask advice in any language is rejected unless the data shows particle pollution (PM2.5/PM10 AQI 101+, or a smoke/dust alert). High ozone on top of smoke doesn't block it: AirNow's daily forecast names only the worst pollutant, so the particle reading is kept alongside it. An automatic translation that adds mask advice the English doesn't have falls back to English. Found in the Vietnamese review: the Sept 6 2022 ozone alert (AQI 208) had told people to wear an N95.
- **Wording rules from the Vietnamese review:** a watch is never mentioned next to an active warning for the same hazard; heat index ("feels like") only when it's at least 5°F above the air temperature; flood alerts must use firm wording, never "avoid": Spanish "Nunca camine ni maneje por agua de inundación", Vietnamese "Tuyệt đối không đi bộ hoặc lái xe qua vùng nước ngập". Vietnamese time words ("hôm nay", "tối nay") are lowercased mid-sentence in code.
- **One zone per run:** the agent can only query or alert the zone under review.
- **Bounded runs:** at most 8 model calls per run. Reasoning text is never fed back into the conversation; tested live, Baseten tool calling works without it.

Live results with the synthetic scenarios (`scripts/run_monitor.py`):

| Scenario | Result | Model calls | Cost |
|---|---|---|---|
| Heat wave, Stockton (108°F, Extreme Heat Warning) | Sent an extreme heat alert in EN/ES/VI | 4 | $0.011 |
| Same heat wave again | Skipped: same hazard already alerted, severity unchanged | 3 | $0.007 |
| Wildfire smoke (AQI 178) after the heat alert | Sent a high smoke alert (different hazard) | 4 | $0.011 |
| Winter storm, Minneapolis (Central time) | Sent a high winter-storm alert grounded in Ready.gov guidance | 4 | $0.011 |
| Tornado Warning only, Minneapolis | Skipped by the pre-filter: excluded warning, agent never called | 0 | $0 |
| Calm day, and today's real Stockton data | Skipped by the pre-filter | 0 | $0 |

```bash
python scripts/run_monitor.py --scenario heatwave --reset   # heatwave|smoke|flood|calm|tornado_warning|winter_storm
python scripts/collect_local.py --monitor                   # real data for monitored zones, agent only where changed
```

## Real-event replays

Demo mode replays **real past events** through the live agent, so the demo never depends on a disaster happening that day. `scripts/build_replays.py` downloads the archives once and saves small files in `backend/src/climateguard/data/replays/` (committed).

| Event | Place (zone) | Moments | What the archives show |
|---|---|---|---|
| `heat_2022`: September 2022 heat wave | Stockton (`CAZ159`; `CAZ019` in 2022) | warning issued (Sept 1), warning starts (Sept 4), record day 7 AM and 3 PM (Sept 6), after (Sept 10) | Excessive Heat Warning Sept 4–9; Stockton tied its all-time record of 115°F on Sept 6 (hourly readings peak at 114°F), with county AQI 208 that day |
| `flood_2023`: January 2023 Merced County floods | Planada (`CAZ303`) | Flood Watch (Jan 8), flood warnings (Jan 9, 10 PM), evacuation morning (Jan 10), after (Jan 20) | Bear Creek "major flooding… flood of record"; Planada evacuated Jan 10; a Freeze Warning followed |
| `smoke_2020`: September 2020 wildfire smoke | Stockton (`CAZ159`) | orange sky (Sept 9), peak (Sept 12), improving (Sept 16) | San Joaquin County daily AQI 206 (Very Unhealthy) on Sept 12 |

**Sources, all public archives:**

| Data | Source |
|---|---|
| Weather | Observed hourly airport readings (IEM ASOS archive, SCK/MCE) |
| NWS products | Watches, warnings and advisories **with their original NWS text and end times as of each moment** (IEM VTEC archive) |
| Air quality | AirNow hourly file archive, plus EPA AirData daily county AQI |

**How the archive is read:** each moment uses the latest NWS product before it, including upgrades: once a watch is upgraded to a warning, the watch disappears. The NWS header lines (zone codes, VTEC code, area names) are stripped, so the agent sees the plain-language message.

**Labeled everywhere:**
- Every replay snapshot carries a `replay` block with the banner "REPLAY of a real event, not live. Weather shown is what was observed."
- Archived NWS hourly forecasts don't exist, so replays use observed weather in their place, and say so.
- The agent is told it's a replay and reasons at the historical local time.
- In the demo story, **Maria is always labeled an example person**. The events, places and data are real.

**Isolation:** replay runs use the `REPLAY-<event>` log. They never email anyone and never appear in the live decision history.

```bash
python scripts/replay.py                       # list events and moments
python scripts/replay.py flood_2023            # run every moment through the live agent
python scripts/build_replays.py                # rebuild from the archives (about 45 s)
```

## Evaluation

`scripts/run_eval.py` runs **34 cases (36 steps)** through the live agent. Each case uses its own `EVAL-<case>` log: nothing is emailed and nothing touches live data.

- **11 real archived moments:** heat warning issued; record day; no repeated alert later the same day; quiet day after; flood watch; flood warning; watch → warning escalation; freeze after the flood; smoke orange-sky day; smoke peak; smoke clearing.
- **9 hard, ambiguous cases**, written after the agent's rules and **not** to match them. Each expectation is what a careful human duty forecaster would want, fixed before any run:
  - a Heat Advisory with highs of 94°F and AQI 148
  - a warning whose text says 110°F while our forecast data shows 82°F
  - a Flood Warning that already expired but is still in the feed
  - a heat warning and a fire-weather watch at once
  - a flood warning that's clearly for a neighboring county
  - a heat warning ending in 2 hours with mild weather ahead
  - added with the fix for that case: a warning ending in 2 hours while **104°F** is forecast after it (should still alert), and an air-quality alert ending with the air already clean (should skip)
  - smoke forecast to reach AQI 165 tomorrow with no NWS alert yet
- **14 edge cases:**
  - calm day; a lone Tornado Warning (excluded); 94°F dry; ozone AQI 150 without smoke
  - smoke at AQI 155; a **prompt injection inside NWS alert text**; a re-issued warning already alerted
  - Heat Advisory → Extreme Heat Warning escalation; daily cap reached, then an extreme alert
  - heat and smoke together; air-quality source down; dense tule fog
  - a Minneapolis winter storm; a Miami hurricane watch

**What it measures:** decision accuracy (send vs. skip), right hazard, severity range, deduplication, escalation, zero model calls on the pre-filter cases, medical wording in every sent message, Vietnamese written with diacritics, guardrail rejections, cost per alert, and latency.

**Two full runs (2026-10-27, `low` reasoning effort, fresh samples each time):**

| Metric | Run 1 | Run 2 (with accent guardrail) |
|---|---|---|
| Cases passed | **25/25** (real 11/11, edge 14/14) | **25/25** (real 11/11, edge 14/14) |
| Decision accuracy / right hazard / severity in range | 25/25 · 19/19 · 7/7 | 25/25 · 19/19 · 7/7 |
| Dedup / escalation / pre-filter zero calls | 2/2 · 1/1 · 5/5 | 2/2 · 1/1 · 5/5 |
| Sent messages free of medical wording | 27/27 | 27/27 |
| Vietnamese written with diacritics | not measured | 27/27 |
| Guardrail rejections | none | 1 duplicate (the agent backed off) |
| Cost per alert | $0.0097 | $0.0089 |
| Latency per agent run (p50 / p95) | 6.2 s / 8.2 s | 6.7 s / 8.6 s |

**Run 3, with the 7 hard cases (2026-10-27, one run, fresh samples):** **31/32** (real 11/11, edge 14/14, **hard 6/7**). Vietnamese diacritics 34/34, no medical wording in any message, $0.0105 per alert, latency p50 6.8 s / p95 9.6 s. Report: `backend/eval/results/20261027-1708.md`.

**Run 4, after fixing the hard-case failure and adding the Vietnamese style rules (2026-10-27, one run, fresh samples):** **34/34** (real 11/11, edge 14/14, **hard 9/9**). Right hazard 24/24, severity in range 8/8, Vietnamese with diacritics 36/36, no medical wording in any message. One guardrail rejection: a message over 400 characters, which the agent shortened. Cost $0.0119 per alert (up from about $0.010, because messages are now longer). Latency p50 6.6 s / p95 10.1 s. Report: `backend/eval/results/20261027-1722.md`.

**Prompt injection in NWS text:** in both runs it was ignored. A clean heat alert was sent, and the agent's own log says it "ignored embedded instruction".

**Two bugs the replays and eval found, both now fixed in code:**
- **Missing accents.** In one replay the model wrote Spanish and Vietnamese without accents ("Canh bao Ngap Lut…"). `send_alert` now rejects Vietnamese with no diacritics and common Spanish words missing their accent; the agent rewrites.
- **A hung request.** One model request in run 2 hung for **19 minutes**, because HTTP timeouts only limit the gap between bytes. Every model call now has a hard **60 s** wall-clock limit (with 1 retry), and every agent run a **150 s** limit, logged as an `error` decision. A stuck zone can no longer use up the collector's 10-minute Lambda limit.

Full reports are in `backend/eval/results/`.

```bash
python scripts/run_eval.py --fresh             # all cases, new samples (~$0.20-0.30)
python scripts/run_eval.py edge_prompt_injection real_flood_warning
```

### Known limitations

- **Fixed after failing first: alerting on a warning that's about to end.** In run 3, `hard_warning_about_to_end` **failed**. The heat warning ended 2 hours later, it was 76°F, and the next 24 hours stayed mild, yet the agent sent an *extreme* alert saying "heat is dangerous now", because an active warning "requires alerting".
  - **The test was also flawed:** its headline said "until 9 PM" while the end time was 2 hours away. Headlines are now built from the real end time.
  - **Fix, part 1 (the agent):** `get_nws_alerts` now shows each alert's `ends_in_hours` from the decision time (the replay time in replays). The prompt says to weigh that against the forecast, and that severity must match the data.
  - **Fix, part 2 (a backstop in code):** `send_alert` rejects a heat or smoke alert when every NWS alert for that hazard ends within 3 hours **and** the next 24 hours meet no threshold for it.
  - **Tested beyond the original case:** two new cases cover a warning ending while 104°F is still forecast (it still alerts) and an air alert ending with clean air (it skips). In run 4 all three passed **on the agent's own judgment**; the code backstop didn't need to step in.
  - **Side effect:** with the extra context, the "warning text says 110°F, data shows 82°F" case now gets a *moderate* heat alert instead of *extreme*. It still passes, and arguably matches the data better.
- **Expired and neighbor-zone alerts are handled by the agent's judgment, not by code.** It correctly skipped both hard cases, but nothing in code drops an expired alert. Alerts are matched to zones by NWS zone or county code, so a county-wide product in a large county (for example, San Bernardino) reaches every zone in that county.
- **The hard cases are judgment calls.** Example: trusting an official warning over our milder forecast data. A reviewer could reasonably expect different outcomes for some of them.
- **Small sample, non-deterministic model.** 32 cases, one sample per case per run. Results can vary between runs; three full runs so far have been 25/25, 25/25 and 31/32.
- **Replays use observed weather in place of the forecast**, because archived NWS hourly forecasts aren't available. The agent sees "perfect forecasts" in replays.
- **Temperatures:** English shows °F; every other language shows both, like "114°F (46°C)". The conversion is done in code, never by the model, including for automatic translations.
- **Vietnamese still needs human review.** A native speaker reviewed the style, and the prompt now carries their rules. In run 4 one Vietnamese sentence reversed the meaning of the English ("limit outdoor work *to* early morning or evening" came out as "limit outdoor work *in* early morning or evening"). There's no automated check for meaning; human review of real alerts is still needed.

## Public decision history

`GET /decisions?zone=&days=7&limit=50` returns the live agent's **real** decisions since deployment, newest first, and is public.

- **Each decision shows:** time, zone and place, sent or skipped, the agent's reason, risk signals, the tools it called (including any guardrail rejections), the alerts it sent, model calls and cost.
- **Live only:** replays and evals live in their own `REPLAY-*`/`EVAL-*` logs, so they can never appear here.
- **Daily counters:** decisions are only written when a zone's data materially changes, so a quiet week has few rows. The response therefore also carries daily totals recorded by every collector run:
  - collector runs and zone checks
  - data changes and pre-filter skips
  - agent runs, budget skips and alerts sent
  - errors and model cost

  An example of how a quiet week reads: "2,000 checks · 9 changes · 7 skipped by pre-filter · 2 agent runs · 0 alerts". The page itself comes in Phase 4.

## Email alerts (sign-up)

- **Sign-up:** a ZIP code or browser location, plus the alert language. One SNS topic per **zone and language**, for example `climateguard-caz159-es`, created on first use. Each subscriber gets alerts only in their language, and the topics show "ClimateGuard" as the email sender name.
- **Languages:**

  | Language | How it's written |
  |---|---|
  | English, Spanish, Vietnamese | **Human-reviewed**; written by the agent and checked by the medical-wording guardrail |
  | Chinese (Simplified), Tagalog, Korean, Arabic | **Automatic translation** of the checked English with Muse Spark 1.3 (about $0.001 per alert per language) |

  - **Only languages with sign-ups:** translations run only for languages that have sign-ups in that zone.
  - **Labeled:** every automatically translated email starts with a localized "automatic translation" label.
  - **Fallback:** if translation fails, the English text goes out with a note in that language.
  - **Subjects:** email subjects stay ASCII, so zh/ko/ar emails use the English subject.
- **Double opt-in:** after sign-up, SNS emails a confirmation link, and nothing is delivered until it's clicked. That confirmation email is in English and comes from AWS, so the app tells users in their own language what to look for.
- **Unsubscribe:** SNS adds an unsubscribe link to every alert email. The localized footer points to it, says "not medical advice; in an emergency call 911", and names the warnings ClimateGuard does not send.
- **Abuse limits** (checked **before** any NWS lookup, so abuse can't turn into API calls):

  | Limit | Value | Response |
  |---|---|---|
  | Sign-ups per IP | 5 per hour | `429` |
  | Sign-ups per email address | 3 per day | `429` |
  | Sign-ups across the whole app | 300 per day | `503` |
  | Total subscribers (`MaxSubscribers`) | 500 | `503` |
  | Location lookups (`/locate`) per IP | 30 per hour | `429` |
  | Request body | 2 KB | `413` |

  The API also has a hidden honeypot field for bots and a throttle of 10 requests per second (burst 20) across the whole API. Re-confirming the same email, zone and language doesn't count toward the subscriber cap.
- **Privacy:** IPs and emails are stored only as hashes in the rate-limit table. SNS holds the email addresses themselves. Locations are never stored, only zones.
- **Local development:** `NOTIFY_MODE=dryrun` writes sign-ups and alert emails to `backend/.local/outbox.jsonl` (dry-run sign-ups count as confirmed). Run `python backend/scripts/local_api.py` to serve the API on `:8787` for the frontend.
- **Endpoints:**

  | Route | What it does |
  |---|---|
  | `GET /locate?zip=` or `?lat=&lon=` | Returns the zone |
  | `GET /zones/{zone}` | Latest snapshot |
  | `GET /zones/{zone}/alerts` | Alerts sent in the last 48 h |
  | `GET /languages` | Supported alert languages |
  | `POST /subscribe {email, lang, zip or lat+lon}` | Sign-up (double opt-in) |
  | `GET /decisions?zone=&days=&limit=` | The live agent's real decisions + daily counters (public) |

## Deploy (AWS SAM), step by step

Commands are for **PowerShell** from the repo root.

**Region: `us-east-2` (Ohio) only.** This account's Organizations SCP explicitly denies other regions; us-west-2 and us-east-1 were checked and are denied. `deploy.ps1` checks this before every deploy.

**Switching from the 6-city test deploy to zones (once, Wednesday).** The snapshot and alert tables changed their key from `city` to `zone`, and CloudFormation can't change the key of a named table in place. So delete the test stack first; this also gives the live decision history a clean start:
```powershell
sam delete --stack-name climateguard --region us-east-2 --no-prompts      # all tables, functions, API
aws sns delete-topic --region us-east-2 --topic-arn (aws sns list-topics --region us-east-2 --query "Topics[?ends_with(TopicArn, ':climateguard-stockton-es')].TopicArn" --output text)
```
Then follow steps 3 to 7 below. The API URL changes, and you sign up again under your zone.

**1. Install the tools (once).**
```powershell
winget install --id Amazon.SAM-CLI -e
winget install --id Python.Python.3.12 -e   # sam build needs the same Python as the Lambda runtime
```
Open a new terminal. If `python --version` doesn't print 3.12, put it first on `PATH` for this session:
```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:LOCALAPPDATA\Programs\Python\Python312\Scripts;$env:Path"
```

**2. Sign in to AWS.** Use an IAM user with an access key (`aws login` may be blocked).
```powershell
aws configure                         # access key, secret, region us-east-2, output json
aws configure set region us-east-2
aws sts get-caller-identity
```

**3. Store the API keys in SSM Parameter Store (SecureString, once).**
- **Why by hand:** CloudFormation can't create SecureStrings.
- **Keys stay hidden:** the commands read each key from `.env` into a variable, so it never appears on screen or in your history.
- **Lengths only:** the checks print each value's length, never the value.
```powershell
$baseten = ((Get-Content .env | Where-Object { $_ -match '^BASETEN_API_KEY=' }) -replace '^BASETEN_API_KEY=', '').Trim()
$airnow  = ((Get-Content .env | Where-Object { $_ -match '^AIRNOW_API_KEY=' })  -replace '^AIRNOW_API_KEY=', '').Trim()
aws ssm put-parameter --region us-east-2 --name /climateguard/baseten-api-key --type SecureString --value $baseten --overwrite
aws ssm put-parameter --region us-east-2 --name /climateguard/airnow-api-key  --type SecureString --value $airnow  --overwrite
$meta    = ((Get-Content .env | Where-Object { $_ -match '^MODEL_API_KEY=' })   -replace '^MODEL_API_KEY=', '').Trim()
aws ssm put-parameter --region us-east-2 --name /climateguard/meta-model-api-key --type SecureString --value $meta --overwrite
Remove-Variable baseten, airnow, meta

aws ssm get-parameter --region us-east-2 --name /climateguard/baseten-api-key --with-decryption --query "[Parameter.Type, length(Parameter.Value)]" --output text
aws ssm get-parameter --region us-east-2 --name /climateguard/airnow-api-key  --with-decryption --query "[Parameter.Type, length(Parameter.Value)]" --output text
```
- **Expected:** `SecureString 45` for Baseten and `SecureString 36` for AirNow, matching the key lengths in `.env`.
- **Rotating a key later:** rerun its `put-parameter` command (it already has `--overwrite`). The Lambda reads the new value on its next cold start.
- **AirNow and Meta are optional:** without AirNow, air quality comes from Open-Meteo. Without the Meta key, zh/tl/ko/ar alerts go out in English with a note. The Meta key's length check should show 48.

**4. Build.**
```powershell
sam build
```
This packages `backend/src` and its dependencies as Linux arm64 wheels, about 28 MB.

**5. Preflight, then deploy.**
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # if scripts are blocked
.\deploy.ps1 -PreflightOnly                                   # dry run: checks only, creates nothing
.\deploy.ps1 -Contact you@example.com                         # preflight + sam deploy
.\deploy.ps1 -Contact you@example.com -FrontendUrl https://<app>.vercel.app   # once the frontend is live
```
The preflight checks three things, without creating anything:
1. **Every permission the stack needs** in us-east-2: CloudFormation, S3, IAM, Lambda, DynamoDB, SNS, Scheduler, API Gateway, Logs and SSM.
2. **That both SSM keys exist.**
3. **DynamoDB capacity:** the provisioned capacity of **every table in every region**, plus this template's, against the free 25 RCU / 25 WCU.

A denied permission prints `DENIED -> service 'x', action 'x:Y'` and stops before SAM runs.

The deploy then shows SAM's change set and waits for `y`. Re-running is safe; SAM only applies differences. If a deploy fails, the script lists failed resources and denied actions; a stack that doesn't exist is reported as "nothing was created".

**6. Check that it works.**
```powershell
$api = aws cloudformation describe-stacks --stack-name climateguard --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
sam remote invoke CollectFunction --stack-name climateguard      # run one collection now
curl.exe "$api/zones/CAZ159"                                      # Stockton demo zone snapshot
aws logs tail /climateguard/collect --follow                      # watch the 15-minute runs (Ctrl+C)
```

**7. Test email for real.**
```powershell
Invoke-RestMethod -Method Post -Uri "$api/subscribe" -ContentType "application/json" `
  -Body (@{ email = "you@example.com"; zip = "95202"; lang = "es" } | ConvertTo-Json)
```
Click "Confirm subscription" in the email from "ClimateGuard". Real alerts arrive only when the agent decides to send one.

**8. Check spend and clean up.**
```powershell
$env:STORAGE = "dynamodb"; backend\.venv\Scripts\python backend\scripts\spend.py; Remove-Item Env:STORAGE
sam delete --stack-name climateguard
```
`sam delete` removes the stack, including its log groups. Two things stay:
- **SNS topics**, which the app creates at runtime. Delete them with `aws sns list-topics`, then `aws sns delete-topic --topic-arn ...`.
- **The two SSM parameters.** Delete them with `aws ssm delete-parameter --name ...`.

**Expected AWS cost:** $0 on the Free plan. All of it stays inside the free allowances:
- Lambda, DynamoDB (16 of 25 RCU/WCU in total), EventBridge Scheduler and CloudWatch Logs (7-day retention)
- SSM standard parameters, which are free
- SNS email, with 1,000 free notifications a month

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
.venv/Scripts/python scripts/collect_local.py       # live data for monitored zones (free, no model calls)

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

### Cost at scale (per month)

Assumptions: $0.010 per agent run (measured $0.0065–0.011); 0.2 runs per zone per day in calm seasons, 1.5 in active seasons; translations about $0.001 per alert per language.

| | 10 zones | 100 zones | 500 zones |
|---|---|---|---|
| Monitoring agent (Baseten), calm → active season | $0.60 – $4.50 | $6 – $45 | $30 – $225 |
| Worst single day (major event, 60% of zones, 4 runs each) | $0.24 | $2.40 | $12 (the **$5/day budget** caps this) |
| Translations for zh/tl/ko/ar | < $0.10 | < $1 | ≈ $3 |
| AWS (Lambda, DynamoDB, SNS, Scheduler, SSM, Logs) | ≈ $0 | ≈ $0 | ≈ $0–2 |

**Why AWS stays near zero:** one national alerts call per run, forecast/AQI reuse within 45 minutes, history written only on change, and at most 500 zones (the subscriber cap). Lambda use at 500 zones is about 30,000 GB-seconds a month, against the free 400,000.

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

- **Short-fuse warnings** (tornado, flash flood, severe thunderstorm, extreme wind): a 1-minute poller with fixed, pre-translated messages that skips the agent. Deferred to protect the deadline; until then they're excluded and the app points to Wireless Emergency Alerts and NOAA Weather Radio.
- Human review of the zh/tl/ko/ar alert templates and translations.

- SMS alerts (US carrier registration takes weeks)
