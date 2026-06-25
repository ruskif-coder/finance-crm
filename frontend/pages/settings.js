import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Navbar from '../components/Navbar'

const api = (token) => axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtDateTime = (s) => s ? new Date(s).toLocaleString('ru-RU') : ''
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'

const BANK_STYLES = {
  'АльфаБанк':  { bg: '#fee2e2', color: '#dc2626', border: '#fca5a5' },
  'ОПТ Банк':   { bg: '#dcfce7', color: '#16a34a', border: '#86efac' },
  'Совкомбанк': { bg: '#f3f4f6', color: '#4b5563', border: '#d1d5db' },
  'Наличные':   { bg: '#dbeafe', color: '#2563eb', border: '#93c5fd' },
}

const ACTION_LABELS_RU = { view: 'Просмотр', create: 'Создание', edit: 'Редактирование', delete: 'Удаление' }

// Должно совпадать с DEFAULT_TERM_DAYS в backend/app/routers/reports.py — используется
// только как плейсхолдер/подсказка в поле "Отсрочка", фактическое значение всегда приходит с backend.
const DEFAULT_TERM_DAYS = 60

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

export default function Settings() {
  const router = useRouter()
  const [tab, setTab] = useState('balances')
  const [role, setRole] = useState('')
  const [permissions, setPermissions] = useState({})
  const [selfId, setSelfId] = useState(null)

  // Роли и права доступа
  const [allRoles, setAllRoles] = useState([])
  const [sections, setSections] = useState([])
  const [loadingRoles, setLoadingRoles] = useState(false)
  const [editingRolePerms, setEditingRolePerms] = useState({})
  const [roleLabels, setRoleLabels] = useState({})
  const [savingRole, setSavingRole] = useState({})
  const [newRoleLabel, setNewRoleLabel] = useState('')
  const [creatingRole, setCreatingRole] = useState(false)
  const [roleError, setRoleError] = useState('')

  // Остатки по банкам
  const [banks, setBanks] = useState([])
  const [totalBalance, setTotalBalance] = useState(0)
  const [editing, setEditing] = useState({})
  const [saving, setSaving] = useState({})
  const [loading, setLoading] = useState(true)

  // Пользователи
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [editingUsers, setEditingUsers] = useState({})
  const [savingUsers, setSavingUsers] = useState({})
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '', role: 'viewer' })
  const [creatingUser, setCreatingUser] = useState(false)
  const [userError, setUserError] = useState('')

  // Контрагенты (справочник)
  const [counterparties, setCounterparties] = useState([])
  const [loadingCounterparties, setLoadingCounterparties] = useState(false)
  const [cpEditingId, setCpEditingId] = useState(null)
  const [cpDraft, setCpDraft] = useState({ name: '', inn: '', status: 'действующий', contract_number: '', contract_date: '', term_days: '' })
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

  // Журнал действий
  const [auditItems, setAuditItems] = useState([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [actionLabels, setActionLabels] = useState({})
  const [auditFilters, setAuditFilters] = useState({ action: '', user_id: '', date_from: '', date_to: '' })
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [auditSkip, setAuditSkip] = useState(0)
  const AUDIT_LIMIT = 50

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    const r = localStorage.getItem('role') || ''
    const perms = getPermissions()
    if (r !== 'admin' && !can(perms, 'settings_balances', 'view') && !can(perms, 'counterparties', 'view') && !can(perms, 'articles', 'view')) { router.push('/dashboard'); return }
    setRole(r)
    setPermissions(perms)
    loadBalances(token)
    api(token).get('/auth/me').then(res => setSelfId(res.data.id)).catch(() => {})
    if (r === 'admin') loadRoles(token)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    if (tab === 'users') loadUsers(token)
    if (tab === 'audit') loadAuditLog(token, 0, auditFilters)
    if (tab === 'roles') loadRoles(token)
    if (tab === 'counterparties') loadCounterparties(token)
    if (tab === 'articles') loadArticles(token)
  }, [tab])

  const loadBalances = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get('/settings/bank-balances')
      setBanks(res.data.banks)
      setTotalBalance(res.data.total_balance)
      const ed = {}
      res.data.banks.forEach(b => { ed[b.bank] = b.opening_balance })
      setEditing(ed)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (bank) => {
    const token = localStorage.getItem('token')
    setSaving(prev => ({ ...prev, [bank]: true }))
    try {
      await api(token).post('/settings/bank-balances', {
        bank,
        opening_balance: parseFloat(editing[bank]) || 0
      })
      await loadBalances(token)
    } catch (e) {
      alert('Ошибка при сохранении')
    } finally {
      setSaving(prev => ({ ...prev, [bank]: false }))
    }
  }

  // ---------- Пользователи ----------

  const loadUsers = async (token) => {
    setLoadingUsers(true)
    try {
      const res = await api(token).get('/users/')
      setUsers(res.data)
      const ed = {}
      res.data.forEach(u => { ed[u.id] = { role: u.role, is_active: u.is_active, password: '' } })
      setEditingUsers(ed)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingUsers(false)
    }
  }

  const handleCreateUser = async () => {
    setUserError('')
    if (!newUser.name || !newUser.email || !newUser.password) {
      setUserError('Заполните имя, email и пароль'); return
    }
    const token = localStorage.getItem('token')
    setCreatingUser(true)
    try {
      await api(token).post('/users/', newUser)
      setNewUser({ name: '', email: '', password: '', role: 'viewer' })
      await loadUsers(token)
    } catch (e) {
      setUserError(e.response?.data?.detail || 'Ошибка при создании')
    } finally {
      setCreatingUser(false)
    }
  }

  const handleSaveUser = async (id) => {
    const token = localStorage.getItem('token')
    const ed = editingUsers[id]
    setSavingUsers(prev => ({ ...prev, [id]: true }))
    try {
      const payload = { role: ed.role, is_active: ed.is_active }
      if (ed.password) payload.password = ed.password
      await api(token).put(`/users/${id}`, payload)
      await loadUsers(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setSavingUsers(prev => ({ ...prev, [id]: false }))
    }
  }

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
    setCpDraft({ name: c.name, inn: c.inn || '', status: c.status, contract_number: c.contract_number || '', contract_date: c.contract_date || '', term_days: c.term_days != null ? String(c.term_days) : '' })
    setCpError('')
  }

  const cancelCpEdit = () => { setCpEditingId(null); setCpError('') }

  const handleSaveCounterparty = async (id) => {
    const token = localStorage.getItem('token')
    setCpSaving(true)
    setCpError('')
    try {
      await api(token).put(`/counterparties/${id}/registry`, { name: cpDraft.name, inn: cpDraft.inn, status: cpDraft.status, contract_number: cpDraft.contract_number, contract_date: cpDraft.contract_date || null, term_days: cpDraft.term_days !== '' ? parseInt(cpDraft.term_days, 10) : null })
      await loadCounterparties(token)
      setCpEditingId(null)
    } catch (e) {
      setCpError(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setCpSaving(false)
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

  // ---------- Журнал действий ----------

  const loadAuditLog = async (token, skip, filters) => {
    setLoadingAudit(true)
    try {
      const params = { skip, limit: AUDIT_LIMIT }
      if (filters.action) params.action = filters.action
      if (filters.user_id) params.user_id = filters.user_id
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const res = await api(token).get('/users/audit-log/', { params })
      if (skip === 0) setAuditItems(res.data.items)
      else setAuditItems(prev => [...prev, ...res.data.items])
      setAuditTotal(res.data.total)
      setActionLabels(res.data.actions)
      setAuditSkip(skip)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingAudit(false)
    }
  }

  const handleAuditFilterChange = (patch) => {
    const next = { ...auditFilters, ...patch }
    setAuditFilters(next)
    const token = localStorage.getItem('token')
    loadAuditLog(token, 0, next)
  }

  // ---------- Роли и права доступа ----------

  const loadRoles = async (token) => {
    setLoadingRoles(true)
    try {
      const res = await api(token).get('/roles/')
      setAllRoles(res.data.roles)
      setSections(res.data.sections)
      const draft = {}
      const labels = {}
      res.data.roles.forEach(r => {
        draft[r.id] = JSON.parse(JSON.stringify(r.permissions))
        labels[r.id] = r.label
      })
      setEditingRolePerms(draft)
      setRoleLabels(labels)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingRoles(false)
    }
  }

  const togglePerm = (roleId, section, action) => {
    setEditingRolePerms(prev => ({
      ...prev,
      [roleId]: {
        ...prev[roleId],
        [section]: { ...prev[roleId]?.[section], [action]: !prev[roleId]?.[section]?.[action] }
      }
    }))
  }

  const handleCreateRole = async () => {
    setRoleError('')
    if (!newRoleLabel.trim()) { setRoleError('Введите название роли'); return }
    const token = localStorage.getItem('token')
    setCreatingRole(true)
    try {
      await api(token).post('/roles/', { label: newRoleLabel.trim() })
      setNewRoleLabel('')
      await loadRoles(token)
    } catch (e) {
      setRoleError(e.response?.data?.detail || 'Ошибка при создании роли')
    } finally {
      setCreatingRole(false)
    }
  }

  const handleSaveRole = async (roleId) => {
    const token = localStorage.getItem('token')
    setSavingRole(prev => ({ ...prev, [roleId]: true }))
    try {
      const draft = editingRolePerms[roleId] || {}
      const permissions = sections.map(s => ({
        section: s.key,
        can_view: s.actions.includes('view') ? !!draft[s.key]?.view : undefined,
        can_create: s.actions.includes('create') ? !!draft[s.key]?.create : undefined,
        can_edit: s.actions.includes('edit') ? !!draft[s.key]?.edit : undefined,
        can_delete: s.actions.includes('delete') ? !!draft[s.key]?.delete : undefined,
      }))
      await api(token).put(`/roles/${roleId}`, { label: roleLabels[roleId], permissions })
      await loadRoles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении роли')
    } finally {
      setSavingRole(prev => ({ ...prev, [roleId]: false }))
    }
  }

  const handleDeleteRole = async (roleId) => {
    if (!confirm('Удалить роль?')) return
    const token = localStorage.getItem('token')
    try {
      await api(token).delete(`/roles/${roleId}`)
      await loadRoles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при удалении роли')
    }
  }

  const buildPermissionBlocks = (secs) => {
    const blocks = []
    let i = 0
    while (i < secs.length) {
      const g = secs[i].group
      const items = [secs[i]]
      i++
      if (g) {
        while (i < secs.length && secs[i].group === g) { items.push(secs[i]); i++ }
      }
      blocks.push({ group: g, items })
    }
    return blocks
  }

  const inp = { width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none', textAlign: 'right' }
  const inpLeft = { ...inp, textAlign: 'left' }
  const select = { padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none' }
  const btn = { padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: 'pointer', fontSize: '15px', whiteSpace: 'nowrap' }
  const th = { textAlign: 'left', padding: '8px 12px', fontSize: '13px', color: '#6b7280', fontWeight: '500', borderBottom: '1px solid #e5e7eb' }
  const td = { padding: '10px 12px', fontSize: '15px', borderBottom: '1px solid #f3f4f6' }

  // Сортируемый заголовок таблицы контрагентов — визуально как в /operations (липкая шапка, стрелка сортировки)
  const cpTh = { textAlign: 'left', padding: '8px 10px', color: '#6b7280', fontWeight: '500', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none', borderBottom: '2px solid #e5e7eb', background: '#f9fafb', position: 'sticky', top: 0, zIndex: 10, fontSize: '14px' }
  const CpSortIcon = ({ col }) => cpSortCol !== col ? <span style={{ color: '#d1d5db', marginLeft: '4px' }}>↕</span> : <span style={{ color: '#2563eb', marginLeft: '4px' }}>{cpSortDir === 'asc' ? '↑' : '↓'}</span>

  const tabs = []
  if (role === 'admin' || can(permissions, 'settings_balances', 'view')) {
    tabs.push({ id: 'balances', label: 'Остатки по банкам' })
  }
  if (role === 'admin' || can(permissions, 'counterparties', 'view')) {
    tabs.push({ id: 'counterparties', label: 'Контрагенты' })
  }
  if (role === 'admin' || can(permissions, 'articles', 'view')) {
    tabs.push({ id: 'articles', label: 'Статьи' })
  }
  if (role === 'admin') {
    tabs.push({ id: 'users', label: 'Пользователи' })
    tabs.push({ id: 'audit', label: 'Журнал действий' })
    tabs.push({ id: 'roles', label: 'Роли' })
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Navbar active="settings" />

      <div style={{ padding: '24px', maxWidth: 1920, margin: '0 auto' }}>

        {/* Вкладки */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ padding: '8px 20px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '16px', background: tab === t.id ? '#2563eb' : 'white', color: tab === t.id ? 'white' : '#374151' }}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'balances' && (
          <div>
            {/* Итоговая карточка */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>Общий остаток по всем счетам</div>
                <div style={{ fontSize: '30px', fontWeight: '700', color: totalBalance >= 0 ? '#16a34a' : '#dc2626' }}>{fmt(totalBalance)} ₽</div>
              </div>
              <div style={{ fontSize: '14px', color: '#6b7280', textAlign: 'right' }}>
                <div>Стартовый остаток + поступления − списания</div>
                <div style={{ marginTop: '4px' }}>по всем банкам (только оплаченные)</div>
              </div>
            </div>

            {loading ? <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {banks.map(b => {
                  const style = BANK_STYLES[b.bank] || { bg: '#f3f4f6', color: '#4b5563', border: '#d1d5db' }
                  return (
                    <div key={b.bank} style={{ background: 'white', borderRadius: '12px', padding: '20px', borderLeft: `4px solid ${style.border}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '20px', flexWrap: 'wrap' }}>

                        {/* Название банка */}
                        <div style={{ minWidth: '120px' }}>
                          <span style={{ fontSize: '14px', padding: '3px 10px', borderRadius: '20px', background: style.bg, color: style.color, border: `1px solid ${style.border}`, fontWeight: '500' }}>
                            {b.bank}
                          </span>
                        </div>

                        {/* Стартовый остаток — редактируемый */}
                        <div style={{ flex: 1, minWidth: '180px' }}>
                          <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Стартовый остаток</div>
                          {(role === 'admin' || can(permissions, 'settings_balances', 'edit')) ? (
                            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                              <input
                                type="number"
                                value={editing[b.bank] ?? b.opening_balance}
                                onChange={e => setEditing(prev => ({ ...prev, [b.bank]: e.target.value }))}
                                style={inp}
                              />
                              <button
                                onClick={() => handleSave(b.bank)}
                                disabled={saving[b.bank]}
                                style={btn}>
                                {saving[b.bank] ? '...' : 'Сохранить'}
                              </button>
                            </div>
                          ) : (
                            <div style={{ fontSize: '18px', fontWeight: '500' }}>{fmt(b.opening_balance)} ₽</div>
                          )}
                        </div>

                        {/* Обороты */}
                        <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                          <div>
                            <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Поступило</div>
                            <div style={{ fontSize: '18px', fontWeight: '500', color: '#16a34a' }}>{fmt(b.total_income)}</div>
                          </div>
                          <div>
                            <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Списано</div>
                            <div style={{ fontSize: '18px', fontWeight: '500', color: '#dc2626' }}>{fmt(b.total_expense)}</div>
                          </div>
                          <div>
                            <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Текущий остаток</div>
                            <div style={{ fontSize: '20px', fontWeight: '700', color: b.balance >= 0 ? '#16a34a' : '#dc2626' }}>{fmt(b.balance)} ₽</div>
                          </div>
                        </div>

                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

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
              <span style={{ fontSize: '14px', color: '#6b7280', marginLeft: 'auto' }}>{filteredCounterparties.length} из {counterparties.length}</span>
            </div>

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
                <button onClick={() => { setCpSelectedIds([]); setCpBulkStatus(''); setCpBulkGroup('') }} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', fontSize: '15px', color: '#6b7280' }}>Снять выделение</button>
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
                      <th style={cpTh} onClick={() => handleCpSort('contract_number')}>№ договора <CpSortIcon col="contract_number" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('contract_date')}>Дата договора <CpSortIcon col="contract_date" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('term_days')}>Отсрочка, дн. <CpSortIcon col="term_days" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('relation')}>Статус <CpSortIcon col="relation" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('group')}>Группа <CpSortIcon col="group" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('status')}>Вид <CpSortIcon col="status" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('op_count')}>Операции <CpSortIcon col="op_count" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('receivable')}>Дебиторка <CpSortIcon col="receivable" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('payable')}>Кредиторка <CpSortIcon col="payable" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('income_paid')}>Поступления <CpSortIcon col="income_paid" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('expense_paid')}>Выплаты <CpSortIcon col="expense_paid" /></th>
                      <th style={{ ...cpTh, textAlign: 'right' }} onClick={() => handleCpSort('diff')}>Разница <CpSortIcon col="diff" /></th>
                      <th style={cpTh} onClick={() => handleCpSort('last_op_date')}>Дата последней операции <CpSortIcon col="last_op_date" /></th>
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
                          <td style={{ padding: '7px 10px' }}>
                            {isEditing
                              ? <input value={cpDraft.contract_number} onChange={e => setCpDraft(d => ({ ...d, contract_number: e.target.value }))}
                                  style={{ ...inpLeft, width: '110px', padding: '5px 8px', fontSize: '14px' }} />
                              : (c.contract_number || '—')}
                          </td>
                          <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                            {isEditing
                              ? <input type="date" value={cpDraft.contract_date} onChange={e => setCpDraft(d => ({ ...d, contract_date: e.target.value }))}
                                  style={{ ...inpLeft, width: '120px', padding: '5px 8px', fontSize: '14px' }} />
                              : fmtDate(c.contract_date)}
                          </td>
                          <td style={{ padding: '7px 10px', textAlign: 'right' }}>
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
                          <td style={{ padding: '7px 10px', textAlign: 'right' }}>{c.op_count}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#2563eb', whiteSpace: 'nowrap' }}>{c.receivable > 0 ? fmt(c.receivable) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#d97706', whiteSpace: 'nowrap' }}>{c.payable > 0 ? fmt(c.payable) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#16a34a', whiteSpace: 'nowrap' }}>{c.income_paid > 0 ? fmt(c.income_paid) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', color: '#dc2626', whiteSpace: 'nowrap' }}>{c.expense_paid > 0 ? fmt(c.expense_paid) : '—'}</td>
                          <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap', color: c.diff >= 0 ? '#16a34a' : '#dc2626', fontWeight: '500' }}>{fmt(c.diff)}</td>
                          <td style={{ padding: '7px 10px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDate(c.last_op_date)}</td>
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

        {tab === 'users' && (
          <div>
            {/* Форма создания */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '20px' }}>
              <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Новый пользователь</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                <input placeholder="Имя" value={newUser.name} onChange={e => setNewUser(p => ({ ...p, name: e.target.value }))} style={{ ...inpLeft, width: '160px' }} />
                <input placeholder="Email" value={newUser.email} onChange={e => setNewUser(p => ({ ...p, email: e.target.value }))} style={{ ...inpLeft, width: '200px' }} />
                <input placeholder="Пароль" type="password" value={newUser.password} onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))} style={{ ...inpLeft, width: '160px' }} />
                <select value={newUser.role} onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))} style={select}>
                  {allRoles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                </select>
                <button onClick={handleCreateUser} disabled={creatingUser} style={btn}>{creatingUser ? '...' : 'Создать'}</button>
              </div>
              {userError && <div style={{ color: '#dc2626', fontSize: '15px', marginTop: '8px' }}>{userError}</div>}
            </div>

            {/* Таблица пользователей */}
            {loadingUsers ? <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ background: 'white', borderRadius: '12px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={th}>Имя</th>
                      <th style={th}>Email</th>
                      <th style={th}>Роль</th>
                      <th style={th}>Активен</th>
                      <th style={th}>Новый пароль</th>
                      <th style={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => {
                      const ed = editingUsers[u.id] || { role: u.role, is_active: u.is_active, password: '' }
                      const isSelf = u.id === selfId
                      return (
                        <tr key={u.id}>
                          <td style={td}>{u.name}</td>
                          <td style={td}>{u.email}</td>
                          <td style={td}>
                            <select disabled={isSelf} value={ed.role}
                              onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, role: e.target.value } }))}
                              style={select}>
                              {allRoles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                            </select>
                          </td>
                          <td style={td}>
                            <button
                              disabled={isSelf}
                              onClick={() => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, is_active: !ed.is_active } }))}
                              style={{ padding: '4px 12px', borderRadius: '20px', border: 'none', cursor: isSelf ? 'default' : 'pointer', fontSize: '14px', fontWeight: '500', background: ed.is_active ? '#dcfce7' : '#fee2e2', color: ed.is_active ? '#16a34a' : '#dc2626' }}>
                              {ed.is_active ? 'Активен' : 'Деактивирован'}
                            </button>
                          </td>
                          <td style={td}>
                            <input type="password" placeholder="не менять" value={ed.password}
                              onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, password: e.target.value } }))}
                              style={{ ...inpLeft, width: '140px', padding: '6px 10px' }} />
                          </td>
                          <td style={td}>
                            <button onClick={() => handleSaveUser(u.id)} disabled={savingUsers[u.id]} style={btn}>
                              {savingUsers[u.id] ? '...' : 'Сохранить'}
                            </button>
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

        {tab === 'audit' && (
          <div>
            {/* Фильтры */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '16px', marginBottom: '20px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              <select value={auditFilters.action} onChange={e => handleAuditFilterChange({ action: e.target.value })} style={select}>
                <option value="">Все действия</option>
                {Object.entries(actionLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <select value={auditFilters.user_id} onChange={e => handleAuditFilterChange({ user_id: e.target.value })} style={select}>
                <option value="">Все пользователи</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
              <input type="date" value={auditFilters.date_from} onChange={e => handleAuditFilterChange({ date_from: e.target.value })} style={select} />
              <span style={{ color: '#9ca3af' }}>—</span>
              <input type="date" value={auditFilters.date_to} onChange={e => handleAuditFilterChange({ date_to: e.target.value })} style={select} />
              <span style={{ fontSize: '14px', color: '#6b7280', marginLeft: 'auto' }}>{fmt(auditTotal)} записей</span>
            </div>

            <div style={{ background: 'white', borderRadius: '12px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={th}>Дата и время</th>
                    <th style={th}>Пользователь</th>
                    <th style={th}>Действие</th>
                    <th style={th}>Детали</th>
                  </tr>
                </thead>
                <tbody>
                  {auditItems.map(a => (
                    <tr key={a.id}>
                      <td style={{ ...td, whiteSpace: 'nowrap', color: '#6b7280' }}>{fmtDateTime(a.created_at)}</td>
                      <td style={td}>{a.user_name || '—'}</td>
                      <td style={td}>
                        <span style={{ fontSize: '14px', padding: '3px 10px', borderRadius: '20px', background: a.action.includes('failed') ? '#fee2e2' : a.action.includes('delete') ? '#fef3c7' : '#f3f4f6', color: a.action.includes('failed') ? '#dc2626' : '#374151' }}>
                          {a.action_label}
                        </span>
                      </td>
                      <td style={{ ...td, color: '#6b7280' }}>{a.details || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {loadingAudit && <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>Загрузка...</div>}
              {!loadingAudit && auditItems.length < auditTotal && (
                <div style={{ textAlign: 'center', padding: '16px' }}>
                  <button onClick={() => { const token = localStorage.getItem('token'); loadAuditLog(token, auditSkip + AUDIT_LIMIT, auditFilters) }}
                    style={{ ...btn, background: 'white', color: '#2563eb', border: '1px solid #2563eb' }}>
                    Показать ещё
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'roles' && (
          <div>
            {/* Создание роли */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '20px', marginBottom: '20px' }}>
              <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Новая роль</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                <input placeholder="Название роли" value={newRoleLabel} onChange={e => setNewRoleLabel(e.target.value)} style={{ ...inpLeft, width: '240px' }} />
                <button onClick={handleCreateRole} disabled={creatingRole} style={btn}>{creatingRole ? '...' : 'Создать'}</button>
              </div>
              {roleError && <div style={{ color: '#dc2626', fontSize: '15px', marginTop: '8px' }}>{roleError}</div>}
            </div>

            {loadingRoles ? <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Загрузка...</div> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {allRoles.map(r => {
                  const isAdmin = r.key === 'admin'
                  return (
                    <div key={r.id} style={{ background: 'white', borderRadius: '12px', padding: '20px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: isAdmin ? 0 : '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, minWidth: '200px' }}>
                          {isAdmin ? (
                            <div style={{ fontSize: '17px', fontWeight: '600' }}>{r.label}</div>
                          ) : (
                            <input value={roleLabels[r.id] ?? r.label}
                              onChange={e => setRoleLabels(prev => ({ ...prev, [r.id]: e.target.value }))}
                              style={{ ...inpLeft, maxWidth: '240px', fontWeight: '600' }} />
                          )}
                          {!!r.is_system && (
                            <span style={{ fontSize: '13px', padding: '2px 8px', borderRadius: '20px', background: '#f3f4f6', color: '#6b7280' }}>системная</span>
                          )}
                          <span style={{ fontSize: '13px', color: '#9ca3af' }}>{r.user_count} {r.user_count === 1 ? 'пользователь' : 'пользователей'}</span>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          {!isAdmin && (
                            <button onClick={() => handleSaveRole(r.id)} disabled={savingRole[r.id]} style={btn}>
                              {savingRole[r.id] ? '...' : 'Сохранить'}
                            </button>
                          )}
                          {!r.is_system && (
                            <button onClick={() => handleDeleteRole(r.id)}
                              style={{ ...btn, background: '#fee2e2', color: '#dc2626' }}>
                              Удалить
                            </button>
                          )}
                        </div>
                      </div>

                      {isAdmin ? (
                        <div style={{ fontSize: '15px', color: '#6b7280' }}>Полный доступ ко всем разделам и действиям — не настраивается.</div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '4px' }}>
                          {buildPermissionBlocks(sections).map((block, bi) => (
                            <div key={bi} style={{ border: '1px solid #f3f4f6', borderRadius: '10px', padding: '10px 14px' }}>
                              {block.group && (
                                <div style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', marginBottom: '6px' }}>{block.group}</div>
                              )}
                              {block.items.map(s => (
                                <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', flexWrap: 'wrap', gap: '8px' }}>
                                  <div style={{ fontSize: '15px', paddingLeft: block.group ? '12px' : 0 }}>{s.label}</div>
                                  <div style={{ display: 'flex', gap: '14px' }}>
                                    {s.actions.map(a => (
                                      <label key={a} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '14px', color: '#374151', cursor: 'pointer' }}>
                                        <input type="checkbox"
                                          checked={!!editingRolePerms[r.id]?.[s.key]?.[a]}
                                          onChange={() => togglePerm(r.id, s.key, a)} />
                                        {ACTION_LABELS_RU[a] || a}
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
