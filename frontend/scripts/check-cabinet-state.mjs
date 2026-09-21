/**
 * Гейт сборки: состояние кабинета описывается только в `lib/cabinetState.js`.
 *
 * ЗАЧЕМ. 21.09.2026 карта «состояние кабинета → цвет» оказалась записана дважды:
 * `STATE_TONE` на экране кабинетов и `CABINET_TONE` в реестре площадок. Разошлись
 * они в тот же день, когда появилась вторая: `приостановлен` был красным на одном
 * экране и оранжевым на другом, `активен` брал разные токены зелёного.
 *
 * Не падает ничего. Обе карты «работают», просто один и тот же кабинет выглядит на
 * двух экранах по-разному, и человек делает вывод, что это разные состояния.
 *
 * Тот же случай, что с тоном уведомления (см. `check-tone.mjs`), и лечится так же.
 *
 * ЧТО ЛОВИМ.
 *   1. объектную карту, ключами которой служат имена состояний («'черновик':»),
 *      где угодно, кроме `lib/cabinetState.js`;
 *   2. литеральный список состояний — вторую копию самого перечня, которая
 *      разойдётся при появлении четвёртого состояния.
 *
 * ЧЕГО НЕ ЛОВИМ. Сравнения вида `c.state === 'активен'`: это не копия правила, а
 * чтение значения. Запрещать их значило бы требовать обёртку на каждое условие.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']
const ALLOW = ['lib/cabinetState.js']

const STATES = ['черновик', 'приостановлен', 'активен']

// Ключ объекта: 'черновик': … — ТОЛЬКО в начале строки. Без якоря сюда попадал
// тернарник `tone={x ? 'активен' : 'приостановлен'}`: его хвост `'активен' :`
// выглядит ровно как ключ карты. Первая редакция гейта на этом и споткнулась,
// объявив дублем два обычных условия.
const asKey = (s) => new RegExp("^\\s*['\"]" + s + "['\"]\\s*:", "m")
// Элемент списка: 'черновик', … — рядом с запятой или скобкой.
const asItem = (s) => new RegExp("['\"]" + s + "['\"]\\s*[,\\]]")

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(js|jsx|mjs)$/.test(name)) out.push(p)
  }
  return out
}

const problems = []
for (const dir of DIRS) {
  let files
  try { files = walk(join(ROOT, dir)) } catch { continue }
  for (const file of files) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    if (ALLOW.includes(rel)) continue
    const src = readFileSync(file, 'utf8')
    // Две из трёх — чтобы не ловить одиночное упоминание состояния в тексте.
    const keys = STATES.filter((s) => asKey(s).test(src))
    const items = STATES.filter((s) => asItem(s).test(src))
    if (keys.length >= 2) {
      problems.push(`${rel}: своя КАРТА состояний кабинета (ключи: ${keys.join(', ')})`)
    } else if (items.length >= 3) {
      problems.push(`${rel}: свой СПИСОК состояний кабинета — берите CABINET_STATES`)
    }
  }
}

if (problems.length) {
  console.error('\nСостояние кабинета описано не в одном месте:\n')
  for (const p of problems) console.error('  · ' + p)
  console.error('\nОдин словарь — lib/cabinetState.js: cabinetState(state) отдаёт'
    + ' plashka, dot и hint, CABINET_STATES — перечень.\n')
  process.exit(1)
}
console.log('Состояние кабинета: один словарь, копий нет')
