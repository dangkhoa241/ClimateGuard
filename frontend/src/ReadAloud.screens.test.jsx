import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import ReadAloud from './ReadAloud.jsx'
import { speechLanguage } from './voice.js'
import { STRINGS } from './i18n.js'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let root
let container

afterEach(() => {
  if (root) act(() => root.unmount())
  container?.remove()
  root = null
  container = null
  delete window.speechSynthesis
})

describe('read aloud locale handling', () => {
  it('sets the utterance language from the alert language and matching device voice', async () => {
    let spoken
    const voice = { voiceURI: 'es-US', name: 'Spanish', lang: 'es-US' }
    window.speechSynthesis = {
      speaking: false, pending: false, getVoices: () => [voice],
      addEventListener() {}, removeEventListener() {}, cancel() {},
      speak: (utterance) => { spoken = utterance },
    }
    globalThis.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text }
    }
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await act(async () => root.render(<ReadAloud text="Hola." lang="es" t={STRINGS.es} />))
    await act(async () => container.querySelector('button').click())

    expect(spoken.lang).toBe('es-US')
    expect(speechLanguage('vi', { lang: 'vi' })).toBe('vi-VN')
  })

  it('shows a message instead of offering English speech when the device has no matching voice', async () => {
    window.speechSynthesis = {
      getVoices: () => [],
      addEventListener() {},
      removeEventListener() {},
      cancel() {},
    }
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await act(async () => root.render(<ReadAloud text="Xin chào." lang="vi" t={STRINGS.vi} />))

    expect(container.textContent).toContain(STRINGS.vi.voiceUnavailable)
    expect(container.querySelector('button')).toBeNull()
  })
})
