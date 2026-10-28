import { useEffect, useState } from 'react'
import { isIOS, savedVoiceURI, saveVoiceURI, speak, stopSpeaking, useVoices } from './voice.js'

const shortName = (v) => v.name.replace(/^Microsoft\s+/, '').replace(/\s+-\s+.*$/, '')

// "Read aloud" with the phone's own voice. Hidden when the phone has no voice for the language
// (often true for Vietnamese or Tagalog on desktop browsers): no button beats a wrong-language voice.
// `options`: show the voice picker and the iPhone voice tip (on the Ask answer, not on every alert card).
export default function ReadAloud({ text, lang, t, options = false }) {
  const voices = useVoices(lang)
  const [uri, setUri] = useState(() => savedVoiceURI(lang))
  const [speaking, setSpeaking] = useState(false)
  // Websites can't detect the iPhone silent switch, which mutes speech: say so when reading starts.
  const [silentHint, setSilentHint] = useState(false)
  useEffect(() => () => stopSpeaking(), []) // leaving the screen stops reading
  useEffect(() => setUri(savedVoiceURI(lang)), [lang])
  useEffect(() => {
    stopSpeaking()
    setSpeaking(false)
    setSilentHint(false)
  }, [text])
  const voice = voices.find((v) => v.voiceURI === uri) || voices[0]
  if (!voice || !text) return null

  function toggle() {
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
      setSilentHint(false)
      return
    }
    setSpeaking(true)
    setSilentHint(isIOS())
    speak(text, voice, { onEnd: () => setSpeaking(false) })
  }

  function choose(e) {
    setUri(e.target.value)
    saveVoiceURI(lang, e.target.value)
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
    }
  }

  const goodVoice = /enhanced|premium/i.test(voice.name)
  return (
    <div className="read-aloud-row">
      <div className="read-aloud-controls">
        <button type="button" className="read-aloud" onClick={toggle} aria-pressed={speaking}>
          <span aria-hidden="true">{speaking ? '■' : '🔊'}</span> {speaking ? t.stopReading : t.readAloud}
        </button>
        {options && voices.length > 1 && (
          <select className="voice-picker" value={voice.voiceURI} onChange={choose} aria-label={t.voiceLabel}>
            {voices.map((v) => (
              <option key={v.voiceURI} value={v.voiceURI}>{shortName(v)}</option>
            ))}
          </select>
        )}
      </div>
      {silentHint && <p className="muted small">{t.silentHint}</p>}
      {options && isIOS() && !goodVoice && <p className="muted small">{t.enhancedVoiceTip}</p>}
    </div>
  )
}
