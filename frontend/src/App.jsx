import { useEffect, useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'
import AlertsScreen from './AlertsScreen.jsx'
import AskScreen from './AskScreen.jsx'
import HistoryScreen from './HistoryScreen.jsx'
import RecoveryScreen from './RecoveryScreen.jsx'
import SupervisorScreen from './SupervisorScreen.jsx'

const SCREENS = { alerts: 'alerts', ask: 'ask', recovery: 'recovery', supervisor: 'supervisor', history: 'history' } // screen -> title key

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
  const meta = LANGS.find((l) => l.code === lang) || {}

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = meta.rtl ? 'rtl' : 'ltr' // Arabic reads right to left
    save('lang', lang)
  }, [lang, meta.rtl])
  useEffect(() => save('zone', zone ? JSON.stringify(zone) : null), [zone])

  return (
    <main className="app">
      <LanguagePicker lang={lang} setLang={setLang} label={t.language} />
      {meta.auto && <p className="muted small">{t.autoUiNote}</p>}
      {screen === 'home' ? (
        <>
          <h1>ClimateGuard</h1>
          <p className="tagline">{t.tagline}</p>
          <nav className="actions">
            <button className="big" onClick={() => setScreen('alerts')}>{t.alerts}</button>
            <button className="big" onClick={() => setScreen('ask')}>{t.ask}</button>
            <button className="big" onClick={() => setScreen('recovery')}>{t.recovery}</button>
            <button className="secondary" onClick={() => setScreen('supervisor')}>{t.supervisor}</button>
            <button className="secondary" onClick={() => setScreen('history')}>{t.history}</button>
          </nav>
        </>
      ) : (
        <>
          <button className="back" onClick={() => setScreen('home')}>{meta.rtl ? '→' : '←'} {t.back}</button>
          <h1>{t[SCREENS[screen]]}</h1>
          {screen === 'ask' && <AskScreen lang={lang} t={t} zone={zone} setZone={setZone} />}
          {screen === 'alerts' && <AlertsScreen lang={lang} t={t} zone={zone} setZone={setZone} />}
          {screen === 'supervisor' && <SupervisorScreen lang={lang} t={t} zone={zone} setZone={setZone} />}
          {screen === 'recovery' && <RecoveryScreen lang={lang} t={t} zone={zone} />}
          {screen === 'history' && <HistoryScreen lang={lang} t={t} zone={zone} />}
        </>
      )}
    </main>
  )
}
