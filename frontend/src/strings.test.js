import { test } from 'node:test'
import assert from 'node:assert/strict'
import { REVIEWED_STRINGS } from './strings.js'
import { readFileSync } from 'node:fs'

// Demo mode text: Spanish and Vietnamese have every key English has, with the same {placeholders}.
const holes = (s) => (s.match(/\{\w+\}/g) || []).sort().join(' ')

function flat(obj, prefix = '') {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flat(v, `${prefix}${k}.`) : [[`${prefix}${k}`, v]])
}

for (const lang of ['es', 'vi']) {
  test(`demo strings complete in ${lang}`, () => {
    const other = Object.fromEntries(flat(REVIEWED_STRINGS[lang]))
    const demoKeys = flat(REVIEWED_STRINGS.en).filter(([k]) => k.startsWith('demo'))
    assert.ok(demoKeys.length > 40)
    for (const [k, en] of demoKeys) {
      assert.equal(typeof other[k], 'string', `${lang} is missing ${k}`)
      assert.equal(holes(other[k]), holes(en), `${lang} ${k} placeholders differ`)
    }
  })
}

// The report's print header and screen note say it is not an insurance claim, in every language.
// Raw strings per language (no English fallback): the auto-translated four are checked in i18n.auto.json.
const AUTO = JSON.parse(readFileSync(new URL('./i18n.auto.json', import.meta.url), 'utf8'))
const NOT_A_CLAIM = {
  en: 'insurance claim', es: 'reclamo de seguro', vi: 'yêu cầu bồi thường bảo hiểm',
  zh: '保险理赔', tl: 'habol sa seguro', ko: '보험 청구', ar: 'مطالبة تأمين',
}
for (const [lang, phrase] of Object.entries(NOT_A_CLAIM)) {
  test(`recNotEstimate says it is not an insurance claim in ${lang}`, () => {
    const s = (REVIEWED_STRINGS[lang] ?? AUTO[lang])?.recNotEstimate
    assert.equal(typeof s, 'string', `${lang} has no recNotEstimate`)
    assert.ok(s.includes(phrase), `${lang}: "${s}" lacks "${phrase}"`)
  })
}
