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
deploy.ps1             permission + free-tier preflight, then sam deploy (us-east-2)
template.yaml          AWS SAM: DynamoDB tables, collector + agent Lambda (every 15 min), public API
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
    subscriptions.py   city sign-up via SNS email (double opt-in), abuse limits
    notify.py          alert delivery: one SNS publish per city + language topic
    ratelimit.py       per-IP / per-email counters, subscriber cap
    ssm.py             read API keys from SSM Parameter Store (Lambda)
    llm.py, cache.py, usage.py   model calls, response cache, usage and cost log
backend/scripts/       smoke tests, collect_local.py, run_monitor.py, local_api.py, spend.py, compare_effort.py
backend/tests/         offline tests (pytest)
frontend/              React + Vite, mobile-first, deployed on Vercel
```

## Data layer

Cities: Stockton, Lodi, Manteca, Tracy, Modesto and Merced (`cities.py`).

| Data | Primary source | Fallback |
|---|---|---|
| Hourly forecast (48 h) | NWS `forecastHourly` | Open-Meteo |
| Heat index | Computed with the NWS Rothfusz formula from temperature and humidity | — |
| Air quality (current and daily forecast) | EPA AirNow monitors, used if `AIRNOW_API_KEY` is set | Open-Meteo (modeled US AQI) |
| Alerts | NWS `alerts/active?point=` | — |

**Every 15 minutes**, the collector builds a snapshot for each city and saves it to DynamoDB. A snapshot holds the hourly data, AQI, alerts and a summary. The summary includes max temperature and heat index, hours at or above 80°F and 95°F, AQI, and Cal/OSHA flags.

**The agent only runs on material changes.** Each snapshot gets a fingerprint built from coarse values only: 5°F temperature buckets, AQI category, and alert event, severity and end time. The monitoring agent runs only for cities whose fingerprint changed. When NWS re-issues the same warning with a new ID, the fingerprint stays the same.

**Cal/OSHA flags use air temperature.** The 80°F (shade) and 95°F (high-heat procedures) flags follow T8 §3395, which is based on air temperature. Heat index is computed and reported separately for information.

**Outages are handled conservatively.** If a source is down, the collector keeps the last good snapshot instead of overwriting it with missing data.

**AirNow moved to new endpoints.** It retired its old lat/long web services on 2026-10-01 (they now return `410 Gone`). ClimateGuard uses the replacements, `/aq/observation/current/ziplatlong/` and `/aq/forecast/current/`. Their field names were checked against live responses, because AirNow's docs require a login.

**Error messages never include API keys.** Error text is stored in snapshots, and the public API serves snapshots, so source errors never contain the request URL's query string. A test covers this.

Old pipeline note: `us-weather-pipeline` serves its data from a local Docker stack, and its live site's JSON URLs return the dashboard page, so ClimateGuard fetches NWS and air quality directly.

## Monitoring agent

`monitor.py` runs Muse Spark Open (`meta-models/muse-spark-open-1026`) on Baseten with real tool calling. For each city whose data changed, the flow is:

1. **Pre-filter (no model call).** The agent runs if there is any risk signal:
   - any active NWS alert, of any type;
   - AQI of 101 or more, now or forecast;
   - an hour at or above 95°F;
   - heat index of 100°F or more;
   - rain chance of 60% or more.

   With no signal, the run is logged as skipped and costs nothing. Tests guarantee that any NWS alert and any AQI above 100 always reach the agent.
2. **Gather data.** The agent calls `get_nws_alerts`, `get_forecast`, `get_aqi` and `get_recent_alerts_sent` for the city.
3. **Ground the advice.** It calls `search_safety_guidance`, which searches 17 official excerpts from Cal/OSHA, NWS, CDC, EPA AirNow and FEMA. These cover protective actions only, with no symptom content.
4. **Decide and send.** The agent decides on its own. To alert, it calls `send_alert(city, hazard, severity, messages_by_language, reason)` with English, Spanish and Vietnamese messages.
5. **Log the decision.** Every run writes one decision-log entry: `sent`, `skipped` or `error`, why, which tools it called, how many model calls, and the cost.

**Guardrails in code** (`send_alert` rejects the alert and tells the agent why):
- **Duplicates:** the same hazard at the same or lower severity within 12 h is rejected. Escalations and different hazards are allowed.
- **Daily cap:** at most 3 alerts per city in 24 h. The one exception is an alert more severe than every alert already sent to that city in the last 24 h, which always goes through.
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

## Email alerts (sign-up)

- **One SNS topic per city and language**, for example `climateguard-stockton-es`. That's 18 topics, created on first use. Each subscriber gets alerts only in the language they chose, and the topics show "ClimateGuard" as the email sender name.
- **Double opt-in:** after sign-up, SNS emails a confirmation link, and nothing is delivered until it's clicked. That confirmation email is in English and comes from AWS, so the app tells users in their own language what to look for.
- **Unsubscribe:** SNS adds an unsubscribe link to every alert email. The localized footer points to it and says "not medical advice; in an emergency call 911".
- **Abuse limits:**

  | Limit | Value | Response |
  |---|---|---|
  | Sign-ups per IP | 5 per hour | `429` |
  | Sign-ups per email address | 3 per day | `429` |
  | Sign-ups across the whole app | 300 per day | `503` |
  | Total subscribers (`MaxSubscribers`) | 500 | `503` |
  | Request body | 2 KB | `413` |

  The API also has a hidden honeypot field for bots and a throttle of 10 requests per second (burst 20) across the whole API. Re-confirming the same email, city and language doesn't count toward the subscriber cap.
- **Privacy:** IPs and emails are stored only as hashes in the rate-limit table. SNS holds the email addresses themselves.
- **Local development:** `NOTIFY_MODE=dryrun` writes sign-ups and alert emails to `backend/.local/outbox.jsonl`. Run `python backend/scripts/local_api.py` to serve the API on `:8787` for the frontend.
- **Endpoints:** `POST /subscribe {email, city, lang}` and `GET /cities/{city}/alerts` (alerts from the last 48 h).

## Deploy (AWS SAM), step by step

Commands are for **PowerShell** from the repo root.

**Region: `us-east-2` (Ohio) only.** This account's Organizations SCP explicitly denies other regions; us-west-2 and us-east-1 were checked and are denied. `deploy.ps1` checks this before every deploy.

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
Remove-Variable baseten, airnow

aws ssm get-parameter --region us-east-2 --name /climateguard/baseten-api-key --with-decryption --query "[Parameter.Type, length(Parameter.Value)]" --output text
aws ssm get-parameter --region us-east-2 --name /climateguard/airnow-api-key  --with-decryption --query "[Parameter.Type, length(Parameter.Value)]" --output text
```
- **Expected:** `SecureString 45` for Baseten and `SecureString 36` for AirNow, matching the key lengths in `.env`.
- **Rotating a key later:** rerun its `put-parameter` command (it already has `--overwrite`). The Lambda reads the new value on its next cold start.
- **AirNow is optional:** without it, air quality comes from Open-Meteo.

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
curl.exe "$api/cities/stockton"                                   # snapshot from DynamoDB
aws logs tail /climateguard/collect --follow                      # watch the 15-minute runs (Ctrl+C)
```

**7. Test email for real.**
```powershell
curl.exe -X POST "$api/subscribe" -H "Content-Type: application/json" --data-raw '{\"email\":\"you@example.com\",\"city\":\"stockton\",\"lang\":\"es\"}'
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
- Lambda, DynamoDB (14 of 25 RCU/WCU in total), EventBridge Scheduler and CloudWatch Logs (7-day retention)
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
