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
