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

// "Your photos will be deleted automatically on Thursday at 6:30 PM." The short weekday ("jue, 18:30") read badly
// in Spanish, and no locale gives the Spanish style "6:30 p. m.", so Spanish is built here: "a las 6:30 p. m.",
// "a la 1:05 p. m.". Vietnamese weekdays are "thứ Năm" mid-sentence (reviewer), "Chủ Nhật" stays as is.
export function deletesAtParts(epoch, lang, timeZone) {
  const d = new Date(epoch * 1000)
  const tz = timeZone ? { timeZone } : {}
  let day = d.toLocaleDateString(lang, { weekday: 'long', ...tz })
  let time
  if (lang === 'es') {
    const parts = new Intl.DateTimeFormat('es', { hour: 'numeric', minute: '2-digit', hourCycle: 'h23', ...tz })
      .formatToParts(d)
    const p = Object.fromEntries(parts.map((x) => [x.type, x.value]))
    const h = Number(p.hour)
    const h12 = h % 12 || 12
    time = `${h12 === 1 ? 'a la' : 'a las'} ${h12}:${p.minute} ${h < 12 ? 'a. m.' : 'p. m.'}`
  } else {
    time = d.toLocaleTimeString(lang, { hour: 'numeric', minute: '2-digit', ...tz })
  }
  if (lang === 'vi' && day.startsWith('Thứ')) day = 't' + day.slice(1)
  return { day, time }
}

export const deletesAtLine = (template, lang, epoch, timeZone) => {
  const { day, time } = deletesAtParts(epoch, lang, timeZone)
  // "…a las 6:30 p. m.." -> one period when the time's abbreviation ends the sentence
  return template.replaceAll('{day}', day).replaceAll('{time}', time).replace(/\.\./g, '.')
}
