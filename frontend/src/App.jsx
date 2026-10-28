import { useEffect, useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'
import AlertsScreen from './AlertsScreen.jsx'
import AskScreen from './AskScreen.jsx'

const ZONE_RE = /^[A-Z]{2}Z\d{3}$/

function readStorage(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null // storage blocked (private mode): fall back to defaults
  }
}

function save(key, value) {
  try {
    if (value == null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // ignore: preference just won't persist
  }
}

function initialLang() {
  // URL params win (links in alert emails carry ?zone=...&lang=...), then saved choice.
  const allowed = LANGS.map((l) => l.code)
  const fromUrl = new URLSearchParams(window.location.search).get('lang')
  return [fromUrl, readStorage('lang')].find((v) => v && allowed.includes(v)) || 'en'
}

function initialZone() {
  const fromUrl = (new URLSearchParams(window.location.search).get('zone') || '').toUpperCase()
  if (ZONE_RE.test(fromUrl)) return { zone: fromUrl, name: fromUrl }
  try {
    const saved = JSON.parse(readStorage('zone') || 'null')
    return saved && ZONE_RE.test(saved.zone) ? saved : null
  } catch {
    return null
  }
}

function LanguagePicker({ lang, setLang, label }) {
  return (
    <div className="lang-picker" role="group" aria-label={label}>
      {LANGS.map((l) => (
        <button
          key={l.code}
          className={l.code === lang ? 'active' : ''}
          aria-pressed={l.code === lang}
          onClick={() => setLang(l.code)}
        >
          {l.label}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  const [lang, setLang] = useState(initialLang)
  const [zone, setZone] = useState(initialZone)
  const [screen, setScreen] = useState(() =>
    new URLSearchParams(window.location.search).has('zone') ? 'alerts' : 'home',
  )
  const t = STRINGS[lang]

  useEffect(() => {
    document.documentElement.lang = lang
    save('lang', lang)
  }, [lang])
  useEffect(() => save('zone', zone ? JSON.stringify(zone) : null), [zone])

  return (
    <main className="app">
      <LanguagePicker lang={lang} setLang={setLang} label={t.language} />
      {screen === 'home' ? (
        <>
          <h1>ClimateGuard</h1>
          <p className="tagline">{t.tagline}</p>
          <nav className="actions">
            <button className="big" onClick={() => setScreen('alerts')}>{t.alerts}</button>
            <button className="big" onClick={() => setScreen('ask')}>{t.ask}</button>
            {/* Phase 5 */}
            <button className="big" disabled>{t.recovery}</button>
          </nav>
        </>
      ) : (
        <>
          <button className="back" onClick={() => setScreen('home')}>← {t.back}</button>
          <h1>{screen === 'ask' ? t.ask : t.alerts}</h1>
          {screen === 'ask' ? (
            <AskScreen lang={lang} t={t} zone={zone} setZone={setZone} />
          ) : (
            <AlertsScreen lang={lang} t={t} zone={zone} setZone={setZone} />
          )}
        </>
      )}
    </main>
  )
}
