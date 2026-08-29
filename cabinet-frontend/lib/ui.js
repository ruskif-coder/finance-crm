/**
 * Примитивы кабинета. Цвета — ТОЛЬКО через переменные из `styles/globals.css`.
 *
 * Раньше здесь лежали хексы константами, и это ломало тёмную тему ровно в тех местах:
 * `data-theme` переключает переменные, а не значения в JS. Ни одного `#RRGGBB` в этом
 * файле и в разметке быть не должно.
 *
 * Имена переменных те же, что в финмодуле: один продукт, и два имени у одного смысла
 * означали бы, что при правке палитры одно из них останется старым.
 */
export const UI = "'Manrope', system-ui, -apple-system, sans-serif"
export const MONO = "'JetBrains Mono', ui-monospace, 'SFMono-Regular', monospace"

export const C = {
  canvas: 'var(--bg-canvas)',
  card: 'var(--bg-card)',
  subtle: 'var(--bg-subtle)',
  tint: 'var(--bg-tint)',
  warnBg: 'var(--warn-bg)',
  dangerBg: 'var(--danger-bg)',
  border: 'var(--border-card)',
  inner: 'var(--border-inner)',
  row: 'var(--border-row)',
  hover: 'var(--border-hover)',
  text: 'var(--text-primary)',
  secondary: 'var(--text-secondary)',
  muted: 'var(--text-muted)',
  faint: 'var(--text-faint)',
  ghost: 'var(--text-ghost)',
  onFill: 'var(--fg-on-fill)',   // текст поверх насыщенной заливки
  accent: 'var(--accent)',
  accentHover: 'var(--accent-hover)',
  accentTint: 'var(--accent-tint)',
  accentBorder: 'var(--accent-border)',
  income: 'var(--income)',
  incomeFg: 'var(--income-fg)',
  incomeTint: 'var(--income-tint)',
  incomeBorder: 'var(--income-border)',
  warning: 'var(--warning)',
  warningFg: 'var(--warning-fg)',
  warningTint: 'var(--warning-tint)',
  warningBorder: 'var(--warning-border)',
  danger: 'var(--danger)',
  dangerTint: 'var(--danger-tint)',
  dangerBorder: 'var(--danger-border)',
  teal: 'var(--teal)',
  violet: 'var(--violet)',
  violetFg: 'var(--violet-fg)',
  violetTint: 'var(--violet-tint)',
}

export const card = {
  background: C.card, border: `1px solid ${C.border}`, borderRadius: 18,
  boxShadow: 'var(--shadow-card)',
}

export const btn = (primary) => ({
  padding: '8px 14px', borderRadius: 9, cursor: 'pointer', fontSize: 12.5,
  fontWeight: primary ? 700 : 600, fontFamily: UI,
  border: primary ? '1px solid transparent' : `1px solid ${C.border}`,
  background: primary ? C.accent : C.card,
  color: primary ? C.onFill : C.secondary,
  transition: 'background 150ms ease, border-color 150ms ease',
})

export const btnSm = (primary) => ({ ...btn(primary), padding: '5px 10px', fontSize: 11.5 })

/** Кнопка-действие контуром: фон карточки, цветной текст, рамка того же тона.
 *
 * Смысл несёт ТЕКСТ, а не плашка. Заливка — даже пастельная — на каждом действии
 * превращает строку в светофор: несколько цветных плашек подряд спорят за внимание, и
 * главное действие перестаёт читаться главным. Залита ровно ОДНА кнопка — та, ради
 * которой карточку открыли; остальные держат тон рамкой и подписью.
 *
 * Цвет берётся парой `fg / border` из тройки токенов; `tint` той же тройки остаётся за
 * чипами состояния, где заливка как раз и нужна — чип не кликают, он не конкурирует.
 */
export const soft = (fg, border) => ({
  padding: '5px 12px', borderRadius: 9, cursor: 'pointer', fontSize: 11.5,
  fontWeight: 700, fontFamily: UI,
  background: C.card, color: fg, border: `1px solid ${border}`,
  transition: 'background 150ms ease, border-color 150ms ease',
})

/** Стрелка шага в переключателе. Гасится цветом, а не исчезновением: пропавшая кнопка
 *  двигает соседей, и пилюля месяца прыгает вбок на каждом шаге. */
export const arrowBtn = (on) => ({
  width: 24, height: 24, borderRadius: 7, border: 0, background: 'transparent',
  color: on ? C.secondary : C.ghost, cursor: on ? 'pointer' : 'default',
  fontSize: 15, lineHeight: 1, fontFamily: UI, padding: 0,
})

export const inp = {
  padding: '9px 11px', border: `1px solid ${C.border}`, borderRadius: 9, fontSize: 13,
  background: C.subtle, color: C.text, fontFamily: UI, outline: 'none',
  boxSizing: 'border-box', width: '100%',
}

/** Капс-подпись. Моноширинный — как все служебные надписи в продукте. */
export const CAP = {
  fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.09em',
  textTransform: 'uppercase', color: C.faint,
}

/** Маркер состояния. Квадратный (радиус 2) — правило языка. */
export const dot = (color) => ({
  width: 7, height: 7, borderRadius: 2, background: color, flex: '0 0 7px',
})

export const chip = (bg, fg, bd) => ({
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 9px',
  borderRadius: 8, background: bg, color: fg,
  border: `1px solid ${bd || 'transparent'}`,
  fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
})

/* Суммы выводятся ПОЛНОСТЬЮ в рублях, не в миллионах: не всякая площадка получает
   миллионы за месяц, и «0,6 млн» вместо «624 753 ₽» скрывает от неё копейки. */
export const rub = (n) => (n || n === 0
  ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽' : '—')
export const num = (n) => (n || n === 0 ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '—')

export const dm = (s) => (s ? String(s).slice(8, 10) + '.' + String(s).slice(5, 7) : '—')

/* Именительный падеж — подпись стоит сама по себе («август 2026»), а не в обороте
   «за августа». Родительный понадобится отдельным списком, если появится «за <месяц>». */
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль',
  'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

/** `2026-08` → «август 2026». Для подписей выбранного среза. */
export const periodLabel = (p) => {
  if (!p) return '—'
  const [y, m] = String(p).split('-')
  return `${MONTHS[Number(m) - 1] || m} ${y}`
}
