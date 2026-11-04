// Выбор месяца: стрелки ← → листают по месяцу, клик по названию открывает календарик
// с сеткой месяцев года (владелец 29.09.2026, вкладка «Согласования» паблишеров).
// value / onChange — 'YYYY-MM'. marked — месяцы, где есть данные: помечаются точкой.
// Сетка — общая с полем месяца (`MonthInput`).
import { useEffect, useState } from 'react'
import { PortalPopover } from '@/components/salesTableKit'
import { MONTHS, MonthGrid } from '@/components/MonthInput'

export const shiftMonth = (ym, delta) => {
  const [y, m] = ym.split('-').map(Number)
  const i = y * 12 + (m - 1) + delta
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`
}

const arrow = { width: 32, height: 34, borderRadius: 9, border: '1px solid var(--border-card)',
  background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 15,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 }

const launchTitle = (ym, marked) => (marked ? 'Есть РК со «Сбором запуска»' : 'РК со «Сбором запуска» нет')

export default function MonthPicker({ value, onChange, marked = [] }) {
  const [open, setOpen] = useState(false)
  const [y, m] = value.split('-').map(Number)

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <span data-pop-root style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <button type="button" style={arrow} title="Предыдущий месяц" onClick={() => onChange(shiftMonth(value, -1))}>‹</button>
      <span style={{ position: 'relative' }}>
        <button type="button" onClick={() => setOpen(o => !o)}
          style={{ ...arrow, width: 'auto', padding: '0 12px', gap: 8, fontWeight: 700, fontSize: 13,
            color: 'var(--text-primary)', borderColor: open ? 'var(--accent)' : 'var(--border-card)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
            strokeLinecap="round"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
          {MONTHS[m - 1]} {y}
        </button>
        <PortalPopover open={open} minWidth={236}>
          <MonthGrid value={value} marked={marked} markTitle={launchTitle} onPick={(ym) => { onChange(ym); setOpen(false) }} />
        </PortalPopover>
      </span>
      <button type="button" style={arrow} title="Следующий месяц" onClick={() => onChange(shiftMonth(value, 1))}>›</button>
    </span>
  )
}
