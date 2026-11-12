// ClimateGuard service worker KILL SWITCH. Not used in normal operation.
//
// To switch the service worker off for everyone (one step, then deploy):
//     copy this file over sw.js      PowerShell:  Copy-Item frontend/public/sw-kill.js frontend/public/sw.js -Force
// Browsers re-check /sw.js on every visit. They find this file, install it, and it deletes every cache and
// unregisters itself. It has no fetch handler, so the site loads straight from the network from then on.
// Unregistering also ends this device's phone notifications (the server forgets it on its next push).
// To bring the service worker back: restore sw.js from git (git checkout <commit> -- frontend/public/sw.js) and deploy.
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) await caches.delete(key)
    await self.registration.unregister()
    // No reload here: open pages keep working, and their next load comes from the network.
  })())
})
