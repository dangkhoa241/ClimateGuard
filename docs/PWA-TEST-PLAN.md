# PWA and phone notifications: test plan (desktop Chrome, localhost, live API)

Run this **after the backend from `feature/pwa-push` is deployed and before merging to `main`**. It tests the branch's frontend on your own machine against the live API, so nothing changes for people using the live site. Commands are PowerShell from the repo root.

## What you need first

1. **Backend deployed from this branch** (`.\deploy.ps1 ...`). The live stack then has the two push routes and the `climateguard-push` table. The live frontend is untouched: it does not call them.
2. **The VAPID key exists:** `python backend/scripts/make_vapid_keys.py` (prints the public key; `--show-public` prints it again).
3. **AWS CLI signed in** (same sign-in as the deploy), for the test script and the table check.
4. **Chrome on Windows, with notifications allowed:** Windows Settings, System, Notifications: on for Google Chrome, and Do not disturb off.

## Why this works from localhost

- **CORS:** `template.yaml` always allows two dev origins next to `FrontendUrl`: **`http://localhost:5173`** (`LocalDevOrigin`) and **`http://localhost:5174`** (`LocalDevOrigin2`). `deploy.ps1` never passes these two parameters, so the live stack keeps the defaults; the preflight prints the `CORS AllowOrigins` line and warns if the live values differ. Use `localhost`, not `127.0.0.1` (a different origin, which CORS would block).
- **Service worker and push** need a secure context, and `http://localhost` counts as one.
- **Use the production build, not `npm run dev`:** the service worker is registered only in a production build (`import.meta.env.PROD`). `npm run dev` would show the screens but never install the worker, so install, offline and push could not be tested.

## Start the app

Create `frontend/.env.local` (ignored by git) with the live API URL and the public key:

```powershell
$api = aws cloudformation describe-stacks --region us-east-2 --stack-name climateguard --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
$pub = (python backend/scripts/make_vapid_keys.py --show-public) -replace "^Public key: ", ""
"VITE_API_URL=$api`nVITE_VAPID_PUBLIC_KEY=$pub" | Set-Content -Encoding ascii frontend/.env.local
```

Build and serve it on the allowed port (the exact command):

```powershell
cd frontend
npm run build
npm run preview -- --port 5173 --strictPort
```

`--strictPort` makes it fail instead of silently moving to another port. If 5173 is taken, use `--port 5174` (the other allowed origin) and replace 5173 with 5174 everywhere below.

Open **http://localhost:5173/?push=1** in Chrome. Keep DevTools open (F12), tab **Application**.

## Tests

Use ZIP code **95202** (Stockton). It is a demo zone that is always monitored, so your test subscription does not add a new zone for the agent to watch (no extra model spend).

| # | Step | Expected |
|---|---|---|
| 1 | **Service worker.** Application, Service workers. | `sw.js` is "activated and is running". Application, Cache storage shows one cache named `cg-shell-<12 characters>` holding `/`, the `/assets/*` files, icons and the manifest. No API URL is in it. |
| 2 | **Install.** Open `http://localhost:5173/#/install`, click "Install the app" (or the install icon in the address bar). | Chrome asks to install; ClimateGuard opens in its own window. The install page then says it is installed. Application, Manifest shows no errors and lists the maskable icons. |
| 3 | **Flag.** Open `http://localhost:5173/#/alerts` in a **new incognito window** (no `?push=1`). | No "Phone notifications" section. Close the incognito window. |
| 4 | **Subscribe.** In the normal window: `http://localhost:5173/?push=1#/alerts`, enter 95202, in "Phone notifications" choose **Español**, click "Turn on phone notifications", allow. | "Notifications are on for Stockton, CA, in Español." Network tab: `POST .../push/subscribe` answers **201**, and its request body has `subscription`, `lang`, `zip` and no `email`. |
| 5 | **Table has the device.** `aws dynamodb scan --region us-east-2 --table-name climateguard-push --select COUNT` | `"Count": 2` (the subscriber and its pointer item). |
| 6 | **Dry run.** `python backend/scripts/send_test_push.py --dry-run` | "1 subscription(s) for the most recent subscription: zone CAZ159, language es", nothing sent. No endpoint or key is printed. |
| 7 | **Test notification.** `python backend/scripts/send_test_push.py --open-url http://localhost:5173` | "Sent 1, gone 0, failed 0." A Windows notification appears: title **ClimateGuard**, text **Notificación de prueba de ClimateGuard**. |
| 8 | **Tap opens the right page and language.** Click the notification. | The ClimateGuard window comes to the front at `http://localhost:5173/?zone=CAZ159&lang=es`: the **Get alerts** page, in **Spanish**, for Stockton. Repeat step 7 with every ClimateGuard window closed: a new window opens at the same address. |
| 9 | **By ZIP code.** `python backend/scripts/send_test_push.py --zip 95202 --open-url http://localhost:5173` | Same notification again (the script found the zone from the ZIP code). |
| 10 | **Offline view.** On Get alerts with Stockton chosen, wait for "Recent alerts" to load. Then DevTools, Network, set **Offline**, and reload. | The app still loads (the shell comes from the cache) with the yellow "You are offline" line. If Stockton had an alert in the last 2 days, it is shown under "Last alert you viewed. Updated <time>. May be out of date." If there was no alert, there is nothing saved to show and you see the normal "could not load" message: that is correct. Set the network back to **No throttling**. |
| 11 | **Demo never subscribes.** Open `http://localhost:5173/?demo=1&push=1#/alerts`. | The section says demo mode never turns on notifications, and has no button. No `/push/` request in the Network tab. |
| 12 | **Turn off.** Back on `http://localhost:5173/?push=1#/alerts`, click "Turn off notifications". | The button to turn them on is back. Network tab: `POST .../push/unsubscribe` answers **200**. |
| 13 | **Table is empty.** `aws dynamodb scan --region us-east-2 --table-name climateguard-push --select COUNT` | `"Count": 0`. |
| 14 | **Nothing left to send to.** `python backend/scripts/send_test_push.py` | "No subscriptions found ... Nothing was sent." |

### Optional: updates and the kill switch (local only, changes nothing in the repo)

| # | Step | Expected |
|---|---|---|
| 15 | **A new build replaces the worker.** Stop the preview. Change any visible text in `frontend/src` temporarily, run `npm run build`, start the preview again, reload the page twice. Undo the text change afterwards (`git checkout -- frontend/src`). | Service workers shows a new `sw.js` activated without closing the tab. Cache storage has **one** cache with a **different** `cg-shell-<id>`; the old one is gone. |
| 16 | **Kill switch.** With the preview running: `Copy-Item frontend/dist/sw-kill.js frontend/dist/sw.js -Force` (the built copy only), then reload the page twice. | Service workers is empty (unregistered) and Cache storage is empty. The site still works online. `npm run build` puts the normal worker back. |

## Clean up

1. Stop the preview (Ctrl+C).
2. In Chrome at `http://localhost:5173`: DevTools, Application, Storage, **Clear site data** (removes the test service worker, caches and saved choices, so it cannot affect later local development on that port).
3. Uninstall the test app: in its window, the three-dot menu, "Uninstall ClimateGuard".
4. You can delete `frontend/.env.local` (it holds no secret: the API URL and the public key).

## What this plan does not cover

- **A real alert.** `send_test_push.py` proves delivery, the tap and the language. The alert wording (title with the official level name, body from the validated message) is covered by the offline tests, and by the first real alert after the merge.
- **A real alert's link from localhost.** Real alerts link to the production site (`FrontendUrl`). A worker installed at localhost only opens its own site, so tapping a real alert there opens the localhost home page. That is why the test script has `--open-url`.
- **Android and iPhone.** After the merge, test on the production URL with `?push=1`: on iPhone only after Add to Home Screen (iOS 16.4 or later), and expect no sound in silent mode. A subscription made at localhost does not exist on the production site.
- **Limits you can hit while testing:** 5 sign-ups per IP per hour and 10 per device per day. If you get "Too many attempts", wait an hour.
