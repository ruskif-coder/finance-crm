/**
 * Гейт правил React-хуков (аудит 23.09.2026, 6.L7).
 *
 * `next.config.js` держит `eslint.ignoreDuringBuilds: true`, а `.eslintrc.json` выключал
 * `react-hooks/exhaustive-deps` — правила хуков не проверял ни один гейт. Здесь они
 * включены отдельно, только для этой проверки:
 *
 *   · `rules-of-hooks` — ОШИБКА, ноль допусков: хук под условием ломает порядок хуков,
 *     и экран падает у части пользователей;
 *   · `exhaustive-deps` — храповик по числу предупреждений. Замер 24.09.2026 — 86 (с .jsx). Больше
 *     — сборка падает (новый эффект с забытой зависимостью). Меньше — гейт просит
 *     опустить планку, чтобы починенное не вернулось.
 *
 * Запускается в контейнере сборки (там есть node_modules), в `prebuild`.
 */
import { ESLint } from 'eslint'

const EXHAUSTIVE_DEPS_MAX = 86   // замер 24.09.2026 с .jsx (без них было 80)

const eslint = new ESLint({
  // Без этого ESLint 8 по каталогу смотрит только .js — 31 файл .jsx шёл мимо (ревью 24.09.2026).
  extensions: ['.js', '.jsx'],
  cwd: new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  overrideConfig: {
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
})

const results = await eslint.lintFiles(['pages', 'components', 'lib'])
let hookErrors = []
let deps = 0
for (const r of results) {
  for (const m of r.messages) {
    if (m.ruleId === 'react-hooks/rules-of-hooks') hookErrors.push(`${r.filePath}:${m.line}  ${m.message}`)
    if (m.ruleId === 'react-hooks/exhaustive-deps') deps += 1
  }
}

const bad = []
if (hookErrors.length) bad.push(...hookErrors.map(e => 'rules-of-hooks: ' + e))
if (deps > EXHAUSTIVE_DEPS_MAX) {
  bad.push(`exhaustive-deps: ${deps} предупреждений при допуске ${EXHAUSTIVE_DEPS_MAX} — у нового эффекта забыта зависимость (npx eslint --rule 'react-hooks/exhaustive-deps: warn')`)
}
if (deps < EXHAUSTIVE_DEPS_MAX) {
  bad.push(`exhaustive-deps: стало ${deps} — опустите EXHAUSTIVE_DEPS_MAX до ${deps}, чтобы починенное не вернулось`)
}
if (bad.length) {
  console.error('\ncheck-hooks-lint: правила хуков\n')
  for (const b of bad) console.error('  ' + b)
  process.exit(1)
}
console.log(`check-hooks-lint: хуки без условий, забытых зависимостей ${deps} (храповик) — порядок`)
