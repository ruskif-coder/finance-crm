// Контраст ролей NAVY: одна проверка на весь файл темы (владелец 26.11.2026 — «потерялись контрастные шрифты»).
//
// Поломка, которую держит прибор: `--warning-bg` объявлен один раз на корне темы, и его var() подставляется ТАМ, то есть
// в браузере на корневой элемент. Вложенной тон-зоне (`[data-tone="light"]` в тёмной теме) достаётся уже готовый цвет из
// корня, хотя текст зона переопределяет — в карточке пакета это дало 1,09:1 на полосе сканов. Поэтому считаем КАК БРАУЗЕР:
// слои по очереди, каждый var() разыменовывается на своём слое, наследство переходит вниз уже значениями.
//
// Запуск: node --test lib/navyContrast.test.mjs (входит в `npm run test-rk`).
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const css = fs.readFileSync(new URL('../styles/navy.css', import.meta.url), 'utf8')
const glob = fs.readFileSync(new URL('../styles/globals.css', import.meta.url), 'utf8')

function blocks(src, selector) {
  const out = []
  const re = new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}', 'g')
  let m
  while ((m = re.exec(src))) out.push(m[1])
  return out
}

function decls(body) {
  const out = {}
  for (const part of body.split(';')) {
    const i = part.indexOf(':')
    if (i < 0) continue
    const k = part.slice(0, i).trim()
    if (k.startsWith('--')) out[k] = part.slice(i + 1).trim()
  }
  return out
}

const merge = (...parts) => Object.assign({}, ...parts)
const take = (src, sel) => merge(...blocks(src, sel).map(decls))

/** Разыменовать var() значением из набора токенов; не разрешилось — null. */
function subst(value, flat, depth = 0) {
  const v = String(value || '').trim()
  const m = /^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$/.exec(v)
  if (!m) return v
  if (depth > 6) return null
  const got = flat[m[1]] != null ? flat[m[1]] : (m[2] ? subst(m[2], flat, depth + 1) : null)
  return got != null && got !== '' ? got : null
}

/** Все var() одного элемента разыменовываются по его же итоговому набору — порядок блоков не важен. */
function resolveAll(tokens) {
  const out = merge(tokens)
  for (let i = 0; i < 8; i++) {
    let changed = false
    for (const [k, v] of Object.entries(out)) {
      const got = subst(v, out)
      if (got != null && got !== v) { out[k] = got; changed = true }
    }
    if (!changed) break
  }
  return out
}

const root = take(glob, ':root')
const compat = take(css, '[data-theme^="navy"]')
const day = take(css, '[data-theme="navy"]')
const night = take(css, '[data-theme="navy-dark"]')
const zoneDark = merge(take(css, '[data-theme^="navy"] [data-tone]'),
  take(css, '[data-theme^="navy"] [data-tone="dark"]'), take(css, '[data-theme="navy-dark"] [data-tone="dark"]'))
const zoneLight = merge(take(css, '[data-theme^="navy"] [data-tone]'), take(css, '[data-theme="navy-dark"] [data-tone="light"]'))

// Корень темы и тон-зона — РАЗНЫЕ элементы: зона наследует уже готовые значения корня, поэтому `--warning-bg`,
// объявленный только на корне, приходит в зону готовым цветом (и не пересчитывается от её `--attn-tint`).
const dayRoot = resolveAll(merge(root, compat, day))
const nightRoot = resolveAll(merge(root, compat, night))
const SCOPES = {
  'navy (день)': dayRoot,
  'navy + зона dark': resolveAll(merge(dayRoot, zoneDark)),
  'navy-dark (ночь)': nightRoot,
  'navy-dark + зона dark': resolveAll(merge(nightRoot, zoneDark)),
  'navy-dark + зона light': resolveAll(merge(nightRoot, zoneLight)),
}

function rgb(v) {
  const h = String(v || '').trim().replace('#', '')
  return /^[0-9a-f]{6}$/i.test(h) ? [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) : null
}

function lum(c) {
  const f = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4 }
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
}

function ratio(a, b) {
  const la = lum(a), lb = lum(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

// Пары «текст на подложке», которые реально встречаются в карточке пакета и на экранах мастер-сделки.
const PAIRS = [
  ['text-primary', 'bg-card'], ['text-secondary', 'bg-card'], ['text-primary', 'bg-subtle'],
  ['text-secondary', 'bg-subtle'], ['text-muted', 'bg-subtle'],
  ['accent-fg', 'accent-tint'], ['attn-fg', 'attn-tint'], ['signal-text', 'signal-tint'],
  ['ok-fg', 'ok-tint'], ['money-fg', 'money-tint'], ['bad-fg', 'bad-tint'],
  ['warning-fg', 'warning-bg'], ['danger-fg', 'danger-bg'], ['income-fg', 'income-bg'],
]
const MIN = 4.5   // WCAG AA для обычного текста

for (const [scopeName, scope] of Object.entries(SCOPES)) {
  test(`${scopeName}: все пары «текст на подложке» не ниже ${MIN}:1`, () => {
    const bad = []
    for (const [fg, bg] of PAIRS) {
      const a = rgb(scope['--' + fg])
      const b = rgb(scope['--' + bg])
      assert.ok(a && b, `${scopeName}: у ${fg} или ${bg} нет цвета (${scope['--' + fg]} / ${scope['--' + bg]})`)
      const r = ratio(a, b)
      if (r < MIN) bad.push(`${fg} на ${bg} = ${r.toFixed(2)}:1`)
    }
    assert.deepEqual(bad, [], `ниже порога: ${bad.join(', ')}`)
  })
}

test('подложки ролей пересчитываются в тон-зоне, а не наследуются готовыми из корня', () => {
  const zone = decls(blocks(css, '[data-theme^="navy"] [data-tone]')[0] || '')
  assert.equal(zone['--warning-bg'], 'var(--attn-tint)', 'в зоне не пересчитан --warning-bg')
  assert.equal(zone['--danger-bg'], 'var(--bad-tint)', 'в зоне не пересчитан --danger-bg')
  assert.equal(zone['--income-bg'], 'var(--money-tint)', 'в зоне не пересчитан --income-bg')
})

test('полоса сканов печатает свои роли в обоих состояниях', () => {
  const base = decls(blocks(css, '[data-theme^="navy"] [data-scans]')[0] || '')
  const due = decls(blocks(css, '[data-theme^="navy"] [data-scans-due]')[0] || '')
  for (const k of ['--scans-bg', '--scans-bd', '--scans-fg', '--scans-dot']) {
    assert.ok(base[k], `нет ${k} у полосы сканов вне «ждём сканы»`)
    assert.ok(due[k], `нет ${k} у полосы сканов на «ждём сканы»`)
  }
  // «ждём сканы» — оранжевый, остальные стадии — сталь: подменять одно другим нельзя
  assert.match(base['--scans-bg'], /--attn-tint/)
  assert.match(due['--scans-bg'], /--signal-tint/)
})
