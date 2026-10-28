import { useEffect, useState } from 'react'
import { askQuestion } from './api.js'
import LocationPicker from './LocationPicker.jsx'

const MAX_CHARS = 500
// The API can't stream (API Gateway HTTP API), so progress is shown in steps. Data takes well under a
// second; the model ~3 s. Steps only move forward and stop at the last one until the answer arrives.
const STEP_AT_MS = [0, 700, 6000] // askStepData, askStepWriting, askStepAlmost

function useAskStep(active) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    if (!active) return undefined
    setStep(0)
    const timers = STEP_AT_MS.slice(1).map((ms, i) => setTimeout(() => setStep(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [active])
  return step
}

function Answer({ result, t }) {
  return (
    <article className="answer" aria-live="polite">
      <p className="answer-text">{result.answer}</p>
      {result.data_time_local && (
        <p className="muted small">{t.askDataFrom.replace('{place}', result.place).replace('{time}', result.data_time_local)}</p>
      )}
      {result.sources?.length > 0 && (
        <details className="sources">
          <summary>{t.askSources}</summary>
          <ul>
            {result.sources.map((s) => (
              <li key={s.title}>
                <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> <span className="muted">({s.source})</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

export default function AskScreen({ lang, t, zone, setZone }) {
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState('idle') // idle | asking | done | error
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const step = useAskStep(status === 'asking')
  const stepText = [t.askStepData, t.askStepWriting, t.askStepAlmost][step]

  async function onSubmit(e) {
    e.preventDefault()
    setStatus('asking')
    setError(null)
    try {
      setResult(await askQuestion({ question: question.trim(), lang, zone: zone.zone }))
      setStatus('done')
    } catch (err) {
      setError(err.code)
      setStatus('error')
    }
  }

  return (
    <>
      <p>{t.askIntro}</p>
      <LocationPicker t={t} zone={zone} onLocated={(z, loc) => setZone({ ...z, location: loc })} />
      {zone && (
        <form className="signup" onSubmit={onSubmit} noValidate>
          <label htmlFor="question">{t.askLabel}</label>
          <textarea
            id="question"
            rows={3}
            maxLength={MAX_CHARS}
            placeholder={t.askPlaceholder}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          {status === 'error' && (
            <p className="notice error" role="alert">{t.errors[error] || t.errors.default}</p>
          )}
          <button className="big" type="submit" disabled={!question.trim() || status === 'asking'}>
            {status === 'asking' ? stepText : t.askButton}
          </button>
          {status === 'asking' && (
            <ol className="ask-steps" aria-live="polite">
              {[t.askStepData, t.askStepWriting].map((label, i) => (
                <li key={label} className={i < step ? 'done' : i === step ? 'now' : ''}>{label}</li>
              ))}
            </ol>
          )}
        </form>
      )}
      {status === 'done' && result && <Answer result={result} t={t} />}
      <p className="muted small">{t.askNotMedical}</p>
    </>
  )
}
