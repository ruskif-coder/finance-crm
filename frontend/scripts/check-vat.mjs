/**
 * Гейт: ставка НДС не зашивается во фронт числом.
 *
 * Ставка фиксируется на дату расчёта (правило владельца 23.09.2026): до 2026 года было
 * 20 %, с 2026 — 22 %, и прошлое не пересчитывается. Ставка живёт у записи — у версии
 * медиаплана (`vat_rate`), у сделки (`vat_rate` карточки), у нашего юрлица для новых
 * расчётов (`vat_rate_income`). Константа `VAT = 0.22` в компоненте печатает план 2025
 * года по 22 %: так было в PDF медиаплана, который уходит клиенту, — ревью 23.09.2026
 * нашло это уже ПОСЛЕ того, как я доложил, что PDF считает по ставке плана.
 *
 * Храповик, как `check-inline-components`: список ниже заморожен 23.09.2026 и должен
 * только сокращаться. Каждая строка — место, которое ещё берёт ставку из константы.
 */
import { readdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'

const ROOTS = ['components', 'pages', 'lib']

// Форма новой сделки, бриф бренда и доска сделок переведены на ставку с сервера тем же
// вечером; два неподключённых файла карточки сделки удалены по решению владельца.
// Заморозка пуста: зашитая ставка не допускается нигде.
const FROZEN = new Set([])

// `const VAT = 0.22`, `const VAT_RATE = 1.22`, `const NDS = 22` — числовая константа ставки.
const DECL = /\bconst\s+(VAT|NDS|VAT_RATE|VAT_PCT|NDS_RATE)\s*=\s*\d/

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(js|jsx|mjs)$/.test(name)) yield p
  }
}

const found = new Map()
for (const root of ROOTS) {
  for (const file of walk(root)) {
    const rel = file.split('\\').join('/')
    readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
      if (DECL.test(line) && !found.has(rel)) found.set(rel, i + 1)
    })
  }
}

const fresh = [...found].filter(([rel]) => !FROZEN.has(rel))
const gone = [...FROZEN].filter(rel => !found.has(rel))

if (fresh.length) {
  console.error('check-vat: ставка НДС зашита числом — брать её у записи (vat_rate плана/сделки, vat_rate_income юрлица):')
  for (const [rel, line] of fresh) console.error(`  ${rel}:${line}`)
  process.exit(1)
}
if (gone.length) {
  console.error('check-vat: место исправлено — уберите его из FROZEN, чтобы храповик не откатился:')
  for (const rel of gone) console.error(`  ${rel}`)
  process.exit(1)
}
console.log(`check-vat: новых зашитых ставок нет (в заморозке ${FROZEN.size})`)
