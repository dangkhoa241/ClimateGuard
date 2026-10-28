import { useEffect, useRef, useState } from 'react'
import { askQuestion, transcribeAudio } from './api.js'
import LocationPicker from './LocationPicker.jsx'
import ReadAloud from './ReadAloud.jsx'
import { canRecord, startRecording } from './voice.js'

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

// Mic button: tap to record, tap again to stop. The text lands in the question box to check first.
function VoiceInput({ lang, t, onText, disabled }) {
  const [state, setState] = useState('idle') // idle | recording | working
  const [error, setError] = useState(null)
  const [secs, setSecs] = useState(0)
  const recRef = useRef(null)

  useEffect(() => {
    if (state !== 'recording') return undefined
    setSecs(0)
    const id = setInterval(() => setSecs((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [state])

  async function finish() {
    setState('working')
    try {
      const wav = await recRef.current.stop()
      const { text } = await transcribeAudio(wav, lang)
      if (text) onText(text)
      else setError('no_speech')
    } catch (err) {
      setError(err.code || 'transcribe_failed')
    }
    recRef.current = null
    setState('idle')
  }

  async function toggle() {
    if (state === 'recording') return finish()
    setError(null)
    try {
      recRef.current = await startRecording({ onAutoStop: finish })
      setState('recording')
    } catch (err) {
      setError(err.message === 'mic_denied' ? 'mic_denied' : 'default')
    }
    return undefined
  }

  if (!canRecord()) return null
  return (
    <div className="voice">
      <button type="button" className={`mic ${state}`} onClick={toggle} disabled={disabled || state === 'working'}
        aria-pressed={state === 'recording'}>
        <span aria-hidden="true">{state === 'recording' ? '■' : '🎤'}</span>{' '}
        {state === 'recording' ? `${t.voiceStop} (${secs}s)` : state === 'working' ? t.voiceWorking : t.voiceSpeak}
      </button>
      {error && <p className="notice error" role="alert">{t.errors[error] || t.errors.default}</p>}
    </div>
  )
}

// The data time in the reader's language: written by the server ("12:48 trưa thứ Tư"), else formatted here.
function dataTime(result, lang, tz) {
  if (result.data_time_text) return result.data_time_text
  if (!result.data_time) return result.data_time_local
  try {
    return new Date(result.data_time).toLocaleString(lang, { weekday: 'short', hour: 'numeric', minute: '2-digit',
      ...(tz ? { timeZone: tz } : {}) })
  } catch {
    return result.data_time_local
  }
}

function Answer({ result, lang, t, tz }) {
  return (
    <article className="answer" aria-live="polite">
      <p className="answer-text">{result.answer}</p>
      <ReadAloud text={result.answer} lang={lang} t={t} options />
      {result.data_time_local && (
        <p className="muted small">{t.askDataFrom.replace('{place}', result.place).replace('{time}', dataTime(result, lang, tz))}</p>
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
  const [fromVoice, setFromVoice] = useState(false)
  const step = useAskStep(status === 'asking')
  const stepText = [t.askStepData, t.askStepWriting, t.askStepAlmost][step]

  async function onSubmit(e) {
    e.preventDefault()
    setStatus('asking')
    setError(null)
    setFromVoice(false)
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
          <VoiceInput lang={lang} t={t} disabled={status === 'asking'}
            onText={(text) => { setQuestion(text.slice(0, MAX_CHARS)); setFromVoice(true) }} />
          {fromVoice && question && <p className="muted small">{t.voiceCheck}</p>}
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
      {status === 'done' && result && <Answer result={result} lang={lang} t={t} tz={zone?.tz} />}
      <p className="muted small">{t.askNotMedical}</p>
    </>
  )
}
