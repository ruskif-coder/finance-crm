/**
 * Гейт сборки: каждый var(--токен) в коде объявлен в styles/globals.css.
 *
 * ЗАЧЕМ. Необъявленная переменная не роняет ни сборку, ни браузер — она делает
 * объявление невалидным «на этапе вычисления значения». Для `color` это означает
 * «наследовать от родителя», для `background` — «прозрачный». То есть опечатка в имени
 * токена выглядит не как ошибка, а как ЗАМЫСЕЛ: элемент просто другого цвета.
 *
 * Так и было найдено 13.09.2026: `--text-ghost` в pages/traffic/queue.js — пять мест,
 * в проекте не объявлен ни разу. Отключённая иконка красилась темнее включённых
 * соседей, а точки на двух плашках из четырёх не рисовались вовсе. Полгода это читалось
 * как особенность оформления. Ни eslint, ни сборка, ни детектор дизайна этого не видят.
 *
 * ЧТО ЛОВИМ. `var(--имя)` БЕЗ запасного значения, когда имя нигде не объявлено.
 * Запись `var(--имя, #f6f8fc)` пропускаем: она рисуется. Ей место в другом правиле —
 * хекс мимо палитры, — а тут речь о дырах.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']

// Объявления берём из globals.css. Сначала вырезаем УПОТРЕБЛЕНИЯ `var(--x`, иначе они
// сами попадут в список объявленных, и гейт станет всегда зелёным.
const css = readFileSync(join(ROOT, 'styles/globals.css'), 'utf8')
const declared = new Set(
  [...css.replace(/var\(\s*--[\w-]+/g, '').matchAll(/(--[\w-]+)\s*:/g)].map(m => m[1])
)

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.jsx?$/.test(name)) out.push(p)
  }
  return out
}

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const text = readFileSync(file, 'utf8')
    // `var(--имя)` или `var(--имя ,` — с запятой значит есть запасное значение.
    for (const m of text.matchAll(/var\(\s*(--[\w-]+)\s*([,)])/g)) {
      if (m[2] === ',') continue
      if (declared.has(m[1])) continue
      const line = (text.slice(0, m.index).match(/\n/g) || []).length + 1
      bad.push(`${relative(ROOT, file)}:${line}  ${m[1]}`)
    }
  }
}

if (bad.length) {
  console.error('\nВ коде есть CSS-переменные, которых нет в styles/globals.css.')
  console.error('Браузер не ругнётся: цвет унаследуется, фон станет прозрачным —')
  console.error('и это будет выглядеть как задуманное оформление.\n')
  bad.forEach(b => console.error('  ' + b))
  console.error('')
  process.exit(1)
}
console.log(`check-tokens: ${declared.size} токенов, все употребления объявлены — порядок`)
