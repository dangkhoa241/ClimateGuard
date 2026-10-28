// Thin client for the ClimateGuard API. Local dev: `python backend/scripts/local_api.py`.
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8787').replace(/\/$/, '')

// Alert languages (mirrors backend/src/climateguard/languages.py). EN/ES/VI are human-reviewed;
// the others are machine-translated and labeled as such everywhere.
export const ALERT_LANGS = [
  { code: 'en', native: 'English', reviewed: true },
  { code: 'es', native: 'Español', reviewed: true },
  { code: 'vi', native: 'Tiếng Việt', reviewed: true },
  { code: 'zh', native: '中文（简体）', reviewed: false },
  { code: 'tl', native: 'Tagalog', reviewed: false },
  { code: 'ko', native: '한국어', reviewed: false },
  { code: 'ar', native: 'العربية', reviewed: false },
]

export class ApiError extends Error {
  constructor(code, status) {
    super(code)
    this.code = code
    this.status = status
  }
}

async function request(path, options) {
  let res
  try {
    res = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new ApiError('network', 0)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(body.error || 'default', res.status)
  return body
}

export const locateByZip = (zip) => request(`/locate?zip=${encodeURIComponent(zip)}`)

// Coordinates are rounded to ~1 km before they leave the phone; the server only keeps the zone.
export const locateByCoords = (lat, lon) =>
  request(`/locate?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}`)

export const getZoneAlerts = (zone) => request(`/zones/${zone}/alerts`)

export const subscribe = ({ email, lang, location, website }) =>
  request('/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, lang, website, ...location }),
  })

// A spoken question (16 kHz WAV from voice.js) -> {text, audio_ms}. The text goes into the question
// box for the person to check before asking.
export async function transcribeAudio(wav, lang) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 25000)
  try {
    return await request(`/transcribe?lang=${encodeURIComponent(lang)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav' },
      body: wav,
      signal: ctrl.signal,
    })
  } catch (err) {
    throw ctrl.signal.aborted ? new ApiError('timeout', 0) : err
  } finally {
    clearTimeout(timer)
  }
}

// One model call behind it: allow 25 s (API Gateway stops at 30 s), then show a friendly "try again".
export async function askQuestion({ question, lang, zone }) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 25000)
  try {
    return await request('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, lang, zone }),
      signal: ctrl.signal,
    })
  } catch (err) {
    throw ctrl.signal.aborted ? new ApiError('timeout', 0) : err
  } finally {
    clearTimeout(timer)
  }
}

// Public decision history of the live agent (last `days` days), optionally for one zone.
export const getDecisions = ({ zone, days = 7 } = {}) =>
  request(`/decisions?days=${days}&limit=100${zone ? `&zone=${encodeURIComponent(zone)}` : ''}`)

// Supervisor view: today's checklist + an AI pre-shift talk. One model call: same 25 s budget as Ask.
export async function getPreTalk({ zone, lang }) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 25000)
  try {
    return await request('/pretalk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zone, lang }),
      signal: ctrl.signal,
    })
  } catch (err) {
    throw ctrl.signal.aborted ? new ApiError('timeout', 0) : err
  } finally {
    clearTimeout(timer)
  }
}
