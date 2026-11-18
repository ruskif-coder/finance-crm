#!/usr/bin/env node
/**
 * Сторож стандарта движения (владелец 18.11.2026: «стандартизированно, а не каждый лист подгонять»). Токены и анимации — в
 * styles/globals.css («Стандарт движения»), JS-сторона — lib/motion.jsx. Роняет сборку, если:
 *   1) `@keyframes` объявлен вне styles/ — новая анимация заводится в globals.css, а не на странице (было ~40 копий шести движений);
 *   2) `@media (prefers-reduced-motion` вне styles/ — правило одно на проект (было 23 копии);
 *   3) DUR в lib/motion.jsx разошёлся с --dur-* в globals.css — таймеры ждали бы не ту длительность;
 *   4) храповик: ручные `cubic-bezier(` и числовые длительности в transition/animation в коде экранов не растут (кривая и время —
 *      var(--ease-*) / var(--dur-*)). Снизил число — опусти потолок.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['pages', 'components', 'lib']
const MAX_BEZIER = 0          // после перевода 18.11.2026

function walk(dir, out = []) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) { if (n !== 'node_modules') walk(p, out) } else if (/\.(jsx?|mjs)$/.test(n)) out.push(p)
  }
  return out
}

const files = DIRS.flatMap(d => walk(join(ROOT, d)))
const bad = []
let bez = 0, dur = 0
const durHits = []
for (const f of files) {
  const rel = relative(ROOT, f).replace(/\\/g, '/')
  const src = readFileSync(f, 'utf8')
  if (/@keyframes\s+[\w-]+\s*\{/.test(src)) bad.push(`${rel}: @keyframes вне styles/ — заведите анимацию в globals.css («Стандарт движения»)`)
  if (/@media\s*\(\s*prefers-reduced-motion/.test(src)) bad.push(`${rel}: своё правило «меньше движения» — оно одно, в globals.css`)
  if (rel === 'lib/motion.jsx' || rel === 'pages/finance/cashflow.js') continue   // cashflow — framer-motion, свои числа
  bez += (src.match(/cubic-bezier\(/g) || []).length
  for (const m of src.matchAll(/(?:transition|animation)\s*:\s*([`'"])([^`'"\n]*)\1/g)) {
    const v = m[2]
    if (/infinite/.test(v)) continue
    // только время сразу после свойства/имени анимации; задержка лесенки (после кривой) — не длительность
    const n = (v.match(/(?:^|,)\s*[\w-]+\s+\d*\.?\d+m?s\b/g) || []).length
    if (n) { dur += n; durHits.push(`${rel}: ${v.slice(0, 70)}`) }
  }
}

// 3) DUR ↔ --dur-*
const css = readFileSync(join(ROOT, 'styles/globals.css'), 'utf8')
const js = readFileSync(join(ROOT, 'lib/motion.jsx'), 'utf8')
for (const k of ['fast', 'base', 'slow']) {
  const c = (css.match(new RegExp(`--dur-${k}:\\s*(\\d+)ms`)) || [])[1]
  const j = (js.match(new RegExp(`${k}:\\s*(\\d+)`)) || [])[1]
  if (!c || c !== j) bad.push(`lib/motion.jsx DUR.${k}=${j} ≠ --dur-${k}=${c}ms в globals.css`)
}

const LIMIT = 0    // после перевода 18.11.2026 числовых длительностей в transition/animation не осталось
if (bez > MAX_BEZIER) bad.push(`ручных cubic-bezier в коде экранов: ${bez} (потолок ${MAX_BEZIER}) — кривая только var(--ease-out|in|move)`)
if (dur > LIMIT) {
  bad.push(`числовых длительностей в transition/animation: ${dur} (потолок ${LIMIT}) — время только var(--dur-fast|base|slow):`)
  durHits.slice(0, 15).forEach(h => bad.push('   ' + h))
}

if (bad.length) {
  console.error('check-motion: стандарт движения нарушен\n' + bad.map(b => '  · ' + b).join('\n'))
  process.exit(1)
}
console.log(`check-motion: анимации только в styles/, «меньше движения» одно, DUR = токены; кривых вручную ${bez}, числовых длительностей ${dur} (потолок ${LIMIT}) — порядок`)
