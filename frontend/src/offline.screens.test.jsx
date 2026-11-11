// Offline: the Alerts screen keeps the last alert it saw, labeled with its time and "may be out of date".
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { STRINGS } from './i18n.js'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)),
           removeItem: (k) => memory.delete(k), clear: () => memory.clear() },
})

const t = STRINGS.en
const ALERT = { sent_at: '2026-11-10T20:00:00+00:00', hazard: 'heat', severity: 'high',
  messages: { en: 'Heat Advisory today until 8 PM.', es: 'Advertencia de calor hoy hasta las 8 PM.', vi: 'Nắng nóng.' } }
let container, root
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 20)) })

beforeEach(() => {
  memory.clear()
  window.history.replaceState(null, '', '/?zone=CAZ159#/alerts')
  window.scrollTo = () => {}
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('offline alerts', () => {
  it('saves the newest alert when the list loads, with no email, ZIP or location in it', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([ALERT]) }))
    await act(async () => root.render(<App />))
    await settle()
    const saved = JSON.parse(memory.get('lastAlert'))
    expect(saved.zone).toBe('CAZ159')
    expect(saved.alert.messages.en).toBe(ALERT.messages.en)
    expect(Object.keys(saved).sort()).toEqual(['alert', 'lang', 'viewedAt', 'zone'])
  })

  it('shows the saved alert with its time and "may be out of date" when the network fails', async () => {
    memory.set('lastAlert', JSON.stringify({ zone: 'CAZ159', lang: 'en', viewedAt: '2026-11-10T20:05:00.000Z', alert: ALERT }))
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('offline')))
    await act(async () => root.render(<App />))
    await settle()
    const text = container.querySelector('.last-viewed').textContent
    expect(text).toContain('Heat Advisory today until 8 PM.')
    expect(text).toContain('May be out of date')
    expect(text).not.toContain('{time}')
  })

  it('shows the saved alert in the chosen language when it has one', async () => {
    memory.set('lang', 'es')
    memory.set('lastAlert', JSON.stringify({ zone: 'CAZ159', lang: 'es', viewedAt: '2026-11-10T20:05:00.000Z', alert: ALERT }))
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('offline')))
    await act(async () => root.render(<App />))
    await settle()
    expect(container.querySelector('.last-viewed').textContent).toContain('Advertencia de calor')
    expect(container.querySelector('.last-viewed').textContent).toContain('desactualizada')
  })

  it('shows nothing saved for a different area, and the normal error stays', async () => {
    memory.set('lastAlert', JSON.stringify({ zone: 'MNZ060', lang: 'en', viewedAt: '2026-11-10T20:05:00.000Z', alert: ALERT }))
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('offline')))
    await act(async () => root.render(<App />))
    await settle()
    expect(container.querySelector('.last-viewed')).toBeNull()
    expect(container.textContent).toContain(t.loadError)
  })

  it('shows the offline banner when the browser is offline', async () => {
    Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: false })
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('offline')))
    await act(async () => root.render(<App />))
    await settle()
    expect(container.querySelector('.offline-banner').textContent).toBe(t.offlineBanner)
    Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: true })
  })
})
