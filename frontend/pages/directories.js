import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Navbar from '../components/Navbar'

const api = (token) => axios.create({
  // См. комментарий в balance.js — относительный путь, проксируется Caddy.
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'

// Должно совпадать с DEFAULT_TERM_DAYS в backend/app/routers/reports.py — используется
// только как плейсхолдер/подсказка в поле "Отсрочка", фактическое значение всегда приходит с backend.
const DEFAULT_TERM_DAYS = 60

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

// Пикер контрагента из реестра (Counterparty — единый источник данных для всех полей
// "контрагент" в системе, см. CLAUDE.md), с инлайн-созданием нового контрагента, если
// нужного нет в списке. Тот же паттерн, что и CounterpartySearch в operations.js
// (продублирован здесь, а не импортирован — см. CLAUDE.md про отсутствие общего lib/).
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

  const selected = counterparties.find(c => c.id === value)
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
      <div onClick={() => { setOpen(o => !o); setSearch('') }}
        style={{ width: '100%', padding: '5px 8px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', cursor: 'pointer', background: 'white', userSelect: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {selected ? selected.name : '— выберите контрагента —'}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, minWidth: '260px', marginTop: '4px', background: 'white', border: '1px solid #d1d5db', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 500, maxHeight: '280px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px', borderBottom: '1px solid #f3f4f6' }}>
            <input autoFocus placeholder="Поиск контрагента..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            <div onClick={() => { onChange(null); setOpen(false) }}
              style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', color: '#6b7280', borderBottom: '1px solid #f9fafb' }}>
              — не указан —
            </div>
            {filtered.map(c => (
              <div key={c.id} onClick={() => { onChange(c.id); setOpen(false); setSearch('') }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', background: value === c.id ? '#eff6ff' : 'white' }}>
                {c.name}
              </div>
            ))}
            {search && !filtered.find(c => c.name.toLowerCase() === search.toLowerCase()) && (
              <div onClick={() => { setNewName(search); setCreating(true) }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '14px', color: '#2563eb', borderTop: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', gap: '6px' }}>
                + Создать «{search}»
              </div>
            )}
          </div>
          {creating && (
            <div style={{ padding: '8px', borderTop: '1px solid #d1d5db', display: 'flex', gap: '6px' }}>
              <input value={newName} onChange={e => setNewName(e.target.value)}
                style={{ flex: 1, padding: '5px 8px', borderRadius: '6px', border: '1px solid #2563eb', fontSize: '14px', outline: 'none' }} />
              <button onClick={handleCreate} style={{ padding: '5px 10px', borderRadius: '6px', border: 'none', background: '#2563eb', color: 'white', fontSize: '14px', cursor: 'pointer' }}>Создать</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Раздел "Справочники" — вынесен из "Настройки" (Контрагенты/Статьи/Договоры),
// доступен из меню кнопкой "Справочники" (заменила "Импорт", см. Navbar.js).
export default function Directories() {
  const router = useRouter()
  const [tab, setTab] = useState('counterparties')
  const [role, setRole] = useState('')
  const [permissions, setPermissions] = useState({})

  // Контрагенты (справочник)
  const [counterparties, setCounterparties] = useState([])
  const [loadingCounterparties, setLoadingCounterparties] = useState(false)
  const [cpEditingId, setCpEditingId] = useState(null)
  const [cpDraft, setCpDraft] = useState({ name: '', inn: '', status: 'действующий', term_days: '' })
  const [cpSaving, setCpSaving] = useState(false)
  const [cpError, setCpError] = useState('')
  const [cpSearch, setCpSearch] = useState('')
  const [cpStatusFilter, setCpStatusFilter] = useState('действующий')
  const [cpSortCol, setCpSortCol] = useState('name')
  const [cpSortDir, setCpSortDir] = useState('asc')
  const [cpSelectedIds, setCpSelectedIds] = useState([])
  const [cpBulkStatus, setCpBulkStatus] = useState('')
  const [cpBulkGroup, setCpBulkGroup] = useState('')
  const [cpBulkSaving, setCpBulkSaving] = useState(false)
  const [cpDeleteConfirming, setCpDeleteConfirming] = useState(false)
  const [cpDeletePassword, setCpDeletePassword] = useState('')
  const [cpDeleteError, setCpDeleteError] = useState('')
  const [cpDeleteLoading, setCpDeleteLoading] = useState(false)
  const [cpCreating, setCpCreating] = useState(false)
  const [cpNewForm, setCpNewForm] = useState({ name: '', inn: '', status: 'действующий' })
  const [cpNewError, setCpNewError] = useState('')
  const [cpNewSaving, setCpNewSaving] = useState(false)

  // Статьи (справочник)
  const [articles, setArticles] = useState([])
  const [loadingArticles, setLoadingArticles] = useState(false)
  const [artEditingId, setArtEditingId] = useState(null)
  const [artDraft, setArtDraft] = useState({ name: '', group: '', type: 'expense' })
  const [artSaving, setArtSaving] = useState(false)
  const [artError, setArtError] = useState('')
  const [artSearch, setArtSearch] = useState('')
  const [artMovingId, setArtMovingId] = useState(null)
  const [newArticle, setNewArticle] = useState({ name: '', group: '', type: 'expense' })
  const [creatingArticle, setCreatingArticle] = useState(false)
  const [artCreateError, setArtCreateError] = useState('')

  // Договоры (справочник) — контрагент привязывается к реестру Контрагентов через
  // counterparty_id (FK); counterparty_name/inn для привязанных строк server-side
  // выводятся из Counterparty и тут только для отображения непривязанных легаси-строк.
  const EMPTY_CONTRACT = { counterparty_id: null, contract_number: '', contract_date: '', inn: '', counterparty_name: '', marketing_name: '', cooperation_format: '', end_date_text: '', prolongation: '', payment_form: '', payment_term_days: '', payment_term_condition: '', note: '' }
  const [contracts, setContracts] = useState([])
  const [loadingContracts, setLoadingContracts] = useState(false)
  const [ctEditingId, setCtEditingId] = useState(null)
  const [ctDraft, setCtDraft] = useState(EMPTY_CONTRACT)
  const [ctSaving, setCtSaving] = useState(false)
  const [ctError, setCtError] = useState('')
  const [ctSearch, setCtSearch] = useState('')
  const [ctFormatFilter, setCtFormatFilter] = useState('')
  const [ctProlongationFilter, setCtProlongationFilter] = useState('')
  const [ctSortCol, setCtSortCol] = useState('contract_date')
  const [ctSortDir, setCtSortDir] = useState('desc')
  const [ctSelectedIds, setCtSelectedIds] = useState([])
  const [ctBulkFormat, setCtBulkFormat] = useState('')
  const [ctBulkProlongation, setCtBulkProlongation] = useState('')
  const [ctBulkPaymentDays, setCtBulkPaymentDays] = useState('')
  const [ctBulkPaymentCondition, setCtBulkPaymentCondition] = useState('')
  const [ctBulkSaving, setCtBulkSaving] = useState(false)
  const [newContract, setNewContract] = useState(EMPTY_CONTRACT)
  const [creatingContract, setCreatingContract] = useState(false)
  const [ctCreateError, setCtCreateError] = useState('')
  const [showNewContract, setShowNewContract] = useState(false)

  // Фиксированные списки для Договоров (запрос пользователя) — старые значения, не
  // входящие в список, не скрываются и не подменяются, просто показываются как есть
  // в селекте отдельным пунктом (см. компонент SelectWithLegacy ниже).
  const COOPERATION_FORMATS = ['Агентство КЛ', 'Агентство ПД', 'Клиент', 'Подрядчик', 'Аптека', 'Паблишер', 'Рекламная система']
  const PROLONGATION_OPTIONS = ['АВТО на год', 'По соглашению', 'Нет']
  const PAYMENT_TERM_CONDITIONS = ['С даты УПД', 'С даты АКТ', 'По периоду']

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    const r = localStorage.getItem('role') || ''
    const perms = getPermissions()
    if (r !== 'admin' && !can(perms, 'counterparties', 'view') && !can(perms, 'articles', 'view') && !can(perms, 'contracts', 'view')) { router.push('/dashboard'); return }
    setRole(r)
    setPermissions(perms)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    // Контрагенты грузятся и для вкладки "Договоры" — нужны для пикера привязки
    // договора к реестру (CounterpartySearch, см. ниже).
    if (tab === 'counterparties' || tab === 'contracts') loadCounterparties(token)
    if (tab === 'articles') loadArticles(token)
    if (tab === 'contracts') loadContracts(token)
  }, [tab])

  // ---------- Контрагенты (справочник) ----------

  const loadCounterparties = async (token) => {
    setLoadingCounterparties(true)
    try {
      const res = await api(token).get('/counterparties/registry')
      setCounterparties(res.data.items)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingCounterparties(false)
    }
  }

  const openCpEdit = (c) => {
    setCpEditingId(c.id)
    setCpDraft({ name: c.name, inn: c.inn || '', status: c.status, term_days: c.term_days != null ? String(c.term_days) : '' })
    setCpError('')
  }

  const cancelCpEdit = () => { setCpEditingId(null); setCpError('') }

  const handleSaveCounterparty = async (id) => {
    const token = localStorage.getItem('token')
    setCpSaving(true)
    setCpError('')
    try {
      await api(token).put(`/counterparties/${id}/registry`, { name: cpDraft.name, inn: cpDraft.inn, status: cpDraft.status, term_days: cpDraft.term_days !== '' ? parseInt(cpDraft.term_days, 10) : null })
      await loadCounterparties(token)
      setCpEditingId(null)
    } catch (e) {
      setCpError(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setCpSaving(false)
    }
  }

  // Создание нового контрагента "на ходу" из пикера на вкладке "Договоры" (см.
  // CounterpartySearch ниже) — тот же паттерн, что и в operations.js. После создания
  // перезагружаем полный реестр (а не просто добавляем в список), т.к. /registry
  // возвращает агрегированные поля (op_count, receivable и т.п.), которых у только
  // что созданного контрагента ещё нет смысла подделывать на клиенте.
  const createCounterparty = async (name) => {
    const token = localStorage.getItem('token')
    try {
      const res = await api(token).post('/counterparties/', { name, vat_rate: 0 })
      await loadCounterparties(token)
      return { id: res.data.id, name }
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при создании контрагента')
      return null
    }
  }

  const handleCpCreate = async () => {
    const name = cpNewForm.name.trim()
    if (!name) { setCpNewError('Название обязательно'); return }
    const token = localStorage.getItem('token')
    setCpNewSaving(true); setCpNewError('')
    try {
      // Создаём контрагента (POST принимает только name+vat_rate)
      const res = await api(token).post('/counterparties/', { name, vat_rate: 0 })
      const newId = res.data.id
      // Затем сразу обновляем ИНН и Вид через реестровый PUT
      await api(token).put(`/counterparties/${newId}/registry`, {
        name,
        inn: cpNewForm.inn.trim() || null,
        status: cpNewForm.status,
        term_days: null,
      })
      setCpCreating(false)
      setCpNewForm({ name: '', inn: '', status: 'действующий' })
      await loadCounterparties(token)
    } catch (e) {
      setCpNewError(e.response?.data?.detail || 'Ошибка при создании контрагента')
    } finally {
      setCpNewSaving(false)
    }
  }

  const toggleCpSelect = (id) => setCpSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const handleCpBulkApply = async () => {
    const fields = {}
    if (cpBulkStatus) fields.status = cpBulkStatus
    if (cpBulkGroup) fields.group_override = cpBulkGroup === '__reset__' ? '' : cpBulkGroup
    if (Object.keys(fields).length === 0) { alert('Выберите хотя бы одно поле для изменения'); return }
    const labels = { status: 'Вид', group_override: 'Группа' }
    const summary = Object.entries(fields).map(([k, v]) => `${labels[k]} → ${v === '' ? 'сброс на авто' : v}`).join(', ')
    if (!confirm(`Изменить ${cpSelectedIds.length} контрагентов?\n${summary}`)) return
    const token = localStorage.getItem('token')
    setCpBulkSaving(true)
    try {
      await api(token).patch('/counterparties/bulk', { ids: cpSelectedIds, ...fields })
      setCpSelectedIds([]); setCpBulkStatus(''); setCpBulkGroup('')
      await loadCounterparties(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при массовом редактировании')
    } finally {
      setCpBulkSaving(false)
    }
  }

  const handleCpBulkDelete = async () => {
    if (!cpDeletePassword) { setCpDeleteError('Введите пароль'); return }
    const token = localStorage.getItem('token')
    setCpDeleteLoading(true); setCpDeleteError('')
    try {
      await api(token).delete('/counterparties/bulk', { data: { ids: cpSelectedIds, password: cpDeletePassword } })
      setCpSelectedIds([]); setCpDeleteConfirming(false); setCpDeletePassword('')
      await loadCounterparties(token)
    } catch (e) {
      const detail = e.response?.data?.detail
      setCpDeleteError(detail ? (typeof detail === 'string' ? detail : JSON.stringify(detail)) : 'Ошибка при удалении')
    } finally {
      setCpDeleteLoading(false)
    }
  }

  const handleCpSort = (col) => {
    setCpSortDir(prev => (cpSortCol === col ? (prev === 'asc' ? 'desc' : 'asc') : 'asc'))
    setCpSortCol(col)
  }

  const RELATION_LABELS = { 'заказчик': 'Заказчик', 'поставщик': 'Поставщик', 'смешенный': 'Смешенный' }
  const RELATION_COLORS = {
    'заказчик': { bg: '#dbeafe', color: '#2563eb' },
    'поставщик': { bg: '#fef9c3', color: '#d97706' },
    'смешенный': { bg: '#f3e8ff', color: '#7c3aed' },
  }

  const filteredCounterparties = counterparties
    .filter(c => {
      if (cpStatusFilter && c.status !== cpStatusFilter) return false
      if (cpSearch) {
        const q = cpSearch.toLowerCase()
        if (!c.name.toLowerCase().includes(q) && !(c.inn || '').includes(q)) return false
      }
      return true
    })
    .sort((a, b) => {
      const av = a[cpSortCol], bv = b[cpSortCol]
      let cmp
      if (typeof av === 'number' || typeof bv === 'number') cmp = (av || 0) - (bv || 0)
      else cmp = String(av || '').localeCompare(String(bv || ''), 'ru')
      return cpSortDir === 'asc' ? cmp : -cmp
    })

  const allCpVisibleSelected = filteredCounterparties.length > 0 && filteredCounterparties.every(c => cpSelectedIds.includes(c.id))
  const toggleCpSelectAllVisible = () => setCpSelectedIds(allCpVisibleSelected ? [] : filteredCounterparties.map(c => c.id))

  // ---------- Статьи (справочник) ----------

  const loadArticles = async (token) => {
    setLoadingArticles(true)
    try {
      const res = await api(token).get('/articles/registry')
      setArticles(res.data.items)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingArticles(false)
    }
  }

  const handleCreateArticle = async () => {
    setArtCreateError('')
    if (!newArticle.name.trim()) { setArtCreateError('Введите название статьи'); return }
    const token = localStorage.getItem('token')
    setCreatingArticle(true)
    try {
      await api(token).post('/articles/', { name: newArticle.name.trim(), group: newArticle.group || null, type: newArticle.type })
      setNewArticle({ name: '', group: '', type: 'expense' })
      await loadArticles(token)
    } catch (e) {
      setArtCreateError(e.response?.data?.detail || 'Ошибка при создании')
    } finally {
      setCreatingArticle(false)
    }
  }

  const openArtEdit = (a) => {
    setArtEditingId(a.id)
    setArtDraft({ name: a.name, group: a.group || '', type: a.type || 'expense' })
    setArtError('')
  }

  const cancelArtEdit = () => { setArtEditingId(null); setArtError('') }

  const handleSaveArticle = async (id) => {
    const token = localStorage.getItem('token')
    setArtSaving(true)
    setArtError('')
    try {
      await api(token).put(`/articles/${id}`, { name: artDraft.name, group: artDraft.group || null, type: artDraft.type })
      await loadArticles(token)
      setArtEditingId(null)
    } catch (e) {
      setArtError(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setArtSaving(false)
    }
  }

  const handleDeleteArticle = async (a) => {
    if (!confirm(`Удалить статью «${a.name}»?`)) return
    const token = localStorage.getItem('token')
    try {
      await api(token).delete(`/articles/${a.id}`)
      await loadArticles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при удалении')
    }
  }

  const handleMoveArticle = async (id, direction) => {
    const token = localStorage.getItem('token')
    setArtMovingId(id)
    try {
      await api(token).put(`/articles/${id}/move`, { direction })
      await loadArticles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при изменении порядка')
    } finally {
      setArtMovingId(null)
    }
  }

  const articleGroups = [...new Set(articles.map(a => a.group).filter(Boolean))]

  const filteredArticles = artSearch
    ? articles.filter(a => a.name.toLowerCase().includes(artSearch.toLowerCase()) || (a.group || '').toLowerCase().includes(artSearch.toLowerCase()))
    : articles

  const ARTICLE_TYPE_META = {
    income: { label: 'Доход', bg: '#dcfce7', color: '#16a34a' },
    expense: { label: 'Расход', bg: '#fee2e2', color: '#dc2626' },
  }

  // ---------- Договоры (справочник) ----------

  const loadContracts = async (token) => {
    setLoadingContracts(true)
    try {
      const res = await api(token).get('/contracts/registry')
      setContracts(res.data.items)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingContracts(false)
    }
  }

  const contractPayload = (d) => ({
    ...d,
    contract_date: d.contract_date || null,
    payment_term_days: d.payment_term_days !== '' && d.payment_term_days != null ? parseInt(d.payment_term_days, 10) : null,
  })

  const handleCreateContract = async () => {
    if (!newContract.counterparty_id) {
      setCtCreateError('Выберите контрагента из реестра контрагентов')
      return
    }
    setCtCreateError('')
    const token = localStorage.getItem('token')
    setCreatingContract(true)
    try {
      await api(token).post('/contracts/', contractPayload(newContract))
      setNewContract(EMPTY_CONTRACT)
      setShowNewContract(false)
      await loadContracts(token)
    } catch (e) {
      setCtCreateError(e.response?.data?.detail || 'Ошибка при создании')
    } finally {
      setCreatingContract(false)
    }
  }

  const openCtEdit = (c) => {
    setCtEditingId(c.id)
    setCtDraft({ ...EMPTY_CONTRACT, ...c, contract_date: c.contract_date || '', payment_term_days: c.payment_term_days != null ? String(c.payment_term_days) : '' })
    setCtError('')
  }

  const cancelCtEdit = () => { setCtEditingId(null); setCtError('') }

  const handleSaveContract = async (id) => {
    const token = localStorage.getItem('token')
    setCtSaving(true)
    setCtError('')
    try {
      await api(token).put(`/contracts/${id}`, contractPayload(ctDraft))
      await loadContracts(token)
      setCtEditingId(null)
    } catch (e) {
      setCtError(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setCtSaving(false)
    }
  }

  const handleDeleteContract = async (c) => {
    if (!confirm(`Удалить договор № ${c.contract_number || '—'} (${c.counterparty_name || '—'})?`)) return
    const token = localStorage.getItem('token')
    try {
      await api(token).delete(`/contracts/${c.id}`)
      await loadContracts(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при удалении')
    }
  }

  const toggleCtSelect = (id) => setCtSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const handleCtBulkApply = async () => {
    const fields = {}
    if (ctBulkFormat) fields.cooperation_format = ctBulkFormat
    if (ctBulkProlongation) fields.prolongation = ctBulkProlongation
    if (ctBulkPaymentDays !== '') fields.payment_term_days = parseInt(ctBulkPaymentDays, 10)
    if (ctBulkPaymentCondition) fields.payment_term_condition = ctBulkPaymentCondition
    if (Object.keys(fields).length === 0) { alert('Выберите хотя бы одно поле для изменения'); return }
    const labels = { cooperation_format: 'Формат сотрудничества', prolongation: 'Пролонгация', payment_term_days: 'Срок оплаты, дни', payment_term_condition: 'Условие' }
    const summary = Object.entries(fields).map(([k, v]) => `${labels[k]} → ${v}`).join(', ')
    if (!confirm(`Изменить ${ctSelectedIds.length} договоров?\n${summary}`)) return
    const token = localStorage.getItem('token')
    setCtBulkSaving(true)
    try {
      await api(token).patch('/contracts/bulk', { ids: ctSelectedIds, ...fields })
      setCtSelectedIds([]); setCtBulkFormat(''); setCtBulkProlongation(''); setCtBulkPaymentDays(''); setCtBulkPaymentCondition('')
      await loadContracts(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при массовом редактировании')
    } finally {
      setCtBulkSaving(false)
    }
  }

  const handleCtBulkDelete = async () => {
    if (!confirm(`Удалить ${ctSelectedIds.length} договоров? Это действие необратимо.`)) return
    const token = localStorage.getItem('token')
    setCtBulkSaving(true)
    try {
      await api(token).delete('/contracts/bulk', { data: { ids: ctSelectedIds } })
      setCtSelectedIds([])
      await loadContracts(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при массовом удалении')
    } finally {
      setCtBulkSaving(false)
    }
  }

  const handleCtSort = (col) => {
    setCtSortDir(prev => (ctSortCol === col ? (prev === 'asc' ? 'desc' : 'asc') : 'asc'))
    setCtSortCol(col)
  }

  const ctFormatOptions = [...new Set(contracts.map(c => c.cooperation_format).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'))
  const ctProlongationOptions = [...new Set(contracts.map(c => c.prolongation).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'))

  const filteredContracts = contracts
    .filter(c => {
      if (ctFormatFilter && c.cooperation_format !== ctFormatFilter) return false
      if (ctProlongationFilter && c.prolongation !== ctProlongationFilter) return false
      if (ctSearch) {
        const q = ctSearch.toLowerCase()
        if (![c.contract_number, c.counterparty_name, c.marketing_name, c.inn].some(v => (v || '').toLowerCase().includes(q))) return false
      }
      return true
    })
    .sort((a, b) => {
      const av = a[ctSortCol], bv = b[ctSortCol]
      let cmp
      if (typeof av === 'number' || typeof bv === 'number') cmp = (av || 0) - (bv || 0)
      else cmp = String(av || '').localeCompare(String(bv || ''), 'ru')
      return ctSortDir === 'asc' ? cmp : -cmp
    })

  const allCtVisibleSelected = filteredContracts.length > 0 && filteredContracts.every(c => ctSelectedIds.includes(c.id))
  const toggleCtSelectAllVisible = () => setCtSelectedIds(allCtVisibleSelected ? [] : filteredContracts.map(c => c.id))

  const inp = { width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none', textAlign: 'right' }
  const inpLeft = { ...inp, textAlign: 'left' }
  const select = { padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none' }
  const btn = { padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: 'pointer', fontSize: '15px', whiteSpace: 'nowrap' }

  // Сортируемый заголовок таблицы контрагентов — визуально как в /operations (липкая шапка, стрелка сортировки)
  const cpTh = { textAlign: 'left', padding: '8px 10px', color: '#6b7280', fontWeight: '500', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid #e5e7eb', background: '#f9fafb', position: 'sticky', top: 0, zIndex: 10, fontSize: '14px' }
  const CpSortIcon = ({ col }) => cpSortCol !== col ? <span style={{ color: '#d1d5db', marginLeft: '4px' }}>↕</span> : <span style={{ color: '#2563eb', marginLeft: '4px' }}>{cpSortDir === 'asc' ? '↑' : '↓'}</span>

  // Сортируемый заголовок таблицы договоров — тот же визуальный паттерн, что и cpTh/CpSortIcon выше
  const ctTh = cpTh
  const CtSortIcon = ({ col }) => ctSortCol !== col ? <span style={{ color: '#d1d5db', marginLeft: '4px' }}>↕</span> : <span style={{ color: '#2563eb', marginLeft: '4px' }}>{ctSortDir === 'asc' ? '↑' : '↓'}</span>

  // Выпадающий список с фиксированными вариантами (COOPERATION_FORMATS и т.п.), но если у строки
  // уже стоит старое значение, не входящее в список — показываем его как отдельный вариант, а не
  // скрываем/подменяем (см. CLAUDE.md про осторожность с нечётким сопоставлением данных).
  const SelectWithLegacy = ({ value, options, onChange, style, emptyLabel }) => (
    <select value={value || ''} onChange={onChange} style={style}>
      <option value="">{emptyLabel || '—'}</option>
      {value && !options.includes(value) && <option value={value}>{value} (старое значение)</option>}
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )

  // Фиксированный список (PROLONGATION_OPTIONS, COOPERATION_FORMATS и т.п.) + пункт "Прочее"
  // с полем для свободного ввода. Старые/нестандартные значения в БД автоматически открываются
  // в режиме "Прочее" с текстом значения в поле, а не скрываются и не подменяются.
  const SelectWithOther = ({ value, options, onChange, style, emptyLabel }) => {
    const isKnownCustom = !!value && !options.includes(value)
    const [customMode, setCustomMode] = useState(isKnownCustom)
    const selectValue = customMode ? 'Прочее' : (value || '')
    return (
      <span style={{ display: 'inline-flex', gap: '6px' }}>
        <select value={selectValue} onChange={e => {
          const v = e.target.value
          if (v === 'Прочее') { setCustomMode(true); onChange({ target: { value: '' } }) }
          else { setCustomMode(false); onChange(e) }
        }} style={style}>
          <option value="">{emptyLabel || '—'}</option>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
          <option value="Прочее">Прочее</option>
        </select>
        {customMode && (
          <input type="text" value={value || ''} placeholder="Укажите вариант" onChange={onChange} style={{ ...inpLeft, width: '150px' }} />
        )}
      </span>
    )
  }

  const tabs = []
  if (role === 'admin' || can(permissions, 'counterparties', 'view')) {
    tabs.push({ id: 'counterparties', label: 'Контрагенты' })
  }
  if (role === 'admin' || can(permissions, 'articles', 'view')) {
    tabs.push({ id: 'articles', label: 'Статьи' })
  }
  if (role === 'admin' || can(permissions, 'contracts', 'view')) {
    tabs.push({ id: 'contracts', label: 'Договоры' })
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Navbar active="directories">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '6px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px', background: tab === t.id ? '#2563eb' : 'transparent', color: tab === t.id ? 'white' : '#374151' }}>
            {t.label}
          </button>
        ))}
      </Navbar>

      <div style={{ padding: '24px', maxWidth: 1920, margin: '0 auto' }}>

        {tab === 'counterparties' && (
          <div>
            {/* Фильтры */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              <input placeholder="Поиск по названию или ИНН" value={cpSearch} onChange={e => setCpSearch(e.target.value)} style={{ ...inpLeft, width: '260px' }} />
              <select value={cpStatusFilter} onChange={e => setCpStatusFilter(e.target.value)} style={select}>
                <option value="">Все виды</option>
                <option value="действующий">Действующий</option>
                <option value="виртуальный">Виртуальный</option>
              </select>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '14px', color: '#6b7280' }}>{filteredCounterparties.length} из {counterparties.length}</span>
                {(role === 'admin' || can(permissions, 'counterparties', 'edit')) && (
                  <button onClick={() => { setCpCreating(c => !c); setCpNewError('') }}
                    style={{ padding: '7px 14px', borderRadius: '8px', border: 'none', background: cpCreating ? '#e5e7eb' : '#2563eb', color: cpCreating ? '#374151' : 'white', cursor: 'pointer', fontSize: '14px', whiteSpace: 'nowrap' }}>
                    {cpCreating ? '✕ Отмена' : '+ Добавить контрагента'}
                  </button>
                )}
              </div>
            </div>

            {cpCreating && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '16px 20px', marginBottom: '12px', border: '2px solid #2563eb', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Название <span style={{ color: '#ef4444' }}>*</span></div>
                  <input value={cpNewForm.name} onChange={e => setCpNewForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="ООО Контрагент" autoFocus
                    style={{ ...inpLeft, width: '260px' }} />
                </div>
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>ИНН</div>
                  <input value={cpNewForm.inn} onChange={e => setCpNewForm(f => ({ ...f, inn: e.target.value }))}
                    placeholder="1234567890"
                    style={{ ...inpLeft, width: '160px' }} />
                </div>
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Вид</div>
                  <select value={cpNewForm.status} onChange={e => setCpNewForm(f => ({ ...f, status: e.target.value }))} style={select}>
                    <option value="действующий">Действующий</option>
                    <option value="виртуальный">Виртуальный</option>
                  </select>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', flexWrap: 'wrap' }}>
                  <button onClick={handleCpCreate} disabled={cpNewSaving}
                    style={{ padding: '8px 20px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: cpNewSaving ? 'default' : 'pointer', fontSize: '15px', opacity: cpNewSaving ? 0.6 : 1 }}>
                    {cpNewSaving ? 'Сохранение...' : 'Сохранить'}
                  </button>
                  <button onClick={() => { setCpCreating(false); setCpNewForm({ name: '', inn: '', status: 'действующий' }); setCpNewError('') }}
                    style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: '#6b7280' }}>
                    Отмена
                  </button>
                  {cpNewError && <span style={{ fontSize: '14px', color: '#ef4444' }}>{cpNewError}</span>}
                </div>
              </div>
            )}

            {(role === 'admin' || can(permissions, 'counterparties', 'edit')) && cpSelectedIds.length > 0 && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', border: '2px solid #2563eb', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ fontSize: '15px', fontWeight: '500', color: '#2563eb', marginRight: '4px', alignSelf: 'center' }}>Выбрано: {cpSelectedIds.length}</div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Вид</div>
                  <select style={select} value={cpBulkStatus} onChange={e => setCpBulkStatus(e.target.value)}>
                    <option value="">— не менять —</option>
                    <option value="действующий">Действующий</option>
                    <option value="виртуальный">Виртуальный</option>
                  </select>
                </div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Группа</div>
                  <input placeholder="Новая группа" value={cpBulkGroup === '__reset__' ? '' : cpBulkGroup}
                    onChange={e => setCpBulkGroup(e.target.value)}
                    style={{ ...inpLeft, width: '180px' }} />
                </div>
                <button onClick={() => setCpBulkGroup('__reset__')} title="Вернуть автоматический расчёт группы (самая частая статья)"
                  style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', background: cpBulkGroup === '__reset__' ? '#eff6ff' : 'transparent', color: cpBulkGroup === '__reset__' ? '#2563eb' : '#6b7280', cursor: 'pointer', fontSize: '14px' }}>
                  Сбросить группу на авто
                </button>
                <button onClick={handleCpBulkApply} disabled={cpBulkSaving} style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: 'pointer', fontSize: '15px' }}>
                  {cpBulkSaving ? 'Сохранение...' : `Применить к ${cpSelectedIds.length}`}
                </button>
                {role === 'admin' && (
                  cpDeleteConfirming ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <input type="password" placeholder="Ваш пароль" value={cpDeletePassword}
                        onChange={e => setCpDeletePassword(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleCpBulkDelete()}
                        autoFocus
                        style={{ ...inpLeft, width: '180px', padding: '8px 12px' }} />
                      <button onClick={handleCpBulkDelete} disabled={cpDeleteLoading}
                        style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#dc2626', color: 'white', cursor: cpDeleteLoading ? 'default' : 'pointer', fontSize: '15px', opacity: cpDeleteLoading ? 0.7 : 1 }}>
                        {cpDeleteLoading ? '...' : 'Подтвердить удаление'}
                      </button>
                      <button onClick={() => { setCpDeleteConfirming(false); setCpDeletePassword(''); setCpDeleteError('') }}
                        style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: '#6b7280' }}>
                        Отмена
                      </button>
                      {cpDeleteError && <span style={{ fontSize: '14px', color: '#dc2626' }}>{cpDeleteError}</span>}
                    </div>
                  ) : (
                    <button onClick={() => { setCpDeleteConfirming(true); setCpDeletePassword(''); setCpDeleteError('') }}
                      style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #fca5a5', background: '#fee2e2', color: '#dc2626', cursor: 'pointer', fontSize: '15px' }}>
                      Удалить {cpSelectedIds.length}
                    </button>
                  )
                )}
                <button onClick={() => { setCpSelectedIds([]); setCpBulkStatus(''); setCpBulkGroup(''); setCpDeleteConfirming(false); setCpDeletePassword(''); setCpDeleteError('') }} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: '#6b7280' }}>Снять выделение</button>
              </div>
            )}

            {loadingCounterparties ? <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr>
                      {(role === 'admin' || can(permissions, 'counterparties', 'edit')) && (
                        <th style={{ ...cpTh, width: '34px', cursor: 'default' }}>
                          <input type="checkbox" checked={allCpVisibleSelected} onChange={toggleCpSelectAllVisible} />
                        </th>
                      )}
                      <th style={{ ...cpTh, width: '48px' }} onClick={() => handleCpSort('id')}>ID <CpSortIcon col="id" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('name')}>Название <CpSortIcon col="name" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('inn')}>ИНН <CpSortIcon col="inn" /></th>
                      {/* contract_number/contract_date УБРАНЫ из реестра Контрагентов (см. CLAUDE.md,
                          models.py) — ложное 1:1 поле для 1:N связи. Вместо них — кол-во привязанных
                          договоров (Contract.counterparty_id), сами договоры редактируются на вкладке "Договоры". */}
                      <th style={{ ...cpTh, width: '90px' }} title="Кол-во договоров, привязанных к контрагенту" onClick={() => handleCpSort('contracts_count')}>Договоров <CpSortIcon col="contracts_count" /></th>
                      <th style={{ ...cpTh, width: '64px' }} title="Отсрочка, дн." onClick={() => handleCpSort('term_days')}>Отс <CpSortIcon col="term_days" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('relation')}>Статус <CpSortIcon col="relation" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('group')}>Группа <CpSortIcon col="group" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('status')}>Вид <CpSortIcon col="status" /></th>
                      <th style={{ ...cpTh, textAlign: 'right', width: '64px' }} title="Операции" onClick={() => handleCpSort('op_count')}>Опе <CpSortIcon col="op_count" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('receivable')}>Дебиторка <CpSortIcon col="receivable" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('payable')}>Кредиторка <CpSortIcon col="payable" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('income_paid')}>Поступления <CpSortIcon col="income_paid" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('expense_paid')}>Выплаты <CpSortIcon col="expense_paid" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('diff')}>Разница <CpSortIcon col="diff" /></th>
                      <th style={{ ...cpTh, width: '90px' }} title="Дата последней операции" onClick={() => handleCpSort('last_op_date')}>Дат <CpSortIcon col="last_op_date" /></th>
                      <th style={{ ...cpTh, cursor: 'default' }}>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCounterparties.map(c => {
                      const canEdit = role === 'admin' || can(permissions, 'counterparties', 'edit')
                      const isEditing = cpEditingId === c.id
                      const relColor = RELATION_COLORS[c.relation] || { bg: '#f3f4f6', color: '#6b7280' }
                      return (
                        <tr key={c.id} style={{ borderBottom: '1px solid #f3f4f6', background: isEditing ? '#fffbeb' : 'transparent' }}
                          onMouseEnter={e => { if (!isEditing) e.currentTarget.style.background = '#f9fafb' }}
                          onMouseLeave={e => { e.currentTarget.style.background = isEditing ? '#fffbeb' : 'transparent' }}>
                          {canEdit && (
                            <td style={{ padding: '7px 10px' }}>
                              <input type="checkbox" checked={cpSelectedIds.includes(c.id)} onChange={() => toggleCpSelect(c.id)} />
                            </td>
                          )}
                          <td style={{ padding: '7px 10px', color: '#9ca3af' }}>{c.id}</td>
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing
                              ? <input autoFocus value={cpDraft.name} onChange={e => setCpDraft(d => ({ ...d, name: e.target.value }))}
                                  style={{ ...inpLeft, width: '220px', padding: '5px 8px', fontSize: '14px' }} />
                              : c.name}
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing
                              ? <input value={cpDraft.inn} onChange={e => setCpDraft(d => ({ ...d, inn: e.target.value }))}
                                  style={{ ...inpLeft, width: '120px', padding: '5px 8px', fontSize: '14px' }} />
                              : (c.inn || '—')}
                          </td>
                          <td style={{ padding: '7px 10px', textAlign: 'center' }} title="Редактируется на вкладке «Договоры»">
                            {c.contracts_count > 0 ? c.contracts_count : <span style={{ color: '#9ca3af' }}>0</span>}
                          </td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', width: '64px' }}>
                            {isEditing
                              ? <input type="number" min="0" value={cpDraft.term_days} onChange={e => setCpDraft(d => ({ ...d, term_days: e.target.value }))}
                                  placeholder={String(DEFAULT_TERM_DAYS)}
                                  style={{ ...inpLeft, width: '70px', padding: '5px 8px', fontSize: '14px', textAlign: 'right' }} />
                              : (c.term_days_is_default
                                  ? <span style={{ color: '#9ca3af' }} title="Значение по умолчанию">{c.term_days_effective}</span>
                                  : <span title="Задано вручную">{c.term_days_effective}</span>)}
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            {c.relation
                              ? <span style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '20px', whiteSpace: 'nowrap', background: relColor.bg, color: relColor.color }}>{RELATION_LABELS[c.relation]}</span>
                              : <span style={{ color: '#9ca3af' }}>—</span>}
                          </td>
                          <td style={{ padding: '7px 10px', color: '#6b7280', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.group_is_override ? `${c.group} (задано вручную)` : c.group}>
                            {c.group_is_override && <span style={{ color: '#d97706', marginRight: '3px' }}>✎</span>}
                            {c.group || '—'}
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing ? (
                              <select value={cpDraft.status} onChange={e => setCpDraft(d => ({ ...d, status: e.target.value }))} style={{ ...select, padding: '5px 8px', fontSize: '14px' }}>
                                <option value="действующий">Действующий</option>
                                <option value="виртуальный">Виртуальный</option>
                              </select>
                            ) : (
                              <span title={c.status === 'действующий' ? 'Действующий' : 'Виртуальный'}
                                style={{ width: '10px', height: '10px', borderRadius: '50%', background: c.status === 'действующий' ? '#16a34a' : '#2563eb', display: 'inline-block' }} />
                            )}
                          </td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', width: '64px' }}>{c.op_count}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#2563eb', whiteSpace: 'nowrap' }}>{c.receivable > 0 ? fmt(c.receivable) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#d97706', whiteSpace: 'nowrap' }}>{c.payable > 0 ? fmt(c.payable) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#16a34a', whiteSpace: 'nowrap' }}>{c.income_paid > 0 ? fmt(c.income_paid) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#dc2626', whiteSpace: 'nowrap' }}>{c.expense_paid > 0 ? fmt(c.expense_paid) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap', color: c.diff >= 0 ? '#16a34a' : '#dc2626', fontWeight: '500' }}>{fmt(c.diff)}</td>
                          <td style={{ padding: '7px 10px', color: '#6b7280', whiteSpace: 'nowrap', width: '90px' }}>{fmtDate(c.last_op_date)}</td>
                          <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                            {!canEdit ? '—' : isEditing ? (
                              <>
                                <button onClick={() => handleSaveCounterparty(c.id)} disabled={cpSaving} title="Сохранить"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #86efac', background: '#dcfce7', cursor: 'pointer', color: '#16a34a', marginRight: '4px' }}>
                                  {cpSaving ? '...' : '✓'}
                                </button>
                                <button onClick={cancelCpEdit} disabled={cpSaving} title="Отмена"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#6b7280' }}>✕</button>
                                {cpError && <div style={{ color: '#dc2626', fontSize: '13px', marginTop: '4px', maxWidth: '200px' }}>{cpError}</div>}
                              </>
                            ) : (
                              <button onClick={() => openCpEdit(c)} title="Редактировать"
                                style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #fde68a', background: '#fffbeb', cursor: 'pointer', color: '#d97706' }}>✏️</button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'articles' && (
          <div>
            <datalist id="article-groups">
              {articleGroups.map(g => <option key={g} value={g} />)}
            </datalist>

            {/* Форма создания */}
            {(role === 'admin' || can(permissions, 'articles', 'edit')) && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '12px' }}>
                <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Новая статья</div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <input placeholder="Название" value={newArticle.name} onChange={e => setNewArticle(p => ({ ...p, name: e.target.value }))} style={{ ...inpLeft, width: '220px' }} />
                  <input placeholder="Группа (верхний уровень)" list="article-groups" value={newArticle.group} onChange={e => setNewArticle(p => ({ ...p, group: e.target.value }))} style={{ ...inpLeft, width: '200px' }} />
                  <select value={newArticle.type} onChange={e => setNewArticle(p => ({ ...p, type: e.target.value }))} style={select}>
                    <option value="expense">Расход</option>
                    <option value="income">Доход</option>
                  </select>
                  <button onClick={handleCreateArticle} disabled={creatingArticle} style={btn}>{creatingArticle ? '...' : 'Создать'}</button>
                </div>
                {artCreateError && <div style={{ color: '#dc2626', fontSize: '15px', marginTop: '8px' }}>{artCreateError}</div>}
              </div>
            )}

            {/* Фильтр */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              <input placeholder="Поиск по названию или группе" value={artSearch} onChange={e => setArtSearch(e.target.value)} style={{ ...inpLeft, width: '260px' }} />
              {artSearch && <span style={{ fontSize: '13px', color: '#d97706' }}>Очистите поиск, чтобы менять порядок вывода</span>}
              <span style={{ fontSize: '14px', color: '#6b7280', marginLeft: 'auto' }}>{filteredArticles.length} из {articles.length}</span>
            </div>

            {loadingArticles ? <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'auto', maxHeight: 'calc(100vh - 320px)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr>
                      <th style={{ ...cpTh, width: '48px', cursor: 'default' }}>ID</th>
                      <th style={{ ...cpTh, cursor: 'default' }}>Название</th>
                      <th style={{ ...cpTh, cursor: 'default' }}>Группа</th>
                      <th style={{ ...cpTh, cursor: 'default' }}>Тип</th>
                      <th style={{ ...cpTh, textAlign: 'right', cursor: 'default' }}>Операций</th>
                      <th style={{ ...cpTh, textAlign: 'center', cursor: 'default', width: '70px' }}>Порядок</th>
                      <th style={{ ...cpTh, cursor: 'default' }}>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredArticles.map((a, i) => {
                      const canEditArt = role === 'admin' || can(permissions, 'articles', 'edit')
                      const isEditing = artEditingId === a.id
                      const typeMeta = ARTICLE_TYPE_META[a.type] || { label: a.type || '—', bg: '#f3f4f6', color: '#6b7280' }
                      return (
                        <tr key={a.id} style={{ borderBottom: '1px solid #f3f4f6', background: isEditing ? '#fffbeb' : 'transparent' }}
                          onMouseEnter={e => { if (!isEditing) e.currentTarget.style.background = '#f9fafb' }}
                          onMouseLeave={e => { e.currentTarget.style.background = isEditing ? '#fffbeb' : 'transparent' }}>
                          <td style={{ padding: '7px 10px', color: '#9ca3af' }}>{a.id}</td>
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing
                              ? <input autoFocus value={artDraft.name} onChange={e => setArtDraft(d => ({ ...d, name: e.target.value }))}
                                  style={{ ...inpLeft, width: '220px', padding: '5px 8px', fontSize: '14px' }} />
                              : a.name}
                          </td>
                          <td style={{ padding: '7px 10px', color: '#6b7280' }}>
                            {isEditing
                              ? <input list="article-groups" value={artDraft.group} onChange={e => setArtDraft(d => ({ ...d, group: e.target.value }))}
                                  style={{ ...inpLeft, width: '180px', padding: '5px 8px', fontSize: '14px' }} />
                              : (a.group || '—')}
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing ? (
                              <select value={artDraft.type} onChange={e => setArtDraft(d => ({ ...d, type: e.target.value }))} style={{ ...select, padding: '5px 8px', fontSize: '14px' }}>
                                <option value="expense">Расход</option>
                                <option value="income">Доход</option>
                              </select>
                            ) : (
                              <span style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '20px', background: typeMeta.bg, color: typeMeta.color }}>{typeMeta.label}</span>
                            )}
                          </td>
                          <td style={{ padding: '7px 10px', textAlign: 'right' }}>{a.op_count}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                            {canEditArt && !artSearch ? (
                              <>
                                <button onClick={() => handleMoveArticle(a.id, 'up')} disabled={i === 0 || artMovingId === a.id} title="Выше"
                                  style={{ border: 'none', background: 'transparent', cursor: i === 0 ? 'default' : 'pointer', color: i === 0 ? '#d1d5db' : '#6b7280', fontSize: '15px', padding: '2px 4px' }}>▲</button>
                                <button onClick={() => handleMoveArticle(a.id, 'down')} disabled={i === filteredArticles.length - 1 || artMovingId === a.id} title="Ниже"
                                  style={{ border: 'none', background: 'transparent', cursor: i === filteredArticles.length - 1 ? 'default' : 'pointer', color: i === filteredArticles.length - 1 ? '#d1d5db' : '#6b7280', fontSize: '15px', padding: '2px 4px' }}>▼</button>
                              </>
                            ) : <span style={{ color: '#d1d5db' }}>—</span>}
                          </td>
                          <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                            {!canEditArt ? '—' : isEditing ? (
                              <>
                                <button onClick={() => handleSaveArticle(a.id)} disabled={artSaving} title="Сохранить"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #86efac', background: '#dcfce7', cursor: 'pointer', color: '#16a34a', marginRight: '4px' }}>
                                  {artSaving ? '...' : '✓'}
                                </button>
                                <button onClick={cancelArtEdit} disabled={artSaving} title="Отмена"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#6b7280' }}>✕</button>
                                {artError && <div style={{ color: '#dc2626', fontSize: '13px', marginTop: '4px', maxWidth: '200px' }}>{artError}</div>}
                              </>
                            ) : (
                              <>
                                <button onClick={() => openArtEdit(a)} title="Редактировать"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #fde68a', background: '#fffbeb', cursor: 'pointer', color: '#d97706', marginRight: '4px' }}>✏️</button>
                                <button onClick={() => handleDeleteArticle(a)} title="Удалить"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #fca5a5', background: '#fee2e2', cursor: 'pointer', color: '#dc2626' }}>🗑️</button>
                              </>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'contracts' && (
          <div>
            <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              {(role === 'admin' || can(permissions, 'contracts', 'edit')) && (
                <button onClick={() => setShowNewContract(v => !v)} title={showNewContract ? 'Скрыть форму' : 'Добавить договор'}
                  style={{ display: 'flex', alignItems: 'center', gap: '2px', padding: '8px 12px', borderRadius: '8px', border: 'none', background: showNewContract ? '#f3f4f6' : '#2563eb', color: showNewContract ? '#374151' : 'white', cursor: 'pointer', fontSize: '16px', lineHeight: 1 }}>
                  <span>{showNewContract ? '✕' : '+'}</span><span>📄</span>
                </button>
              )}
              <input placeholder="Поиск по № договора, контрагенту, ИНН" value={ctSearch} onChange={e => setCtSearch(e.target.value)} style={{ ...inpLeft, width: '280px' }} />
              <select value={ctFormatFilter} onChange={e => setCtFormatFilter(e.target.value)} style={select}>
                <option value="">Все форматы</option>
                {ctFormatOptions.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <select value={ctProlongationFilter} onChange={e => setCtProlongationFilter(e.target.value)} style={select}>
                <option value="">Все типы пролонгации</option>
                {ctProlongationOptions.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <span style={{ fontSize: '14px', color: '#6b7280', marginLeft: 'auto' }}>{filteredContracts.length} из {contracts.length}</span>
            </div>

            {showNewContract && (role === 'admin' || can(permissions, 'contracts', 'edit')) && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '12px' }}>
                <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Новый договор</div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <div style={{ width: '220px' }}>
                    <CounterpartySearch counterparties={counterparties} value={newContract.counterparty_id}
                      onChange={id => setNewContract(p => ({ ...p, counterparty_id: id }))} onCreateNew={createCounterparty} />
                  </div>
                  <input placeholder="№ договора" value={newContract.contract_number} onChange={e => setNewContract(p => ({ ...p, contract_number: e.target.value }))} style={{ ...inpLeft, width: '140px' }} />
                  <input type="date" value={newContract.contract_date} onChange={e => setNewContract(p => ({ ...p, contract_date: e.target.value }))} style={{ ...inpLeft, width: '150px' }} />
                  <input placeholder="Название маркетинговое" value={newContract.marketing_name} onChange={e => setNewContract(p => ({ ...p, marketing_name: e.target.value }))} style={{ ...inpLeft, width: '200px' }} />
                </div>
                {/* ИНН больше не вводится вручную — выводится из реестра контрагентов
                    (Counterparty.inn) по выбранному counterparty_id, см. contracts.py _resolve_counterparty. */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginTop: '8px' }}>
                  <SelectWithOther value={newContract.cooperation_format} options={COOPERATION_FORMATS} emptyLabel="Формат сотрудничества"
                    onChange={e => setNewContract(p => ({ ...p, cooperation_format: e.target.value }))} style={{ ...select, width: '190px' }} />
                  <input placeholder="Дата окончания" value={newContract.end_date_text} onChange={e => setNewContract(p => ({ ...p, end_date_text: e.target.value }))} style={{ ...inpLeft, width: '150px' }} />
                  <SelectWithOther value={newContract.prolongation} options={PROLONGATION_OPTIONS} emptyLabel="Пролонгация"
                    onChange={e => setNewContract(p => ({ ...p, prolongation: e.target.value }))} style={{ ...select, width: '170px' }} />
                  <input type="number" min="0" placeholder="Срок оплаты, дни" value={newContract.payment_term_days} onChange={e => setNewContract(p => ({ ...p, payment_term_days: e.target.value }))} style={{ ...inp, width: '140px' }} />
                  <SelectWithLegacy value={newContract.payment_term_condition} options={PAYMENT_TERM_CONDITIONS} emptyLabel="Условие"
                    onChange={e => setNewContract(p => ({ ...p, payment_term_condition: e.target.value }))} style={{ ...select, width: '170px' }} />
                  <button onClick={handleCreateContract} disabled={creatingContract} style={btn}>{creatingContract ? '...' : 'Создать'}</button>
                </div>
                {ctCreateError && <div style={{ color: '#dc2626', fontSize: '15px', marginTop: '8px' }}>{ctCreateError}</div>}
              </div>
            )}

            {(role === 'admin' || can(permissions, 'contracts', 'edit')) && ctSelectedIds.length > 0 && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '14px 20px', marginBottom: '12px', border: '2px solid #2563eb', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ fontSize: '15px', fontWeight: '500', color: '#2563eb', marginRight: '4px', alignSelf: 'center' }}>Выбрано: {ctSelectedIds.length}</div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Формат сотрудничества</div>
                  <SelectWithOther value={ctBulkFormat} options={COOPERATION_FORMATS} emptyLabel="— не менять —"
                    onChange={e => setCtBulkFormat(e.target.value)} style={{ ...select, width: '190px' }} />
                </div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Пролонгация</div>
                  <SelectWithOther value={ctBulkProlongation} options={PROLONGATION_OPTIONS} emptyLabel="— не менять —"
                    onChange={e => setCtBulkProlongation(e.target.value)} style={{ ...select, width: '170px' }} />
                </div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Срок оплаты, дни</div>
                  <input type="number" min="0" placeholder="— не менять —" value={ctBulkPaymentDays} onChange={e => setCtBulkPaymentDays(e.target.value)} style={{ ...inp, width: '140px' }} />
                </div>
                <div><div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '3px' }}>Условие</div>
                  <SelectWithLegacy value={ctBulkPaymentCondition} options={PAYMENT_TERM_CONDITIONS} emptyLabel="— не менять —"
                    onChange={e => setCtBulkPaymentCondition(e.target.value)} style={{ ...select, width: '170px' }} />
                </div>
                <button onClick={handleCtBulkApply} disabled={ctBulkSaving} style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: 'pointer', fontSize: '15px' }}>
                  {ctBulkSaving ? 'Сохранение...' : `Применить к ${ctSelectedIds.length}`}
                </button>
                {role === 'admin' && (
                  <button onClick={handleCtBulkDelete} disabled={ctBulkSaving} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #fca5a5', background: '#fee2e2', color: '#dc2626', cursor: 'pointer', fontSize: '15px' }}>
                    {ctBulkSaving ? '...' : `Удалить ${ctSelectedIds.length}`}
                  </button>
                )}
                <button onClick={() => { setCtSelectedIds([]); setCtBulkFormat(''); setCtBulkProlongation(''); setCtBulkPaymentDays(''); setCtBulkPaymentCondition('') }} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: '#6b7280' }}>Снять выделение</button>
              </div>
            )}

            {loadingContracts ? <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'auto', maxHeight: 'calc(100vh - 320px)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr>
                      {(role === 'admin' || can(permissions, 'contracts', 'edit')) && (
                        <th style={{ ...ctTh, width: '34px', cursor: 'default' }}>
                          <input type="checkbox" checked={allCtVisibleSelected} onChange={toggleCtSelectAllVisible} />
                        </th>
                      )}
                      <th style={{ ...ctTh, width: '48px' }} onClick={() => handleCtSort('id')}>ID <CtSortIcon col="id" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('counterparty_name')}>Контрагент <CtSortIcon col="counterparty_name" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('contract_number')}>№ договора <CtSortIcon col="contract_number" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('contract_date')}>Дата договора <CtSortIcon col="contract_date" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('inn')}>ИНН <CtSortIcon col="inn" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('marketing_name')}>Маркетинговое название <CtSortIcon col="marketing_name" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('cooperation_format')}>Формат сотрудничества <CtSortIcon col="cooperation_format" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('end_date_text')}>Дата окончания <CtSortIcon col="end_date_text" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('prolongation')}>Пролонгация <CtSortIcon col="prolongation" /></th>
                      <th style={{ ...ctTh, textAlign: 'right' }} onClick={() => handleCtSort('payment_term_days')}>Срок оплаты, дни <CtSortIcon col="payment_term_days" /></th>
                      <th style={ctTh} onClick={() => handleCtSort('payment_term_condition')}>Условие <CtSortIcon col="payment_term_condition" /></th>
                      <th style={{ ...ctTh, cursor: 'default' }}>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredContracts.map(c => {
                      const canEditCt = role === 'admin' || can(permissions, 'contracts', 'edit')
                      const isEditing = ctEditingId === c.id
                      const w = (px) => ({ ...inpLeft, width: px, padding: '5px 8px', fontSize: '14px' })
                      const sw = (px) => ({ ...select, width: px, padding: '5px 8px', fontSize: '14px' })
                      return (
                        <tr key={c.id} style={{ borderBottom: '1px solid #f3f4f6', background: isEditing ? '#fffbeb' : 'transparent' }}
                          onMouseEnter={e => { if (!isEditing) e.currentTarget.style.background = '#f9fafb' }}
                          onMouseLeave={e => { e.currentTarget.style.background = isEditing ? '#fffbeb' : 'transparent' }}>
                          {canEditCt && (
                            <td style={{ padding: '7px 10px' }}>
                              <input type="checkbox" checked={ctSelectedIds.includes(c.id)} onChange={() => toggleCtSelect(c.id)} />
                            </td>
                          )}
                          <td style={{ padding: '7px 10px', color: '#9ca3af' }}>{c.id}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing
                            ? <div style={{ width: '200px' }}><CounterpartySearch counterparties={counterparties} value={ctDraft.counterparty_id} onChange={id => setCtDraft(d => ({ ...d, counterparty_id: id }))} onCreateNew={createCounterparty} /></div>
                            : <>{c.counterparty_name || '—'}{!c.linked && <span title="Не привязан к реестру контрагентов — старая запись" style={{ marginLeft: '5px', color: '#d97706' }}>⚠</span>}</>}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing ? <input value={ctDraft.contract_number || ''} onChange={e => setCtDraft(d => ({ ...d, contract_number: e.target.value }))} style={w('110px')} /> : (c.contract_number || '—')}</td>
                          <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{isEditing ? <input type="date" value={ctDraft.contract_date || ''} onChange={e => setCtDraft(d => ({ ...d, contract_date: e.target.value }))} style={w('130px')} /> : fmtDate(c.contract_date)}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing
                            ? (ctDraft.counterparty_id
                              ? <span style={{ color: '#9ca3af' }}>{(counterparties.find(cp => cp.id === ctDraft.counterparty_id) || {}).inn || '—'}</span>
                              : <input value={ctDraft.inn || ''} onChange={e => setCtDraft(d => ({ ...d, inn: e.target.value }))} style={w('110px')} />)
                            : (c.inn || '—')}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing ? <input value={ctDraft.marketing_name || ''} onChange={e => setCtDraft(d => ({ ...d, marketing_name: e.target.value }))} style={w('180px')} /> : (c.marketing_name || '—')}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing
                            ? <SelectWithOther value={ctDraft.cooperation_format} options={COOPERATION_FORMATS} onChange={e => setCtDraft(d => ({ ...d, cooperation_format: e.target.value }))} style={sw('170px')} />
                            : (c.cooperation_format || '—')}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing ? <input value={ctDraft.end_date_text || ''} onChange={e => setCtDraft(d => ({ ...d, end_date_text: e.target.value }))} style={w('140px')} /> : (c.end_date_text || '—')}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing
                            ? <SelectWithOther value={ctDraft.prolongation} options={PROLONGATION_OPTIONS} onChange={e => setCtDraft(d => ({ ...d, prolongation: e.target.value }))} style={sw('160px')} />
                            : (c.prolongation || '—')}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right' }}>{isEditing
                            ? <input type="number" min="0" value={ctDraft.payment_term_days} onChange={e => setCtDraft(d => ({ ...d, payment_term_days: e.target.value }))} style={{ ...w('80px'), textAlign: 'right' }} />
                            : (c.payment_term_days != null ? c.payment_term_days : '—')}</td>
                          <td style={{ padding: '7px 10px' }}>{isEditing
                            ? <SelectWithLegacy value={ctDraft.payment_term_condition} options={PAYMENT_TERM_CONDITIONS} onChange={e => setCtDraft(d => ({ ...d, payment_term_condition: e.target.value }))} style={sw('170px')} />
                            : (c.payment_term_condition || '—')}</td>
                          <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                            {!canEditCt ? '—' : isEditing ? (
                              <>
                                <button onClick={() => handleSaveContract(c.id)} disabled={ctSaving} title="Сохранить"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #86efac', background: '#dcfce7', cursor: 'pointer', color: '#16a34a', marginRight: '4px' }}>
                                  {ctSaving ? '...' : '✓'}
                                </button>
                                <button onClick={cancelCtEdit} disabled={ctSaving} title="Отмена"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#6b7280' }}>✕</button>
                                {ctError && <div style={{ color: '#dc2626', fontSize: '13px', marginTop: '4px', maxWidth: '200px' }}>{ctError}</div>}
                              </>
                            ) : (
                              <>
                                <button onClick={() => openCtEdit(c)} title="Редактировать"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #fde68a', background: '#fffbeb', cursor: 'pointer', color: '#d97706', marginRight: '4px' }}>✏️</button>
                                <button onClick={() => handleDeleteContract(c)} title="Удалить"
                                  style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '6px', border: '1px solid #fca5a5', background: '#fee2e2', cursor: 'pointer', color: '#dc2626' }}>🗑️</button>
                              </>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
