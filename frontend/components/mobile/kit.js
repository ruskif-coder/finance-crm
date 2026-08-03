// Общие визуальные примитивы мобильного слоя (карточка, моно-подпись, маркер).
// До выноса дублировались в Receivables/Cashflow/Operations/DealCardList.
import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'

export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }

export const monoLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }

// Квадратный маркер (цвет банка / слоя / состояния).
export function Marker({ c, size = 7 }) {
  return <span style={{ width: size, height: size, borderRadius: 2, background: c, flexShrink: 0, display: 'inline-block' }} />
}

// ── Выбор периода: месяц/квартал через селекты (без ручного ввода цифр) ──
// value: 'YYYY-MM' (месяц) | 'QN YYYY' (квартал) | ''. allowQuarter=false → только месяц.
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
function parsePeriod(v) {
  const q = /^Q([1-4])\s+(\d{4})$/.exec(v || '')
  if (q) return { mode: 'quarter', y: q[2], m: '', q: q[1] }
  const mo = /^(\d{4})-(\d{2})$/.exec(v || '')
  if (mo) return { mode: 'month', y: mo[1], m: mo[2], q: '' }
  return { mode: 'month', y: '', m: '', q: '' }
}
export function PeriodSelect({ value, onChange, allowQuarter = true }) {
  const init = parsePeriod(value)
  const [mode, setMode] = useState(init.mode)
  const [y, setY] = useState(init.y)
  const [m, setM] = useState(init.m)
  const [q, setQ] = useState(init.q)

  const nowY = new Date().getFullYear()
  const years = []
  for (let yr = nowY + 1; yr >= 2022; yr--) years.push(String(yr))

  const emit = (nMode, nY, nM, nQ) => {
    if (nMode === 'month') onChange(nY && nM ? `${nY}-${nM}` : '')
    else onChange(nQ && nY ? `Q${nQ} ${nY}` : '')
  }
  const selStyle = { flex: 1, minWidth: 0, boxSizing: 'border-box', appearance: 'none', WebkitAppearance: 'none', border: '1px solid var(--border-card)', borderRadius: 10, padding: '11px 12px', fontSize: 13, fontFamily: UI, fontWeight: 600, color: 'var(--text-primary)', background: 'var(--bg-card)', cursor: 'pointer', outline: 'none' }
  const segBtn = (active) => ({ flex: 1, border: 'none', borderRadius: 8, padding: '7px 0', fontFamily: MONO, fontSize: 12, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {allowQuarter && (
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-subtle)', borderRadius: 10, padding: 3 }}>
          <button type="button" onClick={() => { setMode('month'); emit('month', y, m, q) }} style={segBtn(mode === 'month')}>Месяц</button>
          <button type="button" onClick={() => { setMode('quarter'); emit('quarter', y, m, q) }} style={segBtn(mode === 'quarter')}>Квартал</button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        {mode === 'month' ? (
          <select value={m} onChange={e => { setM(e.target.value); emit('month', y, e.target.value, q) }} style={selStyle}>
            <option value="">Месяц</option>
            {MONTHS_RU.map((mn, i) => <option key={i} value={String(i + 1).padStart(2, '0')}>{mn}</option>)}
          </select>
        ) : (
          <select value={q} onChange={e => { setQ(e.target.value); emit('quarter', y, m, e.target.value) }} style={selStyle}>
            <option value="">Квартал</option>
            {[1, 2, 3, 4].map(n => <option key={n} value={String(n)}>{n}-й квартал</option>)}
          </select>
        )}
        <select value={y} onChange={e => { setY(e.target.value); emit(mode, e.target.value, m, q) }} style={{ ...selStyle, flex: '0 0 108px' }}>
          <option value="">Год</option>
          {years.map(yr => <option key={yr} value={yr}>{yr}</option>)}
        </select>
      </div>
    </div>
  )
}
