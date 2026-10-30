import { Fragment, useEffect, useState } from 'react'
import { getDecisions, getDemo } from './api.js'
import { HOW_LANES, HOW_NODES } from './howItWorksData.js'

function when(ts, lang) {
  return new Date(ts).toLocaleString(lang, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function Arrow() {
  return (
    <span className="how-flow-arrow">
      <svg className="how-arrow-horizontal" viewBox="0 0 32 16" aria-hidden="true" focusable="false">
        <path d="M2 8h25m-6-5 6 5-6 5" />
        <circle cx="4" cy="8" r="2" />
      </svg>
      <svg className="how-arrow-vertical" viewBox="0 0 16 32" aria-hidden="true" focusable="false">
        <path d="M8 2v25m-5-6 5 6 5-6" />
        <circle cx="8" cy="4" r="2" />
      </svg>
    </span>
  )
}

function Flow({ flow, lang, t, activeId, onSelect }) {
  const nodes = flow.nodeIds.map((id) => HOW_NODES.find((node) => node.id === id))
  const columns = nodes.flatMap((_, index) => index < nodes.length - 1 ? ['minmax(0, 1fr)', '32px'] : ['minmax(0, 1fr)'])

  return (
    <div className={`how-flow-wrap how-flow-wrap-${flow.id}`}>
      {flow.titleKey && <h3 className="how-flow-title">{t[flow.titleKey]}</h3>}
      <ol className={`how-flow how-flow-${flow.id}`} style={{ gridTemplateColumns: columns.join(' ') }}>
        {nodes.map((node, index) => (
          <Fragment key={node.id}>
            <li className="how-flow-item">
              <button
                type="button"
                className={`how-node ${node.meta ? 'how-node-meta' : 'how-node-code'}${activeId === node.id ? ' active' : ''}`}
                data-node-id={node.id}
                aria-pressed={activeId === node.id}
                aria-controls="how-node-details"
                aria-label={`${t.howSteps[node.stepIndex]}. ${node.modelLabel}`}
                onFocus={() => onSelect(node.id)}
                onClick={() => onSelect(node.id)}
              >
                <span className={`how-node-badge ${node.meta ? 'meta' : ''}`}>
                  {node.meta ? t.howMetaBadge : t.howNoMetaBadge}
                </span>
                <span className="how-node-title" lang={lang} dir="auto">{t.howSteps[node.stepIndex]}</span>
                <span className="how-model-label" lang="en" dir="ltr">{node.modelLabel}</span>
              </button>
            </li>
            {index < nodes.length - 1 && <li className="how-arrow-item" aria-hidden="true"><Arrow /></li>}
          </Fragment>
        ))}
      </ol>
    </div>
  )
}

function DecisionPanel({ decision, demo, lang, t }) {
  if (!decision) return <p className="muted">{t.howNoAlerts}</p>
  const action = decision.action === 'sent' ? t.decisionSent
    : decision.action === 'error' ? t.decisionError : t.decisionSkipped
  const hazards = (decision.alerts || []).map((alert) => t.hazardNames[alert.hazard] || alert.hazard)

  return (
    <article className={`decision decision-${decision.action || 'skipped'}`}>
      {demo && <p className="muted small">{t.howDemoSample}</p>}
      <div className="alert-meta">
        <strong>{decision.place || decision.event || decision.zone}</strong>
        {decision.ts && <time dateTime={decision.ts}>{when(decision.ts, lang)}</time>}
      </div>
      <dl className="how-decision-fields">
        <div><dt>{t.howDecisionHazard}</dt><dd>{hazards.length ? hazards.join(', ') : t.howNoHazard}</dd></div>
        <div><dt>{t.howDecisionAction}</dt><dd>{action}</dd></div>
        <div><dt>{t.howDecisionCost}</dt><dd>${Number(decision.cost_usd || 0).toFixed(4)}</dd></div>
      </dl>
      <p lang="en" dir="ltr">{decision.reason}</p>
      {decision.alerts?.map((alert) => (
        <p className="small" key={alert.hazard}>{alert.messages?.[lang] || alert.messages?.en}</p>
      ))}
    </article>
  )
}

export default function HowItWorksScreen({ lang, t, demo = false }) {
  const [attempt, setAttempt] = useState(0)
  const [activeId, setActiveId] = useState(HOW_NODES[0].id)
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

  const activeNode = HOW_NODES.find((node) => node.id === activeId) || HOW_NODES[0]
  const decision = demo ? state.data?.sample_decision : state.data?.decisions?.[0]

  return (
    <div className="how-page">
      <p className="how-interaction-hint">{t.howInteractionHint}</p>
      <div className="how-layout">
        <section className="how-diagram" aria-label={t.howDiagramTitle}>
          <div className="how-legend" aria-label={t.howLegend}>
            <span><i className="how-legend-swatch meta" aria-hidden="true" />{t.howMetaBadge}</span>
            <span><i className="how-legend-swatch code" aria-hidden="true" />{t.howNoMetaBadge}</span>
          </div>
          {HOW_LANES.map((lane) => (
            <section className={`how-lane how-lane-${lane.id}`} key={lane.id} aria-labelledby={`how-lane-${lane.id}`}>
              <h2 id={`how-lane-${lane.id}`} className="how-lane-title">{t[lane.titleKey]}</h2>
              {lane.flows.map((flow) => (
                <Flow key={flow.id} flow={flow} lang={lang} t={t} activeId={activeId} onSelect={setActiveId} />
              ))}
            </section>
          ))}
          <section id="how-node-details" className="how-node-details" aria-live="polite" aria-atomic="true">
            <h2>{t.howSelectedStep}: {t.howSteps[activeNode.stepIndex]}</h2>
            <p>{t.howNodeDescriptions[activeNode.infoIndex]}</p>
            <p><strong>{t.howCallCost}:</strong> {t.howNodeCosts[activeNode.infoIndex]}</p>
          </section>
          <section className="sr-only how-fallback" aria-labelledby="how-fallback-title">
            <h2 id="how-fallback-title">{t.howFallbackTitle}</h2>
            <ol>
              {HOW_NODES.map((node) => (
                <li key={node.id}>
                  {t.howSteps[node.stepIndex]}: <span lang="en" dir="ltr">{node.modelLabel}</span>
                </li>
              ))}
            </ol>
          </section>
        </section>
        <section className="how-decisions" aria-labelledby="how-decisions-title">
          <h2 id="how-decisions-title">{demo ? t.howWhyTitle : t.howLatestDecision}</h2>
          {state.loading && <p className="muted" role="status">{t.loading}</p>}
          {state.error && (
            <div className="notice error" role="alert">
              <p>{t.howLoadError}</p>
              <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
            </div>
          )}
          {state.data && <DecisionPanel decision={decision} demo={demo} lang={lang} t={t} />}
        </section>
      </div>
    </div>
  )
}
