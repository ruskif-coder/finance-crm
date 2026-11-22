// «Динамика показов» в расхлопе РК (хендофф design_handoff_traffic_dynamics, 17.11.2026): к факту и плану дня
// добавлены прогноз по темпу и недокрут на будущих днях, линия «нужно в день» и точки расхождения с WR под датами.
//
// Решения по открытым вопросам README (17.11.2026):
//  · темп прогноза — «Средний темп» периода (`speed` с сервера, то же число под графиком), а не последние 7 дней;
//  · точка WR — по уровню расхождения с сервера (`mismatch.level`, боевые пороги — владелец 17.11.2026), а не 10/30 % макета;
//  · недокрут по прошедшим дням не рисуется — в макете не выбран.
// Добавка «темпа размещения» (`boost_extra`) красится по-прежнему — верхняя часть плана будущего дня.
export const SEGS = 15

const lv = (v, max, rows = SEGS) => Math.min(rows, Math.round((v || 0) / max * rows))

/** Факт дня в ЕДИНИЦЕ РК (22.11.2026): у click-РК план дня — клики, значит и факт-слой — клики.
 *  Показы остаются в подсказке дня; здесь важно, чтобы столбик факта и план были в одном числе. */
const factOf = (b, unit) => (unit === 'click' ? b.clicks : b.shows)

/** Максимум шкалы: факт прошедших, план, темп и «нужно в день» — с запасом 8 %, округлено до тысяч. */
export const scaleMax = (buckets, { need, speed, unit } = {}) => {
  const vals = [...buckets.map(b => b.plan || 0), ...buckets.filter(b => b.days_past).map(b => factOf(b, unit) || 0), need || 0, speed || 0]
  const m = Math.max(0, ...vals)
  return m ? Math.ceil(m * 1.08 / 1000) * 1000 : 1
}

/** Будущий день — ещё не наступил, или это сегодня без единого показа (README: «сегодня тоже, пока нет факта»). */
export const isFutureDay = (b, today) => !b.days_past
  || (b.days === 1 && String(b.date_from) === today && !b.shows)

/** Сколько долек на каждый слой колонки. Без темпа (факта ещё нет) будущий день рисуется как раньше — планом.
 *  Правило одно на оба графика динамики: расхлоп v2 (15 долек) и сводка РК `Dynamics` в ките (`rows` = 18). */
export const columnOf = (b, max, { speed = null, future, rows = SEGS, unit } = {}) => {
  const plan = lv(b.plan, max, rows)
  const boost = Math.min(plan, lv(b.boost_extra, max, rows))
  if (future && speed != null) return { future: true, forecast: lv(speed, max, rows), plan, boost }
  return { future: false, fact: future ? 0 : lv(factOf(b, unit), max, rows), plan, boost }
}

/** Слой дольки на высоте `rank` (1 — нижняя). */
export const cellKind = (rank, c) => {
  if (c.future) {
    if (rank <= c.forecast) return 'forecast'
    return rank <= c.plan - c.boost ? 'shortfall' : rank <= c.plan ? 'boost' : 'empty'
  }
  return rank <= c.fact ? 'fact' : rank <= c.plan - c.boost ? 'plan' : rank <= c.plan ? 'boost' : 'empty'
}

/** Уровень линии «нужно в день» в дольках: линия лежит в зазоре над этой долькой, а не режет её. */
export const needLevel = (need, max) => (need == null ? null : lv(need, max))

/** Цвет точки под датой по уровню расхождения с WR с сервера; в норме точки нет. */
export const wrDot = (m) => (m?.level === 'bad' ? 'var(--danger)' : m?.level === 'warn' ? 'var(--warning)' : null)
