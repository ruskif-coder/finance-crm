// Окно «Перераспределить объём» (хендофф docs/перераспределение.zip, 26.10.2026): чистые расчёты экрана.
// Сервер (`app/ad/realloc`) отдаёт площадки, предложение переноса, сценарии и дневной факт; здесь — правки, баланс,
// фильтры и график. Тест — lib/reallocView.test.mjs.

/** Тон темпа площадки: подпись чипа и цвета (`pace` — статус суток с сервера). */
export const TEMPO = {
  'мало трафика': ['мало трафика', 'var(--danger-tint)', 'var(--danger-fg)', 'var(--danger)'],
  'нет трафика': ['нет трафика', 'var(--danger-tint)', 'var(--danger-fg)', 'var(--danger)'],
  'трафик есть, не открутили': ['не открутили', 'var(--danger-tint)', 'var(--danger-fg)', 'var(--danger)'],
  'недобор': ['недобор', 'var(--warning-tint)', 'var(--warning-fg)', 'var(--warning)'],
  'в темпе': ['в темпе', 'var(--income-tint)', 'var(--income-fg)', 'var(--income)'],
  'перебор': ['перебор', 'var(--accent-tint)', 'var(--accent-fg)', 'var(--accent)'],
}
const OK = new Set(['в темпе', 'перебор'])
export const tempoOf = (pace) => TEMPO[pace] || ['нет данных', 'var(--bg-subtle)', 'var(--text-muted)', 'var(--text-faint)']

export const planOf = (r, edits) => (edits[r.id] != null ? edits[r.id] : r.plan)
export const changedRows = (rows, edits) => rows.filter(r => planOf(r, edits) !== r.plan)

/** Баланс: новые планы в сумме — ровно прежние (перенос сохраняет план РК). */
export function balance(rows, edits) {
  const before = rows.reduce((a, r) => a + (r.plan || 0), 0)
  const after = rows.reduce((a, r) => a + (planOf(r, edits) || 0), 0)
  return { before, after, diff: after - before }
}

/** «Переносим» — сумма уменьшений планов после правок. */
export const movedOf = (rows, edits) => rows.reduce((a, r) => a + Math.max(0, r.plan - planOf(r, edits)), 0)

export const FILTERS = [['all', 'Все'], ['problem', 'С проблемами'], ['ok', 'В темпе'], ['changed', 'Изменённые']]
export function passes(r, filter, edits) {
  if (filter === 'problem') return !OK.has(r.pace)
  if (filter === 'ok') return OK.has(r.pace)
  if (filter === 'changed') return planOf(r, edits) !== r.plan
  return true
}

/** Сортировка таблицы по клику на заголовок. Значение колонки по ключу; правки (`edits`) учитываются. */
const PACE_RANK = Object.keys(TEMPO)
const SORT_VALUE = {
  name: (r) => r.name || '',
  pace: (r) => { const i = PACE_RANK.indexOf(r.pace); return i < 0 ? null : i },
  shows_day: (r) => r.shows_day, offered_day: (r) => r.offered_day, capacity: (r) => r.capacity,
  need: (r) => r.need, plan: (r) => r.plan,
  delta: (r, e) => planOf(r, e) - r.plan,
  newplan: (r, e) => planOf(r, e),
  after: (r, e, days) => needPerDay(planOf(r, e), r.fact, days),
}
// Первый клик: текст и темп (от худшего) — с начала, числа — крупное сверху; повторный — наоборот.
const ASC_FIRST = new Set(['name', 'pace'])
export const nextSort = (cur, key) => (cur?.key === key
  ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' }
  : { key, dir: ASC_FIRST.has(key) ? 'asc' : 'desc' })

/** Пустое значение («—») всегда внизу, в любом направлении; без сортировки — порядок сервера. */
export function sortRows(rows, sort, edits, days) {
  const val = sort && SORT_VALUE[sort.key]
  if (!val) return rows
  const k = sort.dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const x = val(a, edits, days), y = val(b, edits, days)
    if (x == null || y == null) return (x == null) - (y == null)
    return (typeof x === 'string' ? x.localeCompare(y, 'ru') : x - y) * k
  })
}

/** «Нужно в сутки» при плане `plan`: остаток ÷ дни до конца флайта. */
export const needPerDay = (plan, fact, days) => (days > 0 ? Math.max(0, (plan || 0) - (fact || 0)) / days : 0)

/** Ввод «Новый план»: только цифры; пусто — null. */
export const parsePlan = (s) => {
  const v = parseInt(String(s ?? '').replace(/\D/g, ''), 10)
  return Number.isNaN(v) ? null : v
}

/**
 * График «Динамика по дням» по набору площадок `scope`.
 * Прошедшие дни (≤ as_of) — факт, красный ниже 90 % суточного плана; оставшиеся — «нужно до / после» против «сеть может».
 */
export function chart(scope, edits, daily, days) {
  const dates = daily?.dates || []
  const asOf = daily?.as_of || ''
  const total = dates.length || 1
  const cPlan = scope.reduce((a, r) => a + (r.plan || 0), 0)
  const cPlanNew = scope.reduce((a, r) => a + (planOf(r, edits) || 0), 0)
  const cFact = scope.reduce((a, r) => a + (r.fact || 0), 0)
  const cNB = scope.reduce((a, r) => a + needPerDay(r.plan, r.fact, days), 0)
  const cNA = scope.reduce((a, r) => a + needPerDay(planOf(r, edits), r.fact, days), 0)
  const cCan = scope.reduce((a, r) => a + (r.capacity != null ? r.capacity : (r.shows_day || 0)), 0)
  const dayPlan = cPlan / total
  const bars = dates.map(dt => {
    if (dt <= asOf) {
      const f = scope.reduce((a, r) => a + ((daily.facts?.[r.id] || {})[dt] || 0), 0)
      return { dt, future: false, fact: f, low: dayPlan > 0 && f / dayPlan < 0.9 }
    }
    return { dt, future: true, before: cNB, after: cNA, over: cNA > cCan }
  })
  const past = bars.filter(b => !b.future).length
  const pastFact = bars.filter(b => !b.future).reduce((a, b) => a + b.fact, 0)
  const max = Math.max(dayPlan, cNB, cNA, ...bars.filter(b => !b.future).map(b => b.fact), 1) * 1.12
  return {
    bars, max, dayPlan, cNB, cNA, cCan,
    avg: past ? pastFact / past : 0,
    pctNow: past && dayPlan ? cFact / (dayPlan * past) * 100 : null,
    forecast: cPlanNew ? (cFact + Math.min(cNA, cCan) * days) / cPlanNew * 100 : null,
  }
}
