// Реестр медиапланов v2 (хендофф design_handoff_mp_registry, 17.11.2026) — правила без React: фильтр, чипы этапов,
// сортировка, группы по месяцу, страницы, короткие подписи. Экран — pages/accounts/mp/index.js.
// Этап, замок, виза, «кто обновил», «мой» считает сервер (backend/app/sales/mp_registry.py) — здесь только раскладка.

/** Цвет чипа этапа: точка, фон, рамка, текст (хендофф §2). Группы — решение владельца 17.11.2026 («группы по этапам»). */
export const BUCKET_TONE = {
  none: ['var(--text-disabled)', 'var(--bg-subtle)', 'var(--border-inner)', 'var(--text-muted)'],
  prep: ['var(--text-faint)', 'var(--bg-subtle)', 'var(--border-inner)', 'var(--text-secondary)'],
  sent: ['var(--accent)', 'var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)'],
  // «Бронь» и «Закрытие» — групп, которых в макете не было: бронь фиолетовая (между «отправлено» и «сборкой»),
  // закрытие — серо-зелёное, чтобы не сливаться с «В размещении».
  booking: ['var(--violet)', 'var(--violet-tint)', 'var(--violet-border)', 'var(--violet-fg)'],
  assembly: ['var(--warning)', 'var(--warning-tint)', 'var(--warning-border)', 'var(--warning-fg)'],
  launch: ['var(--income)', 'var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'],
  closing: ['var(--income)', 'var(--bg-subtle)', 'var(--income-border)', 'var(--income-fg)'],
  done: ['var(--text-muted)', 'var(--bg-subtle)', 'var(--border-inner)', 'var(--text-secondary)'],
}
export const toneOf = (bucket) => BUCKET_TONE[bucket] || BUCKET_TONE.none

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const isYm = (v) => /^\d{4}-\d{2}$/.test(String(v || ''))

/** «2026-11» → «Ноябрь 2026»; без периода — «Без периода». */
export const monthLabel = (ym) => (isYm(ym) ? `${MONTHS[+ym.slice(5) - 1]} ${ym.slice(0, 4)}` : 'Без периода')

/** Сумма коротко: «679 тыс», «1,22 млн», меньше тысячи — целым. Полная сумма — в подсказке. */
export const shortMoney = (v) => {
  if (v == null) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return `${(v / 1e6).toFixed(2).replace('.', ',')} млн`
  if (a >= 1e3) return `${Math.round(v / 1e3)} тыс`
  return String(Math.round(v))
}

/** «Денис Галактионов» → «Денис Г.» — так имена стоят в узких колонках. */
export const shortName = (name) => {
  const p = String(name || '').trim().split(/\s+/)
  return p.length < 2 ? (name || '') : `${p[0]} ${p[1][0]}.`
}

/** Поверхность плана → подпись чипа: web → WEB, app → APP, кросс → WEB+APP. */
export const SURFACE_LABEL = { web: 'WEB', app: 'APP', cross: 'WEB+APP' }
export const SURFACE_HINT = { web: 'только веб', app: 'только приложения', cross: 'веб и приложения' }

/** День момента относительно сегодня: 'today' | 'yesterday' | null. Дни — строками «ГГГГ-ММ-ДД» по Москве. */
export function dayKind(day, today) {
  if (!day || !today) return null
  if (day === today) return 'today'
  const t = Date.parse(today + 'T00:00:00Z'), d = Date.parse(day + 'T00:00:00Z')
  return t - d === 86400000 ? 'yesterday' : null
}

/** Фильтр строк. `bucket` — выбранный чип этапа ('all' — все), `mine` — только свои. */
export function filterRows(items, { q = '', from = '', to = '', sel = {}, bucket = 'all', mine = false } = {}) {
  const needle = q.trim().toLowerCase()
  return items.filter(it => {
    if (needle) {
      const hay = [it.id, it.title, it.agency, it.advertiser, it.brand, it.period, it.payer, it.sales_rep,
        it.account_manager, it.deal_code, it.product_label].map(v => String(v ?? '').toLowerCase()).join(' ')
      if (!hay.includes(needle)) return false
    }
    if (from && String(it.period || '') < from) return false
    if (to && String(it.period || '') > to) return false
    for (const [k, vals] of Object.entries(sel)) {
      if (vals && vals.length && !vals.some(x => String(x) === String(it[k]))) return false
    }
    if (mine && !it.mine) return false
    if (bucket !== 'all' && it.stage_bucket !== bucket) return false
    return true
  })
}

/** Числа у чипов этапов: с учётом всех фильтров и «Мои», но БЕЗ самого этапа (хендофф §5). */
export function bucketCounts(items, filters) {
  const rows = filterRows(items, { ...filters, bucket: 'all' })
  const out = { all: rows.length }
  rows.forEach(r => { out[r.stage_bucket] = (out[r.stage_bucket] || 0) + 1 })
  return out
}

const num = (v) => (Number.isFinite(+v) ? +v : 0)
const VALUE = {
  id: it => num(it.id),
  amount_gross: it => num(it.amount_gross),
  updated_at: it => String(it.updated_at || ''),
  // «Сделка · стадия» — по месту стадии в справочнике, без сделки — в начале; затем по коду.
  deal_code: it => [num(it.stage_pos ?? -1), String(it.deal_code || '')],
}
const cmpRu = (a, b) => String(a).localeCompare(String(b), 'ru')

/** Сортировка: числа — числами, строки — по-русски, при равенстве — `id ↓`. `dir` — 'desc' | 'asc'. */
export function sortRows(rows, key = 'id', dir = 'desc') {
  const val = VALUE[key] || (it => String(it[key] ?? ''))
  const s = dir === 'desc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const va = val(a), vb = val(b)
    let c
    if (Array.isArray(va)) c = (va[0] - vb[0]) || cmpRu(va[1], vb[1])
    else c = typeof va === 'number' ? va - vb : cmpRu(va, vb)
    return c ? c * s : num(b.id) - num(a.id)
  })
}

/** Порядок месяцев: текущий, будущие по возрастанию, прошедшие от свежих к старым, «без периода» — в конце.
    При сортировке по периоду — строго по ней (хендофф §4). */
export function monthOrder(keys, current, sortKey, dir) {
  const ym = keys.filter(isYm), rest = keys.filter(k => !isYm(k))
  if (sortKey === 'period') {
    const s = [...ym].sort()
    return [...(dir === 'desc' ? s.reverse() : s), ...rest]
  }
  const now = ym.filter(k => k === current)
  const future = ym.filter(k => k > current).sort()
  const past = ym.filter(k => k < current).sort().reverse()
  return [...now, ...future, ...past, ...rest]
}

/** Прошедший месяц по умолчанию свёрнут. */
export const closedByDefault = (key, current) => isYm(key) && key < current

/**
 * Что рисовать на странице: заголовки месяцев и строки.
 *
 * Страница режется по ВИДИМЫМ строкам. Свёрнутый месяц места на странице не занимает — только свой заголовок, на той
 * странице, куда он попал по порядку: иначе «Показаны 1–24» стояло над тремя видимыми строками (стенд, 17.11.2026).
 * Месяц, разрезанный страницей, на следующей получает заголовок с пометкой «продолжение»; сумма и число в заголовке —
 * по всему месяцу, а не по странице (хендофф §8).
 */
export function pageView(rows, { grouped = true, current = '', sortKey = 'id', dir = 'desc', page = 0, size = 100, isClosed = () => false } = {}) {
  const sorted = sortRows(rows, sortKey, dir)
  if (!grouped) {
    const total = sorted.length
    const pages = Math.max(1, Math.ceil(total / size))
    const p = Math.min(Math.max(0, page), pages - 1)
    const slice = sorted.slice(p * size, p * size + size)
    return { entries: slice.map(item => ({ type: 'row', item })), total, pages, page: p, from: total ? p * size + 1 : 0, to: p * size + slice.length }
  }
  const groups = new Map()
  sorted.forEach(r => {
    const k = isYm(r.period) ? r.period : ''
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k).push(r)
  })
  const order = monthOrder([...groups.keys()], current, sortKey, dir)
  const total = order.reduce((a, k) => a + (isClosed(k) ? 0 : groups.get(k).length), 0)
  const pages = Math.max(1, Math.ceil(total / size))
  const p = Math.min(Math.max(0, page), pages - 1)
  const lo = p * size, hi = lo + size
  const out = []
  let seen = 0                                   // видимых строк до текущего месяца
  order.forEach(k => {
    const all = groups.get(k)
    const head = (continued) => ({ type: 'group', key: k, label: monthLabel(k), ...groupStats(all), continued,
      current: k === current, past: isYm(k) && k < current, closed: isClosed(k) })
    if (isClosed(k)) {
      // Заголовок свёрнутого месяца — на странице его места в порядке; в самом конце — на последней.
      const at = Math.min(Math.floor(seen / size), pages - 1)
      if (at === p) out.push(head(false))
      return
    }
    const from = Math.max(seen, lo), to = Math.min(seen + all.length, hi)
    if (from < to) {
      out.push(head(from > seen))
      all.slice(from - seen, to - seen).forEach(item => out.push({ type: 'row', item }))
    }
    seen += all.length
  })
  return { entries: out, total, pages, page: p, from: total ? lo + 1 : 0, to: Math.min(hi, total) }
}

/** Заголовок месяца: число планов, сумма с НДС, раскладка по этапам, сколько без визы. */
export function groupStats(rows) {
  const mix = {}
  let gross = 0, visa = 0
  rows.forEach(r => {
    gross += num(r.amount_gross)
    mix[r.stage_bucket] = (mix[r.stage_bucket] || 0) + 1
    if (r.needs_visa) visa += 1
  })
  return { n: rows.length, gross, mix, visa }
}

/** Ячейки шапки плана из реестра правятся, только если план не отдан клиенту и не зафиксирован — или если
    зафиксированный правит администратор/мастер-аккаунт (сервер их правку пропускает, `PATCH`). */
export const cellsOpen = (it, canEditLocked) => !it.lock || (it.lock === 'fixed' && !!canEditLocked)
