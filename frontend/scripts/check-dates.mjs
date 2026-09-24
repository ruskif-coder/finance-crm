/**
 * Гейт сборки: время с сервера разбирается только через `lib/dates`.
 *
 * ЗАЧЕМ. Наивный `datetime` приезжает с сервера БЕЗ суффикса `Z` — строкой вида
 * «2026-09-14T19:30:00», — а хранится в UTC. `new Date()` читает такую строку как
 * МЕСТНОЕ время, и момент показывается на три часа в прошлом. Ошибка правдоподобная:
 * время выглядит настоящим, просто не тем, и потому не замечается ни в тестах, ни
 * глазами.
 *
 * Перепись 14.09.2026 нашла шесть мест, где это чинили ЛОКАЛЬНО — каждое своей копией
 * одного и того же регулярного выражения, — и одиннадцать, где не чинили вовсе. Гейт
 * поставлен, чтобы двенадцатого не появилось.
 *
 * ЧТО ЛОВИМ.
 *   1. `new Date(` от переменной с временем (`*_at`, `*At`, `hour`, `iso`, `str`);
 *   2. локальную копию суффикса `Z` — `+ 'Z'` рядом с `new Date`.
 *
 *   3. «сегодня» через `new Date().toISOString().slice(…)` (дополнено 23.09.2026). Это
 *      дата ПО ГРИНВИЧУ: с полуночи до трёх ночи по Москве новая операция получала
 *      вчерашнее число, а имя выгрузки — вчерашний день. Для «сегодня» есть
 *      `todayMsk()`, для метки в имени файла — `fileStamp()`.
 *
 * ЧЕГО НЕ ЛОВИМ. `new Date()` без аргументов, конструирование из чисел
 * (`new Date(y, m, 1)`), арифметику по календарным дням — там часовых поясов нет.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']
const ALLOW = ['lib/dates.js']

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.jsx?$/.test(name)) out.push(p)
  }
  return out
}

// Аргумент, похожий на время с сервера: имя кончается на _at / At, либо это hour/iso/str.
const TIMEY = /new Date\(\s*[^)]*?(_at\b|At\b|\bhour\b|\biso\b|\bstr\b|\bsince\b)/
const OWN_Z = /new Date\([^)]*\+\s*'Z'|\+\s*'Z'\s*\)/
const UTC_TODAY = /new Date\(\)\.toISOString\(\)\.(slice|substring|split)\(/
// «по месяц» = 28-е: терялись 29–31 числа (аудит 23.09.2026, 6.H4) — нужен monthEnd().
const DAY_28 = /\+\s*'-28'/
// Часы и минуты вырезкой из метки — это UTC, отставание на 3 часа (лента кабинетов, 24.09.2026).
const TIME_SLICE = /\.slice\(\s*11\s*,\s*16\s*\)|\.substring\(\s*11\s*,\s*16\s*\)/

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    if (ALLOW.includes(rel)) continue
    const lines = readFileSync(file, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (line.trimStart().startsWith('*') || line.trimStart().startsWith('//')) return
      if (TIMEY.test(line)) bad.push(`${rel}:${i + 1} — new Date() от метки времени`)
      else if (OWN_Z.test(line)) bad.push(`${rel}:${i + 1} — своя копия суффикса 'Z'`)
      else if (UTC_TODAY.test(line)) bad.push(`${rel}:${i + 1} — «сегодня» по Гринвичу (toISOString)`)
      else if (DAY_28.test(line)) bad.push(`${rel}:${i + 1} — конец месяца 28-м числом, нужен monthEnd()`)
      else if (TIME_SLICE.test(line)) bad.push(`${rel}:${i + 1} — часы вырезаны из UTC-строки, нужен fmtDayTime/fmtTime`)
    })
  }
}

if (bad.length) {
  console.error(
    'check-dates: время с сервера разбирается в обход lib/dates\n  · ' + bad.join('\n  · ')
    + '\n\n  Момент (*_at)      → fmtDateTime / fmtTime / fmtDateOfMoment / ago / daysSince'
    + '\n  Календарный день   → fmtDate / fmtDateShort / calendarDate')
  process.exit(1)
}
console.log('check-dates: время с сервера везде через lib/dates — порядок')
