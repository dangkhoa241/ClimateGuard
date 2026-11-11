# PWA and web push: implementation plan

Branch: `feature/pwa-push` (from `main`). Status: **approved with the revisions below; implementation in progress.**
Baseline before any change: backend **549 passed** (pytest), frontend **88 passed** (node --test) and **85 passed** (vitest).

## Approved revisions (these override anything below that conflicts)

1. **Storage**: new `climateguard-push` table, 1 RCU / 1 WCU. Approved.
2. **Library**: `pywebpush`, pinned, with an offline arm64 wheel check. Approved.
3. **Push title = the email's validated subject line for that alert and language** (`notify.compose()`), not ClimateGuard's risk label alone. **Finding while implementing:** the email subject does *not* by itself carry the official NWS level name. English has our own level (`HIGH heat alert`), Spanish and Vietnamese have no level word (Vietnamese deliberately says "thong bao"), and zh/ko/ar use the English subject. So the title is the subject **plus the official level name** (Warning, Watch or Advisory, in the subscriber's language: Aviso/Vigilancia/Advertencia, Cảnh báo/Cảnh giác/Khuyến cáo, the English NWS word for zh/tl/ko/ar) whenever the alert's validated English message names one (highest wins: Warning, then Watch, then Advisory). A test asserts the title contains the level name for every language whenever the alert has one. Body: first one or two sentences of the validated message.
4. **One place and language per device.** Approved.
5. **Caps and limits**: total push subscriptions capped at 500 (`MaxPushSubscribers`), and the same style of rate limits as email sign-up (per IP per hour, per endpoint per day, whole app per day).
6. **Time budget**: push runs only after every email is published, with a total budget (default 20 s, `PUSH_BUDGET_S`) that also stops starting new sends. Collect's 600 s Lambda timeout therefore cannot be reached because of push. Tested with a fake clock and slow senders.
7. **Cost note**: a push-only zone becomes a monitored zone, so it can trigger agent runs (about $0.013 per alert, plus translation for zh/tl/ko/ar). That spend counts under the existing `DailyModelBudgetUsd` ($10/day) cap like email-driven zones; push itself adds no model calls and no new cost line.
8. **Delivery options**: every push is sent with `TTL = 6 hours` (21600 s) and `Urgency: high`.
9. **Endpoint allow-list**: HTTPS only, no port or credentials, hostname must equal an allowed host or end with `.` + an allowed suffix (so `evilfcm.googleapis.com`, `fcm.googleapis.com.evil.com`, `push.apple.com.evil.com` fail). Tested with look-alike domains.
10. **Unsubscribe requires the subscription endpoint itself** (the endpoint URL is the secret; there is no other identifier, no listing by zone).
11. **Vercel previews and the CORS change are out of scope.** The push UI sits behind a flag: it is **hidden unless the URL has `?push=1`** (remembered for the session in `sessionStorage`), and demo mode never subscribes. Service worker registration and the offline shell are not behind the flag. The flag is removed after your phone test, in a separate change.

## 0. What I found in the repo (it shapes the design)

- The frontend already has a `manifest.webmanifest` (192/512 icons, no maskable, no `id`/`scope`), `apple-touch-icon`, and theme color `#C2410C`. It has **no service worker**. Navigation is hash-based (`#/alerts`), and email links already open `/?zone=CAZ159&lang=es` (App.jsx reads `zone`, `lang`, `demo`). So "open the matching alert page in the user's language" needs no new routing: the push URL is the same link the email uses.
- Alerts reach people in `notify.deliver()` (called from `monitor.tool_send_alert`, which Collect runs). It already builds the per-language texts (EN/ES/VI from the agent, zh/tl/ko/ar machine-translated and labeled) and publishes to SNS per (zone, language).
- A zone is only monitored when `zones.monitored()` sees `confirmed > 0`, and `confirmed` is recounted from SNS by `subscriptions.refresh_confirmed()`. **A push-only subscriber is invisible to that today**, so the design must count push subscribers or their zone would never be collected. This is the most important integration point.
- DynamoDB is provisioned at 15 RCU / 18 WCU of the 25/25 free tier. `deploy.ps1` checks that total (all tables, all regions).
- `ssm.get_secret()` already reads SecureStrings at runtime, and the template already uses `SSMParameterReadPolicy` with the free AWS-managed `aws/ssm` key. VAPID reuses this pattern.
- API Gateway CORS allows `GET, POST, DELETE, OPTIONS` and `Content-Type`; request bodies are capped at 2 KB (enough for a push subscription).

## 1. Decisions I need from you (my recommendation first)

1. **New table, not the existing ones.** Recommend a new `climateguard-push` table (PK `zone`, SK `lang#<endpoint hash>`, TTL `ttl`, provisioned **1 RCU / 1 WCU**). Total goes to 16 RCU / 19 WCU of 25/25, still free. Reasons: the RateLimit table has no sort key (cannot "list all subscribers of zone+language"), and putting subscriptions in the Alerts table would mix a long-lived record with 14-day sent alerts and widen that table's permissions. The cost is one more table and one IAM policy. A fan-out query is one `Query` per (zone, language).
2. **Library: `pywebpush` (pinned) for encryption and VAPID signing**, rather than hand-rolling RFC 8291/8292 with `cryptography`. Adds `pywebpush`, `py-vapid`, `http-ece`, `cryptography` to `backend/src/requirements.txt`. Risk: `sam build` must fetch arm64 wheels for `cryptography`. I will check this **without running sam build** using `pip download --platform manylinux2014_aarch64 --only-binary=:all:` into the scratchpad, and report the result.
3. **"Official level name" in the notification.** The repo has two kinds of level names: ClimateGuard's own risk levels (`moderate/high/extreme`, shown as "High risk", used in email subjects) and NWS words (Warning/Watch/Advisory), which appear only inside the agent's validated message. My plan: **title = `ClimateGuard · <our risk level in the user's language> · <place>`**; **body = the first one or two sentences of the already-validated message in that language** (so any NWS level word is exactly what the guardrails approved, for example es "Aviso" or vi "Cảnh báo"). I never generate or translate level names in new code. Tell me if you meant something else.
4. **One zone and language per device.** A phone subscribes for one place and one language; changing it replaces the old record. Simpler to explain and to cap than the email rule (3 per address). Say if you want multiple places per device.

## 2. Frontend (React/Vite)

### 2.1 Manifest, icons, theme
- Extend `public/manifest.webmanifest`: `id`, `scope`, `lang`, `description`, `orientation: portrait`, keep `display: standalone`, colors; icons 192 and 512 (`purpose: any`) plus `icon-maskable-192.png` and `icon-maskable-512.png` (`purpose: maskable`).
- Maskable icons: generated once from the existing 512 icon with a safe-zone padding (content inside the central 80%) by a small committed script `frontend/scripts/generate-icons.mjs` or a one-off Pillow command (Pillow 11.3 is installed). I will look at the result before committing; if the current icon is not centered I will tell you rather than redesign it.
- `index.html`: add `mobile-web-app-capable`, `apple-mobile-web-app-capable`, `apple-mobile-web-app-title`, `apple-mobile-web-app-status-bar-style`. Theme color stays `#C2410C`.

### 2.2 Service worker (`public/sw.js`, hand-written, no plugin)
- **Caches only the app shell and static assets**: on `install` it fetches `/`, reads the hashed `/assets/*` URLs out of the HTML, and caches those plus the manifest, icons, and favicon in a versioned cache (`cg-shell-v1`). Old caches are deleted on `activate`.
- **Fetch rules** (everything else is not intercepted, so the browser handles it normally):
  - Cache only `GET`, same-origin requests.
  - Navigation requests: network first, fall back to the cached shell (the offline page is the app itself).
  - `/assets/*` and the static files above: cache first.
  - **Never touched**: any cross-origin request (the API lives on `execute-api.amazonaws.com`, so every API call, sign-up, photo upload and recovery request bypasses the worker entirely), any non-GET request, and any same-origin path not on the allow-list.
- `push` handler: parses `{title, body, url, tag, lang}`; shows the notification with `dir` and `lang` set (Arabic is RTL); `tag` = zone + hazard so a repeat replaces rather than stacks.
- `notificationclick` handler: closes it, focuses an open ClimateGuard window and navigates it to `data.url`, otherwise `openWindow(url)`. `url` is built server-side as `<FRONTEND_URL>/?zone=<ZONE>&lang=<lang>` (same as emails), so it opens the alert page in the user's language. The worker only opens URLs on its own origin.
- Registration in `main.jsx` only in production builds (not the Vite dev server), `scope: /`. Updates: new worker takes over on next load (no forced reload mid-session).

### 2.3 Offline
- App shell loads offline from the cache.
- **Last alert viewed**: when the alerts list loads, store the most recent alert for that zone and language in `localStorage` (public alert text plus `viewedAt`; no email, no ZIP, no coordinates). If the live fetch fails or the device is offline, the Alerts screen shows that saved alert in a card labeled **"Last updated {time}. May be out of date. Reconnect to check for new alerts."** (new strings), plus a small offline banner driven by `navigator.onLine`. This is application storage, not the service worker caching an API response, so the "never cache API responses" rule holds literally. All `localStorage` access is wrapped in try/catch.

### 2.4 "Install the app" entry
- New `InstallScreen.jsx` (route `#/install`, linked from the home page and from the Get alerts page). Uses the `beforeinstallprompt` event on Android/desktop Chrome and Edge (an "Install" button), and plain steps otherwise:
  - **iPhone/iPad (Safari)**: Share button, "Add to Home Screen", Add, then open ClimateGuard from the Home Screen icon. A clear line that **notifications only work after installing on iPhone** (iOS 16.4+).
  - Android without the prompt: browser menu, "Install app".
  - Already installed (`display-mode: standalone`): shows "Installed".

### 2.5 "Turn on phone notifications" (Get alerts page)
New `PushSignup.jsx` section, separate from the email form (no email field). Steps shown:
1. Pick the place: reuses the existing `LocationPicker` (ZIP or "use my location"), same state as email sign-up.
2. Pick the language: same selector and "automatic translation" notes as the email form.
3. Button **Turn on phone notifications**. On click (a user gesture, required on iOS) it requests permission, then `serviceWorker.ready` then `pushManager.subscribe({userVisibleOnly: true, applicationServerKey: VITE_VAPID_PUBLIC_KEY})`, then `POST /push/subscribe`. The browser subscription is rolled back if the server call fails.
4. When on: shows "On for {place}, in {language}" and a **Turn off notifications** button (`pushManager` unsubscribe plus `POST /push/unsubscribe`; if the server call fails the local unsubscribe still happens and the server record is cleaned on the first 404/410).
- States with specific messages: unsupported browser, iPhone not installed (links to the install screen), permission denied (how to re-enable in browser settings), no VAPID key configured, network or rate-limit errors (same `t.errors` style).
- **Flag**: the whole section and the Install entry's push mention render only with `?push=1`. **Demo mode (`?demo=1`)**: the section renders an explanation instead of the button, and `api.js` push functions plus the subscribe helper refuse to run when the URL has `demo=1`. A test asserts `pushManager.subscribe` and `fetch('/push/...')` are never called in demo.
- API client: `subscribePush`, `unsubscribePush` in `api.js`. Config: `VITE_VAPID_PUBLIC_KEY` in `frontend/.env.example` (public key only) and as a Vercel env var.

### 2.6 i18n (7 languages, new keys only)
- New keys written by hand in `strings.js` for EN, ES, VI (ES not native-reviewed, same status as the rest). Existing keys, including all safety strings (`notCovered*`, 911, disclaimers), are **not touched**.
- zh/tl/ko/ar: `translate_ui.py` currently retranslates every key. I will add a `--new-only` flag that translates just the keys missing from `i18n.auto.json` and merges them in, so no existing safety translation can change. Cost is under about $0.03 total from the Meta credit (not AWS). It needs `MODEL_API_KEY` in your `.env`; if you prefer, I stop and you run it (command given in the report).
- Tests: a `strings` test that every new key exists in all 7 languages with matching `{placeholders}`, and that a snapshot of the existing safety strings is unchanged.

## 3. Backend (SAM, us-east-2)

### 3.1 Storage: new `climateguard-push` table
Items (one table, no GSI, so no extra capacity):
- Subscriber: `zone = CAZ159`, `sk = es#<sha256(endpoint)[:24]>`, attrs `endpoint`, `p256dh`, `auth`, `lang`, `created`, `ttl` (365 days, refreshed when the same device re-subscribes).
- Pointer for unsubscribe: `zone = EP#<hash>`, `sk = ptr`, attrs `zone`, `lang`. Written together with the subscriber in one transaction; deleted together.
- Local mode (`STORAGE=local`) uses a JSON file under `backend/.local`, like the other stores, so everything is testable offline.
- New module `push_store.py`.

### 3.2 API routes (ApiFunction, same patterns as `/subscribe`)
- `POST /push/subscribe` body `{subscription: {endpoint, keys: {p256dh, auth}}, lang, zip | lat+lon, website}`.
- `POST /push/unsubscribe` body `{endpoint}` (POST rather than DELETE because API Gateway and fetch handle a DELETE body inconsistently).
- **Validation**: JSON object only, 2 KB body cap; `lang` in `LANGS`; `endpoint` must be `https://`, at most 600 characters, and its host must match an allow-list of the real push services (`fcm.googleapis.com`, `*.push.apple.com`, `updates.push.services.mozilla.com`, `*.notify.windows.com`). This allow-list is a security control: the backend later POSTs to this URL, so without it a caller could make Lambda request arbitrary hosts (SSRF). `p256dh` must decode to 65 bytes and start with 0x04, and `auth` to 16 bytes (base64url). Honeypot `website` field as in sign-up.
- **Limits** (same style as email, checked before any NWS lookup): per IP 5/hour; per endpoint 10/day; whole app 300/day (503); total push subscribers `MaxPushSubscribers` = 500 (503, a new template parameter, default 500, passed by `deploy.ps1` on every deploy like the others); one zone+language per endpoint. Unsubscribe: per IP 30/hour. Errors reuse the existing `error` codes and `Retry-After` headers.
- Route throttles in `template.yaml`: `POST /push/subscribe` burst 1 / rate 0.2 (same as `/subscribe`); `POST /push/unsubscribe` burst 2 / rate 0.5.
- On subscribe: `zones.locate()` as email does, `zones.add_language(zone, lang)`, and **if the zone's `confirmed` is 0, set it to 1 so the next 15-minute collect run monitors it**. `refresh_confirmed()` is extended to add the push count for each zone (a `Query` with `Select=COUNT`), so the count stays correct afterwards.
- IAM: the ApiFunction gets `DynamoDBCrudPolicy` on the push table and `TransactWriteItems` on it. No SSM or other access.

### 3.3 Sending (Collect), `webpush.py` + a small hook in `notify.deliver()`
- `deliver()` keeps its email loop exactly as is and records the per-language texts it already computed. **After the email loop finishes**, it calls `webpush.send_for_zone(zone, hazard, severity, texts, translated_flags)` inside `try/except Exception`: log and continue, never raise. Emails are therefore already published before any push network call starts.
- `send_for_zone` bounds its own cost: reads the zone's subscribers per language (`Query`), sends with a small thread pool (8 workers), a 5 s timeout per request, and an overall deadline (20 s) after which remaining sends are skipped and logged by count. Collect's Lambda timeout is 600 s and agent runs have their own 150 s deadline, so this cannot starve them.
- **Payload** (JSON, well under the 4 KB limit): `{title, body, url, tag, lang}`.
  - title: `ClimateGuard · <risk level label in the user's language> · <place>` (labels copied from the frontend strings, with a test that the backend table matches `strings.js` and `i18n.auto.json`, the same "keep in step" pattern `notify.py` already uses).
  - body: the first one or two sentences of the zone's validated message in the subscriber's language, `units.format_temps` applied as in email, limited to about 160 characters at a sentence boundary. For zh/tl/ko/ar that were machine-translated, the existing `AUTO_LABEL` or `AUTO_FALLBACK` note is appended, as in email. **No new advice text is generated**: body comes only from text that already passed the medical-wording and level-name guardrails, so the wording rules match email. The full footer (not medical advice, 911) lives on the alert page the tap opens.
  - url: `<FRONTEND_URL>/?zone=<ZONE>&lang=<lang>`.
- Pruning: a `404` or `410` from the push service deletes that subscription (subscriber item plus pointer, and decrements the push counter). Other failures (`429`, `5xx`, timeout) are logged by status class and kept; `413` or `400` are logged without removing.
- Logs contain only counts and status classes (`sent=12 gone=1 failed=0`), never endpoints, keys, or the private key.
- `TTL`: expired items are dropped by DynamoDB TTL; the count is recomputed from the table hourly.

### 3.4 VAPID keys: storage and handling
- **Private key**: SSM Parameter Store **SecureString** `/climateguard/vapid-private-key`, standard tier, default `aws/ssm` key (free; same pattern as the other keys). Read once per container with the existing `ssm.get_secret()`. Only `CollectFunction` gets `SSMParameterReadPolicy` for it (the API function never needs it, since it only stores subscriptions).
- **Public key**: not secret. Goes in the frontend config (`VITE_VAPID_PUBLIC_KEY`, Vercel env var) and in the docs.
- **Generation without the key ever being displayed**: a new script `backend/scripts/make_vapid_keys.py` generates a P-256 key pair, writes the private key straight to SSM (`put-parameter --type SecureString`, refuses to overwrite unless `--force`), and **prints only the public key**. The private key is never written to disk, to the repo, to `.env.example`, to the console, or to any log. You run it yourself; it does not need to be in the chat. A manual fallback with the same behavior is documented.
- **Behavior if the parameter is missing**: push is silently disabled (one warning line in the log, emails unaffected). `deploy.ps1` handles it like AirNow: its step 3 gets a new check that reports `SecureString, N characters` or `WARN missing: web push alerts are off (emails unaffected)`. It checks length and type only, never reads or prints the value, and never creates or changes the key. `deploy.ps1` also passes `MaxPushSubscribers` like the other numeric parameters.
- Contact claim (`sub`) in the VAPID JWT: the `FRONTEND_URL` (an `https:` URL is allowed by RFC 8292), so no email address goes into any token or log.
- Key rotation note for the docs: changing the key invalidates every existing subscription (they must re-subscribe).

### 3.5 Template and packaging changes (no deploy)
`template.yaml`: new `PushTable`; parameter `MaxPushSubscribers`; env vars `PUSH_TABLE`, `MAX_PUSH_SUBSCRIBERS`, `VAPID_PRIVATE_KEY_PARAM`; two routes plus route throttles; IAM for Api and Collect; Collect also needs `DynamoDBCrudPolicy` on the push table. `deploy.ps1`: the checks above. Existing `test_template.py` and `test_deploy_script.py` get new assertions. I will not run `sam build`, `deploy.ps1`, or touch the live stack.

## 4. Cost: stays at $0 on AWS

| Item | Cost | Why |
|---|---|---|
| New DynamoDB table, 1 RCU / 1 WCU | $0 | total 16 RCU / 19 WCU of the 25/25 free tier; the `deploy.ps1` capacity check keeps verifying it |
| Push-related Lambda time | $0 | adds seconds per alert, far inside the free 400,000 GB-seconds; 5 s per-request timeouts and a 20 s overall cap |
| SSM SecureString (standard tier, `aws/ssm` key) | $0 | free |
| Web push delivery (FCM, Apple, Mozilla, Microsoft) | $0 | no AWS service involved; outbound traffic is tiny |
| API Gateway, CloudWatch Logs | $0 | same free allowances; logs are 7-day retention and carry counts only |
| Vercel preview URL | $0 | Hobby plan |
| Meta credit: `translate_ui.py --new-only` | about $0.03 | not AWS; one time |

**Things that could cost money (all avoided by the plan, and worth knowing):**
- An SSM **Advanced** tier parameter ($0.05 per month) or a **customer-managed KMS key** ($1 per month): I use the standard tier with `aws/ssm`.
- Raising the push table above its provisioned capacity, or switching it to on-demand, if the account total passes 25/25 (`deploy.ps1` would warn).
- Sending to the push services from inside a **VPC with a NAT gateway** (about $32 per month): Lambdas here are not in a VPC and I will not add one.
- A **Lambda layer or package size** problem: none expected, but `cryptography` wheels add about 5 MB (far under limits).
- Free-tier expiry (not caused by this work): API Gateway's free 1M requests is a 12-month allowance, and the plan states the Free plan assumption the repo already makes.
- Reserved or provisioned Lambda concurrency: not used (the preflight already blocks it).

## 5. Tests (all offline)

**Backend** (new `tests/test_webpush.py`, `test_push_api.py`, additions to `test_template.py`, `test_deploy_script.py`):
- Subscription validation: endpoint allow-list (SSRF cases: `http:`, IP addresses, `evil.com`, look-alike hosts, `@` in the URL, over-length), key lengths and base64url, bad JSON, oversized body, bad language, honeypot.
- Subscribe/unsubscribe flow in local storage: create, replace on zone change, idempotent re-subscribe, unsubscribe via the pointer, unknown endpoint is a no-op, rate limits and caps return the right codes.
- Fan-out with a fake `webpush`: payload content per language (title uses the right risk label, body from the validated message, auto-translation label appended for zh/tl/ko/ar, `units` applied, URL has zone and lang); matching only the right zone and language; `404` and `410` remove the subscription and keep the counters right; `429`, `5xx`, and timeouts keep it.
- **Isolation**: a `webpush` that raises or hangs does not stop `deliver()` from returning, and a test asserts the SNS or outbox publish calls happen **before** any push call (call-order assertion); missing VAPID parameter means push is skipped and emails still go out.
- No secret leakage: a test sets a recognizable fake private key, runs send and failure paths, and asserts it never appears in captured logs or exception text; the repo-scan test checks that `.env.example` and tracked files contain no VAPID private key pattern.
- Zone monitoring: a push-only subscriber makes the zone monitored; `refresh_confirmed` counts push subscribers.
- Template: new table is provisioned 1/1, TTL on, the policies, the routes, and the free-tier total stays at or below 25/25; the push private key parameter is only readable by Collect; `deploy.ps1` has the key check and never prints values.

**Frontend**:
- `sw.test.js` (node --test, evaluates `public/sw.js` against fake `self`, `caches`, `fetch`): never caches POST, never caches cross-origin or API URLs, caches only the shell allow-list, navigation falls back to the cached shell offline, `push` shows the right title, body, tag and `dir`, `notificationclick` focuses or opens the right same-origin URL and refuses a foreign origin.
- `push.screens.test.jsx` (vitest): idle, unsupported, iPhone-not-installed, permission denied, subscribe success (permission, `pushManager.subscribe`, POST body has no email), server failure rolls back, turn off, demo mode never subscribes or calls `/push`, RTL language renders.
- `install.screens.test.jsx`: Android prompt button, iPhone steps, already-installed state.
- Offline test: failed fetch shows the saved last alert with its time and the "may be out of date" label; nothing saved shows the normal error.
- `strings.test.js` additions for the 7-language new keys and unchanged safety strings; a manifest test (maskable icon present, files exist).
- All existing suites must still pass: backend 549, frontend 88 + 85 at baseline.

## 6. Files I expect to change or add

New: `docs/PWA-PLAN.md` (this file), `frontend/public/sw.js`, `frontend/public/icon-maskable-192.png`, `frontend/public/icon-maskable-512.png`, `frontend/scripts/generate-icons.mjs` (or equivalent), `frontend/src/PushSignup.jsx`, `frontend/src/InstallScreen.jsx`, `frontend/src/pwa.js` (registration, install and push helpers, offline cache), `frontend/src/sw.test.js`, `frontend/src/push.screens.test.jsx`, `frontend/src/install.screens.test.jsx`, `backend/src/climateguard/push_store.py`, `backend/src/climateguard/webpush.py`, `backend/scripts/make_vapid_keys.py`, `backend/tests/test_webpush.py`, `backend/tests/test_push_api.py`.

Modified: `frontend/public/manifest.webmanifest`, `frontend/index.html`, `frontend/src/main.jsx`, `App.jsx` (route and home entry), `AlertsScreen.jsx`, `api.js`, `strings.js`, `i18n.auto.json`, `frontend/.env.example`, `backend/scripts/translate_ui.py`, `backend/src/requirements.txt`, `backend/src/climateguard/handlers/api.py`, `notify.py`, `subscriptions.py`, `zones.py`, `config.py`, `ratelimit.py` (push counters), `backend/scripts/local_api.py`, `template.yaml`, `deploy.ps1`, existing template and deploy tests. **README.md and docs/TECHNICAL.md only at the very end, after everything passes**, including the iPhone known-limitations note (install required, iOS 16.4 or later, no sound when the phone is in silent mode, notifications can be delayed or limited by Focus modes and battery settings).

## 7. Commit plan (small commits on the branch)

1. Manifest, icons, meta tags, install screen.
2. Service worker and registration, offline last-alert view, with tests.
3. Backend: push store, validation, API routes, counters, zone monitoring, with tests.
4. Backend: send path in `notify`/`webpush`, pruning, isolation, with tests.
5. Template and `deploy.ps1` changes, VAPID script, with tests.
6. Frontend: push sign-up screen, api client, demo guard, i18n keys (EN/ES/VI), with tests.
7. zh/tl/ko/ar translations of the new keys (`--new-only`).
8. README and TECHNICAL.md.

Then I run backend pytest, frontend `npm test`, `npm run build`, `cfn-lint`, and the template test, and report: commit hashes, test counts, files changed, and the exact manual steps (generate and store the VAPID key, set `VITE_VAPID_PUBLIC_KEY`, deploy, test on Android and on iPhone with a Vercel preview URL). I stop before any deploy.

## 8. Risks and known limits

- **iPhone**: push works only after Add to Home Screen (iOS 16.4+), needs a user tap to ask for permission, and does not play sound in silent mode. Safari in a normal tab cannot subscribe, which the screen explains.
- **Vercel preview URLs**: previews are served over HTTPS so push works, but each preview origin is a different site: a subscription made on a preview is not valid on production. A preview's origin must also be allowed by the API's CORS (`FrontendUrl` allows one origin; a preview needs a temporary extra origin, which is a stack change you would deploy). I will spell out the options in the report and not change the stack.
- **Delivery is best-effort**: the push services can delay or drop messages, and users can disable notifications. Alerts are supplementary; the existing "not covered" notice and 911 guidance stay unchanged. Short-fuse warnings stay excluded (the agent never sends them, so push cannot either).
- **Key loss or rotation** breaks all existing subscriptions until people re-subscribe.
- The `cryptography` arm64 wheel is the one packaging risk I cannot fully prove without `sam build`; I check the wheel availability offline and tell you the result.
