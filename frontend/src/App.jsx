import { useEffect, useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'
import AlertsScreen from './AlertsScreen.jsx'
import AskScreen from './AskScreen.jsx'
import DemoScreen from './DemoScreen.jsx'
import { FEATURE_ICONS, Globe, Logo } from './icons.jsx'
import HistoryScreen from './HistoryScreen.jsx'
import RecoveryScreen from './RecoveryScreen.jsx'
import SupervisorScreen from './SupervisorScreen.jsx'

const SCREENS = { alerts: 'alerts', ask: 'ask', recovery: 'recovery', supervisor: 'supervisor', history: 'history', demo: 'demoTitle' } // screen -> title key
// Demo mode's sample area (a demo zone: always monitored). Kept apart from the person's own saved area.
const STOCKTON = { zone: 'CAZ159', name: 'Central San Joaquin County Including Stockton Metro', place: 'Stockton, CA',
  state: 'CA', tz: 'America/Los_Angeles', demo: true, monitored: true, calosha_applies: true }

const ZONE_RE = /^[A-Z]{2}Z\d{3}$/
const WIDE = new Set(['home', 'demo', 'history']) // the rest are forms and reports: reading width
const FEATURES = [ // screen, description key
  ['alerts', 'cardAlerts'], ['ask', 'cardAsk'], ['recovery', 'cardRecovery'], ['supervisor', 'cardSupervisor'],
  ['history', 'cardHistory'],
]

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

// One compact control: a native select, so keyboard, screen readers and phone pickers all work.
function LanguagePicker({ lang, setLang, label }) {
  return (
    <label className="lang-select">
      <Globe />
      <span className="sr-only">{label}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value)}>
        {LANGS.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.label}</option>)}
      </select>
    </label>
  )
}

export default function App() {
  const [lang, setLang] = useState(initialLang)
  const [zone, setZone] = useState(initialZone)
  const [demo, setDemo] = useState(() => new URLSearchParams(window.location.search).get('demo') === '1')
  const [demoZone, setDemoZone] = useState(STOCKTON)
  const [screen, setScreen] = useState(() => {
    const q = new URLSearchParams(window.location.search)
    return q.get('demo') === '1' ? 'demo' : q.has('zone') ? 'alerts' : 'home'
  })
  const area = demo ? demoZone : zone
  const setArea = demo ? setDemoZone : setZone
  const t = STRINGS[lang]
  const meta = LANGS.find((l) => l.code === lang) || {}

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = meta.rtl ? 'rtl' : 'ltr' // Arabic reads right to left
    save('lang', lang)
  }, [lang, meta.rtl])
  useEffect(() => save('zone', zone ? JSON.stringify(zone) : null), [zone])
  useEffect(() => {
    // braces: current Chrome's scrollTo() returns a Promise, and an effect must return a function or nothing
    window.scrollTo(0, 0)
  }, [screen])

  function startDemo() {
    setDemo(true)
    setScreen('demo')
  }

  function leaveDemo() {
    setDemo(false)
    setScreen('home')
    const url = new URL(window.location.href)
    url.searchParams.delete('demo')
    window.history.replaceState(null, '', url)
  }

  return (
    <main className={WIDE.has(screen) ? 'app wide' : 'app'}>
      <header className="topbar">
        {screen !== 'home' && <span className="brand"><Logo size={28} />ClimateGuard</span>}
        <LanguagePicker lang={lang} setLang={setLang} label={t.language} />
      </header>
      {meta.auto && <p className="muted small">{t.autoUiNote}</p>}
      {screen === 'home' ? (
        <>
          <section className="hero">
            <div className="hero-text">
              <h1 className="hero-title"><Logo size={48} />ClimateGuard</h1>
              <p className="tagline">{t.tagline}</p>
              <p>{t.demoAbout1}</p>
              <p>{t.demoAbout2}</p>
              <p>{t.demoAbout3}</p>
            </div>
            <div className="hero-cta">
              <button className="big demo-try" onClick={startDemo}><span aria-hidden="true">▶</span> {t.demoTry}</button>
            </div>
          </section>
          <nav className="feature-grid" aria-label={t.featuresLabel}>
            {FEATURES.map(([key, desc]) => {
              const Icon = FEATURE_ICONS[key]
              return (
                <button key={key} className="feature-card" onClick={() => setScreen(key)}>
                  <span className="feature-icon"><Icon /></span>
                  <span className="feature-title">{t[key]}</span>
                  <span className="feature-desc">{t[desc]}</span>
                </button>
              )
            })}
          </nav>
        </>
      ) : (
        <>
          <button className="back" onClick={() => setScreen(demo && screen !== 'demo' ? 'demo' : 'home')}>
            {meta.rtl ? '→' : '←'} {t.back}
          </button>
          {demo && screen === 'demo' && <button className="back demo-exit" onClick={leaveDemo}>{t.demoExit}</button>}
          <h1>{t[SCREENS[screen]]}</h1>
          {demo && ['ask', 'supervisor'].includes(screen) && <p className="notice demo-note small">{t.demoSampleArea}</p>}
          {screen === 'demo' && <DemoScreen lang={lang} t={t} go={setScreen} />}
          {screen === 'ask' && <AskScreen lang={lang} t={t} zone={area} setZone={setArea} demo={demo} />}
          {screen === 'alerts' && <AlertsScreen lang={lang} t={t} zone={zone} setZone={setZone} />}
          {screen === 'supervisor' && <SupervisorScreen lang={lang} t={t} zone={area} setZone={setArea} />}
          {screen === 'recovery' && <RecoveryScreen lang={lang} t={t} zone={area} demo={demo} />}
          {screen === 'history' && <HistoryScreen lang={lang} t={t} zone={demo ? null : zone} />}
        </>
      )}
    </main>
  )
}
