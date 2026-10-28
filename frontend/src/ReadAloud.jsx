import { useEffect, useState } from 'react'
import { speak, stopSpeaking, useVoice } from './voice.js'

// "Read aloud" with the phone's own voice. Hidden when the phone has no voice for the language
// (often true for Vietnamese or Tagalog on desktop browsers): no button beats a wrong-language voice.
export default function ReadAloud({ text, lang, t }) {
  const voice = useVoice(lang)
  const [speaking, setSpeaking] = useState(false)
  useEffect(() => () => stopSpeaking(), []) // leaving the screen stops reading
  useEffect(() => {
    stopSpeaking()
    setSpeaking(false)
  }, [text])
  if (!voice || !text) return null

  function toggle() {
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
    } else {
      setSpeaking(true)
      speak(text, voice, { onEnd: () => setSpeaking(false) })
    }
  }

  return (
    <button type="button" className="read-aloud" onClick={toggle} aria-pressed={speaking}>
      <span aria-hidden="true">{speaking ? '■' : '🔊'}</span> {speaking ? t.stopReading : t.readAloud}
    </button>
  )
}
