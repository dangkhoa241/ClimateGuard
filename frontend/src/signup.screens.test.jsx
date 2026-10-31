// Sign-up errors on the Alerts screen: each failure says something specific (not "Something went wrong"),
// in every language, and the retry button sends the sign-up again. Offline: fetch is stubbed.
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

const ZONE = { zone: 'CAZ159', name: 'Central San Joaquin County', place: 'Stockton, CA', state: 'CA', tz: 'America/Los_Angeles',
  monitored: false }
const t = STRINGS.en
let container, root

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', '/#/alerts')
  window.scrollTo = () => Promise.resolve()
  window.HTMLElement.prototype.scrollIntoView = () => Promise.resolve()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 15)) })
const button = (text) => [...container.querySelectorAll('button')].find((b) => b.textContent.includes(text))
const type = async (selector, value) => {
  const input = container.querySelector(selector)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const json = (status, body) => ({ ok: status < 400, status, json: () => Promise.resolve(body) })

// `subscribeAnswers`: what each POST /subscribe returns, in order (a function throws, like a network failure)
async function openSignup(subscribeAnswers) {
  const answers = [...subscribeAnswers]
  globalThis.fetch = vi.fn((url) => {
    const path = String(url)
    if (path.includes('/locate')) return Promise.resolve(json(200, ZONE))
    if (path.endsWith('/subscribe')) {
      const next = answers.shift() ?? json(202, { status: 'pending_confirmation' })
      return typeof next === 'function' ? Promise.reject(next()) : Promise.resolve(next)
    }
    return Promise.resolve(json(200, []))
  })
  await act(async () => root.render(<App />))
  await type('#zip', '95202')
  await act(async () => container.querySelector('.zip-row').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  await settle()
  await type('#email', 'maria@example.com')
}
const submit = async () => {
  await act(async () => container.querySelector('form.signup').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  await settle()
}
const alertText = () => container.querySelector('form.signup [role="alert"]')?.textContent || ''
const posts = () => globalThis.fetch.mock.calls.filter(([url]) => String(url).endsWith('/subscribe'))

describe('sign-up errors', () => {
  it('sends the email, language, ZIP and an empty honeypot', async () => {
    await openSignup([])
    await submit()
    const [[, options]] = posts()
    expect(JSON.parse(options.body)).toEqual({ email: 'maria@example.com', lang: 'en', website: '', zip: '95202' })
    expect(container.textContent).toContain(t.checkEmailTitle)
  })

  it.each([
    ['rate limited by our API', json(429, { error: 'rate_limited' }), 'Too many attempts. Please try again in a few minutes.'],
    ['throttled by API Gateway (no error code of ours)', json(429, { message: 'Too Many Requests' }), 'Too many attempts. Please try again in a few minutes.'],
    ['invalid email', json(400, { error: 'invalid_email' }), 'Please check your email address.'],
    ['the daily sign-up limit', json(503, { error: 'busy' }), 'The service is busy. Please try again later.'],
    ['a crashed Lambda (API Gateway 500)', json(500, { message: 'Internal Server Error' }), 'The service is busy. Please try again later.'],
    ['a network failure', () => new TypeError('Failed to fetch'), 'Check your connection and try again.'],
  ])('%s shows a specific message and a retry button', async (_name, answer, message) => {
    await openSignup([answer])
    await submit()
    expect(alertText()).toContain(message)
    expect(alertText()).not.toContain(t.errors.default)
    expect(button(t.retry)).toBeTruthy()
  })

  it('the retry button sends the sign-up again', async () => {
    await openSignup([json(500, { message: 'Internal Server Error' })])
    await submit()
    expect(posts()).toHaveLength(1)
    await act(async () => button(t.retry).dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await settle()
    expect(posts()).toHaveLength(2)
    expect(container.textContent).toContain(t.checkEmailTitle)
  })
})

describe('the four sign-up messages exist in all seven languages', () => {
  it.each(['en', 'es', 'vi', 'zh', 'tl', 'ko', 'ar'])('%s', (code) => {
    const { errors } = STRINGS[code]
    for (const key of ['rate_limited', 'busy', 'over_budget', 'network', 'invalid_email']) {
      expect(errors[key], `${code}.${key}`).toBeTruthy()
      expect(errors[key]).not.toBe(errors.default)
    }
    if (code !== 'en') {
      expect(errors.rate_limited).not.toBe(STRINGS.en.errors.rate_limited)
      expect(errors.busy).not.toBe(STRINGS.en.errors.busy)
      expect(errors.network).not.toBe(STRINGS.en.errors.network)
    }
    expect(errors.busy).toBe(errors.over_budget) // the daily spend cap and a busy server read the same
  })
})
