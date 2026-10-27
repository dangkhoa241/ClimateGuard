import { useEffect, useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'
import { CITIES } from './api.js'
import AlertsScreen from './AlertsScreen.jsx'

function load(key, fallback, allowed) {
  // URL params win (links in alert emails carry ?city=...&lang=...), then saved choice.
  const fromUrl = new URLSearchParams(window.location.search).get(key)
  let saved = null
  try {
    saved = localStorage.getItem(key)
  } catch {
    // storage blocked (private mode): fall back to defaults
  }
  return [fromUrl, saved].find((v) => v && allowed.includes(v)) || fallback
}

function save(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore: preference just won't persist
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
  const [lang, setLang] = useState(() => load('lang', 'en', LANGS.map((l) => l.code)))
  const [city, setCity] = useState(() => load('city', 'stockton', CITIES.map((c) => c.slug)))
  const [screen, setScreen] = useState(() =>
    new URLSearchParams(window.location.search).has('city') ? 'alerts' : 'home',
  )
  const t = STRINGS[lang]

  useEffect(() => {
    document.documentElement.lang = lang
    save('lang', lang)
  }, [lang])
  useEffect(() => save('city', city), [city])

  return (
    <main className="app">
      <LanguagePicker lang={lang} setLang={setLang} label={t.language} />
      {screen === 'home' ? (
        <>
          <h1>ClimateGuard</h1>
          <p className="tagline">{t.tagline}</p>
          <nav className="actions">
            <button className="big" onClick={() => setScreen('alerts')}>{t.alerts}</button>
            {/* Phases 4–5 */}
            <button className="big" disabled>{t.ask}</button>
            <button className="big" disabled>{t.recovery}</button>
          </nav>
        </>
      ) : (
        <>
          <button className="back" onClick={() => setScreen('home')}>← {t.back}</button>
          <h1>{t.alerts}</h1>
          <AlertsScreen lang={lang} t={t} city={city} setCity={setCity} />
        </>
      )}
    </main>
  )
}
