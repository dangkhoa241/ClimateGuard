// Phone notifications (web push): browser side. The server only ever gets the push subscription, the language and
// the ZIP or rounded coordinates, never an email address. Demo mode never gets here (see assertNotDemo).
import { subscribePush, unsubscribePush } from './api.js'
import { inDemo, isIos, isStandalone } from './pwa.js'

const KEY = 'pushSub' // {zone, place, lang}: what this phone is subscribed to, for the "On for ..." line

export class PushError extends Error {
  constructor(code) {
    super(code)
    this.code = code
  }
}

export function pushSupported() {
  return typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// iPhone and iPad only deliver web push to an app added to the Home Screen.
export const needsInstall = () => isIos() && !isStandalone()

export const vapidPublicKey = () => (import.meta.env.VITE_VAPID_PUBLIC_KEY || '').trim()

function assertNotDemo() {
  if (inDemo()) throw new PushError('demo_mode') // demo mode never creates a real push subscription
}

export function urlBase64ToUint8Array(value) {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

export function savedPush() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || 'null')
  } catch {
    return null
  }
}

function remember(record) {
  try {
    if (record) localStorage.setItem(KEY, JSON.stringify(record))
    else localStorage.removeItem(KEY)
  } catch { /* storage blocked: the screen just will not remember it */ }
}

async function registration() {
  return navigator.serviceWorker.ready
}

// Is this phone subscribed right now? (browser subscription AND our saved record)
export async function currentPush() {
  if (!pushSupported() || inDemo()) return null
  try {
    const sub = await (await registration()).pushManager.getSubscription()
    return sub ? savedPush() : null
  } catch {
    return null
  }
}

// Called from a tap (iOS requires a user gesture for the permission prompt).
export async function enablePush({ lang, location, place }) {
  assertNotDemo()
  if (!pushSupported()) throw new PushError('unsupported')
  if (needsInstall()) throw new PushError('need_install')
  const key = vapidPublicKey()
  if (!key) throw new PushError('no_key')
  if (!location) throw new PushError('missing_location')

  const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission()
  if (permission !== 'granted') throw new PushError('denied')

  const reg = await registration()
  let sub = await reg.pushManager.getSubscription()
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) })
  try {
    const result = await subscribePush({ subscription: sub.toJSON(), lang, location })
    remember({ zone: result.zone, place: result.place || place || result.zone_name, lang })
    return result
  } catch (err) {
    await sub.unsubscribe().catch(() => {}) // do not keep a browser subscription the server does not know
    throw err
  }
}

// Server first (it needs the endpoint itself), then the browser. If the server cannot be reached the browser
// subscription is still removed, and the server forgets the device on its first undeliverable push.
export async function disablePush() {
  assertNotDemo()
  remember(null)
  if (!pushSupported()) return
  const sub = await (await registration()).pushManager.getSubscription()
  if (!sub) return
  try {
    await unsubscribePush(sub.endpoint)
  } catch { /* offline: cleaned up server-side later */ }
  await sub.unsubscribe()
}
