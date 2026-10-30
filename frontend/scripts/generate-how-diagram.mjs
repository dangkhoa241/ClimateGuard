import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { HOW_LANES, HOW_NODES } from '../src/howItWorksData.js'
import { REVIEWED_STRINGS } from '../src/strings.js'

const english = REVIEWED_STRINGS.en
const nodeById = new Map(HOW_NODES.map((node) => [node.id, node]))
const output = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/architecture.svg')
const escapeXml = (text) => String(text).replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
}[char]))

function wrap(text, maxLength) {
  const words = String(text).split(/\s+/)
  const lines = []
  let line = ''
  for (const word of words) {
    if (line && `${line} ${word}`.length > maxLength) {
      lines.push(line)
      line = word
    } else {
      line = line ? `${line} ${word}` : word
    }
  }
  if (line) lines.push(line)
  return lines.flatMap((part) => {
    if (part.length <= maxLength) return [part]
    const chunks = part.match(new RegExp(`.{1,${maxLength}}`, 'g')) || []
    return chunks
  })
}

function textLines(text, x, y, maxLength, className, lineHeight) {
  return wrap(text, maxLength).map((line, index) =>
    `<tspan x="${x}" y="${y + index * lineHeight}" class="${className}">${escapeXml(line)}</tspan>`,
  ).join('')
}

function renderNode(node, x, y, width, height) {
  const fill = node.meta ? '#c2410c' : '#f5f5f4'
  const stroke = node.meta ? '#9a3412' : '#a8a29e'
  const foreground = node.meta ? '#ffffff' : '#1d1d1b'
  const badge = node.meta ? english.howMetaBadge : english.howNoMetaBadge
  const badgeWidth = Math.max(100, badge.length * 8 + 18)
  const titleY = y + 67
  const modelY = y + 126
  return `<g class="node">
    <rect x="${x}" y="${y}" width="${width}" height="${height}" rx="14" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
    <rect x="${x + 14}" y="${y + 13}" width="${badgeWidth}" height="26" rx="13" fill="${node.meta ? '#a3360b' : '#e7e5e4'}" stroke="${node.meta ? '#fff' : '#a8a29e'}"/>
    <text x="${x + 14 + badgeWidth / 2}" y="${y + 31}" text-anchor="middle" class="badge" fill="${node.meta ? '#fff' : '#292524'}">${escapeXml(badge)}</text>
    <text text-anchor="middle" fill="${foreground}">${textLines(english.howSteps[node.stepIndex], x + width / 2, titleY, Math.max(18, Math.floor(width / 9)), 'title', 21)}</text>
    <text text-anchor="middle" fill="${foreground}">${textLines(node.modelLabel, x + width / 2, modelY, Math.max(24, Math.floor(width / 6.7)), 'model', 17)}</text>
  </g>`
}

function renderArrow(x1, x2, y) {
  return `<g class="arrow" aria-hidden="true">
    <path d="M${x1} ${y}H${x2 - 7}m-7 -7 7 7-7 7" fill="none" stroke="#78716c" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${(x1 + x2) / 2}" cy="${y}" r="4" fill="#c2410c"/>
  </g>`
}

function renderFlow(flow, { x, y, nodeWidth, nodeHeight, gap }) {
  const nodes = flow.nodeIds.map((id) => nodeById.get(id))
  if (nodes.some((node) => !node)) throw new Error(`Unknown node in flow: ${flow.id}`)
  const parts = []
  nodes.forEach((node, index) => {
    const nodeX = x + index * (nodeWidth + gap)
    parts.push(renderNode(node, nodeX, y, nodeWidth, nodeHeight))
    if (index < nodes.length - 1) parts.push(renderArrow(nodeX + nodeWidth + 5, nodeX + nodeWidth + gap - 5, y + nodeHeight / 2))
  })
  return parts.join('\n')
}

const alertsLane = HOW_LANES.find((lane) => lane.id === 'alerts')
const recoveryLane = HOW_LANES.find((lane) => lane.id === 'recovery')
const alertsFlow = alertsLane?.flows.find((flow) => flow.id === 'alerts')
const askFlow = alertsLane?.flows.find((flow) => flow.id === 'ask')
const recoveryFlow = recoveryLane?.flows.find((flow) => flow.id === 'recovery')
if (!alertsFlow || !askFlow || !recoveryFlow) throw new Error('Expected alerts, Ask, and recovery flows.')

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 890" role="img" aria-labelledby="title description">
  <title id="title">${escapeXml(english.howDiagramTitle)}</title>
  <desc id="description">${escapeXml(`${english.howLaneAlerts}: NWS data, alert decision, safety rules, translation and read-aloud; Ask: voice transcription and answer. ${english.howLaneRecovery}: photos, SAM outlines, image analysis and report.`)}</desc>
  <style>
    text { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
    .lane-title { font-size: 24px; font-weight: 700; fill: #1d1d1b; }
    .flow-title { font-size: 19px; font-weight: 700; fill: #1d1d1b; }
    .legend { font-size: 15px; fill: #1d1d1b; }
    .badge { font-size: 12px; font-weight: 700; }
    .title { font-size: 17px; font-weight: 700; }
    .model { font-size: 13px; }
  </style>
  <rect width="1440" height="890" fill="#fffdf8"/>
  <g transform="translate(40 28)">
    <rect width="14" height="14" rx="4" fill="#c2410c"/>
    <text x="22" y="12" class="legend">${escapeXml(english.howMetaBadge)}</text>
    <rect x="150" width="14" height="14" rx="4" fill="#e7e5e4" stroke="#78716c"/>
    <text x="172" y="12" class="legend">${escapeXml(english.howNoMetaBadge)}</text>
  </g>
  <rect x="24" y="58" width="1392" height="472" rx="20" fill="#fff" stroke="#e7e1d6" stroke-width="2"/>
  <text x="48" y="94" class="lane-title">${escapeXml(english[alertsLane.titleKey])}</text>
  ${renderFlow(alertsFlow, { x: 53, y: 112, nodeWidth: 238, nodeHeight: 192, gap: 36 })}
  <text x="53" y="347" class="flow-title">${escapeXml(english[askFlow.titleKey])}</text>
  ${renderFlow(askFlow, { x: 53, y: 365, nodeWidth: 330, nodeHeight: 140, gap: 62 })}
  <rect x="24" y="548" width="1392" height="310" rx="20" fill="#fff" stroke="#e7e1d6" stroke-width="2"/>
  <text x="48" y="586" class="lane-title">${escapeXml(english[recoveryLane.titleKey])}</text>
  ${renderFlow(recoveryFlow, { x: 45, y: 610, nodeWidth: 300, nodeHeight: 220, gap: 50 })}
</svg>
`

await writeFile(output, svg, 'utf8')
console.log(`Wrote ${output}`)
