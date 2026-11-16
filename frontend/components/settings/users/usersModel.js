// Логика экрана «Пользователи» (макет design_handoff_users, 16.11.2026) — без React, чтобы её было видно целиком.
//
// Группы — из рабочей группы РОЛИ (`Role.staff_group`, правится в «Ролях»), а не своим списком: роль переедет в другую
// группу там — переедет и здесь. Секции, которых нет у ролей, не выдумываются (в макете были «Финансы» — у ролей такой
// группы нет, Фин Менеджер и Бухгалтер попадают во «Вне групп»).

export const GROUPS = [
  { id: 'seller', title: 'Продавцы' },
  { id: 'account', title: 'Аккаунты' },
  { id: 'traffic', title: 'Трафики' },
  { id: 'other', title: 'Вне групп' },
]
const KNOWN = new Set(['seller', 'account', 'traffic'])
export const groupOfRole = (role) => (role && KNOWN.has(role.staff_group) ? role.staff_group : 'other')

// Порядок ролей внутри группы: мастер первым, дальше по названию; «Администратор» — первым во «Вне групп».
export function rolesOrdered(roles) {
  return [...roles].sort((a, b) => (b.key === 'admin') - (a.key === 'admin') || (!!b.is_master) - (!!a.is_master)
    || String(a.label).localeCompare(String(b.label), 'ru'))
}

export const emailOk = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(e || '').trim())
export const isMasterRole = (role) => !!role && !!role.is_master && KNOWN.has(role.staff_group)

// Пароль показывается один раз, до сохранения. 12 знаков в три блока, без похожих символов (0/O, 1/l/I).
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
export function genPassword() {
  const bytes = new Uint32Array(12)
  window.crypto.getRandomValues(bytes)
  let s = ''
  bytes.forEach((b, i) => { s += (i === 4 || i === 8 ? '-' : '') + ALPHABET[b % ALPHABET.length] })
  return s
}

export const plural = (n, a, b, c) => {
  const m = n % 10, h = n % 100
  return `${n} ${h >= 11 && h <= 14 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c}`
}

// Черновик строки — то, что можно поправить на экране. `pid` — профиль уведомлений (null — по умолчанию).
export const draftOf = (u) => ({ id: u.id, name: u.name || '', email: u.email || '', role: u.role,
  active: !!u.is_active, pid: u.notification_profile_id || null, isNew: false })

// Что изменилось: ключи «id:поле», как в макете; счётчик на кнопке — их число.
export function dirtyKeys(drafts, origs, pw, removed) {
  const keys = []
  drafts.forEach(d => {
    if (d.isNew) { keys.push(`${d.id}:new`); return }
    const o = origs[d.id]
    if (!o) return
    if (d.name !== o.name) keys.push(`${d.id}:name`)
    if (d.email !== o.email) keys.push(`${d.id}:email`)
    if (d.role !== o.role) keys.push(`${d.id}:role`)
    if (d.active !== o.active) keys.push(`${d.id}:active`)
    if ((d.pid || null) !== (o.pid || null)) keys.push(`${d.id}:prof`)
    if (pw[d.id]) keys.push(`${d.id}:pw`)
  })
  removed.forEach(id => keys.push(`${id}:del`))
  return keys
}

export const invalidRows = (drafts) => drafts.filter(d => !String(d.name).trim() || !emailOk(d.email))

// Тело `PUT /users/batch`: только изменённые поля; новые — целиком; удалённые — `delete`.
export function batchOf(drafts, origs, pw, removed) {
  const out = []
  drafts.forEach(d => {
    if (d.isNew) {
      out.push({ new: true, name: d.name.trim(), email: d.email.trim(), role: d.role, is_active: d.active,
        notification_profile_id: d.pid || null, password: pw[d.id] })
      return
    }
    const o = origs[d.id]
    if (!o) return
    const p = { id: d.id }
    if (d.name !== o.name) p.name = d.name.trim()
    if (d.email !== o.email) p.email = d.email.trim()
    if (d.role !== o.role) p.role = d.role
    if (d.active !== o.active) p.is_active = d.active
    if ((d.pid || null) !== (o.pid || null)) p.notification_profile_id = d.pid || 0      // 0 — сброс на «по умолчанию»
    if (pw[d.id]) p.password = pw[d.id]
    if (Object.keys(p).length > 1) out.push(p)
  })
  removed.forEach(id => out.push({ id, delete: true }))
  return out
}

// Секции таблицы: новые — сверху всегда; дальше группы по порядку; внутри — роль (мастер первым), активные выше,
// по имени. Пустые секции не показываются. Фильтры складываются по «И»; новые строки видны при любом фильтре.
export function sectionsOf(drafts, rolesByKey, f) {
  const order = {}
  GROUPS.forEach(g => {
    rolesOrdered(Object.values(rolesByKey).filter(r => groupOfRole(r) === g.id)).forEach((r, i) => { order[r.key] = i })
  })
  const ql = f.q.trim().toLowerCase()
  const pass = (d) => d.isNew || ((f.status === 'all' || (f.status === 'on') === d.active)
    && (!f.role || d.role === f.role)
    && (!f.group || groupOfRole(rolesByKey[d.role]) === f.group)
    && (!ql || `${d.name} ${d.email}`.toLowerCase().includes(ql)))
  const shown = drafts.filter(pass)
  const sortIn = (list) => [...list].sort((a, b) => (order[a.role] ?? 99) - (order[b.role] ?? 99)
    || (b.active ? 1 : 0) - (a.active ? 1 : 0) || a.name.localeCompare(b.name, 'ru'))
  const fresh = shown.filter(d => d.isNew)
  const out = fresh.length ? [{ id: 'new', title: 'Новые — ещё не сохранены', rows: fresh, roles: [] }] : []
  GROUPS.forEach(g => {
    const rows = sortIn(shown.filter(d => !d.isNew && groupOfRole(rolesByKey[d.role]) === g.id))
    if (!rows.length) return
    const roles = rolesOrdered(Object.values(rolesByKey).filter(r => groupOfRole(r) === g.id))
    out.push({ id: g.id, title: g.title, rows, roles })
  })
  return out
}
