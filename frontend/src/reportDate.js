// The report's date line ("Made on October 28, 2026"). Browsers format dates differently: iPhone Safari writes
// Vietnamese as "ngày 28 tháng 10, 2026" (Node and Chrome: "28 tháng 10, 2026"), so "Lập ngày {date}" came out
// as "Lập ngày ngày 28 tháng 10, 2026". A word repeated next to itself is dropped, whatever the browser does.
export const formatReportDate = (created, lang) =>
  new Date(created * 1000).toLocaleDateString(lang, { year: 'numeric', month: 'long', day: 'numeric' })

const bare = (w) => w.toLocaleLowerCase().replace(/[.,:;]+$/, '')

export function dropRepeatedWords(text) {
  const out = []
  for (const w of text.split(/\s+/).filter(Boolean)) {
    if (!out.length || bare(out[out.length - 1]) !== bare(w)) out.push(w)
  }
  return out.join(' ')
}

export function reportDateLine(template, lang, created, format = formatReportDate) {
  return dropRepeatedWords(template.replaceAll('{date}', format(created, lang)))
}
