// PWA helpers: service worker registration, install prompt, the push feature flag, and the "last alert viewed"
// copy used offline. Nothing here touches the network except registering /sw.js.

// --- feature flag: push UI is hidden for normal browser visitors. It shows when the URL has ?push=1 (remembered
// for the tab session) OR the app runs installed: an iPhone Home Screen app has no address bar and its own storage,
// so ?push=1 cannot reach it. Demo mode is guarded separately (PushSignup, api.js, push.js never subscribe). ---
export function pushFlagOn() {
  if (isStandalone()) return true
  try {
    if (new URLSearchParams(window.location.search).get('push') === '1') {
      try { sessionStorage.setItem('cgPush', '1') } catch { /* storage blocked: the URL flag still works */ }
      return true
    }
    return sessionStorage.getItem('cgPush') === '1'
  } catch {
    return false
  }
}

export const inDemo = () => new URLSearchParams(window.location.search).get('demo') === '1'

// --- install ---
let deferredPrompt = null
const listeners = new Set()
const notify = () => listeners.forEach((fn) => fn())

export function initInstallPrompt() {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferredPrompt = e
    notify()
  })
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    notify()
  })
}

export function onInstallChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const canPromptInstall = () => Boolean(deferredPrompt)

export async function promptInstall() {
  if (!deferredPrompt) return 'unavailable'
  const prompt = deferredPrompt
  deferredPrompt = null
  notify()
  await prompt.prompt()
  const choice = await prompt.userChoice
  return choice?.outcome || 'dismissed'
}

export function isStandalone() {
  return Boolean(window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone)
}

export function isIos() {
  const ua = window.navigator.userAgent || ''
  // iPadOS 13+ reports a Mac user agent but has touch points
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && window.navigator.maxTouchPoints > 1)
}

// --- service worker ---
export function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {})
  })
}

// --- offline: the last alert the person viewed (public alert text only; no email, ZIP or coordinates) ---
const LAST_KEY = 'lastAlert'

export function saveLastAlert(zone, lang, alert) {
  try {
    if (!alert) return
    const record = { zone, lang, viewedAt: new Date().toISOString(),
      alert: { sent_at: alert.sent_at, hazard: alert.hazard, severity: alert.severity, messages: alert.messages } }
    localStorage.setItem(LAST_KEY, JSON.stringify(record))
  } catch { /* storage blocked or full: the offline copy just won't exist */ }
}

export function loadLastAlert(zone) {
  try {
    const record = JSON.parse(localStorage.getItem(LAST_KEY) || 'null')
    return record && record.zone === zone && record.alert ? record : null
  } catch {
    return null
  }
}
