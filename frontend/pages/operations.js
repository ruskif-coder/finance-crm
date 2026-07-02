import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Navbar from '../components/Navbar'

const api = (token) => axios.create({
  // См. комментарий в balance.js — относительный путь, проксируется Caddy.
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '—'

const URL_RE = /(https?:\/\/[^\s,;]+)/g
function renderDescription(text) {
  if (!text) return '—'
  const parts = String(text).split(URL_RE)
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const trailMatch = part.match(/[.,;:)\]}»"']+$/)
      const trail = trailMatch ? trailMatch[0] : ''
      const url = trail ? part.slice(0, -trail.length) : part
      return (
        <span key={i}>
          <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'underline' }} onClick={e => e.stopPropagation()}>{url}</a>
          {trail}
        </span>
      )
    }
    return part
  })
}

// Статусы — нейтральная плашка + цветная точка (см. design_integration.MD §6)
const STATUS_DOT = {
  'ОПЛАЧЕНО': 'var(--income)',
  'ПЛАН ОПЛАТ': 'var(--dot-expense)',
  'ПЛАН ПОСТУПЛЕНИЙ': 'var(--dot-income)',
}

const BANK_STYLES = {
  'АльфаБанк':  { color: 'var(--bank-alfa)' },
  'ОПТ Банк':   { color: 'var(--bank-opt)' },
  'Совкомбанк': { color: 'var(--bank-sovkom)' },
  'Наличные':   { color: 'var(--bank-cash)' },
}

// Статус дебиторки по операции — те же 3 категории и цвета, что и в /receivables
// (см. AGING_META там), считается backend'ом только для 'План поступлений'.
const RECEIVABLE_META = {
  overdue: { label: 'Просрочка', color: 'var(--dot-overdue)' },
  current: { label: 'Текущая',   color: 'var(--dot-current-dz)' },
  future:  { label: 'План',      color: 'var(--accent)' },
}

const STATUSES = ['ОПЛАЧЕНО', 'ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const PAGE_SIZE_OPTIONS = [50, 100, 300, 500]
const VAT_OPTIONS = [0, 5, 7, 10, 20, 22]
const isPlan = (s) => s === 'ПЛАН ОПЛАТ' || s === 'ПЛАН ПОСТУПЛЕНИЙ'
const isQuarterPeriod = (p) => /^Q[1-4] \d{4}$/.test(p || '')

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

const emptyForm = {
  date: new Date().toISOString().split('T')[0],
  status: 'ОПЛАЧЕНО', income: 0, expense: 0,
  bank: 'АльфаБанк', period: '', vat_rate: 0,
  article_id: '', counterparty_id: '',
  ds_num: '', invoice: '', invoice_date: '', description: '', document_link: ''
}

function MultiDropdown({ label, items, selected, onToggle, onClear, placeholder, getLabel, getId }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const filtered = items.filter(i => getLabel(i).toLowerCase().includes(search.toLowerCase()))

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '3px' }}>
        {label} {selected.length > 0 && <span style={{ color: 'var(--accent)' }}>({selected.length})</span>}
      </div>
      <div onClick={() => setOpen(o => !o)} style={{ padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '15px', cursor: 'pointer', background: 'white', minWidth: '150px', userSelect: 'none', whiteSpace: 'nowrap' }}>
        {selected.length === 0 ? `${placeholder} ▾` : `Выбрано: ${selected.length} ▾`}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '4px', background: 'white', border: '1px solid var(--border-card)', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 300, minWidth: '200px', maxHeight: '300px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px' }}>
            <input autoFocus placeholder="Поиск..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--border-card)', fontSize: '14px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.map(item => {
              const id = getId(item)
              const lbl = getLabel(item)
              const active = selected.includes(id)
              return (
                <div key={id} onClick={() => onToggle(id)}
                  style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', background: active ? 'var(--accent-tint)' : 'white' }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = active ? 'var(--accent-tint)' : 'white' }}>
                  <span style={{ width: '14px', height: '14px', borderRadius: '3px', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent)' : 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {active && <span style={{ color: 'white', fontSize: '12px', lineHeight: 1 }}>✓</span>}
                  </span>
                  {lbl}
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


function CounterpartySearch({ counterparties, value, onChange, onCreateNew }) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const selected = counterparties.find(c => c.id === parseInt(value))
  const filtered = counterparties.filter(c => c.name.toLowerCase().includes(search.toLowerCase())).slice(0, 50)

  const handleCreate = async () => {
    if (!newName.trim()) return
    const created = await onCreateNew(newName.trim())
    if (created) {
      onChange(created.id)
      setSearch('')
      setNewName('')
      setCreating(false)
      setOpen(false)
    }
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div
        onClick={() => { setOpen(o => !o); setSearch('') }}
        style={{ width: '100%', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '15px', cursor: 'pointer', background: 'white', userSelect: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {selected ? selected.name : '— выберите или введите —'}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px', background: 'white', border: '1px solid var(--border-card)', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 500, maxHeight: '280px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px', borderBottom: '1px solid var(--border-row)' }}>
            <input autoFocus placeholder="Поиск контрагента..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', fontSize: '14px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            <div onClick={() => { onChange(''); setOpen(false) }}
              style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', color: 'var(--text-muted)', borderBottom: '1px solid var(--bg-subtle)' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
              onMouseLeave={e => e.currentTarget.style.background = 'white'}>
              — не указан —
            </div>
            {filtered.map(c => (
              <div key={c.id} onClick={() => { onChange(c.id); setOpen(false); setSearch('') }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', background: value === c.id ? 'var(--accent-tint)' : 'white' }}
                onMouseEnter={e => { if (value !== c.id) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                onMouseLeave={e => { e.currentTarget.style.background = value === c.id ? 'var(--accent-tint)' : 'white' }}>
                {c.name}
              </div>
            ))}
            {search && !filtered.find(c => c.name.toLowerCase() === search.toLowerCase()) && (
              <div onClick={() => { setNewName(search); setCreating(true) }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', color: 'var(--accent)', borderTop: '1px solid var(--border-row)', display: 'flex', alignItems: 'center', gap: '6px' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-tint)'}
                onMouseLeave={e => e.currentTarget.style.background = 'white'}>
                + Создать «{search}»
              </div>
            )}
          </div>
          {creating && (
            <div style={{ padding: '8px', borderTop: '1px solid var(--border-card)', display: 'flex', gap: '6px' }}>
              <input value={newName} onChange={e => setNewName(e.target.value)}
                style={{ flex: 1, padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--accent)', fontSize: '14px', outline: 'none' }} />
              <button onClick={handleCreate} style={{ padding: '5px 10px', borderRadius: '6px', border: 'none', background: 'var(--accent)', color: 'white', fontSize: '14px', cursor: 'pointer' }}>Создать</button>
              <button onClick={() => setCreating(false)} style={{ padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'white', fontSize: '14px', cursor: 'pointer' }}>✕</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Operations() {
  const router = useRouter()
  const [operations, setOperations] = useState([])
  const [articles, setArticles] = useState([])
  const [counterparties, setCounterparties] = useState([])
  const [periods, setPeriods] = useState([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const [pageSize, setPageSize] = useState(300)

  const [filterStatuses, setFilterStatuses] = useState([])
  const [filterBanks, setFilterBanks] = useState([])
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [filterArticles, setFilterArticles] = useState([])
  const [filterCounterparties, setFilterCounterparties] = useState([])
  const [filterPeriods, setFilterPeriods] = useState([])
  // Фильтр по типу контрагента — только для админа. Значения: 'все' | 'действующий' | 'виртуальный'
  // (точно совпадают с Counterparty.status в БД, чтобы c.status === filterCpStatus работало напрямую).
  const [filterCpStatus, setFilterCpStatus] = useState('все')
  const [isAdmin, setIsAdmin] = useState(false)

  const [form, setForm] = useState(emptyForm)
  const [periodMode, setPeriodMode] = useState('month')
  const [copyOf, setCopyOf] = useState(null)
  const [permissions, setPermissions] = useState({})

  const [selectedIds, setSelectedIds] = useState([])
  const [bulkStatus, setBulkStatus] = useState('')
  const [bulkDate, setBulkDate] = useState('')
  const [bulkBank, setBulkBank] = useState('')
  const [bulkArticle, setBulkArticle] = useState('')
  const [bulkCounterparty, setBulkCounterparty] = useState('')
  const [bulkPeriod, setBulkPeriod] = useState('')
  const [bulkPeriodMode, setBulkPeriodMode] = useState('month')
  const [bulkVatRate, setBulkVatRate] = useState('')

  useEffect(() => {
    const col = localStorage.getItem('ops_sort_col')
    const dir = localStorage.getItem('ops_sort_dir')
    const size = localStorage.getItem('ops_page_size')
    if (col) setSortCol(col)
    if (dir) setSortDir(dir)
    if (size) setPageSize(parseInt(size))
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    const perms = getPermissions()
    if (!can(perms, 'operations', 'view')) { router.push('/dashboard'); return }
    setPermissions(perms)
    setIsAdmin(localStorage.getItem('is_admin') === '1')
    loadRefs(token)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) loadOps(token)
  }, [page, sortCol, sortDir, pageSize, filterStatuses, filterBanks, filterDateFrom, filterDateTo, filterArticles, filterCounterparties, filterPeriods, filterCpStatus])

  // Выделение строк для массового редактирования привязано к текущей странице —
  // при смене страницы/фильтра/сортировки оно сбрасывается, чтобы не оставалось
  // "невидимых" выбранных операций, которых уже нет в текущей выдаче.
  useEffect(() => {
    setSelectedIds([])
  }, [page, sortCol, sortDir, pageSize, filterStatuses, filterBanks, filterDateFrom, filterDateTo, filterArticles, filterCounterparties, filterPeriods, filterCpStatus])

  const loadRefs = async (token) => {
    try {
      const a = api(token)
      const [artRes, contRes] = await Promise.all([a.get('/articles/'), a.get('/counterparties/?limit=1000')])
      setArticles(Array.isArray(artRes.data) ? artRes.data : [])
      setCounterparties(contRes.data?.items || [])
    } catch (e) {}
    try {
      const a = api(token)
      const perRes = await a.get('/reports/periods')
      setPeriods(Array.isArray(perRes.data) ? perRes.data : [])
    } catch (e) {}
  }

  const loadOps = async (token) => {
    setLoading(true)
    try {
      const a = api(token)
      const params = new URLSearchParams({ skip: page * pageSize, limit: pageSize, sort_col: sortCol, sort_dir: sortDir })
      filterStatuses.forEach(s => params.append('status', s))
      filterBanks.forEach(b => params.append('bank', b))
      if (filterDateFrom) params.append('date_from', filterDateFrom)
      if (filterDateTo) params.append('date_to', filterDateTo)
      filterArticles.forEach(id => params.append("article_id", id))
      // Фильтр по типу контрагента (только для админа). Если тип выбран — берём
      // ID контрагентов этого типа и пересекаем с ручным выбором (если он есть).
      let cpIdsToFilter = filterCounterparties
      if (filterCpStatus !== 'все') {
        const statusIds = counterparties.filter(c => c.status === filterCpStatus).map(c => c.id)
        if (filterCounterparties.length > 0) {
          const statusSet = new Set(statusIds)
          cpIdsToFilter = filterCounterparties.filter(id => statusSet.has(id))
        } else {
          cpIdsToFilter = statusIds
        }
        if (cpIdsToFilter.length === 0) cpIdsToFilter = [-1] // гарантированно пустой результат
      }
      cpIdsToFilter.forEach(id => params.append("counterparty_id", id))
      filterPeriods.forEach(p => params.append("period", p))
      const res = await a.get(`/operations/?${params}`)
      setOperations(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const handleSort = (col) => {
    const dir = sortCol === col ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortCol(col); setSortDir(dir)
    localStorage.setItem('ops_sort_col', col); localStorage.setItem('ops_sort_dir', dir)
    setPage(0)
  }

  const handlePageSize = (s) => { setPageSize(s); localStorage.setItem('ops_page_size', s); setPage(0) }

  const tog = (arr, set, val) => { set(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val]); setPage(0) }

  const resetFilters = () => {
    setFilterStatuses([]); setFilterBanks([]); setFilterDateFrom(''); setFilterDateTo('')
    setFilterArticles([]); setFilterCounterparties([]); setFilterPeriods([]); setFilterCpStatus('все'); setPage(0)
  }

  const openNew = () => { setEditingId(null); setCopyOf(null); setForm(emptyForm); setPeriodMode('month'); setShowForm(true) }

  const downloadTemplate = async () => {
    const token = localStorage.getItem('token')
    try {
      const res = await api(token).get('/operations/import/template', { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = 'shablon_operaciy.xlsx'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      alert('Не удалось скачать шаблон')
    }
  }

  const downloadExport = async () => {
    const token = localStorage.getItem('token')
    try {
      const params = new URLSearchParams({ sort_col: sortCol, sort_dir: sortDir })
      filterStatuses.forEach(s => params.append('status', s))
      filterBanks.forEach(b => params.append('bank', b))
      if (filterDateFrom) params.append('date_from', filterDateFrom)
      if (filterDateTo) params.append('date_to', filterDateTo)
      filterArticles.forEach(id => params.append('article_id', id))
      let cpIdsExp = filterCounterparties
      if (filterCpStatus !== 'все') {
        const statusIds = counterparties.filter(c => c.status === filterCpStatus).map(c => c.id)
        if (filterCounterparties.length > 0) {
          const statusSet = new Set(statusIds)
          cpIdsExp = filterCounterparties.filter(id => statusSet.has(id))
        } else {
          cpIdsExp = statusIds
        }
        if (cpIdsExp.length === 0) cpIdsExp = [-1]
      }
      cpIdsExp.forEach(id => params.append('counterparty_id', id))
      filterPeriods.forEach(p => params.append('period', p))
      const res = await api(token).get(`/operations/export?${params}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `operacii_${new Date().toISOString().slice(0,16).replace('T','_').replace(':','')}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      alert('Не удалось скачать файл')
    }
  }

  const openEdit = (op) => {
    setEditingId(op.id)
    setCopyOf(null)
    setForm({ date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || 0, expense: op.expense || 0, bank: op.bank || 'АльфаБанк', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    setPeriodMode(isQuarterPeriod(op.period) ? 'quarter' : 'month')
    setShowForm(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Копия операции: та же форма, что и для редактирования, но editingId не
  // выставляется — поэтому handleSubmit уйдёт через POST (создание новой
  // записи), а не PUT (перезапись операции-источника).
  const openCopy = (op) => {
    setEditingId(null)
    setCopyOf(op.id)
    setForm({ date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || 0, expense: op.expense || 0, bank: op.bank || 'АльфаБанк', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    setPeriodMode(isQuarterPeriod(op.period) ? 'quarter' : 'month')
    setShowForm(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSubmit = async () => {
    const token = localStorage.getItem('token')
    try {
      const payload = { ...form, income: parseFloat(form.income) || 0, expense: parseFloat(form.expense) || 0, vat_rate: parseFloat(form.vat_rate) || 0, article_id: form.article_id ? parseInt(form.article_id) : null, counterparty_id: form.counterparty_id ? parseInt(form.counterparty_id) : null, invoice_date: form.invoice_date || null, date: form.date || null, bank: isPlan(form.status) && !form.bank ? null : form.bank }
      if (editingId) { await api(token).put(`/operations/${editingId}`, payload) } else { await api(token).post('/operations/', payload) }
      setShowForm(false); setEditingId(null); setCopyOf(null); setForm(emptyForm); loadOps(token)
    } catch (e) { alert('Ошибка при сохранении') }
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить операцию?')) return
    const token = localStorage.getItem('token')
    await api(token).delete(`/operations/${id}`)
    loadOps(token)
  }

  const toggleSelect = (id) => setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  const allVisibleSelected = operations.length > 0 && operations.every(op => selectedIds.includes(op.id))
  const toggleSelectAllVisible = () => setSelectedIds(allVisibleSelected ? [] : operations.map(op => op.id))
  // Суммы по выбранным строкам (только видимые на текущей странице — selectedIds могут включать
  // id с других страниц, но сумму считаем по факту найденных в operations, как и selectedIds.length по смыслу выбора)
  const selectedIncome = operations.filter(op => selectedIds.includes(op.id)).reduce((s, op) => s + (op.income || 0), 0)
  const selectedExpense = operations.filter(op => selectedIds.includes(op.id)).reduce((s, op) => s + (op.expense || 0), 0)

  const resetBulkFields = () => {
    setSelectedIds([]); setBulkStatus(''); setBulkDate(''); setBulkBank(''); setBulkArticle(''); setBulkCounterparty('')
    setBulkPeriod(''); setBulkPeriodMode('month'); setBulkVatRate('')
  }

  const handleBulkApply = async () => {
    const fields = {}
    if (bulkStatus) fields.status = bulkStatus
    if (bulkDate) fields.date = bulkDate
    if (bulkBank) fields.bank = bulkBank
    if (bulkArticle) fields.article_id = Number(bulkArticle)
    if (bulkCounterparty) fields.counterparty_id = Number(bulkCounterparty)
    if (bulkPeriod) fields.period = bulkPeriod
    if (bulkVatRate !== '') fields.vat_rate = Number(bulkVatRate)
    if (Object.keys(fields).length === 0) { alert('Выберите хотя бы одно поле для изменения'); return }
    const labels = { status: 'Статус', date: 'Дата', bank: 'Банк', article_id: 'Статья', counterparty_id: 'Контрагент', period: 'Период', vat_rate: 'НДС %' }
    const valueLabels = { article_id: (v) => articles.find(a => a.id === v)?.name || v, counterparty_id: (v) => counterparties.find(c => c.id === v)?.name || v }
    const summary = Object.entries(fields).map(([k, v]) => `${labels[k]} → ${valueLabels[k] ? valueLabels[k](v) : v}`).join(', ')
    if (!confirm(`Изменить ${selectedIds.length} операций?\n${summary}`)) return
    const token = localStorage.getItem('token')
    try {
      await api(token).patch('/operations/bulk', { ids: selectedIds, ...fields })
      resetBulkFields()
      loadOps(token)
    } catch (e) {
      const status = e.response?.status
      const detail = e.response?.data?.detail
      alert(`Ошибка при массовом изменении${status ? ` (${status})` : ''}${detail ? `: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}` : ''}`)
    }
  }

  const handleBulkDelete = async () => {
    if (!confirm(`Удалить ${selectedIds.length} операций? Это действие нельзя отменить.`)) return
    const token = localStorage.getItem('token')
    try {
      await api(token).delete('/operations/bulk', { data: { ids: selectedIds } })
      resetBulkFields()
      loadOps(token)
    } catch (e) {
      const status = e.response?.status
      const detail = e.response?.data?.detail
      alert(`Ошибка при массовом удалении${status ? ` (${status})` : ''}${detail ? `: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}` : ''}`)
    }
  }


  const createCounterparty = async (name) => {
    const token = localStorage.getItem('token')
    try {
      const res = await api(token).post('/counterparties/', { name, vat_rate: 0 })
      const newC = { id: res.data.id, name }
      setCounterparties(prev => [...prev, newC].sort((a, b) => a.name.localeCompare(b.name)))
      return newC
    } catch (e) {
      alert('Ошибка при создании контрагента')
      return null
    }
  }

  const totalPages = Math.ceil(total / pageSize)
  const inp = { width: '100%', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '15px', outline: 'none' }
  const lbl = { fontSize: '13px', color: 'var(--text-muted)', display: 'block', marginBottom: '3px' }
  const thS = { textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: '500', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid var(--border-card)', background: 'var(--bg-subtle)', position: 'sticky', top: 0, zIndex: 10 }
  const SortIcon = ({ col }) => sortCol !== col ? <span style={{ color: 'var(--text-faint)', marginLeft: '4px' }}>↕</span> : <span style={{ color: 'var(--accent)', marginLeft: '4px' }}>{sortDir === 'asc' ? '↑' : '↓'}</span>
  const planMode = isPlan(form.status)
  const quarterMatch = (form.period || '').match(/^Q([1-4]) (\d{4})$/)
  const quarterNum = quarterMatch ? quarterMatch[1] : '1'
  const quarterYear = quarterMatch ? quarterMatch[2] : String(new Date().getFullYear())

  const bulkQuarterMatch = (bulkPeriod || '').match(/^Q([1-4]) (\d{4})$/)
  const bulkQuarterNum = bulkQuarterMatch ? bulkQuarterMatch[1] : '1'
  const bulkQuarterYear = bulkQuarterMatch ? bulkQuarterMatch[2] : String(new Date().getFullYear())

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar active="operations">
        <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>Строк:</span>
        {PAGE_SIZE_OPTIONS.map(s => <button key={s} onClick={() => handlePageSize(s)} style={{ fontSize: '14px', padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', cursor: 'pointer', background: pageSize === s ? 'var(--accent)' : 'white', color: pageSize === s ? 'white' : 'var(--text-secondary)' }}>{s}</button>)}
        {can(permissions, 'operations', 'create') && <button onClick={openNew} style={{ fontSize: '15px', padding: '6px 14px', borderRadius: '8px', border: 'none', background: 'var(--accent)', color: 'white', cursor: 'pointer', marginLeft: '8px' }}>+ Новая операция</button>}
        {can(permissions, 'operations', 'create') && <button onClick={downloadTemplate} style={{ fontSize: '15px', padding: '6px 14px', borderRadius: '8px', border: '1px solid var(--accent)', background: 'white', color: 'var(--accent)', cursor: 'pointer' }}>Шаблон</button>}
        {can(permissions, 'import') && <button onClick={() => router.push('/import')} title="Импорт" style={{ fontSize: '17px', padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'white', color: 'var(--text-secondary)', cursor: 'pointer', lineHeight: 1 }}>
          <span style={{ display: 'inline-block', transform: 'rotate(180deg)' }}>⬇️</span>
        </button>}
        <button onClick={downloadExport} title="Скачать (с учётом текущих фильтров и сортировки)" style={{ fontSize: '17px', padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'white', color: 'var(--text-secondary)', cursor: 'pointer', lineHeight: 1 }}>⬇️</button>
      </Navbar>

      <div style={{ padding: '16px 24px' }}>

        {showForm && (
          <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '16px', border: `2px solid ${editingId ? 'var(--dot-current-dz)' : 'var(--accent)'}` }}>
            <div style={{ fontWeight: '500', marginBottom: '14px', display: 'flex', justifyContent: 'space-between' }}>
              <span>{editingId ? '✏️ Редактирование #' + editingId : (copyOf ? `📋 Копия операции #${copyOf}` : '+ Новая операция')}</span>
              <button onClick={() => { setShowForm(false); setEditingId(null); setCopyOf(null); setForm(emptyForm); setPeriodMode('month') }} style={{ fontSize: '20px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>✕</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '10px', marginBottom: '14px' }}>
              <div><label style={lbl}>Статус</label>
                <select style={inp} value={form.status} onChange={e => setForm({ ...form, status: e.target.value, date: isPlan(e.target.value) ? '' : (form.date || new Date().toISOString().split('T')[0]), bank: isPlan(e.target.value) ? '' : form.bank })}>
                  <option value="ОПЛАЧЕНО">Оплачено</option>
                  <option value="ПЛАН ОПЛАТ">План оплат</option>
                  <option value="ПЛАН ПОСТУПЛЕНИЙ">План поступлений</option>
                </select>
              </div>
              <div><label style={lbl}>Дата {planMode && <span style={{ color: 'var(--dot-current-dz)' }}>(необяз.)</span>}</label>
                <input type="date" style={{ ...inp, borderColor: planMode ? 'var(--dot-current-dz)' : 'var(--border-card)' }} value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
              </div>
              <div><label style={lbl}>Поступление</label><input type="number" style={inp} value={form.income} onChange={e => setForm({ ...form, income: e.target.value })} /></div>
              <div><label style={lbl}>Списание</label><input type="number" style={inp} value={form.expense} onChange={e => setForm({ ...form, expense: e.target.value })} /></div>
              <div><label style={lbl}>Банк {planMode && <span style={{ color: 'var(--dot-current-dz)' }}>(необяз.)</span>}</label>
                <select style={{ ...inp, borderColor: planMode ? 'var(--dot-current-dz)' : 'var(--border-card)' }} value={form.bank} onChange={e => setForm({ ...form, bank: e.target.value })}>
                  {planMode && <option value="">— не указан —</option>}
                  {BANKS.map(b => <option key={b}>{b}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>Период</label>
                <div style={{ display: 'flex', gap: '3px', marginBottom: '4px' }}>
                  <button type="button" onClick={() => { setPeriodMode('month'); setForm({ ...form, period: '' }) }}
                    style={{ flex: 1, padding: '3px 6px', fontSize: '13px', borderRadius: '6px', border: '1px solid var(--border-card)', cursor: 'pointer', background: periodMode === 'month' ? 'var(--accent)' : 'white', color: periodMode === 'month' ? 'white' : 'var(--text-secondary)' }}>
                    Месяц
                  </button>
                  <button type="button" onClick={() => { setPeriodMode('quarter'); setForm({ ...form, period: `Q1 ${new Date().getFullYear()}` }) }}
                    style={{ flex: 1, padding: '3px 6px', fontSize: '13px', borderRadius: '6px', border: '1px solid var(--border-card)', cursor: 'pointer', background: periodMode === 'quarter' ? 'var(--accent)' : 'white', color: periodMode === 'quarter' ? 'white' : 'var(--text-secondary)' }}>
                    Квартал
                  </button>
                </div>
                {periodMode === 'month' ? (
                  <input type="month" style={inp} value={form.period} onChange={e => setForm({ ...form, period: e.target.value })} />
                ) : (
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <select style={inp} value={quarterNum} onChange={e => setForm({ ...form, period: `Q${e.target.value} ${quarterYear}` })}>
                      <option value="1">Q1</option>
                      <option value="2">Q2</option>
                      <option value="3">Q3</option>
                      <option value="4">Q4</option>
                    </select>
                    <input type="number" style={inp} placeholder="Год" value={quarterYear} onChange={e => setForm({ ...form, period: `Q${quarterNum} ${e.target.value}` })} />
                  </div>
                )}
              </div>
              <div><label style={lbl}>НДС %</label>
                <select style={inp} value={form.vat_rate} onChange={e => setForm({ ...form, vat_rate: e.target.value })}>
                  {VAT_OPTIONS.map(v => <option key={v} value={v}>{v}%</option>)}
                </select>
              </div>
              <div><label style={lbl}>Статья</label>
                <select style={inp} value={form.article_id} onChange={e => setForm({ ...form, article_id: e.target.value })}>
                  <option value="">— выберите —</option>
                  {articles.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <div><label style={lbl}>Контрагент</label>
                <CounterpartySearch
                  counterparties={counterparties}
                  value={form.counterparty_id}
                  onChange={v => setForm({ ...form, counterparty_id: v })}
                  onCreateNew={createCounterparty}
                />
              </div>
              <div><label style={lbl}>№ ДС</label><input type="text" style={inp} value={form.ds_num} onChange={e => setForm({ ...form, ds_num: e.target.value })} /></div>
              <div><label style={lbl}>№ Счёта</label><input type="text" style={inp} value={form.invoice} onChange={e => setForm({ ...form, invoice: e.target.value })} /></div>
              <div><label style={lbl}>Дата счёта</label><input type="date" style={inp} value={form.invoice_date} onChange={e => setForm({ ...form, invoice_date: e.target.value })} /></div>
              <div><label style={lbl}>Ссылка на документ</label><input type="url" style={inp} placeholder="https://..." value={form.document_link} onChange={e => setForm({ ...form, document_link: e.target.value })} /></div>
              <div style={{ gridColumn: 'span 2' }}><label style={lbl}>Описание</label><input type="text" style={inp} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={handleSubmit} style={{ padding: '8px 20px', borderRadius: '8px', border: 'none', background: editingId ? 'var(--dot-current-dz)' : 'var(--accent)', color: 'white', cursor: 'pointer', fontSize: '15px' }}>{editingId ? 'Сохранить изменения' : 'Добавить операцию'}</button>
              <button onClick={() => { setShowForm(false); setEditingId(null); setCopyOf(null); setForm(emptyForm); setPeriodMode('month') }} style={{ padding: '8px 20px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '15px' }}>Отмена</button>
            </div>
          </div>
        )}

        <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <MultiDropdown label="Статус" items={STATUSES} selected={filterStatuses} onToggle={v => tog(filterStatuses, setFilterStatuses, v)} onClear={() => { setFilterStatuses([]); setPage(0) }} placeholder="Все статусы" getLabel={o => o} getId={o => o} />
          <MultiDropdown label="Банк" items={BANKS} selected={filterBanks} onToggle={v => tog(filterBanks, setFilterBanks, v)} onClear={() => { setFilterBanks([]); setPage(0) }} placeholder="Все банки" getLabel={o => o} getId={o => o} />
          <MultiDropdown label="Статья" items={articles} selected={filterArticles} onToggle={v => tog(filterArticles, setFilterArticles, v)} onClear={() => { setFilterArticles([]); setPage(0) }} placeholder="Все статьи" getLabel={o => o.name} getId={o => o.id} />
          <MultiDropdown
            label="Контрагент"
            items={filterCpStatus === 'все' ? counterparties : counterparties.filter(c => c.status === filterCpStatus)}
            selected={filterCounterparties}
            onToggle={v => tog(filterCounterparties, setFilterCounterparties, v)}
            onClear={() => { setFilterCounterparties([]); setPage(0) }}
            placeholder="Все контрагенты"
            getLabel={o => o.name}
            getId={o => o.id}
          />
          <MultiDropdown label="Период" items={periods} selected={filterPeriods} onToggle={v => tog(filterPeriods, setFilterPeriods, v)} onClear={() => { setFilterPeriods([]); setPage(0) }} placeholder="Все периоды" getLabel={o => o} getId={o => o} />
          <div><div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '3px' }}>Дата с</div><input type="date" style={{ padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '15px' }} value={filterDateFrom} onChange={e => { setFilterDateFrom(e.target.value); setPage(0) }} /></div>
          <div><div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '3px' }}>Дата по</div><input type="date" style={{ padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-card)', fontSize: '15px' }} value={filterDateTo} onChange={e => { setFilterDateTo(e.target.value); setPage(0) }} /></div>
          {isAdmin && (
            <div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '3px' }}>Тип контрагента</div>
              <select value={filterCpStatus} onChange={e => { setFilterCpStatus(e.target.value); setFilterCounterparties([]); setPage(0) }}
                style={{ padding: '7px 10px', borderRadius: '8px', border: `1px solid ${filterCpStatus !== 'все' ? 'var(--accent)' : 'var(--border-card)'}`, fontSize: '15px', background: 'white', cursor: 'pointer', color: filterCpStatus !== 'все' ? 'var(--accent)' : 'inherit', outline: 'none' }}>
                <option value="все">Все</option>
                <option value="действующий">Действующие</option>
                <option value="виртуальный">Виртуальные</option>
              </select>
            </div>
          )}
          <button onClick={resetFilters} style={{ padding: '7px 14px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'var(--text-muted)' }}>Сбросить всё</button>
        </div>

        {(can(permissions, 'operations', 'edit') || can(permissions, 'operations', 'delete')) && selectedIds.length > 0 && (
          <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', border: '2px solid var(--accent)', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginRight: '4px', alignSelf: 'center' }}>
              <div style={{ fontSize: '15px', fontWeight: '500', color: 'var(--accent)' }}>Выбрано: {selectedIds.length}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', whiteSpace: 'nowrap', color: 'var(--income)', fontWeight: 600 }}>
                <span>↑</span><span>+{new Intl.NumberFormat('ru-RU').format(Math.round(selectedIncome))} ₽</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', whiteSpace: 'nowrap', color: 'var(--expense)', fontWeight: 600 }}>
                <span>↓</span><span>−{new Intl.NumberFormat('ru-RU').format(Math.round(selectedExpense))} ₽</span>
              </div>
            </div>
            {can(permissions, 'operations', 'edit') && (<>
            <div><label style={lbl}>Статус</label>
              <select style={inp} value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}>
                <option value="">— не менять —</option>
                <option value="ОПЛАЧЕНО">Оплачено</option>
                <option value="ПЛАН ОПЛАТ">План оплат</option>
                <option value="ПЛАН ПОСТУПЛЕНИЙ">План поступлений</option>
              </select>
            </div>
            <div><label style={lbl}>Дата</label>
              <input type="date" style={inp} value={bulkDate} onChange={e => setBulkDate(e.target.value)} />
            </div>
            <div>
              <label style={lbl}>Период</label>
              <div style={{ display: 'flex', gap: '3px', marginBottom: '4px' }}>
                <button type="button" onClick={() => { setBulkPeriodMode('month'); setBulkPeriod('') }} style={{ fontSize: '13px', padding: '3px 8px', borderRadius: '6px', border: '1px solid ' + (bulkPeriodMode === 'month' ? 'var(--accent)' : 'var(--border-card)'), background: bulkPeriodMode === 'month' ? 'var(--accent-tint)' : 'white', color: bulkPeriodMode === 'month' ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer' }}>Месяц</button>
                <button type="button" onClick={() => { setBulkPeriodMode('quarter'); setBulkPeriod(`Q1 ${new Date().getFullYear()}`) }} style={{ fontSize: '13px', padding: '3px 8px', borderRadius: '6px', border: '1px solid ' + (bulkPeriodMode === 'quarter' ? 'var(--accent)' : 'var(--border-card)'), background: bulkPeriodMode === 'quarter' ? 'var(--accent-tint)' : 'white', color: bulkPeriodMode === 'quarter' ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer' }}>Квартал</button>
              </div>
              {bulkPeriodMode === 'month' ? (
                <input type="month" style={inp} value={bulkPeriod} onChange={e => setBulkPeriod(e.target.value)} />
              ) : (
                <div style={{ display: 'flex', gap: '6px' }}>
                  <select style={inp} value={bulkQuarterNum} onChange={e => setBulkPeriod(`Q${e.target.value} ${bulkQuarterYear}`)}>
                    <option value="1">Q1</option><option value="2">Q2</option><option value="3">Q3</option><option value="4">Q4</option>
                  </select>
                  <input type="number" style={inp} placeholder="Год" value={bulkQuarterYear} onChange={e => setBulkPeriod(`Q${bulkQuarterNum} ${e.target.value}`)} />
                </div>
              )}
            </div>
            <div><label style={lbl}>Банк</label>
              <select style={inp} value={bulkBank} onChange={e => setBulkBank(e.target.value)}>
                <option value="">— не менять —</option>
                {BANKS.map(b => <option key={b}>{b}</option>)}
              </select>
            </div>
            <div><label style={lbl}>НДС %</label>
              <select style={inp} value={bulkVatRate} onChange={e => setBulkVatRate(e.target.value)}>
                <option value="">— не менять —</option>
                {VAT_OPTIONS.map(v => <option key={v} value={v}>{v}%</option>)}
              </select>
            </div>
            <div><label style={lbl}>Статья</label>
              <select style={inp} value={bulkArticle} onChange={e => setBulkArticle(e.target.value)}>
                <option value="">— не менять —</option>
                {articles.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
            <div style={{ minWidth: '180px' }}><label style={lbl}>Контрагент</label>
              <CounterpartySearch
                counterparties={counterparties}
                value={bulkCounterparty}
                onChange={v => setBulkCounterparty(v)}
                onCreateNew={createCounterparty}
              />
            </div>
            <button onClick={handleBulkApply} style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: 'var(--accent)', color: 'white', cursor: 'pointer', fontSize: '15px' }}>Применить к {selectedIds.length}</button>
            </>)}
            {can(permissions, 'operations', 'delete') && (
              <button onClick={handleBulkDelete} style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: 'var(--dot-overdue)', color: 'white', cursor: 'pointer', fontSize: '15px' }}>Удалить {selectedIds.length}</button>
            )}
            <button onClick={resetBulkFields} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: 'var(--text-muted)' }}>Снять выделение</button>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ fontSize: '15px', color: 'var(--text-muted)' }}>Показано {Math.min(page * pageSize + 1, total)}–{Math.min((page + 1) * pageSize, total)} из {total} операций</div>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button onClick={() => setPage(0)} disabled={page === 0} style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'white', cursor: page === 0 ? 'default' : 'pointer', fontSize: '14px', opacity: page === 0 ? 0.4 : 1 }}>«</button>
            <button onClick={() => setPage(p => p - 1)} disabled={page === 0} style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'white', cursor: page === 0 ? 'default' : 'pointer', fontSize: '14px', opacity: page === 0 ? 0.4 : 1 }}>‹</button>
            <span style={{ padding: '4px 12px', fontSize: '14px', color: 'var(--text-muted)' }}>{page + 1} / {totalPages || 1}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1} style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'white', cursor: page >= totalPages - 1 ? 'default' : 'pointer', fontSize: '14px', opacity: page >= totalPages - 1 ? 0.4 : 1 }}>›</button>
            <button onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1} style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'white', cursor: page >= totalPages - 1 ? 'default' : 'pointer', fontSize: '14px', opacity: page >= totalPages - 1 ? 0.4 : 1 }}>»</button>
          </div>
        </div>

        {loading ? <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>Загрузка...</div> : (
          <div style={{ background: 'white', borderRadius: '12px', border: '1px solid var(--border-card)', overflow: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr>
                  {can(permissions, 'operations', 'edit') && (
                    <th style={{ ...thS, width: '34px', cursor: 'default' }}>
                      <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} />
                    </th>
                  )}
                  <th style={thS} onClick={() => handleSort('date')}>Дата <SortIcon col="date" /></th>
                  <th style={thS} onClick={() => handleSort('status')}>Статус <SortIcon col="status" /></th>
                  <th style={{ ...thS, textAlign: 'center' }}>ДЗ</th>
                  <th style={thS}>Поступление</th>
                  <th style={thS}>Списание</th>
                  <th style={thS} onClick={() => handleSort('bank')}>Банк <SortIcon col="bank" /></th>
                  <th style={thS} onClick={() => handleSort('period')}>Период <SortIcon col="period" /></th>
                  <th style={thS} onClick={() => handleSort('article')}>Статья <SortIcon col="article" /></th>
                  <th style={thS} onClick={() => handleSort('counterparty')}>Контрагент <SortIcon col="counterparty" /></th>
                  <th style={thS}>НДС%</th>
                  <th style={thS}>НДС сумма</th>
                  <th style={thS}>№ ДС</th>
                  <th style={thS}>№ Счёта</th>
                  <th style={thS}>Дата счёта</th>
                  <th style={thS}>Док</th>
                  <th style={thS}>Описание</th>
                  <th style={thS}>Действия</th>
                </tr>
              </thead>
              <tbody>
                {operations.map(op => {
                  const bankStyle = BANK_STYLES[op.bank] || { color: 'var(--text-faint)' }
                  return (
                    <tr key={op.id} style={{ borderBottom: '1px solid var(--border-row)', background: editingId === op.id ? 'var(--warning-tint)' : 'transparent' }}
                      onMouseEnter={e => { if (editingId !== op.id) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = editingId === op.id ? 'var(--warning-tint)' : 'transparent' }}>
                      {can(permissions, 'operations', 'edit') && (
                        <td style={{ padding: '7px 10px' }}>
                          <input type="checkbox" checked={selectedIds.includes(op.id)} onChange={() => toggleSelect(op.id)} />
                        </td>
                      )}
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{op.date || '—'}</td>
                      <td style={{ padding: '7px 10px' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '11px', padding: '3px 9px', borderRadius: 'var(--radius-badge)', whiteSpace: 'nowrap', background: 'var(--bg-subtle)', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_DOT[op.status] || 'var(--text-faint)', flexShrink: 0 }} />
                          {op.status}
                        </span>
                      </td>
                      <td style={{ padding: '7px 10px', textAlign: 'center' }}>
                        {op.receivable_status && RECEIVABLE_META[op.receivable_status]
                          ? <span title={RECEIVABLE_META[op.receivable_status].label} style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', background: RECEIVABLE_META[op.receivable_status].color }} />
                          : '—'}
                      </td>
                      <td style={{ padding: '7px 10px', color: 'var(--income)', fontWeight: op.income > 0 ? '500' : '400', whiteSpace: 'nowrap' }}>{op.income > 0 ? fmt(op.income) : '—'}</td>
                      <td style={{ padding: '7px 10px', color: 'var(--expense)', fontWeight: op.expense > 0 ? '500' : '400', whiteSpace: 'nowrap' }}>{op.expense > 0 ? fmt(op.expense) : '—'}</td>
                      <td style={{ padding: '7px 10px' }}>
                        {op.bank
                          ? <span style={{ fontSize: '11px', padding: '3px 9px', borderRadius: 'var(--radius-badge)', whiteSpace: 'nowrap', background: 'var(--bg-subtle)', color: bankStyle.color, border: `1px solid ${bankStyle.color}`, fontWeight: 600 }}>{op.bank}</span>
                          : '—'}
                      </td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{op.period || '—'}</td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{op.article || '—'}</td>
                      <td style={{ padding: '7px 10px', maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={op.counterparty}>{op.counterparty || '—'}</td>
                      <td style={{ padding: '7px 10px' }}>{op.vat_rate > 0 ? op.vat_rate + '%' : '—'}</td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{op.vat_fact > 0 ? fmt(op.vat_fact) : '—'}</td>
                      <td style={{ padding: '7px 10px' }}>{op.ds_num || '—'}</td>
                      <td style={{ padding: '7px 10px' }}>{op.invoice || '—'}</td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{op.invoice_date || '—'}</td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                        {op.document_link
                          ? <a href={op.document_link} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} title="Открыть документ"
                              style={{ fontSize: '15px', padding: '2px 8px', borderRadius: '6px', border: '1px solid var(--accent)', background: 'var(--accent-tint)', color: 'var(--accent)', textDecoration: 'none', cursor: 'pointer', display: 'inline-block' }}>
                              📄
                            </a>
                          : '—'}
                      </td>
                      <td style={{ padding: '7px 10px', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={op.description}>{renderDescription(op.description)}</td>
                      <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                        {can(permissions, 'operations', 'create') && <button onClick={() => openCopy(op)} title="Скопировать" style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid var(--accent)', background: 'var(--accent-tint)', cursor: 'pointer', color: 'var(--accent)', marginRight: '4px' }}>📋</button>}
                        {can(permissions, 'operations', 'edit') && <button onClick={() => openEdit(op)} style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid var(--dot-current-dz)', background: 'var(--warning-tint)', cursor: 'pointer', color: 'var(--dot-current-dz)', marginRight: '4px' }}>✏️</button>}
                        {can(permissions, 'operations', 'delete') && <button onClick={() => handleDelete(op.id)} style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid var(--border-card)', background: 'transparent', cursor: 'pointer', color: 'var(--dot-overdue)' }}>✕</button>}
                        {!can(permissions, 'operations', 'create') && !can(permissions, 'operations', 'edit') && !can(permissions, 'operations', 'delete') && '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

      </div>
    </div>
  )
}
