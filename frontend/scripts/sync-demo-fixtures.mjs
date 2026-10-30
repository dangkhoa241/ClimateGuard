// Copies the demo replay fixtures the screens need offline from the backend data into src/.
// Run after backend/scripts/build_demo_translations.py or save_demo_replays.py:  node scripts/sync-demo-fixtures.mjs
import { readFileSync, writeFileSync } from 'node:fs'

const data = (name) => new URL(`../../backend/src/climateguard/data/${name}`, import.meta.url)
const out = (name) => new URL(`../src/${name}`, import.meta.url)
const translations = JSON.parse(readFileSync(data('demo_translations.json'), 'utf8'))
const saved = JSON.parse(readFileSync(data('demo_saved.json'), 'utf8')).flood_2023

writeFileSync(out('demoTranslations.json'), JSON.stringify(translations, null, 2) + '\n')
writeFileSync(out('demoSample.json'), JSON.stringify({
  event: 'flood_2023',
  place: 'Planada, CA',
  ts: saved.ran_at,
  action: saved.action,
  reason: saved.reason,
  model_calls: saved.model_calls,
  cost_usd: saved.cost_usd,
  safety_checks_passed: saved.action === 'sent', // a sent alert has passed the code safety rules
  alerts: saved.sent.map((a) => ({ hazard: a.hazard, severity: a.severity, messages: translations.flood_2023[a.hazard] })),
}, null, 2) + '\n')
