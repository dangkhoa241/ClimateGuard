import { getDecisions, getDemo } from './api.js'
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

export default function HowItWorksScreen({ lang, t, demo = false }) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true })
    const request = demo ? getDemo() : getDecisions({ days: 7 })
    request
      .then((data) => {
        if (demo && !data.sample_decision) throw new Error('demo_sample_missing')
        if (!cancelled) setState({ loading: false, data })
      })
      .catch(() => !cancelled && setState({ loading: false, error: true }))
    return () => { cancelled = true }
  }, [attempt, demo])

  const sent = !demo ? state.data?.decisions?.filter((decision) => decision.action === 'sent').slice(0, 3) || [] : []
  const sample = demo ? state.data?.sample_decision : null

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
        {demo && sample && (
          <article className="decision decision-sent">
            <p className="muted small">{t.howDemoSample}</p>
            <div className="alert-meta">
              <strong>{sample.place || sample.event}</strong>
              <time dateTime={sample.ts}>{when(sample.ts, lang)}</time>
            </div>
            <p><strong>{sample.action === 'sent' ? t.decisionSent : t.decisionSkipped}</strong>
              {' · '}{sample.alerts?.map((alert) => t.hazardNames[alert.hazard] || alert.hazard).join(', ')}</p>
            <p lang="en" dir="ltr">{sample.reason}</p>
            {sample.alerts?.map((alert) => (
              <p className="small" key={alert.hazard}>{alert.messages?.[lang] || alert.messages?.en}</p>
            ))}
            <p className="muted small">{t.decisionSteps.replace('{n}', sample.model_calls)
              .replace('{cost}', Number(sample.cost_usd).toFixed(4))}</p>
          </article>
        )}
        {!demo && state.data && sent.length === 0 && <p className="muted">{t.howNoAlerts}</p>}
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
