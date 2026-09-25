/**
 * Гейт: вкладки и встроенные окна не получают доступа к нашей странице (аудит 23.09.2026,
 * 7.L1 и 7.L2).
 *
 *  · `window.open(…)` — либо третьим аргументом `noopener`, либо следом `tab.opener = null`:
 *    иначе открытая страница (DSP, Битрикс) через `window.opener` может увести наш экран;
 *  · каждый `<iframe` — с атрибутом `sandbox`: превью баннеров исполняет чужой код.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SKIP = new Set(['node_modules', '.next', 'public', 'scripts'])

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
  const src = readFileSync(file, 'utf8')
  const lines = src.split('\n')
  lines.forEach((line, i) => {
    if (/window\.open\(/.test(line)) {
      const near = lines.slice(i, i + 4).join('\n')
      if (!/noopener|\.opener\s*=\s*null/.test(near)) bad.push(`${rel}:${i + 1}  window.open без noopener`)
    }
    if (/<iframe\b/.test(line)) {
      const tag = src.slice(src.indexOf(line)).split('/>')[0]
      if (!/\bsandbox=/.test(tag)) bad.push(`${rel}:${i + 1}  <iframe> без sandbox`)
    }
  })
}
if (bad.length) {
  console.error('\ncheck-embeds: вкладки и окна с доступом к нашей странице\n')
  for (const b of bad) console.error('  ' + b)
  process.exit(1)
}
console.log('check-embeds: вкладки без opener, окна в песочнице — порядок')
