/**
 * Экран «Деньги» — расчёт на клиенте (README хендоффа, п. 4: «что если» считается кодом, мгновенно).
 * Вход — ответ GET /api/money/overview: остаток на счетах и открытые плановые операции с ожидаемой датой.
 *
 * Допущения, которые видны на экране словами:
 *  · просроченное поступление в календарь НЕ ставится (его нет в срок — оно в «Нам должны»; «что если заплатит» его добавляет);
 *  · оплата с прошедшей датой встаёт на сегодня с пометкой «просрочено»;
 *  · поступление или оплата, выпавшие на выходной, — на ближайший рабочий день (праздников система не знает);
 *  · «По сроку» — начало следующего периода + отсрочка из реестра; «Как платят на деле» — + среднее время оплаты клиента
 *    (колонка «Опл.» реестра); ушедшее за горизонт — в сумму «уйдут».
 */
export const HORIZON = 14
const DAY = 86400000
export const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']
export const WD_FULL = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
export const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
export const MONTHS_NOM = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
export const MON = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export const parseDate = (s) => { if (!s) return null; const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d) }
export const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
export const diffDays = (a, b) => Math.round((a - b) / DAY)
export const ddmm = (d) => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`
const isWeekend = (d) => d.getDay() === 0 || d.getDay() === 6
export const nextWorkday = (d) => { let x = d; while (isWeekend(x)) x = addDays(x, 1); return x }

/**
 * Куда операция встаёт в календаре. Возвращает { idx, flag, note } или { out: true } (за горизонт) или null (не в календарь).
 * scen.moveOut — id оплаты, перенесённой «что если» за горизонт.
 */
function place(p, today, real, scen) {
  const due = parseDate(p.due)
  if (!due) return null
  if (p.kind === 'out') {
    if (scen.moveOut === p.id) return { out: true }
    if (due < today) return { idx: 0, flag: 'late', note: `просрочено с ${ddmm(due)}` }
    const d = nextWorkday(due)
    const idx = diffDays(d, today)
    if (idx >= HORIZON) return null
    return { idx, flag: idx === 0 ? 'today' : '', note: '' }
  }
  // «Как платят на деле»: обычная дата = начало следующего периода + среднее время оплаты клиента (колонка «Опл.» реестра).
  // Просроченное по сроку, но ещё не дошедшее до обычной даты, — в календаре: клиент так и платит.
  const usual = real ? parseDate(p.usual) : null
  const base = usual || due
  if (base < today) return null
  const d = nextWorkday(base)
  const idx = diffDays(d, today)
  if (idx >= HORIZON) return diffDays(due, today) < HORIZON && due >= today ? { out: true } : null
  const shifted = usual && p.delay
  return { idx, flag: shifted ? 'shift' : '', note: shifted ? `обычно ${p.delay > 0 ? '+' : '−'}${Math.abs(p.delay)} дн к сроку` : '' }
}

/** 14 дней: операции, приход/расход, остаток на конец дня, минимум, выпавшие за горизонт поступления. */
export function buildDays(data, { real = false, scen = {} } = {}) {
  const today = parseDate(data.today)
  const days = Array.from({ length: HORIZON }, (_, i) => { const d = addDays(today, i); return { d, ops: [], inS: 0, outS: 0, bal: 0 } })
  let out = 0
  for (const p of data.plans) {
    const at = place(p, today, real, scen)
    if (!at) continue
    if (at.out) { if (p.kind === 'in') out += p.amount; continue }
    days[at.idx].ops.push({ ...p, v: p.kind === 'in' ? p.amount : -p.amount, flag: at.flag, note: at.note })
  }
  if (scen.payIn) {
    const idx = Math.min(HORIZON - 1, diffDays(nextWorkday(addDays(today, 7)), today))
    days[idx].ops.push({ id: 'scen', kind: 'in', who: scen.payIn.who, cat: 'клиенты', amount: scen.payIn.amount, v: scen.payIn.amount,
      flag: 'scen', note: `если заплатит к ${ddmm(days[idx].d)}` })
  }
  let bal = data.balance_total
  for (const x of days) {
    x.ops.sort((a, b) => a.v - b.v)
    x.inS = x.ops.filter(o => o.v > 0).reduce((a, o) => a + o.v, 0)
    x.outS = x.ops.filter(o => o.v < 0).reduce((a, o) => a - o.v, 0)
    bal += x.inS - x.outS
    x.bal = bal
  }
  const mi = days.reduce((m, x, k) => (x.bal < days[m].bal ? k : m), 0)
  return { days, mi, minB: days[mi].bal, out, inAll: days.reduce((a, x) => a + x.inS, 0), outAll: days.reduce((a, x) => a + x.outS, 0) }
}

/** Дебиторка из открытых плановых поступлений: дни до срока (минус — просрочка), корзины как в макете. */
export function receivables(data) {
  const today = parseDate(data.today)
  return data.plans.filter(p => p.kind === 'in').map(p => {
    const due = parseDate(p.due)
    return { ...p, d: due ? diffDays(due, today) : 0 }
  })
}
export const bucketOf = (x) => (x.d < 0 ? 'over' : x.d <= 7 ? 'soon' : 'ok')

/** Остаток на конец месяца m (0 — текущий, 1 — следующий …) по сценарию. */
function monthEnd(today, k) { return new Date(today.getFullYear(), today.getMonth() + k + 1, 0) }

/**
 * Накопительный прогноз: остаток на конец текущего и трёх следующих месяцев по трём сценариям.
 *  contract — все платят в срок; просроченное приходит сейчас;
 *  real     — поступление в обычную дату клиента: начало следующего периода + его среднее время оплаты;
 *  careful  — как на деле, но то, что опоздало даже против привычки клиента, не вернётся.
 * Оплаты: по дате (просроченная — сейчас), без даты — сейчас: обязательство есть, срок не назначен.
 */
export function scenarios(data) {
  const today = parseDate(data.today)
  const ends = [0, 1, 2, 3].map(k => monthEnd(today, k))
  const undated = data.undated_out?.sum || 0
  const run = (mode) => ends.map(end => {
    let bal = data.balance_total - undated
    for (const p of data.plans) {
      const due = parseDate(p.due)
      if (!due) continue
      if (p.kind === 'out') { if ((due < today ? today : due) <= end) bal -= p.amount; continue }
      const usual = parseDate(p.usual) || due
      const when = mode === 'contract' ? due : usual
      if (mode === 'careful' && when < today) continue      // опоздал даже против своей привычки — не вернётся
      if ((when < today ? today : when) <= end) bal += p.amount
    }
    return bal
  })
  return { ends, contract: run('contract'), real: run('real'), careful: run('careful') }
}
