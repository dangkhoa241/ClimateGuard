import { Fragment, useEffect, useRef, useState } from 'react'
import { getDecisions } from './api.js'
import { HOW_LANES, HOW_NODES } from './howItWorksData.js'
import DEMO_SAMPLE from './demoSample.json'

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

  return (
    <div className={`how-flow-wrap how-flow-wrap-${flow.id}`}>
      {flow.titleKey && <h4 className="how-flow-title">{t[flow.titleKey]}</h4>}
      <ol className={`how-flow how-flow-${flow.id}`}>
        {nodes.map((node, index) => (
          <Fragment key={node.id}>
            <li className="how-flow-item">
              <button
                type="button"
                className={`how-node ${node.meta ? 'how-node-meta' : 'how-node-code'}${activeId === node.id ? ' active' : ''}`}
                data-node-id={node.id}
                aria-expanded={activeId === node.id}
                aria-controls={activeId === node.id ? 'how-node-details' : undefined}
                aria-label={`${t.howSteps[node.stepIndex]}. ${node.modelLabel}`}
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

function DecisionPanel({ decision, lang, t }) {
  if (!decision) return <p className="muted">{t.howNoAlerts}</p>
  const action = decision.action === 'sent' ? t.decisionSent
    : decision.action === 'error' ? t.decisionError : t.decisionSkipped
  const hazards = (decision.alerts || []).map((alert) => t.hazardNames[alert.hazard] || alert.hazard)

  return (
    <article className={`decision decision-${decision.action || 'skipped'}`}>
      <div className="alert-meta">
        <strong>{decision.place || decision.event || decision.zone}</strong>
        {decision.ts && <time dateTime={decision.ts}>{when(decision.ts, lang)}</time>}
      </div>
      <dl className="how-decision-fields">
        <div><dt>{t.howDecisionHazard}</dt><dd>{hazards.length ? hazards.join(', ') : t.howNoHazard}</dd></div>
        <div><dt>{t.howDecisionAction}</dt><dd>{action}</dd></div>
        {decision.safety_checks_passed != null && (
          <div><dt>{t.howDecisionSafety}</dt><dd>{decision.safety_checks_passed ? t.howSafetyPassed : t.howSafetyNotPassed}</dd></div>
        )}
        {decision.model_calls != null && <div><dt>{t.howDecisionCalls}</dt><dd>{decision.model_calls}</dd></div>}
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
  const [openNodeId, setOpenNodeId] = useState(null)
  const [view, setView] = useState('all')
  const [state, setState] = useState({ loading: true })
  const closeButtonRef = useRef(null)

  useEffect(() => {
    if (demo) return undefined // demo mode shows the bundled sample: no API call, so nothing to fail
    let cancelled = false
    setState({ loading: true })
    getDecisions({ days: 7 })
      .then((data) => !cancelled && setState({ loading: false, data }))
      .catch(() => !cancelled && setState({ loading: false, error: true }))
    return () => { cancelled = true }
  }, [attempt, demo])

  useEffect(() => {
    if (!openNodeId) return undefined

    closeButtonRef.current?.focus()

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpenNodeId(null)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.querySelector(`[data-node-id="${openNodeId}"]`)?.focus()
    }
  }, [openNodeId])

  const activeNode = HOW_NODES.find((node) => node.id === openNodeId)
  const decision = demo ? DEMO_SAMPLE : state.data?.decisions?.[0]
  const visibleLanes = HOW_LANES.map((lane) => ({
    ...lane,
    flows: lane.flows.filter((flow) => view === 'all' || flow.id === view),
  })).filter((lane) => lane.flows.length > 0)
  const visibleNodeCount = visibleLanes.reduce((count, lane) =>
    count + lane.flows.reduce((flowCount, flow) => flowCount + flow.nodeIds.length, 0), 0)
  const chooseView = (nextView) => {
    setView(nextView)
    setOpenNodeId(null)
  }
  const selectNode = (nodeId) => setOpenNodeId((current) => current === nodeId ? null : nodeId)

  return (
    <div className="how-page">
      <section className="how-intro" aria-labelledby="how-intro-title">
        <p className="how-intro-kicker">{t.howWorksTitle}</p>
        <h2 id="how-intro-title">{t.howIntroTitle}</h2>
        <p>{t.howIntroBody}</p>
      </section>
      <div className="how-layout">
        <section className="how-diagram" aria-label={t.howDiagramTitle}>
          <div className="how-diagram-header">
            <div>
              <h2>{t.howDiagramTitle}</h2>
              <p>{t.howInteractionHint}</p>
            </div>
            <div className="how-view-switch" role="group" aria-label={t.howViewLabel}>
              {[
                ['all', t.howViewAll],
                ['alerts', t.howLaneAlerts],
                ['ask', t.howAskLabel],
                ['recovery', t.howLaneRecovery],
              ].map(([id, label]) => (
                <button key={id} type="button" aria-pressed={view === id}
                  onClick={() => chooseView(id)}>{label}</button>
              ))}
            </div>
          </div>
          <div className="how-diagram-meta">
            <div className="how-legend" aria-label={t.howLegend}>
              <span><i className="how-legend-swatch meta" aria-hidden="true" />{t.howMetaBadge}</span>
              <span><i className="how-legend-swatch code" aria-hidden="true" />{t.howNoMetaBadge}</span>
            </div>
            <span className="how-node-count">{visibleNodeCount} {t.howStepsLabel}</span>
          </div>
          <div className="how-lanes">
            {visibleLanes.map((lane) => (
              <section className={`how-lane how-lane-${lane.id}`} key={lane.id} aria-labelledby={`how-lane-${lane.id}`}>
                <h3 id={`how-lane-${lane.id}`} className="how-lane-title">{t[lane.titleKey]}</h3>
                {lane.flows.map((flow) => (
                  <Flow key={flow.id} flow={flow} lang={lang} t={t} activeId={openNodeId} onSelect={selectNode} />
                ))}
              </section>
            ))}
          </div>
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
        <div className="how-support-grid">
          {activeNode && (
            <section id="how-node-details" className="how-node-dialog" role="dialog" aria-modal="false"
              aria-labelledby="how-node-dialog-title" aria-describedby="how-node-dialog-description">
              <button ref={closeButtonRef} type="button" className="how-dialog-close"
                aria-label={t.howCloseDetails} onClick={() => setOpenNodeId(null)}>×</button>
              <p className="how-card-kicker">{t.howSelectedStep}</p>
              <h2 id="how-node-dialog-title">{t.howSteps[activeNode.stepIndex]}</h2>
              <p className="how-dialog-model" lang="en" dir="ltr">{activeNode.modelLabel}</p>
              <p id="how-node-dialog-description">{t.howNodeDescriptions[activeNode.infoIndex]}</p>
              <p><strong>{t.howCallCost}:</strong> {t.howNodeCosts[activeNode.infoIndex]}</p>
            </section>
          )}
          <section className="how-decisions" aria-labelledby="how-decisions-title">
            <p className="how-card-kicker">{demo ? t.howDemoSample : t.howLatestDecision}</p>
            <h2 id="how-decisions-title">{demo ? t.howWhyTitle : t.howLatestDecision}</h2>
            {!demo && state.loading && <p className="muted" role="status">{t.loading}</p>}
            {!demo && state.error && (
              <div className="notice error" role="alert">
                <p>{t.howLoadError}</p>
                <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
              </div>
            )}
            {(demo || state.data) && <DecisionPanel decision={decision} lang={lang} t={t} />}
          </section>
        </div>
      </div>
    </div>
  )
}
