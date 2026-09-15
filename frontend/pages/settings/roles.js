import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { MONO, UI, card, inp, sel, primaryBtn, th } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

// ── Роли и права доступа — отдельная страница раздела «Настройки» ──
// Матрица: разделы по вертикали, роли по горизонтали, в ячейке — уровень доступа.
// Уровни маппятся на булевы поля бэкенда (can_view/edit/…) + deals_scope.

// Секции с 5-уровневым доступом (свои/все). Каждая привязана к «группе scope»:
// продажи (общий deals_scope на три секции) и медиапланы (свой, независимый).
const SCOPE_GROUP = {
  sales_dashboard: 'sales', sales_registry: 'sales', sales_analytics: 'sales',
  media_plans: 'mp', media_plans_editor: 'mp',
  year_plan: 'yp',
  // Дашборд аккаунта несёт свой scope: очередь «Что делать» — это его сделки, и решать
  // «свои/все» надо здесь, а не наследовать от продаж. Уровни те же пять, что и везде.
  accounts_dashboard: 'acc',
}
const SCOPED_KEYS = Object.keys(SCOPE_GROUP)

// Рабочая группа роли (для конструктора МП) — классификация «кто продавец/аккаунт/трафик».
// Пользователь наследует её через свою роль; «мастер» помечается ★ в пикерах МП.
const STAFF_GROUPS = [{ v: '', l: '— не в группе' }, { v: 'seller', l: 'Продавцы' }, { v: 'account', l: 'Аккаунты' }, { v: 'traffic', l: 'Трафики' }]

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
const sectionKind = (s) => SCOPED_KEYS.includes(s.key) ? 'sales'
  : (s.actions.some(a => a !== 'view') ? 'edit' : 'view')
const levelsFor = (s) => { const k = sectionKind(s); return k === 'sales' ? LEVELS_SALES : k === 'edit' ? LEVELS_EDIT : LEVELS_VIEW }
const levelLabel = (s, v) => (levelsFor(s).find(x => x.v === v) || {}).l || v
const adminLevel = (s) => { const k = sectionKind(s); return k === 'sales' ? 'edit_all' : k === 'edit' ? 'edit' : 'view' }

export default function SettingsRoles() {
  const router = useRouter()
  const [allRoles, setAllRoles] = useState([])
  const [sections, setSections] = useState([])
  const [loadingRoles, setLoadingRoles] = useState(false)
  const [editingRolePerms, setEditingRolePerms] = useState({})
  const [roleScopes, setRoleScopes] = useState({})   // { roleId: { sales: 'all'|'own', mp: 'all'|'own' } }
  const [roleGroups, setRoleGroups] = useState({})   // { roleId: '' | 'seller' | 'account' | 'traffic' }
  const [roleMasters, setRoleMasters] = useState({}) // { roleId: bool }
  const [roleLabels, setRoleLabels] = useState({})
  const [savingRole, setSavingRole] = useState({})
  const [savingAll, setSavingAll] = useState(false)
  const [newRoleLabel, setNewRoleLabel] = useState('')
  const [creatingRole, setCreatingRole] = useState(false)
  const [roleError, setRoleError] = useState('')

  useRefreshOnReturn(() => loadRoles())
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (localStorage.getItem('role') !== 'admin') { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
    loadRoles()
  }, [])

  // ---------- Роли и права доступа ----------

  const loadRoles = async () => {
    setLoadingRoles(true)
    try {
      const res = await api.get('/roles/', auth())
      setAllRoles(res.data.roles)
      setSections(res.data.sections)
      const draft = {}
      const labels = {}
      const scopes = {}
      const groups = {}
      const masters = {}
      res.data.roles.forEach(r => {
        draft[r.id] = JSON.parse(JSON.stringify(r.permissions))
        labels[r.id] = r.label
        scopes[r.id] = { sales: r.deals_scope || 'all', mp: r.mp_scope || 'all', yp: r.year_plan_scope || 'all' }
        groups[r.id] = r.staff_group || ''
        masters[r.id] = !!r.is_master
      })
      setEditingRolePerms(draft)
      setRoleLabels(labels)
      setRoleScopes(scopes)
      setRoleGroups(groups)
      setRoleMasters(masters)
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
    setCreatingRole(true)
    try {
      await api.post('/roles/', { label: newRoleLabel.trim() }, auth())
      setNewRoleLabel('')
      await loadRoles()
    } catch (e) {
      setRoleError(e.response?.data?.detail || 'Ошибка при создании роли')
    } finally {
      setCreatingRole(false)
    }
  }

  const setScope = (roleId, group, value) => setRoleScopes(prev => ({ ...prev, [roleId]: { ...prev[roleId], [group]: value } }))

  const buildPermPayload = (roleId) => {
    const draft = editingRolePerms[roleId] || {}
    return sections.map(s => ({
      section: s.key,
      can_view: s.actions.includes('view') ? !!draft[s.key]?.view : undefined,
      can_create: s.actions.includes('create') ? !!draft[s.key]?.create : undefined,
      can_edit: s.actions.includes('edit') ? !!draft[s.key]?.edit : undefined,
      can_delete: s.actions.includes('delete') ? !!draft[s.key]?.delete : undefined,
      can_view_operations: s.actions.includes('view_operations') ? !!draft[s.key]?.view_operations : undefined,
      can_approve: s.actions.includes('approve') ? !!draft[s.key]?.approve : undefined,
      deals_scope: SCOPED_KEYS.includes(s.key) ? (roleScopes[roleId]?.[SCOPE_GROUP[s.key]] || 'all') : undefined,
    }))
  }

  const handleSaveRole = async (roleId) => {
    setSavingRole(prev => ({ ...prev, [roleId]: true }))
    try {
      await api.put(`/roles/${roleId}`, { label: roleLabels[roleId], permissions: buildPermPayload(roleId), staff_group: roleGroups[roleId] || '', is_master: !!roleMasters[roleId] }, auth())
      await loadRoles()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении роли')
    } finally {
      setSavingRole(prev => ({ ...prev, [roleId]: false }))
    }
  }

  // Сохранить все роли разом — удобнее для матрицы, где правишь несколько сразу.
  const handleSaveAll = async () => {
    setSavingAll(true)
    try {
      for (const r of allRoles) {
        if (r.key === 'admin') continue
        await api.put(`/roles/${r.id}`, { label: roleLabels[r.id], permissions: buildPermPayload(r.id), staff_group: roleGroups[r.id] || '', is_master: !!roleMasters[r.id] }, auth())
      }
      await loadRoles()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setSavingAll(false)
    }
  }

  const handleDeleteRole = async (roleId) => {
    if (!confirm('Удалить роль?')) return
    try {
      await api.delete(`/roles/${roleId}`, auth())
      await loadRoles()
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
    if (SCOPED_KEYS.includes(s.key)) {
      if (!d.view) return 'none'
      return (d.edit ? 'edit_' : 'view_') + (roleScopes[roleId]?.[SCOPE_GROUP[s.key]] === 'own' ? 'own' : 'all')
    }
    if (!d.view) return 'none'
    return s.actions.some(a => a !== 'view' && d[a]) ? 'edit' : 'view'
  }

  // Установка уровня → раскладка по булевым полям секции (+ scope для scoped-секций).
  const setLevel = (roleId, s, level) => {
    let sec
    if (SCOPED_KEYS.includes(s.key)) {
      sec = { view: level !== 'none', edit: level.startsWith('edit') }
      setScope(roleId, SCOPE_GROUP[s.key], level.endsWith('own') ? 'own' : 'all')
    } else if (level === 'view') {
      sec = Object.fromEntries(s.actions.map(a => [a, a === 'view']))
    } else if (level === 'edit') {
      sec = Object.fromEntries(s.actions.map(a => [a, true]))
    } else { // none
      sec = Object.fromEntries(s.actions.map(a => [a, false]))
    }
    setEditingRolePerms(prev => ({ ...prev, [roleId]: { ...prev[roleId], [s.key]: sec } }))
  }

  // стили — общий модуль components/salesTableKit

  return (
    <>
      <Head><title>Роли · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="roles" />

        {/* Создание роли */}
        <div style={{ ...card, padding: '16px 20px', marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>Новая роль</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="Название роли" value={newRoleLabel} onChange={e => setNewRoleLabel(e.target.value)} style={{ ...inp, width: 240 }} />
            <button onClick={handleCreateRole} disabled={creatingRole} style={primaryBtn}>{creatingRole ? '...' : 'Создать'}</button>
          </div>
          {roleError && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{roleError}</div>}
        </div>

        {loadingRoles ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
          <div style={{ ...card, padding: '14px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                Разделы — по вертикали, роли — по горизонтали. «Админ» имеет полный доступ и не настраивается.
              </div>
              <button onClick={handleSaveAll} disabled={savingAll} style={primaryBtn}>
                {savingAll ? 'Сохранение...' : 'Сохранить изменения'}
              </button>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 480 }}>
                <thead>
                  <tr>
                    <th style={{ ...th, position: 'sticky', left: 0, background: 'var(--bg-card)', zIndex: 2, minWidth: 260 }}>
                      Раздел / действие
                    </th>
                    {allRoles.map(r => {
                      const isAdmin = r.key === 'admin'
                      return (
                        <th key={r.id} style={{ ...th, textAlign: 'center', minWidth: 200, verticalAlign: 'top' }}>
                          {isAdmin ? (
                            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', textTransform: 'none', letterSpacing: 'normal', fontFamily: UI }}>{r.label}</div>
                          ) : (
                            <input value={roleLabels[r.id] ?? r.label}
                              onChange={e => setRoleLabels(prev => ({ ...prev, [r.id]: e.target.value }))}
                              style={{ ...inp, textAlign: 'center', fontWeight: 700, fontSize: 13, padding: '5px 8px' }} />
                          )}
                          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 4, textTransform: 'none', letterSpacing: 'normal', fontFamily: UI, fontWeight: 500 }}>
                            {r.is_system ? 'системная · ' : ''}{r.user_count} польз.
                          </div>
                          {!isAdmin && (
                            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'center', textTransform: 'none', letterSpacing: 'normal', fontFamily: UI, fontWeight: 500 }}>
                              <select value={roleGroups[r.id] ?? ''} onChange={e => setRoleGroups(prev => ({ ...prev, [r.id]: e.target.value }))}
                                title="Рабочая группа (для конструктора МП)"
                                style={{ ...sel, fontSize: 12, padding: '4px 6px', width: '100%', maxWidth: 180 }}>
                                {STAFF_GROUPS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                              </select>
                              {roleGroups[r.id] ? (
                                <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                                  <input type="checkbox" checked={!!roleMasters[r.id]}
                                    onChange={e => setRoleMasters(prev => ({ ...prev, [r.id]: e.target.checked }))}
                                    style={{ width: 15, height: 15, cursor: 'pointer' }} />
                                  мастер ★
                                </label>
                              ) : null}
                            </div>
                          )}
                          {!r.is_system && (
                            <button onClick={() => handleDeleteRole(r.id)}
                              style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', textTransform: 'none', letterSpacing: 'normal', fontFamily: UI, fontWeight: 600 }}>
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
                          {/* Липнет ЯРЛЫК ВНУТРИ ячейки, а не сама ячейка.
                              `position: sticky` на ячейке с colSpan не делает ничего:
                              она и так шириной во всю таблицу, смещать её некуда — и
                              название контура («Финансы», «Справочники») уезжало влево
                              вместе с колонками ролей. Ячейка остаётся растянутой ради
                              заливки на весь ряд, липкость переехала на внутренний блок,
                              которому есть куда смещаться внутри неё. */}
                          <td colSpan={allRoles.length + 1} style={{
                            background: 'var(--accent-tint)', padding: 0,
                            borderTop: '1px solid var(--border-row)' }}>
                            <div style={{ position: 'sticky', left: 0, display: 'inline-block',
                              padding: '7px 12px', fontSize: 12, fontWeight: 700,
                              color: 'var(--text-secondary)',
                              fontFamily: MONO, letterSpacing: '.06em', textTransform: 'uppercase' }}>
                              {row.label}
                            </div>
                          </td>
                        </tr>
                      )
                    }
                    const s = row.s
                    return (
                      <tr key={s.key}>
                        <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', zIndex: 1,
                          padding: '9px 12px', borderBottom: '1px solid var(--border-row)', fontSize: 13, color: 'var(--text-primary)' }}>
                          {s.label}
                        </td>
                        {allRoles.map(r => {
                          const isAdmin = r.key === 'admin'
                          return (
                            <td key={r.id} style={{ textAlign: 'center', padding: '6px 10px', borderBottom: '1px solid var(--border-row)' }}>
                              {isAdmin ? (
                                <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>{levelLabel(s, adminLevel(s))}</span>
                              ) : (
                                <select value={currentLevel(r.id, s)} onChange={e => setLevel(r.id, s, e.target.value)}
                                  style={{ ...sel, fontSize: 13, padding: '5px 8px', width: '100%', maxWidth: 200 }}>
                                  {levelsFor(s).map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                                </select>
                              )}
                              {s.actions.includes('approve') && !isAdmin && (
                                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginTop: 5, fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }} title="Право согласовывать/отклонять/архивировать МП">
                                  <input type="checkbox" checked={!!editingRolePerms[r.id]?.[s.key]?.approve}
                                    onChange={e => setEditingRolePerms(prev => ({ ...prev, [r.id]: { ...prev[r.id], [s.key]: { ...prev[r.id]?.[s.key], approve: e.target.checked } } }))} />
                                  согласование
                                </label>
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
    </>
  )
}
