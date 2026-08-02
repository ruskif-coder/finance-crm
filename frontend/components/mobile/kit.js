// Общие визуальные примитивы мобильного слоя (карточка, моно-подпись, маркер).
// До выноса дублировались в Receivables/Cashflow/Operations/DealCardList.
import { MONO } from '../salesTableKit'

export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }

export const monoLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }

// Квадратный маркер (цвет банка / слоя / состояния).
export function Marker({ c, size = 7 }) {
  return <span style={{ width: size, height: size, borderRadius: 2, background: c, flexShrink: 0, display: 'inline-block' }} />
}
