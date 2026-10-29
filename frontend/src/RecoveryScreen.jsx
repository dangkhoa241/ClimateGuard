import { useEffect, useRef, useState } from 'react'
import {
  createRecovery, deleteRecovery, getRecovery, sendRecoveryAnswers, startRecoveryAnalysis, uploadRecoveryPhoto,
} from './api.js'
import { preparePhoto } from './photoPrep.js'
import { deletesAtLine } from './reportDate.js'
import { reveal } from './reveal.js'
import { ResultsView, fill } from './RecoveryReport.jsx'

// Recovery agent: pick the disaster (or let the agent decide), add 1-6 photos, see the damage outlined by
// SAM 3.1, answer a few questions. The analysis is an async job: start it, then poll every 2 s.
const DISASTERS = ['flood', 'wildfire', 'earthquake', 'storm', 'heat_outage', 'other']
const MAX_PHOTOS = 6
const POLL_MS = 2000
const GIVE_UP_MS = 180000
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
// Demo mode: public-domain photos (US government works, via Wikimedia Commons) so nobody needs their own.
// The fire photo is cropped to leave out a bystander. Files in frontend/public/samples/.
const SAMPLES = [
  { id: 'storm', disaster: 'storm', credit: 'Greg Henshall / FEMA, Greensburg, Kansas, 2007',
    source: 'https://commons.wikimedia.org/wiki/File:FEMA_-_30163_-_Tornado_damaged_home_in_Kansas.jpg' },
  { id: 'flood', disaster: 'flood', credit: 'Liz Roll / FEMA, Liberty, Kentucky, 2010',
    source: 'https://commons.wikimedia.org/wiki/File:FEMA_-_44499_-_Liberty_Kentucky_water_damage.jpg' },
  { id: 'fire', disaster: 'wildfire', credit: 'Susie Shapira / FEMA, Pauma, California, 2007',
    source: 'https://commons.wikimedia.org/wiki/File:FEMA_-_33504_-_debris_from_a_burned_home_in_California.jpg' },
  { id: 'earthquake', disaster: 'earthquake', credit: 'J.K. Nakata / U.S. Geological Survey, Watsonville, California, 1989',
    source: 'https://commons.wikimedia.org/wiki/File:089srUSGSoffFoundation.jpg' },
]

function SamplePhotos({ t, onPick, disabled }) {
  return (
    <section className="rec-samples">
      <h2 className="rec-h2">{t.demoSamplesTitle}</h2>
      <ul>
        {SAMPLES.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onPick(s)} disabled={disabled}>
              <img src={`/samples/${s.id}.jpg`} alt="" loading="lazy" />
              <span>{t.recDisasters[s.disaster]}</span>
            </button>
            <a className="muted small" href={s.source} target="_blank" rel="noreferrer" lang="en" dir="ltr">
              {fill(t.demoSampleCredit, { credit: s.credit })}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}

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

function Questions({ t, questions, answers, setAnswer, headingRef }) {
  return (
    <section className="recent">
      <h2 ref={headingRef}>{t.recQuestionsTitle}</h2>
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

export default function RecoveryScreen({ lang, t, zone, demo }) {
  const place = zone?.place || null // "Stockton, CA" when the person picked an area elsewhere in the app
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
  // Scroll to what just appeared: the questions after the photo check, the report once written (both also get
  // focus, for screen readers), and any error. `revealNext` is set only by a step that finished successfully.
  const [revealNext, setRevealNext] = useState(null) // 'questions' | 'report'
  const questionsRef = useRef(null)
  const reportRef = useRef(null)
  const errorRef = useRef(null)

  useEffect(() => {
    if (!revealNext) return
    reveal((revealNext === 'report' ? reportRef : questionsRef).current, { focus: true })
    setRevealNext(null)
  }, [revealNext, phase])
  useEffect(() => {
    if (error) reveal(errorRef.current)
  }, [error])

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

  // Demo: a sample is added like a photo the person picked (same canvas step), and sets the disaster
  // when it's the first photo; mixed samples go back to "let the agent decide".
  async function addSample(sample) {
    setError(null)
    try {
      const res = await fetch(`/samples/${sample.id}.jpg`)
      if (!res.ok) throw new Error('photo_unreadable')
      const file = new File([await res.blob()], `${sample.id}.jpg`, { type: 'image/jpeg' })
      await addFiles([file])
      setDisaster((d) => (photos.length === 0 ? sample.disaster : d === sample.disaster ? d : 'auto'))
    } catch {
      setError('photo_unreadable')
    }
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
      setRevealNext('questions')
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
      setRevealNext('report')
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

  return (
    <>
      {(phase === 'pick' || phase === 'working') && <p>{t.recIntro}</p>}
      <p className="muted small">{t.recPrivacy}</p>
      {error && <p ref={errorRef} className="notice error" role="alert">{t.errors[error] || t.errors.default}</p>}

      {phase === 'deleted' && (
        <>
          <p className="notice success">{t.recDeleted}</p>
          <button className="big" onClick={startOver}>{t.recStartOver}</button>
        </>
      )}

      {(phase === 'pick' || phase === 'working') && (
        <>
          <DisasterPicker t={t} value={disaster} onChange={setDisaster} disabled={phase === 'working'} />
          {demo && phase === 'pick' && photos.length < MAX_PHOTOS && <SamplePhotos t={t} onPick={addSample} />}
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
        <ResultsView t={t} lang={lang} view={view} showReport={phase === 'report'} place={place} reportHeadingRef={reportRef}
                     photoUrls={photos.map((p) => p.url)} outlines={outlines} setOutlines={setOutlines}>
          {phase !== 'report' && (
            <>
              <Questions t={t} questions={view.questions} answers={answers} headingRef={questionsRef}
                         setAnswer={(q, a) => setAnswers((x) => ({ ...x, [q]: a }))} />
              <button className="big rec-make" onClick={makeReport} disabled={phase === 'reporting'}>
                {phase === 'reporting' ? t.recStepReport : t.recMakeReport}
              </button>
            </>
          )}
          <p className="muted small">{t.recNotEstimate}</p>
          <p className="muted small">{deletesAtLine(t.recDeletesAt, lang, view.expires_at)}</p>
          <button className="secondary" type="button" onClick={removeAll}>{t.recDeleteNow}</button>
        </ResultsView>
      )}
    </>
  )
}
