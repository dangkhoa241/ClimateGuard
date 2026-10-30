# ClimateGuard handoff (Wed Oct 28, 2026)

## Status
- Phases 0–5 are done and deployed. Latest commit: **68bb5e5**. About 2 days ahead of schedule.
- Offline tests: 491 backend (`pytest`) + 22 frontend (`npm test`) passing. Ask eval: 7/7 on Oct 28 (the cooling-center cases were rechecked live after ed237f7: 7 of 8 cited a source). Agent eval: 35/36, back-translation meaning match 92% (Oct 27).
- Spend: Meta about $1.5 of $150 (Phase 5 live checks added about $0.1), Baseten $1.90 of $100, AWS $0. Check `scripts/spend.py` for exact numbers.
- Subscribed: ZIP 95202 (Stockton, CAZ159), Vietnamese.

## Live
- Frontend (Vercel, auto-deploys on every push to `main`): https://climate-guard-khaki.vercel.app
- API (AWS us-east-2, SAM): https://mvte1tq4tg.execute-api.us-east-2.amazonaws.com
- Repo: https://github.com/dangkhoa241/ClimateGuard
- **What works:**
  - Email alerts in 7 languages; EN/ES/VI are human-reviewed, zh/tl/ko/ar are labeled automatic.
  - Ask by text or voice, answers with sources, and read-aloud on the phone's voices.
  - Cooling centers and shelters from a cited web search, with a fixed 211 sentence and tappable links (Call 211, 211.org, county site) as the fallback.
  - Supervisor view with a fixed Cal/OSHA checklist and an AI pre-shift talk.
  - History page "How ClimateGuard decides".
  - WhatsApp share, and screen text in 7 languages (Arabic right-to-left).
  - **Recovery (Phase 5):** pick a disaster (or let the agent decide), add 1 to 6 photos (EXIF/GPS stripped on the phone and again on the server; kept 24 h in a private S3 bucket, deleted by the collector, with a "Delete now" button). Muse Spark reads the photos, SAM 3.1 outlines the damage, 2 to 4 fixed follow-up questions, then a report in your language plus English, a fixed checklist per disaster, and print-to-PDF ("Not an official damage estimate" on every page). Danger in the photos puts "leave and call 911" first. Guardrails in code: no safe/unsafe verdicts, no costs, no medical advice, "your home" (never owned/rented). Auto-scroll to the questions, the report and errors.
- **Routes:**
  - `GET /locate`, `/zones/{zone}`, `/zones/{zone}/alerts`, `/languages`, `/decisions`
  - `POST /subscribe`, `/ask`, `/transcribe?lang=` (WAV body), `/pretalk`
  - **Recovery (own Lambda `climateguard-recovery`, async jobs):** `POST /recovery`, `POST /recovery/{job}/photos?i=` (JPEG body), `POST /recovery/{job}/analyze`, `POST /recovery/{job}/answers`, `GET /recovery/{job}` (the app polls every 2 s), `DELETE /recovery/{job}`
  - The history page reads `/decisions`; its daily counters now work (the collector permission bug is fixed).

## Deploy and test
- Backend deploy: `.\deploy.ps1 -Contact dangkhoa2401bg@gmail.com`
  - The Vercel URL is saved in `deploy.local.json` (untracked), so no `-FrontendUrl` is needed.
  - A deploy that would reset it to localhost shows a red warning and waits for you to type `reset`.
- Frontend: push to `main`. For local work, use `frontend\.env.local` (it points at the AWS API) and run `cd frontend`, then `npm run dev -- --port 5173 --strictPort` (or 5174). CORS allows both.
- Tests: `cd backend; .venv\Scripts\python -m pytest -q tests`. Frontend: `cd frontend; npm test` and `npx vite build`.
- Evals (spend credits): `python scripts/run_ask_eval.py` (about $0.04; `--effort minimal low` compares reasoning), `python scripts/run_eval.py --fresh` (about $0.25). Run from `backend` with the venv.
- Recovery: `python scripts/run_recovery_eval.py` (6 trick cases, about $0.04), `python scripts/smoke_sam.py photo.jpg "debris"` (about $0.0025 per concept). Local API for the app: `python scripts/local_api.py`.
- Spend: `python scripts/spend.py` for the local log; `$env:STORAGE="dynamodb"` first for the deployed log.
- Screen translations: `python scripts/translate_ui.py` (about $0.08). Rerun after changing English strings in `frontend/src/strings.js`.

## Know before continuing
- Cooling-center search still returns the 211 links in about 1 run in 8, when the model writes an uncited answer. Not built: accept it if each place's name and address appear in the search results. It would loosen the cited-sources-only rule, so it's your call.
- Backend and Vercel are separate: backend changes reach the live app only after `deploy.ps1`.
- Windows editing trap: never write regexes with `\b` through a Python heredoc (it becomes a backspace character). Use the Edit tool, then scan for `\x08`.

## Remaining order (deadline Wed Nov 4, 6 PM PT; submit by noon)
1. **Phase 5 recovery: done and deployed.** Cost per report: about **$0.01 for 1 photo, about $0.07 for 6** (one Muse Spark vision call about $0.01 + SAM $0.0025 per damage type per photo, at most 3 per photo + report about $0.007). Rate limit 6 reports per IP per hour; at the configurable $3/day hard model-spend cap it returns a friendly 429 "very busy" response.
   - Code map: `recovery.py` (job flow), `recovery_data.py` (fixed lists, 7 languages), `recovery_checklist.py`, `recovery_report.py`, `recovery_guard.py`, `sam.py` + `sam_mask.py` (one_bit decoder ported from meta-sam-parser, `LICENSE-SAM`), `photos.py`, `recovery_store.py`, `handlers/recovery.py`; frontend `RecoveryScreen.jsx`, `RecoveryReport.jsx` (screen + print), `photoPrep.js`, `reveal.js`, `reportDate.js`.
   - Know: SAM masks cover their box, not the photo; use noun concepts, not adjectives. Masks are dropped under 1.5% (debris, furniture), 0.05% (water line, crack, mold, mud) or 0.3% (other labels). Demo flood sample (FEMA 44499) now gives water line x2, crack x3, debris x1 (fixed Oct 28: needs a backend deploy). Print uses a table `<thead>` for the disclaimer (checked in Chrome and on iPhone Safari).
   - Review text for Spanish and Vietnamese: `docs/recovery-text-es-vi.md`. zh/tl/ko/ar recovery screen text shows in English until `translate_ui.py` is rerun.
2. **Phase 6, polish:**
   - **Demo mode: built (Oct 28), needs a backend deploy** (`deploy.ps1`; new routes `GET /demo`, `POST /demo/replay`, and the Ask Lambda now reads the Baseten key and writes `DEMO-*` decisions). Until then the live site shows the demo page, but replay buttons fail and the cost line is hidden. See README "Demo mode". Spanish and Vietnamese demo text (`demo*` keys in `strings.js`) still needs human review.
   - **README: final (Oct 28).** Old detailed README is `docs/TECHNICAL.md`. MIT `LICENSE` added (SAM code keeps `LICENSE-SAM`). Final eval run Oct 28 and its numbers are in the README: alert agent 35/36, Ask 8/8, recovery 6/6, back-translation 54/62. `translate_ui.py` rerun, so zh/tl/ko/ar now cover the recovery and demo text too (no native reviewer). Still open: Spanish reviewer; no `mmdc`, so no SVG/PNG of the diagram.
3. **Final eval ("final polish"):** `run_eval.py --fresh`, the back-translation check, the recovery eval, and the **zh/tl/ko/ar screen text: rerun `translate_ui.py`** (recovery and demo keys show in English until then).
4. **Demo video:**
   - **Open:** the true Stockton story.
   - **Maria:** labeled as an example person, in the real 2022 heat wave and the 2023 Planada flood.
   - **Show:** real Meta model behavior (guardrails, self-correction), the architecture, the cost, and the live URL.
   - **After submitting:** post on X (viral prize deadline Nov 8, 8:59 PM PT).
5. **Video walkthrough, only if usage allows:** Muse Spark 1.3 video (damage by room) plus SAM 3.1 video tracking on a 2 fps clip made with ffmpeg in Lambda. Fall back to key frames. Photos stay the fallback.
6. **Phase 7, Muse Image cards:** first to cut.

## Still to do outside code
- Set the AWS $1 budget alert.
- Find a Spanish speaker to review the Spanish alerts, screen text and the recovery text (`docs/recovery-text-es-vi.md`).
- Check the Vietnamese wording on a phone. (iPhone Safari PDF header confirmed Oct 28: the repeating disclaimer shows on pages 1 to 5; page 6 has the plain "Not an official damage estimate" line.)

## First prompt for the next session
```
Read climateguard-handoff.md and the README in this folder to catch up on the project status, then wait for my next message.
```
