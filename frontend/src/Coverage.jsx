import { COVERAGE_ORDER } from './hazards.js'

// What ClimateGuard covers, grouped by hazard. Names come from hazardNames, one line each from coverage.
export function CoverageList({ t }) {
  return (
    <section className="coverage" aria-labelledby="coverage-title">
      <h2 id="coverage-title">{t.coverageTitle}</h2>
      <p>{t.coverageIntro}</p>
      <ul className="coverage-list">
        {COVERAGE_ORDER.map((hazard) => (
          <li key={hazard}>
            <strong>{t.hazardNames[hazard]}</strong>
            <span>{t.coverage[hazard]}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">{t.coverageOwnData}</p>
    </section>
  )
}

export function NotCoveredNotice({ t }) {
  return (
    <aside className="notice warn" role="note">
      <strong>{t.notCoveredTitle}</strong>
      <p>{t.notCoveredBody}</p>
    </aside>
  )
}

// One plain line for pages that do not show the full notice.
export function NotCoveredLine({ t }) {
  return <p className="not-covered-line" role="note">{t.notCoveredShort}</p>
}
