/**
 * Гейт: цвет в разметке кабинета берётся ТОЛЬКО из переменных.
 *
 * У кабинета, в отличие от ядра, тёмная тема есть — `data-theme` переключает значения
 * переменных, а не хексы в JS. Поэтому «#2FA37C» в стиле компонента остаётся зелёным и
 * в тёмной теме, где зелёный другой, и ломается ровно тот случай, который никто не
 * проверяет глазами: разработчик сидит в светлой.
 *
 * Правило было записано словами в шапке `lib/ui.js` — и я сам нарушил его четырежды за
 * два дня. Слова не держат; держит гейт, который роняет сборку.
 *
 * Что разрешено:
 *   · `styles/globals.css` — там переменные и определяются;
 *   · `var(--…)` в любом виде;
 *   · `#fff` ФОНОМ ИФРЕЙМА баннера (`preview.js`) — это не цвет интерфейса, а полотно
 *     чужой страницы: баннер рисуют для белого сайта, и тёмный фон под ним показал бы
 *     не то размещение, которое будет на самом деле. Исключение перечислено поимённо,
 *     а не по маске, чтобы второй такой случай тоже потребовал решения.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SKIP_DIRS = new Set(['node_modules', '.next', 'public', 'scripts'])
const HEX = /#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b/g

// Поимённые исключения: файл → сколько допущено и почему.
const ALLOWED = {
  'lib/preview.js': 1,   // background: '#fff' у ифрейма — полотно баннера, см. шапку
  // Руководство (24.09.2026): слайды — сгенерированная выгрузка Claude Design со своей
  // палитрой. Это полотно ДОКУМЕНТА, как полотно баннера: в тёмной теме слайд остаётся
  // таким, каким его нарисовали. Счёт точный — новая выгрузка с другим числом цветов
  // потребует поправить его здесь осознанно.
  'components/guide/slides.js': 271,
  'components/guide/Guide.jsx': 2,   // фон сцены и цвет текста слайда — те же, что в выгрузке
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(js|jsx)$/.test(name)) out.push(p)
  }
  return out
}

const bad = []
for (const file of walk(ROOT)) {
  const rel = relative(ROOT, file).replace(/\\/g, '/')
  const src = readFileSync(file, 'utf8')
  const hits = src.split('\n').flatMap((line, i) => {
    const m = line.match(HEX)
    return m ? m.map(h => ({ line: i + 1, hex: h, text: line.trim().slice(0, 90) })) : []
  })
  const budget = ALLOWED[rel] || 0
  if (hits.length > budget) bad.push({ rel, hits, budget })
}

if (bad.length) {
  console.error('\ncheck-tokens: цвет мимо переменных\n')
  for (const { rel, hits, budget } of bad) {
    console.error(`  ${rel}  (найдено ${hits.length}, допущено ${budget})`)
    for (const h of hits) console.error(`    ${h.line}: ${h.hex}  ${h.text}`)
  }
  console.error('\n  Цвета живут в styles/globals.css. Нужен новый — заведите переменную')
  console.error('  и используйте var(--…): тёмная тема переключает их, а не хексы в JS.\n')
  process.exit(1)
}
console.log('check-tokens: цвет только из переменных — порядок')
