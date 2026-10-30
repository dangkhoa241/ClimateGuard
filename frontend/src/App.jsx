import { useEffect, useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'
import AlertsScreen from './AlertsScreen.jsx'
import AskScreen from './AskScreen.jsx'
import DemoScreen from './DemoScreen.jsx'
import { FEATURE_ICONS, Globe, Logo } from './icons.jsx'
import HistoryScreen from './HistoryScreen.jsx'
import HowItWorksScreen from './HowItWorksScreen.jsx'
import RecoveryScreen from './RecoveryScreen.jsx'
import SupervisorScreen from './SupervisorScreen.jsx'

const SCREENS = { alerts: 'alerts', ask: 'ask', recovery: 'recovery', supervisor: 'supervisor', history: 'history', demo: 'demoTitle', 'how-it-works': 'howWorksTitle' } // screen -> title key
// Demo mode's sample area (a demo zone: always monitored). Kept apart from the person's own saved area.
const STOCKTON = { zone: 'CAZ159', name: 'Central San Joaquin County Including Stockton Metro', place: 'Stockton, CA',
  state: 'CA', tz: 'America/Los_Angeles', demo: true, monitored: true, calosha_applies: true }

const ZONE_RE = /^[A-Z]{2}Z\d{3}$/
const WIDE = new Set(['home', 'demo', 'history', 'how-it-works']) // the rest are forms and reports: reading width
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

function initialTextSize() {
  return readStorage('textSize') === 'large' ? 'large' : 'normal'
}

// The current screen lives in the URL hash (#/ask, #/demo...) so refresh and the browser's Back and Forward
// buttons work. Only the screen name and the demo flag go in the URL, never a ZIP code, question or photo.
function screenFromUrl() {
  const { hash, search } = window.location
  if (hash && hash !== '#') {
    const name = hash.startsWith('#/') ? hash.slice(2) : ''
    return Object.hasOwn(SCREENS, name) ? name : 'home' // unknown hash (or none): home
  }
  const q = new URLSearchParams(search) // links without a hash: ?demo=1, and alert emails with ?zone=
  return q.get('demo') === '1' ? 'demo' : q.has('zone') ? 'alerts' : 'home'
}

const demoInUrl = () => new URLSearchParams(window.location.search).get('demo') === '1'

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
  const [textSize, setTextSize] = useState(initialTextSize)
  const [zone, setZone] = useState(initialZone)
  const [demo, setDemo] = useState(demoInUrl)
  const [demoZone, setDemoZone] = useState(STOCKTON)
  const [screen, setScreen] = useState(screenFromUrl)
  const area = demo ? demoZone : zone
  const setArea = demo ? setDemoZone : setZone
  const t = STRINGS[lang]
  const meta = LANGS.find((l) => l.code === lang) || {}

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = meta.rtl ? 'rtl' : 'ltr' // Arabic reads right to left
    save('lang', lang)
  }, [lang, meta.rtl])
  useEffect(() => {
    document.documentElement.classList.toggle('large-text', textSize === 'large')
    save('textSize', textSize)
  }, [textSize])
  useEffect(() => save('zone', zone ? JSON.stringify(zone) : null), [zone])
  useEffect(() => {
    // braces: current Chrome's scrollTo() returns a Promise, and an effect must return a function or nothing
    window.scrollTo(0, 0)
  }, [screen])

  // Browser Back/Forward (and a hand-edited hash): follow the URL.
  useEffect(() => {
    const sync = () => {
      setScreen(screenFromUrl())
      setDemo(demoInUrl())
    }
    window.addEventListener('popstate', sync)
    window.addEventListener('hashchange', sync)
    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener('hashchange', sync)
    }
  }, [])

  // Every in-app move adds a history entry; demo mode is kept in the URL (?demo=1) so a refresh stays in it.
  function go(next, demoOn = demo) {
    const url = new URL(window.location.href)
    if (demoOn) url.searchParams.set('demo', '1')
    else url.searchParams.delete('demo')
    url.hash = next === 'home' ? '/' : `/${next}`
    if (url.href !== window.location.href) window.history.pushState({ cg: true }, '', url) // cg: we pushed it
    setDemo(demoOn)
    setScreen(next)
  }

  const startDemo = () => go('demo', true)
  const leaveDemo = () => go('home', false)

  // The in-app Back button: one step back in the browser's history when this page pushed the entry; if the
  // page was opened straight on a screen (refresh, shared link), go to its parent instead.
  function goBack() {
    if (window.history.state?.cg) window.history.back()
    else if (demo && screen !== 'demo') go('demo')
    else go('home', false)
  }

  return (
    <main className={WIDE.has(screen) ? `app wide${screen === 'how-it-works' ? ' how-app' : ''}` : 'app'}>
      <header className="topbar">
        {screen !== 'home' && <button className="brand" type="button" onClick={() => go('home')}><Logo size={28} />ClimateGuard</button>}
        <div className="header-actions">
          <button type="button" className="text-size-toggle secondary" aria-label={t.textSizeToggle}
            aria-pressed={textSize === 'large'} onClick={() => setTextSize((size) => size === 'large' ? 'normal' : 'large')}>
            {textSize === 'large' ? t.normalText : t.largeText}
          </button>
          <LanguagePicker lang={lang} setLang={setLang} label={t.language} />
        </div>
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
                <button key={key} className="feature-card" onClick={() => go(key)}>
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
          <button className="back" onClick={goBack}>
            {meta.rtl ? '→' : '←'} {t.back}
          </button>
          {demo && screen === 'demo' && <button className="back demo-exit" onClick={leaveDemo}>{t.demoExit}</button>}
          <h1>{t[SCREENS[screen]]}</h1>
          {demo && screen === 'demo' && (
            <aside className="notice demo-note small">
              <p>{t.demoSampleArea}</p>
              <a href="#/how-it-works">{t.howWorksTitle}</a>
            </aside>
          )}
          {screen === 'demo' && <DemoScreen lang={lang} t={t} go={(next) => go(next)} />}
          {screen === 'how-it-works' && <HowItWorksScreen lang={lang} t={t} demo={demo} />}
          {screen === 'ask' && <AskScreen lang={lang} t={t} zone={area} setZone={setArea} demo={demo} />}
          {screen === 'alerts' && <AlertsScreen lang={lang} t={t} zone={zone} setZone={setZone} />}
          {screen === 'supervisor' && <SupervisorScreen lang={lang} t={t} zone={area} setZone={setArea} />}
          {screen === 'recovery' && <RecoveryScreen lang={lang} t={t} zone={area} demo={demo} />}
          {screen === 'history' && <HistoryScreen lang={lang} t={t} zone={demo ? null : zone} />}
        </>
      )}
      <footer className="app-footer">
        {screen !== 'how-it-works' && <a href="#/how-it-works">{t.howWorksTitle}</a>}
      </footer>
    </main>
  )
}
