// Единая палитра для inline-стилей (JS-сторона) — зеркало дизайн-гайдлайна
// docs/.../design_system/ds.jsx. До выноса те же хексы были размножены по 14 файлам
// (только #C93A3E — в 9), местами расходясь.
//
// Соотношение с globals.css: CSS-переменные (--accent и т.п.) остаются источником
// для CSS/className; T — их JS-двойник для style={{...}}. Значения совпадают, кроме
// исторических расхождений, отмеченных ниже (их НЕ трогаем — это вопрос дизайна).

export const T = {
  // поверхности
  canvas: '#EBEEF6', card: '#FFFFFF', subtle: '#F6F7FB',
  pick: '#F0F3FF', tipBg: '#F6F8FF',

  // границы
  border: '#E3E7F1', inner: '#EDF0F7', row: '#F2F4FA', hoverBorder: '#C7D0E8',

  // текст
  t1: '#1C2433', t2: '#525C70', t3: '#79839A', t4: '#A3ABBD',

  // акцент
  accent: '#4F6CE6', accentHover: '#3A50BE', accentTint: '#ECEFFD',
  accentBorder: '#D7DEFA', accentSoft: '#A9B6F2',

  // статусы
  income: '#2FA37C', incomeTint: '#E6F5EF',
  expense: '#8B93A6',                                   // расход на графиках (не путать с --expense #DB5C6E в CSS)
  warning: '#E89020', warningTint: '#FBF0DE', warningText: '#B26A0C',
  danger: '#C93A3E', dangerTint: '#FBEAEA',             // handoff-красный; в CSS --dot-overdue = #E5484D (иной)
  mixed: '#7B62D6', mixedTint: '#F1EDFC',

  // банки — совпадает с BANK_HEX в lib/salesFormat.js (там источник для bankColor())
  banks: { 'АльфаБанк': '#E8453F', 'ОПТ Банк': '#2FB8A8', 'Совкомбанк': '#8B93A6', 'Наличные': '#8B7BE8', default: '#C3C9D8' },

  // шрифты
  mono: "'JetBrains Mono', ui-monospace, monospace",
  sans: "'Manrope', system-ui, sans-serif",
}
