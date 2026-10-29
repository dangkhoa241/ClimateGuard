import { Component } from 'react'
import { LANGS, STRINGS } from './i18n.js'

// Last line of defence: if anything crashes while rendering, show a friendly message instead of a blank page.
// It runs when the app itself may be broken, so it reads the language straight from the URL or storage.
function pickLang() {
  const allowed = LANGS.map((l) => l.code)
  let saved = null
  try {
    saved = localStorage.getItem('lang')
  } catch {
    // storage blocked: default to English
  }
  const fromUrl = new URLSearchParams(window.location.search).get('lang')
  return [fromUrl, saved].find((v) => v && allowed.includes(v)) || 'en'
}

export default class ErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    console.error('ClimateGuard crashed:', error, info?.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    const lang = pickLang()
    const t = STRINGS[lang]
    const rtl = LANGS.find((l) => l.code === lang)?.rtl
    return (
      <main className="app crash" lang={lang} dir={rtl ? 'rtl' : 'ltr'} role="alert">
        <h1>{t.crashTitle}</h1>
        <p>{t.crashBody}</p>
        <button className="big" onClick={() => window.location.reload()}>{t.crashReload}</button>
        <p><a href="/?demo=1">{t.crashDemo}</a></p>
      </main>
    )
  }
}
