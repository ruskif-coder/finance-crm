/**
 * Гейт экранов: сбой, быстрый клик и права (аудит 23.09.2026, этап 10).
 *
 * 1. ГОНКИ (10.1). Экраны с фильтрами грузят данные через `lib/useLatest`: иначе ответ
 *    старого фильтра, пришедший позже, ложится под подпись нового. Список экранов —
 *    `LATEST_PAGES`; новый экран с фильтрами добавляется сюда.
 *
 * 2. СБОЙ = ПУСТО (10.2). `.catch(() => setX([]))` — ошибка, нарисованная как «данных
 *    нет». Разрешено только для вспомогательных списков выпадашек, перечисленных в
 *    `EMPTY_CATCH_FROZEN` с числом вхождений: новое такое место роняет сборку, а
 *    исправленное — требует уменьшить счёт (храповик).
 *
 * 3. УДАЛЕНИЕ БЕЗ ПРАВА (10.4). Кнопка, зовущая del… / delete… / remove… / drop…, обязана
 *    стоять рядом (4 строки выше) с проверкой права — иначе человек без него видит
 *    кнопку, отвечающую 403. Старые места, где право проверено выше по разметке или
 *    удаляется строка ЧЕРНОВИКА формы (не сервер), заморожены поимённо в `DELETE_FROZEN`.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SKIP = new Set(['node_modules', '.next', 'public', 'scripts'])

const LATEST_PAGES = [
  'pages/finance/report.js', 'pages/finance/pnl.js', 'pages/finance/plan-fact.js',
  'pages/finance/balance.js', 'pages/finance/receivables.js', 'pages/finance/operations.js',
  'pages/sales/dashboard.js', 'pages/settings/audit.js',
]

// Вспомогательные списки выпадашек и справочники формы: пустой список при сбое там не
// выдаёт ложь о данных экрана. Основные данные экранов сюда не попадают.
const EMPTY_CATCH_FROZEN = {
  'pages/accounts/mp/[id].js': 4,        // версии, каталоги услуг/допов, подстановка брифа
  'pages/accounts/ord.js': 1,            // состояние подключения
  'pages/directory/advertisers.js': 1,   // список сейлзов для выпадашки
  'pages/sales/dashboard.js': 2,         // колокольчик уведомлений, каталог стадий
  'components/DealCreateForm.js': 2,     // выпадашки стадий и брендов
  'components/notify/TemplateEditor.jsx': 1,  // текстовая часть предпросмотра
}

// Право проверено выше по разметке (mayEdit/canEdit в обёртке), либо удаляется строка
// черновика формы до сохранения. Ключ — файл и фрагмент строки, без номера.
const DELETE_FROZEN = [
  ['pages/accounts/ord.js', 'dropPicked(false)'],
  ['pages/directory/counterparties/[id].js', 'delBank(i)'],
  ['pages/settings/services.js', 'deleteFormat(f)'],
  ['pages/settings/stages.js', 'delPhase(p._k)'],
  ['pages/settings/stages.js', 'delStage(p._k, s._k)'],
  ['components/deal/BriefFiles.jsx', 'remove(f)'],
  ['components/MaintenanceButton.jsx', "api.delete('/maintenance'"],
  ['components/mediaplan/MediaPlanBuilder.jsx', 'main.remove(r.id)'],
  ['components/mediaplan/MediaPlanBuilder.jsx', 'extras.remove(e.id)'],
  ['components/mobile/CounterpartyCardMobile.js', 'delBank(i)'],
  ['components/publishers/PublisherCard.jsx', 'api.deleteContact(c.id)'],
]

const EMPTY_CATCH = /\.catch\(\s*\(?[a-z_]*\)?\s*=>\s*\{?\s*set[A-Z]\w*\(\s*(\[\s*\]|\{\s*\}|null)\s*\)\s*\}?\s*\)/g
const DEL_CLICK = /onClick=\{[^}]*\b(del|delete|remove|drop)[A-Z]?\w*\(/
const PERM_NEAR = /can[A-Z]\w*|mayDelete|mayEdit|isAdmin|can\([^)]*'delete'/

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(js|jsx)$/.test(name)) out.push(p)
  }
  return out
}

const bad = []
const files = walk(ROOT).map(f => [relative(ROOT, f).split('\\').join('/'), readFileSync(f, 'utf8')])
const byName = Object.fromEntries(files)

for (const page of LATEST_PAGES) {
  if (!byName[page]) bad.push(`${page}: экрана нет — обновите список LATEST_PAGES`)
  else if (!byName[page].includes("from '@/lib/useLatest'") || !byName[page].includes('fresh()')) {
    // Мало импортировать — надо проверять `fresh()` после ответа (ревью 24.09.2026).
    bad.push(`${page}: данные грузятся без lib/useLatest (импорт и проверка fresh()) — старый ответ ляжет поверх нового`)
  }
}

for (const [rel, src] of files) {
  const n = (src.match(EMPTY_CATCH) || []).length
  const allowed = EMPTY_CATCH_FROZEN[rel] || 0
  if (n > allowed) bad.push(`${rel}: .catch обнуляет данные без сообщения (${n}, допущено ${allowed})`)
  if (n < allowed) bad.push(`${rel}: пустых .catch стало ${n} — уменьшите счёт в EMPTY_CATCH_FROZEN до ${n}`)

  const lines = src.split('\n')
  lines.forEach((line, i) => {
    if (!DEL_CLICK.test(line)) return
    if (DELETE_FROZEN.some(([f, frag]) => f === rel && line.includes(frag))) return
    const near = lines.slice(Math.max(0, i - 4), i + 1).join('\n')
    if (!PERM_NEAR.test(near)) bad.push(`${rel}:${i + 1}  удаление без проверки права рядом`)
  })
}

if (bad.length) {
  console.error('\ncheck-screens: сбой, гонка или права\n')
  for (const b of bad) console.error('  ' + b)
  process.exit(1)
}
console.log('check-screens: гонки, пустые сбои и права удаления — порядок')
