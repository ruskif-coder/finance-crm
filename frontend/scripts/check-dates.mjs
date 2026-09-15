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
 * ЧЕГО НЕ ЛОВИМ. `new Date()` без аргументов, конструирование из чисел
 * (`new Date(y, m, 1)`), арифметику по календарным дням — там часовых поясов нет.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components']
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
