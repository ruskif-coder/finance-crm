// node --test lib/salesPlan.test.mjs — расчёты экрана «План продаж» на маленьком наборе.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sumCells, buckets, phase, currentMonth, pct, heat, cellValue, fmtK, toDate, spreadEven, spreadBySeason, copyPrev, groupServices } from './salesPlan.mjs'

const c = (goal, done, forecast = done, extra = {}) => ({ goal, fact: done, work: 0, green: 0, orange: 0, grey: 0, done, forecast, forecast_week_ago: null, ...extra })

test('сумма ячеек: цель null, если нигде не задана; иначе сумма заданных', () => {
  assert.equal(sumCells([c(null, 5), c(null, 7)]).goal, null)
  assert.equal(sumCells([c(null, 5), c(100, 7)]).goal, 100)
  assert.equal(sumCells([c(10, 5), c(20, 7)]).done, 12)
})

test('кварталы и положение колонок относительно сегодня', () => {
  const months = Array.from({ length: 12 }, (_, m) => c(10, m))
  const q = buckets(months, 'q')
  assert.equal(q.length, 4)
  assert.equal(q[3].c.goal, 30)
  const cur = currentMonth(2026, '2026-10-24')
  assert.equal(cur, 9)
  assert.deepEqual(q.map(b => phase(b, cur)), ['past', 'past', 'past', 'now'])
  assert.equal(currentMonth(2025, '2026-10-24'), 12, 'прошлый год — весь в прошлом')
  assert.equal(currentMonth(2027, '2026-10-24'), -1, 'следующий год — весь в будущем')
})

test('прошлое — выполнено к цели, будущее — прогноз к цели; без цели процента нет', () => {
  assert.deepEqual(cellValue(c(100, 80, 95), 'done', 'past'), { v: 80, p: 80, base: 80, future: false })
  assert.equal(cellValue(c(100, 80, 95), 'done', 'future').p, 95)
  assert.equal(cellValue(c(null, 80, 95), 'pct', 'past').v, null)
  assert.equal(cellValue(c(null, 80, 95), 'gap', 'past').v, null, 'разрыва без цели нет')
  assert.equal(cellValue(c(100, 80, 95), 'gap', 'past').v, -5)
})

test('подсветка и формат', () => {
  assert.deepEqual([heat(79), heat(80), heat(100), heat(110), heat(null)], ['bad', 'mid', 'ok', 'over', null])
  assert.equal(pct(5, 0), null)
  assert.equal(fmtK(34312000).replace(/\s/g, ' '), '34 300')
  assert.equal(fmtK(null), '—')
})

test('к сегодняшнему дню — по месяцам до текущего включительно', () => {
  const months = Array.from({ length: 12 }, () => c(10, 9))
  assert.deepEqual(toDate({ months }, 9), { done: 90, goal: 100, p: 90 })
})

test('разложение года сходится до копейки', () => {
  const e = spreadEven(1000)
  assert.equal(e.length, 12)
  assert.equal(Math.round(e.reduce((a, b) => a + b, 0) * 100), 100000)
  const s = spreadBySeason(1200, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3])
  assert.equal(s[11], 900)
  assert.equal(Math.round(s.reduce((a, b) => a + b, 0) * 100), 120000)
  assert.deepEqual(spreadBySeason(120, null), spreadEven(120))
  assert.deepEqual(copyPrev([100, null], 10).slice(0, 2), [110, null])
})

test('услуги по группам в порядке сервера', () => {
  const g = groupServices([{ group: 'SIMB-AD', name: 'a' }, { group: 'AlPharm', name: 'b' }, { group: 'SIMB-AD', name: 'c' }])
  assert.deepEqual(g.map(x => [x.group, x.rows.length]), [['SIMB-AD', 2], ['AlPharm', 1]])
})

test('ввод целей — полные рубли с тройками', async () => {
  const { parseRub, fmtRub, typeRub } = await import('./salesPlan.mjs')
  assert.equal(parseRub('10 000 000'), 10000000)
  assert.equal(parseRub('10 000 000'), 10000000)
  assert.equal(parseRub(''), null)
  assert.equal(parseRub('1 250,5'), 1250.5)
  assert.equal(fmtRub(10000000).replace(/\s/g, ' '), '10 000 000')
  assert.equal(fmtRub(null), '')
  assert.equal(typeRub('10000000').replace(/\s/g, ' '), '10 000 000')
  assert.equal(typeRub('1250,567').replace(/\s/g, ' '), '1 250,56')
  assert.equal(typeRub('абв'), '')
})

test('аналитика: нарастающий итог, кто держит разрыв, состав прогноза, сезонность, неделя', async () => {
  const { cumulative, whoHolds, composition, seasonality, weekDelta } = await import('./salesPlan.mjs')
  const months = Array.from({ length: 12 }, (_, m) => ({ goal: 10, fact: m < 2 ? 10 : m === 2 ? 4 : 0, work: m === 2 ? 2 : 0,
    green: m >= 3 ? 5 : 0, orange: 0, grey: 0, done: m < 2 ? 10 : m === 2 ? 6 : 0, forecast: m < 2 ? 10 : m === 2 ? 6 : 5, forecast_week_ago: null }))
  const c = cumulative({ months }, 3)
  assert.equal(c.behindFrom, 2, 'отстаём с марта: 26 < 30')
  assert.equal(c.bars[11].extra, 45, 'прогноз сверх выполненного — с текущего месяца')
  assert.equal(c.short, 120 - (26 + 45))
  const who = whoHolds([{ name: 'A', months: months.map(x => ({ ...x, goal: 20 })) }, { name: 'B', months }, { name: 'без', months: months.map(x => ({ ...x, goal: null })) }])
  assert.deepEqual(who.map(x => x.name), ['A', 'B'], 'от худшего; без цели не участвует')
  const comp = composition({ months: months.map(x => ({ ...x, orange: 2 })) })
  assert.equal(comp.parts.find(p => p.k === 'orange').v, 12, 'оранжевые с весом 50 %')
  const s = seasonality([10, 10, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0], [10, 10, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0])
  assert.equal(s.worst, null, 'совпадает с прошлым годом — перекоса нет')
  assert.equal(seasonality([50, 50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [10, 10, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0]).worst.m, 2)
  assert.equal(weekDelta([{ forecast: 100 }, { forecast: 110 }, { forecast: 120 }, { forecast: 130 }, { forecast: 140 }, { forecast: 150 }]), 40)
  assert.equal(weekDelta([{ forecast: 1 }]), null)
})
