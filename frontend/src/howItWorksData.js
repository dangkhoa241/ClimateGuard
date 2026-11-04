export const HOW_MODEL_LABELS = Object.freeze({
  nws: 'National Weather Service · no Meta model',
  decision: 'Muse Spark Open (meta-models/muse-spark-open-1026), via Baseten',
  safety: 'Python safety rules · no Meta model',
  translation: 'Muse Spark 1.3 (Meta Model API)',
  readAloud: 'Device speech synthesis · no Meta model',
  askTranscribe: 'Muse Voice Transcribe 1.0',
  askAnswer: 'Muse Spark 1.3',
  recoveryPhotos: 'No Meta model',
  sam: 'SAM 3.1',
  imageAnalysis: 'Muse Spark 1.3',
  report: 'Muse Spark 1.3',
  wonder: 'Muse Wonder 1.0 (Meta Model API)',
})

// Short model names for the static README diagram (docs/architecture.svg). The app shows HOW_MODEL_LABELS; full
// model IDs are in the README's Meta tooling table. An empty label shows only the "No Meta model" badge.
export const HOW_DIAGRAM_LABELS = Object.freeze({
  nws: 'National Weather Service',
  decision: 'Muse Spark Open (Baseten)',
  safety: 'Python rules',
  translation: 'Muse Spark 1.3',
  'read-aloud': 'Device voice',
  'ask-transcribe': 'Muse Voice Transcribe 1.0',
  'ask-answer': 'Muse Spark 1.3',
  'recovery-photos': '',
  sam: 'SAM 3.1',
  'image-analysis': 'Muse Spark 1.3',
  report: 'Muse Spark 1.3',
  'wonder-review': 'Muse Wonder 1.0',
})

export const HOW_NODES = [
  { id: 'nws', stepIndex: 0, modelLabel: HOW_MODEL_LABELS.nws, meta: false, infoIndex: 0 },
  { id: 'decision', stepIndex: 1, modelLabel: HOW_MODEL_LABELS.decision, meta: true, infoIndex: 1 },
  { id: 'safety', stepIndex: 2, modelLabel: HOW_MODEL_LABELS.safety, meta: false, infoIndex: 2 },
  { id: 'translation', stepIndex: 3, modelLabel: HOW_MODEL_LABELS.translation, meta: true, infoIndex: 3 },
  { id: 'read-aloud', stepIndex: 4, modelLabel: HOW_MODEL_LABELS.readAloud, meta: false, infoIndex: 4 },
  { id: 'ask-transcribe', stepIndex: 5, modelLabel: HOW_MODEL_LABELS.askTranscribe, meta: true, infoIndex: 5 },
  { id: 'ask-answer', stepIndex: 6, modelLabel: HOW_MODEL_LABELS.askAnswer, meta: true, infoIndex: 6 },
  { id: 'recovery-photos', stepIndex: 7, modelLabel: HOW_MODEL_LABELS.recoveryPhotos, meta: false, infoIndex: 7 },
  { id: 'sam', stepIndex: 8, modelLabel: HOW_MODEL_LABELS.sam, meta: true, infoIndex: 8 },
  { id: 'image-analysis', stepIndex: 9, modelLabel: HOW_MODEL_LABELS.imageAnalysis, meta: true, infoIndex: 9 },
  { id: 'report', stepIndex: 10, modelLabel: HOW_MODEL_LABELS.report, meta: true, infoIndex: 10 },
]

export const HOW_LANES = [
  {
    id: 'alerts',
    titleKey: 'howLaneAlerts',
    flows: [
      { id: 'alerts', nodeIds: ['nws', 'decision', 'safety', 'translation', 'read-aloud'] },
      { id: 'ask', titleKey: 'howAskLabel', nodeIds: ['ask-transcribe', 'ask-answer'] },
    ],
  },
  {
    id: 'recovery',
    titleKey: 'howLaneRecovery',
    flows: [{ id: 'recovery', nodeIds: ['recovery-photos', 'sam', 'image-analysis', 'report'] }],
  },
]

// Evaluation only: not a live step, so it is not in HOW_NODES (those match the howSteps / howNodeDescriptions /
// howNodeCosts lists) and not in any flow of HOW_LANES: nothing leads to it or away from it. Its text has its own keys.
export const HOW_EVAL_NODES = [
  { id: 'wonder-review', evalOnly: true, titleKey: 'howEvalStep', descriptionKey: 'howEvalDescription',
    costLabelKey: 'howEvalCostLabel', costKey: 'howEvalCost', modelLabel: HOW_MODEL_LABELS.wonder, meta: true },
]

export const ALL_HOW_NODES = [...HOW_NODES, ...HOW_EVAL_NODES]

// The section below the live diagram (dashed border, no arrows to the live path).
export const HOW_EVAL = {
  id: 'evaluation',
  titleKey: 'howEvalTitle',
  noteKey: 'howEvalNote',
  flows: [{ id: 'eval', nodeIds: ['wonder-review'] }],
}

// What a node shows in its box and details card: the live steps read the indexed lists, the evaluation node its own keys.
export const nodeTitle = (node, t) => (node.titleKey ? t[node.titleKey] : t.howSteps[node.stepIndex])
export const nodeDescription = (node, t) => (node.descriptionKey ? t[node.descriptionKey] : t.howNodeDescriptions[node.infoIndex])
export const nodeCostLabel = (node, t) => (node.costLabelKey ? t[node.costLabelKey] : t.howCallCost)
export const nodeCost = (node, t) => (node.costKey ? t[node.costKey] : t.howNodeCosts[node.infoIndex])
