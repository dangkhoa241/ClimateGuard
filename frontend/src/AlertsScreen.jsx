import { useEffect, useState } from 'react'
import { CITIES, getCityAlerts, subscribe } from './api.js'

function RecentAlerts({ city, lang, t }) {
  const [state, setState] = useState({ loading: true, alerts: [], error: false })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true, alerts: [], error: false })
    getCityAlerts(city)
      .then((alerts) => !cancelled && setState({ loading: false, alerts, error: false }))
      .catch(() => !cancelled && setState({ loading: false, alerts: [], error: true }))
    return () => {
      cancelled = true
    }
  }, [city])

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
        </article>
      ))}
    </section>
  )
}

export default function AlertsScreen({ lang, t, city, setCity }) {
  const [email, setEmail] = useState('')
  const [website, setWebsite] = useState('') // honeypot: hidden from people, bots fill it in
  const [status, setStatus] = useState('idle') // idle | sending | done | error
  const [error, setError] = useState(null)

  async function onSubmit(e) {
    e.preventDefault()
    setStatus('sending')
    setError(null)
    try {
      await subscribe({ email, city, lang, website })
      setStatus('done')
    } catch (err) {
      setError(err.code)
      setStatus('error')
    }
  }

  return (
    <>
      {status === 'done' ? (
        <div className="notice success" role="status">
          <h2>{t.checkEmailTitle}</h2>
          <p>{t.checkEmailBody}</p>
          <p className="muted">{t.unsubscribeNote}</p>
        </div>
      ) : (
        <form className="signup" onSubmit={onSubmit} noValidate>
          <p>{t.signupIntro}</p>
          <label htmlFor="city">{t.city}</label>
          <select id="city" value={city} onChange={(e) => setCity(e.target.value)}>
            {CITIES.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
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
          <button className="big" type="submit" disabled={status === 'sending' || !email}>
            {status === 'sending' ? t.sending : t.signupButton}
          </button>
          <p className="muted small">{t.privacyNote}</p>
        </form>
      )}
      <RecentAlerts city={city} lang={lang} t={t} />
    </>
  )
}
