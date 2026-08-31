/**
 * Гейт: хук не объявляется ПОСЛЕ раннего выхода из компонента.
 *
 * React сверяет число хуков между рендерами. Компонент, который на первом проходе
 * выходит через `if (!ready) return null`, а ниже объявляет `useMemo`, отдаёт на разных
 * рендерах разное их число — и падает не там, где ошибка, а целиком:
 *
 *     Minified React error #310 … at Object.useMemo
 *
 * В минифицированной сборке это стек из букв `ah`, `aV`, `eh` — по нему не видно ни
 * файла, ни строки, ни того, что дело в порядке объявлений. Экран при этом белый.
 *
 * Поймано 30.08.2026: при добавлении выбора площадки два `useMemo` встали ниже
 * `if (!ready) return null`, и кабинет перестал открываться целиком.
 *
 * В ядре это ловит eslint (`react-hooks/rules-of-hooks` из `next/core-web-vitals`).
 * У кабинета линтера нет намеренно — он собран без dev-зависимостей, — поэтому правило
 * держит отдельный гейт, как и правило про цвета.
 *
 * ЧТО ПРОВЕРЯЕТСЯ. Внутри объявления компонента (`function Имя(` с заглавной буквы на
 * нулевом отступе) ищется первый `return` НА ВЕРХНЕМ УРОВНЕ ТЕЛА — это ровно два
 * пробела отступа, вложенные лежат глубже. Любое объявление хука после него —
 * нарушение. Проверка формальная и держится на отступах, зато не требует парсера и
 * ловит именно ту форму, которая ломает экран.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SKIP_DIRS = new Set(['node_modules', '.next', 'public', 'scripts'])

const COMPONENT = /^(export default )?function [A-Z]\w*\s*\(/
const TOP_RETURN = /^ {2}(?:if \(.*\) )?return\b/
const HOOK = /^ {2}(?:const|let)\s+.*=\s*use[A-Z]\w*\(/
const END = /^\}/

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.js') || name.endsWith('.jsx')) out.push(full)
  }
  return out
}

const bad = []
for (const file of walk(ROOT)) {
  const lines = readFileSync(file, 'utf8').split('\n')
  let component = null
  let returnedAt = 0
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (COMPONENT.test(line)) {
      component = line.match(/function ([A-Z]\w*)/)[1]
      returnedAt = 0
      continue
    }
    if (!component) continue
    if (END.test(line)) { component = null; continue }
    if (!returnedAt && TOP_RETURN.test(line)) { returnedAt = i + 1; continue }
    if (returnedAt && HOOK.test(line)) {
      bad.push({
        rel: relative(ROOT, file).replace(/\\/g, '/'),
        component, returnedAt, line: i + 1, text: line.trim().slice(0, 70),
      })
    }
  }
}

if (bad.length) {
  console.error('\ncheck-hooks: хук объявлен после раннего выхода\n')
  for (const b of bad) {
    console.error(`  ${b.rel}:${b.line}  в компоненте ${b.component}`)
    console.error(`    ${b.text}`)
    console.error(`    выход из компонента уже был на строке ${b.returnedAt}`)
  }
  console.error('\n  Поднимите объявление ВЫШЕ всех `return`. React сверяет число хуков')
  console.error('  между рендерами; при разном числе падает весь экран, а сообщение')
  console.error('  приходит минифицированным и без имени файла.\n')
  process.exit(1)
}
console.log('check-hooks: хуки объявлены до выходов — порядок')
