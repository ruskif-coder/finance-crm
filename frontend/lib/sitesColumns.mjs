// Колонки таблицы площадок в расхлопе дашборда трафика (просьба трафиков, 19.11.2026): между «Площадкой» (закреплена
// слева) и «Статусом» человек выбирает, какие показывать и в каком порядке. Настройка — у пользователя на сервере
// (`/api/ui-prefs/traffic.sites.columns`, форма {order, hidden}); ключи — те же, что `SITES_COLUMNS` в backend/app/ui_prefs.py.
// Ширины — прежней сетки макета (8.2); подписи — в шапке таблицы (`COLS` в components/traffic/v2/SiteRow.jsx).

export const PREF_KEY = 'traffic.sites.columns'

const NAME_W = 'minmax(184px,1.4fr)'
const TAIL_W = ['74px', '68px', '54px']   // статус · системы · действия

export const MOVABLE = [
  { key: 'cr', w: '44px' },
  { key: 'weight', w: '50px' },
  { key: 'share', w: '44px' },
  { key: 'plan', w: '96px' },
  { key: 'fact', w: '60px' },
  { key: 'clk', w: '42px' },
  { key: 'ctr', w: '50px' },
  { key: 'exec', w: 'minmax(70px,1fr)' },
  { key: 'under', w: '62px' },
  { key: 'wr', w: '56px' },
  { key: 'pace', w: '64px' },
]
const W = Object.fromEntries(MOVABLE.map(c => [c.key, c.w]))
const ALL = MOVABLE.map(c => c.key)

/** Полный порядок: сохранённый (без неизвестных), затем колонки, которых в нём нет, — на своих местах по умолчанию. */
export function orderOf(pref) {
  const saved = (pref?.order || []).filter(k => W[k])
  return [...saved, ...ALL.filter(k => !saved.includes(k))]
}

/** Видимые колонки в порядке показа. */
export function shownCols(pref) {
  const hidden = new Set(pref?.hidden || [])
  return orderOf(pref).filter(k => !hidden.has(k))
}

/** CSS-сетка строки под выбранные колонки. */
export const gridOf = (keys) => [NAME_W, ...keys.map(k => W[k]), ...TAIL_W].join(' ')

const norm = (pref) => ({ order: orderOf(pref), hidden: (pref?.hidden || []).filter(k => W[k]) })

/** Сдвинуть колонку на одну позицию (dir −1 — левее, +1 — правее). */
export function moveCol(pref, key, dir) {
  const p = norm(pref)
  const i = p.order.indexOf(key)
  const j = i + dir
  if (i < 0 || j < 0 || j >= p.order.length) return p
  const order = [...p.order]
  ;[order[i], order[j]] = [order[j], order[i]]
  return { ...p, order }
}

/** Показать / скрыть колонку. */
export function toggleCol(pref, key) {
  const p = norm(pref)
  return { ...p, hidden: p.hidden.includes(key) ? p.hidden.filter(k => k !== key) : [...p.hidden, key] }
}
