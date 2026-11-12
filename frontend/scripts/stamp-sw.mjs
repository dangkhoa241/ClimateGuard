// Gives the built service worker a new identity on every deploy.
// public/sw.js is a static file: without this, a new deploy would ship the same bytes, the browser would keep the
// old service worker, and its cache would never be versioned. The build id is a hash of the built index.html, which
// names the hashed JS and CSS, so the id changes exactly when the app changes.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

export const PLACEHOLDER = '__BUILD_ID__'

export const buildIdFor = (indexHtml) => createHash('sha256').update(indexHtml).digest('hex').slice(0, 12)

export function stampServiceWorker(source, buildId) {
  if (!/^[a-z0-9]{6,40}$/.test(buildId)) throw new Error(`bad build id: ${buildId}`)
  return source.replaceAll(PLACEHOLDER, buildId)
}

// Vite plugin: after the bundle is written, stamp dist/sw.js. (The kill-switch file has no placeholder, so if it
// was swapped in as sw.js it is left exactly as it is.)
export function stampServiceWorkerPlugin() {
  let outDir = 'dist'
  return {
    name: 'climateguard-stamp-sw',
    apply: 'build',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      const sw = resolve(outDir, 'sw.js')
      const index = resolve(outDir, 'index.html')
      if (!existsSync(sw) || !existsSync(index)) return
      const source = readFileSync(sw, 'utf8')
      if (!source.includes(PLACEHOLDER)) return
      writeFileSync(sw, stampServiceWorker(source, buildIdFor(readFileSync(index, 'utf8'))))
    },
  }
}
