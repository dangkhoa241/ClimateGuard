import { useState } from 'react'
import { LANGS, STRINGS } from './i18n.js'

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
  const [lang, setLang] = useState(() => localStorage.getItem('lang') || 'en')
  const t = STRINGS[lang]

  const choose = (code) => {
    setLang(code)
    localStorage.setItem('lang', code)
    document.documentElement.lang = code
  }

  return (
    <main className="app">
      <LanguagePicker lang={lang} setLang={choose} label={t.language} />
      <h1>ClimateGuard</h1>
      <p className="tagline">{t.tagline}</p>
      {/* Screens arrive in Phases 3–5 */}
      <nav className="actions">
        <button className="big" disabled>{t.alerts}</button>
        <button className="big" disabled>{t.ask}</button>
        <button className="big" disabled>{t.recovery}</button>
      </nav>
    </main>
  )
}
