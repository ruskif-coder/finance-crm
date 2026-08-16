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

// Единое появление карточек снизу. До выноса жило в четырёх экземплярах под
// именами riseIn / rcvRise / ddsRise / sheetFade — одна кривая, одно смещение.
export const RISE_KEYFRAMES = `@keyframes mRise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@media (prefers-reduced-motion:reduce){[style*="animation"]{animation:none!important}}`

// rise(0) — первая карточка, rise(1) — вторая и так далее. Лесенка задержек
// та же, что была: шаг 70 мс, не длиннее шести ступеней.
export const rise = (i = 0, dur = '.4s') => ({
  animation: `mRise ${dur} cubic-bezier(0.22,1,0.36,1) both`,
  animationDelay: `${Math.min(i, 6) * 0.07}s`,
})

