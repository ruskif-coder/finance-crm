/**
 * Гейт сборки: в `style` не попадает функция-стиль из общего кита.
 *
 * ЗАЧЕМ. В `components/salesTableKit.js` часть стилей — ФУНКЦИИ: `btn(primary)`,
 * `btnSm(p)`, `inpSm(w)`, `selSm(w)`, `ctaStyle(kind)`. Забыть скобки легко, а
 * последствия у двух написаний разные, и оба тихие:
 *
 *   · `style={btn}` — React бросает ошибку #62 («style ожидает объект») и роняет
 *     ВСЮ страницу в белый экран. Не строку, не компонент — страницу целиком;
 *   · `style={{ ...btn }}` — не падает вовсе. У функции нет перечисляемых
 *     собственных свойств, поэтому расплыв даёт пустой объект: кнопка просто
 *     остаётся без базового вида, и это списывают на «так и было задумано».
 *
 * ЧТО СЛУЧИЛОСЬ (22.09.2026). Так были написаны шесть мест в трёх файлах, в том
 * числе сам экран заявок о сбоях и форма их подачи. Человек нажимал «Сообщить о
 * сбое» — и страница умирала; пожаловаться на это было уже нечем. Прожило пять
 * дней и нашлось только по жалобе владельца: «баг-трекер отвалился».
 *
 * ЧТО ЛОВИМ. Имена берём НЕ списком, а разбором самого кита: `export const X = (`
 * — функция. Список в гейте разошёлся бы с китом ровно так же, как разошлись
 * копии карты состояний кабинета.
 *
 * ЧЕГО НЕ ЛОВИМ. Файлы со СВОИМ локальным `btn` (например `pages/directory/
 * reconcile.js`, где это объект). Поэтому смотрим только на те файлы, которые
 * действительно импортируют имя из кита, — иначе гейт краснел бы на здоровом
 * коде, а такому сторожу перестают верить.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const KIT = 'components/salesTableKit.js'
const DIRS = ['pages', 'components', 'lib']

// Имена функций-стилей — из самого кита. Берём только те, что возвращают объект
// стиля (стрелка сразу к скобке), а не компоненты: у компонентов заглавная буква.
const kitSrc = readFileSync(join(ROOT, KIT), 'utf8')
const FN_STYLES = [...kitSrc.matchAll(/^export const ([a-z][A-Za-z0-9]*) = \(/gm)]
  .map((m) => m[1])
  .filter((name) => new RegExp(`export const ${name} = \\([^)]*\\) => \\(\\{`).test(kitSrc))

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(js|jsx)$/.test(name)) out.push(p)
  }
  return out
}

const problems = []
for (const dir of DIRS) {
  let files
  try { files = walk(join(ROOT, dir)) } catch { continue }
  for (const file of files) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    if (rel === KIT) continue
    const src = readFileSync(file, 'utf8')
    // Что этот файл реально берёт из кита: одна строка импорта, фигурные скобки.
    const imp = /import\s*\{([^}]*)\}\s*from\s*['"][^'"]*salesTableKit['"]/.exec(src)
    if (!imp) continue
    const taken = new Set(imp[1].split(',').map((x) => x.trim().split(/\s+as\s+/)[0].trim()))
    for (const name of FN_STYLES) {
      if (!taken.has(name)) continue
      const bare = new RegExp(`style=\\{${name}\\}`)
      const spread = new RegExp(`\\.\\.\\.${name}\\s*[,}]`)
      if (bare.test(src)) {
        problems.push(`${rel}: style={${name}} — функция вместо объекта, страница упадёт`)
      }
      if (spread.test(src)) {
        problems.push(`${rel}: {...${name}} — расплыв функции даёт ПУСТОЙ объект`)
      }
    }
  }
}

if (problems.length) {
  console.error('\nФункция-стиль передана как объект:\n')
  for (const p of problems) console.error('  · ' + p)
  console.error('\nЗовите её: style={btn(false)}, {...btn(true)} и так далее.\n')
  process.exit(1)
}
console.log(`check-style-fn: функции-стили (${FN_STYLES.join(', ')}) везде вызваны — порядок`)
