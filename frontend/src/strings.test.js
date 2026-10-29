import { test } from 'node:test'
import assert from 'node:assert/strict'
import { REVIEWED_STRINGS } from './strings.js'

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
