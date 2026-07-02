import Navbar from '../components/Navbar'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const api = (token) => axios.create({
  // См. комментарий в balance.js — относительный путь, проксируется Caddy.
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))

const MONTH_NAMES = {
  '01':'Янв','02':'Фев','03':'Мар','04':'Апр','05':'Май','06':'Июн',
  '07':'Июл','08':'Авг','09':'Сен','10':'Окт','11':'Ноя','12':'Дек'
}

const formatPeriod = (p) => {
  if (!p) return '—'
  const m = p.match(/^(\d{4})-(\d{2})$/)
  if (m) return `${MONTH_NAMES[m[2]] || m[2]} ${m[1]}`
  return p
}

const formatDate = (d) => {
  if (!d) return '—'
  const [year, month, day] = d.split('-')
  return day ? `${day}.${month}.${year}` : d
}

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

// Нейтральная плашка + цветная точка (см. design_integration.MD §7 AGING_DOT)
const AGING_META = {
  overdue: { label: 'Просрочено',            short: 'Просрочка', color: 'var(--dot-overdue)' },
  current: { label: 'Текущая задолженность', short: 'Текущая',   color: 'var(--dot-current-dz)' },
  future:  { label: 'План',                  short: 'План',      color: 'var(--accent)' },
  unknown: { label: 'Без периода',           short: 'Без периода', color: 'var(--text-faint)' },
}
const BUCKET_ORDER = ['overdue', 'current', 'future', 'unknown']

function MultiDropdown({ label, items, selected, onToggle, onClear, placeholder, formatItem }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)
  const fmtItem = formatItem || (x => x)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const filtered = items.filter(i => fmtItem(i).toLowerCase().includes(search.toLowerCase()))

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '3px' }}>
        {label} {selected.length > 0 && <span style={{ color: 'var(--accent)' }}>({selected.length})</span>}
      </div>
      <div onClick={() => setOpen(o => !o)}
        style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '14px', cursor: 'pointer', background: 'white', minWidth: '150px', userSelect: 'none', whiteSpace: 'nowrap' }}>
        {selected.length === 0 ? `${placeholder} ▾` : `Выбрано: ${selected.length} ▾`}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '4px', background: 'white', border: '1px solid var(--border-card)', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 300, minWidth: '220px', maxHeight: '280px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px' }}>
            <input autoFocus placeholder="Поиск..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--border-card)', fontSize: '14px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.map(item => {
              const active = selected.includes(item)
              return (
                <div key={item} onClick={() => onToggle(item)}
                  style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', background: active ? 'var(--accent-tint)' : 'white' }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = active ? 'var(--accent-tint)' : 'white' }}>
                  <span style={{ width: '14px', height: '14px', borderRadius: '3px', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent)' : 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {active && <span style={{ color: 'white', fontSize: '12px' }}>✓</span>}
                  </span>
                  {fmtItem(item)}
                </div>
              )
            })}
          </div>
          {selected.length > 0 && (
            <div onClick={() => { onClear(); setSearch('') }} style={{ padding: '8px 12px', borderTop: '1px solid var(--border-card)', fontSize: '14px', color: 'var(--dot-overdue)', cursor: 'pointer' }}>
              Сбросить выбор
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SummaryCard({ label, value, color, isCount }) {
  return (
    <div style={{ background: 'white', borderRadius: '12px', padding: '16px 20px', border: '1px solid var(--border-card)' }}>
      <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '6px' }}>{label}</div>
      <div style={{ fontSize: '24px', fontWeight: '700', color }}>{isCount ? fmt(value) : `${fmt(value)} ₽`}</div>
    </div>
  )
}

function AgingCard({ bucket, data, active, onClick }) {
  const meta = AGING_META[bucket]
  if (!data || (data.amount === 0 && data.count === 0)) return null
  return (
    <div onClick={onClick}
      style={{
        borderRadius: 'var(--radius-card-sm)', padding: '14px 18px', background: 'var(--bg-subtle)',
        border: active ? `1px solid ${meta.color}` : '1px solid var(--border-card)',
        cursor: bucket === 'overdue' ? 'pointer' : 'default', boxShadow: active ? `0 0 0 2px ${meta.color}33` : 'none',
      }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '14px', fontWeight: '500', color: 'var(--text-secondary)', marginBottom: '6px' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
        {meta.label}
      </div>
      <div style={{ fontSize: '19px', fontWeight: '700', color: 'var(--text-primary)' }}>{fmt(data.amount)} ₽</div>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>{data.count} операций</div>
    </div>
  )
}

function AgingPieCard({ aging }) {
  const segments = ['overdue', 'current', 'future']
    .map(key => ({ key, value: aging?.[key]?.amount || 0 }))
    .filter(s => s.value > 0)
  const total = segments.reduce((s, x) => s + x.value, 0)

  return (
    <div style={{ background: 'var(--bg-card)', borderRadius: '12px', border: '1px solid var(--border-card)', padding: '16px', width: '380px', flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '8px', flexShrink: 0 }}>Структура задолженности</div>
      {total === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: '13px' }}>Нет данных</div>
      ) : (
        <>
          {/* легенда слева, диаграмма справа — занимает всю оставшуюся высоту
              карточки целиком (без легенды под собой), поэтому кольцо крупнее */}
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flexShrink: 0, width: '130px' }}>
              {segments.map(s => (
                <div key={s.key}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: AGING_META[s.key].color, flexShrink: 0 }} />
                    <span style={{ color: 'var(--text-secondary)' }}>{AGING_META[s.key].short}</span>
                  </div>
                  <div style={{ color: 'var(--text-primary)', fontWeight: '700', fontSize: '18px', marginLeft: '14px' }}>{Math.round(s.value / total * 100)}%</div>
                </div>
              ))}
            </div>
            <div style={{ flex: 1, minWidth: 0, height: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={segments} dataKey="value" nameKey="key" cx="50%" cy="50%" innerRadius="58%" outerRadius="100%" paddingAngle={2} stroke="none">
                    {segments.map(s => <Cell key={s.key} fill={AGING_META[s.key].color} />)}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12 }}
                    formatter={(value, name, props) => [`${fmt(value)} ₽`, AGING_META[props.payload.key].label]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function AgingBadges({ aging }) {
  const entries = BUCKET_ORDER.filter(b => aging[b] > 0)
  return (
    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
      {entries.map(b => {
        const meta = AGING_META[b]
        return (
          <span key={b} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '12px', padding: '2px 8px', borderRadius: 'var(--radius-badge)', background: 'var(--bg-subtle)', color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontWeight: 600 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
            {fmt(aging[b])} ₽
          </span>
        )
      })}
    </div>
  )
}

export default function Receivables() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filterCounterparties, setFilterCounterparties] = useState([])
  const [filterArticles, setFilterArticles] = useState([])
  const [filterPeriods, setFilterPeriods] = useState([])
  const [overdueOnly, setOverdueOnly] = useState(true)
  const [sortCol, setSortCol] = useState('amount')
  const [sortDir, setSortDir] = useState('desc')
  const [expanded, setExpanded] = useState({})
  const [notes, setNotes] = useState({})
  const [savedNotes, setSavedNotes] = useState({})
  const [noteStatus, setNoteStatus] = useState({})

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    load(token)
  }, [])

  useEffect(() => {
    if (data) {
      const initial = Object.fromEntries(data.rows.map(r => [r.counterparty_id, r.note || '']))
      setNotes(initial)
      setSavedNotes(initial)
    }
  }, [data])

  const load = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get('/reports/receivables')
      setData(res.data)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const saveNote = async (cid, value) => {
    const token = localStorage.getItem('token')
    setNoteStatus(prev => ({ ...prev, [cid]: 'saving' }))
    try {
      await api(token).patch(`/reports/receivables/${cid}/note`, { note: value })
      setSavedNotes(prev => ({ ...prev, [cid]: value }))
      setNoteStatus(prev => ({ ...prev, [cid]: 'saved' }))
      setTimeout(() => setNoteStatus(prev => ({ ...prev, [cid]: undefined })), 1500)
    } catch (e) {
      setNoteStatus(prev => ({ ...prev, [cid]: undefined }))
      alert('Не удалось сохранить примечание')
    }
  }

  const downloadExport = async () => {
    const token = localStorage.getItem('token')
    try {
      const params = new URLSearchParams()
      filterCounterparties.forEach(c => params.append('counterparty', c))
      filterArticles.forEach(a => params.append('article', a))
      filterPeriods.forEach(p => params.append('period', p))
      if (overdueOnly) params.append('overdue_only', 'true')
      const qs = params.toString()
      const res = await api(token).get(`/reports/receivables/export${qs ? '?' + qs : ''}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `debitorka_${new Date().toISOString().slice(0,16).replace('T','_').replace(':','')}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      alert('Не удалось скачать файл')
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)' }}>Загрузка дебиторской задолженности...</div>
  if (!data) return null

  const canEditNote = can(getPermissions(), 'receivables', 'edit')

  const allCounterparties = [...new Set(data.rows.map(r => r.counterparty))].filter(Boolean).sort()
  const allArticles = [...new Set(data.rows.flatMap(r => r.operations.map(o => o.article)))].filter(Boolean).sort()
  const allPeriods = [...new Set(data.rows.flatMap(r => r.operations.map(o => o.period)))].filter(Boolean).sort()

  const toggle = (arr, set, val) => set(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val])

  const filteredRows = data.rows
    .filter(r => filterCounterparties.length === 0 || filterCounterparties.includes(r.counterparty))
    .map(r => {
      const ops = r.operations.filter(o => {
        // "только актуальные" — просрочено + текущая задолженность, без плановых (будущих) платежей
        if (overdueOnly && o.aging_bucket !== 'overdue' && o.aging_bucket !== 'current') return false
        if (filterArticles.length > 0 && !filterArticles.includes(o.article)) return false
        if (filterPeriods.length > 0 && !filterPeriods.includes(o.period)) return false
        return true
      })
      if (ops.length === 0) return null
      const amount = ops.reduce((s, o) => s + o.amount, 0)
      const aging = { overdue: 0, current: 0, future: 0, unknown: 0 }
      ops.forEach(o => { aging[o.aging_bucket] += o.amount })
      return { ...r, operations: ops, amount, op_count: ops.length, aging }
    })
    .filter(Boolean)

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('desc') }
  }

  const sortedRows = [...filteredRows].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const SortIcon = ({ col }) => sortCol !== col
    ? <span style={{ color: 'var(--text-faint)', marginLeft: '4px' }}>↕</span>
    : <span style={{ color: 'var(--accent)', marginLeft: '4px' }}>{sortDir === 'asc' ? '↑' : '↓'}</span>

  const toggleExpand = (cid) => setExpanded(prev => ({ ...prev, [cid]: !prev[cid] }))

  const totalFiltered = sortedRows.reduce((s, r) => s + r.amount, 0)
  const totalOpsFiltered = sortedRows.reduce((s, r) => s + r.op_count, 0)

  const hasActiveFilters = filterCounterparties.length > 0 || filterArticles.length > 0 || filterPeriods.length > 0 || !overdueOnly

  const thS = { textAlign: 'left', padding: '7px 8px', color: 'var(--text-muted)', fontWeight: '500', fontSize: '14px', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid var(--border-card)', whiteSpace: 'nowrap' }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar active="receivables">
        <button onClick={downloadExport} title="Скачать в Excel"
          style={{ fontSize: '17px', padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'white', color: 'var(--text-secondary)', cursor: 'pointer', lineHeight: 1 }}>
          ⬇️
        </button>
      </Navbar>

      <div style={{ padding: '24px', maxWidth: 1920, margin: '0 auto' }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '16px' }}>
          <div style={{ fontSize: '20px', fontWeight: '700', color: 'var(--text-primary)' }}>Дебиторская задолженность</div>
          <div style={{ fontSize: '14px', color: 'var(--text-faint)' }}>на {formatDate(data.as_of)}</div>
        </div>

        {/* Сводка + статус задолженности (слева), структура долга (справа) */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', alignItems: 'stretch' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Сводка */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '16px' }}>
              <SummaryCard label="Итого дебиторка" value={data.summary.total_amount} color="var(--income)" />
              <SummaryCard label="Контрагентов-должников" value={data.summary.counterparty_count} color="var(--text-secondary)" isCount />
              <SummaryCard label="Счетов / операций" value={data.summary.operation_count} color="var(--text-secondary)" isCount />
            </div>

            {/* Статус задолженности */}
            <div style={{ fontSize: '13px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px', marginLeft: '4px' }}>
              Срок оплаты = период + отсрочка контрагента (договорных сроков пока нет — стандартно 60 дн., см. колонку «Отсрочка»); текущая задолженность — до 30 дн. после срока, далее — просрочка
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
              {BUCKET_ORDER.map(b => (
                <AgingCard key={b} bucket={b} data={data.aging_summary[b]}
                  active={b === 'overdue' && overdueOnly}
                  onClick={() => b === 'overdue' && setOverdueOnly(v => !v)} />
              ))}
            </div>
          </div>

          <AgingPieCard aging={data.aging_summary} />
        </div>

        {/* Фильтры */}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px', alignItems: 'flex-end' }}>
          <MultiDropdown
            label="Контрагент" items={allCounterparties} selected={filterCounterparties}
            onToggle={v => toggle(filterCounterparties, setFilterCounterparties, v)}
            onClear={() => setFilterCounterparties([])} placeholder="Все контрагенты" />
          <MultiDropdown
            label="Статья" items={allArticles} selected={filterArticles}
            onToggle={v => toggle(filterArticles, setFilterArticles, v)}
            onClear={() => setFilterArticles([])} placeholder="Все статьи" />
          <MultiDropdown
            label="Период" items={allPeriods} selected={filterPeriods} formatItem={formatPeriod}
            onToggle={v => toggle(filterPeriods, setFilterPeriods, v)}
            onClear={() => setFilterPeriods([])} placeholder="Все периоды" />
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: 'var(--text-secondary)', cursor: 'pointer', padding: '7px 10px', border: '1px solid var(--border-card)', borderRadius: '8px', background: overdueOnly ? 'var(--accent-tint)' : 'white' }}>
            <input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)} />
            Только актуальные
          </label>
          {hasActiveFilters && (
            <button onClick={() => { setFilterCounterparties([]); setFilterArticles([]); setFilterPeriods([]); setOverdueOnly(true) }}
              style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'var(--text-muted)' }}>
              Сбросить всё
            </button>
          )}
        </div>

        {/* Таблица по контрагентам */}
        <div style={{ background: 'white', borderRadius: '12px', border: '1px solid var(--border-card)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
            <thead>
              <tr>
                <th style={thS} onClick={() => handleSort('counterparty')}>Контрагент <SortIcon col="counterparty" /></th>
                <th style={thS}>ИНН</th>
                <th style={thS}>№ договора</th>
                <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('term_days')}>Отсрочка <SortIcon col="term_days" /></th>
                <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('amount')}>Сумма <SortIcon col="amount" /></th>
                <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('op_count')}>Кол-во <SortIcon col="op_count" /></th>
                <th style={thS}>Возраст</th>
                <th style={thS}>Примечание</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map(r => {
                const key = r.counterparty_id
                const isOpen = !!expanded[key]
                return (
                  <>
                    <tr key={key} style={{ borderBottom: isOpen ? 'none' : '1px solid var(--border-row)', cursor: 'pointer' }}
                      onClick={() => toggleExpand(key)}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      <td style={{ padding: '8px', color: 'var(--text-secondary)' }}>
                        <span style={{ display: 'inline-block', width: '14px', color: 'var(--text-faint)', fontSize: '13px' }}>{isOpen ? '▾' : '▸'}</span>
                        {r.counterparty}
                      </td>
                      <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{r.inn || '—'}</td>
                      <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{r.contract_number || '—'}</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: 'var(--text-muted)' }}>{r.term_days} дн.</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: 'var(--income)', fontWeight: '500' }}>{fmt(r.amount)} ₽</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: 'var(--text-muted)' }}>{r.op_count}</td>
                      <td style={{ padding: '8px' }}><AgingBadges aging={r.aging} /></td>
                      <td style={{ padding: '4px 8px' }} onClick={e => e.stopPropagation()}>
                        {canEditNote ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <input
                              type="text"
                              value={notes[key] ?? ''}
                              onChange={e => setNotes(prev => ({ ...prev, [key]: e.target.value }))}
                              onBlur={e => {
                                const val = e.target.value
                                if (val !== (savedNotes[key] ?? '')) saveNote(key, val)
                              }}
                              onKeyDown={e => { if (e.key === 'Enter') e.target.blur() }}
                              placeholder="—"
                              style={{ width: '100%', minWidth: '140px', padding: '4px 6px', borderRadius: '6px', border: '1px solid var(--border-card)', fontSize: '14px', outline: 'none' }}
                            />
                            {noteStatus[key] === 'saving' && <span style={{ fontSize: '12px', color: 'var(--text-faint)', flexShrink: 0 }}>…</span>}
                            {noteStatus[key] === 'saved' && <span style={{ fontSize: '12px', color: 'var(--income)', flexShrink: 0 }}>✓</span>}
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>{r.note || '—'}</span>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={key + '_detail'} style={{ borderBottom: '1px solid var(--border-row)' }}>
                        <td colSpan={8} style={{ padding: '0 8px 10px 28px', background: 'var(--bg-subtle)' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                            <thead>
                              <tr>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Дата</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Статья</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Период</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Срок оплаты</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Возраст</th>
                                <th style={{ textAlign: 'right', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Сумма</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>№ ДС</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>№ Счёта</th>
                                <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Дата счёта</th>
                              </tr>
                            </thead>
                            <tbody>
                              {r.operations.map(op => {
                                const meta = AGING_META[op.aging_bucket]
                                return (
                                  <tr key={op.id}>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{formatDate(op.date)}</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{op.article}</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-muted)' }}>{formatPeriod(op.period)}</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-muted)' }}>{formatDate(op.due_date)}</td>
                                    <td style={{ padding: '4px 6px' }}>
                                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '12px', padding: '2px 8px', borderRadius: 'var(--radius-badge)', background: 'var(--bg-subtle)', color: 'var(--text-secondary)', fontWeight: 600 }}>
                                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                                        {meta.short}
                                      </span>
                                    </td>
                                    <td style={{ padding: '4px 6px', textAlign: 'right', color: 'var(--income)' }}>{fmt(op.amount)} ₽</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{op.ds_num || '—'}</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{op.invoice || '—'}</td>
                                    <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{formatDate(op.invoice_date)}</td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
              {sortedRows.length === 0 && (
                <tr><td colSpan={8} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-faint)' }}>Нет данных по выбранным фильтрам</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: '2px solid var(--border-card)' }}>
                <td colSpan={4} style={{ padding: '8px', fontWeight: '600', fontSize: '15px' }}>
                  Итого {sortedRows.length < data.rows.length ? `(${sortedRows.length} из ${data.rows.length})` : ''}
                </td>
                <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700', color: 'var(--income)' }}>{fmt(totalFiltered)} ₽</td>
                <td style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: 'var(--text-muted)' }}>{totalOpsFiltered}</td>
                <td></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>

      </div>
    </div>
  )
}
