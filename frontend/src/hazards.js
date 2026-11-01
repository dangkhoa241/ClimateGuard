// Backend hazard groups (hazards.py): the icon and color family each one uses, and the groups the app says it covers.
// fog, dust and fire weather have no icon of their own, so they get the neutral one: the label never says "smoke".
const KIND_OF = { heat: 'heat', smoke: 'smoke', flood: 'flood', coastal: 'flood', tropical: 'storm', tornado: 'storm',
  thunderstorm: 'storm', wind: 'storm', winter: 'cold', cold: 'cold' }
export const hazardKind = (hazard) => KIND_OF[hazard] || 'other'

// The coverage list, in display order. Tornado and severe thunderstorm are left out on purpose: only their
// watches are handled, their warnings are not covered (see the not-covered notice).
export const COVERAGE_ORDER = ['heat', 'smoke', 'flood', 'fog', 'wind', 'winter', 'cold', 'dust', 'fire', 'coastal',
  'tropical']
