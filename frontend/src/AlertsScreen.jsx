import { useEffect, useState } from 'react'
import { ALERT_LANGS, getZoneAlerts, subscribe } from './api.js'
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

  useEffect(() => {
    let cancelled = false
    setState({ loading: true, alerts: [], error: false })
    getZoneAlerts(zone)
      .then((alerts) => !cancelled && setState({ loading: false, alerts, error: false }))
      .catch(() => !cancelled && setState({ loading: false, alerts: [], error: true }))
    return () => {
      cancelled = true
    }
  }, [zone])

  if (state.loading) return null
  return (
    <section className="recent" aria-live="polite">
      <h2>{t.recentAlerts}</h2>
      {state.error && <p className="muted">{t.loadError}</p>}
      {!state.error && state.alerts.length === 0 && <p className="muted">{t.noAlerts}</p>}
      {state.alerts.map((a) => (
        <article key={a.sent_at + a.hazard} className={`alert-card sev-${a.severity}`}>
          <div className="alert-meta">
            <strong>{t.severity[a.severity] || a.severity}</strong>
            <time dateTime={a.sent_at}>
              {new Date(a.sent_at).toLocaleString(lang, { weekday: 'short', hour: 'numeric', minute: '2-digit' })}
            </time>
          </div>
          <p>{a.messages[lang] || a.messages.en}</p>
          <ReadAloud text={a.messages[lang] || a.messages.en} lang={a.messages[lang] ? lang : 'en'} t={t} />
          <ShareWhatsApp text={a.messages[lang] || a.messages.en} zone={zone} lang={lang} t={t} />
        </article>
      ))}
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

  async function onSubmit(e) {
    e.preventDefault()
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
              <p className="notice error" role="alert">
                {t.errors[error] || t.errors.default}
              </p>
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
