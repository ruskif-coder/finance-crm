import Navbar from '../components/Navbar'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

const api = (token) => axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))

// Нейтральная карточка + цвет банка (см. design_integration.MD §11)
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

function MultiDropdown({ label, items, selected, onToggle, onClear, placeholder }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const filtered = items.filter(i => i.toLowerCase().includes(search.toLowerCase()))

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
                  {item}
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

function DebtTable({ rows, amountColor, filterArticles, setFilterArticles, filterCounterparties, setFilterCounterparties }) {
  const [sortCol, setSortCol] = useState('amount')
  const [sortDir, setSortDir] = useState('desc')
  const [expanded, setExpanded] = useState({})

  const rowKey = (r) => `${r.counterparty_id}_${r.article_id}_${r.period}`
  const toggleExpand = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  const allArticles = [...new Set(rows.map(r => r.article).filter(Boolean))]
  const allCounterparties = [...new Set(rows.map(r => r.counterparty).filter(Boolean))]

  const toggle = (arr, set, val) => set(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val])

  const filtered = rows.filter(r => {
    if (filterArticles.length > 0 && !filterArticles.includes(r.article)) return false
    if (filterCounterparties.length > 0 && !filterCounterparties.includes(r.counterparty)) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const totalFiltered = sorted.reduce((s, r) => s + r.amount, 0)

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('desc') }
  }

  const SortIcon = ({ col }) => sortCol !== col
    ? <span style={{ color: 'var(--text-faint)', marginLeft: '4px' }}>↕</span>
    : <span style={{ color: 'var(--accent)', marginLeft: '4px' }}>{sortDir === 'asc' ? '↑' : '↓'}</span>

  const thS = { textAlign: 'left', padding: '7px 8px', color: 'var(--text-muted)', fontWeight: '500', fontSize: '14px', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid var(--border-card)', whiteSpace: 'nowrap' }

  return (
    <div>
      {/* Фильтры */}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px', marginTop: '4px' }}>
        <MultiDropdown
          label="Статья" items={allArticles} selected={filterArticles}
          onToggle={v => toggle(filterArticles, setFilterArticles, v)}
          onClear={() => setFilterArticles([])} placeholder="Все статьи" />
        <MultiDropdown
          label="Контрагент" items={allCounterparties} selected={filterCounterparties}
          onToggle={v => toggle(filterCounterparties, setFilterCounterparties, v)}
          onClear={() => setFilterCounterparties([])} placeholder="Все контрагенты" />
        {(filterArticles.length > 0 || filterCounterparties.length > 0) && (
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button onClick={() => { setFilterArticles([]); setFilterCounterparties([]) }}
              style={{ padding: '6px 12px', borderRadius: 'var(--radius-badge)', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'var(--text-muted)' }}>
              Сбросить всё
            </button>
          </div>
        )}
      </div>

      {/* Таблица */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
        <thead>
          <tr>
            <th style={thS} onClick={() => handleSort('counterparty')}>Контрагент <SortIcon col="counterparty" /></th>
            <th style={thS} onClick={() => handleSort('article')}>Статья <SortIcon col="article" /></th>
            <th style={thS} onClick={() => handleSort('period')}>Период <SortIcon col="period" /></th>
            <th style={{ ...thS, textAlign: 'right' }} onClick={() => handleSort('amount')}>Сумма <SortIcon col="amount" /></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const key = rowKey(r)
            const isOpen = !!expanded[key]
            const hasOps = r.operations && r.operations.length > 0
            return (
              <>
                <tr key={key} style={{ borderBottom: isOpen ? 'none' : '1px solid var(--border-row)', cursor: hasOps ? 'pointer' : 'default' }}
                  onClick={() => hasOps && toggleExpand(key)}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <td style={{ padding: '7px 8px', color: 'var(--text-secondary)' }}>
                    {hasOps && <span style={{ display: 'inline-block', width: '14px', color: 'var(--text-faint)', fontSize: '13px' }}>{isOpen ? '▾' : '▸'}</span>}
                    {r.counterparty}
                  </td>
                  <td style={{ padding: '7px 8px', color: 'var(--text-muted)' }}>{r.article}</td>
                  <td style={{ padding: '7px 8px', color: 'var(--text-muted)' }}>{formatPeriod(r.period)}</td>
                  <td style={{ padding: '7px 8px', textAlign: 'right', color: amountColor, fontWeight: '500' }}>{fmt(r.amount)} ₽</td>
                </tr>
                {isOpen && hasOps && (
                  <tr key={key + '_detail'} style={{ borderBottom: '1px solid var(--border-row)' }}>
                    <td colSpan={4} style={{ padding: '0 8px 10px 28px', background: 'var(--bg-subtle)' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Сумма</th>
                            <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>№ ДС</th>
                            <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>№ Счёта</th>
                            <th style={{ textAlign: 'left', padding: '5px 6px', color: 'var(--text-faint)', fontWeight: '500' }}>Дата счёта</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.operations.map(op => (
                            <tr key={op.id}>
                              <td style={{ padding: '4px 6px', color: amountColor }}>{fmt(op.amount)} ₽</td>
                              <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{op.ds_num || '—'}</td>
                              <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{op.invoice || '—'}</td>
                              <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{formatDate(op.invoice_date)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </>
            )
          })}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: '2px solid var(--border-card)' }}>
            <td colSpan={3} style={{ padding: '8px', fontWeight: '600', fontSize: '15px' }}>
              Итого {filtered.length < rows.length ? `(${filtered.length} из ${rows.length})` : ''}
            </td>
            <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700', color: amountColor }}>{fmt(totalFiltered)} ₽</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export default function Balance() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showReceivables, setShowReceivables] = useState(false)
  const [showPayables, setShowPayables] = useState(false)
  const [recArticles, setRecArticles] = useState([])
  const [recCounterparties, setRecCounterparties] = useState([])
  const [payArticles, setPayArticles] = useState([])
  const [payCounterparties, setPayCounterparties] = useState([])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    loadBalance(token)
  }, [])

  const loadBalance = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get('/reports/balance/full')
      setData(res.data)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)' }}>Загрузка баланса...</div>
  if (!data) return null

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

      <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>

        {/* Итоговые карточки */}
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

        {/* Денежные средства */}
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

        {/* Дебиторская */}
        <Section
          title="Дебиторская задолженность"
          amount={data.total_receivables}
          color="var(--dot-current-dz)"
          count={data.receivables.length}
          isExpanded={showReceivables}
          onToggle={() => setShowReceivables(v => !v)}>
          <div style={{ padding: '0 20px 16px' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '12px', marginTop: '12px' }}>
              Ожидаемые поступления (план поступлений)
            </div>
            <DebtTable
              rows={data.receivables}
              amountColor="var(--income)"
              filterArticles={recArticles}
              setFilterArticles={setRecArticles}
              filterCounterparties={recCounterparties}
              setFilterCounterparties={setRecCounterparties}
            />
          </div>
        </Section>

        <div style={{ ...sectionHeader, marginBottom: '8px', marginTop: '8px' }}>Обязательства</div>

        {/* Кредиторская */}
        <Section
          title="Кредиторская задолженность"
          amount={data.total_payables}
          color="var(--expense)"
          count={data.payables.length}
          isExpanded={showPayables}
          onToggle={() => setShowPayables(v => !v)}>
          <div style={{ padding: '0 20px 16px' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '12px', marginTop: '12px' }}>
              Запланированные выплаты (план оплат)
            </div>
            <DebtTable
              rows={data.payables}
              amountColor="var(--expense)"
              filterArticles={payArticles}
              setFilterArticles={setPayArticles}
              filterCounterparties={payCounterparties}
              setFilterCounterparties={setPayCounterparties}
            />
          </div>
        </Section>

      </div>
    </div>
  )
}
