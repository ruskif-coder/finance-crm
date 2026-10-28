/**
 * «Операции» карточки контрагента v2 (хендофф «контрикZ»): поиск (№ ДС, счёт, статья, сумма), чипы со счётчиками (все · план ·
 * оплачено · приход · расход) и чип выбранного месяца; прокрутка внутри, липкая шапка; план — подложка `--warning-bg`; банк — квадрат
 * цвета банка; ДС и счёт — одной ячейкой; сортировка по дате убыванием, план без даты сверху; подвал — итоги по отфильтрованному.
 * Фильтр, месяц и поиск живут на странице: «показать →» в «Расчётах» и клик по графику их ставят.
 */
import { useMemo } from 'react'
import { MONO } from '@/components/salesTableKit'
import { bankColor, fmtDateFull } from '@/lib/salesFormat'
import { box, cap, h2, count, money } from '@/components/contractCard/ui'

const COLS = '90px 110px minmax(150px, 1fr) 80px 130px 130px 130px minmax(150px, 1fr)'
export const FILTERS = [
  { key: 'all', label: 'все', test: () => true },
  { key: 'plan', label: 'план', test: o => /ПЛАН/.test(o.status) },
  { key: 'paid', label: 'оплачено', test: o => o.status === 'ОПЛАЧЕНО' },
  { key: 'in', label: 'приход', test: o => (o.income || 0) > 0 },
  { key: 'out', label: 'расход', test: o => (o.expense || 0) > 0 },
]
const STATUS = { 'ОПЛАЧЕНО': ['оплачено', 'var(--income-fg)'], 'ПЛАН ОПЛАТ': ['план оплат', 'var(--warning-fg)'], 'ПЛАН ПОСТУПЛЕНИЙ': ['план поступл.', 'var(--accent-fg)'] }

function Chip({ on, label, n, onClick, close }) {
  return (
    <span onClick={onClick} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 8, border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                                      background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
      {label}{n != null && <span style={{ fontFamily: MONO, fontSize: 10.5, color: on ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{n}</span>}{close && <span>×</span>}
    </span>
  )
}

const byDate = (a, b) => {
  const pa = !a.date && /ПЛАН/.test(a.status), pb = !b.date && /ПЛАН/.test(b.status)
  if (pa !== pb) return pa ? -1 : 1
  return String(b.date || '').localeCompare(String(a.date || ''))
}

export default function Operations({ rows, filter, onFilter, month, onMonth, q, onQ }) {
  const sorted = useMemo(() => [...rows].sort(byDate), [rows])
  const base = month ? sorted.filter(o => o.period === month) : sorted
  const needle = q.trim().toLowerCase()
  const f = FILTERS.find(x => x.key === filter) || FILTERS[0]
  const pass = base.filter(o => f.test(o) && (!needle || [o.ds_num, o.invoice, o.article, o.income, o.expense].join(' ').toLowerCase().includes(needle)))
  const inc = pass.reduce((s, o) => s + (o.income || 0), 0)
  const exp = pass.reduce((s, o) => s + (o.expense || 0), 0)
  return (
    <section style={{ ...box, padding: '16px 20px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 10 }}><span style={h2}>Операции</span><span style={count}>{rows.length}</span></div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 10 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 10px', width: 240, boxSizing: 'border-box', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 9 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
          <input value={q} onChange={e => onQ(e.target.value)} placeholder="№ ДС, счёт, статья, сумма" style={{ flex: 1, minWidth: 0, border: 0, outline: 'none', background: 'transparent', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--text-primary)' }} />
        </span>
        {FILTERS.map(x => <Chip key={x.key} on={filter === x.key} label={x.label} n={base.filter(x.test).length} onClick={() => onFilter(x.key)} />)}
        {month && <Chip on label={`месяц ${month}`} close onClick={() => onMonth(null)} />}
      </div>
      <div style={{ overflow: 'auto', maxHeight: 520, borderBottom: '1px solid var(--border-inner)' }}>
        <div style={{ minWidth: 1040 }}>
          <div style={{ ...cap, position: 'sticky', top: 0, zIndex: 1, background: 'var(--bg-card)', display: 'grid', gridTemplateColumns: COLS, gap: 12, padding: '0 8px 7px', borderBottom: '1px solid var(--border-card)' }}>
            <span>дата</span><span>статус</span><span>статья</span><span>период</span><span style={{ textAlign: 'right' }}>приход</span>
            <span style={{ textAlign: 'right' }}>расход</span><span>банк</span><span>ДС · счёт</span>
          </div>
          {pass.map(o => {
            const plan = /ПЛАН/.test(o.status)
            const st = STATUS[o.status] || [o.status, 'var(--text-secondary)']
            return (
              <div key={o.id} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: '8px 8px', borderBottom: '1px solid var(--border-row)', background: plan ? 'var(--warning-bg)' : 'transparent', fontSize: 12.5 }}>
                <span style={{ fontFamily: MONO }}>{o.date ? fmtDateFull(o.date) : '—'}</span>
                <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: st[1], textTransform: 'uppercase' }}>{st[0]}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.article || '—'}</span>
                <span style={{ fontFamily: MONO, fontSize: 12 }}>{o.period || '—'}</span>
                <span style={{ fontFamily: MONO, fontWeight: 700, textAlign: 'right', color: o.income ? (plan ? 'var(--warning-fg)' : 'var(--income-fg)') : 'var(--text-disabled)' }}>{o.income ? money(o.income) : '—'}</span>
                <span style={{ fontFamily: MONO, fontWeight: 700, textAlign: 'right', color: o.expense ? (plan ? 'var(--warning-fg)' : 'var(--text-primary)') : 'var(--text-disabled)' }}>{o.expense ? money(o.expense) : '—'}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: o.bank ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, flex: '0 0 8px', background: o.bank ? bankColor(o.bank) : 'var(--text-disabled)' }} />{o.bank || 'не указан'}
                </span>
                <span style={{ fontFamily: MONO, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {[o.ds_num, o.invoice ? `сч. ${o.invoice}` : null].filter(Boolean).join(' · ') || '—'}
                </span>
              </div>
            )
          })}
          {!pass.length && <span style={{ display: 'block', padding: '16px 8px', fontSize: 12.5, color: 'var(--text-muted)' }}>Под фильтр ничего не попало</span>}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '9px 8px 0', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>показано {pass.length} из {rows.length}</span>
        <span style={{ ...cap, marginLeft: 'auto' }}>приход</span><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--income-fg)' }}>{money(inc)}</span>
        <span style={cap}>расход</span><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{money(exp)}</span>
      </div>
    </section>
  )
}
