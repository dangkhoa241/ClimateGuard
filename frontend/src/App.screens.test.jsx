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
// history.back() / forward() fire popstate a moment later: wait for it
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 15)) })
const click = async (el) => {
  const before = window.location.href
  const isBack = el.classList.contains('back') // the in-app Back button uses history.back(), which is async
  await act(async () => el.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  if (isBack) for (let i = 0; i < 100 && window.location.href === before; i++) await settle()
  await settle()
}
const heading = () => container.querySelector('h1').textContent
// Poll until the page shows `title` (history changes finish a moment later, longer on a busy machine)
const waitForHeading = async (title) => {
  for (let i = 0; i < 100 && heading() !== title; i++) await settle()
}
const remount = async (url) => { // what F5 does: a fresh page at the same URL (storage survives, state does not)
  act(() => root.unmount())
  root = createRoot(container)
  await mount(url)
}
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

describe('the URL follows the screen (refresh, Back and Forward)', () => {
  const SCREENS = [['ask', t.ask], ['alerts', t.alerts], ['recovery', t.recovery], ['supervisor', t.supervisor],
    ['history', t.history], ['demo', t.demoTitle], ['how-it-works', t.howWorksTitle]]

  it.each(SCREENS)('loading #/%s opens that screen', async (name, title) => {
    await mount(`/#/${name}`)
    expect(heading()).toBe(title)
  })

  it('opening a screen puts only its name in the URL', async () => {
    await mount()
    await click(button(t.ask))
    expect(window.location.hash).toBe('#/ask')
    expect(window.location.search).toBe('')
  })

  it.each(['#/nope', '#/constructor', '#/__proto__', '#/ask/extra', '#', ''])('unknown hash %j opens home', async (hash) => {
    await mount(`/${hash}`)
    expect(heading()).toBe('ClimateGuard')
  })

  it('F5 on a screen stays on it', async () => {
    await mount()
    await click(button(t.supervisor))
    await remount(window.location.href)
    expect(heading()).toBe(t.supervisor)
  })

  it('browser Back and Forward move between screens, and the in-app Back button does too', async () => {
    await mount()
    await click(button(t.ask))
    await click(button(t.back)) // in-app Back: one step back in the browser history
    await waitForHeading('ClimateGuard')
    expect(heading()).toBe('ClimateGuard')
    await click(button(t.history))
    expect(heading()).toBe(t.history)
    window.history.back() // the browser's Back button
    await waitForHeading('ClimateGuard')
    expect(heading()).toBe('ClimateGuard')
    window.history.forward()
    await waitForHeading(t.history)
    expect(heading()).toBe(t.history)
  })

  it('a screen opened directly (refresh, shared link) goes home with the in-app Back button', async () => {
    await mount('/#/history')
    await click(button(t.back))
    await waitForHeading('ClimateGuard')
    expect(heading()).toBe('ClimateGuard')
  })

  it('clicking the header brand returns to home', async () => {
    await mount()
    await click(button(t.ask))
    expect(heading()).toBe(t.ask)
    await click(button('ClimateGuard'))
    expect(heading()).toBe('ClimateGuard')
    expect(window.location.hash).toBe('#/')
  })

  it('demo mode survives a refresh, on the demo page and on a screen opened from it', async () => {
    await mount('/?demo=1')
    expect(heading()).toBe(t.demoTitle)
    await click(button(t.demoAskButton))
    expect(heading()).toBe(t.ask)
    expect(window.location.search).toBe('?demo=1')
    await remount(window.location.href)
    expect(heading()).toBe(t.ask)
    expect(container.textContent).toContain(t.demoSampleArea) // still the sample-area demo
    await click(button(t.back))
    await waitForHeading(t.demoTitle)
    expect(heading()).toBe(t.demoTitle)
    await click(button(t.demoExit))
    expect(heading()).toBe('ClimateGuard')
    expect(window.location.search).toBe('')
  })

  it('the language survives a refresh', async () => {
    await mount('/#/ask')
    const select = container.querySelector('.lang-select select')
    await act(async () => {
      select.value = 'vi'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(heading()).toBe(STRINGS.vi.ask)
    await remount(window.location.href)
    expect(heading()).toBe(STRINGS.vi.ask)
    expect(document.documentElement.lang).toBe('vi')
  })

  it('the How it works page lists the pipeline and loads sent decisions', async () => {
    await mount('/#/how-it-works')
    expect(heading()).toBe(t.howWorksTitle)
    expect(container.querySelectorAll('.how-steps > li')).toHaveLength(8)
    expect(container.textContent).toContain('Muse Spark Open')
    expect(container.textContent).toContain('SAM 3.1')
    expect(globalThis.fetch.mock.calls.some(([url]) => String(url).includes('/decisions?'))).toBe(true)
  })

  it('the footer and demo banner link to How it works', async () => {
    await mount()
    expect(container.querySelector('.app-footer a').getAttribute('href')).toBe('#/how-it-works')
    await remount('/?demo=1')
    expect(container.querySelector('.demo-note a').getAttribute('href')).toBe('#/how-it-works')
  })

  it('the How it works title and step names render in all seven languages', async () => {
    for (const code of ['en', 'es', 'vi', 'zh', 'tl', 'ko', 'ar']) {
      localStorage.setItem('lang', code)
      await remount('/#/how-it-works')
      expect(heading()).toBe(STRINGS[code].howWorksTitle)
      expect(container.querySelectorAll('.how-steps > li')).toHaveLength(8)
      if (['zh', 'tl', 'ko', 'ar'].includes(code)) {
        expect(container.textContent).toContain(STRINGS[code].autoUiNote)
      }
    }
  })

  it('the text-size toggle is accessible and persists the selected size', async () => {
    await mount()
    const toggle = () => container.querySelector('.text-size-toggle')
    expect(toggle().getAttribute('aria-pressed')).toBe('false')
    await click(toggle())
    expect(toggle().getAttribute('aria-pressed')).toBe('true')
    expect(document.documentElement.classList.contains('large-text')).toBe(true)
    await remount('/')
    expect(toggle().getAttribute('aria-pressed')).toBe('true')
    await click(toggle())
    expect(document.documentElement.classList.contains('large-text')).toBe(false)
  })

  it('demo cold starts show loading and failed requests can be retried', async () => {
    let rejectInitial
    const response = (body) => ({ ok: true, status: 200, json: () => Promise.resolve(body) })
    globalThis.fetch = vi.fn()
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectInitial = reject }))
      .mockResolvedValueOnce(response({ events: [{ event: 'heat_2022' }], over_budget: false }))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response({
        event: 'heat_2022', source: 'live',
        decision: { action: 'skipped', reason: 'No risk found.', model_calls: 1, cost_usd: 0.001 },
        alerts: [],
      }))

    await mount('/?demo=1')
    expect(container.querySelector('[role="status"]').textContent).toBe(t.loading)
    await act(async () => rejectInitial(new Error('cold start')))
    await settle()
    expect(container.textContent).toContain(t.errors.default)
    expect(button(t.retry)).toBeTruthy()
    await click(button(t.retry))
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)

    await click(button(t.demoEvents.heat_2022))
    expect(container.textContent).toContain(t.errors.network)
    expect(button(t.retry)).toBeTruthy()
    await click(button(t.retry))
    expect(globalThis.fetch).toHaveBeenCalledTimes(4)
    expect(container.textContent).toContain('No risk found.')
  })

  it('the recovery screen restarts at its first step on refresh instead of crashing', async () => {
    await mount('/#/recovery')
    expect(button(t.recCheck).disabled).toBe(true) // no photos yet
    expect(container.querySelector('.rec-disasters')).toBeTruthy() // the disaster picker, step one
  })
})
