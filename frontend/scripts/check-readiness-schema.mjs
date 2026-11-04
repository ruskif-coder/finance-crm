/**
 * Гейт сборки: окно контрагента держит одну схему полей и не расходится с базой (план 2026-11-05, Task 7).
 *
 * ЗАЧЕМ. Пакет дизайнера пришёл со своими списками значений и с полями, которых у контрагента нет
 * (спецификация, «Сверка схемы дизайнера с базой»). Свой список форматов в окне — это вторая копия
 * `lib/contractTerms`: сохранённое из окна значение не совпадёт буквально с тем, что сравнивают
 * подбор шаблона и пакет закрытия, и ДС молча не соберётся. Поэтому:
 *
 *   · формат, условие отсрочки, пролонгация и канал — только ссылкой на `lib/contractTerms`;
 *   · у агентства нет блока «Рекламодатели и бренды» (решение владельца 04.11.2026: они независимы);
 *   · в блоке «Юрлицо» нет краткого имени, условия отсрочки и формы оплаты — это поля других сущностей;
 *   · в компоненте нет `<select` (выбор из списка — только ValuePopover) и хекс-цветов (только var(--*)).
 */
import { readFileSync } from 'node:fs'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIR = `${ROOT}components/counterparty/readiness/`
const schema = readFileSync(`${DIR}readinessSchema.js`, 'utf8')
const comp = readFileSync(`${DIR}CounterpartyReadiness.jsx`, 'utf8')
const errors = []

const LISTS = { format: 'COOPERATION_FORMATS', term_cond: 'PAYMENT_TERM_CONDITIONS', prolongation: 'PROLONGATION_OPTIONS', channel: 'ISSUE_CHANNELS' }
for (const [k, ident] of Object.entries(LISTS)) {
  const lines = schema.split('\n').filter(l => l.includes(`k: '${k}'`) && l.includes('opts:'))
  for (const l of lines) if (!new RegExp(`opts:\\s*${ident}\\b`).test(l)) errors.push(`поле «${k}»: список значений не из lib/contractTerms (${ident})`)
}
if (Object.values(LISTS).some(i => schema.includes(i)) && !/from\s+['"][^'"]*lib\/contractTerms['"]/.test(schema))
  errors.push('readinessSchema.js не импортирует lib/contractTerms')

const ad = schema.split('\n').find(l => /id:\s*'ad'/.test(l)) || ''
if (/kinds:\s*\[[^\]]*'agency'/.test(ad)) errors.push("блок «ad» доступен агентству — агентство и рекламодатель независимы")

const cp = (schema.match(/\n\s*cp:\s*\[([\s\S]*?)\n\s*\],\n/) || [, ''])[1]
for (const k of ['short_name', 'term_cond', 'pay_form']) if (cp.includes(`k: '${k}'`)) errors.push(`блок «Юрлицо»: поля «${k}» у контрагента нет`)

if (/<select\b/.test(comp)) errors.push('в компоненте <select — выбор из списка только через ValuePopover')
const hex = comp.split('\n').map((l, i) => [i + 1, l]).filter(([, l]) => /#[0-9A-Fa-f]{3,8}\b/.test(l.replace(/\/\/.*$/, '')))
for (const [n] of hex) errors.push(`CounterpartyReadiness.jsx:${n}: хекс-цвет — только var(--*)`)

if (errors.length) {
  console.error(`check-readiness-schema: ${errors.length}\n  ` + errors.join('\n  '))
  process.exit(1)
}
console.log('check-readiness-schema: ok')
