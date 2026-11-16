/**
 * Гейт: классы и id без «рекламных» имён (16.11.2026). Экран «Закрывающие документы» пришёл хендоффом с классами `ad-root`,
 * `ad-btn`… — блокировщики рекламы прячут `[class^="ad-"]` / `.ad-*`, и у части машин экран был пуст при живых данных
 * (шапка на месте, текст есть в DOM, `display: none`). На одной машине открывалось, на соседней — нет: фильтры разные.
 *
 * Ловит в .js/.jsx: `className="ad-…"`, `id="ad-…"`, селекторы `.ad-…` / `#ad-…` в строках стилей; то же с `ads-`, `advert`,
 * `banner-` в начале имени. Имена анимаций (`@keyframes adRise`) не трогает — блокировщики режут элементы, а не анимации.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SKIP = new Set(['node_modules', '.next', 'public', 'scripts'])
const NAME = '(?:ad|ads|advert\\w*|banner)[-_]\\w'
const RULES = [
  new RegExp(`\\b(?:className|id)=["'\`{][^"'\`}]*?(?:^|[\\s"'\`{])${NAME}`),
  new RegExp(`(?:^|[\\s"'\`(,}])([.#]${NAME})`),
]

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
for (const file of walk(ROOT)) {
  const rel = relative(ROOT, file).split('\\').join('/')
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    if (/^\s*(\/\/|\*|\/\*)/.test(line)) return
    if (RULES.some(r => r.test(line))) bad.push(`${rel}:${i + 1}  ${line.trim().slice(0, 110)}`)
  })
}
if (bad.length) {
  console.error('\ncheck-adblock: «рекламные» имена классов — блокировщик спрячет элемент (переименуйте, напр. ad- → acc-)\n')
  for (const b of bad) console.error('  ' + b)
  process.exit(1)
}
console.log('check-adblock: рекламных имён классов нет — порядок')
