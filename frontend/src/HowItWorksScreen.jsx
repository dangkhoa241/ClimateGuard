import { getDecisions } from './api.js'
import { useEffect, useState } from 'react'

const MODELS = [
  'National Weather Service · no Meta model',
  'Muse Spark Open (meta-models/muse-spark-open-1026), via Baseten',
  'Python safety rules · no Meta model',
  'Muse Spark 1.3 (Meta Model API)',
  'Device speech synthesis · no Meta model',
  'Muse Voice Transcribe 1.0; answer with Muse Spark 1.3',
  'SAM 3.1 outlines + Muse Spark 1.3 image analysis',
  'Muse Spark 1.3',
]

function when(ts, lang) {
  return new Date(ts).toLocaleString(lang, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export default function HowItWorksScreen({ lang, t }) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true })
    getDecisions({ days: 7 })
      .then((data) => !cancelled && setState({ loading: false, data }))
      .catch(() => !cancelled && setState({ loading: false, error: true }))
    return () => { cancelled = true }
  }, [attempt])

  const sent = state.data?.decisions?.filter((decision) => decision.action === 'sent').slice(0, 3) || []

  return (
    <div className="how-page">
      <ol className="how-steps">
        {t.howSteps.map((step, index) => (
          <li key={step}>
            <h2>{step}</h2>
            <p className="muted small">{MODELS[index]}</p>
          </li>
        ))}
      </ol>
      <section className="how-decisions" aria-labelledby="how-decisions-title">
        <h2 id="how-decisions-title">{t.howWhyTitle}</h2>
        {state.loading && <p className="muted" role="status">{t.loading}</p>}
        {state.error && (
          <div className="notice error" role="alert">
            <p>{t.howLoadError}</p>
            <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
          </div>
        )}
        {state.data && sent.length === 0 && <p className="muted">{t.howNoAlerts}</p>}
        {sent.map((decision) => (
          <article className="decision decision-sent" key={`${decision.ts}-${decision.zone}`}>
            <div className="alert-meta">
              <strong>{decision.place || decision.zone}</strong>
              <time dateTime={decision.ts}>{when(decision.ts, lang)}</time>
            </div>
            <p lang="en" dir="ltr">{decision.reason}</p>
            {decision.alerts?.map((alert) => (
              <p className="small" key={alert.hazard}>{alert.messages?.[lang] || alert.messages?.en}</p>
            ))}
          </article>
        ))}
      </section>
    </div>
  )
}
