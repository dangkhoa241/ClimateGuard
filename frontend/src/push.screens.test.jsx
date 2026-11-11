// "Turn on phone notifications": hidden without ?push=1, every state it can be in, no email involved, demo mode
// never subscribes, and turning it off. Offline: fetch, the service worker and the browser push API are fakes.
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

const ZONE = { zone: 'CAZ159', name: 'Central San Joaquin County', place: 'Stockton, CA', state: 'CA',
  tz: 'America/Los_Angeles', monitored: false }
const PUBLIC_KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'
const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/abc'
const t = STRINGS.en
let container, root, browserSub, pushManager, fetchMock

const json = (status, body) => ({ ok: status < 400, status, json: () => Promise.resolve(body) })
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 15)) })
const button = (text) => [...container.querySelectorAll('button')].find((b) => b.textContent.includes(text))
const type = async (selector, value) => {
  const input = container.querySelector(selector)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

function fakePush({ permission = 'default', answer = 'granted', existing = null } = {}) {
  browserSub = existing
  const make = () => ({ endpoint: ENDPOINT, toJSON: () => ({ endpoint: ENDPOINT, keys: { p256dh: 'P', auth: 'A' } }),
    unsubscribe: vi.fn(() => Promise.resolve(true)) })
  pushManager = {
    getSubscription: vi.fn(() => Promise.resolve(browserSub)),
    subscribe: vi.fn(() => { browserSub = make(); return Promise.resolve(browserSub) }),
  }
  Object.defineProperty(window.navigator, 'serviceWorker', { configurable: true,
    value: { ready: Promise.resolve({ pushManager }) } })
  window.PushManager = function PushManager() {}
  window.Notification = { permission, requestPermission: vi.fn(() => Promise.resolve(answer)) }
}

const setUa = (ua, standalone = false) => {
  Object.defineProperty(window.navigator, 'userAgent', { configurable: true, value: ua })
  window.matchMedia = vi.fn(() => ({ matches: standalone }))
}
const ANDROID = 'Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537.36'
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1'

function routes({ subscribe = json(201, { status: 'subscribed', zone: 'CAZ159', place: 'Stockton, CA' }) } = {}) {
  fetchMock = vi.fn((url, options) => {
    const path = String(url)
    if (path.includes('/locate')) return Promise.resolve(json(200, ZONE))
    if (path.endsWith('/push/subscribe')) return typeof subscribe === 'function' ? subscribe(options) : Promise.resolve(subscribe)
    if (path.endsWith('/push/unsubscribe')) return Promise.resolve(json(200, { status: 'unsubscribed' }))
    return Promise.resolve(json(200, []))
  })
  globalThis.fetch = fetchMock
}
const pushCalls = () => fetchMock.mock.calls.filter(([url]) => String(url).includes('/push/'))

async function open({ url = '/?push=1#/alerts', locate = true } = {}) {
  window.history.replaceState(null, '', url)
  await act(async () => root.render(<App />))
  if (locate) {
    await type('#zip', '95202')
    await act(async () => container.querySelector('.zip-row').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
    await settle()
  }
}

beforeEach(() => {
  memory.clear()
  sessionStorage.clear()
  vi.stubEnv('VITE_VAPID_PUBLIC_KEY', PUBLIC_KEY)
  setUa(ANDROID)
  window.scrollTo = () => {}
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  fakePush()
  routes()
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.unstubAllEnvs()
})

describe('feature flag', () => {
  it('is hidden without ?push=1', async () => {
    await open({ url: '/#/alerts' })
    expect(container.querySelector('.push-signup')).toBeNull()
    expect(container.textContent).not.toContain(t.pushButton)
  })

  it('shows with ?push=1 and stays on for the rest of the tab session', async () => {
    await open()
    expect(container.querySelector('.push-signup')).not.toBeNull()
    act(() => root.unmount())
    root = createRoot(container)
    await open({ url: '/#/alerts', locate: false })
    expect(container.querySelector('.push-signup')).not.toBeNull()
  })
})

describe('turning notifications on', () => {
  it('asks permission on the tap, subscribes with the public key, and sends no email', async () => {
    await open()
    expect(container.querySelector('#push-lang')).not.toBeNull()
    expect(container.querySelector('.push-signup input[type="email"]')).toBeNull()
    expect(window.Notification.requestPermission).not.toHaveBeenCalled() // never on page load
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(window.Notification.requestPermission).toHaveBeenCalledTimes(1)
    const options = pushManager.subscribe.mock.calls[0][0]
    expect(options.userVisibleOnly).toBe(true)
    expect(options.applicationServerKey).toBeInstanceOf(Uint8Array)
    expect(options.applicationServerKey.length).toBe(65)
    const [[url, init]] = pushCalls()
    expect(String(url)).toMatch(/\/push\/subscribe$/)
    const body = JSON.parse(init.body)
    expect(body).toMatchObject({ lang: 'en', zip: '95202', website: '',
      subscription: { endpoint: ENDPOINT, keys: { p256dh: 'P', auth: 'A' } } })
    expect(Object.keys(body)).not.toContain('email')
    expect(container.querySelector('.push-signup .success').textContent)
      .toBe(t.pushOn.replace('{place}', 'Stockton, CA').replace('{language}', 'English') + t.pushTurnOff)
    expect(JSON.parse(memory.get('pushSub'))).toMatchObject({ zone: 'CAZ159', lang: 'en' })
  })

  it('sends the chosen language, which can differ from the app language', async () => {
    await open()
    const select = container.querySelector('#push-lang')
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'es')
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(JSON.parse(pushCalls()[0][1].body).lang).toBe('es')
  })

  it('is disabled until an area is chosen', async () => {
    await open({ locate: false })
    expect(button(t.pushButton).disabled).toBe(true)
    expect(container.textContent).toContain(t.pushStepPlace)
  })

  it('is disabled, with a note, when no public key is configured', async () => {
    vi.stubEnv('VITE_VAPID_PUBLIC_KEY', '')
    await open()
    expect(button(t.pushButton).disabled).toBe(true)
    expect(container.textContent).toContain(t.pushNoKey)
  })

  it('says how to fix a blocked permission and subscribes to nothing', async () => {
    fakePush({ answer: 'denied' })
    await open()
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(container.querySelector('.push-signup [role="alert"]').textContent).toContain(t.pushDenied)
    expect(pushManager.subscribe).not.toHaveBeenCalled()
    expect(pushCalls()).toHaveLength(0)
  })

  it('rolls the browser subscription back when the server refuses', async () => {
    routes({ subscribe: json(503, { error: 'subscriber_cap' }) })
    await open()
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(browserSub.unsubscribe).toHaveBeenCalled()
    expect(container.querySelector('.push-signup [role="alert"]').textContent).toBe(t.errors.subscriber_cap)
    expect(memory.get('pushSub')).toBeUndefined()
    expect(button(t.pushButton)).toBeTruthy() // can try again
  })

  it('shows the rate limit message', async () => {
    routes({ subscribe: json(429, { error: 'rate_limited' }) })
    await open()
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(container.querySelector('.push-signup [role="alert"]').textContent).toBe(t.errors.rate_limited)
  })
})

describe('unsupported and iPhone', () => {
  it('explains when the browser has no push support', async () => {
    delete window.PushManager
    await open()
    expect(container.querySelector('.push-signup').textContent).toContain(t.pushUnsupported)
    expect(button(t.pushButton)).toBeUndefined()
  })

  it('on iPhone in a browser tab, asks to install first and links to the install steps', async () => {
    setUa(IPHONE, false)
    await open()
    const section = container.querySelector('.push-signup')
    expect(section.textContent).toContain(t.pushNeedInstall)
    expect(section.querySelector('a[href="#/install"]')).not.toBeNull()
    expect(button(t.pushButton)).toBeUndefined()
    expect(window.Notification.requestPermission).not.toHaveBeenCalled()
  })

  it('on iPhone as an installed app, the button works', async () => {
    setUa(IPHONE, true)
    await open()
    await act(async () => button(t.pushButton).click())
    await settle()
    expect(pushManager.subscribe).toHaveBeenCalled()
    expect(container.querySelector('.push-signup .success')).not.toBeNull()
  })
})

describe('turning notifications off', () => {
  async function turnedOn() {
    await open()
    await act(async () => button(t.pushButton).click())
    await settle()
  }

  it('sends the endpoint itself, removes the browser subscription and the saved record', async () => {
    await turnedOn()
    const sub = browserSub
    await act(async () => button(t.pushTurnOff).click())
    await settle()
    const unsub = pushCalls().find(([url]) => String(url).endsWith('/push/unsubscribe'))
    expect(JSON.parse(unsub[1].body)).toEqual({ endpoint: ENDPOINT })
    expect(sub.unsubscribe).toHaveBeenCalled()
    expect(memory.get('pushSub')).toBeUndefined()
    expect(button(t.pushButton)).toBeTruthy()
  })

  it('still turns off on the phone when the server cannot be reached', async () => {
    await turnedOn()
    const sub = browserSub
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('offline')))
    await act(async () => button(t.pushTurnOff).click())
    await settle()
    expect(sub.unsubscribe).toHaveBeenCalled()
    expect(button(t.pushButton)).toBeTruthy()
  })

  it('shows "on" again after a reload when this phone is already subscribed', async () => {
    memory.set('pushSub', JSON.stringify({ zone: 'CAZ159', place: 'Stockton, CA', lang: 'vi' }))
    fakePush({ existing: { endpoint: ENDPOINT, unsubscribe: vi.fn() } })
    await open({ locate: false })
    await settle()
    expect(container.querySelector('.push-signup .success').textContent).toContain('Tiếng Việt')
  })
})

describe('demo mode', () => {
  it('never subscribes, never calls the push routes, and says so', async () => {
    await open({ url: '/?demo=1&push=1#/alerts', locate: false })
    const section = container.querySelector('.push-signup')
    expect(section.textContent).toContain(t.pushDemoNote)
    expect(section.querySelector('button')).toBeNull()
    expect(window.Notification.requestPermission).not.toHaveBeenCalled()
    expect(pushManager.subscribe).not.toHaveBeenCalled()
    expect(pushManager.getSubscription).not.toHaveBeenCalled()
    expect(pushCalls()).toHaveLength(0)
  })

  it('the API client itself refuses in demo mode, even if the screen were bypassed', async () => {
    window.history.replaceState(null, '', '/?demo=1&push=1')
    const { subscribePush, unsubscribePush } = await import('./api.js')
    await expect(subscribePush({ subscription: {}, lang: 'en', location: { zip: '95202' } })).rejects.toMatchObject({ code: 'demo_mode' })
    await expect(unsubscribePush(ENDPOINT)).rejects.toMatchObject({ code: 'demo_mode' })
    const { enablePush } = await import('./push.js')
    await expect(enablePush({ lang: 'en', location: { zip: '95202' } })).rejects.toMatchObject({ code: 'demo_mode' })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(pushManager.subscribe).not.toHaveBeenCalled()
  })
})

describe('languages', () => {
  it('renders in Arabic (right to left) and uses that language for the section', async () => {
    memory.set('lang', 'ar')
    await open()
    expect(document.documentElement.dir).toBe('rtl')
    expect(container.querySelector('.push-signup h2').textContent).toBe(STRINGS.ar.pushTitle)
    expect(container.querySelector('#push-lang').value).toBe('ar')
  })
})
