import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getDecisions } from './api.js'
import { HOW_LANES, HOW_NODES } from './howItWorksData.js'
import DEMO_SAMPLE from './demoSample.json'

function when(ts, lang) {
  return new Date(ts).toLocaleString(lang, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

// The legend already says which steps use no Meta model, so a node shows only the model it runs.
function shownModel(node) {
  if (node.meta) return node.modelLabel
  return node.modelLabel.replace(/\s*·\s*no Meta model$/i, '').replace(/^no Meta model$/i, '')
}

function Arrow() {
  return (
    <span className="how-flow-arrow">
      <svg className="how-arrow-horizontal" viewBox="0 0 40 16" aria-hidden="true" focusable="false">
        <path d="M3 8h31m-7-6 8 6-8 6" />
        <circle cx="5" cy="8" r="2.5" />
      </svg>
      <svg className="how-arrow-vertical" viewBox="0 0 16 40" aria-hidden="true" focusable="false">
        <path d="M8 3v31m-6-7 6 8 6-8" />
        <circle cx="8" cy="5" r="2.5" />
      </svg>
    </span>
  )
}

// How the page is laid out: 'wide' (1100px and up, mouse or pen) shows the step details in a draggable floating card,
// 'row' (900 to 1099px, or touch) shows them under the row of the tapped node, 'column' (phones) directly under the node.
const MODE_QUERIES = [['(min-width: 1100px) and (pointer: fine)', 'wide'], ['(min-width: 900px)', 'row']]
const CARD_WIDTH = 240
const EDGE = 16 // the diagram card's padding: the floating card starts at its right edge
const STEP = 16
const BIG_STEP = 48
const layoutMode = () => {
  if (typeof window === 'undefined' || !window.matchMedia) return 'column'
  return MODE_QUERIES.find(([query]) => window.matchMedia(query).matches)?.[1] || 'column'
}
function useLayoutMode() {
  const [mode, setMode] = useState(layoutMode)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const lists = MODE_QUERIES.map(([query]) => window.matchMedia(query))
    const update = () => setMode(layoutMode())
    lists.forEach((list) => list.addEventListener?.('change', update))
    return () => lists.forEach((list) => list.removeEventListener?.('change', update))
  }, [])
  return mode
}

function Flow({ flow, lang, t, activeId, onSelect, mode, details }) {
  const nodes = flow.nodeIds.map((id) => HOW_NODES.find((node) => node.id === id))
  const rowDetails = mode === 'row' && nodes.some((node) => node.id === activeId) && details

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
                {node.meta && <span className="how-node-badge">{t.howMetaBadge}</span>}
                <span className="how-node-title" lang={lang} dir="auto">{t.howSteps[node.stepIndex]}</span>
                {shownModel(node) && <span className="how-model-label" lang="en" dir="ltr">{shownModel(node)}</span>}
              </button>
            </li>
            {mode === 'column' && activeId === node.id && details && <li className="how-details-item">{details}</li>}
            {index < nodes.length - 1 && <li className="how-arrow-item" aria-hidden="true"><Arrow /></li>}
          </Fragment>
        ))}
      </ol>
      {rowDetails && <div className="how-details-row">{details}</div>}
    </div>
  )
}

function DecisionPanel({ decision, lang, t, demo }) {
  if (!decision) return <p className="muted">{t.howNoAlerts}</p>
  const action = decision.action === 'sent' ? t.decisionSent
    : decision.action === 'error' ? t.decisionError : t.decisionSkipped
  const hazards = (decision.alerts || []).map((alert) => t.hazardNames[alert.hazard] || alert.hazard)

  return (
    <article className={`decision decision-${decision.action || 'skipped'}`}>
      <div className="how-decision-facts">
      <div className="alert-meta">
        {/* the demo sample is an earlier replay of a past event: name the event, never show a date as if it were live */}
        <strong>{demo ? t.demoEvents[decision.event] || decision.place : decision.place || decision.event || decision.zone}</strong>
        {!demo && decision.ts && <time dateTime={decision.ts}>{when(decision.ts, lang)}</time>}
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
      </div>
      <div className="how-decision-text">
        <p lang="en" dir="ltr">{decision.reason}</p>
        {decision.alerts?.map((alert) => (
          <p className="small" key={alert.hazard}>{alert.messages?.[lang] || alert.messages?.en}</p>
        ))}
      </div>
    </article>
  )
}

const LOAD_TIMEOUT_MS = 12000

export default function HowItWorksScreen({ lang, t, demo = false }) {
  const [attempt, setAttempt] = useState(0)
  const [openNodeId, setOpenNodeId] = useState(null)
  const [view, setView] = useState('all')
  const [state, setState] = useState({ loading: true })
  const closeButtonRef = useRef(null)
  const popoverRef = useRef(null)
  const mode = useLayoutMode()
  const restoreFocus = useRef(true)
  const diagramRef = useRef(null)
  const lanesRef = useRef(null)
  const dragRef = useRef(null)
  const [floatPos, setFloatPos] = useState(null) // where the person dragged the card; null = the default spot
  const [defaultPos, setDefaultPos] = useState(null)

  useEffect(() => {
    if (demo) return undefined // demo mode shows the bundled sample: no API call, so nothing to fail
    let cancelled = false
    setState({ loading: true })
    // Never leave "Loading..." forever: a call that takes too long becomes the retryable error.
    const slow = new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), LOAD_TIMEOUT_MS))
    Promise.race([getDecisions({ days: 7 }), slow])
      .then((data) => !cancelled && setState({ loading: false, data }))
      .catch(() => !cancelled && setState({ loading: false, error: true }))
    return () => { cancelled = true }
  }, [attempt, demo])

  useEffect(() => {
    if (!openNodeId) return undefined

    restoreFocus.current = true
    closeButtonRef.current?.focus({ preventScroll: true })
    if (mode !== 'wide') popoverRef.current?.scrollIntoView?.({ block: 'nearest' }) // opened under a node near the bottom: keep it on screen

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpenNodeId(null)
      }
    }
    // A press anywhere outside the popover closes it (a press on a node is handled by the node itself)
    function handlePress(event) {
      if (popoverRef.current?.contains(event.target) || event.target.closest?.('.how-node')) return
      restoreFocus.current = false // the person moved on: don't pull focus back
      setOpenNodeId(null)
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handlePress)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handlePress)
      if (restoreFocus.current) document.querySelector(`[data-node-id="${openNodeId}"]`)?.focus({ preventScroll: true })
    }
  }, [openNodeId, mode])

  const activeNode = HOW_NODES.find((node) => node.id === openNodeId)
  const decision = demo ? DEMO_SAMPLE : state.data?.decisions?.[0]
  const visibleLanes = HOW_LANES.map((lane) => ({
    ...lane,
    flows: lane.flows.filter((flow) => view === 'all' || flow.id === view),
  })).filter((lane) => lane.flows.length > 0)
  const visibleNodeCount = visibleLanes.reduce((count, lane) =>
    count + lane.flows.reduce((flowCount, flow) => flowCount + flow.nodeIds.length, 0), 0)
  const floating = mode === 'wide'
  const pos = floatPos || defaultPos

  // Sizes inside the diagram card, in px. The card is positioned against its padding box (inside the 1px border)
  // and is kept fully inside it. `anchorTop` is where the default spot starts: the top of the Ask lane, or, when a
  // filter hides the Ask lane, just under the last visible lane.
  const measure = () => {
    const diagramEl = diagramRef.current
    const diagram = diagramEl?.getBoundingClientRect()
    const lanes = lanesRef.current?.getBoundingClientRect()
    if (!diagram || !lanes) return null
    const card = popoverRef.current?.getBoundingClientRect()
    const originTop = diagram.top + (diagramEl.clientTop || 0)
    const ask = diagramEl.querySelector('.how-flow-wrap-ask')?.getBoundingClientRect()
    const laneEls = diagramEl.querySelectorAll('.how-lane')
    const lastLane = laneEls[laneEls.length - 1]?.getBoundingClientRect()
    return { width: diagramEl.clientWidth || diagram.width, height: diagramEl.clientHeight || diagram.height,
      cardW: card?.width || CARD_WIDTH, cardH: card?.height || 0, hasAsk: !!ask,
      anchorTop: ask ? ask.top - originTop : (lastLane ? lastLane.bottom - originTop : lanes.top - originTop) }
  }
  const clamp = (p, m) => ({
    x: Math.round(Math.min(Math.max(0, p.x), Math.max(0, m.width - m.cardW))),
    y: Math.round(Math.min(Math.max(0, p.y), Math.max(0, m.height - m.cardH))),
  })
  const same = (a, b) => a && b && a.x === b.x && a.y === b.y

  // Default spot: the right edge of the diagram card, level with the Ask lane (the empty space right of its nodes). Re-fitted when anything resizes
  // (window, language, Large text, another step's text), so the card can't end up outside the diagram card.
  useLayoutEffect(() => {
    if (!floating || !openNodeId) return undefined
    const fit = () => {
      // With the Ask lane hidden the card sits under the last lane: make room for it there first, so it never
      // lands on a node and the clamp below sees the final height of the diagram card.
      const room = lanesRef.current
      if (room) {
        const needsRoom = !diagramRef.current.querySelector('.how-flow-wrap-ask')
        room.style.paddingBottom = needsRoom ? `${(popoverRef.current?.getBoundingClientRect().height || 0) + 16}px` : ''
      }
      const m = measure()
      if (!m) return
      const next = clamp({ x: m.width - m.cardW - EDGE, y: m.anchorTop + 8 }, m)
      setDefaultPos((current) => (same(current, next) ? current : next))
      setFloatPos((current) => {
        if (!current) return current
        const kept = clamp(current, m)
        return same(current, kept) ? current : kept
      })
    }
    fit()
    window.addEventListener('resize', fit)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(fit)
    for (const el of [diagramRef.current, popoverRef.current]) if (el) observer?.observe(el)
    return () => {
      window.removeEventListener('resize', fit)
      observer?.disconnect()
      if (lanesRef.current) lanesRef.current.style.paddingBottom = ''
    }
  }, [floating, openNodeId, lang, view])

  const endDrag = (event) => {
    if (!dragRef.current) return
    dragRef.current = null
    document.documentElement.classList.remove('how-dragging')
    event?.currentTarget?.releasePointerCapture?.(event.pointerId)
  }
  useEffect(() => () => document.documentElement.classList.remove('how-dragging'), [])
  const startDrag = (event) => {
    if (event.pointerType === 'touch' || (event.button != null && event.button > 0)) return // mouse and pen only
    const m = measure()
    if (!m || !pos) return
    dragRef.current = { x: event.clientX, y: event.clientY, from: pos, m }
    event.currentTarget.setPointerCapture?.(event.pointerId)
    document.documentElement.classList.add('how-dragging') // no text selection while dragging
    event.preventDefault()
  }
  const moveDrag = (event) => {
    const drag = dragRef.current
    if (!drag) return
    setFloatPos(clamp({ x: drag.from.x + event.clientX - drag.x, y: drag.from.y + event.clientY - drag.y }, drag.m))
  }
  const handleKey = (event) => {
    const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
    if (event.key === 'Home') {
      event.preventDefault()
      setFloatPos(null)
    } else if (arrows[event.key]) {
      event.preventDefault()
      const m = measure()
      if (!m || !pos) return
      const step = event.shiftKey ? BIG_STEP : STEP
      const [dx, dy] = arrows[event.key]
      setFloatPos(clamp({ x: pos.x + dx * step, y: pos.y + dy * step }, m))
    }
  }

  const details = activeNode && (
    <section id="how-node-details" ref={popoverRef} className={`how-node-dialog${floating ? ' floating' : ''}`} role="dialog" aria-modal="false"
      aria-labelledby="how-node-dialog-title" aria-describedby="how-node-dialog-description"
      style={floating ? (pos ? { left: pos.x, top: pos.y } : { visibility: 'hidden' }) : undefined}>
      <button ref={closeButtonRef} type="button" className="how-dialog-close"
        aria-label={t.howCloseDetails} onClick={() => setOpenNodeId(null)}>
        <span aria-hidden="true">
          <svg viewBox="0 0 14 14" width="14" height="14" focusable="false"><path d="M2 2l10 10M12 2 2 12" /></svg>
        </span>
      </button>
      {floating ? (
        <div className="how-details-handle" role="button" tabIndex={0} aria-label={t.howMoveDetails}
          onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}
          onDoubleClick={() => setFloatPos(null)} onKeyDown={handleKey}>
          <span className="how-card-kicker">{t.howDetails}</span>
        </div>
      ) : (
        <p className="how-card-kicker">{t.howDetails}</p>
      )}
      <h2 id="how-node-dialog-title">{t.howSteps[activeNode.stepIndex]}</h2>
      <p className="how-dialog-model" lang="en" dir="ltr">{activeNode.modelLabel}</p>
      <p id="how-node-dialog-description">{t.howNodeDescriptions[activeNode.infoIndex]}</p>
      <p><strong>{t.howCallCost}:</strong> {t.howNodeCosts[activeNode.infoIndex]}</p>
    </section>
  )
  const chooseView = (nextView) => {
    setView(nextView)
    setOpenNodeId(null)
  }
  const selectNode = (nodeId) => setOpenNodeId((current) => current === nodeId ? null : nodeId)

  return (
    <div className="how-page">
      <p className="how-intro">{t.howIntroBody}</p>
      <div className="how-layout">
        <section className="how-diagram" aria-label={t.howDiagramTitle} ref={diagramRef}>
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
          <div className="how-lanes" ref={lanesRef}>
            {visibleLanes.map((lane) => (
              <section className={`how-lane how-lane-${lane.id}`} key={lane.id} aria-labelledby={`how-lane-${lane.id}`}>
                <h3 id={`how-lane-${lane.id}`} className="how-lane-title">{t[lane.titleKey]}</h3>
                {lane.flows.map((flow) => (
                  <Flow key={flow.id} flow={flow} lang={lang} t={t} activeId={openNodeId} onSelect={selectNode} mode={mode} details={details} />
                ))}
              </section>
            ))}
          </div>
          {floating && details}
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
          {demo && <p className="how-card-kicker">{t.howDemoSample}</p>}
          <h2 id="how-decisions-title">{demo ? t.howWhyTitle : t.howLatestDecision}</h2>
          {!demo && state.loading && <p className="muted" role="status">{t.loading}</p>}
          {!demo && state.error && (
            <div className="notice error" role="alert">
              <p>{t.howLoadError}</p>
              <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
            </div>
          )}
          {(demo || state.data) && <DecisionPanel decision={decision} lang={lang} t={t} demo={demo} />}
        </section>
      </div>
    </div>
  )
}
