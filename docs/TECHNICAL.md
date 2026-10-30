# ClimateGuard: technical notes

The full engineering record behind the [README](../README.md): data layer, agent rules, evaluation history, deploy steps and cost numbers. Paths are from the repo root.

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
    budget.py          daily model budget ($3/day hard cap)
    languages.py, translate.py   alert languages; automatic translation of the English alert
    scenarios.py       synthetic heatwave / smoke / flood / calm / tornado_warning / winter_storm
    replays.py         real past events (data/replays/*.json) as snapshots, labeled REPLAY
    demo.py            demo mode: replay buttons, saved fallback runs (data/demo_saved.json), cost so far
    stats.py           daily counters for the public decision history
    subscriptions.py   sign-up by zone + language via SNS (double opt-in), abuse limits, confirmed counts
    notify.py          alert delivery: one SNS publish per zone + language topic
    ratelimit.py       per-IP / per-email counters, subscriber cap
    ssm.py             read API keys from SSM Parameter Store (Lambda)
    llm.py, cache.py, usage.py   model calls, response cache, usage and cost log
backend/scripts/       smoke tests, collect_local.py, run_monitor.py, local_api.py, spend.py, compare_effort.py,
                       build_replays.py, replay.py, save_demo_replays.py, run_eval.py + eval_cases.py
backend/eval/results/  evaluation reports (.md + .json)
backend/tests/         offline tests (pytest)
frontend/              React + Vite, mobile-first, deployed on Vercel (root directory `frontend`, env `VITE_API_URL`)
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
2. **Budget check.** When the **$3/day** hard model-spend cap is reached, new monitoring model calls are skipped, including for active NWS Warnings. This keeps spend bounded; keep Wireless Emergency Alerts enabled on your phone.
3. **Gather data.** The agent calls `get_nws_alerts`, `get_forecast` (in the zone's local time), `get_aqi` and `get_recent_alerts_sent`.
4. **Ground the advice.** It calls `search_safety_guidance`, which searches 28 official excerpts from NWS, Ready.gov, CDC, EPA AirNow, FEMA, Cal/OSHA and OSHA. These cover protective actions only, with no symptom content.
5. **Decide and send.** The agent decides on its own. To alert, it calls `send_alert(zone, hazard, severity, messages_by_language, reason)` with English, Spanish and Vietnamese messages.
6. **Log the decision.** Every run writes one decision-log entry: `sent`, `skipped` or `error`, why, which tools it called, how many model calls, and the cost.

**Guardrails in code** (`send_alert` rejects the alert and tells the agent why):
- **Duplicates:** the same hazard at the same or lower severity within 12 h is rejected. Escalations and different hazards are allowed.
- **Daily cap:** at most 3 alerts per zone in 24 h. The one exception is an alert more severe than every alert already sent to that zone in the last 24 h, which always goes through.
- **Messages:** all three reviewed languages are required, each at most 400 characters.
- **No medical wording:** symptoms, diagnoses and medicines are blocked in English, Spanish and Vietnamese. Other languages are translated from the already-checked English.
- **Masks only for particles (safety):** N95 masks filter smoke, dust and ash (PM2.5/PM10), not ozone. Mask advice in any language is rejected unless the data shows particle pollution (PM2.5/PM10 AQI 101+, or a smoke/dust alert). High ozone on top of smoke doesn't block it: AirNow's daily forecast names only the worst pollutant, so the particle reading is kept alongside it. An automatic translation that adds mask advice the English doesn't have falls back to English. Found in the Vietnamese review: the Sept 6 2022 ozone alert (AQI 208) had told people to wear an N95.
- **Wording rules from the Vietnamese review:** a watch is never mentioned next to an active warning for the same hazard; heat index ("feels like") only when it's at least 5°F above the air temperature; flood alerts must use firm wording, never "avoid": Spanish "Nunca camine ni maneje por agua de inundación", Vietnamese "Tuyệt đối không đi bộ hoặc lái xe qua vùng nước ngập". Vietnamese time words ("hôm nay", "tối nay") are lowercased mid-sentence in code. Spanish NWS level names are checked in code: Warning "Aviso", Watch "Vigilancia", Advisory "Advertencia", each only when that level is active. Replayed over 113 Spanish messages from earlier eval runs, this check flagged 9, all real errors: 8 advisories called "Aviso", and 1 warning called "Advertencia".
- **Active Warnings are not skippable** (added Oct 28 after the eval case `hard_warning_vs_mild_data` found the agent skipping a 110°F Extreme Heat Warning because our data showed 82°F). `unalerted_warnings()` lists active official Warnings with no alert yet; if the agent finishes without alerting one, it is sent back with a nudge (at most 2). Not required: already alerted this run or in the last 24 h at that severity or higher, blocked by the daily cap, or ending within 3 h with the hazard gone. While an active heat Warning is on and the data shows no heat, `send_alert` rejects any message with a temperature, so the warning's own wording is used. Known cost: `hard_neighbor_zone_alert` (a Fresno County warning in a Stockton feed) now sends.
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

## Ask (questions in your language)

`POST /ask {question, lang, zone}` answers in any of the 7 languages with `muse-spark-1.3`, from live data for the person's NWS zone. It runs in its own Lambda (`handlers/ask.py`, 28 s timeout). Each answer is one model call with a 20 s deadline, and the browser gives up after 29 s with a "try again" message (a cooling-center search with its retry can take up to about 24 s).

1. **Symptom guardrail (no model call).** Questions about symptoms, illness, medicine, pregnancy or chronic conditions, in all 7 languages, get a fixed, pre-written answer: call 911 in an emergency, otherwise a doctor or clinic. The model never sees them. Over-matching is the safe direction: "pesticide" in Chinese (农药) contains "medicine" (药) and gets the fixed answer too.
2. **Grounded context.** The zone's latest snapshot (if under 2 hours old; otherwise a fresh one built on demand, so Ask works in zones nobody has subscribed to yet), the alerts ClimateGuard sent there, and 4 official guidance excerpts (28 in the corpus, including CDC sun safety and CDC/NIOSH layers for cool mornings). The model gets the full 48-hour hourly forecast and a summary for each day: low, high and when, rain, wind and AQI forecast. The guidance corpus is English, so common words in the 7 languages are mapped to English search terms.
3. **One model call**, told to answer only from that context in up to 5 short sentences. It should be useful: it says it doesn't know only when the data truly can't answer. It doesn't open with the data time, because the app shows that under the answer, in the reader's language. It never names cooling centers, shelters, addresses or phone numbers, and never writes 211 itself. Vietnamese and Spanish answers get the reviewed wording rules.
   - **211 is a fixed sentence written in code:** "To find a cooling center or shelter near you, call 211 or check your county's website", reviewed in EN/ES/VI. It's added when the question asks for a place (cooling center, shelter, where to go, in all 7 languages), or when the model marks its answer `[211]`. Any 211 sentence the model writes itself is removed.
   - **Not added to plain "I don't know" answers:** live, a cooling-center sentence after "Will there be a tornado next month?" read wrong.
4. **The answer is checked again.** Medical wording in any language replaces it with the fixed symptom answer. Mask advice when masks wouldn't help (no smoke, dust or ash) replaces it with a fallback. When someone asks about masks on such a day, a fixed sentence is added: "A mask won't help with the air here right now: N95 masks only filter smoke, dust or ash, not ozone."

**Voice questions.** The mic button records the question. The browser converts it to a 16 kHz mono WAV, the only format the API takes, and posts it to `POST /transcribe?lang=` (`transcribe.py`). That calls Muse Voice Transcribe (`POST /v1/asr/transcribe`) with a language bias for the person's language plus English. The text goes into the question box, where the person can check and fix it before tapping Ask, so Ask and all its guardrails only ever see text.
- Measured: a 4.4 s question takes 2.6–3.3 s.
- Cost: $0.18 per hour of audio, about $0.0002 per question, logged in the usage log like model calls.
- Limits: 60 s of audio; 30 recordings per IP per hour.

**Read aloud** uses the phone's own voices (Web Speech API), because the Meta Model API has no text-to-speech model. Answers and alert cards get a read-aloud button only when the phone has a voice for that language. Desktop browsers often have no Vietnamese or Tagalog voice, so the button is hidden there rather than reading in the wrong voice.
- **Better voices are picked automatically:** names with Natural, Neural, Premium, Enhanced or Online, plus known good voices (iOS Linh; Edge HoaiMy, NamMinh, Jenny, Aria). Edge's online voices load late, so the list is refreshed on `voiceschanged`.
  - Picked on sample voice lists: Edge gets HoaiMy, iPhone gets Linh (Enhanced), Android gets Google tiếng Việt.
  - On Windows, Edge is the browser with Vietnamese voices.
- **Voice picker:** the Ask answer has a voice picker (voices for the current language only), remembered per language.
- **Sentence by sentence, at rate 0.95:** all sentences are queued inside the tap, because iOS only speaks from a user gesture.
- **iPhone hints:**
  - The silent switch mutes speech, and websites can't detect it. So on iPhone/iPad, starting to read shows "Can't hear it? Turn off your phone's silent mode."
  - A one-line tip suggests downloading an "Enhanced" voice. It's hidden once one is in use.

Every answer shows the place and time of the data it used, and its official sources. Limits: 20 questions per IP per hour; at the $3/day hard model-spend cap, Ask returns HTTP 429 with a friendly busy message.

**Times in the question are resolved in code** (`timeref.py`), against the zone's local time: "3 giờ chiều", "3 PM", "a las 3 de la tarde", "下午3点", "오후 3시", "alas-3 ng hapon", "الساعة 3 مساءً". If that time has already passed today, the answer is for the same time tomorrow and starts with a note written in code, for example "3 giờ chiều hôm nay đã qua, đây là dự báo cho 3 giờ chiều ngày mai (thứ Tư)." The model gets the target time and the forecast for that hour. "Tomorrow" in the question, or tomorrow's weekday, means tomorrow with no note. Another weekday or a date is left to the model.
- **Ranges:** "từ 6 giờ sáng đến 2 giờ chiều" or "from 6 AM to 2 PM" get a summary computed in code: temperature at the start, the warmest and when, and at the end, plus sky, wind, rain and AQI. The model summarizes the range first, then gives 2–3 actions from the guidance.
- **Number words:** read in Vietnamese, Spanish and English, only before a clock word ("sáu giờ sáng", "a las tres", "six PM"). "Tôi có hai con" isn't read as a time.
- **Why ranges were added:** in the iPhone test, "Ngày mai tôi làm ngoài đồng từ sáu giờ sáng đến hai giờ chiều, tôi nên chuẩn bị gì?" got only the 6 AM forecast and "I don't know how to prepare". Three causes:
  - the model saw only 24 hours, in 3-hour steps;
  - "sáu giờ" wasn't recognized;
  - there was no guidance on layers or sun protection.

**Ask eval** (`scripts/run_ask_eval.py`, about $0.03 per run): 5 real questions on today's live data, checked in code. The checks look for "I don't know", an answer that opens with the data time, unasked health advice, too few temperatures, too few practical actions, and the fixed 211 sentence for "where can I cool off".

| Reasoning effort | Passed | Median latency | Notes |
|---|---|---|---|
| `minimal` (kept) | 3/5 before the last prompt fixes, then **5/5** | 3.6–3.7 s | Range answer: "51°F … 66°F at 2 PM, haze then clouds, light wind", then layers, water, shade and sun protection |
| `low` | 2/5 | 5.9 s | No more useful than `minimal`, about 2 s slower (860–1,030 reasoning tokens) |

The failures, fixed in the prompt: "66 degrees" instead of "66°F", and an unasked "see a doctor". Vietnamese weekday names are capitalized in code ("thứ Năm"). Reports: `backend/eval/results/ask-*.md`.

**Second round** (two more tests, reviewer's wording): **7/7**, median about 2.2 s, after splitting the "answer first" rule.
- **Answer order:**
  - Yes/no and other questions answer in the first sentence, then the forecast briefly. "Do I need to repair anything for tomorrow?" gets "No, you do not need to repair anything for tomorrow… There is nothing to fix or secure because of the weather."
  - Off-topic questions get the weather-safety part, never "ask a repair worker".
  - "What should I wear or bring" questions follow the reviewer's Vietnamese example: forecast first, then each action once. Answering first there made the clothing appear twice.
- **Fixed in code:**
  - °F gets °C in every language but English ("51°F (11°C)"), as in the alerts.
  - Vietnamese "Bạn nên …" becomes "Hãy …".
  - The data line is written by the server in the reader's language: "Dựa trên dữ liệu cho Stockton, CA lúc 12:48 trưa thứ Tư."
- **Example numbers:** the example's numbers differ from any real day, so the model can't copy them. It still wrote the real 51°F → 66°F.

**Speed.** Each answer carries a timing breakdown (`timings_ms`), also logged. Measured on 3 questions (EN/ES/VI), standard `muse-spark-1.3`, fresh calls:

| | Before | After |
|---|---|---|
| Model call | 3.0–6.5 s (461–1,190 hidden reasoning tokens; `low` effort, 1,500 max) | 2.7–3.8 s (203–405; `minimal` effort, 900 max) |
| Zone data | 0.5–1.3 s (stale snapshot rebuilt on every question) | ~12 ms (stored or in-memory snapshot; data, alerts and budget read in parallel) |
| Total | 3.8–7.8 s locally; ~10–11 s on AWS | **2.7–3.8 s locally** |

- `low` effort with a 700-token cap failed 2 times out of 3: reasoning used up the whole limit.
- The model client (OpenAI SDK import, API key from SSM) is created during Lambda init, not inside the first question.
- Ask always uses the standard model, never `-contributor`: questions are real user input.
- Streaming isn't possible behind an API Gateway HTTP API, and Python Lambdas have no native response streaming. So the screen shows progress in steps instead: "Checking today's weather data…" → "Writing your answer…" → "Almost done…" after 6 s.
- A live answer costs about $0.003.

**Cooling centers and shelters: web search with sources** (`places.py`). Questions that ask for a place ("Where can I cool off?", "Gần Stockton có trung tâm làm mát nào không?") get a live web search. It uses Muse Spark 1.3 search grounding: the Responses API `web_search` tool, with the zone's city as the location.
- **Instructions:** official city, county, state, library or Red Cross sources only; at most 3 places as "name: address, hours", exactly as the source states; say how old the source is; never invent places.
- **Checked in code:**
  - The answer is used only if it cites a web source, and the sources are always shown as links.
  - Medical wording replaces it with the fixed 211 sentence.
  - A fixed sentence is always added: "Openings and hours change: call 211 or the place before you go."
  - If nothing is cited after one retry, the answer is the fixed 211 sentence **with three tappable links**: "Call 211" (a `tel:` link), 211.org, and the county website. The county site is known for the demo zones (San Joaquin, Merced); any other area gets USA.gov's directory of local governments, because a county URL is never guessed. Place answers that do have sources show the same links.
- **What triggers it:** `PLACE_QUESTION` in `ask.py` matches cooling or warming centers/stations/zones/places, shelters, "where can I go / stay / cool off", "somewhere cool", and the same in Spanish, Vietnamese, Chinese, Tagalog, Korean and Arabic. It looks only at the question, never at the weather, so a mild day can't skip it. Over the daily budget there's no search, but the sentence and links still appear.
- **Measured:** 6–12 s, about $0.02–0.03 per question (2–5 searches at $0.0025, plus tokens). It found the City of Stockton's current cooling zones list (updated 08/18/2026).
- **Failure found on the live app (2026-10-28):** "Where is the cooling center near me?" returned only the plain 211 sentence. It was not a timeout (the search took under 10 s) and not the trigger. Cause: **the 1,500-token output limit.** About 1 run in 4 made up to 10 searches, used all 1,500 tokens (reasoning included) and stopped with status `incomplete`. Its last message was a note, "I'll open the county page…", with no citation, which the guardrail correctly refused.
  - **Fix:** at most 3 searches (told in the instructions), 2,500 tokens, and a retry (at most 2 searches, 3,000 tokens, `minimal` reasoning) when the first try times out, runs out of tokens or has no citation.
  - **Result:** 7 of 8 live runs cited a source, the slowest in 11.9 s.
  - **Remaining:** the other run finished normally but wrote an uncited answer from search snippets after two page opens failed (its list was from 2024). Both tries did the same, so it fell back to the 211 links. That is the guardrail working, at about 1 run in 8.
- **Time budget:** the search and its retry get 22 s together (12 s for the first try), inside Ask's 28 s Lambda timeout and API Gateway's hard 30 s limit. The 150 s limit applies only to the alert agent. The app now waits 29 s for an Ask answer.
- **Stale sources:** one earlier test found the county's 2021 list. That's why the answer states the source date and the check-first sentence is fixed.

## Supervisor view and pre-shift talk

`POST /pretalk {zone, lang}` (`pretalk.py`, Ask Lambda) gives a crew supervisor today's checklist and a short talk to read aloud before the shift.
- **The checklist is fixed text in code**, picked by today's data:
  - **Every day:** water (about 1 quart per worker per hour) and an emergency plan with 911.
  - **California:** shade at 80°F; high-heat procedures at 95°F, with the 10-minute cool-down every 2 hours for farm work; extra care for new workers in a heat wave (Cal/OSHA T8 §3395).
  - **Smoke:** reduced exposure and N95 for voluntary use at AQI 151+ wildfire smoke (T8 §5141.1). On ozone days, the item says masks don't help.
  - **Outside California:** federal OSHA "Water, Rest, Shade".
- **The talk:** Muse Spark 1.3 writes 5–7 spoken sentences in the crew's language, only from that checklist and today's numbers.
- **Guardrails:** medical wording, or mask advice without particle pollution, replaces the talk with the checklist itself. Temperatures get °C in code.
- **Languages:** EN/ES/VI checklists are written in code. For zh/tl/ko/ar the checklist shows in English and the talk is labeled automatic.
- **In the app:** the talk can be read aloud or shared in the crew's WhatsApp group. It costs about $0.004, with 10 per IP per hour; over the daily budget, the checklist still works.
- **Live:** a 108°F Spanish talk covered water, shade, the 9 hours at 95°F+, rest every 2 hours, new workers and 911 (3.9 s). A Tagalog talk on today's mild Stockton data (69°F) covered water and the emergency plan only.

## Sharing, decision history and screen languages

- **WhatsApp share:** answers, alerts and pre-shift talks have a "Share on WhatsApp" link (`wa.me`). The text carries a link back to the same area and language (`?zone=…&lang=…`).
- **Decision history page** ("How ClimateGuard decides"): the public `/decisions` feed for your area or all areas. It shows the 7-day counters, then each decision: sent or no alert, the agent's reason (in English, as written), the alerts in the reader's language, and the steps with cost.
  - **Bug found while building it:** the collector's IAM role couldn't write the daily counters (`AccessDenied` on `UpdateItem` for the rate-limit table, on every run), so the history showed 0 checks. Fixed in `template.yaml`, with a test.
- **Screen languages:** EN/ES/VI are written by hand (`strings.js`). Chinese, Tagalog, Korean and Arabic are translated by Muse Spark 1.3 (`scripts/translate_ui.py`, about $0.02 per language) into `i18n.auto.json`. They are labeled "Screen text translated automatically".
  - Checked in code: every key, every `{placeholder}`, and names and numbers that must not change (911, 211, N95, OSHA…).
  - The risk badges are told never to use the NWS level words.
  - Arabic switches the page to right-to-left.

## Recovery agent (photos after a disaster)

`recovery.py` and friends, in their own Lambda (`climateguard-recovery`). It runs as an async job because it takes longer than API Gateway's 30 s: the app creates a job, uploads 1 to 6 photos, starts the analysis and polls `GET /recovery/{job}` every 2 s.

1. **Pick a disaster** (flood, wildfire, earthquake, storm, heat or power outage, other) or let the agent decide from the photos. Questions, damage labels and checklists are fixed data keyed by disaster type (`recovery_data.py`), so nothing is flood-only.
2. **Photos are cleaned twice.** The phone redraws each photo on a canvas (upright, at most 1,280 px, a fresh JPEG with no EXIF, so no GPS). The server strips metadata again (`photos.py`). Photos sit in a private S3 bucket with no public links, are deleted by the collector after 24 hours, and have a "Delete now" button.
3. **One vision call** (Muse Spark 1.3, standard model, never the contributor model for real photos) reads all photos: areas, visible damage, danger, which damage types to outline, which questions to ask. It can only pick ids from the fixed lists.
4. **SAM 3.1 outlines the damage:** once per chosen damage type per photo, at most 3 per photo, in parallel. SAM masks cover their box, not the whole photo, so use noun concepts ("debris"), not adjectives. Masks are dropped under 1.5% of the photo (debris, furniture), 0.05% (water line, crack, mold, mud: thin by nature) or 0.3% (other labels). The water-line prompt is "water stain line on wall": plain "water stain" found nothing on the demo flood photo, and "stain on wall" or "cracked wall" outline the whole wall. Flood photos may also ask for cracks.
5. **2 to 4 fixed follow-up questions**, then **one text call** writes the report in the person's language plus English. The checklist per disaster is fixed text; the model only adds a detail sentence to some items.
6. **Danger first:** if the photos show danger, the first line of every screen and of the report is "Leave the area now and call 911 from a safe place."
7. **Guardrails in code, in all 7 languages** (`recovery_guard.py`): no safe/unsafe verdicts about the building, no repair costs or prices, no medical or injury advice, and the home is always "your home" (never owned or rented). A line that breaks a rule is retried once, then dropped.
8. **Print or save as PDF:** "Not an official damage estimate" on every page.
9. **Limits and cost:** 6 reports per IP per hour; at the $3/day hard model-spend cap it returns HTTP 429 with a friendly "very busy" message. About $0.01 for 1 photo and about $0.07 for 6 (one vision call about $0.01, SAM $0.0025 per damage type per photo, report about $0.007).
10. **Checked with** `python scripts/run_recovery_eval.py` (6 trick cases, about $0.04). Spanish and Vietnamese screen text for review: `docs/recovery-text-es-vi.md`.

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

## Demo mode

"Try the demo" on the home screen (or `?demo=1`) shows every feature in about a minute: no sign-up, no email, no photos of your own.

- **Replay alerts:** one button per real event (2022 heat wave, record-day morning; 2023 Planada flood, night of the flood warnings; 2020 smoke peak). `POST /demo/replay {event, lang}` runs the **real monitoring agent** on that moment and shows the alert in the chosen language, labeled "REPLAY of a real event", with the agent's decision, reason and cost.
  - Each run gets its own `DEMO-<event>-<id>` log, so earlier demo runs never make the agent skip a duplicate. Nothing is emailed and nothing enters the live history. Repeats within an hour reuse cached model answers ($0, and the page says so). zh/tl/ko/ar alerts are translated automatically and labeled.
  - **Fallback:** over the $3/day budget, over the rate limit (15 per IP per hour), or when the agent takes more than 23 s or fails, the page shows an **earlier real run** of the same moment with its date and the reason, never an error. These saved runs (`data/demo_saved.json`) come from the local replay/eval logs: `python scripts/save_demo_replays.py`.
- **Recovery with sample photos:** tap a sample photo (it goes through the same canvas step as your own photos), then the normal flow: outlines, questions, report, checklist, PDF. Same rate limit and budget guard as real reports. Sample photos (public domain, US government works, via Wikimedia Commons; credited in the app):

  | Photo | Credit | Source |
  |---|---|---|
  | Storm | Greg Henshall / FEMA, Greensburg, Kansas, 2007 | [FEMA 30163](https://commons.wikimedia.org/wiki/File:FEMA_-_30163_-_Tornado_damaged_home_in_Kansas.jpg) |
  | Flood | Liz Roll / FEMA, Liberty, Kentucky, 2010 (water line from the Green River flood) | [FEMA 44499](https://commons.wikimedia.org/wiki/File:FEMA_-_44499_-_Liberty_Kentucky_water_damage.jpg) |
  | Fire | Susie Shapira / FEMA, Pauma, California, 2007 (cropped to leave out a bystander) | [FEMA 33504](https://commons.wikimedia.org/wiki/File:FEMA_-_33504_-_debris_from_a_burned_home_in_California.jpg) |
  | Earthquake | J.K. Nakata / USGS, Watsonville, California, 1989 | [089srUSGSoffFoundation](https://commons.wikimedia.org/wiki/File:089srUSGSoffFoundation.jpg) |
- **Ask and Supervisor view** use Stockton (`CAZ159`) as the sample area, kept apart from the person's own saved area. Ask offers three sample questions.
- **How it works** strip with the history page link and the live site's real AI cost since launch (`GET /demo`, summed from the usage log one day at a time, cached 15 minutes).

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

**Run 5, after Vietnamese review round 2 (2026-10-27, one run, fresh samples, 36 cases):** **35/36** (real 11/11, edge 16/16, **hard 8/9**). No mask advice on any ozone-only alert (28/28 checked), mask advice kept when smoke and ozone were both high (1/1), no medical wording, Vietnamese diacritics 38/38. Guardrail rejections the agent fixed itself: 3 heat-index mentions too close to the air temperature, 1 message too long, 1 medical word (hurricane case). $0.0124 per alert; latency p50 7.4 s / p95 11.4 s. Report: `backend/eval/results/20261027-2125.md`.
- **Failed:** `hard_warning_vs_mild_data` (warning text says 110°F, our data shows 82°F). This time the agent trusted the data and skipped; in run 4 it sent a moderate alert. It's a judgment call, and the result varies between samples.
- **Meaning check (back-translation, new):** 49/62 Spanish and Vietnamese messages matched the English. Of the 13 flagged, **8 are real meaning errors**: Vietnamese "rất có hại cho sức khỏe" (= Very Unhealthy) used for Unhealthy AQI 157–185 (4 alerts); Spanish "en la tarde" (afternoon, the hottest time) for "evening" (2); a Flood **Watch** called "Cảnh báo" (warning) in Vietnamese (1); "2 AM tonight" written as "2 giờ sáng nay" (this morning) (1). The other 5 were the checker's mistakes or wording the reviewer approved (the added weekday, "chỉ"). None of these is caught by code yet.

**Run 6, after the reviewer's wording decisions (2026-10-27, the 19 affected cases only, fresh samples):** the four meaning errors became code checks: Vietnamese AQI category wording from the AQI value; Vietnamese level names (Warning "Cảnh báo", Watch "Cảnh giác", Advisory "Khuyến cáo", never "Cảnh báo" without a warning); "rạng sáng [weekday]" instead of a past "sáng nay"; no Spanish "en la tarde" in work advice. Replayed over run 5's messages, the checks caught all 8 real errors, none of the 5 false flags, and 4 more watches or advisories called "Cảnh báo". **Meaning match 48/52 (92%, up from 49/62 = 79%).** Of the 4 still flagged, 2 are the checker's mistakes (it doesn't know the date) or wording the reviewer approved, 1 is "may be unhealthy" written as certain, and 1 is the reviewer's own phrasing ("Nếu bạn ở vùng trũng thấp, …") making an unconditional "move to higher ground now" conditional. 18/19 cases passed: `hard_warning_plus_other_watch` sent the heat alert but chose not to send the fire-weather watch ("to keep a single-hazard message"), an agent judgment that varies between runs (it passed in runs 4 and 5). Report: `backend/eval/results/20261027-2138.md`.

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
- **Vietnamese still needs human review.** A native speaker reviewed the style, and the prompt now carries their rules. In run 4 one Vietnamese sentence reversed the meaning of the English ("limit outdoor work *to* early morning or evening" came out as "limit outdoor work *in* early morning or evening"). The eval now back-translates every Spanish and Vietnamese message into English with a second model and flags meaning differences (run 5: 8 real errors in 62 messages, listed above). It's a flag for human review, not a pass/fail gate: the checker is a model too and was wrong 5 times out of 13.

## Public decision history

`GET /decisions?zone=&days=7&limit=50` returns the live agent's **real** decisions since deployment, newest first, and is public.

- **Each decision shows:** time, zone and place, sent or skipped, the agent's reason, risk signals, the tools it called (including any guardrail rejections), the alerts it sent, model calls and cost.
- **Live only:** replays and evals live in their own `REPLAY-*`/`EVAL-*` logs, so they can never appear here.
- **Daily counters:** decisions are only written when a zone's data materially changes, so a quiet week has few rows. The response therefore also carries daily totals recorded by every collector run:
  - collector runs and zone checks
  - data changes and pre-filter skips
  - agent runs, budget skips and alerts sent
  - errors and model cost

  An example of how a quiet week reads: "2,000 checks · 9 changes · 7 skipped by pre-filter · 2 agent runs · 0 alerts". The page is "How ClimateGuard decides" in the app.

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
| `POST /ask {question, lang, zone}` | Answer a question from live data (Ask Lambda) |
| `POST /transcribe?lang=` (body: WAV) | Spoken question → text (Ask Lambda) |
| `POST /pretalk {zone, lang}` | Supervisor view: today's crew checklist + AI pre-shift talk (Ask Lambda) |

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
`deploy.ps1` finds Python 3.12 by itself (even if `python` on `PATH` or an active `.venv` is another version), so no `PATH` changes are needed.

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

**4. Build is part of deploy.** `deploy.ps1` runs `sam build` with Python 3.12 after the preflight. This packages `backend/src` and its dependencies as Linux arm64 wheels, about 28 MB. `-SkipBuild` deploys the existing `.aws-sam` build as is.

**5. Preflight, build, then deploy.**
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # if scripts are blocked
.\deploy.ps1 -PreflightOnly                                   # dry run: checks only, creates nothing
.\deploy.ps1 -Contact you@example.com                         # preflight + sam build + sam deploy
.\deploy.ps1 -Contact you@example.com -FrontendUrl https://<app>.vercel.app   # once the frontend is live
```
CORS always allows `http://localhost:5173` and `http://localhost:5174` for local dev, plus `FrontendUrl`, which is also the link in alert emails.
- **Saved after a deploy:** a successful deploy that passes `-FrontendUrl` saves it to `deploy.local.json` (untracked), and later deploys reuse it without the flag.
- **Guarded against resets:** if a deploy would switch the live stack from a real URL back to localhost, the preflight shows a red warning and the deploy waits for you to type `reset`.
- Live frontend: https://climate-guard-khaki.vercel.app (Vercel, root directory `frontend`, env `VITE_API_URL`).
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
| Worst single day (major event, 60% of zones, 4 runs each) | $0.24 | $2.40 | $12 (the **$3/day budget** caps new model calls) |
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
