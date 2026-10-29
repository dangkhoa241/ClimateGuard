// Bring something the person needs to see next into view: the report card when it's written, the questions after
// the photo check, an error message. Smooth scroll, or instant with prefers-reduced-motion; no scroll at all when
// it's already fully in view. `focus`: move keyboard / screen-reader focus to it too (a heading gets tabindex -1).
export function inView(el, win = globalThis.window) {
  const r = el.getBoundingClientRect()
  return r.top >= 0 && r.bottom <= win.innerHeight
}

export function reveal(el, { focus = false, win = globalThis.window } = {}) {
  if (!el) return false
  let scrolled = false
  if (!inView(el, win)) {
    const reduce = win.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    scrolled = true
  }
  if (focus) {
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
    el.focus({ preventScroll: true }) // the scroll above (or none) decides where the page goes
  }
  return scrolled
}
