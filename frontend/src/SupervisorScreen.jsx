import { useState } from 'react'
import { getPreTalk } from './api.js'
import LocationPicker from './LocationPicker.jsx'
import ReadAloud from './ReadAloud.jsx'
import ShareWhatsApp from './ShareWhatsApp.jsx'

// Supervisor view: today's crew checklist (fixed Cal/OSHA or OSHA text, picked by today's data) and an
// AI pre-shift talk written only from that checklist, to read aloud or share in the crew's WhatsApp group.
function Today({ d, t }) {
  const rows = [
    [t.todayHigh, d.high_f != null ? `${d.high_f}°F` : null], [t.todayLow, d.low_f != null ? `${d.low_f}°F` : null],
    [t.todayHours95, d.hours_ge_95f], [t.todayAqi, d.aqi_forecast_max || d.aqi_now],
  ].filter(([, v]) => v != null)
  return (
    <section className="stats">
      <h2>{t.todayTitle}</h2>
      <dl>
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
      {d.nws_alerts?.length > 0 && <p className="small" lang="en" dir="ltr">⚠ {d.nws_alerts.join(', ')}</p>}
    </section>
  )
}

export default function SupervisorScreen({ lang, t, zone, setZone }) {
  const [state, setState] = useState({ status: 'idle' }) // idle | loading | done | error

  async function load() {
    setState({ status: 'loading' })
    try {
      setState({ status: 'done', data: await getPreTalk({ zone: zone.zone, lang }) })
    } catch (err) {
      setState({ status: 'error', error: err.code })
    }
  }

  const data = state.data
  return (
    <>
      <p>{t.supervisorIntro}</p>
      <LocationPicker t={t} zone={zone} onLocated={(z, loc) => setZone({ ...z, location: loc })} />
      {zone && (
        <button className="big" onClick={load} disabled={state.status === 'loading'}>
          {state.status === 'loading' ? t.makingTalk : t.makeTalk}
        </button>
      )}
      {state.status === 'error' && (
        <div className="notice error" role="alert">
          <p>{t.errors[state.error] || t.errors.default}</p>
          <button type="button" className="secondary" onClick={load}>{t.retry}</button>
        </div>
      )}
      {data && (
        <>
          <Today d={data.today} t={t} />
          <article className="answer" aria-live="polite">
            <h2>{t.talkTitle}</h2>
            {data.kind === 'checklist_only' && <p className="muted small">{t.talkChecklistOnly}</p>}
            {data.automatic && <p className="muted small">{t.autoTalkNote}</p>}
            <p className="answer-text">{data.talk}</p>
            <ReadAloud text={data.talk} lang={lang} t={t} options />
            <ShareWhatsApp text={data.talk} zone={zone?.zone} lang={lang} t={t} />
          </article>
          <section className="recent">
            <h2>{t.checklistTitle}</h2>
            {data.checklist_lang !== lang && <p className="muted small">{t.checklistEnglishNote}</p>}
            <ul className="checklist" lang={data.checklist_lang}>
              {data.checklist.map((i) => <li key={i.id}>{i.text}</li>)}
            </ul>
            <p className="muted small">{data.today.calosha_applies ? t.calOshaNote : t.federalOshaNote}</p>
          </section>
          <p className="muted small">{t.supervisorNotLegal}</p>
        </>
      )}
    </>
  )
}
