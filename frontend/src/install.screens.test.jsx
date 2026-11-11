// Install screen: the Android/Chrome install button, the iPhone Add to Home Screen steps, and the installed state.
// Also checks the manifest and icon files. Offline: nothing here uses the network.
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { STRINGS } from './i18n.js'
import { initInstallPrompt } from './pwa.js'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const t = STRINGS.en
let container, root

const setUa = (ua, standalone = false) => {
  Object.defineProperty(window.navigator, 'userAgent', { configurable: true, value: ua })
  window.matchMedia = vi.fn(() => ({ matches: standalone }))
}

beforeEach(() => {
  window.history.replaceState(null, '', '/#/install')
  window.scrollTo = () => {}
  globalThis.fetch = vi.fn(() => Promise.reject(new Error('install screen must not use the network')))
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('install screen', () => {
  it('shows the Add to Home Screen steps on iPhone', async () => {
    setUa('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1')
    await act(async () => root.render(<App />))
    expect(container.textContent).toContain(t.installIos3)
    expect(container.textContent).toContain(t.installIos4)
    expect(container.textContent).not.toContain(t.installAndroid)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('shows an Install button when the browser offers the install prompt', async () => {
    setUa('Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537.36')
    initInstallPrompt()
    const prompt = vi.fn(() => Promise.resolve())
    const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }),
      { prompt, userChoice: Promise.resolve({ outcome: 'accepted' }) })
    window.dispatchEvent(event)
    await act(async () => root.render(<App />))
    const button = [...container.querySelectorAll('button')].find((b) => b.textContent === t.installButton)
    expect(button).toBeTruthy()
    await act(async () => button.click())
    expect(prompt).toHaveBeenCalled()
  })

  it('says it is installed when already running as an app', async () => {
    setUa('Mozilla/5.0 (Linux; Android 14) Chrome/120', true)
    await act(async () => root.render(<App />))
    expect(container.textContent).toContain(t.installDone)
  })

  it('mentions notifications on the iPhone steps only behind ?push=1', async () => {
    setUa('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1')
    sessionStorage.clear()
    await act(async () => root.render(<App />))
    expect(container.textContent).not.toContain(t.installPushNote)
    act(() => root.unmount())
    window.history.replaceState(null, '', '/?push=1#/install')
    root = createRoot(container)
    await act(async () => root.render(<App />))
    expect(container.textContent).toContain(t.installPushNote)
  })
})

describe('manifest', () => {
  const manifest = JSON.parse(readFileSync(resolve(process.cwd(), 'public/manifest.webmanifest'), 'utf8'))
  it('is installable: standalone, theme colors, 192 and 512 icons, and maskable icons', () => {
    expect(manifest.display).toBe('standalone')
    expect(manifest.theme_color).toBe('#C2410C')
    const sizes = manifest.icons.map((i) => `${i.sizes}:${i.purpose}`)
    for (const want of ['192x192:any', '512x512:any', '192x192:maskable', '512x512:maskable']) expect(sizes).toContain(want)
  })
  it('points only at icon files that exist', () => {
    for (const icon of manifest.icons) expect(existsSync(resolve(process.cwd(), `public${icon.src}`))).toBe(true)
  })
})
