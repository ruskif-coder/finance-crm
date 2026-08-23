import Navbar from '@/components/Navbar'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { makeApi as api } from '@/lib/http'
import { getPermissions, can } from '@/lib/auth'
import { grp0 as fmt } from '@/lib/salesFormat'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const BalanceMobile = dynamic(() => import('@/components/mobile/BalanceMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })


const BANK_STYLES = {
  'АльфаБанк':  { color: 'var(--bank-alfa)' },
  'ОПТ Банк':   { color: 'var(--bank-opt)' },
  'Совкомбанк': { color: 'var(--bank-sovkom)' },
  'Наличные':   { color: 'var(--bank-cash)' },
}

const sectionHeader = {
  fontSize: 13, fontWeight: 700, color: 'var(--accent)',
  background: 'var(--accent-tint)', padding: '10px 22px',
  borderBottom: '1px solid var(--border-inner)',
  letterSpacing: '.03em', textTransform: 'uppercase', borderRadius: 'var(--radius-card-sm) var(--radius-card-sm) 0 0',
}

const diffStyle = (diff) => ({
  color: diff >= 0 ? 'var(--income)' : 'var(--expense)',
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
})

const MONTH_NAMES = {
  '01':'Янв','02':'Фев','03':'Мар','04':'Апр','05':'Май','06':'Июн',
  '07':'Июл','08':'Авг','09':'Сен','10':'Окт','11':'Ноя','12':'Дек'
}

const formatPeriod = (p) => {
  if (!p) return '—'
  const [year, month] = p.split('-')
  return month ? `${MONTH_NAMES[month] || month} ${year}` : p
}

const formatDate = (d) => {
  if (!d) return '—'
  const [year, month, day] = d.split('-')
  return day ? `${day}.${month}.${year}` : d
}

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
        style={{ padding: '6px 10px', borderRadius: 'var(--radius-badge)', border: '1px solid var(--border-card)', fontSize: '14px', cursor: 'pointer', background: 'var(--bg-card)', minWidth: '150px', userSelect: 'none', whiteSpace: 'nowrap' }}>
        {selected.length === 0 ? `${placeholder} ▾` : `Выбрано: ${selected.length} ▾`}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '4px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 'var(--radius-badge)', boxShadow: 'var(--shadow-card)', zIndex: 300, minWidth: '220px', maxHeight: '280px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px' }}>
            <input autoFocus placeholder="Поиск..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--border-card)', fontSize: '14px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.map(item => {
              const active = selected.includes(item)
              return (
                <div key={item} onClick={() => onToggle(item)}
                  style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', background: active ? 'var(--accent-tint)' : 'var(--bg-card)' }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = active ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
                  <span style={{ width: '14px', height: '14px', borderRadius: '3px', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent)' : 'var(--bg-card)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {active && <span style={{ color: 'var(--bg-card)', fontSize: '12px' }}>✓</span>}
                  </span>
                  {fmtItem(item)}
                </div>
              )
            })}
          </div>
          {selected.length > 0 && (
            <div onClick={() => { onClear(); setSearch('') }} style={{ padding: '8px 12px', borderTop: '1px solid var(--border-card)', fontSize: '14px', color: 'var(--expense)', cursor: 'pointer' }}>
              Сбросить выбор
            </div>
          )}
        </div>
      )}
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

function DebtPanel({ data, mode, canEditNote, onSaveNote }) {
  const isReceivables = mode === 'receivables'
  const amountColor = isReceivables ? 'var(--income)' : 'var(--expense)'
  const groupLabel = isReceivables ? 'Контрагент' : 'Статья'
  const secondaryLabel = isReceivables ? 'Статья' : 'Контрагент'
  const groupKey = (r) => isReceivables ? r.counterparty_id : r.article_id
  const groupTitle = (r) => isReceivables ? r.counterparty : r.article
  const opSecondary = (op) => isReceivables ? op.article : op.counterparty
  const totalCols = isReceivables ? 8 : 4

  const [filterPrimary, setFilterPrimary] = useState([])
  const [filterPeriods, setFilterPeriods] = useState([])
  const [overdueOnly, setOverdueOnly] = useState(true)
  const [sortCol, setSortCol] = useState('amount')
  const [sortDir, setSortDir] = useState('desc')
  const [expanded, setExpanded] = useState({})
  const [notes, setNotes] = useState({})
  const [savedNotes, setSavedNotes] = useState({})
  const [noteStatus, setNoteStatus] = useState({})

  useEffect(() => {
    if (data && isReceivables) {
      const initial = Object.fromEntries(data.rows.map(r => [r.counterparty_id, r.note || '']))
      setNotes(initial)
      setSavedNotes(initial)
    }
  }, [data, isReceivables])

  const saveNote = async (key, value) => {
    setNoteStatus(prev => ({ ...prev, [key]: 'saving' }))
    try {
      await onSaveNote(key, value)
      setSavedNotes(prev => ({ ...prev, [key]: value }))
      setNoteStatus(prev => ({ ...prev, [key]: 'saved' }))
      setTimeout(() => setNoteStatus(prev => ({ ...prev, [key]: undefined })), 1500)
    } catch (e) {
      setNoteStatus(prev => ({ ...prev, [key]: undefined }))
      alert('Не удалось сохранить примечание')
    }
  }

  const allPrimary = [...new Set(data.rows.flatMap(r => r.operations.map(opSecondary)))].filter(Boolean).sort()
  const allPeriods = [...new Set(data.rows.flatMap(r => r.operations.map(o => o.period)))].filter(Boolean).sort()

  const toggle = (arr, set, val) => set(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val])

  const filteredRows = data.rows.map(r => {
    const ops = r.operations.filter(o => {
      if (overdueOnly && o.aging_bucket !== 'overdue' && o.aging_bucket !== 'current') return false
      if (filterPrimary.length > 0 && !filterPrimary.includes(opSecondary(o))) return false
      if (filterPeriods.length > 0 && !filterPeriods.includes(o.period)) return false
      return true
    })
    if (ops.length === 0) return null
    const amount = ops.reduce((s, o) => s + o.amount, 0)
    const aging = { overdue: 0, current: 0, future: 0, unknown: 0 }
    ops.forEach(o => { aging[o.aging_bucket] += o.amount })
    return { ...r, title: groupTitle(r), operations: ops, amount, op_count: ops.length, aging }
  }).filter(Boolean)

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

  const toggleExpand = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  const totalFiltered = sortedRows.reduce((s, r) => s + r.amount, 0)
  const totalOpsFiltered = sortedRows.reduce((s, r) => s + r.op_count, 0)

  const hasActiveFilters = filterPrimary.length > 0 || filterPeriods.length > 0 || !overdueOnly

  const thS = { textAlign: 'left', padding: '7px 8px', color: 'var(--text-muted)', fontWeight: '500', fontSize: '14px', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid var(--border-card)', whiteSpace: 'nowrap' }

  return (
    <div>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '10px' }}>
        Срок оплаты = период операции + отсрочка контрагента (стандартно 60 дн.); текущая задолженность — до 30 дн. после срока, далее — просрочка
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '16px' }}>
        {BUCKET_ORDER.map(b => (
          <AgingCard key={b} bucket={b} data={data.aging_summary[b]}
            active={b === 'overdue' && overdueOnly}
            onClick={() => b === 'overdue' && setOverdueOnly(v => !v)} />
        ))}
      </div>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px', alignItems: 'flex-end' }}>
        <MultiDropdown
          label={secondaryLabel} items={allPrimary} selected={filterPrimary}
          onToggle={v => toggle(filterPrimary, setFilterPrimary, v)}
          onClear={() => setFilterPrimary([])} placeholder={`Все: ${secondaryLabel.toLowerCase()}`} />
        <MultiDropdown
          label="Период" items={allPeriods} selected={filterPeriods} formatItem={formatPeriod}
          onToggle={v => toggle(filterPeriods, setFilterPeriods, v)}
          onClear={() => setFilterPeriods([])} placeholder="Все периоды" />
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: 'var(--text-secondary)', cursor: 'pointer', padding: '7px 10px', border: '1px solid var(--border-card)', borderRadius: 'var(--radius-badge)', background: overdueOnly ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
          <input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)} />
          Только актуальные
        </label>
        {hasActiveFilters && (
          <button onClick={() => { setFilterPrimary([]); setFilterPeriods([]); setOverdueOnly(true) }}
            style={{ padding: '7px 12px', borderRadius: 'var(--radius-badge)', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'var(--text-muted)' }}>
            Сбросить всё
          </button>
        )}
      </div>

      <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card-sm)', border: '1px solid var(--border-card)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
          <thead>
            <tr>
              <th style={thS} onClick={() => handleSort('title')}>{groupLabel} <SortIcon col="title" /></th>
              {isReceivables && <th style={thS}>ИНН</th>}
              {isReceivables && <th style={thS}>№ договора</th>}
              {isReceivables && <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('term_days')}>Отсрочка <SortIcon col="term_days" /></th>}
              <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('amount')}>Сумма <SortIcon col="amount" /></th>
              <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('op_count')}>Кол-во <SortIcon col="op_count" /></th>
              <th style={thS}>Возраст</th>
              {isReceivables && <th style={thS}>Примечание</th>}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map(r => {
              const key = groupKey(r)
              const isOpen = !!expanded[key]
              return (
                <>
                  <tr key={key} style={{ borderBottom: isOpen ? 'none' : '1px solid var(--border-row)', cursor: 'pointer' }}
                    onClick={() => toggleExpand(key)}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding: '8px', color: 'var(--text-secondary)' }}>
                      <span style={{ display: 'inline-block', width: '14px', color: 'var(--text-faint)', fontSize: '13px' }}>{isOpen ? '▾' : '▸'}</span>
                      {r.title}
                    </td>
                    {isReceivables && (
                      <td style={{ padding: '8px' }} onClick={e => e.stopPropagation()}>
                        {r.inn ? (
                          <a href={`/directory/counterparties/${r.counterparty_id}`} target="_blank" rel="noopener noreferrer"
                            style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}
                            onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
                            onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
                            title="Открыть карточку контрагента в справочнике">
                            {r.inn}
                          </a>
                        ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                    )}
                    {isReceivables && <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{r.contract_number || '—'}</td>}
                    {isReceivables && <td style={{ padding: '8px', textAlign: 'right', color: 'var(--text-muted)' }}>{r.term_days} дн.</td>}
                    <td style={{ padding: '8px', textAlign: 'right', color: amountColor, fontWeight: '500' }}>{fmt(r.amount)} ₽</td>
                    <td style={{ padding: '8px', textAlign: 'right', color: 'var(--text-muted)' }}>{r.op_count}</td>
                    <td style={{ padding: '8px' }}><AgingBadges aging={r.aging} /></td>
                    {isReceivables && (
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
                    )}
                  </tr>
                  {isOpen && (
                    <tr key={key + '_detail'} style={{ borderBottom: '1px solid var(--border-row)' }}>
                      <td colSpan={totalCols} style={{ padding: '0 8px 10px 28px', background: 'var(--bg-subtle)' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                          <thead>
                            <tr>
                              <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Дата</th>
                              <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>{secondaryLabel}</th>
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
                                  <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{opSecondary(op)}</td>
                                  <td style={{ padding: '4px 6px', color: 'var(--text-muted)' }}>{formatPeriod(op.period)}</td>
                                  <td style={{ padding: '4px 6px', color: 'var(--text-muted)' }}>{formatDate(op.due_date)}</td>
                                  <td style={{ padding: '4px 6px' }}>
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '12px', padding: '2px 8px', borderRadius: 'var(--radius-badge)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontWeight: 600 }}>
                                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                                      {meta.short}
                                    </span>
                                  </td>
                                  <td style={{ padding: '4px 6px', textAlign: 'right', color: amountColor }}>{fmt(op.amount)} ₽</td>
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
              <tr><td colSpan={totalCols} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-faint)' }}>Нет данных по выбранным фильтрам</td></tr>
            )}
          </tbody>
          <tfoot>
            <tr style={{ borderTop: '2px solid var(--border-card)' }}>
              <td colSpan={isReceivables ? 4 : 1} style={{ padding: '8px', fontWeight: '600', fontSize: '15px' }}>
                Итого {sortedRows.length < data.rows.length ? `(${sortedRows.length} из ${data.rows.length})` : ''}
              </td>
              <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700', color: amountColor }}>{fmt(totalFiltered)} ₽</td>
              <td style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: 'var(--text-muted)' }}>{totalOpsFiltered}</td>
              <td></td>
              {isReceivables && <td></td>}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

export default function Balance() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [data, setData] = useState(null)
  const [receivablesData, setReceivablesData] = useState(null)
  const [payablesData, setPayablesData] = useState(null)
  const [permissions, setPermissions] = useState({})
  const [loading, setLoading] = useState(true)
  const [showReceivables, setShowReceivables] = useState(false)
  const [showPayables, setShowPayables] = useState(false)
  // Примечания дебиторки на мобиле: десктоп держит это состояние внутри DebtPanel
  // (свой экземпляр на каждый рендер), мобильному компоненту нужно то же на уровне
  // страницы — тот же паттерн, что уже применяется в pages/finance/receivables.js.
  const [notes, setNotes] = useState({})
  const [savedNotes, setSavedNotes] = useState({})
  const [noteStatus, setNoteStatus] = useState({})

  useEffect(() => {
    if (receivablesData) {
      const initial = Object.fromEntries(receivablesData.rows.map(r => [r.counterparty_id, r.note || '']))
      setNotes(initial)
      setSavedNotes(initial)
    }
  }, [receivablesData])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    setPermissions(getPermissions())
    loadBalance(token)
  }, [])

  const loadBalance = async (token) => {
    setLoading(true)
    try {
      const a = api(token)
      const [fullRes, recRes, payRes] = await Promise.all([
        a.get('/reports/balance/full'),
        a.get('/reports/balance/receivables'),
        a.get('/reports/balance/payables'),
      ])
      setData(fullRes.data)
      setReceivablesData(recRes.data)
      setPayablesData(payRes.data)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const saveCounterpartyNote = async (counterpartyId, note) => {
    const token = localStorage.getItem('token')
    await api(token).patch(`/reports/receivables/${counterpartyId}/note`, { note })
  }

  const saveNote = async (key, value) => {
    setNoteStatus(prev => ({ ...prev, [key]: 'saving' }))
    try {
      await saveCounterpartyNote(key, value)
      setSavedNotes(prev => ({ ...prev, [key]: value }))
      setNoteStatus(prev => ({ ...prev, [key]: 'saved' }))
      setTimeout(() => setNoteStatus(prev => ({ ...prev, [key]: undefined })), 1500)
    } catch (e) {
      setNoteStatus(prev => ({ ...prev, [key]: undefined }))
      alert('Не удалось сохранить примечание')
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)' }}>Загрузка баланса...</div>
  if (!data || !receivablesData || !payablesData) return null

  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
        <Head><title>Баланс | Финансовый учёт</title></Head>
        <Navbar active="balance" />
        <BalanceMobile
          data={data} receivablesData={receivablesData} payablesData={payablesData}
          notes={notes} setNotes={setNotes} savedNotes={savedNotes} saveNote={saveNote}
          canEditNote={can(permissions, 'receivables', 'edit')} noteStatus={noteStatus}
        />
      </div>
    )
  }

  const Section = ({ title, amount, color, children, isExpanded, onToggle, count }) => (
    <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', marginBottom: '12px', overflow: 'hidden' }}>
      <div onClick={onToggle} style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: children ? 'pointer' : 'default', borderBottom: isExpanded ? '1px solid var(--border-card)' : 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '17px', fontWeight: '600', color: 'var(--text-primary)' }}>{title}</span>
          {count !== undefined && <span style={{ fontSize: '14px', color: 'var(--text-muted)', background: 'var(--bg-subtle)', padding: '2px 8px', borderRadius: '20px' }}>{count} позиций</span>}
          {children && <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>{isExpanded ? '▲' : '▼'}</span>}
        </div>
        <span style={{ fontSize: '20px', fontWeight: '700', color }}>{fmt(amount)} ₽</span>
      </div>
      {isExpanded && children}
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar active="balance" />
      <Head><title>Баланс | Финансовый учёт</title></Head>

      <div style={{ padding: '24px', maxWidth: 1920, margin: '0 auto' }}>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '24px' }}>
          {[
            { label: 'Итого активы', val: data.total_assets, color: 'var(--income)' },
            { label: 'Итого обязательства', val: data.total_payables, color: 'var(--expense)' },
            { label: 'Чистые активы', val: data.net_assets, color: data.net_assets >= 0 ? 'var(--income)' : 'var(--expense)' },
          ].map(m => (
            <div key={m.label} style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', padding: '16px 20px', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '6px' }}>{m.label}</div>
              <div style={{ fontSize: '24px', fontWeight: '700', color: m.color }}>{fmt(m.val)} ₽</div>
            </div>
          ))}
        </div>

        <div style={{ ...sectionHeader, marginBottom: '8px' }}>Активы</div>

        <Section title="Денежные средства" amount={data.total_cash} color="var(--income)" isExpanded={true}>
          <div style={{ padding: '12px 20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
              {data.banks.map(b => {
                const style = BANK_STYLES[b.bank] || { color: 'var(--text-secondary)' }
                return (
                  <div key={b.bank} style={{ borderRadius: 'var(--radius-card-sm)', padding: '12px 16px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderLeft: `3px solid ${style.color}` }}>
                    <div style={{ fontSize: '14px', fontWeight: '500', color: style.color, marginBottom: '8px' }}>{b.bank}</div>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '2px' }}>Стартовый: {fmt(b.opening_balance)} ₽</div>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '2px' }}>Поступило: {fmt(b.income)} ₽</div>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '6px' }}>Списано: {fmt(b.expense)} ₽</div>
                    <div style={{ fontSize: '18px', ...diffStyle(b.balance) }}>{fmt(b.balance)} ₽</div>
                  </div>
                )
              })}
            </div>
          </div>
        </Section>

        <Section
          title="Дебиторская задолженность"
          amount={receivablesData.summary.total_amount}
          color="var(--dot-current-dz)"
          count={receivablesData.summary.counterparty_count}
          isExpanded={showReceivables}
          onToggle={() => setShowReceivables(v => !v)}>
          <div style={{ padding: '16px 20px' }}>
            <DebtPanel
              data={receivablesData}
              mode="receivables"
              canEditNote={can(permissions, 'receivables', 'edit')}
              onSaveNote={saveCounterpartyNote}
            />
          </div>
        </Section>

        <div style={{ ...sectionHeader, marginBottom: '8px', marginTop: '8px' }}>Обязательства</div>

        <Section
          title="Кредиторская задолженность"
          amount={payablesData.summary.total_amount}
          color="var(--expense)"
          count={payablesData.summary.article_count}
          isExpanded={showPayables}
          onToggle={() => setShowPayables(v => !v)}>
          <div style={{ padding: '16px 20px' }}>
            <DebtPanel data={payablesData} mode="payables" />
          </div>
        </Section>

      </div>
    </div>
  )
}
