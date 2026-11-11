import { useEffect, useState } from 'react'
import { ALERT_LANGS } from './api.js'
import { currentPush, disablePush, enablePush, needsInstall, pushSupported, vapidPublicKey } from './push.js'
import { pushFlagOn } from './pwa.js'

const MESSAGE_KEYS = { denied: 'pushDenied', no_key: 'pushNoKey', unsupported: 'pushUnsupported',
  invalid_subscription: 'pushErrInvalid' }

// "Turn on phone notifications": hidden unless the URL has ?push=1 until the owner has tested it on a phone.
export default function PushSignup({ lang, t, zone, demo = false }) {
  const location = zone?.location
  const [pushLang, setPushLang] = useState(lang)
  const [status, setStatus] = useState('idle') // idle | working | on | error
  const [on, setOn] = useState(null)
  const [error, setError] = useState(null)
  const flag = pushFlagOn()

  useEffect(() => setPushLang(lang), [lang])
  useEffect(() => {
    let cancelled = false
    if (flag && !demo) {
      currentPush().then((record) => {
        if (cancelled || !record) return
        setOn(record)
        setStatus('on')
      })
    }
    return () => {
      cancelled = true
    }
  }, [flag, demo])

  if (!flag) return null
  const langName = (code) => ALERT_LANGS.find((l) => l.code === code)?.native || code

  if (demo) {
    return (
      <section className="push-signup">
        <h2>{t.pushTitle}</h2>
        <p className="notice demo-note small">{t.pushDemoNote}</p>
      </section>
    )
  }

  async function turnOn() {
    setStatus('working')
    setError(null)
    try {
      await enablePush({ lang: pushLang, location, place: zone?.place })
      setOn({ place: zone?.place || zone?.name, lang: pushLang })
      setStatus('on')
    } catch (err) {
      setError(err.code || 'default')
      setStatus('error')
    }
  }

  async function turnOff() {
    setStatus('working')
    try {
      await disablePush()
    } finally {
      setOn(null)
      setStatus('idle')
    }
  }

  const errorText = (code) => (MESSAGE_KEYS[code] ? t[MESSAGE_KEYS[code]] : t.errors[code] || t.errors.default)
  const blocked = !pushSupported() ? 'pushUnsupported' : needsInstall() ? 'pushNeedInstall' : null

  return (
    <section className="push-signup">
      <h2>{t.pushTitle}</h2>
      <p>{t.pushIntro}</p>
      {blocked && (
        <div className="notice" role="status">
          <p>{t[blocked]}</p>
          {blocked === 'pushNeedInstall' && <a href="#/install">{t.pushNeedInstallLink}</a>}
        </div>
      )}
      {!blocked && status === 'on' && on && (
        <div className="notice success" role="status">
          <p>{t.pushOn.replace('{place}', on.place || '').replace('{language}', langName(on.lang))}</p>
          <button type="button" className="secondary" onClick={turnOff}>{t.pushTurnOff}</button>
        </div>
      )}
      {!blocked && status !== 'on' && (
        <>
          {!location && <p className="muted small">{t.pushStepPlace}</p>}
          <label htmlFor="push-lang">{t.alertLanguage}</label>
          <select id="push-lang" value={pushLang} onChange={(e) => setPushLang(e.target.value)}>
            {ALERT_LANGS.map((l) => (
              <option key={l.code} value={l.code}>{l.native}{l.reviewed ? '' : ` · ${t.autoTranslation}`}</option>
            ))}
          </select>
          {!ALERT_LANGS.find((l) => l.code === pushLang)?.reviewed && <p className="muted small">{t.autoTranslationNote}</p>}
          {status === 'error' && (
            <div className="notice error" role="alert">
              <p>{errorText(error)}</p>
            </div>
          )}
          <button className="big" type="button" disabled={!location || status === 'working' || !vapidPublicKey()}
            onClick={turnOn}>
            {status === 'working' ? t.pushWorking : t.pushButton}
          </button>
          {!vapidPublicKey() && <p className="muted small">{t.pushNoKey}</p>}
          <p className="muted small">{t.pushPrivacy}</p>
          <p className="muted small">{t.pushSilentNote}</p>
        </>
      )}
    </section>
  )
}
