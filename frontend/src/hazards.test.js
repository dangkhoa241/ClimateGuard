import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { REVIEWED_STRINGS } from './strings.js'
import { COVERAGE_ORDER, hazardKind } from './hazards.js'

// Hazard names and the coverage list are generated from data: the backend's hazard groups (hazards.py).
// Raw strings per language, with no English fallback, so a language that lacks a name fails here.
const AUTO = JSON.parse(readFileSync(new URL('./i18n.auto.json', import.meta.url), 'utf8'))
const HAZARDS_PY = readFileSync(new URL('../../backend/src/climateguard/hazards.py', import.meta.url), 'utf8')
const BACKEND_GROUPS = [...HAZARDS_PY.matchAll(/^\s+\("(\w+)", \(/gm)].map((m) => m[1]).concat('other')
const RAW = { ...REVIEWED_STRINGS, ...AUTO }
const LANGS = ['en', 'es', 'vi', 'zh', 'tl', 'ko', 'ar']
const text = (v) => typeof v === 'string' && v.trim().length > 0

test('the backend has the 14 hazard groups this test expects', () => {
  assert.equal(BACKEND_GROUPS.length, 14, BACKEND_GROUPS.join(', '))
  for (const g of ['heat', 'smoke', 'flood', 'fog', 'wind', 'winter', 'cold', 'dust', 'fire', 'coastal', 'tropical',
    'tornado', 'thunderstorm', 'other']) assert.ok(BACKEND_GROUPS.includes(g), `backend lacks ${g}`)
})

for (const lang of LANGS) {
  test(`every backend hazard group has its own name in ${lang}`, () => {
    const names = RAW[lang]?.hazardNames
    assert.ok(names, `${lang} has no hazardNames`)
    for (const g of BACKEND_GROUPS) assert.ok(text(names[g]), `${lang} is missing a name for "${g}"`)
    assert.equal(new Set(BACKEND_GROUPS.map((g) => names[g])).size, BACKEND_GROUPS.length,
      `${lang}: two hazard groups share a name (fog, dust and fire weather must not read as smoke)`)
  })

  test(`the coverage list and not-covered line are complete in ${lang}`, () => {
    for (const g of COVERAGE_ORDER) assert.ok(text(RAW[lang].coverage?.[g]), `${lang} is missing coverage text for "${g}"`)
    for (const key of ['coverageTitle', 'coverageIntro', 'coverageOwnData', 'notCoveredShort']) {
      assert.ok(text(RAW[lang][key]), `${lang} is missing ${key}`)
    }
  })
}

test('the coverage list covers real groups and leaves out tornado, thunderstorm and other', () => {
  assert.deepEqual([...COVERAGE_ORDER].sort(), BACKEND_GROUPS.filter((g) => !['tornado', 'thunderstorm', 'other'].includes(g)).sort())
})

test('fog, dust and fire weather use the neutral icon, not the smoke one', () => {
  for (const g of ['fog', 'dust', 'fire']) assert.equal(hazardKind(g), 'other', g)
  assert.equal(hazardKind('smoke'), 'smoke')
  for (const g of BACKEND_GROUPS) assert.ok(['heat', 'smoke', 'flood', 'storm', 'cold', 'other'].includes(hazardKind(g)), g)
})

test('"storm" is gone from the English tagline and intros', () => {
  for (const key of ['tagline', 'signupIntro', 'askIntro', 'demoAbout1']) {
    assert.doesNotMatch(REVIEWED_STRINGS.en[key], /storm/i, key)
  }
  assert.doesNotMatch(REVIEWED_STRINGS.es.tagline + REVIEWED_STRINGS.es.signupIntro + REVIEWED_STRINGS.es.askIntro
    + REVIEWED_STRINGS.es.demoAbout1, /tormenta/i)
  assert.doesNotMatch(REVIEWED_STRINGS.vi.tagline + REVIEWED_STRINGS.vi.signupIntro + REVIEWED_STRINGS.vi.askIntro
    + REVIEWED_STRINGS.vi.demoAbout1, /bão/i)
})

test('the covered list says nothing about medical advice, building safety or repair costs', () => {
  for (const lang of ['en', 'es', 'vi']) {
    const all = JSON.stringify([REVIEWED_STRINGS[lang].coverage, REVIEWED_STRINGS[lang].coverageIntro,
      REVIEWED_STRINGS[lang].coverageOwnData, REVIEWED_STRINGS[lang].notCoveredShort])
    assert.doesNotMatch(all, /medic|symptom|síntoma|triệu chứng|repair|reparaci|sửa chữa|\$\d/i, lang)
  }
})
