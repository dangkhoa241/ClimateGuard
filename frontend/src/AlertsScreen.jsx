import { useEffect, useState } from 'react'
import { ALERT_LANGS, getZoneAlerts, subscribe, translateAlert } from './api.js'
import { HazardIcon, hazardKind } from './icons.jsx'
import LocationPicker from './LocationPicker.jsx'
import ReadAloud from './ReadAloud.jsx'
import ShareWhatsApp from './ShareWhatsApp.jsx'

function NotCoveredNotice({ t }) {
  return (
    <aside className="notice warn" role="note">
      <strong>{t.notCoveredTitle}</strong>
      <p>{t.notCoveredBody}</p>
    </aside>
  )
}

function RecentAlerts({ zone, lang, t }) {
  const [state, setState] = useState({ loading: true, alerts: [], error: false })
  const [attempt, setAttempt] = useState(0)
  const [translations, setTranslations] = useState({})
  const [translating, setTranslating] = useState({})

  useEffect(() => {
    let cancelled = false
    setState({ loading: true, alerts: [], error: false })
    setTranslations({})
    getZoneAlerts(zone)
      .then((alerts) => !cancelled && setState({ loading: false, alerts, error: false }))
      .catch(() => !cancelled && setState({ loading: false, alerts: [], error: true }))
    return () => {
      cancelled = true
    }
  }, [zone, attempt])

  async function retryTranslation(alert) {
    const key = `${alert.sent_at}-${alert.hazard}-${lang}`
    setTranslating((current) => ({ ...current, [key]: true }))
    try {
      const result = await translateAlert({ zone, sentAt: alert.sent_at, hazard: alert.hazard, lang })
      setTranslations((current) => ({ ...current, [key]: result.text }))
    } catch {
      setTranslations((current) => ({ ...current, [key]: null }))
    } finally {
      setTranslating((current) => ({ ...current, [key]: false }))
    }
  }

  useEffect(() => {
    if (lang === 'en') return
    for (const alert of state.alerts) {
      const key = `${alert.sent_at}-${alert.hazard}-${lang}`
      if (!alert.messages[lang] && translations[key] === undefined) retryTranslation(alert)
    }
  }, [lang, state.alerts])

  return (
    <section className="recent" aria-live="polite">
      <h2>{t.recentAlerts}</h2>
      {state.loading && <p className="muted" role="status">{t.loading}</p>}
      {state.error && (
        <div className="notice error" role="alert">
          <p>{t.loadError}</p>
          <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
        </div>
      )}
      {!state.error && state.alerts.length === 0 && <p className="muted">{t.noAlerts}</p>}
      {state.alerts.map((a) => {
        const key = `${a.sent_at}-${a.hazard}-${lang}`
        const translated = a.messages[lang] || translations[key]
        const text = translated || a.messages.en
        const textLang = translated ? lang : 'en'
        return (
        <article key={a.sent_at + a.hazard} className={`alert-card sev-${a.severity} hz-${hazardKind(a.hazard)}`}>
          <div className="alert-meta">
            <span className="alert-kind"><HazardIcon hazard={a.hazard} t={t} /><strong>{t.severity[a.severity] || a.severity}</strong></span>
            <time dateTime={a.sent_at}>
              {new Date(a.sent_at).toLocaleString(lang, { weekday: 'short', hour: 'numeric', minute: '2-digit' })}
            </time>
          </div>
          <p lang={textLang}>{text}</p>
          {!translated && lang !== 'en' && (
            <div className="muted small" role="status">
              <span>{translating[key] ? t.loading : t.translationUnavailable}</span>{' '}
              {!translating[key] && (
                <button type="button" className="text-button" onClick={() => retryTranslation(a)}>{t.retry}</button>
              )}
            </div>
          )}
          <ReadAloud text={text} lang={textLang} t={t} />
          <ShareWhatsApp text={text} zone={zone} lang={lang} t={t} />
        </article>
      )})}
    </section>
  )
}

export default function AlertsScreen({ lang, t, zone, setZone }) {
  // zone.location ({zip} or {lat, lon}) is set when picked here; a zone from an email link has none,
  // so it shows alerts but asks for a location before signing up.
  const location = zone?.location
  const [alertLang, setAlertLang] = useState(lang)
  const [email, setEmail] = useState('')
  const [website, setWebsite] = useState('') // honeypot: hidden from people, bots fill it in
  const [status, setStatus] = useState('idle') // idle | sending | done | error
  const [error, setError] = useState(null)

  useEffect(() => setAlertLang(lang), [lang])

  async function submitSubscription() {
    setStatus('sending')
    setError(null)
    try {
      await subscribe({ email, lang: alertLang, location, website })
      setStatus('done')
    } catch (err) {
      setError(err.code)
      setStatus('error')
    }
  }

  function onSubmit(e) {
    e.preventDefault()
    submitSubscription()
  }

  const canSubmit = email && location && status !== 'sending'

  return (
    <>
      <p>{t.signupIntro}</p>
      <LocationPicker t={t} zone={zone} onLocated={(z, loc) => setZone({ ...z, location: loc })} />

      {status === 'done' ? (
        <div className="notice success" role="status">
          <h2>{t.checkEmailTitle}</h2>
          <p>{t.checkEmailBody}</p>
          <p>{t.monitoringStarts}</p>
          <p className="muted">{t.unsubscribeNote}</p>
        </div>
      ) : (
        location && (
          <form className="signup" onSubmit={onSubmit} noValidate>
            <label htmlFor="alert-lang">{t.alertLanguage}</label>
            <select id="alert-lang" value={alertLang} onChange={(e) => setAlertLang(e.target.value)}>
              {ALERT_LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.native}{l.reviewed ? '' : ` · ${t.autoTranslation}`}
                </option>
              ))}
            </select>
            {!ALERT_LANGS.find((l) => l.code === alertLang)?.reviewed && (
              <p className="muted small">{t.autoTranslationNote}</p>
            )}
            <label htmlFor="email">{t.email}</label>
            <input
              id="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder={t.emailPlaceholder}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <div className="hp" aria-hidden="true">
              <label htmlFor="website">Website</label>
              <input id="website" tabIndex={-1} autoComplete="off" value={website}
                onChange={(e) => setWebsite(e.target.value)} />
            </div>
            {status === 'error' && (
              <div className="notice error" role="alert">
                <p>{t.errors[error] || t.errors.default}</p>
                <button type="button" className="secondary" onClick={submitSubscription}>{t.retry}</button>
              </div>
            )}
            <button className="big" type="submit" disabled={!canSubmit}>
              {status === 'sending' ? t.sending : t.signupButton}
            </button>
            <p className="muted small">{t.privacyNote}</p>
          </form>
        )
      )}
      <NotCoveredNotice t={t} />
      {zone && <RecentAlerts zone={zone.zone} lang={lang} t={t} />}
    </>
  )
}
