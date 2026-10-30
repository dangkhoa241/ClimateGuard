// Voice: record a spoken question as WAV (for Muse Voice Transcribe), and read text aloud with the
// phone's own voices (the Meta Model API has no text-to-speech model).
import { useEffect, useState } from 'react'

export const MAX_RECORD_MS = 55000 // the API side allows 60 s
const RATE = 16000 // the transcription API takes only mono 16-bit WAV at 16 or 24 kHz

export const canRecord = () =>
  typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

// Browsers record compressed audio (webm/opus, or mp4 on iPhone). Decode it, resample to 16 kHz mono
// in an OfflineAudioContext, and write a 16-bit PCM WAV.
async function toWav(blob) {
  const Ctx = window.AudioContext || window.webkitAudioContext
  const ctx = new Ctx()
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer())
    const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * RATE)), RATE)
    const src = offline.createBufferSource()
    src.buffer = decoded
    src.connect(offline.destination)
    src.start()
    const pcm = (await offline.startRendering()).getChannelData(0)
    const view = new DataView(new ArrayBuffer(44 + pcm.length * 2))
    const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)))
    text(0, 'RIFF'); view.setUint32(4, 36 + pcm.length * 2, true); text(8, 'WAVE')
    text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
    view.setUint32(24, RATE, true); view.setUint32(28, RATE * 2, true); view.setUint16(32, 2, true)
    view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, pcm.length * 2, true)
    pcm.forEach((v, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true))
    return new Blob([view], { type: 'audio/wav' })
  } finally {
    ctx.close()
  }
}

// Starts recording; resolves to { stop } where stop() resolves to the WAV blob. Stops by itself at
// MAX_RECORD_MS (onAutoStop is called). Rejects with 'mic_denied' when there's no microphone access.
export async function startRecording({ onAutoStop } = {}) {
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    throw new Error('mic_denied')
  }
  const rec = new MediaRecorder(stream)
  const chunks = []
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  const finished = new Promise((resolve) => {
    rec.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop())
      resolve(new Blob(chunks, { type: rec.mimeType }))
    }
  })
  rec.start()
  const timer = setTimeout(() => {
    if (rec.state === 'recording') {
      rec.stop()
      onAutoStop?.()
    }
  }, MAX_RECORD_MS)
  return {
    stop: async () => {
      clearTimeout(timer)
      if (rec.state === 'recording') rec.stop()
      return toWav(await finished)
    },
  }
}

// --- read aloud --------------------------------------------------------------

// BCP 47 prefixes per app language, best first; Tagalog voices are usually tagged Filipino ("fil-PH").
const VOICE_LANGS = { en: ['en-US', 'en'], es: ['es-US', 'es-MX', 'es'], vi: ['vi'], zh: ['zh-CN', 'zh'],
  tl: ['fil', 'tl'], ko: ['ko'], ar: ['ar'] }
const SPEECH_LANGS = { en: 'en-US', es: 'es-MX', vi: 'vi-VN', zh: 'zh-CN', tl: 'fil-PH', ko: 'ko-KR', ar: 'ar-SA' }
// Higher-quality voices by name: iOS "Enhanced"/"Premium" downloads, Edge's online "Natural" voices
// (e.g. "Microsoft HoaiMy Online (Natural) - Vietnamese (Vietnam)"), and a few known good ones.
const QUALITY = [[/natural|neural|premium/i, 3], [/enhanced|online/i, 2],
  [/hoaimy|namminh|\blinh\b|jenny|aria|samantha|paulina|m[oó]nica/i, 2], [/google/i, 1]]

export const isIOS = () =>
  typeof navigator !== 'undefined' &&
  (/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1))

function langRank(voice, lang) {
  const tag = voice.lang.replace('_', '-').toLowerCase()
  const i = (VOICE_LANGS[lang] || [lang]).findIndex((p) => tag.startsWith(p.toLowerCase()))
  return i < 0 ? null : i
}

const quality = (v) => QUALITY.reduce((sum, [rx, pts]) => sum + (rx.test(v.name) ? pts : 0), 0)

// The phone's voices for `lang`, best first (quality, then the closest regional variant).
export function voicesFor(all, lang) {
  return all
    .filter((v) => langRank(v, lang) !== null)
    .sort((a, b) => quality(b) - quality(a) || langRank(a, lang) - langRank(b, lang) || a.name.localeCompare(b.name))
}

export function speechLanguage(lang, voice) {
  const voiceLang = voice?.lang?.replace('_', '-')
  const prefix = lang === 'tl' ? /^(fil|tl)(-|$)/i : new RegExp(`^${lang}(-|$)`, 'i')
  return voiceLang && voiceLang.includes('-') && prefix.test(voiceLang)
    ? voiceLang
    : (SPEECH_LANGS[lang] || 'en-US')
}

const storeKey = (lang) => `cg-voice-${lang}`
export function savedVoiceURI(lang) {
  try { return localStorage.getItem(storeKey(lang)) } catch { return null }
}
export function saveVoiceURI(lang, uri) {
  try { localStorage.setItem(storeKey(lang), uri) } catch { /* private mode: just not remembered */ }
}

// Voices for `lang` (best first). They load asynchronously: Chrome and Edge fire voiceschanged (Edge's
// online voices arrive late); iOS Safari may return none at first without an event, so retry briefly.
export function useVoices(lang) {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined
  const [voices, setVoices] = useState(() => (synth ? voicesFor(synth.getVoices(), lang) : []))
  useEffect(() => {
    if (!synth) return undefined
    const update = () => setVoices(voicesFor(synth.getVoices(), lang))
    update()
    synth.addEventListener?.('voiceschanged', update)
    const retries = [250, 1000, 3000].map((ms) => setTimeout(update, ms))
    return () => {
      synth.removeEventListener?.('voiceschanged', update)
      retries.forEach(clearTimeout)
    }
  }, [synth, lang])
  return voices
}

// Short chunks: Chrome stops long utterances after ~15 s, and sentence by sentence sounds more natural.
export function chunks(text) {
  return text
    .split(/(?<=[.!?。！？؟])\s+|\n+/)
    .flatMap((s) => (s.length > 200 ? s.split(/(?<=[,;，、])\s*/) : [s]))
    .map((s) => s.trim())
    .filter(Boolean)
}

// Must run directly in the tap handler (iOS only speaks from a user gesture), so every chunk is queued
// right away. cancel() only when something is playing: on iOS, cancel() then speak() can drop the speech.
export function speak(text, voice, { onEnd, lang = 'en' } = {}) {
  const synth = window.speechSynthesis
  if (synth.speaking || synth.pending) synth.cancel()
  const parts = chunks(text)
  let done = false
  const finish = () => {
    if (!done) {
      done = true
      onEnd?.()
    }
  }
  parts.forEach((part, i) => {
    const u = new SpeechSynthesisUtterance(part)
    u.voice = voice
    u.lang = speechLanguage(lang, voice)
    u.rate = 0.95 // a little slower than default: plain, clear speech
    u.onerror = finish
    if (i === parts.length - 1) u.onend = finish
    synth.speak(u)
  })
}

export const stopSpeaking = () => window.speechSynthesis?.cancel()
