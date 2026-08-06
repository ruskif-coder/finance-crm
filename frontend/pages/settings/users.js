import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { MONO, UI, card, inp, sel, th, td, primaryBtn } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'

// ── Пользователи — отдельная страница раздела «Настройки» ──
// Создание/редактирование/удаление пользователей + привязка к сотруднику Битрикс24.
// Логика перенесена 1:1 из pages/settings.js (вкладка «Пользователи»); изменён
// только HTTP-слой (синглтон api + auth()) и оформление (дизайн-токены).

export default function SettingsUsers() {
  const router = useRouter()
  const [selfId, setSelfId] = useState(null)
  const [allRoles, setAllRoles] = useState([])

  // Пользователи
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(true)
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

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (localStorage.getItem('role') !== 'admin') { router.push('/dashboard'); return }
    loadRoles()
    loadUsers()
    api.get('/auth/me', auth()).then(res => setSelfId(res.data.id)).catch(() => {})
  }, [])

  // Роли нужны для выпадающих списков «Роль» (создание + строки таблицы).
  const loadRoles = async () => {
    try {
      const res = await api.get('/roles/', auth())
      setAllRoles(res.data.roles)
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
  }

  const loadUsers = async () => {
    setLoadingUsers(true)
    try {
      const res = await api.get('/users/', auth())
      setUsers(res.data)
      const ed = {}
      res.data.forEach(u => { ed[u.id] = { name: u.name, email: u.email, role: u.role, is_active: u.is_active, password: '', bitrix_user_id: u.bitrix_user_id || '' } })
      setEditingUsers(ed)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoadingUsers(false)
    }
    loadBitrixUsers()
  }

  // Справочник пользователей Битрикса кэшируем в localStorage (TTL 12ч) — не дёргаем
  // Битрикс при каждом открытии вкладки «Пользователи». refresh=true — принудительно.
  const loadBitrixUsers = async (refresh = false) => {
    const CACHE_KEY = 'bitrix_users_cache_v1', TTL = 12 * 60 * 60 * 1000
    if (!refresh) {
      try {
        const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
        if (c && Array.isArray(c.items) && (Date.now() - c.ts) < TTL) {
          setBitrixUsers(c.items); setBxLoading(false); setBxError(''); return
        }
      } catch (e) {}
    }
    setBxLoading(true); setBxError('')
    try {
      const res = await api.get('/users/bitrix-directory', auth())
      const items = res.data.items || []
      setBitrixUsers(items)
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), items })) } catch (e) {}
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
    setCreatingUser(true)
    try {
      await api.post('/users/', newUser, auth())
      setNewUser({ name: '', email: '', password: '', role: 'viewer' })
      await loadUsers()
    } catch (e) {
      setUserError(e.response?.data?.detail || 'Ошибка при создании')
    } finally {
      setCreatingUser(false)
    }
  }

  const handleSaveUser = async (id) => {
    const ed = editingUsers[id]
    setSavingUsers(prev => ({ ...prev, [id]: true }))
    try {
      const payload = { name: ed.name, email: ed.email, role: ed.role, is_active: ed.is_active, bitrix_user_id: ed.bitrix_user_id || '' }
      if (ed.password) payload.password = ed.password
      await api.put(`/users/${id}`, payload, auth())
      await loadUsers()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении')
    } finally {
      setSavingUsers(prev => ({ ...prev, [id]: false }))
    }
  }

  const handleSaveAllUsers = async () => {
    setSavingAllUsers(true)
    let ok = 0; const errs = []
    for (const u of users) {
      const ed = editingUsers[u.id]
      if (!ed) continue
      try {
        const payload = { name: ed.name, email: ed.email, role: ed.role, is_active: ed.is_active, bitrix_user_id: ed.bitrix_user_id || '' }
        if (ed.password) payload.password = ed.password
        await api.put(`/users/${u.id}`, payload, auth())
        ok++
      } catch (e) { errs.push(`${u.name}: ${e.response?.data?.detail || 'ошибка'}`) }
    }
    await loadUsers()
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
    try {
      await api.delete(`/users/${id}`, auth())
      await loadUsers()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при удалении')
    }
  }

  // стили — общий модуль components/salesTableKit
  const rowBtn = { padding: '6px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13, background: 'var(--accent)', color: '#fff', fontFamily: UI }
  const iconBtn = { padding: '5px 8px', borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, color: 'var(--text-secondary)' }

  return (
    <>
      <Head><title>Пользователи | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="users" />

        {/* Форма создания */}
        <div style={{ ...card, padding: '16px 18px', marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>Новый пользователь</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="Имя" value={newUser.name} onChange={e => setNewUser(p => ({ ...p, name: e.target.value }))} style={{ ...inp, width: 160 }} />
            <input placeholder="Email" value={newUser.email} onChange={e => setNewUser(p => ({ ...p, email: e.target.value }))} style={{ ...inp, width: 200 }} />
            <input placeholder="Пароль" type="password" value={newUser.password} onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))} style={{ ...inp, width: 160 }} />
            <select value={newUser.role} onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))} style={sel}>
              {allRoles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
            <button onClick={handleCreateUser} disabled={creatingUser} style={primaryBtn}>{creatingUser ? '...' : 'Создать'}</button>
          </div>
          {userError && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{userError}</div>}
        </div>

        {/* Тулбар: скрыть деактивированных + массовое сохранение */}
        {!loadingUsers && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
            <label style={{ fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <input type="checkbox" checked={hideInactive} onChange={e => setHideInactive(e.target.checked)} /> скрыть деактивированных
            </label>
            <button onClick={handleSaveAllUsers} disabled={savingAllUsers} style={{ ...primaryBtn, marginLeft: 'auto' }}>
              {savingAllUsers ? 'Сохранение…' : 'Сохранить все'}
            </button>
          </div>
        )}

        {/* Таблица пользователей */}
        {loadingUsers ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
          <div style={{ ...card, padding: '14px 18px' }}>
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1000 }}>
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
                  const cur = ed.bitrix_user_id || ''
                  const known = bitrixUsers.some(b => String(b.id) === String(cur))
                  return (
                    <tr key={u.id}>
                      <td style={td}>
                        <input value={ed.name}
                          onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, name: e.target.value } }))}
                          style={{ ...inp, width: 160 }} />
                      </td>
                      <td style={td}>
                        <input type="email" value={ed.email}
                          onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, email: e.target.value } }))}
                          style={{ ...inp, width: 200 }} />
                      </td>
                      <td style={td}>
                        <select disabled={isSelf} value={ed.role}
                          onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, role: e.target.value } }))}
                          style={sel}>
                          {allRoles.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                        </select>
                      </td>
                      <td style={td}>
                        <button
                          disabled={isSelf}
                          onClick={() => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, is_active: !ed.is_active } }))}
                          style={{ padding: '5px 12px', borderRadius: 20, border: '1px solid ' + (ed.is_active ? 'var(--border-card)' : 'var(--danger-tint)'), cursor: isSelf ? 'default' : 'pointer', fontSize: 13, fontWeight: 600, fontFamily: UI, background: ed.is_active ? 'var(--bg-subtle)' : 'var(--danger-tint)', color: ed.is_active ? 'var(--success)' : 'var(--danger)' }}>
                          {ed.is_active ? 'Активен' : 'Деактивирован'}
                        </button>
                      </td>
                      <td style={td}>
                        <select value={cur}
                          onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, bitrix_user_id: e.target.value } }))}
                          disabled={bxLoading || (!!bxError && bitrixUsers.length === 0)}
                          title={bxError || ''}
                          style={{ ...sel, minWidth: 200 }}>
                          <option value="">{bxLoading ? 'загрузка…' : (bxError && bitrixUsers.length === 0 ? '⚠ ' + bxError : '— не привязан —')}</option>
                          {cur && !known && <option value={cur}>ID {cur} (не в списке)</option>}
                          {[...bitrixUsers].sort((a, b) => (a.active === b.active ? 0 : a.active ? -1 : 1)).map(b =>
                            <option key={b.id} value={b.id}>{b.name}{b.active ? '' : ' (уволен)'} · #{b.id}</option>)}
                        </select>
                      </td>
                      <td style={td}>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                          <input type={ed.showPw ? 'text' : 'password'} placeholder="не менять" value={ed.password}
                            onChange={e => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, password: e.target.value } }))}
                            style={{ ...inp, width: 150, fontFamily: ed.showPw ? MONO : UI }} />
                          <button title="Сгенерировать пароль (16 символов)"
                            onClick={() => setEditingUsers(prev => ({ ...prev, [u.id]: { ...ed, password: genPassword(16), showPw: true } }))}
                            style={iconBtn}>🎲</button>
                          {ed.password && (
                            <button title="Скопировать пароль"
                              onClick={() => copyText(ed.password)}
                              style={iconBtn}>📋</button>
                          )}
                        </div>
                      </td>
                      <td style={td}>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <button onClick={() => handleSaveUser(u.id)} disabled={savingUsers[u.id]} style={rowBtn}>
                            {savingUsers[u.id] ? '...' : 'Сохранить'}
                          </button>
                          {/* Удаление — только деактивированных и не себя (2026-07-16) */}
                          {!isSelf && !u.is_active && (
                            <button onClick={() => handleDeleteUser(u.id, u.name)} title="Удалить пользователя"
                              style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--danger-tint)', background: 'var(--danger-tint)', cursor: 'pointer', color: 'var(--danger)', fontSize: 14 }}>
                              🗑
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {!users.filter(u => !hideInactive || u.is_active).length && (
                  <tr><td colSpan={7} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Пользователей нет</td></tr>
                )}
              </tbody>
            </table>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
