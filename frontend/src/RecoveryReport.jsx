import { STRINGS } from './i18n.js'
import { formatReportDate, reportDateLine } from './reportDate.js'

// The recovery results and report as shown on screen and printed / saved as PDF.
//
// Print layout (iPhone Safari test, Oct 28): position:fixed footers don't repeat in Safari and covered the last
// question on page 1. Now:
//   - the printed content sits in a <table>; its <thead> holds the disclaimer line, and browsers repeat a
//     table header at the top of every printed page;
//   - as a backup, each section (report, English copy, checklist, photos) starts with the same line, so no page
//     can be without "Not an official damage estimate", even where <thead> doesn't repeat;
//   - headings are kept with the first item after them, and each question stays with its answer.
// On screen the table, header and backup lines are invisible (display: block / none in index.css).

export const fill = (s, vars) => Object.entries(vars).reduce((out, [k, v]) => out.replaceAll(`{${k}}`, v), s)

function DangerBanner({ lines }) {
  if (!lines?.length) return null
  return (
    <div className="notice error rec-danger" role="alert">
      <p><strong>{lines[0]}</strong></p>
      {lines.slice(1).map((l) => <p key={l}>{l}</p>)}
      <a className="big call911" href="tel:911">911</a>
    </div>
  )
}

// "Not an official damage estimate · October 28, 2026 · Stockton, CA" (print only)
export const disclaimerLine = (s, lang, created, place) =>
  [s.recNotEstimate, formatReportDate(created, lang), place].filter(Boolean).join(' · ')

function Disclaimer({ t, lang, created, place, english = false }) {
  return (
    <div className="print-disclaimer print-only">
      <p lang={lang}>{disclaimerLine(t, lang, created, place)}</p>
      {english && lang !== 'en' && <p lang="en" dir="ltr">{disclaimerLine(STRINGS.en, 'en', created, place)}</p>}
    </div>
  )
}

function PhotoResult({ t, photo, url, n, outlines }) {
  return (
    <figure className="rec-photo">
      <div className="rec-photo-frame">
        <img src={url} alt={fill(t.recPhotoN, { n })} />
        {outlines && photo.overlay && <img className="rec-overlay" src={photo.overlay} alt="" />}
      </div>
      <figcaption>
        <strong>{fill(t.recPhotoN, { n })}</strong>
        {photo.found.length ? (
          <ul className="rec-legend">
            {photo.found.map((f) => (
              <li key={f.concept}>
                <span className="swatch" style={{ background: f.color }} aria-hidden="true" />
                {f.label}{f.count > 1 ? ` (${f.count})` : ''}
              </li>
            ))}
          </ul>
        ) : (
          <span className="muted small"> {t.recNothingOutlined}</span>
        )}
      </figcaption>
    </figure>
  )
}

// One side of the report: the person's language, or the English copy for the insurer.
// Each heading prints together with the first item after it (.keep); the rest follows in a continued list.
function ReportSide({ t, side, created, place, headingRef }) {
  const [firstArea, ...areas] = side.areas
  const [firstAnswer, ...answers] = side.answers
  const [firstItem, ...items] = side.checklist
  const area = (a) => (
    <li key={a.area}>
      <strong>{a.area}</strong>
      {a.photos.length > 0 && <span className="muted small"> · {fill(t.recPhotosRef, { list: a.photos.join(', ') })}</span>}
      <ul>{a.damage.map((d) => <li key={d}>{d}</li>)}</ul>
    </li>
  )
  const answer = (x) => <div key={x.q} className="rec-answer"><dt>{x.q}</dt><dd>{x.a}</dd></div>
  const item = (c) => <li key={c.id} lang={c.lang}>{c.text}{c.detail && <><br /><em>{c.detail}</em></>}</li>
  return (
    <article className="answer rec-report" lang={side.lang} dir={side.lang === 'ar' ? 'rtl' : 'ltr'}>
      <div className="keep">
        <Disclaimer t={t} lang={side.lang} created={created} place={place} />
        <h2 ref={headingRef}>{t.recReportTitle}</h2>
        <p className="muted small">{reportDateLine(t.recReportDate, side.lang, created)} · {side.disaster_label}</p>
        <p className="rec-not-estimate no-print">{t.recNotEstimate}</p>
        {side.fallback_en && <p className="muted small">{t.recFallbackEn}</p>}
        {side.danger_lines.map((l) => <p key={l}><strong>{l}</strong></p>)}
      </div>
      <div className="keep">
        <h3>{t.recSummary}</h3>
        <p>{side.summary}</p>
      </div>
      {firstArea && (
        <>
          <div className="keep">
            <h3>{t.recAreas}</h3>
            <ul className="rec-areas list-head">{area(firstArea)}</ul>
          </div>
          {areas.length > 0 && <ul className="rec-areas list-rest">{areas.map(area)}</ul>}
        </>
      )}
      {firstAnswer && (
        <>
          <div className="keep">
            <h3>{t.recYourAnswers}</h3>
            <dl className="rec-answers list-head">{answer(firstAnswer)}</dl>
          </div>
          {answers.length > 0 && <dl className="rec-answers list-rest">{answers.map(answer)}</dl>}
        </>
      )}
      <div className="keep">
        <Disclaimer t={t} lang={side.lang} created={created} place={place} />
        <h3>{t.recNextSteps}</h3>
        {side.checklist_lang !== side.lang && <p className="muted small">{t.checklistEnglishNote}</p>}
        {firstItem && <ol className="checklist list-head" lang={side.checklist_lang}>{item(firstItem)}</ol>}
      </div>
      {items.length > 0 && (
        <ol className="checklist list-rest" start={2} lang={side.checklist_lang}>{items.map(item)}</ol>
      )}
      <p className="muted small">{t.recAiNote}</p>
    </article>
  )
}

// Results (outlined photos) and, once written, the report. `children`: what only the screen needs after the
// photos (questions, buttons). `photoUrls[i]` is the person's own copy of photo i on the phone.
export function ResultsView({ t, lang, view, showReport, photoUrls, place, outlines, setOutlines, reportHeadingRef,
  children }) {
  const report = showReport && view.report
  const created = report ? report.created : Date.now() / 1000
  const [firstPhoto, ...photos] = view.photos
  const photo = (p) => (
    <PhotoResult key={p.index} t={t} photo={p} url={photoUrls[p.index]} n={p.index + 1} outlines={outlines} />
  )
  return (
    <table className="print-table">
      <thead className="print-only-group">
        <tr><td><Disclaimer t={t} lang={lang} created={created} place={place} english /></td></tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <DangerBanner lines={view.danger_lines} />
            {report && (
              <>
                <section className="print-hint no-print">
                  <button className="mid" type="button" onClick={() => window.print()}>{t.recPrintButton}</button>
                  <p className="muted small">{t.recPrintHintDesktop}</p>
                  <p className="muted small">{t.recPrintHintIphone}</p>
                </section>
                <ReportSide t={t} side={report.sides[0]} created={created} place={place} headingRef={reportHeadingRef} />
                {report.sides[1] && (
                  <>
                    {/* on screen: collapsed (the person reads their own language; the insurer gets the English copy) */}
                    <details className="rec-english no-print">
                      <summary>{t.recShowEnglish}</summary>
                      <ReportSide t={STRINGS.en} side={report.sides[1]} created={created} place={place} />
                    </details>
                    {/* on paper: always printed, on its own page; a closed <details> wouldn't print */}
                    <div className="print-only page-break">
                      <ReportSide t={STRINGS.en} side={report.sides[1]} created={created} place={place} />
                    </div>
                  </>
                )}
              </>
            )}
            <section className={report ? 'rec-photos page-break' : 'rec-photos'}>
              <div className="keep">
                <Disclaimer t={t} lang={lang} created={created} place={place} />
                <p className="rec-disaster">
                  <strong>{fill(t.recDisasterSeen, { label: view.disaster_label })}</strong>
                  {view.inferred_label && <span className="muted small"> · {fill(t.recInferredNote, { label: view.inferred_label })}</span>}
                </p>
                <button className="mid no-print" type="button" aria-pressed={outlines} onClick={() => setOutlines(!outlines)}>
                  {outlines ? t.recHideOutlines : t.recShowOutlines}
                </button>
                {firstPhoto && photo(firstPhoto)}
              </div>
              {photos.map(photo)}
            </section>
            {children}
          </td>
        </tr>
      </tbody>
    </table>
  )
}
