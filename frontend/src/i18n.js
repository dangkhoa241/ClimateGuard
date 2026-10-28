// UI strings: EN/ES/VI are human-reviewed (strings.js); zh/tl/ko/ar are translated automatically from
// English by backend/scripts/translate_ui.py into i18n.auto.json and labeled in the app. Any key the
// automatic file lacks falls back to English.
import { REVIEWED_LANGS, REVIEWED_STRINGS } from './strings.js'
import AUTO from './i18n.auto.json'

const AUTO_LANGS = [
  { code: 'zh', label: '中文' },
  { code: 'tl', label: 'Tagalog' },
  { code: 'ko', label: '한국어' },
  { code: 'ar', label: 'العربية', rtl: true },
].filter((l) => AUTO[l.code])

function withFallback(base, extra) {
  const out = { ...base }
  for (const [k, v] of Object.entries(extra || {})) {
    out[k] = v && typeof v === 'object' && !Array.isArray(v) ? withFallback(base[k] || {}, v) : v
  }
  return out
}

export const LANGS = [...REVIEWED_LANGS, ...AUTO_LANGS.map((l) => ({ ...l, auto: true }))]
export const STRINGS = {
  ...REVIEWED_STRINGS,
  ...Object.fromEntries(AUTO_LANGS.map((l) => [l.code, withFallback(REVIEWED_STRINGS.en, AUTO[l.code])])),
}
