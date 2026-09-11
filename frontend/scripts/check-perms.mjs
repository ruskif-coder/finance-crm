/**
 * Гейт сборки: первым аргументом проверки прав идёт СНИМОК прав, а не имя раздела.
 *
 * ЗАЧЕМ. Сигнатура — `can(perms, section, action = 'view')` (`lib/auth.js`). Вызов
 * `can('traffic_dashboard', 'edit')` не падает и не ругается: в `perms` уезжает строка
 * раздела, в `section` — действие, выражение `'traffic_dashboard'['edit']` даёт
 * `undefined`, и проверка возвращает **false всем, кроме админа** — у него внутри `can`
 * свой обход по роли.
 *
 * ЧЕМ ЭТО БЫЛО. На 11.09.2026 так были записаны десять вызовов в шести файлах, и пять
 * живых учёток с правом управления кампаниями не видели НИ ОДНОЙ кнопки: ни старта РК,
 * ни статусов площадок, ни вердиктов в очереди. Со стороны это выглядит не как поломка
 * прав, а как «на экране просто нет такой кнопки», поэтому и прожило с конца августа.
 *
 * ПОЧЕМУ ГЕЙТ, А НЕ ЗАМЕТКА. Дефект невидим глазами — админ, который его чинит, видит
 * всё, — и не ловится ни одним прибором бэкенда: сервер права проверяет правильно, врёт
 * только экран. Единственное место, где это можно поймать дёшево, — сборка.
 *
 * ЧТО СЧИТАЕТСЯ ОШИБКОЙ. Только строковый литерал первым аргументом: снимок прав строкой
 * не бывает. Два аргумента сами по себе законны — действие по умолчанию `view`, и
 * `can(perms, 'dashboard')` верно. Комментарии из исходника вырезаются: про `can()` в
 * этом проекте написано в десятке пояснений, и ловить их незачем.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['components', 'pages', 'lib']
const BACKSLASH = String.fromCharCode(92)
const NL = String.fromCharCode(10)

/**
 * Вырезает построчные и блочные комментарии, не трогая их внутри строк.
 * Переводы строк сохраняются, чтобы номера строк в отчёте остались настоящими.
 */
function stripComments(src) {
  let out = ''
  let quote = null
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    const next = src[i + 1]
    if (quote) {
      out += ch
      if (ch === quote && src[i - 1] !== BACKSLASH) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; out += ch; continue }
    if (ch === '/' && next === '/') {
      while (i < src.length && src[i] !== NL) { out += ' '; i++ }
      out += NL
      continue
    }
    if (ch === '/' && next === '*') {
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) {
        out += src[i] === NL ? NL : ' '
        i++
      }
      out += '  '
      i++
      continue
    }
    out += ch
  }
  return out
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(js|jsx)$/.test(name)) out.push(p)
  }
  return out
}

/** Разбор аргументов вызова с учётом вложенных скобок, строк и запятых внутри них. */
function topLevelArgs(src, openIdx) {
  let depth = 0
  let quote = null
  let arg = ''
  const args = []
  for (let i = openIdx; i < src.length; i++) {
    const ch = src[i]
    if (quote) {
      arg += ch
      if (ch === quote && src[i - 1] !== BACKSLASH) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; arg += ch; continue }
    if (ch === '(' || ch === '[' || ch === '{') { depth++; if (depth > 1) arg += ch; continue }
    if (ch === ')' || ch === ']' || ch === '}') {
      depth--
      if (depth === 0) { args.push(arg.trim()); return args }
      arg += ch
      continue
    }
    if (ch === ',' && depth === 1) { args.push(arg.trim()); arg = ''; continue }
    arg += ch
  }
  return null            // скобка не закрылась — не наше дело, пусть ругается сборщик
}

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const src = stripComments(readFileSync(file, 'utf8'))
    const re = /(^|[^\w.])can\s*\(/g
    let m
    while ((m = re.exec(src)) !== null) {
      const open = m.index + m[0].length - 1
      const args = topLevelArgs(src, open)
      if (!args || args.length === 0) continue
      if (/^['"`]/.test(args[0])) {
        const line = src.slice(0, m.index).split(NL).length
        bad.push(`${relative(ROOT, file)}:${line}  can(${args.join(', ')})`)
      }
    }
  }
}

if (bad.length) {
  console.error(NL + 'Права проверяются неверно — сигнатура can(perms, section, action):' + NL)
  for (const b of bad) console.error('  ' + b)
  console.error(NL + 'Первым аргументом идёт СНИМОК прав (getPermissions()), а не имя раздела.')
  console.error('Со строкой вместо снимка проверка возвращает false всем, кроме админа,')
  console.error('и экран молча остаётся без кнопок у тех, у кого право есть.' + NL)
  process.exit(1)
}
console.log('check-perms: снимок прав первым аргументом везде — порядок')
