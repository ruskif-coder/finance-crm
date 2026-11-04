/**
 * Гейт сборки: на десктопе месяц выбирается через `components/MonthInput`, а не `<input type="month">`.
 *
 * ЗАЧЕМ. Десктопный Safari поля месяца не знает и рисует обычное текстовое: календаря нет, месяц надо вписывать
 * руками как «2025-12», а onChange срабатывает на каждой букве недописанного значения (владелец 03.11.2026:
 * «в сафари ломается календарь выбора периода»). Проверено в WebKit: `input.type` у такого поля — 'text'.
 * В Chrome всё работает, поэтому поломка не видна ни в обходе экранов, ни при ручной проверке.
 *
 * ЧЕГО НЕ ЛОВИМ. Мобильные экраны (`components/mobile/`, мобильная панель сделок) намеренно остаются на родном поле:
 * в iOS у него есть свой выбор месяца, а мобилку правим только по указанию владельца.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']
const ALLOW = [/^components\/mobile\//, /^components\/sales\/DealsMobileControls\.js$/]
const MONTH = /type=["']month["']|type:\s*["']month["']/

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(jsx?|mjs)$/.test(name)) out.push(p)
  }
  return out
}

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    if (ALLOW.some(re => re.test(rel))) continue
    readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
      const t = line.trimStart()
      if (t.startsWith('//') || t.startsWith('*')) return
      if (MONTH.test(line)) bad.push(`${rel}:${i + 1}`)
    })
  }
}

if (bad.length) {
  console.error(`Поле месяца мимо MonthInput — в десктопном Safari это текстовое поле без календаря (${bad.length}):`)
  bad.forEach(b => console.error('  · ' + b))
  console.error('Замена: import MonthInput from \'@/components/MonthInput\' — те же value / onChange.')
  process.exit(1)
}
console.log('Поля месяца: все через MonthInput')
