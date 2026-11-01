import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ALL_HOW_NODES, HOW_EVAL, HOW_EVAL_NODES, HOW_LANES, HOW_NODES } from './howItWorksData.js'
import { REVIEWED_STRINGS } from './strings.js'

// Muse Wonder is in the evaluation only, never in the live product: the node must not be in any live flow (the
// diagram draws an arrow only between neighbours of a flow, so a node alone in its own flow has none), and its
// text must exist in all 7 languages (raw strings, no English fallback).
const AUTO = JSON.parse(readFileSync(new URL('./i18n.auto.json', import.meta.url), 'utf8'))
const RAW = { ...REVIEWED_STRINGS, ...AUTO }
const LANGS = ['en', 'es', 'vi', 'zh', 'tl', 'ko', 'ar']
const KEYS = ['howEvalTitle', 'howEvalNote', 'howEvalStep', 'howEvalDescription', 'howEvalCostLabel', 'howEvalCost', 'howLegendEval']
const node = HOW_EVAL_NODES.find((n) => n.id === 'wonder-review')

test('the evaluation node exists, is a Meta model node and is marked evaluation only', () => {
  assert.ok(node)
  assert.equal(node.evalOnly, true)
  assert.equal(node.meta, true)
  assert.match(node.modelLabel, /Muse Wonder 1\.0/)
})

test('the evaluation node is in no live flow and has no neighbour to connect to', () => {
  const live = HOW_LANES.flatMap((lane) => lane.flows)
  assert.equal(live.some((flow) => flow.nodeIds.includes('wonder-review')), false)
  assert.deepEqual(HOW_EVAL.flows.map((flow) => flow.nodeIds), [['wonder-review']])
  assert.equal(HOW_NODES.some((n) => n.id === 'wonder-review' || n.evalOnly), false) // the 11 live steps are unchanged
  assert.equal(HOW_NODES.length, 11)
  assert.equal(ALL_HOW_NODES.length, 12)
  assert.deepEqual(new Set(live.flatMap((flow) => flow.nodeIds)), new Set(HOW_NODES.map((n) => n.id)))
})

for (const lang of LANGS) {
  test(`the evaluation node has its text in ${lang}`, () => {
    for (const key of KEYS) {
      assert.equal(typeof RAW[lang]?.[key], 'string', `${lang} lacks ${key}`)
      assert.ok(RAW[lang][key].trim().length > 0, `${lang} ${key} is empty`)
    }
    const s = RAW[lang]
    assert.ok(s.howEvalStep.includes('Muse Wonder 1.0'), `${lang}: step name`)
    assert.ok(s.howEvalDescription.includes('N95'), `${lang}: description lost N95`)
    for (const fact of ['38', '78', '92', '$0.02', '$3']) assert.ok(s.howEvalCost.includes(fact), `${lang}: cost text lost ${fact}`)
  })
}

test('the diagram files agree with the app: the SVG and the Mermaid source both show the evaluation section', () => {
  const svg = readFileSync(new URL('../../docs/architecture.svg', import.meta.url), 'utf8')
  const mmd = readFileSync(new URL('../../docs/architecture.mmd', import.meta.url), 'utf8')
  assert.ok(svg.includes(REVIEWED_STRINGS.en.howEvalStep) && svg.includes(REVIEWED_STRINGS.en.howEvalTitle) && svg.includes('stroke-dasharray'))
  assert.ok(mmd.includes(REVIEWED_STRINGS.en.howEvalTitle) && mmd.includes('WONDER') && /style EVAL stroke-dasharray/.test(mmd))
  assert.equal(/-->\s*WONDER|WONDER\s*(-->|-\.|---)/.test(mmd), false, 'no edge to or from the evaluation node')
})
