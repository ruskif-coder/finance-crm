/**
 * Гейт сборки: тон уведомления читается только через `lib/tone.js`.
 *
 * ЗАЧЕМ. 14.09.2026 у тона было ДВА словаря: реестр событий говорил
 * `danger | warning | success | info`, всё остальное — `bad | warn | ok | info`.
 * Пересекались они на `info`, поэтому не падало ничего. Бэкенд свели к канону, ручки
 * стали отдавать новые слова — и два экрана со своими картами перестали находить цвет:
 *
 *   · виджет уведомлений на дашборде — маркер у всех строк стал синим, а красная
 *     подсветка срочной кнопки (`n.tone === 'danger'`) не срабатывала больше никогда;
 *   · каталог в настройках уведомлений — точка у всех событий, кроме `info`.
 *
 * Ничего из этого не падает и не пишет в консоль: цвет молча берётся из `|| accent`.
 * Бэкендный ратчет (`tests/test_tone_vocabulary.py`) фронт не видит — поэтому гейт здесь.
 *
 * ЧТО ЛОВИМ.
 *   1. объектную карту тона со СТАРЫМИ ключами (`danger:`/`warning:`/`success:` рядом
 *      с `info:`) где угодно, кроме `lib/tone.js`;
 *   2. сравнение поля тона со старым словом: `.tone === 'danger'` и подобные.
 *
 * ЧЕГО НЕ ЛОВИМ. Чужие шкалы: у экрана «Статус» свои `bad|warn|ok|idle`, у фильтра
 * стадий `tone: 'danger'` для «Сделка провалена», у журнала кабинета своя. Запрещать им
 * слово значило бы объявить чужую шкалу ошибкой, поэтому ищется именно КАРТА ЦВЕТОВ
 * уведомления и сравнение с полем `tone` объекта уведомления.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']
const ALLOW = ['lib/tone.js']

// Экраны с собственной, не уведомленческой шкалой тона — названы поимённо, с причиной.
const OWN_SCALE = [
  'pages/settings/system.js',        // bad | warn | ok | idle — состояние проверок
  'pages/traffic/queue.js',          // тон плашки факта в очереди трафика
  'components/deal/Section.js',      // тон факта в карточке сделки
  'components/salesTableKit.js',     // «Сделка провалена» в фильтре стадий
  'components/DiadocImport.js',      // состояния импорта документов
  'components/creatives/AssemblyCreatives.jsx',
  'pages/accounts/dashboard.js',     // CTA_TONE — тон действия очереди
]

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.jsx?$/.test(name)) out.push(p)
  }
  return out
}

const OLD_MAP = /(danger|warning|success)\s*:\s*['"`v]/
const OLD_CMP = /\.tone\s*[=!]==?\s*['"](danger|warning|success)['"]/

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    if (ALLOW.includes(rel) || OWN_SCALE.includes(rel)) continue
    const text = readFileSync(file, 'utf8')
    text.split('\n').forEach((line, i) => {
      const t = line.trimStart()
      if (t.startsWith('*') || t.startsWith('//')) return
      // карта тона: старый ключ в объекте, где рядом есть `info:`
      if (OLD_MAP.test(line) && /\binfo\s*:/.test(text)) {
        bad.push(`${rel}:${i + 1} — карта тона со старыми ключами`)
      } else if (OLD_CMP.test(line)) {
        bad.push(`${rel}:${i + 1} — сравнение тона со старым словом`)
      }
    })
  }
}

if (bad.length) {
  console.error('check-tone: старые слова тона на фронте\n  · ' + bad.join('\n  · ')
    + "\n\n  Канон — bad | warn | ok | info. Цвет и приведение: import { TONE, toneOf } from '@/lib/tone'")
  process.exit(1)
}
console.log('check-tone: тон везде через lib/tone — порядок')
