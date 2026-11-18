// Общие визуальные примитивы мобильного слоя (карточка, моно-подпись, маркер).
// До выноса дублировались в Receivables/Cashflow/Operations/DealCardList.
import { MONO } from '../salesTableKit'

// PeriodSelect переехал в общий components/PeriodSelect.js (используется и десктопом
// через проп dense). Ре-экспорт — чтобы существующие мобильные импорты из kit не сломались.
export { PeriodSelect } from '../PeriodSelect'

export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }

export const monoLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }

// Квадратный маркер (цвет банка / слоя / состояния).
export function Marker({ c, size = 7 }) {
  return <span style={{ width: size, height: size, borderRadius: 2, background: c, flexShrink: 0, display: 'inline-block' }} />
}

// Появление карточек снизу — общая анимация m-rise (styles/globals.css, «Стандарт движения», 18.11.2026). rise(0) — первая карточка,
// rise(1) — вторая…; лесенка — общий шаг --stagger, не длиннее десяти ступеней (как data-motion="rise").
export const rise = (i = 0) => ({
  animation: 'm-rise var(--dur-slow) var(--ease-out) both',
  animationDelay: `calc(${Math.min(i, 10)} * var(--stagger))`,
})

