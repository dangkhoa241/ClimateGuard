// public/sw.js against fake service worker globals. Checks the promise in its header: only the app shell and static
// files are cached, API traffic and every non-GET request are never touched, and push notifications behave.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const SOURCE = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
const ORIGIN = 'https://app.example'

function loadWorker({ online = true, pages = {} } = {}) {
  const handlers = {}
  const store = new Map() // cache: url -> response
  const cache = {
    put: async (req, res) => store.set(typeof req === 'string' ? new URL(req, ORIGIN).href : req.url, res),
    add: async (url) => { if (!online) throw new Error('offline'); store.set(new URL(url, ORIGIN).href, { ok: true, url }) },
  }
  const caches = {
    open: async () => cache,
    keys: async () => ['old-cache', 'cg-shell-v1'],
    delete: async (k) => { deleted.push(k) },
    match: async (req) => store.get(typeof req === 'string' ? new URL(req, ORIGIN).href : req.url),
  }
  const deleted = []
  const fetched = []
  const shown = []
  const opened = []
  const fetchFn = async (req) => {
    const url = typeof req === 'string' ? new URL(req, ORIGIN).href : req.url
    fetched.push(url)
    if (!online) throw new Error('offline')
    const body = pages[new URL(url).pathname] ?? ''
    return { ok: true, url, clone() { return this }, text: async () => body }
  }
  const clientsList = []
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type, fn) => { handlers[type] = fn },
    registration: { showNotification: async (title, opts) => { shown.push({ title, opts }) } },
    clients: { claim: async () => {}, matchAll: async () => clientsList, openWindow: async (u) => { opened.push(u) } },
  }
  new Function('self', 'caches', 'fetch', 'Response', SOURCE)(self, caches, fetchFn, { error: () => 'error-response' })
  const waits = []
  const dispatch = (type, event) => { handlers[type]({ waitUntil: (p) => waits.push(p), ...event }); return Promise.all(waits) }
  return { dispatch, store, fetched, shown, opened, deleted, clientsList, handlers }
}

const req = (url, method = 'GET', mode = 'cors') => ({ url, method, mode })
async function fetchEvent(w, request) {
  let responded
  w.handlers.fetch({ request, respondWith: (p) => { responded = p } })
  return responded === undefined ? undefined : await responded
}

test('install caches the page and the hashed assets it names, then the static files', async () => {
  const w = loadWorker({ pages: { '/': '<script src="/assets/index-abc.js"></script><link href="/assets/index-def.css">' } })
  await w.dispatch('install', {})
  const urls = [...w.store.keys()]
  for (const want of ['/', '/assets/index-abc.js', '/assets/index-def.css', '/manifest.webmanifest', '/icon-192.png'])
    assert.ok(urls.includes(ORIGIN + want), `missing ${want}`)
})

test('activate removes old caches', async () => {
  const w = loadWorker()
  await w.dispatch('activate', {})
  assert.deepEqual(w.deleted, ['old-cache'])
})

test('API calls, sign-ups, uploads and any cross-origin request are never intercepted', async () => {
  const w = loadWorker()
  const api = 'https://abc123.execute-api.us-east-2.amazonaws.com'
  for (const r of [
    req(`${api}/zones/CAZ159/alerts`), req(`${api}/subscribe`, 'POST'), req(`${api}/recovery/x/photos?i=0`, 'POST'),
    req(`${api}/push/subscribe`, 'POST'), req(`${ORIGIN}/subscribe`, 'POST'), req(`${ORIGIN}/assets/a.js`, 'POST'),
    req(`${ORIGIN}/assets/a.js`, 'DELETE'),
  ]) assert.equal(await fetchEvent(w, r), undefined, `${r.method} ${r.url} must pass through`)
  assert.equal(w.store.size, 0)
  assert.deepEqual(w.fetched, [])
})

test('same-origin paths outside the allow-list are not cached (even API-looking ones)', async () => {
  const w = loadWorker()
  for (const p of ['/zones/CAZ159', '/api/alerts', '/locate?zip=95202', '/assets/', '/assets/a/b.js', '/sw.js', '/data.json'])
    assert.equal(await fetchEvent(w, req(ORIGIN + p)), undefined, p)
  assert.equal(w.store.size, 0)
})

test('static assets are cached on first use and served from the cache after', async () => {
  const w = loadWorker()
  await fetchEvent(w, req(`${ORIGIN}/assets/index-abc.js`))
  assert.ok(w.store.has(`${ORIGIN}/assets/index-abc.js`))
  const before = w.fetched.length
  await fetchEvent(w, req(`${ORIGIN}/assets/index-abc.js`))
  assert.equal(w.fetched.length, before)
})

test('navigation falls back to the cached shell when offline', async () => {
  const w = loadWorker({ online: false })
  w.store.set(`${ORIGIN}/`, { ok: true, shell: true })
  const res = await fetchEvent(w, req(`${ORIGIN}/?zone=CAZ159&lang=es`, 'GET', 'navigate'))
  assert.equal(res.shell, true)
})

function pushEvent(payload) {
  return { data: { json: () => payload } }
}

test('push shows the notification with title, body, tag, language and direction', async () => {
  const w = loadWorker()
  await w.dispatch('push', pushEvent({ title: 'T', body: 'B', url: `${ORIGIN}/?zone=CAZ159&lang=ar`, tag: 'CAZ159-heat', lang: 'ar' }))
  assert.equal(w.shown.length, 1)
  const { title, opts } = w.shown[0]
  assert.equal(title, 'T')
  assert.equal(opts.body, 'B')
  assert.equal(opts.tag, 'CAZ159-heat')
  assert.equal(opts.dir, 'rtl')
  assert.equal(opts.data.url, `${ORIGIN}/?zone=CAZ159&lang=ar`)
})

test('push with a broken payload still shows a notification (browsers require one)', async () => {
  const w = loadWorker()
  await w.dispatch('push', { data: { json: () => { throw new Error('bad json') } } })
  assert.equal(w.shown[0].title, 'ClimateGuard')
})

const click = (url) => ({ notification: { close() {}, data: { url } } })

test('tapping a notification opens the alert link in a new window when the app is closed', async () => {
  const w = loadWorker()
  await w.dispatch('notificationclick', click(`${ORIGIN}/?zone=CAZ159&lang=es`))
  assert.deepEqual(w.opened, [`${ORIGIN}/?zone=CAZ159&lang=es`])
})

test('tapping navigates and focuses an open ClimateGuard window', async () => {
  const w = loadWorker()
  const calls = []
  w.clientsList.push({ url: `${ORIGIN}/#/ask`, navigate: async (u) => calls.push(['navigate', u]), focus: async () => calls.push(['focus']) })
  await w.dispatch('notificationclick', click(`${ORIGIN}/?zone=CAZ159&lang=vi`))
  assert.deepEqual(calls, [['navigate', `${ORIGIN}/?zone=CAZ159&lang=vi`], ['focus']])
  assert.deepEqual(w.opened, [])
})

test('a notification can never open another origin', async () => {
  const w = loadWorker()
  await w.dispatch('notificationclick', click('https://evil.example/phish'))
  assert.deepEqual(w.opened, [`${ORIGIN}/`])
})
