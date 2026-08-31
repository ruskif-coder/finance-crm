/**
 * Гейт: компонент не объявляется внутри рендера другого компонента.
 *
 * Объявленный внутри, он пересоздаётся как НОВЫЙ тип на каждый рендер родителя, и React
 * при каждом рендере размонтирует поддерево и монтирует заново. Симптомы разные, корень
 * один, и оба уже случались в этом проекте:
 *
 *   · поле ввода теряет фокус после каждого символа — компонент-обёртка над `input`
 *     пересоздавался вместе с состоянием формы;
 *   · выпадающее меню шапки открывалось и тут же гасло при наведении СНИЗУ (31.08.2026):
 *     панель уничтожалась и создавалась заново, `mouseleave` от удаляемого узла запускал
 *     закрытие, а `mouseenter` на новый без движения мыши не приходил. Сверху работало —
 *     там мышь продолжает двигаться и успевает переоткрыть.
 *
 * Гейт устроен ХРАПОВИКОМ, как `KNOWN_SILENT` в приборах уведомлений: список ниже
 * заморожен 31.08.2026 и должен только сокращаться. Требовать переписать все одиннадцать
 * сегодня — не задача этого гейта; его дело в том, чтобы четырнадцатого не появилось.
 *
 * Почему не eslint-правило: `react/no-unstable-nested-components` требует плагина и
 * настройки под наш конфиг, а здесь нужен ровно один запрет и понятный текст ошибки.
 */
import { readdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'

const ROOTS = ['components', 'pages']

/**
 * Замороженный список. Формат: `путь:имя`.
 *
 * Каждая строка — компонент, объявленный внутри другого. Убирать их по одному, вынося
 * объявление на уровень модуля и передавая нужное пропсами; строка тогда уходит отсюда.
 * Первым уехал `Section` из `components/Nav.js` — он и стоил бага с меню.
 */
const FROZEN = new Set([
  'components/mobile/DealCardList.js:Row',
  'pages/accounts/mp/index.js:EditCell',
  'pages/directory/contracts.js:SortIcon',
  'pages/directory/contracts.js:Head',
  'pages/directory/counterparties/index.js:HeadCell',
  'pages/finance/balance.js:SortIcon',
  'pages/finance/balance.js:Section',
  'pages/finance/operations.js:HeadCard',
  'pages/finance/plan-fact.js:SummaryCard',
  'pages/finance/pnl.js:SummaryRow',
  'pages/finance/report.js:TotalRow',
])

// Объявление с ОТСТУПОМ — то есть внутри чего-то. Имя с заглавной и хотя бы одной
// строчной: `GRID`, `COLS`, `CAP` — это данные и стили, а не компоненты.
const DECL = /^[ \t]+(?:const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:\(|function\b)|function\s+([A-Z][A-Za-z0-9_]*)\s*\()/

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(js|jsx)$/.test(name)) yield p
  }
}

const found = []
for (const root of ROOTS) {
  for (const file of walk(root)) {
    const rel = file.split('\\').join('/')
    const lines = readFileSync(file, 'utf8').split('\n')
    lines.forEach((line, i) => {
      const m = DECL.exec(line)
      if (!m) return
      const name = m[1] || m[2]
      if (!/[a-z]/.test(name) || name.length < 2) return   // ИМЕНА-КОНСТАНТЫ и односимвольные
      // Компонент, а не хелпер: где-то ниже он отдаёт разметку. Двенадцати строк хватает
      // и на короткую стрелку `=> (<div>`, и на тело с `return (` через пару проверок, и
      // на тернарник `=> a ? <X/> : <Y/>`. Хелперы вроде `(a, b) => a + b` разметки не
      // содержат и сюда не попадают.
      const head = lines.slice(i, i + 12).join('\n')
      if (!/<[A-Za-z][A-Za-z0-9.]*[\s/>]/.test(head)) return
      found.push({ key: `${rel}:${name}`, file: rel, line: i + 1, name })
    })
  }
}

const fresh = found.filter(f => !FROZEN.has(f.key))
const gone = [...FROZEN].filter(k => !found.some(f => f.key === k))

if (fresh.length) {
  console.error('\nКомпонент объявлен внутри другого компонента:\n')
  for (const f of fresh) console.error(`  ${f.file}:${f.line}  ${f.name}`)
  console.error(`
Такой компонент пересоздаётся на каждый рендер родителя: React размонтирует поддерево и
монтирует заново. Поле теряет фокус после каждого символа, выпадашка гаснет сразу после
открытия, состояние внутри обнуляется.

Вынесите объявление на уровень модуля, а нужное передайте пропсами.
`)
  process.exit(1)
}

if (gone.length) {
  console.error('\nВ замороженном списке остались разобранные места — уберите их из FROZEN:\n')
  for (const k of gone) console.error(`  ${k}`)
  console.error('\nСписок долгов обязан сокращаться, иначе он перестаёт быть списком долгов.\n')
  process.exit(1)
}

console.log(`check-inline-components: ok (в заморозке ${FROZEN.size})`)
