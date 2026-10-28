// Share a message on WhatsApp (wa.me opens the app on phones, WhatsApp Web on desktop). Families and
// crews pass warnings along in WhatsApp groups, so the text carries a link back to the same area and
// language: ?zone=...&lang=... opens the app on that area's alerts.
export function shareText(text, { zone, lang, t }) {
  const url = new URL(window.location.origin + window.location.pathname)
  if (zone) url.searchParams.set('zone', zone)
  if (lang) url.searchParams.set('lang', lang)
  return `${text}\n\n${t.shareFooter} ${url.toString()}`
}

export default function ShareWhatsApp({ text, zone, lang, t }) {
  if (!text) return null
  const href = `https://wa.me/?text=${encodeURIComponent(shareText(text, { zone, lang, t }))}`
  return (
    <a className="share-wa" href={href} target="_blank" rel="noreferrer">
      <span aria-hidden="true">💬</span> {t.shareWhatsApp}
    </a>
  )
}
