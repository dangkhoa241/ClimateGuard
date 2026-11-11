import { useEffect, useState } from 'react'
import { canPromptInstall, isIos, isStandalone, onInstallChange, promptInstall, pushFlagOn } from './pwa.js'

export default function InstallScreen({ t }) {
  const [canInstall, setCanInstall] = useState(canPromptInstall())
  const [installed, setInstalled] = useState(isStandalone())
  useEffect(() => onInstallChange(() => { setCanInstall(canPromptInstall()); setInstalled(isStandalone()) }), [])
  const ios = isIos()

  if (installed) return <p className="notice success" role="status">{t.installDone}</p>

  return (
    <section className="install">
      <p>{t.installIntro}</p>
      {canInstall && (
        <button type="button" className="big" onClick={() => promptInstall()}>{t.installButton}</button>
      )}
      {(ios || !canInstall) && (
        <div className="notice">
          <h2>{t.installIosTitle}</h2>
          <ol>
            <li>{t.installIos1}</li>
            <li>{t.installIos2}</li>
            <li>{t.installIos3}</li>
            <li>{t.installIos4}</li>
          </ol>
          {pushFlagOn() && <p className="muted small">{t.installPushNote}</p>}
        </div>
      )}
      {!ios && (
        <div className="notice">
          <h2>{t.installAndroidTitle}</h2>
          <p>{t.installAndroid}</p>
          <p className="muted small">{t.installDesktop}</p>
        </div>
      )}
    </section>
  )
}
