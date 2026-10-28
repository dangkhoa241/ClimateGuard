import { useState } from 'react'
import { askQuestion } from './api.js'
import LocationPicker from './LocationPicker.jsx'

const MAX_CHARS = 500

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
            {status === 'asking' ? t.asking : t.askButton}
          </button>
        </form>
      )}
      {status === 'done' && result && <Answer result={result} t={t} />}
      <p className="muted small">{t.askNotMedical}</p>
    </>
  )
}
