// Колонка «Что сделать»: точка срочности + факты стадии чипами (макет «акки 3», ТЗ §3.2).
//
// Четыре типа элементов приходят с сервера готовыми (app/sales/queue_state.py) —
// здесь только оформление. Больше трёх — три и «+N», полный список — в подсказке.
import { UI } from '@/components/salesTableKit'
import { URGENCY_DOT } from './ladder'

const base = {
  display: 'inline-flex', alignItems: 'center', padding: '2px 7px', borderRadius: 6,
  fontSize: 10.5, whiteSpace: 'nowrap', border: '1px solid transparent', fontFamily: UI,
}

const text = (e) => {
  if (e.type === 'status') return e.v
  if (e.type === 'check') return `${e.ok ? '✓' : '✗'} ${e.v}`
  if (e.type === 'progress') return `${e.k} ${e.unit ? `${e.x} ${e.unit}` : `${e.x} / ${e.y}`}`
  if (e.type === 'fact') return e.k ? `${e.k} ${e.v}` : e.v
  return e.v
}

const look = (e) => {
  // Состояние РК («запущена») — зелёной плашкой, как статус РК в дашборде трафика.
  if (e.type === 'status') {
    return { background: 'var(--income)', color: 'var(--on-accent)', fontWeight: 700 }
  }
  if (e.type === 'check') {
    if (e.ok) return { background: 'var(--income-tint)', color: 'var(--income-fg)', fontWeight: 600 }
    // Не запирает переход этой сделки — серым, без тревоги.
    if (e.optional) return { background: 'var(--bg-subtle)', borderColor: 'var(--border-inner)', color: 'var(--text-faint)', fontWeight: 600 }
    return { background: 'var(--bg-card)', borderColor: 'var(--danger-border)', color: 'var(--danger-fg)', fontWeight: 600 }
  }
  if (e.type === 'alert') {
    return { padding: '2px 2px', color: e.tone === 'bad' ? 'var(--danger-fg)' : 'var(--warning-fg)', fontWeight: 700 }
  }
  if (e.type === 'progress') {
    const full = e.x >= e.y
    return { background: full ? 'var(--income-tint)' : 'var(--bg-subtle)',
             color: full ? 'var(--income-fg)' : 'var(--text-primary)', fontWeight: 700 }
  }
  return { background: 'var(--bg-subtle)', color: 'var(--text-secondary)', fontWeight: 600 }
}

export default function StateChips({ row }) {
  const all = row.state || []
  // Четыре: у запущенной РК — «запущена · открутка · площадок · скрины» (01.10.2026).
  const shown = all.slice(0, 4)
  const more = all.length - shown.length
  const title = [row.reason, ...all.map(text)].filter(Boolean).join(' · ')
  return (
    <span title={title} style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap', minWidth: 0 }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, flex: '0 0 7px',
        background: URGENCY_DOT[row.urgency] || URGENCY_DOT.normal }} />
      {shown.map((e, i) => <span key={i} style={{ ...base, ...look(e) }}>{text(e)}</span>)}
      {more > 0 && <span style={{ ...base, padding: '2px 2px', color: 'var(--text-muted)', fontWeight: 700 }}>+{more}</span>}
      {!all.length && !!row.reason && (
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.reason}</span>
      )}
    </span>
  )
}
