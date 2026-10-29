import assert from 'node:assert/strict'
import { test } from 'node:test'
import { reveal } from './reveal.js'

function fakeEl(top, bottom) {
  const el = {
    attrs: {}, scrolls: [], focused: null,
    getBoundingClientRect: () => ({ top, bottom }),
    scrollIntoView(opts) { el.scrolls.push(opts) },
    hasAttribute: (k) => k in el.attrs,
    setAttribute(k, v) { el.attrs[k] = v },
    focus(opts) { el.focused = opts },
  }
  return el
}
const win = (reduce) => ({ innerHeight: 800, matchMedia: () => ({ matches: reduce }) })

test('below the fold: smooth scroll to its top', () => {
  const el = fakeEl(1200, 1240)
  assert.equal(reveal(el, { win: win(false) }), true)
  assert.deepEqual(el.scrolls, [{ behavior: 'smooth', block: 'start' }])
  assert.equal(el.focused, null)
})

test('reduced motion: instant scroll', () => {
  const el = fakeEl(-300, -260)
  reveal(el, { win: win(true) })
  assert.deepEqual(el.scrolls, [{ behavior: 'auto', block: 'start' }])
})

test('already in view: no scroll, focus still moves', () => {
  const el = fakeEl(100, 140)
  assert.equal(reveal(el, { focus: true, win: win(false) }), false)
  assert.deepEqual(el.scrolls, [])
  assert.deepEqual(el.focused, { preventScroll: true })
  assert.equal(el.attrs.tabindex, '-1')
})

test('nothing to reveal', () => {
  assert.equal(reveal(null), false)
})
