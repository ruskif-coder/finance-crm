import { useState, useEffect, useRef, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import axios from 'axios'
import Navbar, { can } from '../components/Navbar'
import { MONO, UI, MultiDrop, IconBtn } from '../components/salesTableKit'
import useIsMobile from '../components/mobile/useIsMobile'
import OperationsMobile from '../components/mobile/OperationsMobile'

const api = (token) => axios.create({ baseURL: '/api', headers: { Authorization: `Bearer ${token}` }, paramsSerializer: { indexes: null } })
const getPerms = () => { if (typeof window === 'undefined') return {}; try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} } }

const STATUSES = ['ОПЛАЧЕНО', 'ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const BANK_COLOR = { 'АльфаБанк': 'var(--bank-alfa)', 'ОПТ Банк': 'var(--bank-opt)', 'Совкомбанк': 'var(--bank-sovkom)', 'Наличные': 'var(--bank-cash)' }
const VAT_OPTIONS = [0, 5, 7, 10, 20, 22]
const PAGE_SIZES = [50, 100, 300, 500]
// статус-чип: фон / текст / точка
const STATUS_CHIP = {
  'ОПЛАЧЕНО': ['#E6F5EF', '#1F7D5E', 'var(--income)'],
  'ПЛАН ОПЛАТ': ['#EEF1FE', '#3A50BE', 'var(--dot-expense)'],
  'ПЛАН ПОСТУПЛЕНИЙ': ['var(--warning-tint)', '#B26A0C', 'var(--dot-current-dz)'],
  'ОЖИДАЕТ': ['var(--warning-tint)', '#B26A0C', 'var(--dot-current-dz)'],
}
const statusChip = (s) => STATUS_CHIP[s] || ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--text-faint)']

const fmt = (n) => (n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '')
const fmtDate = (d) => { if (!d) return ''; const [y, m, dd] = String(d).slice(0, 10).split('-'); return dd ? `${dd}.${m}.${y.slice(2)}` : d }
const emptyForm = () => ({ date: new Date().toISOString().slice(0, 10), status: 'ОПЛАЧЕНО', income: 0, expense: 0, bank: 'АльфаБанк', period: '', vat_rate: 0, article_id: '', counterparty_id: '', ds_num: '', invoice: '', invoice_date: '', description: '', document_link: '' })
const isQuarter = (p) => /^Q[1-4]\s*\d{4}$/.test(p || '')

const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const lbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 5, display: 'block' }
const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 11px', fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', fontFamily: UI }

// сегмент-переключатель (Месяц|Квартал, ставка НДС и т.п.)
function Seg({ options, value, onChange, mono }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, height: 36, alignItems: 'stretch' }}>
      {options.map(o => {
        const on = String(o.value) === String(value)
        return <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
          style={{ flex: '0 0 auto', border: 'none', borderRadius: 7, padding: '0 12px', cursor: 'pointer', fontFamily: mono ? MONO : UI, fontSize: 12, fontWeight: on ? 700 : 600, background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-secondary)' }}>{o.label}</button>
      })}
    </div>
  )
}

// поле периода: сегмент Месяц|Квартал + значение
function PeriodField({ value, onChange }) {
  const q = isQuarter(value)
  const [mode, setMode] = useState(q ? 'quarter' : 'month')
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'stretch', height: 36 }}>
      <Seg options={[{ value: 'month', label: 'Месяц' }, { value: 'quarter', label: 'Квартал' }]} value={mode} onChange={m => { setMode(m); onChange('') }} />
      {mode === 'month'
        ? <input type="month" value={q ? '' : value} onChange={e => onChange(e.target.value)} style={{ ...inp, flex: 1, minWidth: 0 }} />
        : <input placeholder="Q3 2025" value={q ? value : ''} onChange={e => onChange(e.target.value)} style={{ ...inp, flex: 1, minWidth: 0, fontFamily: MONO }} />}
    </div>
  )
}

// Однослот с поиском в шапке (для длинных списков — Статья/Контрагент)
function SingleSelect({ value, onChange, options, placeholder, emptyLabel }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const selO = options.find(o => String(o.value) === String(value))
  const shown = options.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase())).slice(0, 300)
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ ...inp, cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: selO ? 'var(--text-primary)' : 'var(--text-faint)' }}>{selO ? selO.label : placeholder} ▾</div>
      {open && (
        <div style={{ position: 'absolute', top: '110%', left: 0, right: 0, minWidth: 210, zIndex: 50, marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', maxHeight: 300, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 8 }}><input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск" style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} /></div>
          <div style={{ overflowY: 'auto', padding: 5 }}>
            <div onClick={() => { onChange(''); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', color: 'var(--text-muted)' }}>{emptyLabel || '— не выбрано —'}</div>
            {shown.map(o => <div key={o.value} onClick={() => { onChange(o.value); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12.5, cursor: 'pointer', background: String(o.value) === String(value) ? 'var(--accent-tint)' : 'transparent', color: String(o.value) === String(value) ? 'var(--accent)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</div>)}
            {!shown.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// Единый набор полей формы (создание/редактирование)
function OpFields({ f, set, articles, counterparties, accent }) {
  const artOpts = articles.map(a => ({ value: a.id, label: a.name }))
  const cpOpts = counterparties.map(c => ({ value: c.id, label: c.name }))
  const Cell = ({ label, opt, children }) => (
    <div><span style={lbl}>{label}{opt ? <span style={{ color: accent === 'warn' ? '#B26A0C' : 'var(--text-faint)', marginLeft: 6 }}>необяз.</span> : ''}</span>{children}</div>
  )
  const sel = (val, onCh, opts, ph) => (
    <select value={val} onChange={e => onCh(e.target.value)} style={inp}><option value="">{ph}</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="Статус">{sel(f.status, v => set({ status: v }), STATUSES.map(s => ({ value: s, label: s })), 'статус')}</Cell>
        <Cell label="Дата" opt>{<input type="date" value={f.date} onChange={e => set({ date: e.target.value })} style={{ ...inp, ...(accent === 'warn' ? { borderColor: 'var(--dot-current-dz)' } : {}) }} />}</Cell>
        <Cell label="Поступление"><input inputMode="numeric" value={f.income || ''} onChange={e => set({ income: +e.target.value.replace(/\D/g, '') || 0 })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Списание"><input inputMode="numeric" value={f.expense || ''} onChange={e => set({ expense: +e.target.value.replace(/\D/g, '') || 0 })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Банк" opt>{sel(f.bank, v => set({ bank: v }), BANKS.map(b => ({ value: b, label: b })), 'не указан')}</Cell>
        <Cell label="Период"><PeriodField value={f.period} onChange={v => set({ period: v })} /></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="НДС"><Seg mono options={VAT_OPTIONS.map(v => ({ value: v, label: v + '%' }))} value={f.vat_rate} onChange={v => set({ vat_rate: v })} /></Cell>
        <Cell label="Статья"><SingleSelect value={f.article_id} onChange={v => set({ article_id: v })} options={artOpts} placeholder="не выбрана" emptyLabel="— не выбрано —" /></Cell>
        <Cell label="Контрагент"><SingleSelect value={f.counterparty_id} onChange={v => set({ counterparty_id: v })} options={cpOpts} placeholder="выберите или введите" emptyLabel="— не выбрано —" /></Cell>
        <Cell label="№ ДС"><input value={f.ds_num} onChange={e => set({ ds_num: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="№ счёта"><input value={f.invoice} onChange={e => set({ invoice: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Дата счёта"><input type="date" value={f.invoice_date} onChange={e => set({ invoice_date: e.target.value })} style={inp} /></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 14 }}>
        <Cell label="Ссылка на документ"><input value={f.document_link} onChange={e => set({ document_link: e.target.value })} placeholder="https://…" style={inp} /></Cell>
        <Cell label="Описание"><input value={f.description} onChange={e => set({ description: e.target.value })} placeholder="комментарий к операции" style={inp} /></Cell>
      </div>
    </div>
  )
}

// колонки таблицы (сетка из хендоффа)
const COLS = [
  ['sel', '26px', ''], ['date', '78px', 'Дата', 'date'], ['status', '112px', 'Статус', 'status'], ['dz', '36px', 'ДЗ'],
  ['income', '98px', 'Поступление', 'income'], ['expense', '98px', 'Списание', 'expense'], ['bank', '96px', 'Банк', 'bank'],
  ['period', '78px', 'Период', 'period'], ['article', '122px', 'Статья'], ['counterparty', '1.2fr', 'Контрагент'],
  ['vat', '46px', 'НДС'], ['vat_amount', '84px', 'НДС сумма'], ['ds_num', '62px', '№ ДС'], ['invoice', '112px', '№ счёта'],
  ['invoice_date', '88px', 'Дата счёта'], ['doc', '32px', 'Док'], ['description', '0.9fr', 'Описание'], ['actions', '72px', 'Действия'],
]
const GRID = COLS.map(c => c[1]).join(' ')
const RIGHT = new Set(['income', 'expense', 'vat', 'vat_amount'])

export default function Operations2() {
  const router = useRouter()
  const [perms, setPerms] = useState({})
  const canEdit = can(perms, 'operations', 'edit')
  const canImport = can(perms, 'import')
  const isMobile = useIsMobile()
  const [ops, setOps] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [articles, setArticles] = useState([])
  const [counterparties, setCounterparties] = useState([])
  const [updatedAt] = useState('09:12')

  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(300)
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')

  const [dateFrom, setDateFrom] = useState(''); const [dateTo, setDateTo] = useState('')
  const [fStatus, setFStatus] = useState([]); const [fBank, setFBank] = useState([]); const [fArticle, setFArticle] = useState([]); const [fCp, setFCp] = useState([]); const [fPeriod, setFPeriod] = useState([]); const [fOpType, setFOpType] = useState([])

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState(emptyForm())
  const [editing, setEditing] = useState(null)        // { id, ...form }
  const [sel, setSel] = useState({})                  // { id: true }
  const [bulk, setBulk] = useState({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' })
  const [saving, setSaving] = useState(false)
  const editAnchor = useRef(null)
  const [hidden, setHidden] = useState(new Set())   // скрытые колонки
  const [colPicker, setColPicker] = useState(false)
  const toggleCol = (k) => setHidden(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); localStorage.setItem('ops2_hidden', JSON.stringify([...n])); return n })
  const visibleCols = COLS.filter(([k]) => !hidden.has(k))
  const gridT = visibleCols.map(c => c[1]).join(' ')

  const tok = () => localStorage.getItem('token')

  useEffect(() => {
    if (!tok()) { router.push('/login'); return }
    try { setPerms(getPerms()) } catch (e) {}
    try { const h = JSON.parse(localStorage.getItem('ops2_hidden')); if (Array.isArray(h)) setHidden(new Set(h)) } catch (e) {}
    Promise.all([api(tok()).get('/articles/'), api(tok()).get('/counterparties/?limit=1000')])
      .then(([a, c]) => { setArticles(a.data?.items || a.data || []); setCounterparties(c.data?.items || c.data || []) }).catch(() => {})
  }, [])

  const loadOps = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ skip: page * pageSize, limit: pageSize, sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      const res = await api(tok()).get(`/operations/?${params}`)
      setOps(res.data?.items || []); setTotal(res.data?.total || 0)
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
    finally { setLoading(false) }
  }
  useEffect(() => { if (tok()) loadOps() }, [page, pageSize, sortCol, sortDir, fStatus, fBank, fArticle, fCp, fPeriod, dateFrom, dateTo])

  // op-type фильтр — клиентски по загруженной странице
  const rows = ops.filter(o => !fOpType.length || (fOpType.includes('income') && o.income > 0) || (fOpType.includes('expense') && o.expense > 0))

  const onSort = (k) => { if (!k) return; if (sortCol === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortCol(k); setSortDir('desc') }; setPage(0) }
  const resetFilters = () => { setDateFrom(''); setDateTo(''); setFStatus([]); setFBank([]); setFArticle([]); setFCp([]); setFPeriod([]); setFOpType([]); setPage(0) }

  const saveCreate = async () => {
    setSaving(true)
    try { await api(tok()).post('/operations/', createForm); setCreateForm(emptyForm()); setCreateOpen(false); loadOps() }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось создать') } finally { setSaving(false) }
  }
  const downloadTemplate = async () => {
    try {
      const res = await api(tok()).get('/operations/import/template', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url; a.download = 'shablon_operaciy.xlsx'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось скачать шаблон') }
  }
  const downloadExport = async () => {
    try {
      const params = new URLSearchParams({ sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      const res = await api(tok()).get(`/operations/export?${params}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      a.download = `operacii_${new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '')}.xlsx`
      a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось выгрузить') }
  }
  const openEdit = (op) => {
    setEditing({ id: op.id, date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || 0, expense: op.expense || 0, bank: op.bank || '', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    requestAnimationFrame(() => { const el = editAnchor.current; if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 24, behavior: 'smooth' }) })
  }
  const saveEdit = async () => {
    setSaving(true)
    try { const { id, ...body } = editing; await api(tok()).put(`/operations/${id}`, body); setEditing(null); loadOps() }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить') } finally { setSaving(false) }
  }
  // Копирование: не создаём дубль сразу, а открываем форму «Новая операция» с данными
  // копируемой — пользователь правит и подтверждает (POST на «Добавить операцию»).
  const dupOp = (op) => {
    setEditing(null)
    setCreateForm({ date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || 0, expense: op.expense || 0, bank: op.bank || 'АльфаБанк', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    setCreateOpen(true)
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }
  // мобильные CRUD-хендлеры (форма в OperationsMobile)
  const mobileSave = async (body, id) => {
    try { if (id) await api(tok()).put(`/operations/${id}`, body); else await api(tok()).post('/operations/', body); loadOps(); return true }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить'); return false }
  }
  const mobileDelete = async (id) => { try { await api(tok()).delete(`/operations/${id}`); loadOps() } catch (e) { alert('Не удалось удалить') } }
  const delOp = async (id) => { if (!window.confirm('Удалить операцию?')) return; try { await api(tok()).delete(`/operations/${id}`); loadOps() } catch (e) { alert('Не удалось удалить') } }

  const selIds = Object.keys(sel).filter(k => sel[k]).map(Number)
  const selRows = rows.filter(o => sel[o.id])
  const selIncome = selRows.reduce((s, o) => s + (o.income || 0), 0)
  const selExpense = selRows.reduce((s, o) => s + (o.expense || 0), 0)
  const applyBulk = async () => {
    const body = { ids: selIds }
    Object.entries(bulk).forEach(([k, v]) => { if (v !== '') body[k] = k === 'vat_rate' ? +v : v })
    if (Object.keys(body).length <= 1) { alert('Заполните хотя бы одно поле'); return }
    setSaving(true)
    try { await api(tok()).patch('/operations/bulk', body); setSel({}); setBulk({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' }); loadOps() }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось применить') } finally { setSaving(false) }
  }
  const delBulk = async () => { if (!window.confirm(`Удалить ${selIds.length} операций?`)) return; setSaving(true); try { await api(tok()).delete('/operations/bulk', { data: { ids: selIds } }); setSel({}); loadOps() } catch (e) { alert('Не удалось удалить') } finally { setSaving(false) } }

  const pageIncome = rows.reduce((s, o) => s + (o.income || 0), 0)
  const pageExpense = rows.reduce((s, o) => s + (o.expense || 0), 0)
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const cpName = Object.fromEntries(counterparties.map(c => [c.id, c.name]))
  const artName = Object.fromEntries(articles.map(a => [a.id, a.name]))
  const opt = (arr, get = x => x) => arr.map(get)

  const allOnPage = rows.length > 0 && rows.every(o => sel[o.id])
  const someOnPage = rows.some(o => sel[o.id])

  const chev = (d) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={d} /></svg>
  const IcoStroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round', strokeLinejoin: 'round' }

  const cell = (o, key) => {
    switch (key) {
      case 'sel': return <input type="checkbox" checked={!!sel[o.id]} onChange={() => setSel(s => ({ ...s, [o.id]: !s[o.id] }))} style={{ width: 14, height: 14, cursor: 'pointer' }} />
      case 'date': return <span style={{ fontFamily: MONO }}>{fmtDate(o.date) || '—'}</span>
      case 'status': { const [bg, fg, dot] = statusChip(o.status); return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: bg, color: fg, borderRadius: 8, padding: '3px 8px', fontFamily: MONO, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', whiteSpace: 'nowrap' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{o.status}</span> }
      case 'dz': { const rs = o.receivable_status; const meta = { overdue: ['Просрочка', 'var(--dot-overdue)'], current: ['Текущая', 'var(--dot-current-dz)'], future: ['План', 'var(--accent)'] }[rs]; return meta ? <span title={meta[0]} style={{ width: 10, height: 10, borderRadius: '50%', background: meta[1], display: 'inline-block' }} /> : <span style={{ color: '#C3C9D8' }}>—</span> }
      case 'income': return o.income ? <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--income)' }}>{fmt(o.income)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'expense': return o.expense ? <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(o.expense)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'bank': return o.bank ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}><span style={{ width: 8, height: 8, borderRadius: 2, background: BANK_COLOR[o.bank] || 'var(--text-faint)' }} />{o.bank}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'period': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.period || '—'}</span>
      case 'article': return <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{artName[o.article_id] || o.article || '—'}</span>
      case 'counterparty': return <span style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cpName[o.counterparty_id] || o.counterparty || '—'}</span>
      case 'vat': return <span style={{ fontFamily: MONO }}>{o.vat_rate ? o.vat_rate + '%' : <span style={{ color: '#C3C9D8' }}>—</span>}</span>
      case 'vat_amount': return o.vat_amount ? <span style={{ fontFamily: MONO }}>{fmt(o.vat_amount)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'ds_num': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.ds_num || '—'}</span>
      case 'invoice': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.invoice || '—'}</span>
      case 'invoice_date': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{fmtDate(o.invoice_date) || '—'}</span>
      case 'doc': return o.document_link ? <a href={o.document_link} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} title="Открыть документ" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, background: 'var(--accent-tint)', color: 'var(--accent)' }}><svg width="14" height="14" viewBox="0 0 24 24" style={IcoStroke}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg></a> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'description': return <span title={o.description} style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.description || '—'}</span>
      case 'actions': return canEdit ? <span style={{ display: 'inline-flex', gap: 4 }}>
        <span onClick={() => dupOp(o)} title="Дублировать" className="op-ico" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg></span>
        <span onClick={() => openEdit(o)} title="Редактировать" className="op-ico op-ico-w" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>
        <span onClick={() => delOp(o.id)} title="Удалить" className="op-ico op-ico-d" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M6 6l12 12M18 6L6 18" /></svg></span>
      </span> : null
      default: return null
    }
  }

  const HeadCard = ({ title, right, iconBg, iconFg, iconPath, onClose }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 24px', borderBottom: '1px solid var(--border-inner)' }}>
      <span style={{ width: 28, height: 28, borderRadius: 9, background: iconBg, color: iconFg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={IcoStroke}>{iconPath}</svg></span>
      <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{title}</span>
      {right}
      <span onClick={onClose} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1, padding: 4 }}>✕</span>
    </div>
  )

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Операции</title></Head>
        <Navbar active="operations" />
        <OperationsMobile
          total={total} rows={rows} loading={loading} articles={articles} counterparties={counterparties} canEdit={canEdit}
          dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
          fStatus={fStatus} setFStatus={setFStatus} fBank={fBank} setFBank={setFBank}
          fArticle={fArticle} setFArticle={setFArticle} fCp={fCp} setFCp={setFCp} fOpType={fOpType} setFOpType={setFOpType}
          resetFilters={resetFilters} pageSize={pageSize} setPageSize={setPageSize}
          onSave={mobileSave} onDelete={mobileDelete} downloadExport={downloadExport} emptyForm={emptyForm} />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head>
        <title>Операции</title>
      </Head>
      <Navbar active="operations" />
      <style>{`
        @keyframes opRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        .op-row:hover { background: var(--bg-subtle) !important; }
        .op-ico { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:7px; cursor:pointer; }
        .op-ico:hover { background: var(--accent-tint); color: var(--accent) !important; }
        .op-ico-w:hover { background: var(--warning-tint); color: #B26A0C !important; }
        .op-ico-d:hover { background: var(--danger-tint); color: #C93A3E !important; }
        @media (prefers-reduced-motion: reduce){ [style*="animation"]{ animation:none !important } }
      `}</style>

      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', margin: 0, color: 'var(--text-primary)' }}>Операции</h1>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{new Intl.NumberFormat('ru-RU').format(total)} записей · обновлено {updatedAt}</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {canEdit && <button onClick={() => setCreateOpen(o => !o)} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Новая операция</button>}
            {canEdit && <button onClick={downloadTemplate} style={{ background: 'var(--bg-card)', color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: 12, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Шаблон</button>}
            {canImport && <IconBtn title="Импорт из файла" onClick={() => router.push('/import')}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 15V3" /><path d="M7 8l5-5 5 5" /><path d="M5 21h14" /></svg></IconBtn>}
            <IconBtn title="Выгрузить в Excel (с учётом фильтров)" onClick={downloadExport}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg></IconBtn>
          </div>
        </div>

        {/* Форма создания */}
        {createOpen && canEdit && (
          <div style={{ ...CARD, border: '1px solid #D7DEFA', boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 28px rgba(79,108,230,.10)', animation: 'opRise .28s cubic-bezier(0.22,1,0.36,1) both' }}>
            <HeadCard title="Новая операция" iconBg="var(--accent-tint)" iconFg="var(--accent)" iconPath={<><path d="M12 5v14" /><path d="M5 12h14" /></>} onClose={() => setCreateOpen(false)} />
            <div style={{ padding: '20px 24px' }}><OpFields f={createForm} set={p => setCreateForm(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} /></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px', background: '#FBFCFE', borderTop: '1px solid var(--border-inner)' }}>
              <button onClick={saveCreate} disabled={saving} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Добавить операцию</button>
              <button onClick={() => setCreateOpen(false)} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '9px 16px', fontSize: 13, cursor: 'pointer' }}>Отмена</button>
              <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-faint)' }}>сумма НДС считается автоматически по ставке · обязательны статус, дата, банк, статья, сумма</span>
            </div>
          </div>
        )}

        {/* Карточка таблицы */}
        <div style={{ ...CARD, padding: '18px 24px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* строка фильтров */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--border-card)', borderRadius: 10, padding: '7px 10px', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
              <input type="month" value={dateFrom.slice(0, 7)} onChange={e => setDateFrom(e.target.value ? e.target.value + '-01' : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
              <span style={{ color: '#C3C9D8' }}>—</span>
              <input type="month" value={dateTo.slice(0, 7)} onChange={e => setDateTo(e.target.value ? e.target.value + '-28' : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
            </span>
            <MultiDrop label="Статус" options={STATUSES.map(s => ({ value: s, label: s }))} selected={fStatus} onChange={setFStatus} />
            <MultiDrop label="Банк" options={BANKS.map(b => ({ value: b, label: b }))} selected={fBank} onChange={setFBank} />
            <MultiDrop label="Статья" options={articles.map(a => ({ value: a.id, label: a.name }))} selected={fArticle} onChange={setFArticle} />
            <MultiDrop label="Контрагент" options={counterparties.map(c => ({ value: c.id, label: c.name }))} selected={fCp} onChange={setFCp} />
            <MultiDrop label="Тип операции" options={[{ value: 'income', label: 'Поступления' }, { value: 'expense', label: 'Списания' }]} selected={fOpType} onChange={setFOpType} />
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, position: 'relative' }}>
              <IconBtn title="Сбросить фильтры" onClick={resetFilters}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
              <IconBtn title="Настройка колонок" active={colPicker} onClick={() => setColPicker(o => !o)}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></svg></IconBtn>
              {colPicker && (<>
                <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setColPicker(false)} />
                <div style={{ position: 'absolute', right: 0, top: '120%', zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, minWidth: 200, maxHeight: 340, overflowY: 'auto' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Колонки</div>
                  {COLS.filter(([k]) => k !== 'sel' && k !== 'actions').map(([k, , label]) => (
                    <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 2px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggleCol(k)} /> {label || k}
                    </label>
                  ))}
                </div>
              </>)}
            </div>
          </div>

          {/* слот форм: редактирование / массовое */}
          <div ref={editAnchor} data-edit-anchor>
            {editing && canEdit && (
              <div style={{ background: '#FFFCF7', border: '1px solid #F0D7AE', borderRadius: 14, padding: '18px 20px', margin: '10px 0 4px', animation: 'opRise .24s cubic-bezier(0.22,1,0.36,1) both' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <span style={{ width: 28, height: 28, borderRadius: 9, background: 'var(--warning-tint)', color: '#B26A0C', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>
                  <span style={{ fontSize: 15, fontWeight: 700, flex: 1 }}>Редактирование #{editing.id}</span>
                  <span onClick={() => setEditing(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>✕</span>
                </div>
                <OpFields f={editing} set={p => setEditing(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} accent="warn" />
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)', flex: 1 }}>поля, отмеченные «необяз.», можно оставить пустыми</span>
                  <button onClick={saveEdit} disabled={saving} style={{ background: 'var(--dot-current-dz)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Сохранить изменения</button>
                  <button onClick={() => setEditing(null)} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 16px', fontSize: 13, cursor: 'pointer' }}>Отмена</button>
                </div>
              </div>
            )}
            {canEdit && selIds.length > 0 && (
              <div style={{ background: '#F6F8FF', border: '1px solid #D7DEFA', borderRadius: 14, padding: '16px 18px', margin: '10px 0 4px', display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap', animation: 'opRise .24s cubic-bezier(0.22,1,0.36,1) both' }}>
                <div style={{ minWidth: 150, borderRight: '1px solid #DDE3F5', paddingRight: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#3A50BE', marginBottom: 6 }}>Выбрано: {selIds.length}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--income)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)' }} />+{fmt(selIncome)} ₽</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--text-primary)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: '#8B93A6' }} />−{fmt(selExpense)} ₽</div>
                </div>
                {[['Статус', 'status', STATUSES.map(s => ({ value: s, label: s })), 150], ['Банк', 'bank', BANKS.map(b => ({ value: b, label: b })), 140], ['НДС', 'vat_rate', VAT_OPTIONS.map(v => ({ value: v, label: v + '%' })), 112], ['Статья', 'article_id', articles.map(a => ({ value: a.id, label: a.name })), 160], ['Контрагент', 'counterparty_id', counterparties.map(c => ({ value: c.id, label: c.name })), 190]].map(([label, k, opts, w]) => (
                  <div key={k} style={{ display: 'flex', flexDirection: 'column', width: w, flexShrink: 0 }}>
                    <span style={lbl}>{label}</span>
                    {(k === 'article_id' || k === 'counterparty_id')
                      ? <SingleSelect value={bulk[k]} onChange={v => setBulk(b => ({ ...b, [k]: v }))} options={opts} placeholder="не менять" emptyLabel="не менять" />
                      : <select value={bulk[k]} onChange={e => setBulk(b => ({ ...b, [k]: e.target.value }))} style={{ ...inp, width: '100%' }}><option value="">не менять</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>}
                  </div>
                ))}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  <button onClick={applyBulk} disabled={saving} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 15px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Применить к {selIds.length}</button>
                  <button onClick={delBulk} disabled={saving} style={{ background: 'var(--bg-card)', border: '1px solid #F3C9CC', color: '#C93A3E', borderRadius: 10, padding: '9px 15px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Удалить {selIds.length}</button>
                  <button onClick={() => setSel({})} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', padding: '9px 12px', fontSize: 13, cursor: 'pointer' }}>Снять выделение</button>
                </div>
              </div>
            )}
          </div>

          {/* показано + пагинация */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
            <span>Показано <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{total ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, total)}</b> из <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{new Intl.NumberFormat('ru-RU').format(total)}</b></span>
            <span style={{ display: 'inline-flex', gap: 14 }}>
              {[['оплачено', 'var(--income)'], ['план оплат', 'var(--dot-expense)'], ['ожидает', 'var(--dot-current-dz)']].map(([l, c]) => <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>)}
            </span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, alignItems: 'center' }}>
              <IconBtn title="В начало" onClick={() => setPage(0)}>«</IconBtn>
              <IconBtn title="Назад" onClick={() => setPage(p => Math.max(0, p - 1))}>‹</IconBtn>
              <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', padding: '0 6px' }}>{page + 1} / {totalPages}</span>
              <IconBtn title="Вперёд" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}>›</IconBtn>
              <IconBtn title="В конец" onClick={() => setPage(totalPages - 1)}>»</IconBtn>
            </div>
          </div>

          {/* таблица */}
          <div style={{ overflowX: 'auto', margin: '10px -8px 0', padding: '0 8px' }}>
            <div style={{ minWidth: 1580 }}>
              <div style={{ display: 'grid', gridTemplateColumns: gridT, gap: 10, padding: '0 0 10px', borderBottom: '1px solid var(--border-card)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                {visibleCols.map(([k, w, label, sc]) => k === 'sel'
                  ? <span key={k}><input type="checkbox" ref={el => { if (el) el.indeterminate = someOnPage && !allOnPage }} checked={allOnPage} onChange={e => setSel(e.target.checked ? Object.fromEntries(rows.map(o => [o.id, true])) : {})} style={{ width: 14, height: 14, cursor: 'pointer' }} /></span>
                  : <span key={k} onClick={() => onSort(sc)} style={{ textAlign: RIGHT.has(k) ? 'right' : 'left', cursor: sc ? 'pointer' : 'default', color: sortCol === sc ? 'var(--accent)' : undefined }}>{label}{sortCol === sc ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}</span>)}
              </div>
              {loading ? <div style={{ padding: 30, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
                : rows.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет операций по выбранным фильтрам</div>
                  : rows.map(o => (
                    <div key={o.id} className="op-row" style={{ display: 'grid', gridTemplateColumns: gridT, gap: 10, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', fontSize: 14.4, color: 'var(--text-primary)', background: sel[o.id] ? 'var(--accent-tint)' : 'transparent' }}>
                      {visibleCols.map(([k]) => <span key={k} style={{ textAlign: RIGHT.has(k) ? 'right' : 'left', overflow: 'hidden' }}>{cell(o, k)}</span>)}
                    </div>
                  ))}
            </div>
          </div>

          {/* подвал */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', paddingTop: 14, marginTop: 6, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
            <span>выделено <b style={{ color: 'var(--text-primary)' }}>{selIds.length}</b> операций</span>
            <span>итого на странице: поступления <b style={{ color: 'var(--income)', fontFamily: MONO }}>{fmt(pageIncome)} ₽</b> · списания <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{fmt(pageExpense)} ₽</b></span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
              <span>строк на странице</span>
              <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
                {PAGE_SIZES.map(n => <button key={n} onClick={() => { setPageSize(n); setPage(0) }} style={{ border: 'none', borderRadius: 8, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, background: pageSize === n ? 'var(--accent-tint)' : 'transparent', color: pageSize === n ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: pageSize === n ? 700 : 600 }}>{n}</button>)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
