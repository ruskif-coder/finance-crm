// Выбор месяца: стрелки ← → листают по месяцу, клик по названию открывает календарик
// с сеткой месяцев года (владелец 29.09.2026, вкладка «Согласования» паблишеров).
// value / onChange — 'YYYY-MM'. marked — месяцы, где есть данные: помечаются точкой.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover } from '@/components/salesTableKit'

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август',
  'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export const shiftMonth = (ym, delta) => {
  const [y, m] = ym.split('-').map(Number)
  const i = y * 12 + (m - 1) + delta
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`
}

const arrow = { width: 32, height: 34, borderRadius: 9, border: '1px solid var(--border-card)',
  background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 15,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 }

export default function MonthPicker({ value, onChange, marked = [] }) {
  const [open, setOpen] = useState(false)
  const [year, setYear] = useState(Number(value.slice(0, 4)))
  const [y, m] = value.split('-').map(Number)
  const has = new Set(marked)

  useEffect(() => { if (open) setYear(y) }, [open, y])
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 2px 8px' }}>
            <button type="button" style={{ ...arrow, width: 28, height: 28 }} onClick={() => setYear(v => v - 1)}>‹</button>
            <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 13 }}>{year}</span>
            <button type="button" style={{ ...arrow, width: 28, height: 28 }} onClick={() => setYear(v => v + 1)}>›</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 72px)', gap: 4 }}>
            {SHORT.map((label, i) => {
              const ym = `${year}-${String(i + 1).padStart(2, '0')}`
              const on = ym === value
              return (
                <button type="button" key={ym} onClick={() => { onChange(ym); setOpen(false) }}
                  title={has.has(ym) ? 'Есть РК со «Сбором запуска»' : 'РК со «Сбором запуска» нет'}
                  style={{ position: 'relative', height: 34, borderRadius: 8, cursor: 'pointer',
                    fontFamily: MONO, fontSize: 12, fontWeight: 700,
                    border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
                    background: on ? 'var(--accent)' : 'var(--bg-card)',
                    color: on ? 'var(--on-accent)' : has.has(ym) ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                  {label}
                  {has.has(ym) && !on && <span style={{ position: 'absolute', top: 4, right: 5, width: 5, height: 5,
                    borderRadius: 3, background: 'var(--accent)' }} />}
                </button>
              )
            })}
          </div>
        </PortalPopover>
      </span>
      <button type="button" style={arrow} title="Следующий месяц" onClick={() => onChange(shiftMonth(value, 1))}>›</button>
    </span>
  )
}
