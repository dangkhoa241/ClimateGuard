// node --test (npm test): the report date line in all 7 languages, with this runtime's dates and with the
// iPhone Safari Vietnamese form that showed "Lập ngày ngày 28 tháng 10, 2026" on the phone test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { dropRepeatedWords, reportDateLine } from './reportDate.js'
import { REVIEWED_STRINGS } from './strings.js'

const AUTO = JSON.parse(readFileSync(new URL('./i18n.auto.json', import.meta.url), 'utf8'))
const LANGS = ['en', 'es', 'vi', 'zh', 'tl', 'ko', 'ar']
const template = (lang) => REVIEWED_STRINGS[lang]?.recReportDate || AUTO[lang]?.recReportDate || REVIEWED_STRINGS.en.recReportDate
const CREATED = Date.UTC(2026, 9, 28, 19) / 1000 // Oct 28, 2026, noon in California

const repeated = (line) => {
  const words = line.split(/\s+/).map((w) => w.toLocaleLowerCase().replace(/[.,:;]+$/, ''))
  return words.find((w, i) => i > 0 && w === words[i - 1])
}

for (const lang of LANGS) {
  test(`date line in ${lang}: filled, no repeated word`, () => {
    const line = reportDateLine(template(lang), lang, CREATED)
    assert.ok(!line.includes('{date}'), line)
    assert.ok(line.includes('2026') || line.includes('٢٠٢٦'), line)
    assert.equal(repeated(line), undefined, line)
  })
}

test('vi: iPhone Safari date form', () => {
  const safari = () => 'ngày 28 tháng 10, 2026'
  assert.equal(reportDateLine(template('vi'), 'vi', CREATED, safari), 'Lập ngày 28 tháng 10, 2026')
  assert.equal(reportDateLine(template('vi'), 'vi', CREATED, () => '28 tháng 10, 2026'), 'Lập ngày 28 tháng 10, 2026')
})

test('only neighbors are merged', () => {
  assert.equal(dropRepeatedWords('Hecho el 28 de octubre de 2026'), 'Hecho el 28 de octubre de 2026')
  assert.equal(dropRepeatedWords('Made on on October 28'), 'Made on October 28')
})
