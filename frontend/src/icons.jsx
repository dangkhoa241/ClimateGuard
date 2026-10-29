// Small inline SVG icons (no icon library). Decorative unless given a label: the text next to them carries the
// meaning, and hazard icons pair a color with a shape so color is never the only signal.
const base = { width: 24, height: 24, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
  strokeLinecap: 'round', strokeLinejoin: 'round' }

function Svg({ label, children, ...rest }) {
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true, focusable: 'false' }
  return <svg {...base} {...rest} {...a11y}>{children}</svg>
}

// Shield with a sun over a water drop: heat and flood, the two hazards the demo story is about.
export function Logo({ size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false" className="logo">
      <path d="M24 3 6 10v12c0 11.5 7.6 19.6 18 23 10.4-3.4 18-11.5 18-23V10L24 3Z" fill="var(--accent)" />
      <circle cx="24" cy="18" r="5.5" fill="#fde68a" />
      <g stroke="#fde68a" strokeWidth="2.2" strokeLinecap="round">
        <path d="M24 8.5v2.2M24 25.3v2.2M14.5 18h2.2M31.3 18h2.2M17.3 11.3l1.6 1.6M29.1 23.1l1.6 1.6M30.7 11.3l-1.6 1.6M17.3 24.7l1.6-1.6" />
      </g>
      <path d="M24 26.5c-3.2 4-4.8 6.6-4.8 8.6a4.8 4.8 0 0 0 9.6 0c0-2-1.6-4.6-4.8-8.6Z" fill="#fff" />
    </svg>
  )
}

export const Globe = () => (
  <Svg><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" /></Svg>
)

export const FEATURE_ICONS = {
  alerts: () => <Svg><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></Svg>,
  ask: () => <Svg><path d="M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.7A8 8 0 1 1 21 12Z" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.3 2.4c-.5.2-.8.6-.8 1.1v.5M12 16.5h.01" /></Svg>,
  recovery: () => <Svg><path d="M3 11 12 4l9 7" /><path d="M5 10v10h14V10" /><path d="m10 13-1 3 3-1 2 3" /></Svg>,
  supervisor: () => <Svg><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M9 10l1.5 1.5L14 8M9 16h6" /></Svg>,
  history: () => <Svg><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></Svg>,
}

// NWS hazard groups (backend hazards.py) -> the icon and color family shown on alert cards.
const KIND_OF = { heat: 'heat', smoke: 'smoke', dust: 'smoke', fog: 'smoke', fire: 'smoke', flood: 'flood',
  coastal: 'flood', tornado: 'storm', thunderstorm: 'storm', tropical: 'storm', wind: 'storm', cold: 'cold',
  winter: 'cold' }
export const hazardKind = (hazard) => KIND_OF[hazard] || 'other'

const HAZARD_SHAPES = {
  heat: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  smoke: <><path d="M7 18h10a4 4 0 0 0 .5-8 5.5 5.5 0 0 0-10.6 1.2A3.5 3.5 0 0 0 7 18Z" /><path d="M4 21h7M14 21h6" /></>,
  flood: <><path d="M2 8c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0 3 1.5 5 0M2 13c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0 3 1.5 5 0M2 18c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0 3 1.5 5 0" /></>,
  storm: <><path d="M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h8" /></>,
  cold: <><path d="M12 2v20M4.9 7l14.2 10M4.9 17 19.1 7M9 4l3 3 3-3M9 20l3-3 3 3" /></>,
  other: <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
}

export function HazardIcon({ hazard, t }) {
  const kind = hazardKind(hazard)
  return <Svg className="hazard-icon" label={t.hazardNames?.[kind]}>{HAZARD_SHAPES[kind]}</Svg>
}
