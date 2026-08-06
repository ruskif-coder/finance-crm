import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { MONO, UI, card, sel, th, td } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'

// ── Журнал действий — отдельная страница раздела «Настройки» ──
// Аудит мутаций: фильтры (действие/пользователь/период) + пагинация «показать ещё».
// Список пользователей грузим для выпадающего фильтра «по пользователю».
const AUDIT_LIMIT = 50

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtDateTime = (s) => {
  if (!s) return ''
  // DB хранит UTC (func.now()); добавляем 'Z' если нет маркера зоны, чтобы браузер
  // воспринял как UTC, затем отображаем в московском времени (UTC+3).
  const str = /[Z+]/.test(s) ? s : s + 'Z'
  return new Date(str).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })
}

export default function SettingsAudit() {
  const router = useRouter()
  const [users, setUsers] = useState([])
  const [auditItems, setAuditItems] = useState([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [actionLabels, setActionLabels] = useState({})
  const [auditFilters, setAuditFilters] = useState({ action: '', user_id: '', date_from: '', date_to: '' })
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [auditSkip, setAuditSkip] = useState(0)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('audit')) { router.push('/dashboard'); return }
    // При маунте грузим и журнал, и список пользователей (для фильтра «по пользователю»).
    loadUsers()
    loadAuditLog(0, auditFilters)
  }, [])

  const loadUsers = async () => {
    try {
      const res = await api.get('/users/', auth())
      setUsers(res.data)
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
  }

  const loadAuditLog = async (skip, filters) => {
    setLoadingAudit(true)
    try {
      const params = { skip, limit: AUDIT_LIMIT }
      if (filters.action) params.action = filters.action
      if (filters.user_id) params.user_id = filters.user_id
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const res = await api.get('/users/audit-log/', { ...auth(), params })
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
    loadAuditLog(0, next)
  }

  // стили — общий модуль components/salesTableKit

  return (
    <>
      <Head><title>Журнал действий | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="audit" />

        {/* Фильтры */}
        <div style={{ ...card, padding: '14px 18px', marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select value={auditFilters.action} onChange={e => handleAuditFilterChange({ action: e.target.value })} style={sel}>
            <option value="">Все действия</option>
            {Object.entries(actionLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={auditFilters.user_id} onChange={e => handleAuditFilterChange({ user_id: e.target.value })} style={sel}>
            <option value="">Все пользователи</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <input type="date" value={auditFilters.date_from} onChange={e => handleAuditFilterChange({ date_from: e.target.value })} style={sel} />
          <span style={{ color: 'var(--text-faint)' }}>—</span>
          <input type="date" value={auditFilters.date_to} onChange={e => handleAuditFilterChange({ date_to: e.target.value })} style={sel} />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 'auto' }}>{fmt(auditTotal)} записей</span>
        </div>

        {/* Таблица журнала */}
        <div style={{ ...card, padding: '14px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Журнал действий</h1>
            <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{fmt(auditTotal)}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr>
                <th style={{ ...th, width: 180 }}>Дата и время</th>
                <th style={{ ...th, width: 180 }}>Пользователь</th>
                <th style={{ ...th, width: 200 }}>Действие</th>
                <th style={th}>Детали</th>
              </tr></thead>
              <tbody>
                {auditItems.map(a => (
                  <tr key={a.id}>
                    <td style={{ ...td, whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>{fmtDateTime(a.created_at)}</td>
                    <td style={td}>{a.user_name || '—'}</td>
                    <td style={td}>
                      <span style={{ fontSize: 13, padding: '3px 10px', borderRadius: 20,
                        background: a.action.includes('failed') ? 'var(--danger-tint)' : a.action.includes('delete') ? 'var(--warning-tint)' : 'var(--accent-tint)',
                        color: a.action.includes('failed') ? 'var(--danger)' : 'var(--text-secondary)' }}>
                        {a.action_label}
                      </span>
                    </td>
                    <td style={{ ...td, color: 'var(--text-muted)' }}>{a.details || ''}</td>
                  </tr>
                ))}
                {!auditItems.length && !loadingAudit && <tr><td colSpan={4} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Записей нет</td></tr>}
              </tbody>
            </table>
          </div>
          {loadingAudit && <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)' }}>Загрузка…</div>}
          {!loadingAudit && auditItems.length < auditTotal && (
            <div style={{ textAlign: 'center', padding: 16 }}>
              <button onClick={() => loadAuditLog(auditSkip + AUDIT_LIMIT, auditFilters)}
                style={{ padding: '9px 16px', borderRadius: 10, border: '1px solid var(--border-card)', cursor: 'pointer', fontWeight: 600, fontSize: 13, background: 'var(--bg-card)', color: 'var(--accent)', fontFamily: UI }}>
                Показать ещё
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
