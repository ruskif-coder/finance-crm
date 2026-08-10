// Единый выбор периода — «выбор, не ввод». Формат value: 'YYYY-MM' (месяц) |
// 'QN YYYY' (квартал) | ''. Раньше существовали ДВА разных: мобильный PeriodSelect
// (селекты, в kit.js) и десктопный PeriodField (свободный ввод квартала, в operations.js).
// Свободный ввод давал тихий промах при опечатке в квартале — теперь везде выбор.
//
// dense=false — мобильная раскладка (сегмент строкой сверху, селекты снизу), не менялась.
// dense=true  — десктоп: один ряд height 36 под стиль полей operations (inp/Seg).
// allowQuarter=false — только месяц (напр. период размещения сделки).
import { useState, useEffect, useRef } from 'react'
import { MONO, UI } from './salesTableKit'

const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

function parsePeriod(v) {
  const q = /^Q([1-4])\s+(\d{4})$/.exec(v || '')
  if (q) return { mode: 'quarter', y: q[2], m: '', q: q[1] }
  const mo = /^(\d{4})-(\d{2})$/.exec(v || '')
  if (mo) return { mode: 'month', y: mo[1], m: mo[2], q: '' }
  return { mode: 'month', y: '', m: '', q: '' }
}

export function PeriodSelect({ value, onChange, allowQuarter = true, dense = false }) {
  const init = parsePeriod(value)
  const [mode, setMode] = useState(init.mode)
  const [y, setY] = useState(init.y)
  const [m, setM] = useState(init.m)
  const [q, setQ] = useState(init.q)

  const nowY = new Date().getFullYear()
  const years = []
  for (let yr = nowY + 1; yr >= 2022; yr--) years.push(String(yr))

  // Ре-синхронизация с пропом value при ВНЕШНЕЙ смене (переиспользование того же
  // инстанса под другую запись — напр. форма правки операций не пере-монтируется
  // между строками). lastEmit отделяет наш собственный emit от внешнего изменения:
  // без этого переход Месяц→Квартал (эмитит '') сбрасывал бы режим обратно на месяц.
  const lastEmit = useRef(value)
  useEffect(() => {
    if (value === lastEmit.current) return
    lastEmit.current = value
    const p = parsePeriod(value)
    setMode(p.mode); setY(p.y); setM(p.m); setQ(p.q)
  }, [value])

  const emit = (nMode, nY, nM, nQ) => {
    const v = nMode === 'month' ? (nY && nM ? `${nY}-${nM}` : '') : (nQ && nY ? `Q${nQ} ${nY}` : '')
    lastEmit.current = v
    onChange(v)
  }

  // ── Десктоп: один компактный ряд под стиль полей operations.js ──
  if (dense) {
    const sel = { boxSizing: 'border-box', appearance: 'none', WebkitAppearance: 'none', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 11px', fontSize: 13, fontFamily: UI, color: 'var(--text-primary)', background: 'var(--bg-card)', cursor: 'pointer', outline: 'none' }
    const segBtn = (active) => ({ flex: '0 0 auto', border: 'none', borderRadius: 7, padding: '0 12px', fontFamily: MONO, fontSize: 12, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })
    return (
      <div style={{ display: 'flex', gap: 6, height: 36, alignItems: 'stretch' }}>
        {allowQuarter && (
          <div style={{ display: 'flex', flex: '0 0 auto', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, alignItems: 'stretch' }}>
            <button type="button" onClick={() => { setMode('month'); emit('month', y, m, q) }} style={segBtn(mode === 'month')}>Мес</button>
            <button type="button" onClick={() => { setMode('quarter'); emit('quarter', y, m, q) }} style={segBtn(mode === 'quarter')}>Кв</button>
          </div>
        )}
        {mode === 'month' ? (
          <select value={m} onChange={e => { const nm = e.target.value; const ny = y || (nm ? String(nowY) : ''); setM(nm); setY(ny); emit('month', ny, nm, q) }} style={{ ...sel, flex: 1, minWidth: 0 }}>
            <option value="">Месяц</option>
            {MONTHS_RU.map((mn, i) => <option key={i} value={String(i + 1).padStart(2, '0')}>{mn}</option>)}
          </select>
        ) : (
          <select value={q} onChange={e => { const nq = e.target.value; const ny = y || (nq ? String(nowY) : ''); setQ(nq); setY(ny); emit('quarter', ny, m, nq) }} style={{ ...sel, flex: 1, minWidth: 0 }}>
            <option value="">Квартал</option>
            {[1, 2, 3, 4].map(n => <option key={n} value={String(n)}>{n}-й кв</option>)}
          </select>
        )}
        <select value={y} onChange={e => { setY(e.target.value); emit(mode, e.target.value, m, q) }} style={{ ...sel, flex: '0 0 74px' }}>
          <option value="">Год</option>
          {years.map(yr => <option key={yr} value={yr}>{yr}</option>)}
        </select>
      </div>
    )
  }

  // ── Мобильная раскладка (без изменений) ──
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

export default PeriodSelect
