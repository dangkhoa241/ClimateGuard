// Renders the app in a browser-like page and opens every main screen. Any error thrown while rendering,
// or in an effect, fails the test. The app is rendered WITHOUT the error boundary on purpose, so a crash
// is not hidden. Offline: fetch is stubbed.
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'
import { STRINGS } from './i18n.js'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

// Newer Node versions define their own (broken) global localStorage that hides jsdom's: use a plain one.
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)),
           removeItem: (k) => memory.delete(k), clear: () => memory.clear() },
})

let container, root

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', '/')
  // Current Chrome: window.scrollTo() returns a Promise. An effect that returns it crashes React on the next
  // render ("n is not a function"). Safari returns undefined, which hid the bug on an iPhone.
  window.scrollTo = () => Promise.resolve()
  window.HTMLElement.prototype.scrollIntoView = () => Promise.resolve()
  globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ events: [], decisions: [], zones: [], by_day: [], totals: {} }) }))
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

const mount = async (url = '/') => {
  window.history.replaceState(null, '', url)
  await act(async () => root.render(<App />))
}
const click = async (el) => act(async () => el.dispatchEvent(new MouseEvent('click', { bubbles: true })))
const button = (text) => [...container.querySelectorAll('button')].find((b) => b.textContent.includes(text))
const t = STRINGS.en

describe('every main screen renders without throwing', () => {
  it('home', async () => {
    await mount()
    expect(container.querySelector('h1').textContent).toBe('ClimateGuard')
    expect(button(t.demoTry)).toBeTruthy()
  })

  it.each([
    ['Ask', t.ask, t.ask],
    ['Report damage', t.recovery, t.recovery],
    ['Supervisor', t.supervisor, t.supervisor],
    ['History', t.history, t.history],
    ['Alerts', t.alerts, t.alerts],
  ])('%s', async (_name, label, heading) => {
    await mount()
    await click(button(label))
    expect(container.querySelector('h1').textContent).toBe(heading)
    await click(button(t.back)) // back to home and into the screen again: effects run, clean up and re-run
    await click(button(label))
    expect(container.querySelector('h1').textContent).toBe(heading)
  })

  it('Demo, from the home button and from ?demo=1, and on into the other screens', async () => {
    await mount()
    await click(button(t.demoTry))
    expect(container.querySelector('h1').textContent).toBe(t.demoTitle)
    for (const label of [t.demoRecoveryButton, t.demoAskButton, t.demoSupervisorButton, t.demoHowHistory]) {
      await click(button(label)) // lands on another screen
      expect(container.querySelector('h1').textContent).not.toBe(t.demoTitle)
      await click(button(t.back)) // back returns to the demo page, not home
      expect(container.querySelector('h1').textContent).toBe(t.demoTitle)
    }
    act(() => root.unmount())
    root = createRoot(container)
    await mount('/?demo=1')
    expect(container.querySelector('h1').textContent).toBe(t.demoTitle)
  })
})

describe('error boundary', () => {
  it('shows a friendly message with Reload and the demo link instead of a blank page, in the saved language', async () => {
    localStorage.setItem('lang', 'vi')
    window.history.replaceState(null, '', '/')
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    function Boom() {
      throw new TypeError('n is not a function')
    }
    await act(async () => root.render(<ErrorBoundary><Boom /></ErrorBoundary>))
    expect(container.textContent).toContain(STRINGS.vi.crashTitle)
    expect(container.textContent).toContain(STRINGS.vi.crashReload)
    expect(container.querySelector('a').getAttribute('href')).toBe('/?demo=1')
    expect(spy.mock.calls.some((c) => String(c[0]).includes('ClimateGuard crashed'))).toBe(true)
    spy.mockRestore()
  })
})
