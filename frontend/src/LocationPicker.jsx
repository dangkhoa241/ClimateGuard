import { useState } from 'react'
import { locateByCoords, locateByZip } from './api.js'

// Pick a location by ZIP code or browser geolocation; resolves to an NWS forecast zone.
// `onLocated(zone, location)` gets the zone info and what to send with a sign-up.
export default function LocationPicker({ t, zone, onLocated }) {
  const [zip, setZip] = useState('')
  const [status, setStatus] = useState('idle') // idle | busy | error
  const [error, setError] = useState(null)
  const [retry, setRetry] = useState(null)

  async function run(lookup, location) {
    setStatus('busy')
    setError(null)
    setRetry(() => () => run(lookup, location))
    try {
      const z = await lookup()
      onLocated(z, location)
      setStatus('idle')
    } catch (err) {
      setError(err.code)
      setStatus('error')
    }
  }

  function byZip(e) {
    e.preventDefault()
    const clean = zip.trim()
    if (!/^\d{5}$/.test(clean)) {
      setError('invalid_zip')
      setStatus('error')
      return
    }
    run(() => locateByZip(clean), { zip: clean })
  }

  function byGps() {
    if (!navigator.geolocation) {
      setError('no_gps')
      setStatus('error')
      return
    }
    setStatus('busy')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = Number(pos.coords.latitude.toFixed(2))
        const lon = Number(pos.coords.longitude.toFixed(2))
        run(() => locateByCoords(lat, lon), { lat, lon })
      },
      () => {
        setError('gps_denied')
        setStatus('error')
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    )
  }

  return (
    <section className="location">
      <form className="zip-row" onSubmit={byZip}>
        <label htmlFor="zip">{t.zipLabel}</label>
        <div className="row">
          <input id="zip" inputMode="numeric" autoComplete="postal-code" maxLength={5} placeholder="95202"
            value={zip} onChange={(e) => setZip(e.target.value.replace(/\D/g, ''))} />
          <button type="submit" className="mid" disabled={status === 'busy'}>{t.findArea}</button>
        </div>
      </form>
      <button type="button" className="gps" onClick={byGps} disabled={status === 'busy'}>
        📍 {t.useMyLocation}
      </button>
      {status === 'busy' && <p className="muted">{t.locating}</p>}
      {status === 'error' && (
        <div className="notice error" role="alert">
          <p>{t.errors[error] || t.errors.default}</p>
          {retry && <button type="button" className="secondary" onClick={retry}>{t.retry}</button>}
        </div>
      )}
      {zone && (
        <p className="zone-chip" aria-live="polite">
          {t.yourArea}: <strong>{zone.place || zone.name}</strong>
          <span className="muted small"> · NWS {zone.zone} ({zone.name})</span>
        </p>
      )}
    </section>
  )
}
