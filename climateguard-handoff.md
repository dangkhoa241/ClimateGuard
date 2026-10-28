# ClimateGuard handoff (Wed Oct 28, 2026)

## Status
- Phases 0–4 are done and deployed. Latest commit: **ed237f7** (the cooling-center fix: 211 links as fallback, retry, wider trigger). About 2 days ahead of schedule.
- Offline tests: 408 passing. Ask eval: 7/7 on Oct 28 (the cooling-center cases were rechecked live after ed237f7: 7 of 8 cited a source). Agent eval: 35/36, back-translation meaning match 92% (Oct 27).
- Spend: Meta about $1.42 of $150, Baseten $1.90 of $100, AWS $0.
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
- **Routes:**
  - `GET /locate`, `/zones/{zone}`, `/zones/{zone}/alerts`, `/languages`, `/decisions`
  - `POST /subscribe`, `/ask`, `/transcribe?lang=` (WAV body), **`/pretalk`** (new)
  - The history page reads `/decisions`; its daily counters now work (the collector permission bug is fixed).

## Deploy and test
- Backend deploy: `.\deploy.ps1 -Contact dangkhoa2401bg@gmail.com`
  - The Vercel URL is saved in `deploy.local.json` (untracked), so no `-FrontendUrl` is needed.
  - A deploy that would reset it to localhost shows a red warning and waits for you to type `reset`.
- Frontend: push to `main`. For local work, use `frontend\.env.local` (it points at the AWS API) and run `cd frontend`, then `npm run dev -- --port 5173 --strictPort` (or 5174). CORS allows both.
- Tests: `cd backend; .venv\Scripts\python -m pytest -q tests`. Frontend build check: `cd frontend; npx vite build`.
- Evals (spend credits): `python scripts/run_ask_eval.py` (about $0.04; `--effort minimal low` compares reasoning), `python scripts/run_eval.py --fresh` (about $0.25). Run from `backend` with the venv.
- Spend: `python scripts/spend.py` for the local log; `$env:STORAGE="dynamodb"` first for the deployed log.
- Screen translations: `python scripts/translate_ui.py` (about $0.08). Rerun after changing English strings in `frontend/src/strings.js`.

## Know before continuing
- Cooling-center search still returns the 211 links in about 1 run in 8, when the model writes an uncited answer. Not built: accept it if each place's name and address appear in the search results. It would loosen the cited-sources-only rule, so it's your call.
- Backend and Vercel are separate: backend changes reach the live app only after `deploy.ps1`.
- Windows editing trap: never write regexes with `\b` through a Python heredoc (it becomes a backspace character). Use the Edit tool, then scan for `\x08`.

## Remaining order (deadline Wed Nov 4, 6 PM PT; submit by noon)
1. **Phase 5, recovery agent:** steps 1-6 and 8-9 done (Oct 28), **NOT deployed yet** (run `deploy.ps1`, then `git push`). Left: **step 7, PDF** (approach not chosen), README section.
   - Code: `recovery.py` (job flow), `recovery_data.py` (fixed lists, 7 languages), `recovery_checklist.py` (EN/ES/VI), `recovery_report.py`, `recovery_guard.py`, `sam.py` + `sam_mask.py` (one_bit decoder ported from meta-sam-parser, LICENSE-SAM), `photos.py`, `recovery_store.py` (S3 `climateguard-recovery-<account>`), `handlers/recovery.py` (own Lambda `climateguard-recovery`, invokes itself async). Frontend `RecoveryScreen.jsx`, `photoPrep.js`.
   - Routes: `POST /recovery`, `POST /recovery/{job}/photos?i=`, `POST /recovery/{job}/analyze`, `POST /recovery/{job}/answers`, `GET /recovery/{job}`, `DELETE /recovery/{job}`.
   - SAM masks cover their box, not the frame (measured). Adjective concepts ("damaged drywall") find nothing; use nouns.
   - Live: analysis of 2 photos 7.4 s, $0.017; report ~5 s, ~$0.007. `scripts/run_recovery_eval.py` 6/6 (Oct 28, $0.04). `scripts/smoke_sam.py` for one photo.
   - Screen text for the new keys is EN/ES/VI only: rerun `translate_ui.py` for zh/tl/ko/ar (final polish).
2. **Video walkthrough:** Muse Spark 1.3 video (damage by room) plus SAM 3.1 video tracking on a 2 fps clip made with ffmpeg in Lambda. Fall back to key frames. Photos stay the fallback.
3. **Phase 6, polish:** demo mode with replay banners (the replays exist in the backend), a final agent eval, README, and the "Recovery" button on the home screen (still disabled).
4. **Demo video:**
   - **Open:** the true Stockton story.
   - **Maria:** labeled as an example person, in the real 2022 heat wave and the 2023 Planada flood.
   - **Show:** real Meta model behavior (guardrails, self-correction), the architecture, the cost, and the live URL.
   - **After submitting:** post on X (viral prize deadline Nov 8, 8:59 PM PT).
5. **Phase 7, Muse Image cards:** first to cut.

## Still to do outside code
- Set the AWS $1 budget alert.
- Find a Spanish speaker to review the Spanish alerts, screen text and the new checklist items.
- Check the new Vietnamese badge and checklist wording on a phone.

## First prompt for the next session
```
Read climateguard-handoff.md and the README in this folder to catch up on the project status, then wait for my next message.
```
