/**
 * Общие мелочи итоговой сверки: тона, подписи, плашка, показатель, пин режима суммы, пункт чек-листа.
 * Часть блока «Итоговая сверка» (`ClosingBlock.jsx`), вынесено при аудите 20.10.2026.
 */
import { CLOSE_MODE, capFirst } from '@/lib/masterStatus'
import { MONO, UI } from '@/components/salesTableKit'
import { grp, rub2 } from '@/lib/salesFormat'

import { Dot, num } from '@/components/master/kit'
export { Dot, num }

export const unitOf = (model) => (/^cpc$/i.test((model || '').trim()) ? { plural: 'клики', gen: 'кликов', price: 'клик' }
  : FIX_RE.test((model || '').trim()) ? { plural: 'пакеты', gen: 'пакетов', price: 'пакет' } : { plural: 'показы', gen: 'показов', price: '1000' })
export const asText = (v) => (v == null ? '' : grp(v))
export const isNum = (v) => String(v || '').trim() !== '' && num(v) >= 0

export const TONE = {
  ok: ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'],
  warn: ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-text)'],
  bad: ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)'],
  off: ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-muted)'],
}

export const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }

export const GRID = 'minmax(0,2.1fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) minmax(0,.9fr) minmax(0,1.1fr)'

export const FIX_RE = /^(fix|фикс|пакет)$/i

export function Pill({ tone, children, onClick, title }) {
  const [bg, bd, fg] = TONE[tone] || TONE.off
  return (
    <span onClick={onClick} title={title}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 700,
        background: bg, border: `1px solid ${bd}`, color: fg, whiteSpace: 'nowrap', cursor: onClick ? 'pointer' : 'default' }}>
      <Dot c={fg} />{children}</span>
  )
}

export function Kpi({ label, value, tone, tag, hint }) {
  return (
    <div style={{ padding: '4px 22px', minWidth: 0 }}>
      <span style={CAP}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginTop: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, color: tone || 'var(--text-primary)', lineHeight: 1.1 }}>{value}</span>{tag}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 6 }}>{hint}</div>
    </div>
  )
}

export function Pin({ k, on, isDefault, value, disabled, onPick, by }) {
  return (
    <button type="button" disabled={disabled} onClick={() => onPick(k)} title={disabled && k === 'manual' ? 'Ручная сумма — только мастер или админ' : undefined}
      style={{ minWidth: 0, textAlign: 'left', padding: '10px 12px', borderRadius: 12, fontFamily: UI, fontSize: 13, fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer', background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
        color: disabled ? 'var(--text-faint)' : on ? 'var(--accent-fg)' : 'var(--text-primary)',
        border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}` }}>
      {capFirst(CLOSE_MODE[k])}
      <span style={{ display: 'block', fontFamily: MONO, fontSize: 13, marginTop: 4 }}>{value == null ? '—' : rub2(value)}</span>
      {(isDefault || by) && <span style={{ display: 'block', ...CAP, fontWeight: 600, marginTop: 2 }}>{by || 'по умолч.'}</span>}
    </button>
  )
}

// СК юрлица закрытия (владелец 19.10.2026): способ подсвечивается плашкой. «Скидка в счёт» — процент правится по этой
// сделке (Альфарм: через него закрывается весь Альфарм-Таргет); «постоплата» — только показ: счёт на полную сумму, СК потом.
// Способ задаётся у юрлица (карточка контрагента), не здесь.

export function Check({ ok, warn, children }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: ok ? 'var(--income-fg)' : warn ? 'var(--warning-text)' : 'var(--danger-fg)' }}>
      <b>{ok ? '✓' : '!'}</b>{children}</span>
  )
}
