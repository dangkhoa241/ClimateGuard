// ClimateGuard service worker.
// - Caches ONLY the app shell and static assets (same-origin GET). It never sees API traffic: the API is on another
//   origin, and every request that is not on the allow-list below is left alone for the browser to handle.
//   Sign-ups, photo uploads, damage reports and every other API response are never cached.
// - Shows web push notifications and opens the matching alert page when one is tapped.
const CACHE = 'cg-shell-v1'
const SHELL = ['/', '/manifest.webmanifest', '/favicon.svg', '/favicon.ico', '/apple-touch-icon.png',
  '/icon-192.png', '/icon-512.png', '/icon-maskable-192.png', '/icon-maskable-512.png']
// Static files only: hashed build assets and the icon and manifest files.
const STATIC_RE = /^\/(assets\/[^/]+|icon-[\w-]+\.png|favicon\.(svg|ico)|apple-touch-icon\.png|manifest\.webmanifest)$/

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE)
    // The page itself, then the hashed JS/CSS it names, so the shell works offline on the very first visit.
    const page = await fetch('/', { cache: 'reload' })
    const html = await page.clone().text()
    await cache.put('/', page)
    const assets = [...new Set(html.match(/\/assets\/[^"'\s)]+/g) || [])]
    await Promise.all([...SHELL.slice(1), ...assets].map((url) => cache.add(url).catch(() => {})))
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key)
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return // the API, push services, anything cross-origin

  if (req.mode === 'navigate') {
    // Network first, so a new version arrives as soon as there is a connection; offline, the cached shell.
    event.respondWith((async () => {
      try {
        const res = await fetch(req)
        if (res.ok && url.pathname === '/') (await caches.open(CACHE)).put('/', res.clone())
        return res
      } catch {
        return (await caches.match('/')) || Response.error()
      }
    })())
    return
  }
  if (!STATIC_RE.test(url.pathname)) return // not on the allow-list: never cached

  event.respondWith((async () => {
    const hit = await caches.match(req)
    if (hit) return hit
    const res = await fetch(req)
    if (res.ok) (await caches.open(CACHE)).put(req, res.clone())
    return res
  })())
})

// Payload: {title, body, url, tag, lang}. userVisibleOnly: every push must show a notification.
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = {}
  }
  const lang = typeof data.lang === 'string' ? data.lang : undefined
  event.waitUntil(self.registration.showNotification(String(data.title || 'ClimateGuard'), {
    body: String(data.body || ''),
    tag: data.tag ? String(data.tag) : undefined,
    lang,
    dir: lang === 'ar' ? 'rtl' : 'ltr',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: typeof data.url === 'string' ? data.url : '/' },
  }))
})

// Opens only our own pages; the alert link carries ?zone=...&lang=..., so it lands in the person's language.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  let target = new URL('/', self.location.origin)
  try {
    const wanted = new URL(event.notification.data?.url || '/', self.location.origin)
    if (wanted.origin === self.location.origin) target = wanted
  } catch {
    // keep the home page
  }
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const mine = windows.find((w) => new URL(w.url).origin === self.location.origin)
    if (mine) {
      try {
        await mine.navigate(target.href)
      } catch {
        // some browsers refuse navigate(); fall through to focus
      }
      return mine.focus()
    }
    return self.clients.openWindow(target.href)
  })())
})
