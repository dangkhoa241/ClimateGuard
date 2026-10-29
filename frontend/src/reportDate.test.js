// node --test (npm test): the report date line in all 7 languages, with this runtime's dates and with the
// iPhone Safari Vietnamese form that showed "Lập ngày ngày 28 tháng 10, 2026" on the phone test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { deletesAtLine, dropRepeatedWords, reportDateLine } from './reportDate.js'
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

// Thu Oct 29, 2026, 6:30 PM and 1:05 PM in California
const THU_1830 = Date.UTC(2026, 9, 30, 1, 30) / 1000
const THU_1305 = Date.UTC(2026, 9, 29, 20, 5) / 1000
const tpl = (lang) => REVIEWED_STRINGS[lang]?.recDeletesAt || AUTO[lang]?.recDeletesAt || REVIEWED_STRINGS.en.recDeletesAt
const spaces = (s) => s.replace(/[  ]/g, ' ')
const LA = 'America/Los_Angeles'

test('deletes-at line: Spanish weekday and time', () => {
  assert.equal(deletesAtLine(tpl('es'), 'es', THU_1830, LA), 'Sus fotos se borrarán automáticamente el jueves a las 6:30 p. m.')
  assert.equal(deletesAtLine(tpl('es'), 'es', THU_1305, LA), 'Sus fotos se borrarán automáticamente el jueves a la 1:05 p. m.')
  assert.ok(!deletesAtLine(tpl('es'), 'es', THU_1830, LA).includes('jue,'))
})

test('deletes-at line: English and Vietnamese', () => {
  assert.equal(spaces(deletesAtLine(tpl('en'), 'en', THU_1830, LA)), 'Your photos will be deleted automatically on Thursday at 6:30 PM.')
  assert.equal(deletesAtLine(tpl('vi'), 'vi', THU_1830, LA), 'Ảnh của bạn sẽ tự động bị xóa lúc 18:30 thứ Năm.')
})

for (const lang of LANGS) {
  test(`deletes-at line in ${lang}: filled, no repeated word`, () => {
    const line = deletesAtLine(tpl(lang), lang, THU_1830, LA)
    assert.ok(!line.includes('{'), line)
    assert.equal(repeated(line), undefined, line)
  })
}

test('only neighbors are merged', () => {
  assert.equal(dropRepeatedWords('Hecho el 28 de octubre de 2026'), 'Hecho el 28 de octubre de 2026')
  assert.equal(dropRepeatedWords('Made on on October 28'), 'Made on October 28')
})
