// Единая палитра для inline-стилей (JS-сторона) — зеркало дизайн-гайдлайна
// docs/.../design_system/ds.jsx. До выноса те же хексы были размножены по 14 файлам
// (только #C93A3E — в 9), местами расходясь.
//
// Соотношение с globals.css: с 17.11.2026 T — просто имена CSS-переменных темы для style={{...}};
// источник цвета один — styles/globals.css и styles/navy.css.

export const T = {
  // 17.11.2026 (темы NAVY): значения — ПЕРЕМЕННЫЕ ТЕМЫ, а не хексы. Раньше здесь стояли хексы светлой темы, и всё, что красилось
  // через T (бары и графики ДДС, плашки ошибок справочников), в других темах оставалось светлым. T — только для style={{...}}:
  // склеивать значение с прозрачностью (`T.accent + '33'`) больше нельзя — для оттенков есть свои токены (-tint, -soft).
  // поверхности
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)',
  pick: 'var(--bg-pick)', tipBg: 'var(--bg-tint)',

  // границы
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)', hoverBorder: 'var(--border-hover)',

  // текст
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)',

  // акцент
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)',
  accentBorder: 'var(--accent-border)', accentSoft: 'var(--accent-soft)',

  // статусы
  income: 'var(--income)', incomeTint: 'var(--income-tint)',
  expense: 'var(--chart-out)',                          // расход на графиках — нейтральный (не --expense: тот красный)
  warning: 'var(--warning)', warningTint: 'var(--warning-tint)', warningText: 'var(--warning-text)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)',
  mixed: 'var(--mixed)', mixedTint: 'var(--mixed-tint)',

  // банки — совпадает с BANK_HEX в lib/salesFormat.js (там источник для bankColor())
  banks: { 'АльфаБанк': '#E8453F', 'ОПТ Банк': '#2FB8A8', 'Совкомбанк': '#8B93A6', 'Наличные': '#8B7BE8', default: '#C3C9D8' },

  // шрифты
  mono: "'JetBrains Mono', ui-monospace, monospace",
  sans: "'Manrope', system-ui, sans-serif",
}
