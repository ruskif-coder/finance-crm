import { useState, useEffect, useMemo, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import { isAdmin } from '../../lib/auth'
import SettingsTabs from '../../components/SettingsTabs'
import { MONO, UI, Modal, Z, primaryBtn } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { detailText } from '@/lib/loadError'
import UserRow, { COLS } from '@/components/settings/users/UserRow'
import AccessOverview from '@/components/settings/users/AccessOverview'
import {
  GROUPS, groupOfRole, rolesOrdered, isMasterRole, genPassword, plural, draftOf, dirtyKeys, invalidRows, batchOf, sectionsOf,
} from '@/components/settings/users/usersModel'

// ── Пользователи — раздел «Настройки» (макет design_handoff_users, 16.11.2026) ──
// Как «Роли и доступы»: без нативных <select>, правки кликом по плашкам, одно «Сохранить N» на всю страницу —
// все правки уходят одним запросом `PUT /users/batch` и применяются одной транзакцией. Секции — по рабочей группе роли.
// Право — по-прежнему только администратор (`require_admin` на сервере).

const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
const pinStyle = (on) => ({ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 11px', borderRadius: 9,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
  color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap' })
const Num = ({ n }) => <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>

export default function SettingsUsers() {
  const router = useRouter()
  const [roles, setRoles] = useState([])
  const [profiles, setProfiles] = useState([])
  const [byRole, setByRole] = useState({})
  const [drafts, setDrafts] = useState([])
  const [origs, setOrigs] = useState({})
  const [pw, setPw] = useState({})
  const [removed, setRemoved] = useState([])
  const [selfId, setSelfId] = useState(null)
  const [f, setF] = useState({ q: '', status: 'all', group: '', role: '' })
  const [open, setOpen] = useState(null)          // { id, kind } — открытый список роли/профиля
  const [copied, setCopied] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [toDelete, setToDelete] = useState(null)
  const [accessOpen, setAccessOpen] = useState(false)
  const seq = useRef(0)
  const dirtyRef = useRef(false)
  const timers = useRef({})

  const rolesByKey = useMemo(() => Object.fromEntries(roles.map(r => [r.key, r])), [roles])
  const rolesList = useMemo(() => GROUPS.flatMap(g => rolesOrdered(roles.filter(r => groupOfRole(r) === g.id))), [roles])
  const counts = useMemo(() => drafts.reduce((m, d) => ({ ...m, [d.role]: (m[d.role] || 0) + 1 }), {}), [drafts])
  const keys = dirtyKeys(drafts, origs, pw, removed)
  const invalid = invalidRows(drafts)
  const canSave = keys.length > 0 && invalid.length === 0 && !saving
  dirtyRef.current = keys.length > 0

  const load = async () => {
    try {
      const [u, r, p, me] = await Promise.all([api.get('/users/', auth()), api.get('/roles/', auth()),
        api.get('/users/notification-profiles', auth()).catch(() => ({ data: { profiles: [], by_role: {} } })), api.get('/auth/me', auth())])
      const list = u.data.map(draftOf)
      setRoles(r.data.roles); setProfiles(p.data.profiles || []); setByRole(p.data.by_role || {}); setSelfId(me.data.id)
      setDrafts(list); setOrigs(Object.fromEntries(list.map(d => [d.id, d]))); setPw({}); setRemoved([])
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
      else setError(detailText(e, 'Не удалось загрузить пользователей'))
    } finally { setLoading(false) }
  }

  // Несохранённое не теряем: ни возвратом на вкладку (перечитывание), ни закрытием, ни уходом — как в «Ролях».
  useRefreshOnReturn(() => { if (!dirtyRef.current) load() })
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!isAdmin()) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, isAdmin())); return }
    load()
    const beforeUnload = (e) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = '' } }
    const beforeRoute = () => {
      if (dirtyRef.current && !window.confirm('Есть несохранённые изменения пользователей. Уйти без сохранения?')) {
        router.events.emit('routeChangeError'); throw 'пользователи: уход отменён'
      }
    }
    const outside = (e) => { if (!e.target.closest?.('[data-pop-root]')) setOpen(null) }
    window.addEventListener('beforeunload', beforeUnload)
    router.events.on('routeChangeStart', beforeRoute)
    document.addEventListener('mousedown', outside)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload); router.events.off('routeChangeStart', beforeRoute)
      document.removeEventListener('mousedown', outside)
    }
  }, [])

  const say = (t) => { setToast(t); clearTimeout(timers.current.toast); timers.current.toast = setTimeout(() => setToast(''), 2200) }

  // У новой строки профиль идёт за ролью, пока его не выбрали руками; у существующих — нет (роль — доступ, профиль — рассылка).
  const patch = (id, field, value) => setDrafts(prev => prev.map(d => {
    if (d.id !== id) return d
    const next = { ...d, [field]: value }
    if (field === 'role' && d.isNew && (d.pid || null) === (byRole[d.role] || null)) next.pid = byRole[value] || null
    return next
  }))

  const addUser = () => {
    seq.current += 1
    const id = `n${seq.current}`
    // Роль новой строки — самая людная рядовая роль продавцов (по макету — «Сейлз»), а не первая по алфавиту.
    const seller = [...roles.filter(r => groupOfRole(r) === 'seller' && !r.is_master)].sort((a, b) => (counts[b.key] || 0) - (counts[a.key] || 0))[0]
      || rolesList[0]
    const role = seller ? seller.key : 'viewer'
    setDrafts(prev => [{ id, name: '', email: '', role, active: true, pid: byRole[role] || null, isNew: true }, ...prev])
    setPw(prev => ({ ...prev, [id]: genPassword() }))
  }

  const dropRow = (id) => {
    setDrafts(prev => prev.filter(d => d.id !== id))
    setPw(prev => { const p = { ...prev }; delete p[id]; return p })
  }
  const remove = (d) => { if (d.isNew) dropRow(d.id); else if (!d.active && origs[d.id] && !origs[d.id].active) setToDelete(d) }   // только сохранённый деактивированный
  const confirmDelete = () => { setRemoved(prev => [...prev, toDelete.id]); dropRow(toDelete.id); setToDelete(null) }

  const copy = (id) => {
    try { const pr = navigator.clipboard && navigator.clipboard.writeText(pw[id]); pr && pr.catch(() => {}) } catch (e) { /* без буфера — пароль виден на экране */ }
    setCopied(id); clearTimeout(timers.current.copy); timers.current.copy = setTimeout(() => setCopied(null), 2000)
  }

  const save = async () => {
    if (!canSave) return
    setSaving(true); setError('')
    try {
      await api.put('/users/batch', { changes: batchOf(drafts, origs, pw, removed) }, auth())
      const n = keys.length
      await load()
      say(`Сохранено: ${plural(n, 'изменение', 'изменения', 'изменений')}`)
    } catch (e) {
      setError(detailText(e, 'Ошибка при сохранении — ничего не сохранено'))
    } finally { setSaving(false) }
  }

  const sections = sectionsOf(drafts, rolesByKey, f)
  const rowsShown = sections.reduce((n, s) => n + s.rows.length, 0)
  const active = drafts.filter(d => d.active).length
  const inGroup = (g) => drafts.filter(d => groupOfRole(rolesByKey[d.role]) === g).length
  let ord = 0

  return (
    <>
      <Head><title>Пользователи · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 22px', background: 'var(--bg-canvas)', height: '100vh', boxSizing: 'border-box',
        display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
        <SettingsTabs active="users" />

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-primary)' }}>Пользователи</span>
            <span style={{ ...cap, fontSize: 10 }}>
              {plural(drafts.length, 'пользователь', 'пользователя', 'пользователей')} · активных {active} · деактивировано {drafts.length - active}
            </span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {keys.length > 0 && invalid.length > 0 && <span style={{ fontSize: 11.5, color: 'var(--warning-fg)' }}>заполните имя и email: {invalid.length}</span>}
            <button type="button" onClick={() => setAccessOpen(true)} className="u-add"
              title="Оба контура одним списком: ядро и кабинеты паблишеров — только чтение"
              style={{ ...plain, display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 14px', background: 'var(--bg-card)',
                border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
              Кто имеет доступ</button>
            <button type="button" onClick={addUser} className="u-add"
              style={{ ...plain, display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 14px', background: 'var(--bg-card)',
                border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
              + Пользователь</button>
            <button type="button" onClick={save} disabled={!canSave}
              title={canSave ? 'Сохранить все изменения одним запросом' : keys.length ? 'Есть строки без имени или с неверным email' : 'Изменений нет'}
              style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 16px', borderRadius: 12, fontSize: 13,
                fontWeight: 700, background: canSave ? 'var(--accent)' : 'var(--text-disabled)', cursor: canSave ? 'pointer' : 'not-allowed' }}>
              {saving ? 'Сохранение…' : 'Сохранить'}
              {keys.length > 0 && !saving && (
                <span style={{ minWidth: 18, height: 18, padding: '0 5px', borderRadius: 6, background: 'rgba(255,255,255,.22)', fontFamily: MONO,
                  fontSize: 10, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{keys.length}</span>
              )}
            </button>
          </span>
        </div>

        {!!error && (
          <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger-border)', color: 'var(--danger-fg)', borderRadius: 12, padding: '8px 14px', fontSize: 12.5 }}>{error}</div>
        )}

        <div data-no-unsaved style={{ display: 'flex', alignItems: 'center', gap: '10px 14px', flexWrap: 'wrap' }}>
          <input value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Имя или email" aria-label="Поиск" type="search"
            style={{ width: 220, height: 32, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: UI, color: 'var(--text-primary)' }} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {[['all', 'Все', drafts.length], ['on', 'Активные', active], ['off', 'Деактивированные', drafts.length - active]].map(([v, l, n]) => (
              <button key={v} type="button" onClick={() => setF({ ...f, status: v })} style={pinStyle(f.status === v)}>{l}<Num n={n} /></button>
            ))}
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <span style={{ ...cap, paddingRight: 4 }}>Группы</span>
            <button type="button" onClick={() => setF({ ...f, group: '', role: '' })} style={pinStyle(!f.group && !f.role)}>Все<Num n={drafts.length} /></button>
            {GROUPS.filter(g => inGroup(g.id) > 0).map(g => (
              <button key={g.id} type="button" onClick={() => setF({ ...f, group: f.group === g.id ? '' : g.id, role: '' })}
                style={pinStyle(f.group === g.id)}>{g.title}<Num n={inGroup(g.id)} /></button>
            ))}
          </span>
        </div>

        <div style={{ flex: '1 1 auto', minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, overflow: 'auto' }}>
          {loading ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
            <div style={{ minWidth: 1320 }}>
              <div style={{ position: 'sticky', top: 0, zIndex: 5, display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center',
                padding: '12px 20px 10px', background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)', ...cap }}>
                <span /><span style={{ paddingLeft: 9 }}>Имя</span><span style={{ paddingLeft: 9 }}>Email</span><span>Роль</span><span>Статус</span>
                <span>Профиль уведомлений</span><span>Пароль</span><span />
              </div>
              {sections.map(s => {
                const act = s.rows.filter(d => d.active).length
                return (
                  <div key={s.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 20px 7px 46px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>{s.title}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)' }}>
                        {plural(s.rows.length, 'человек', 'человека', 'человек')}{act < s.rows.length ? ` · активных ${act}` : ''}
                      </span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                        {s.roles.filter(r => counts[r.key]).map(r => {
                          const on = f.role === r.key
                          return (
                            <button key={r.key} type="button" title="Показать только эту роль" onClick={() => setF({ ...f, role: on ? '' : r.key })}
                              style={{ ...plain, display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 7px', borderRadius: 6,
                                background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                                fontSize: 11, fontWeight: on ? 700 : 600, color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                              {r.label}{isMasterRole(r) ? ' ★' : ''}<span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{counts[r.key]}</span>
                            </button>
                          )
                        })}
                      </span>
                    </div>
                    {s.rows.map(d => {
                      const idx = ord++
                      const me = d.id === selfId
                      return (
                        <UserRow key={d.id} d={d} savedActive={!!(origs[d.id] && origs[d.id].active)} me={me} changed={keys.some(k => k.startsWith(`${d.id}:`))} roles={rolesList} rolesByKey={rolesByKey}
                          counts={counts} profiles={profiles} pw={pw[d.id]} copied={copied === d.id}
                          open={open && open.id === d.id ? open.kind : ''} setOpen={kind => setOpen(kind ? { id: d.id, kind } : null)}
                          up={idx > rowsShown - 6 && idx > 8} onPatch={(field, v) => patch(d.id, field, v)}
                          onGenPw={() => setPw(prev => ({ ...prev, [d.id]: genPassword() }))}
                          onClearPw={() => setPw(prev => { const p = { ...prev }; delete p[d.id]; return p })}
                          onCopy={() => copy(d.id)} onRemove={() => remove(d)} />
                      )
                    })}
                  </div>
                )
              })}
              {rowsShown === 0 && <div style={{ padding: '36px 20px', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Никого не нашлось — измените поиск или фильтр</div>}
            </div>
          )}
        </div>
      </div>
      <style jsx global>{`
        .u-row:hover { background: var(--bg-tint) !important }
        .u-inline:hover:not([data-bad]), .u-inline:focus:not([data-bad]) { border-color: var(--border-card) !important; background: var(--bg-card) !important }
        .u-inline:focus:not([data-bad]) { border-color: var(--accent) !important }
        .u-opt:hover { background: var(--bg-subtle) !important }
        .u-link:hover, .u-add:hover { color: var(--accent) !important }
        .u-add:hover { border-color: var(--border-hover) !important }
        .u-quiet:hover { color: var(--text-secondary) !important }
        .u-danger:hover { color: var(--danger) !important }
      `}</style>

      {!!toast && (
        <div role="status" style={{ position: 'fixed', right: 24, bottom: 24, zIndex: Z.toast, background: 'var(--text-primary)', color: 'var(--bg-card)',
          padding: '11px 16px', borderRadius: 12, fontSize: 13, fontWeight: 600, boxShadow: 'var(--shadow-modal)' }}>{toast}</div>
      )}

      {accessOpen && <AccessOverview onClose={() => setAccessOpen(false)} />}

      {toDelete && (
        <Modal title={`Удалить пользователя «${toDelete.name}»?`} width={460} onClose={() => setToDelete(null)}
          footer={<>
            <button type="button" onClick={() => setToDelete(null)} style={{ ...plain, height: 34, padding: '0 14px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, color: 'var(--text-secondary)' }}>Отмена</button>
            <button type="button" onClick={confirmDelete} style={{ ...plain, marginLeft: 'auto', height: 34, padding: '0 14px', borderRadius: 10, fontSize: 13, fontWeight: 700, background: 'var(--danger)', color: 'var(--bg-card)' }}>Удалить при сохранении</button>
          </>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Учётка {toDelete.email} будет удалена при нажатии «Сохранить». Записи журнала действий останутся с его именем.
            Если у пользователя есть созданные им операции, система удалить не даст — тогда оставьте его деактивированным.
          </div>
        </Modal>
      )}
    </>
  )
}
