import { useEffect, useRef, useState } from 'react'
import { getDemo, runDemoReplay } from './api.js'
import { HazardIcon, hazardKind } from './icons.jsx'
import ReadAloud from './ReadAloud.jsx'
import { fill } from './RecoveryReport.jsx'
import { reveal } from './reveal.js'

// Demo mode: everything a judge needs in about a minute, with no sign-up, no email and no photos of their own.
// Replays run the real alert agent on real past events (labeled REPLAY); when that isn't possible the server
// answers with an earlier saved run and says why.
const EVENTS = ['heat_2022', 'flood_2023', 'smoke_2020'] // the server's catalog may arrive later (or not at all)
const money = (n) => (n < 0.01 && n > 0 ? n.toFixed(4) : n.toFixed(2))

function day(iso, lang) {
  return new Date(iso).toLocaleDateString(lang, { month: 'long', day: 'numeric', year: 'numeric' })
}

function ReplayResult({ r, lang, t, headingRef }) {
  const d = r.decision
  return (
    <article className="answer demo-result" aria-live="polite">
      <p className="replay-banner">{t.demoReplayLabel}</p>
      <h3 ref={headingRef} tabIndex={-1}>{t.demoEvents[r.event]}</h3>
      <p className="muted small">{t.demoMoments[r.event]}</p>
      {r.source === 'saved' && (
        <p className="notice warn small">{fill(t.demoSaved[r.why] || t.demoSaved.error, { date: day(r.ran_at, lang) })}</p>
      )}
      <div className="alert-meta">
        <strong>{t.demoDecision}: {d.action === 'sent' ? t.decisionSent : t.decisionSkipped}</strong>
      </div>
      <p className="muted small">
        {d.cached
          ? fill(t.demoCached, { cost: money(r.typical_cost_usd) })
          : fill(t.demoCost, { calls: d.model_calls, cost: money(d.cost_usd) })}
      </p>
      {r.alerts.map((a) => (
        <div key={a.hazard} className={`alert-card sev-${a.severity} hz-${hazardKind(a.hazard)}`}>
          <div className="alert-meta">
            <span className="alert-kind"><HazardIcon hazard={a.hazard} t={t} /><strong>{t.severity[a.severity] || a.severity}</strong></span>
          </div>
          {(() => {
            const text = a.translations?.[lang] || a.text
            const shownLang = a.translations?.[lang] ? lang : a.lang
            return (
              <>
                <p lang={shownLang} dir={shownLang === 'en' ? 'ltr' : undefined}>{text}</p>
                {shownLang !== 'en' && !['es', 'vi'].includes(shownLang) && <p className="muted small">{t.demoAutoAlert}</p>}
                {shownLang !== lang && <p className="muted small">{t.demoEnglishShown}</p>}
                <ReadAloud text={text} lang={shownLang} t={t} />
              </>
            )
          })()}
        </div>
      ))}
      <details className="sources">
        <summary>{t.demoReason}</summary>
        <p lang="en" dir="ltr" className="small">{d.reason}</p>
      </details>
      <p className="muted small">{t.demoNoEmail} {t.demoExamplePerson}</p>
    </article>
  )
}

function HowItWorks({ t, lang, cost, onHistory }) {
  return (
    <section className="stats demo-how">
      <h2>{t.demoHowTitle}</h2>
      <ul>
        <li>{t.demoHowMonitor}</li>
        <li>{t.demoHowAsk}</li>
        <li>{t.demoHowRecovery}</li>
      </ul>
      {cost && (
        <p className="small"><strong>{fill(t.demoCostSoFar, { date: day(`${cost.since}T12:00:00Z`, lang), total: cost.total_usd.toFixed(2) })}</strong></p>
      )}
      <button className="secondary" onClick={onHistory}>{t.demoHowHistory}</button>
    </section>
  )
}

export default function DemoScreen({ lang, t, go }) {
  const [info, setInfo] = useState(null) // GET /demo: {events, cost, over_budget}
  const [infoStatus, setInfoStatus] = useState('loading')
  const [infoAttempt, setInfoAttempt] = useState(0)
  const [running, setRunning] = useState(null) // event id
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [failedEvent, setFailedEvent] = useState(null)
  const resultRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setInfoStatus('loading')
    getDemo()
      .then((data) => {
        if (!cancelled) {
          setInfo(data)
          setInfoStatus('done')
        }
      })
      .catch(() => !cancelled && setInfoStatus('error'))
    return () => { cancelled = true }
  }, [infoAttempt])
  useEffect(() => {
    if (result) reveal(resultRef.current, { focus: true })
  }, [result])

  async function replay(event) {
    setRunning(event)
    setError(null)
    setFailedEvent(null)
    setResult(null)
    try {
      setResult(await runDemoReplay({ event, lang }))
    } catch (err) {
      setError(err.code || 'default')
      setFailedEvent(event)
    }
    setRunning(null)
  }

  return (
    <>
      <p>{t.demoIntro}</p>
      {infoStatus === 'loading' && <p className="muted" role="status">{t.loading}</p>}
      {infoStatus === 'error' && (
        <div className="notice error" role="alert">
          <p>{t.errors.default}</p>
          <button type="button" className="secondary" onClick={() => setInfoAttempt((n) => n + 1)}>{t.retry}</button>
        </div>
      )}
      {info?.over_budget && <p className="notice warn">{t.demoBudgetNote}</p>}

      <section className="demo-section">
        <h2>{t.demoReplayTitle}</h2>
        <p className="small">{t.demoReplayIntro}</p>
        <div className="demo-replays">
          {(info?.events?.map((e) => e.event) || EVENTS).map((e) => (
            <button key={e} className="mid demo-replay" onClick={() => replay(e)} disabled={!!running}>
              {t.demoEvents[e]}
            </button>
          ))}
        </div>
        {running && <p className="muted" role="status">{t.demoRunning}</p>}
        {error && (
          <div className="notice error" role="alert">
            <p>{t.errors[error] || t.errors.default}</p>
            <button type="button" className="secondary" onClick={() => replay(failedEvent)} disabled={!failedEvent}>
              {t.retry}
            </button>
          </div>
        )}
        {result && <ReplayResult r={result} lang={lang} t={t} headingRef={resultRef} />}
      </section>

      <div className="demo-pair">
      <section className="demo-section">
        <h2>{t.demoRecoveryTitle}</h2>
        <p className="small">{t.demoRecoveryIntro}</p>
        <button className="big" onClick={() => go('recovery')}>{t.demoRecoveryButton}</button>
      </section>

      <section className="demo-section">
        <h2>{t.demoAskTitle}</h2>
        <p className="small">{t.demoAskIntro}</p>
        <div className="actions">
          <button className="big" onClick={() => go('ask')}>{t.demoAskButton}</button>
          <button className="secondary" onClick={() => go('supervisor')}>{t.demoSupervisorButton}</button>
        </div>
      </section>
      </div>

      <HowItWorks t={t} lang={lang} cost={info?.cost} onHistory={() => go('history')} />
    </>
  )
}
