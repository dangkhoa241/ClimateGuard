import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { STRINGS } from './i18n.js'
import { ResultsView } from './RecoveryReport.jsx'

// The printed "Not an official damage estimate or an insurance claim" line comes from ONE place: the table's
// <thead>, which the browser repeats at the top of every printed page. Inline copies at the start of each section
// printed it again on the same page (three times on page 3, Nov 1).
const side = (lang) => ({
  lang, disaster_label: 'Flood', fallback_en: false, danger_lines: ['Leave the area now and call 911.'],
  summary: 'Water in the living room.', areas: [{ area: 'Living room', photos: [1], damage: ['wet carpet'] }],
  answers: [{ q: 'Is the power on?', a: 'Some of it' }], checklist_lang: 'en',
  checklist: [{ id: 'document', text: 'Document the damage.', lang: 'en', detail: null }],
})
const view = (sides) => ({ danger_lines: ['Leave the area now and call 911.'], disaster_label: 'Flood', inferred_label: null,
  photos: [{ index: 0, found: [], overlay: null }], report: { created: 1793000000, sides } })

describe('the printed disclaimer', () => {
  it.each(['en', 'es', 'vi'])('is in the table header only, once, in %s', (lang) => {
    const sides = lang === 'en' ? [side('en')] : [side(lang), side('en')]
    const html = renderToStaticMarkup(
      <ResultsView t={STRINGS[lang]} lang={lang} view={view(sides)} showReport photoUrls={['x']} place="Stockton, CA"
        outlines={false} setOutlines={() => {}} reportHeadingRef={null} />)
    expect(html.match(/class="print-disclaimer print-only"/g)).toHaveLength(1)
    const head = html.slice(html.indexOf('<thead'), html.indexOf('</thead>'))
    expect(head).toContain('class="print-disclaimer print-only"')
    expect(head).toContain(STRINGS[lang].recNotEstimate)
    if (lang !== 'en') expect(head).toContain(STRINGS.en.recNotEstimate) // the insurer's English line, in the same block
  })
})
