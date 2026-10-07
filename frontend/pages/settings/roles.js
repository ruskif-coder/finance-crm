import { useState, useEffect, useMemo, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import { isAdmin } from '../../lib/auth'
import SettingsTabs from '../../components/SettingsTabs'
import { MONO, UI, Modal, primaryBtn } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { flagsForLevel } from '../../lib/roleLevels.mjs'

// ── Роли и права доступа — раздел «Настройки» ──
// Матрица «раздел × роль»: уровень доступа — плашка, клик по тексту переключает на следующий,
// «удаление» и «согласование» — квадраты внутри плашки. Уровни маппятся на булевы поля бэкенда
// (can_view/edit/…) + deals_scope; раскладку держит lib/roleLevels.mjs (стережёт check-role-levels).

// Секции с 5-уровневым доступом (свои/все). Каждая привязана к «группе scope»:
// продажи (общий deals_scope на три секции), медиапланы, годовой план, дашборд аккаунта.
const SCOPE_GROUP = {
  sales_dashboard: 'sales', sales_registry: 'sales', sales_analytics: 'sales',
  media_plans: 'mp', media_plans_editor: 'mp',
  year_plan: 'yp',
  accounts_dashboard: 'acc',
}
const SCOPED_KEYS = Object.keys(SCOPE_GROUP)

// Рабочая группа роли (для конструктора МП): кто продавец / аккаунт / трафик.
const STAFF_GROUPS = [{ v: '', l: 'не в группе' }, { v: 'seller', l: 'Продавцы' }, { v: 'account', l: 'Аккаунты' }, { v: 'traffic', l: 'Трафики' }]

const LEVELS_VIEW = ['none', 'view']
const LEVELS_EDIT = ['none', 'view', 'edit']
const LEVELS_SCOPED = ['none', 'view_own', 'view_all', 'edit_own', 'edit_all']
// [подпись, фон, рамка, текст, насыщенность]
const LOOK = {
  none:      ['нет', 'var(--bg-card)', 'var(--border-inner)', 'var(--text-disabled)', 500],
  view:      ['просмотр', 'var(--bg-subtle)', 'var(--border-card)', 'var(--text-secondary)', 600],
  view_own:  ['просмотр · свои', 'var(--bg-subtle)', 'var(--border-card)', 'var(--text-secondary)', 600],
  view_all:  ['просмотр · все', 'var(--bg-subtle)', 'var(--border-card)', 'var(--text-secondary)', 600],
  edit:      ['редактирование', 'var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)', 700],
  edit_own:  ['редактирование · свои', 'var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)', 700],
  edit_all:  ['редактирование · все', 'var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)', 700],
}
const LEGEND = ['none', 'view', 'edit', 'edit_all']

const isScoped = (s) => SCOPED_KEYS.includes(s.key)
const levelsFor = (s) => isScoped(s) ? LEVELS_SCOPED : (s.actions.some(a => a !== 'view') ? LEVELS_EDIT : LEVELS_VIEW)
const isEditLevel = (lv) => String(lv).startsWith('edit')

const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }

// Состояние одной роли целиком: всё, что можно поправить на странице.
const draftOf = (r) => ({
  label: r.label,
  group: r.staff_group || '',
  master: !!r.is_master,
  scopes: { sales: r.deals_scope || 'all', mp: r.mp_scope || 'all', yp: r.year_plan_scope || 'all', acc: r.acc_scope || 'all' },
  perms: JSON.parse(JSON.stringify(r.permissions)),
})

function levelOf(d, s) {
  const p = d.perms[s.key] || {}
  if (!p.view) return 'none'
  if (isScoped(s)) return (p.edit ? 'edit_' : 'view_') + (d.scopes[SCOPE_GROUP[s.key]] === 'own' ? 'own' : 'all')
  return s.actions.some(a => a !== 'view' && p[a]) ? 'edit' : 'view'
}

// Что изменилось в роли: список ярлыков изменённых мест (по одному на поле / на раздел).
function changesOf(d, o, sections) {
  if (!o) return []
  const out = []
  if (d.label !== o.label) out.push('name')
  if (d.group !== o.group) out.push('group')
  if (d.master !== o.master) out.push('master')
  sections.forEach(s => {
    const a = d.perms[s.key] || {}, b = o.perms[s.key] || {}
    if (levelOf(d, s) !== levelOf(o, s) || !!a.delete !== !!b.delete || !!a.approve !== !!b.approve) out.push(s.key)
  })
  return out
}

function Flag({ on, onClick, title, color, diamond }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={on}
      style={{ ...plain, flex: '0 0 16px', width: 16, height: 16, marginLeft: 4, borderRadius: 4,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: on ? color : 'var(--bg-card)', border: `1px solid ${on ? color : 'var(--border-hover)'}`,
        transform: diamond ? 'rotate(45deg)' : 'none', transition: 'background-color 120ms ease' }}>
      {on && <span style={{ color: 'var(--bg-card)', fontSize: 9, fontWeight: 700, transform: diamond ? 'rotate(-45deg)' : 'none' }}>✓</span>}
    </button>
  )
}

export default function SettingsRoles() {
  const router = useRouter()
  const [roles, setRoles] = useState([])        // без админа
  const [sections, setSections] = useState([])
  const [drafts, setDrafts] = useState({})      // { roleId: draft }
  const [origs, setOrigs] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState([])
  const [okAt, setOkAt] = useState(0)
  const [pin, setPin] = useState('')            // фильтр по группе разделов
  const [newLabel, setNewLabel] = useState('')
  const [creating, setCreating] = useState(false)
  const [toDelete, setToDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const dirtyRef = useRef(false)

  const changes = useMemo(() => {
    const m = {}
    roles.forEach(r => { m[r.id] = changesOf(drafts[r.id], origs[r.id], sections) })
    return m
  }, [roles, drafts, origs, sections])
  const dirtyCount = Object.values(changes).reduce((n, c) => n + c.length, 0)
  dirtyRef.current = dirtyCount > 0

  // Несохранённое не теряем: ни возвратом на вкладку (перечитывание), ни закрытием, ни уходом.
  useRefreshOnReturn(() => { if (!dirtyRef.current) loadRoles() })
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!isAdmin()) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, isAdmin())); return }
    loadRoles()
    const beforeUnload = (e) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = '' } }
    const beforeRoute = () => {
      if (dirtyRef.current && !window.confirm('Есть несохранённые изменения ролей. Уйти без сохранения?')) {
        router.events.emit('routeChangeError'); throw 'роли: уход отменён'
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    router.events.on('routeChangeStart', beforeRoute)
    return () => { window.removeEventListener('beforeunload', beforeUnload); router.events.off('routeChangeStart', beforeRoute) }
  }, [])

  const loadRoles = async () => {
    try {
      const res = await api.get('/roles/', auth())
      const list = res.data.roles.filter(r => r.key !== 'admin')
      const d = {}
      list.forEach(r => { d[r.id] = draftOf(r) })
      setRoles(list); setSections(res.data.sections); setDrafts(d); setOrigs(JSON.parse(JSON.stringify(d)))
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const patch = (id, fn) => setDrafts(prev => ({ ...prev, [id]: fn(prev[id]) }))

  const setLevel = (id, s, level) => patch(id, d => {
    const scopes = isScoped(s) ? { ...d.scopes, [SCOPE_GROUP[s.key]]: level.endsWith('own') ? 'own' : 'all' } : d.scopes
    return { ...d, scopes, perms: { ...d.perms, [s.key]: flagsForLevel(s, level, d.perms[s.key] || {}, isScoped(s)) } }
  })
  const cycle = (id, s) => {
    const list = levelsFor(s), cur = levelOf(drafts[id], s)
    setLevel(id, s, list[(list.indexOf(cur) + 1) % list.length])
  }
  const setFlag = (id, s, action) => patch(id, d => ({
    ...d, perms: { ...d.perms, [s.key]: { ...d.perms[s.key], [action]: !d.perms[s.key]?.[action] } },
  }))
  const cycleGroup = (id) => patch(id, d => {
    const i = STAFF_GROUPS.findIndex(g => g.v === d.group)
    const group = STAFF_GROUPS[(i + 1) % STAFF_GROUPS.length].v
    return { ...d, group }
  })

  const payload = (d) => ({
    label: d.label,
    staff_group: d.group || '',
    is_master: !!d.master,
    permissions: sections.map(s => ({
      section: s.key,
      can_view: s.actions.includes('view') ? !!d.perms[s.key]?.view : undefined,
      can_create: s.actions.includes('create') ? !!d.perms[s.key]?.create : undefined,
      can_edit: s.actions.includes('edit') ? !!d.perms[s.key]?.edit : undefined,
      can_delete: s.actions.includes('delete') ? !!d.perms[s.key]?.delete : undefined,
      can_view_operations: s.actions.includes('view_operations') ? !!d.perms[s.key]?.view_operations : undefined,
      can_approve: s.actions.includes('approve') ? !!d.perms[s.key]?.approve : undefined,
      deals_scope: isScoped(s) ? (d.scopes[SCOPE_GROUP[s.key]] || 'all') : undefined,
    })),
  })

  // Сохраняются только изменённые роли: чужие не переписываются.
  const save = async () => {
    if (!dirtyCount || saving) return
    setSaving(true); setErrors([])
    const failed = []
    for (const r of roles) {
      if (!changes[r.id].length) continue
      try { await api.put(`/roles/${r.id}`, payload(drafts[r.id]), auth()) }
      catch (e) { failed.push(`${drafts[r.id].label || r.label}: ${e.response?.data?.detail || 'ошибка при сохранении'}`) }
    }
    await loadRoles()
    setSaving(false); setErrors(failed); if (!failed.length) setOkAt(Date.now())
  }

  const createRole = async () => {
    const label = newLabel.trim()
    if (!label) { setErrors(['Введите название роли']); return }
    setCreating(true); setErrors([])
    try {
      const res = await api.post('/roles/', { label }, auth())
      setNewLabel('')
      // Новая роль добавляется, а правки в остальных остаются.
      const all = await api.get('/roles/', auth())
      const r = all.data.roles.find(x => x.id === res.data.id)
      if (r) {
        setRoles(prev => [...prev, r])
        setDrafts(prev => ({ ...prev, [r.id]: draftOf(r) }))
        setOrigs(prev => ({ ...prev, [r.id]: draftOf(r) }))
      }
    } catch (e) {
      setErrors([e.response?.data?.detail || 'Ошибка при создании роли'])
    } finally { setCreating(false) }
  }

  const removeRole = async () => {
    setDeleting(true)
    try {
      await api.delete(`/roles/${toDelete.id}`, auth())
      const id = toDelete.id
      setRoles(prev => prev.filter(r => r.id !== id))
      setToDelete(null)
    } catch (e) {
      setErrors([e.response?.data?.detail || 'Ошибка при удалении роли']); setToDelete(null)
    } finally { setDeleting(false) }
  }

  // Группы разделов в порядке появления; пины фильтруют строки.
  const groups = useMemo(() => {
    const out = []
    sections.forEach(s => {
      const g = s.group || 'Прочее'
      let x = out.find(o => o.name === g)
      if (!x) { x = { name: g, items: [] }; out.push(x) }
      x.items.push(s)
    })
    return out
  }, [sections])
  const shown = pin ? groups.filter(g => g.name === pin) : groups

  const nUsers = roles.reduce((n, r) => n + (r.user_count || 0), 0)
  const cols = `260px repeat(${roles.length}, 210px)`
  const canSave = dirtyCount > 0 && !saving
  const pinStyle = (on) => ({ ...plain, display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px', borderRadius: 9,
    background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
    color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 500, whiteSpace: 'nowrap' })

  return (
    <>
      <Head><title>Роли · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 22px', background: 'var(--bg-canvas)', height: '100vh', boxSizing: 'border-box',
        display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
        <SettingsTabs active="roles" />

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-primary)' }}>Роли и доступы</span>
            <span style={cap}>{roles.length} ролей · {nUsers} пользователей · админ не настраивается</span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {!!okAt && !dirtyCount && <span style={{ fontSize: 12, color: 'var(--income-fg)' }}>Сохранено</span>}
            <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Название новой роли"
              onKeyDown={e => { if (e.key === 'Enter') createRole() }}
              style={{ width: 220, height: 36, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 13, outline: 'none', fontFamily: UI, color: 'var(--text-primary)' }} />
            <button type="button" onClick={createRole} disabled={creating}
              style={{ ...plain, display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 14px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
              {creating ? '…' : '+ Роль'}
            </button>
            <button type="button" onClick={save} disabled={!canSave}
              style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 16px', borderRadius: 12, fontSize: 13, fontWeight: 700,
                opacity: canSave ? 1 : 0.45, cursor: canSave ? 'pointer' : 'default' }}>
              {saving ? 'Сохранение…' : 'Сохранить'}
              {dirtyCount > 0 && !saving && (
                <span style={{ minWidth: 18, height: 18, padding: '0 5px', borderRadius: 6, background: 'rgba(255,255,255,.22)', fontFamily: MONO, fontSize: 10, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{dirtyCount}</span>
              )}
            </button>
          </span>
        </div>

        {errors.length > 0 && (
          <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger-border)', color: 'var(--danger-fg)', borderRadius: 12, padding: '8px 14px', fontSize: 12.5 }}>
            {errors.map((e, i) => <div key={i}>{e}</div>)}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ ...cap, paddingRight: 4 }}>Легенда</span>
            {LEGEND.map(k => (
              <span key={k} style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 9px', borderRadius: 7, background: LOOK[k][1], border: `1px solid ${LOOK[k][2]}`, color: LOOK[k][3], fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap' }}>
                {k === 'edit_all' ? 'редактирование · все' : LOOK[k][0]}
              </span>
            ))}
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)', paddingLeft: 6 }}>клик по плашке — следующий уровень · ■ удаление · ◆ согласование · «свои» — сделки своей группы</span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ ...cap, paddingRight: 4 }}>Разделы</span>
            <button type="button" onClick={() => setPin('')} style={pinStyle(!pin)}>Все</button>
            {groups.map(g => <button key={g.name} type="button" onClick={() => setPin(g.name)} style={pinStyle(pin === g.name)}>{g.name}</button>)}
          </span>
        </div>

        <div style={{ flex: '1 1 auto', minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, overflow: 'auto' }}>
          {loading ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
            <div style={{ minWidth: 'max-content' }}>
              {/* шапка ролей */}
              <div style={{ position: 'sticky', top: 0, zIndex: 5, display: 'grid', gridTemplateColumns: cols, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)' }}>
                <span style={{ position: 'sticky', left: 0, zIndex: 6, background: 'var(--bg-card)', padding: '14px 20px 10px', borderRight: '1px solid var(--border-inner)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 2 }}>
                  <span style={cap}>Раздел · действие</span>
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>Администратор — полный доступ, не настраивается</span>
                </span>
                {roles.map(r => {
                  const d = drafts[r.id]
                  if (!d) return null
                  const grp = STAFF_GROUPS.find(g => g.v === d.group)
                  const changed = changes[r.id].length > 0
                  return (
                    <div key={r.id} style={{ padding: '12px 10px 10px', display: 'flex', flexDirection: 'column', gap: 6, borderRight: '1px solid var(--border-row)', background: r.is_system ? 'var(--bg-subtle)' : 'var(--bg-card)', minWidth: 0 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                        <input value={d.label} onChange={e => patch(r.id, x => ({ ...x, label: e.target.value }))} aria-label="Название роли"
                          style={{ flex: 1, minWidth: 0, height: 28, boxSizing: 'border-box', padding: '0 8px', background: 'transparent', border: '1px solid transparent', borderRadius: 8, fontSize: 13, fontWeight: 700, outline: 'none', fontFamily: UI, color: 'var(--text-primary)' }}
                          onFocus={e => { e.target.style.borderColor = 'var(--accent)'; e.target.style.background = 'var(--bg-card)' }}
                          onBlur={e => { e.target.style.borderColor = 'transparent'; e.target.style.background = 'transparent' }} />
                        {d.master && !!d.group && <span title="Мастер группы — видит сделки всей группы" style={{ fontSize: 12, color: 'var(--warning)', flex: '0 0 auto' }}>★</span>}
                        {changed && <span title="Есть несохранённые правки" style={{ width: 7, height: 7, borderRadius: 4, background: 'var(--accent)', flex: '0 0 auto' }} />}
                      </span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 2px', fontFamily: MONO, fontSize: 9.5, letterSpacing: '.04em', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                        <span>{r.user_count} польз.</span>
                        <span style={{ color: 'var(--text-disabled)' }}>·</span>
                        <button type="button" onClick={() => cycleGroup(r.id)} title="Рабочая группа роли (для конструктора МП) — клик меняет"
                          style={{ ...plain, fontFamily: MONO, fontSize: 9.5, letterSpacing: '.04em', color: d.group ? 'var(--accent-fg)' : 'var(--text-faint)' }}>
                          {grp ? grp.l : 'не в группе'}
                        </button>
                      </span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 2px' }}>
                        {d.group ? (
                          <button type="button" onClick={() => patch(r.id, x => ({ ...x, master: !x.master }))} title="Мастер группы — видит сделки всей группы"
                            style={{ ...plain, display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10.5, color: d.master ? 'var(--text-primary)' : 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                            <span style={{ width: 14, height: 14, borderRadius: 4, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: d.master ? 'var(--accent)' : 'var(--bg-card)', border: `1px solid ${d.master ? 'var(--accent)' : 'var(--border-hover)'}` }}>
                              {d.master && <span style={{ color: 'var(--bg-card)', fontSize: 9, fontWeight: 700 }}>✓</span>}
                            </span>
                            мастер
                          </button>
                        ) : <span style={{ fontSize: 10.5, color: 'var(--text-disabled)' }}>мастер — после выбора группы</span>}
                        {r.is_system
                          ? <span style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--text-disabled)' }}>системная</span>
                          : <button type="button" onClick={() => setToDelete(r)} style={{ ...plain, marginLeft: 'auto', fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}
                              onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-faint)' }}>удалить</button>}
                      </span>
                    </div>
                  )
                })}
              </div>

              {shown.map(g => (
                <div key={g.name}>
                  <div style={{ display: 'grid', gridTemplateColumns: cols, background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
                    <span style={{ position: 'sticky', left: 0, zIndex: 4, background: 'var(--bg-subtle)', padding: '7px 20px', borderRight: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>{g.name}</span>
                    {roles.map(r => {
                      const open = drafts[r.id] ? g.items.filter(s => levelOf(drafts[r.id], s) !== 'none').length : 0
                      return <span key={r.id} style={{ padding: '7px 10px', borderRight: '1px solid var(--border-row)', fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{open ? `${open} из ${g.items.length}` : '—'}</span>
                    })}
                  </div>
                  {g.items.map(s => (
                    <div key={s.key} className="roles-row" style={{ display: 'grid', gridTemplateColumns: cols, borderBottom: '1px solid var(--border-row)' }}>
                      <span style={{ position: 'sticky', left: 0, zIndex: 3, background: 'var(--bg-card)', padding: '0 20px', minHeight: 40, borderRight: '1px solid var(--border-inner)', display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                        <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.label}</span>
                        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4, flex: '0 0 auto' }}>
                          {s.actions.includes('delete') && <span title="У раздела есть право удаления" style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--text-disabled)' }} />}
                          {s.actions.includes('approve') && <span title="У раздела есть право согласования" style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--text-disabled)', transform: 'rotate(45deg)' }} />}
                        </span>
                      </span>
                      {roles.map(r => {
                        const d = drafts[r.id]
                        if (!d) return <span key={r.id} />
                        const lv = levelOf(d, s)
                        const [label, bg, border, fg, weight] = LOOK[lv]
                        const list = levelsFor(s)
                        const next = LOOK[list[(list.indexOf(lv) + 1) % list.length]][0]
                        const p = d.perms[s.key] || {}
                        const canDelete = s.actions.includes('delete') && isEditLevel(lv)
                        const canApprove = s.actions.includes('approve') && (isEditLevel(lv) || !!p.approve)
                        const dirty = changes[r.id].includes(s.key)
                        return (
                          <span key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '0 10px', borderRight: '1px solid var(--border-row)', minWidth: 0 }}>
                            <span style={{ display: 'flex', alignItems: 'center', flex: '1 1 auto', minWidth: 0, height: 26, boxSizing: 'border-box', padding: '0 4px 0 8px', borderRadius: 7, background: bg, border: `1px solid ${dirty ? 'var(--accent)' : border}`, transition: 'background-color 120ms ease' }}>
                              <button type="button" onClick={() => cycle(r.id, s)} title={`Клик — «${next}»`}
                                style={{ ...plain, flex: '1 1 auto', minWidth: 0, color: fg, fontSize: 11, fontWeight: weight, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', userSelect: 'none' }}>{label}</button>
                              {canDelete && <Flag on={!!p.delete} color="var(--danger)" onClick={() => setFlag(r.id, s, 'delete')}
                                title={p.delete ? 'Может удалять записи раздела — клик снимет' : 'Не может удалять: убрать вложение, отвязать связь или сбросить значение — это правка, а не удаление'} />}
                              {canApprove && <Flag on={!!p.approve} diamond color="var(--income)" onClick={() => setFlag(r.id, s, 'approve')}
                                title={p.approve ? 'Может согласовывать, отклонять и архивировать — клик снимет' : 'Не может согласовывать'} />}
                            </span>
                          </span>
                        )
                      })}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <style jsx global>{`.roles-row:hover > span:not(:first-child) { background: var(--bg-tint) }`}</style>

      {toDelete && (
        <Modal title={`Удалить роль «${toDelete.label}»?`} width={460} onClose={() => setToDelete(null)}
          footer={<>
            <button type="button" onClick={() => setToDelete(null)} style={{ ...plain, height: 34, padding: '0 14px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, color: 'var(--text-secondary)' }}>Отмена</button>
            <button type="button" onClick={removeRole} disabled={deleting || toDelete.user_count > 0} style={{ ...plain, opacity: toDelete.user_count > 0 ? 0.4 : 1, marginLeft: 'auto', height: 34, padding: '0 14px', borderRadius: 10, fontSize: 13, fontWeight: 700, background: 'var(--danger)', color: 'var(--bg-card)' }}>{deleting ? 'Удаляю…' : 'Удалить роль'}</button>
          </>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            {toDelete.user_count > 0
              ? <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger-border)', color: 'var(--danger-fg)', borderRadius: 10, padding: '8px 12px' }}>
                  У роли {toDelete.user_count} польз. — система не даст её удалить, пока они в ней. Сначала переведите их на другую роль.
                </div>
              : 'Роль без пользователей. Права роли будут стёрты, вернуть их можно только заново.'}
          </div>
        </Modal>
      )}
    </>
  )
}
