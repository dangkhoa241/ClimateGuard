import { useEffect, useRef, useState } from 'react'
import {
  createRecovery, deleteRecovery, getRecovery, sendRecoveryAnswers, startRecoveryAnalysis, uploadRecoveryPhoto,
} from './api.js'
import { STRINGS } from './i18n.js'
import { preparePhoto } from './photoPrep.js'
import { reportDateLine } from './reportDate.js'

// Recovery agent: pick the disaster (or let the agent decide), add 1-6 photos, see the damage outlined by
// SAM 3.1, answer a few questions. The analysis is an async job: start it, then poll every 2 s.
const DISASTERS = ['flood', 'wildfire', 'earthquake', 'storm', 'heat_outage', 'other']
const MAX_PHOTOS = 6
const POLL_MS = 2000
const GIVE_UP_MS = 180000
const fill = (s, vars) => Object.entries(vars).reduce((out, [k, v]) => out.replaceAll(`{${k}}`, v), s)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function DisasterPicker({ t, value, onChange, disabled }) {
  return (
    <fieldset className="rec-disasters" disabled={disabled}>
      <legend>{t.recDisasterLabel}</legend>
      {[...DISASTERS, 'auto'].map((d) => (
        <button
          key={d}
          type="button"
          className={value === d ? 'active' : ''}
          aria-pressed={value === d}
          onClick={() => onChange(d)}
        >
          {d === 'auto' ? t.recAuto : t.recDisasters[d]}
        </button>
      ))}
    </fieldset>
  )
}

function DangerBanner({ lines }) {
  if (!lines?.length) return null
  return (
    <div className="notice error rec-danger" role="alert">
      <p><strong>{lines[0]}</strong></p>
      {lines.slice(1).map((l) => <p key={l}>{l}</p>)}
      <a className="big call911" href="tel:911">911</a>
    </div>
  )
}

function PhotoResult({ t, photo, url, n, outlines }) {
  return (
    <figure className="rec-photo">
      <div className="rec-photo-frame">
        <img src={url} alt={fill(t.recPhotoN, { n })} />
        {outlines && photo.overlay && <img className="rec-overlay" src={photo.overlay} alt="" />}
      </div>
      <figcaption>
        <strong>{fill(t.recPhotoN, { n })}</strong>
        {photo.found.length ? (
          <ul className="rec-legend">
            {photo.found.map((f) => (
              <li key={f.concept}>
                <span className="swatch" style={{ background: f.color }} aria-hidden="true" />
                {f.label}{f.count > 1 ? ` (${f.count})` : ''}
              </li>
            ))}
          </ul>
        ) : (
          <span className="muted small"> {t.recNothingOutlined}</span>
        )}
      </figcaption>
    </figure>
  )
}

// One side of the report: the person's language, or the English copy for the insurer.
function ReportSide({ t, side, created }) {
  return (
    <article className="answer rec-report" lang={side.lang} dir={side.lang === 'ar' ? 'rtl' : 'ltr'}>
      <h2>{t.recReportTitle}</h2>
      <p className="muted small">{reportDateLine(t.recReportDate, side.lang, created)} · {side.disaster_label}</p>
      <p className="rec-not-estimate">{t.recNotEstimate}</p>
      {side.fallback_en && <p className="muted small">{t.recFallbackEn}</p>}
      {side.danger_lines.map((l) => <p key={l}><strong>{l}</strong></p>)}
      <h3>{t.recSummary}</h3>
      <p>{side.summary}</p>
      <h3>{t.recAreas}</h3>
      <ul className="rec-areas">
        {side.areas.map((a) => (
          <li key={a.area}>
            <strong>{a.area}</strong>
            {a.photos.length > 0 && <span className="muted small"> · {fill(t.recPhotosRef, { list: a.photos.join(', ') })}</span>}
            <ul>{a.damage.map((d) => <li key={d}>{d}</li>)}</ul>
          </li>
        ))}
      </ul>
      {side.answers.length > 0 && (
        <>
          <h3>{t.recYourAnswers}</h3>
          <dl className="rec-answers">
            {side.answers.map((x) => <div key={x.q}><dt>{x.q}</dt><dd>{x.a}</dd></div>)}
          </dl>
        </>
      )}
      <h3>{t.recNextSteps}</h3>
      {side.checklist_lang !== side.lang && <p className="muted small">{t.checklistEnglishNote}</p>}
      <ol className="checklist" lang={side.checklist_lang}>
        {side.checklist.map((c) => (
          <li key={c.id} lang={c.lang}>{c.text}{c.detail && <><br /><em>{c.detail}</em></>}</li>
        ))}
      </ol>
      <p className="muted small">{t.recAiNote}</p>
    </article>
  )
}

function Questions({ t, questions, answers, setAnswer }) {
  return (
    <section className="recent">
      <h2>{t.recQuestionsTitle}</h2>
      <p className="muted small">{t.recQuestionsIntro} {t.recSkipNote}</p>
      {questions.map((q) => (
        <fieldset key={q.id} className="rec-question">
          <legend>{q.text}</legend>
          <div className="rec-options">
            {q.options.map((o) => (
              <button
                key={o.id}
                type="button"
                className={answers[q.id] === o.id ? 'active' : ''}
                aria-pressed={answers[q.id] === o.id}
                onClick={() => setAnswer(q.id, o.id)}
              >
                {o.text}
              </button>
            ))}
          </div>
        </fieldset>
      ))}
    </section>
  )
}

export default function RecoveryScreen({ lang, t }) {
  const [disaster, setDisaster] = useState('auto')
  const [photos, setPhotos] = useState([]) // {url, blob}
  const [phase, setPhase] = useState('pick') // pick | working | results | deleted
  const [step, setStep] = useState('')
  const [error, setError] = useState(null)
  const [view, setView] = useState(null)
  const [outlines, setOutlines] = useState(true)
  const [answers, setAnswers] = useState({})
  const fileInput = useRef(null)
  const alive = useRef(true)

  useEffect(() => () => { alive.current = false }, [])

  async function addFiles(files) {
    setError(null)
    const room = MAX_PHOTOS - photos.length
    if (files.length > room) setError('too_many_photos')
    const added = []
    for (const f of [...files].slice(0, Math.max(room, 0))) {
      try {
        added.push(await preparePhoto(f))
      } catch {
        setError('photo_unreadable')
      }
    }
    setPhotos((p) => [...p, ...added])
  }

  function removePhoto(i) {
    URL.revokeObjectURL(photos[i].url)
    setPhotos((p) => p.filter((_, j) => j !== i))
  }

  // Poll the job while the worker runs `busy` ("analyzing" or "reporting"); throws the job's error.
  async function waitWhile(job, v, busy, laterStep) {
    const start = Date.now()
    while (v.status === busy && alive.current) {
      await sleep(POLL_MS)
      if (laterStep && Date.now() - start > 6000) setStep(laterStep)
      if (Date.now() - start > GIVE_UP_MS) throw Object.assign(new Error(), { code: 'timeout' })
      v = await getRecovery(job)
    }
    if (v.status === 'error') throw Object.assign(new Error(), { code: v.error || 'default' })
    return v
  }

  async function run() {
    setError(null)
    setPhase('working')
    try {
      setStep(t.recStepPrepare)
      const job = (await createRecovery({ lang, disaster })).job
      for (let i = 0; i < photos.length; i++) {
        setStep(fill(t.recStepUpload, { n: i + 1, total: photos.length }))
        await uploadRecoveryPhoto(job, i, photos[i].blob)
      }
      setStep(t.recStepLook)
      const v = await waitWhile(job, await startRecoveryAnalysis(job), 'analyzing', t.recStepOutline)
      if (!alive.current) return
      setView(v)
      setPhase('results')
    } catch (err) {
      if (!alive.current) return
      setError(err.code || 'default')
      setPhase('pick')
    }
  }

  async function makeReport() {
    setError(null)
    setPhase('reporting')
    try {
      const v = await waitWhile(view.job, await sendRecoveryAnswers(view.job, answers), 'reporting')
      if (!alive.current) return
      setView(v)
      setPhase('report')
    } catch (err) {
      if (!alive.current) return
      setError(err.code || 'default')
      setPhase('results')
    }
  }

  async function removeAll() {
    try {
      await deleteRecovery(view.job)
    } catch (err) {
      if (err.code !== 'job_not_found') return setError(err.code || 'default')
    }
    photos.forEach((p) => URL.revokeObjectURL(p.url))
    setPhotos([])
    setView(null)
    setPhase('deleted')
  }

  function startOver() {
    setView(null)
    setAnswers({})
    setPhase('pick')
  }

  const expires = view && new Date(view.expires_at * 1000).toLocaleString(lang, {
    weekday: 'short', hour: 'numeric', minute: '2-digit',
  })

  return (
    <>
      {(phase === 'pick' || phase === 'working') && <p>{t.recIntro}</p>}
      <p className="muted small">{t.recPrivacy}</p>
      {error && <p className="notice error" role="alert">{t.errors[error] || t.errors.default}</p>}

      {phase === 'deleted' && (
        <>
          <p className="notice success">{t.recDeleted}</p>
          <button className="big" onClick={startOver}>{t.recStartOver}</button>
        </>
      )}

      {(phase === 'pick' || phase === 'working') && (
        <>
          <DisasterPicker t={t} value={disaster} onChange={setDisaster} disabled={phase === 'working'} />
          <h2 className="rec-h2">{t.recPhotosLabel}</h2>
          {photos.length > 0 && (
            <ul className="rec-thumbs">
              {photos.map((p, i) => (
                <li key={p.url}>
                  <img src={p.url} alt={fill(t.recPhotoN, { n: i + 1 })} />
                  {phase === 'pick' && (
                    <button type="button" aria-label={fill(t.recRemovePhoto, { n: i + 1 })} onClick={() => removePhoto(i)}>×</button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              addFiles(e.target.files)
              e.target.value = '' // the same photo can be picked again after removing it
            }}
          />
          {phase === 'pick' && photos.length < MAX_PHOTOS && (
            <button className="mid rec-add" type="button" onClick={() => fileInput.current.click()}>
              {photos.length ? t.recAddMore : t.recAddPhotos}
            </button>
          )}
          {photos.length > 0 && <p className="muted small">{fill(t.recPhotoCount, { n: photos.length })}</p>}
          <button className="big" onClick={run} disabled={!photos.length || phase === 'working'}>
            {phase === 'working' ? step : t.recCheck}
          </button>
        </>
      )}

      {['results', 'reporting', 'report'].includes(phase) && view && (
        <>
          <DangerBanner lines={view.danger_lines} />
          {phase === 'report' && view.report && (
            <>
              <ReportSide t={t} side={view.report.sides[0]} created={view.report.created} />
              {view.report.sides[1] && (
                // collapsed by default: the person reads their own language; the insurer gets the English copy
                <details className="rec-english">
                  <summary>{t.recShowEnglish}</summary>
                  <ReportSide t={STRINGS.en} side={view.report.sides[1]} created={view.report.created} />
                </details>
              )}
            </>
          )}
          <p className="rec-disaster">
            <strong>{fill(t.recDisasterSeen, { label: view.disaster_label })}</strong>
            {view.inferred_label && <span className="muted small"> · {fill(t.recInferredNote, { label: view.inferred_label })}</span>}
          </p>
          <button className="mid" type="button" aria-pressed={outlines} onClick={() => setOutlines(!outlines)}>
            {outlines ? t.recHideOutlines : t.recShowOutlines}
          </button>
          {view.photos.map((p) => (
            <PhotoResult key={p.index} t={t} photo={p} url={photos[p.index]?.url} n={p.index + 1} outlines={outlines} />
          ))}
          {phase !== 'report' && (
            <>
              <Questions t={t} questions={view.questions} answers={answers}
                         setAnswer={(q, a) => setAnswers((x) => ({ ...x, [q]: a }))} />
              <button className="big rec-make" onClick={makeReport} disabled={phase === 'reporting'}>
                {phase === 'reporting' ? t.recStepReport : t.recMakeReport}
              </button>
            </>
          )}
          <p className="muted small">{t.recNotEstimate}</p>
          <p className="muted small">{fill(t.recDeletesAt, { time: expires })}</p>
          <button className="secondary" type="button" onClick={removeAll}>{t.recDeleteNow}</button>
        </>
      )}
    </>
  )
}
