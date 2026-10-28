import { useEffect, useState } from 'react'
import { getDecisions } from './api.js'

// Public decision history: every decision the LIVE agent made, including the many times it chose not
// to alert, plus daily counters from every collector run. Replays and evals are never in this feed.
const STATS = [
  ['zone_checks', 'statChecks'], ['data_changes', 'statChanges'], ['prefilter_skips', 'statPrefilter'],
  ['agent_runs', 'statAgentRuns'], ['alerts_sent', 'statAlerts'],
]

function when(ts, lang) {
  return new Date(ts).toLocaleString(lang, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric',
    minute: '2-digit' })
}

function Decision({ d, lang, t }) {
  const label = d.action === 'sent' ? t.decisionSent : d.action === 'error' ? t.decisionError : t.decisionSkipped
  return (
    <article className={`decision decision-${d.action}`}>
      <div className="alert-meta">
        <strong>{label}</strong>
        <time dateTime={d.ts}>{when(d.ts, lang)}</time>
      </div>
      <p className="muted small">{d.place || d.zone}</p>
      {/* the agent's own words: English, shown as written */}
      <p lang="en" dir="ltr">{d.reason}</p>
      {d.alerts?.map((a) => (
        <p key={a.hazard + a.severity} className="small">
          <strong>{t.severity[a.severity] || a.severity}:</strong> {a.messages?.[lang] || a.messages?.en}
        </p>
      ))}
      {d.tools?.length > 0 && (
        <details className="small">
          <summary>{t.decisionSteps.replace('{n}', d.model_calls).replace('{cost}', d.cost_usd.toFixed(4))}</summary>
          <ol lang="en" dir="ltr">
            {d.tools.map((s, i) => <li key={i}>{s.tool}{s.rejected ? ` (rejected: ${s.rejected})` : ''}</li>)}
          </ol>
        </details>
      )}
    </article>
  )
}

export default function HistoryScreen({ lang, t, zone }) {
  const [onlyMine, setOnlyMine] = useState(Boolean(zone))
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true })
    getDecisions({ zone: onlyMine ? zone?.zone : undefined, days: 7 })
      .then((data) => !cancelled && setState({ loading: false, data }))
      .catch(() => !cancelled && setState({ loading: false, error: true }))
    return () => {
      cancelled = true
    }
  }, [onlyMine, zone])

  const data = state.data
  return (
    <>
      <p>{t.historyIntro}</p>
      {zone && (
        <div className="lang-picker" role="group">
          <button className={onlyMine ? 'active' : ''} aria-pressed={onlyMine} onClick={() => setOnlyMine(true)}>
            {zone.place || zone.name}
          </button>
          <button className={!onlyMine ? 'active' : ''} aria-pressed={!onlyMine} onClick={() => setOnlyMine(false)}>
            {t.allAreas}
          </button>
        </div>
      )}
      {state.loading && <p className="muted">{t.loading}</p>}
      {state.error && <p className="notice error">{t.loadError}</p>}
      {data && (
        <>
          <section className="stats" aria-label={t.historyLast7}>
            <h2>{t.historyLast7}</h2>
            <dl>
              {STATS.map(([key, label]) => (
                <div key={key}>
                  <dt>{t[label]}</dt>
                  <dd>{(data.totals?.[key] ?? 0).toLocaleString(lang)}</dd>
                </div>
              ))}
              <div>
                <dt>{t.statCost}</dt>
                <dd>${(data.totals?.model_cost_usd ?? 0).toFixed(2)}</dd>
              </div>
            </dl>
            <p className="muted small">{t.historyHowItWorks}</p>
          </section>
          <section className="recent">
            <h2>{t.historyDecisions}</h2>
            {data.decisions.length === 0 && <p className="muted">{t.noDecisions}</p>}
            {data.decisions.map((d) => <Decision key={d.ts + d.zone} d={d} lang={lang} t={t} />)}
          </section>
          <p className="muted small">{t.historyNote}</p>
        </>
      )}
    </>
  )
}
