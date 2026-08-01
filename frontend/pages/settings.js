import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Navbar from '../components/Navbar'
import Head from 'next/head'
import Articles from './articles'
import Pipelines from './pipelines'
import FieldAuditPanel from '../components/FieldAuditPanel'

// Секции продаж — 5-уровневый доступ (свои/все). Единый список для матрицы.
const SALES_KEYS = ['sales_dashboard', 'sales_registry', 'sales_analytics']

const api = (token) => axios.create({
  // См. комментарий в balance.js — относительный путь, проксируется Caddy.
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtDateTime = (s) => {
  if (!s) return ''
  // DB хранит UTC (func.now()); добавляем 'Z' если нет маркера зоны, чтобы браузер
  // воспринял как UTC, затем отображаем в московском времени (UTC+3).
  const str = /[Z+]/.test(s) ? s : s + 'Z'
  return new Date(str).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })
}
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'

const BANK_STYLES = {
  'АльфаБанк':  { bg: '#fee2e2', color: '#dc2626', border: '#fca5a5' },
  'ОПТ Банк':   { bg: '#dcfce7', color: '#16a34a', border: '#86efac' },
  'Совкомбанк': { bg: '#f3f4f6', color: '#4b5563', border: '#d1d5db' },
  'Наличные':   { bg: '#dbeafe', color: '#2563eb', border: '#93c5fd' },
}

const ACTION_LABELS_RU = { view: 'Просмотр', create: 'Создание', edit: 'Редактирование', delete: 'Удаление', view_operations: 'Опер. в карточке' }

// Одна строка на страницу, в ячейке — уровень доступа. Уровни маппятся на булевы
// поля бэкенда (can_view/edit/…) + deals_scope. Три вида страниц:
//   view  — только чтение (отчёты без правки): нет / просмотр
//   edit  — справочники и разделы с правкой: нет / просмотр / редактирование
//   sales — раздел «Продажи»: + измерение свои/все (deals_scope)
const LEVELS_VIEW = [{ v: 'none', l: 'нет' }, { v: 'view', l: 'просмотр' }]
const LEVELS_EDIT = [{ v: 'none', l: 'нет' }, { v: 'view', l: 'просмотр' }, { v: 'edit', l: 'редактирование' }]
const LEVELS_SALES = [
  { v: 'none', l: 'нет' },
  { v: 'view_own', l: 'просмотр — свои' },
  { v: 'view_all', l: 'просмотр — все' },
  { v: 'edit_own', l: 'редактирование — свои' },
  { v: 'edit_all', l: 'редактирование — все' },
]
const sectionKind = (s) => SALES_KEYS.includes(s.key) ? 'sales'
  : (s.actions.some(a => a !== 'view') ? 'edit' : 'view')
const levelsFor = (s) => { const k = sectionKind(s); return k === 'sales' ? LEVELS_SALES : k === 'edit' ? LEVELS_EDIT : LEVELS_VIEW }
const levelLabel = (s, v) => (levelsFor(s).find(x => x.v === v) || {}).l || v
const adminLevel = (s) => { const k = sectionKind(s); return k === 'sales' ? 'edit_all' : k === 'edit' ? 'edit' : 'view' }

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
  const [roleScopes, setRoleScopes] = useState({})   // { roleId: 'all' | 'own' }
  const [roleLabels, setRoleLabels] = useState({})
  const [savingRole, setSavingRole] = useState({})
  const [savingAll, setSavingAll] = useState(false)
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
  const [savingAllUsers, setSavingAllUsers] = useState(false)
  const [hideInactive, setHideInactive] = useState(false)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '', role: 'viewer' })
  const [creatingUser, setCreatingUser] = useState(false)
  const [userError, setUserError] = useState('')
  // Справочник сотрудников Битрикса (для привязки)
  const [bitrixUsers, setBitrixUsers] = useState([])
  const [bxLoading, setBxLoading] = useState(false)
  const [bxError, setBxError] = useState('')

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
    // Доступ: админ или роль с правом «Настройки» (остатки/статьи/воронки).
    if (r !== 'admin' && !can(perms, 'settings', 'view')) { router.push('/dashboard'); return }
    setRole(r)
    setPermissions(perms)
    setTab(r === 'admin' || can(perms, 'settings', 'view') ? 'balances' : 'balances')
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
    if (tab === 'services') loadServices(token)
  }, [tab])

  // ---------- Услуги (синхрон с Битриксом «Продукты Simb-ad») ----------
  const [services, setServices] = useState([])
  const [svcLoading, setSvcLoading] = useState(false)
  const [svcBusy, setSvcBusy] = useState(false)
  const loadServices = async (token) => {
    setSvcLoading(true)
    try {
      const r = await api(token).get('/sales/directories/services?only_active=false')
      setServices(r.data.items || [])
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
    finally { setSvcLoading(false) }
  }
  const toggleServiceUse = async (id, on) => {
    const token = localStorage.getItem('token')
    try { await api(token).put(`/sales/directories/services/${id}/use`, { on }); await loadServices(token) }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
  }
  const refreshServices = async () => {
    const token = localStorage.getItem('token')
    setSvcBusy(true)
    try {
      const r = await api(token).post('/sales/directories/services/refresh', {})
      alert(`Синхронизация услуг: добавлено ${r.data.added} (в Битриксе всего: ${r.data.bitrix_total})`)
      await loadServices(token)
    } catch (e) { alert(e.response?.data?.detail || 'Обновление недоступно') }
    finally { setSvcBusy(false) }
  }

  // Реквизиты компании для экспорта платёжек
  const [companyReq, setCompanyReq] = useState({})     // { "АльфаБанк": { inn, kpp, rs, bik, ... } }
  const [editingReq, setEditingReq] = useState({})
  const [savingReq, setSavingReq] = useState({})
  const [reqOpen, setReqOpen] = useState({})           // { "АльфаБанк": true } — раскрыта секция

  // Юрлица (is_own_company) для привязки к банковскому счёту
  const [ownCompanies, setOwnCompanies] = useState([])  // [{ id, name, inn }, ...]
  const [bankOwnCompany, setBankOwnCompany] = useState({})  // { "АльфаБанк": id|null }
  const [savingOwnCompany, setSavingOwnCompany] = useState({})

  const loadBalances = async (token) => {
    setLoading(true)
    try {
      const [balRes, ownRes] = await Promise.all([
        api(token).get('/settings/bank-balances'),
        api(token).get('/counterparties/own'),
      ])
      setBanks(balRes.data.banks)
      setTotalBalance(balRes.data.total_balance)
      setOwnCompanies(ownRes.data)
      const ed = {}
      const cr = {}
      const er = {}
      const boc = {}
      balRes.data.banks.forEach(b => {
        ed[b.bank] = b.opening_balance
        cr[b.bank] = {
          company_name: b.company_name || '',
          inn: b.inn || '',
          kpp: b.kpp || '',
          rs: b.rs || '',
          bik: b.bik || '',
          bank_full_name: b.bank_full_name || '',
          bank_city: b.bank_city || '',
          ks: b.ks || '',
        }
        er[b.bank] = { ...cr[b.bank] }
        boc[b.bank] = b.own_company_id || ''
      })
      setEditing(ed)
      setCompanyReq(cr)
      setEditingReq(er)
      setBankOwnCompany(boc)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveBankOwnCompany = async (bank) => {
    const token = localStorage.getItem('token')
    setSavingOwnCompany(prev => ({ ...prev, [bank]: true }))
    try {
      const ownId = bankOwnCompany[bank]
      await api(token).patch('/settings/bank-balances/own-company', {
        bank,
        own_company_id: ownId ? parseInt(ownId, 10) : null,
      })
      await loadBalances(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении юрлица')
    } finally {
      setSavingOwnCompany(prev => ({ ...prev, [bank]: false }))
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

  const handleSaveReq = async (bank) => {
    const token = localStorage.getItem('token')
    setSavingReq(prev => ({ ...prev, [bank]: true }))
    try {
      await api(token).put('/settings/company-requisites', { bank, ...editingReq[bank] })
      await loadBalances(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении реквизитов')
    } finally {
      setSavingReq(prev => ({ ...prev, [bank]: false }))
    }
  }

  // ---------- Пользователи ----------

  const loadUsers = async (token) => {
    setLoadingUsers(true)
    try {
      const res = await api(token).get('/users/')
      setUsers(res.data)
      const ed = {}
      res.data.forEach(u => { ed[u.id] = { name: u.name, email: u.email, role: u.role, is_active: u.is_active, password: '', bitrix_user_id: u.bitrix_user_id || '' } })
      setEditingUsers(ed)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingUsers(false)
    }
    loadBitrixUsers(token)
  }

  const loadBitrixUsers = async (token) => {
    setBxLoading(true); setBxError('')
    try {
      const res = await api(token).get('/users/bitrix-directory')
      setBitrixUsers(res.data.items || [])
    } catch (e) {
      setBxError(e.response?.data?.detail || 'Битрикс недоступен')
    } finally {
      setBxLoading(false)
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
      const payload = { name: ed.name, email: ed.email, role: ed.role, is_active: ed.is_active, bitrix_user_id: ed.bitrix_user_id || '' }
      if (ed.password) payload.password = ed.password
      await api(token).put(`/users/${id}`, payload)
      await loadUsers(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setSavingUsers(prev => ({ ...prev, [id]: false }))
    }
  }

  const handleSaveAllUsers = async () => {
    const token = localStorage.getItem('token')
    setSavingAllUsers(true)
    let ok = 0; const errs = []
    for (const u of users) {
      const ed = editingUsers[u.id]
      if (!ed) continue
      try {
        const payload = { name: ed.name, email: ed.email, role: ed.role, is_active: ed.is_active, bitrix_user_id: ed.bitrix_user_id || '' }
        if (ed.password) payload.password = ed.password
        await api(token).put(`/users/${u.id}`, payload)
        ok++
      } catch (e) { errs.push(`${u.name}: ${e.response?.data?.detail || 'ошибка'}`) }
    }
    await loadUsers(token)
    setSavingAllUsers(false)
    alert(`Сохранено: ${ok}` + (errs.length ? `\nОшибки (${errs.length}):\n` + errs.join('\n') : ''))
  }

  // Генератор пароля через Web Crypto (готовое безопасное решение). Без похожих символов (0/O/1/l/I).
  const genPassword = (len = 16) => {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*-_=+'
    const arr = new Uint32Array(len)
    window.crypto.getRandomValues(arr)
    return Array.from(arr, x => chars[x % chars.length]).join('')
  }
  const copyText = async (t) => {
    try { await navigator.clipboard.writeText(t) } catch (e) {
      const ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select()
      try { document.execCommand('copy') } catch (_) {} document.body.removeChild(ta)
    }
  }

  // Удаление — только деактивированных; backend дополнительно блокирует, если есть операции
  const handleDeleteUser = async (id, name) => {
    if (!confirm(`Удалить пользователя «${name}»? Действие необратимо.`)) return
    const token = localStorage.getItem('token')
    try {
      await api(token).delete(`/users/${id}`)
      await loadUsers(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при удалении')
    }
  }

  // Контрагенты/Статьи/Договоры были перенесены в pages/directories.js (раздел "Справочники")

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
      const scopes = {}
      res.data.roles.forEach(r => {
        draft[r.id] = JSON.parse(JSON.stringify(r.permissions))
        labels[r.id] = r.label
        scopes[r.id] = r.deals_scope || 'all'
      })
      setEditingRolePerms(draft)
      setRoleLabels(labels)
      setRoleScopes(scopes)
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

  const setScope = (roleId, value) => setRoleScopes(prev => ({ ...prev, [roleId]: value }))

  const buildPermPayload = (roleId) => {
    const draft = editingRolePerms[roleId] || {}
    return sections.map(s => ({
      section: s.key,
      can_view: s.actions.includes('view') ? !!draft[s.key]?.view : undefined,
      can_create: s.actions.includes('create') ? !!draft[s.key]?.create : undefined,
      can_edit: s.actions.includes('edit') ? !!draft[s.key]?.edit : undefined,
      can_delete: s.actions.includes('delete') ? !!draft[s.key]?.delete : undefined,
      can_view_operations: s.actions.includes('view_operations') ? !!draft[s.key]?.view_operations : undefined,
      deals_scope: SALES_KEYS.includes(s.key) ? (roleScopes[roleId] || 'all') : undefined,
    }))
  }

  const handleSaveRole = async (roleId) => {
    const token = localStorage.getItem('token')
    setSavingRole(prev => ({ ...prev, [roleId]: true }))
    try {
      await api(token).put(`/roles/${roleId}`, { label: roleLabels[roleId], permissions: buildPermPayload(roleId) })
      await loadRoles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении роли')
    } finally {
      setSavingRole(prev => ({ ...prev, [roleId]: false }))
    }
  }

  // Сохранить все роли разом — удобнее для матрицы, где правишь несколько сразу.
  const handleSaveAll = async () => {
    const token = localStorage.getItem('token')
    setSavingAll(true)
    try {
      for (const r of allRoles) {
        if (r.key === 'admin') continue
        await api(token).put(`/roles/${r.id}`, { label: roleLabels[r.id], permissions: buildPermPayload(r.id) })
      }
      await loadRoles(token)
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setSavingAll(false)
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

  // Строки матрицы: заголовки групп + по одной строке на страницу. Роли — колонки.
  const buildMatrixRows = (secs) => {
    const out = []
    let group
    secs.forEach(s => {
      if (s.group !== group) { group = s.group; if (s.group) out.push({ type: 'group', label: s.group }) }
      out.push({ type: 'section', s })
    })
    return out
  }

  // Текущий уровень доступа роли к странице — выводится из булевых полей + scope.
  const currentLevel = (roleId, s) => {
    const d = editingRolePerms[roleId]?.[s.key] || {}
    if (SALES_KEYS.includes(s.key)) {
      if (!d.view) return 'none'
      return (d.edit ? 'edit_' : 'view_') + (roleScopes[roleId] === 'own' ? 'own' : 'all')
    }
    if (!d.view) return 'none'
    return s.actions.some(a => a !== 'view' && d[a]) ? 'edit' : 'view'
  }

  // Установка уровня → раскладка по булевым полям секции (+ scope для продаж).
  const setLevel = (roleId, s, level) => {
    let sec
    if (SALES_KEYS.includes(s.key)) {
      sec = { view: level !== 'none', edit: level.startsWith('edit') }
      setScope(roleId, level.endsWith('own') ? 'own' : 'all')
    } else if (level === 'view') {
      sec = Object.fromEntries(s.actions.map(a => [a, a === 'view']))
    } else if (level === 'edit') {
      sec = Object.fromEntries(s.actions.map(a => [a, true]))
    } else { // none
      sec = Object.fromEntries(s.actions.map(a => [a, false]))
    }
    setEditingRolePerms(prev => ({ ...prev, [roleId]: { ...prev[roleId], [s.key]: sec } }))
  }

  const inp = { width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none', textAlign: 'right' }
  const inpLeft = { ...inp, textAlign: 'left' }
  const select = { padding: '8px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '16px', outline: 'none' }
  const btn = { padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: 'white', cursor: 'pointer', fontSize: '15px', whiteSpace: 'nowrap' }
  const th = { textAlign: 'left', padding: '8px 12px', fontSize: '13px', color: '#6b7280', fontWeight: '500', borderBottom: '1px solid #e5e7eb' }
  const td = { padding: '10px 12px', fontSize: '15px', borderBottom: '1px solid #f3f4f6' }

  // Настройки теперь доступны только администратору (см. page-guard выше), поэтому
  // вкладки ниже не нуждаются в индивидуальных permission-проверках — admin проходит их все.
  const isAdmin = role === 'admin'
  const maySettings = isAdmin || can(permissions, 'settings', 'view')
  const tabs = [
    ...(maySettings ? [
      { id: 'balances', label: 'Остатки по банкам' },
      { id: 'articles', label: 'Статьи' },
      { id: 'pipelines', label: 'Воронки' },
      { id: 'services', label: 'Услуги' },
      { id: 'field_audit', label: 'Сверка полей' },
    ] : []),
    ...(isAdmin ? [
      { id: 'users', label: 'Пользователи' },
      { id: 'audit', label: 'Журнал действий' },
      { id: 'roles', label: 'Роли' },
    ] : []),
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Navbar active="settings" />
      <Head><title>Настройки | Финансовый учёт</title></Head>

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

        {tab === 'field_audit' && <FieldAuditPanel />}

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
                          {(role === 'admin' || can(permissions, 'settings', 'edit')) ? (
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

                      {/* Юрлицо-плательщик для этого банка */}
                      {(role === 'admin' || can(permissions, 'settings', 'edit')) && b.bank !== 'Наличные' && ownCompanies.length > 0 && (
                        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 13, color: '#6b7280', whiteSpace: 'nowrap' }}>🏢 Юрлицо:</span>
                          <select
                            value={bankOwnCompany[b.bank] || ''}
                            onChange={e => setBankOwnCompany(prev => ({ ...prev, [b.bank]: e.target.value }))}
                            style={{ fontSize: 13, padding: '4px 8px', border: '1px solid #e5e7eb', borderRadius: 6, background: '#f9fafb', minWidth: '180px' }}
                          >
                            <option value="">— не привязано —</option>
                            {ownCompanies.map(cp => (
                              <option key={cp.id} value={cp.id}>{cp.name}{cp.inn ? ` (ИНН ${cp.inn})` : ''}</option>
                            ))}
                          </select>
                          <button
                            onClick={() => handleSaveBankOwnCompany(b.bank)}
                            disabled={savingOwnCompany[b.bank]}
                            style={{ fontSize: 13, padding: '4px 12px', borderRadius: 6, border: '1px solid #93c5fd', background: '#dbeafe', color: '#1d4ed8', cursor: 'pointer', opacity: savingOwnCompany[b.bank] ? 0.6 : 1 }}
                          >
                            {savingOwnCompany[b.bank] ? '...' : 'Сохранить'}
                          </button>
                        </div>
                      )}

                      {/* Реквизиты компании для выгрузки платёжек — раскрывающийся блок */}
                      {(role === 'admin' || can(permissions, 'settings', 'edit')) && b.bank !== 'Наличные' && (
                        <div style={{ marginTop: 14, borderTop: '1px solid #f3f4f6', paddingTop: 12 }}>
                          <button
                            onClick={() => setReqOpen(prev => ({ ...prev, [b.bank]: !prev[b.bank] }))}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 13,
                                     color: '#2563eb', padding: 0, display: 'flex', alignItems: 'center', gap: 4 }}
                          >
                            {reqOpen[b.bank] ? '▾' : '▸'} Реквизиты компании-плательщика
                            {editingReq[b.bank]?.inn && <span style={{ color: '#6b7280', fontWeight: 400 }}> · ИНН {editingReq[b.bank].inn}</span>}
                          </button>
                          {reqOpen[b.bank] && (
                            <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
                              {[
                                { key: 'company_name', label: 'Наименование организации', full: true },
                                { key: 'inn',          label: 'ИНН' },
                                { key: 'kpp',          label: 'КПП' },
                                { key: 'rs',           label: 'Расчётный счёт (Р/С)' },
                                { key: 'bik',          label: 'БИК банка' },
                                { key: 'bank_full_name', label: 'Наименование банка', full: true },
                                { key: 'bank_city',    label: 'Город банка' },
                                { key: 'ks',           label: 'Корр. счёт (К/С)' },
                              ].map(f => (
                                <div key={f.key} style={f.full ? { gridColumn: '1 / -1' } : {}}>
                                  <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 2 }}>{f.label}</div>
                                  <input
                                    style={{ width: '100%', padding: '5px 8px', fontSize: 13,
                                             border: '1px solid #e5e7eb', borderRadius: 6,
                                             background: '#f9fafb', boxSizing: 'border-box' }}
                                    value={editingReq[b.bank]?.[f.key] || ''}
                                    onChange={e => setEditingReq(prev => ({
                                      ...prev,
                                      [b.bank]: { ...prev[b.bank], [f.key]: e.target.value }
                                    }))}
                                  />
                                </div>
                              ))}
                              <div style={{ gridColumn: '1 / -1', marginTop: 4 }}>
                                <button
                                  onClick={() => handleSaveReq(b.bank)}
                                  disabled={savingReq[b.bank]}
                                  style={btn}
                                >
                                  {savingReq[b.bank] ? 'Сохранение...' : 'Сохранить реквизиты'}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {tab === 'articles' && (
          <div style={{ background: 'white', borderRadius: '12px', padding: '16px' }}>
            <Articles embedded />
          </div>
        )}

        {tab === 'pipelines' && (
          <div style={{ background: 'white', borderRadius: '12px', padding: '16px' }}>
            <Pipelines embedded />
          </div>
        )}

        {tab === 'services' && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
              <h2 style={{ fontSize: 17, fontWeight: 600, margin: 0 }}>Услуги</h2>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{services.length}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>синхронизация с «Продукты Simb-ad» (Битрикс)</span>
              <button onClick={refreshServices} disabled={svcBusy}
                style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: 14, background: '#2563eb', color: 'white' }}>
                {svcBusy ? 'Обновление…' : 'Обновить из Битрикса'}
              </button>
            </div>
            {svcLoading ? <div style={{ color: '#6b7280', padding: 20 }}>Загрузка…</div> : (
              <div style={{ background: 'white', borderRadius: '12px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr>
                    <th style={th}>Услуга</th>
                    <th style={th}>Группа</th>
                    <th style={{ ...th, textAlign: 'center', width: 120 }}>Использовать</th>
                  </tr></thead>
                  <tbody>
                    {services.map(s => (
                      <tr key={s.id} style={{ opacity: s.is_active ? 1 : 0.5 }}>
                        <td style={td}>{s.name}</td>
                        <td style={{ ...td, color: '#6b7280' }}>{s.group || ''}</td>
                        <td style={{ ...td, textAlign: 'center' }}>
                          <input type="checkbox" checked={!!s.is_active}
                            onChange={e => toggleServiceUse(s.id, e.target.checked)}
                            style={{ cursor: 'pointer' }} />
                        </td>
                      </tr>
                    ))}
                    {!services.length && <tr><td colSpan={3} style={{ ...td, textAlign: 'center', color: '#9ca3af' }}>Услуг нет — нажмите «Обновить из Битрикса»</td></tr>}
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

            {/* Тулбар: скрыть деактивированных + массовое сохранение */}
            {!loadingUsers && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
                <label style={{ fontSize: 13, color: '#374151', cursor: 'pointer' }}>
                  <input type="checkbox" checked={hideInactive} onChange={e => setHideInactive(e.target.checked)} /> скрыть деактивированных
                </label>
                <button onClick={handleSaveAllUsers} disabled={savingAllUsers} style={{ ...btn, marginLeft: 'auto' }}>
                  {savingAllUsers ? 'Сохранение…' : 'Сохранить все'}
                </button>
              </div>
            )}

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
                      <th style={th}>Сотрудник в Битрикс24</th>
                      <th style={th}>Новый пароль</th>
                      <th style={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.filter(u => !hideInactive || u.is_active).map(u => {
                      const ed = editingUsers[u.id] || { name: u.name, email: u.email, role: u.role, is_active: u.is_active, password: '', bitrix_user_id: u.bitrix_user_id || '' }
                      const isSelf = u.id === selfId
                      return (
                        <tr key={u.id}>
                          <td style={td}>
                            <input value={ed.name}
                              onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, name: e.target.value } }))}
                              style={{ ...inpLeft, width: '160px', padding: '6px 10px' }} />
                          </td>
                          <td style={td}>
                            <input type="email" value={ed.email}
                              onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, email: e.target.value } }))}
                              style={{ ...inpLeft, width: '200px', padding: '6px 10px' }} />
                          </td>
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
                            {(() => {
                              const cur = ed.bitrix_user_id || ''
                              const known = bitrixUsers.some(b => b.id === cur)
                              return (
                                <select value={cur}
                                  onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, bitrix_user_id: e.target.value } }))}
                                  disabled={bxLoading || (!!bxError && bitrixUsers.length === 0)}
                                  title={bxError || ''}
                                  style={{ ...select, minWidth: '200px' }}>
                                  <option value="">{bxLoading ? 'загрузка…' : (bxError && bitrixUsers.length === 0 ? '⚠ ' + bxError : '— не привязан —')}</option>
                                  {cur && !known && <option value={cur}>ID {cur} (не в списке)</option>}
                                  {[...bitrixUsers].sort((a, b) => (a.active === b.active ? 0 : a.active ? -1 : 1)).map(b =>
                                    <option key={b.id} value={b.id}>{b.name}{b.active ? '' : ' (уволен)'} · #{b.id}</option>)}
                                </select>
                              )
                            })()}
                          </td>
                          <td style={td}>
                            <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                              <input type={ed.showPw ? 'text' : 'password'} placeholder="не менять" value={ed.password}
                                onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, password: e.target.value } }))}
                                style={{ ...inpLeft, width: '150px', padding: '6px 10px', fontFamily: ed.showPw ? 'monospace' : 'inherit' }} />
                              <button title="Сгенерировать пароль (16 символов)"
                                onClick={() => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, password: genPassword(16), showPw: true } }))}
                                style={{ padding: '5px 8px', borderRadius: '8px', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', fontSize: '14px' }}>🎲</button>
                              {ed.password && (
                                <button title="Скопировать пароль"
                                  onClick={() => copyText(ed.password)}
                                  style={{ padding: '5px 8px', borderRadius: '8px', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', fontSize: '14px' }}>📋</button>
                              )}
                            </div>
                          </td>
                          <td style={td}>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                              <button onClick={() => handleSaveUser(u.id)} disabled={savingUsers[u.id]} style={btn}>
                                {savingUsers[u.id] ? '...' : 'Сохранить'}
                              </button>
                              {/* Удаление — только деактивированных и не себя (2026-07-16) */}
                              {!isSelf && !u.is_active && (
                                <button onClick={() => handleDeleteUser(u.id, u.name)} title="Удалить пользователя"
                                  style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid #fca5a5',
                                           background: '#fee2e2', cursor: 'pointer', color: '#dc2626', fontSize: '14px' }}>
                                  🗑
                                </button>
                              )}
                            </div>
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
              <div style={{ background: 'white', borderRadius: '12px', padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ fontSize: '14px', color: '#6b7280' }}>
                    Разделы — по вертикали, роли — по горизонтали. «Админ» имеет полный доступ и не настраивается.
                  </div>
                  <button onClick={handleSaveAll} disabled={savingAll} style={btn}>
                    {savingAll ? 'Сохранение...' : 'Сохранить изменения'}
                  </button>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 480 }}>
                    <thead>
                      <tr>
                        <th style={{ position: 'sticky', left: 0, background: 'white', zIndex: 2, textAlign: 'left',
                          padding: '8px 12px', borderBottom: '2px solid #e5e7eb', minWidth: 260, fontSize: 13, color: '#6b7280' }}>
                          Раздел / действие
                        </th>
                        {allRoles.map(r => {
                          const isAdmin = r.key === 'admin'
                          return (
                            <th key={r.id} style={{ padding: '8px 10px', borderBottom: '2px solid #e5e7eb',
                              textAlign: 'center', minWidth: 200, verticalAlign: 'top' }}>
                              {isAdmin ? (
                                <div style={{ fontWeight: 600, fontSize: 15 }}>{r.label}</div>
                              ) : (
                                <input value={roleLabels[r.id] ?? r.label}
                                  onChange={e => setRoleLabels(prev => ({ ...prev, [r.id]: e.target.value }))}
                                  style={{ ...inp, textAlign: 'center', fontWeight: 600, fontSize: 14, padding: '5px 8px' }} />
                              )}
                              <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                                {r.is_system ? 'системная · ' : ''}{r.user_count} польз.
                              </div>
                              {!r.is_system && (
                                <button onClick={() => handleDeleteRole(r.id)}
                                  style={{ marginTop: 6, fontSize: 12, color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                                  удалить
                                </button>
                              )}
                            </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {buildMatrixRows(sections).map((row, ri) => {
                        if (row.type === 'group') {
                          return (
                            <tr key={`g${ri}`}>
                              <td colSpan={allRoles.length + 1} style={{ position: 'sticky', left: 0,
                                background: '#f9fafb', padding: '7px 12px', fontSize: 13, fontWeight: 600,
                                color: '#6b7280', borderTop: '1px solid #f3f4f6' }}>
                                {row.label}
                              </td>
                            </tr>
                          )
                        }
                        const s = row.s
                        return (
                          <tr key={s.key}>
                            <td style={{ position: 'sticky', left: 0, background: 'white', zIndex: 1,
                              padding: '9px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 14 }}>
                              {s.label}
                            </td>
                            {allRoles.map(r => {
                              const isAdmin = r.key === 'admin'
                              return (
                                <td key={r.id} style={{ textAlign: 'center', padding: '6px 10px', borderBottom: '1px solid #f3f4f6' }}>
                                  {isAdmin ? (
                                    <span style={{ fontSize: 13, color: '#9ca3af' }}>{levelLabel(s, adminLevel(s))}</span>
                                  ) : (
                                    <select value={currentLevel(r.id, s)} onChange={e => setLevel(r.id, s, e.target.value)}
                                      style={{ ...select, fontSize: 13, padding: '5px 8px', width: '100%', maxWidth: 200 }}>
                                      {levelsFor(s).map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                                    </select>
                                  )}
                                </td>
                              )
                            })}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
