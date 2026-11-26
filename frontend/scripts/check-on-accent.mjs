/**
 * Гейт сборки: белый литерал в `color:` — только ролью `--on-accent`.
 *
 * ЗАЧЕМ. 26.11.2026 владелец прислал скриншот Фин. отчёта в NAVY-ночи: активный сегмент
 * залит `var(--accent)` (в ночной теме это #F7FAFC — почти белый), а подпись на нём была
 * литералом `#fff`. Контраст 1,05:1 — подпись есть и её нет. В светлой теме тот же код
 * нормален (10,96:1), поэтому днём дефекта не видно, а ночью это «опять баги».
 *
 * Роль `--on-accent` объявлена в globals.css:78 и переопределена в navy.css по темам
 * И ЗОНАМ (navy: #F7FAFC, тёмная зона светлой темы: #101820, navy-dark: #101820,
 * светлая зона ночной темы: #F7FAFC). Она и означает «чем писать на accent / hot /
 * text-primary». К 26.11.2026 её использовали 72 файла — одиннадцать мест отстали.
 *
 * ЧТО ЛОВИМ. Куски строки/стиля, которые НАЧИНАЮТСЯ с `color:` и содержат белый литерал:
 *   `color: '#fff'`, `color: canSubmit ? '#fff' : …`, `color:#FFFFFF` в CSS-шаблоне,
 *   `color: 'white'`, `rgba(255,255,255,…)`.
 * Соседний `background: 'var(--accent)'` на той же строке не спасает: именно так и было.
 *
 * ЧЕГО НЕ ЛОВИМ.
 *   · `background: '#fff'` — белая подложка под документ законна и от темы не зависит;
 *   · печать и «бумажные» поверхности — там белый это лист или постоянная синяя кнопка,
 *     такие файлы перечислены поимённо с причиной;
 *   · `color: 'var(--on-accent)'` и любой другой токен.
 *
 * ПОЧЕМУ ГЕЙТ, А НЕ ВНИМАНИЕ. `check-tokens` проверяет только «объявлен ли var(--…)»,
 * `check-tone` — словарь тонов. Литерал `#fff` легален для всех: ни eslint, ни сборка его
 * не видят, а глазами дефект ловится лишь в одной теме из пяти.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']

// Белый здесь — не роль темы, а поверхность документа. Каждая строка — с причиной.
const ALLOW = {
  'components/annex/AnnexDocument.jsx': 'печать ДС: белый текст на постоянной синей шапке таблицы (#4472C4)',
  'pages/accounts/mp/pdf/[id].js': 'страница печати МП: белый текст на постоянной синей кнопке (#4F6CE6)',
}

const WHITE = /(?:#fff\b|#ffffff\b|\bwhite\b|rgba?\(\s*255\s*,\s*255\s*,\s*255)/i
// Куски, начинающиеся с `color:` — `background-color:` и `border-color:` под это не попадают.
const COLOR_CHUNK = /^color\s*:/i

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
    if (ALLOW[rel]) continue
    const text = readFileSync(file, 'utf8')
    text.split('\n').forEach((line, i) => {
      const t = line.trimStart()
      if (t.startsWith('*') || t.startsWith('//')) return          // комментарии не код
      for (const chunk of line.split(/[,;}]/)) {
        const c = chunk.trim()
        if (!COLOR_CHUNK.test(c) || !WHITE.test(c)) continue
        bad.push(`${rel}:${i + 1}  ${c.slice(0, 90)}`)
        return
      }
    })
  }
}

if (bad.length) {
  console.error('\nБелый литерал в `color:` — в тёмной теме он невидим на светлой заливке.')
  console.error('В ночной теме `--accent` это #F7FAFC: белым по белому даёт 1,05:1.')
  console.error('Пишите цветом роли: `var(--on-accent)` (она уже знает про тему и зону).\n')
  bad.forEach(b => console.error('  ' + b))
  console.error('\nЕсли белый тут — поверхность документа (печать), добавьте файл в ALLOW с причиной.\n')
  process.exit(1)
}
