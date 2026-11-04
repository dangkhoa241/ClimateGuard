// Writes docs/architecture.svg, the README's main diagram, from the same data as the app's How it works page
// (howItWorksData.js + the English strings). Run: npm run generate:how-diagram
//
// Designed for a README about 900px wide: the viewBox is 960px, so at 900px every label is still 14px or larger
// and the badge 12px or larger. Each node is sized to its own text. The SVG paints its own light background, so it
// reads the same in GitHub light and dark mode.
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ALL_HOW_NODES, HOW_DIAGRAM_LABELS, HOW_EVAL, HOW_LANES, nodeTitle } from '../src/howItWorksData.js'
import { REVIEWED_STRINGS } from '../src/strings.js'

const english = REVIEWED_STRINGS.en
const nodeById = new Map(ALL_HOW_NODES.map((node) => [node.id, node]))
const output = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/architecture.svg')
const escapeXml = (text) => String(text).replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
}[char]))

// ---- Sizes (viewBox px). At a 900px render the scale is 0.9375: 16 -> 15, 15 -> 14.1, 13 -> 12.2.
const W = 960
const MARGIN = 20 // background edge to lane card
const LANE_PAD = 16
const PAD = 12 // node padding
const ARROW_GAP = 34 // space between two nodes in a flow (holds the arrow)
const MAX_TEXT_RANGE = [100, 210] // widest line inside a node: each row uses the largest limit that still fits its lane
const FONT = {
  laneTitle: { size: 19, bold: true, line: 24 },
  flowTitle: { size: 17, bold: true, line: 22 },
  legend: { size: 15, bold: false, line: 20 },
  note: { size: 15, bold: false, line: 20 },
  title: { size: 16, bold: true, line: 20 },
  model: { size: 15, bold: false, line: 19 },
  badge: { size: 13, bold: true, line: 22 },
}
const COLOR = {
  page: '#fffdf8', pageBorder: '#e7e1d6',
  lane: '#f7f5f2', laneBorder: '#e2dcd2',
  text: '#1d1d1b', muted: '#57534e',
  metaFill: '#fff1e3', metaBorder: '#ea580c', metaTitle: '#7c2d12', metaModel: '#9a3412', metaBadgeBorder: '#f4c79a',
  plainFill: '#ffffff', plainBorder: '#a8a29e', plainBadgeFill: '#f5f5f4', plainBadgeBorder: '#d6d3d1', plainBadgeText: '#44403c',
  arrow: '#57534e', evalBorder: '#78716c',
}

// ---- Text measurement: Arial/Helvetica advance widths (per 1000 em), widened 8% so wider system fonts still fit.
const REGULAR = { ' ': 278, '!': 278, "'": 191, '(': 333, ')': 333, '+': 584, ',': 278, '-': 333, '.': 278, '/': 278, ':': 278, '·': 278,
  A: 667, B: 667, C: 722, D: 722, E: 667, F: 611, G: 778, H: 722, I: 278, J: 500, K: 667, L: 556, M: 833, N: 722, O: 778, P: 667, Q: 778,
  R: 722, S: 667, T: 611, U: 722, V: 667, W: 944, X: 667, Y: 667, Z: 611, a: 556, b: 556, c: 500, d: 556, e: 556, f: 278, g: 556, h: 556,
  i: 222, j: 222, k: 500, l: 222, m: 833, n: 556, o: 556, p: 556, q: 556, r: 333, s: 500, t: 278, u: 556, v: 500, w: 722, x: 500, y: 500, z: 500 }
const BOLD = { ' ': 278, '!': 333, "'": 238, '(': 333, ')': 333, '+': 584, ',': 278, '-': 333, '.': 278, '/': 278, ':': 333, '·': 278,
  A: 722, B: 722, C: 722, D: 722, E: 667, F: 611, G: 778, H: 722, I: 278, J: 556, K: 722, L: 611, M: 833, N: 722, O: 778, P: 667, Q: 778,
  R: 722, S: 667, T: 611, U: 722, V: 667, W: 944, X: 667, Y: 667, Z: 611, a: 556, b: 611, c: 556, d: 611, e: 556, f: 333, g: 611, h: 611,
  i: 278, j: 278, k: 556, l: 278, m: 889, n: 611, o: 611, p: 611, q: 611, r: 389, s: 556, t: 333, u: 611, v: 556, w: 778, x: 556, y: 556, z: 500 }
function measure(text, { size, bold }) {
  const table = bold ? BOLD : REGULAR
  let units = 0
  for (const char of String(text)) units += table[char] ?? 556
  return (units / 1000) * size * 1.08
}

// Greedy wrap by measured width; a single word wider than the limit keeps its own line (and widens the node).
// A word that starts with a digit stays with the word before it ("SAM 3.1", "Muse Spark 1.3", "every 15").
function wrap(text, font, maxWidth) {
  if (!text) return []
  const words = []
  for (const word of String(text).split(/\s+/)) {
    if (/^\d/.test(word) && words.length) words[words.length - 1] += ` ${word}`
    else words.push(word)
  }
  const lines = []
  let line = ''
  for (const word of words) {
    const next = line ? `${line} ${word}` : word
    if (line && measure(next, font) > maxWidth) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

function textBlock(lines, x, y, font, attrs) {
  // y is the top of the block; each baseline sits ~0.78 of the line height down.
  return lines.map((line, i) =>
    `<text x="${x}" y="${(y + i * font.line + font.line * 0.78).toFixed(1)}" ${attrs}>${escapeXml(line)}</text>`).join('\n    ')
}

// ---- Nodes
function layoutNode(node, maxText) {
  const badge = node.meta ? english.howMetaBadge : english.howNoMetaBadge
  const title = wrap(nodeTitle(node, english), FONT.title, maxText)
  const model = wrap(HOW_DIAGRAM_LABELS[node.id] ?? '', FONT.model, maxText)
  if (!(node.id in HOW_DIAGRAM_LABELS)) throw new Error(`No diagram label for node ${node.id}`)
  const badgeWidth = Math.ceil(measure(badge, FONT.badge) + 20)
  const textWidth = Math.max(badgeWidth, ...title.map((l) => measure(l, FONT.title)), ...model.map((l) => measure(l, FONT.model)))
  const contentHeight = FONT.badge.line + 8 + title.length * FONT.title.line + (model.length ? 6 + model.length * FONT.model.line : 0)
  return { node, badge, badgeWidth, title, model, width: Math.ceil(textWidth + 2 * PAD), contentHeight }
}

function renderNode(box, x, y, height) {
  const { node, badge, badgeWidth, title, model, width, contentHeight } = box
  const cx = x + width / 2
  let top = y + (height - contentHeight) / 2 // center the content in a row of equal-height nodes
  const parts = [
    `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="10" fill="${node.meta ? COLOR.metaFill : COLOR.plainFill}" stroke="${node.meta ? COLOR.metaBorder : COLOR.plainBorder}" stroke-width="2"/>`,
    `<rect x="${cx - badgeWidth / 2}" y="${top}" width="${badgeWidth}" height="${FONT.badge.line}" rx="${FONT.badge.line / 2}" fill="${node.meta ? '#ffffff' : COLOR.plainBadgeFill}" stroke="${node.meta ? COLOR.metaBadgeBorder : COLOR.plainBadgeBorder}"/>`,
    `<text x="${cx}" y="${top + 15.5}" class="badge" fill="${node.meta ? COLOR.metaTitle : COLOR.plainBadgeText}">${escapeXml(badge)}</text>`,
  ]
  top += FONT.badge.line + 8
  parts.push(textBlock(title, cx, top, FONT.title, `class="title" fill="${node.meta ? COLOR.metaTitle : COLOR.text}"`))
  top += title.length * FONT.title.line + 6
  if (model.length) parts.push(textBlock(model, cx, top, FONT.model, `class="model" fill="${node.meta ? COLOR.metaModel : COLOR.muted}"`))
  return `<g class="node" data-id="${node.id}">\n    ${parts.join('\n    ')}\n  </g>`
}

function renderArrow(x1, x2, y) {
  return `<path class="arrow" d="M${x1} ${y}H${x2 - 1}" fill="none" stroke="${COLOR.arrow}" stroke-width="2.5" stroke-linecap="round" marker-end="url(#arrowhead)"/>`
}

// A row of nodes, centered between left and right; arrows only between neighbours of the same flow.
const ROW_SPACE = W - 2 * MARGIN - 2 * LANE_PAD
function layoutFlow(flow, title) {
  const nodes = flow.nodeIds.map((id) => {
    const node = nodeById.get(id)
    if (!node) throw new Error(`Unknown node in flow: ${flow.id}`)
    return node
  })
  let boxes
  let rowWidth
  for (let maxText = MAX_TEXT_RANGE[1]; maxText >= MAX_TEXT_RANGE[0]; maxText -= 2) {
    boxes = nodes.map((node) => layoutNode(node, maxText))
    rowWidth = boxes.reduce((sum, b) => sum + b.width, 0) + ARROW_GAP * (boxes.length - 1)
    if (rowWidth <= ROW_SPACE - 8) break
  }
  const nodeHeight = Math.max(...boxes.map((b) => b.contentHeight)) + 2 * PAD
  const titleHeight = title ? FONT.flowTitle.line + 6 : 0
  return { boxes, rowWidth, nodeHeight, title, height: titleHeight + nodeHeight }
}

function renderFlow(flowLayout, left, right, y) {
  const { boxes, rowWidth, nodeHeight, title } = flowLayout
  if (rowWidth > right - left) throw new Error(`Flow is ${Math.ceil(rowWidth)}px wide, only ${right - left}px fit`)
  const parts = []
  if (title) {
    parts.push(`<text x="${(left + right) / 2}" y="${y + FONT.flowTitle.line * 0.78}" class="flow-title">${escapeXml(title)}</text>`)
    y += FONT.flowTitle.line + 6
  }
  let x = Math.round(left + (right - left - rowWidth) / 2)
  boxes.forEach((box, i) => {
    parts.push(renderNode(box, x, y, nodeHeight))
    x += box.width
    if (i < boxes.length - 1) parts.push(renderArrow(x + 5, x + ARROW_GAP - 5, y + nodeHeight / 2))
    x += i < boxes.length - 1 ? ARROW_GAP : 0
  })
  return parts.join('\n  ')
}

// A lane card: centered title (and optional note), then its flows stacked.
function renderLane({ title, note, flows, dashed }, y) {
  const left = MARGIN
  const right = W - MARGIN
  const innerLeft = left + LANE_PAD
  const innerRight = right - LANE_PAD
  const noteLines = note ? wrap(note, FONT.note, innerRight - innerLeft) : []
  const headHeight = LANE_PAD + FONT.laneTitle.line + (noteLines.length ? 4 + noteLines.length * FONT.note.line : 0) + 14
  const flowsHeight = flows.reduce((sum, f) => sum + f.height, 0) + 20 * (flows.length - 1)
  const height = headHeight + flowsHeight + LANE_PAD + 4
  const parts = [
    dashed
      ? `<rect x="${left}" y="${y}" width="${right - left}" height="${height}" rx="16" fill="${COLOR.page}" stroke="${COLOR.evalBorder}" stroke-width="2.5" stroke-dasharray="10 7"/>`
      : `<rect x="${left}" y="${y}" width="${right - left}" height="${height}" rx="16" fill="${COLOR.lane}" stroke="${COLOR.laneBorder}" stroke-width="1.5"/>`,
    `<text x="${W / 2}" y="${y + LANE_PAD + FONT.laneTitle.line * 0.78}" class="lane-title">${escapeXml(title)}</text>`,
  ]
  if (noteLines.length) parts.push(textBlock(noteLines, W / 2, y + LANE_PAD + FONT.laneTitle.line + 4, FONT.note, 'class="note"'))
  let flowY = y + headHeight
  for (const flow of flows) {
    parts.push(renderFlow(flow, innerLeft, innerRight, flowY))
    flowY += flow.height + 20
  }
  return { svg: parts.join('\n  '), height }
}

// ---- Data checks (same as before): the evaluation node is never in a live flow.
const alertsLane = HOW_LANES.find((lane) => lane.id === 'alerts')
const recoveryLane = HOW_LANES.find((lane) => lane.id === 'recovery')
const alertsFlow = alertsLane?.flows.find((flow) => flow.id === 'alerts')
const askFlow = alertsLane?.flows.find((flow) => flow.id === 'ask')
const recoveryFlow = recoveryLane?.flows.find((flow) => flow.id === 'recovery')
const evalFlow = HOW_EVAL.flows[0]
if (!alertsFlow || !askFlow || !recoveryFlow || !evalFlow) throw new Error('Expected alerts, Ask, recovery and evaluation flows.')
if (HOW_LANES.some((lane) => lane.flows.some((flow) => flow.nodeIds.some((id) => evalFlow.nodeIds.includes(id))))) {
  throw new Error('An evaluation node must not be in a live flow.')
}

// ---- Legend (centered row)
function renderLegend(y) {
  const items = [
    { label: english.howMetaBadge, swatch: `fill="${COLOR.metaFill}" stroke="${COLOR.metaBorder}" stroke-width="2"` },
    { label: english.howNoMetaBadge, swatch: `fill="${COLOR.plainFill}" stroke="${COLOR.plainBorder}" stroke-width="2"` },
    { label: english.howLegendEval, swatch: `fill="${COLOR.page}" stroke="${COLOR.evalBorder}" stroke-width="2" stroke-dasharray="4 3"` },
  ]
  const SW = 22
  const widths = items.map((it) => SW + 8 + measure(it.label, FONT.legend))
  const total = widths.reduce((a, b) => a + b, 0) + 28 * (items.length - 1)
  let x = (W - total) / 2
  return items.map((it, i) => {
    const part = `<rect x="${x.toFixed(1)}" y="${y}" width="${SW}" height="16" rx="4" ${it.swatch}/>
  <text x="${(x + SW + 8).toFixed(1)}" y="${y + 13}" class="legend">${escapeXml(it.label)}</text>`
    x += widths[i] + 28
    return part
  }).join('\n  ')
}

let y = 20
const legend = renderLegend(y)
y += 16 + 18
const lanes = []
for (const lane of [
  { title: english[alertsLane.titleKey], flows: [layoutFlow(alertsFlow), layoutFlow(askFlow, english[askFlow.titleKey])] },
  { title: english[recoveryLane.titleKey], flows: [layoutFlow(recoveryFlow)] },
  { title: english[HOW_EVAL.titleKey], note: english[HOW_EVAL.noteKey], flows: [layoutFlow(evalFlow)], dashed: true },
]) {
  const { svg, height } = renderLane(lane, y)
  lanes.push(svg)
  y += height + 16
}
const H = y + 4

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-labelledby="title description">
  <title id="title">${escapeXml(english.howDiagramTitle)}</title>
  <desc id="description">${escapeXml(`${english.howLaneAlerts}: NWS data, alert decision, safety rules, translation and read-aloud; Ask: voice transcription and answer. ${english.howLaneRecovery}: photos, SAM outlines, image analysis and report. ${english[HOW_EVAL.titleKey]}: Muse Wonder 1.0 review, not connected to the live path.`)}</desc>
  <defs>
    <marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="${COLOR.arrow}"/>
    </marker>
  </defs>
  <style>
    text { font-family: 'Segoe UI', system-ui, -apple-system, Helvetica, Arial, sans-serif; text-anchor: middle; }
    .legend { font-size: ${FONT.legend.size}px; fill: ${COLOR.text}; text-anchor: start; }
    .lane-title { font-size: ${FONT.laneTitle.size}px; font-weight: 700; fill: ${COLOR.text}; }
    .flow-title { font-size: ${FONT.flowTitle.size}px; font-weight: 700; fill: ${COLOR.text}; }
    .note { font-size: ${FONT.note.size}px; fill: ${COLOR.muted}; }
    .badge { font-size: ${FONT.badge.size}px; font-weight: 700; }
    .title { font-size: ${FONT.title.size}px; font-weight: 700; }
    .model { font-size: ${FONT.model.size}px; font-weight: 500; }
  </style>
  <rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="20" fill="${COLOR.page}" stroke="${COLOR.pageBorder}" stroke-width="2"/>
  ${legend}
  ${lanes.join('\n  ')}
</svg>
`

await writeFile(output, svg, 'utf8')
console.log(`Wrote ${output} (${W}x${H})`)
