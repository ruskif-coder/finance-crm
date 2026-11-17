// node lib/dynamicsModel.test.mjs — «Динамика показов» с прогнозом, недокрутом и «нужно в день» (хендофф
// design_handoff_traffic_dynamics, 17.11.2026; входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import test from 'node:test'
import { SEGS, cellKind, columnOf, isFutureDay, needLevel, scaleMax, wrDot } from './dynamicsModel.mjs'

const past = (plan, shows) => ({ date_from: '2026-11-10', date_to: '2026-11-10', days: 1, days_past: 1, plan, shows })
const fut = (plan, extra = 0) => ({ date_from: '2026-11-20', date_to: '2026-11-20', days: 1, days_past: 0, plan, shows: 0, boost_extra: extra })

test('шкала — от максимума факта, плана, темпа и «нужно в день» с запасом 8 %', () => {
  // поломка: «нужно в день» выше всех столбцов — линия уходит за верх графика
  assert.equal(scaleMax([past(40000, 30000), fut(45000)], { need: 50000, speed: 41000 }), 54000)
  assert.equal(scaleMax([], {}), 1)
})

test('сегодня без факта считается будущим днём, сегодня с фактом — прошедшим', () => {
  const today = { date_from: '2026-11-17', date_to: '2026-11-17', days: 1, days_past: 1, plan: 100, shows: 0 }
  assert.equal(isFutureDay(today, '2026-11-17'), true)
  assert.equal(isFutureDay({ ...today, shows: 5 }, '2026-11-17'), false)
  assert.equal(isFutureDay(fut(100), '2026-11-17'), true)
  assert.equal(isFutureDay(past(100, 0), '2026-11-17'), false)   // прошлый день без показов — ноль, а не прогноз
})

test('будущий день: прогноз до темпа, недокрут до плана, выше пусто', () => {
  // посчитано руками: шкала 15 000 → 1 000 на дольку; план 9 000 = 9 долек, темп 6 000 = 6
  const c = columnOf(fut(9000), 15000, { speed: 6000, future: true })
  const kinds = Array.from({ length: SEGS }, (_, k) => cellKind(k + 1, c))
  assert.deepEqual(kinds.slice(0, 10), ['forecast', 'forecast', 'forecast', 'forecast', 'forecast', 'forecast',
    'shortfall', 'shortfall', 'shortfall', 'empty'])
})

test('темп выше плана дня — тёплых долек нет', () => {
  const c = columnOf(fut(5000), 15000, { speed: 8000, future: true })
  const kinds = Array.from({ length: SEGS }, (_, k) => cellKind(k + 1, c))
  assert.equal(kinds.filter(k => k === 'shortfall').length, 0)
  assert.equal(kinds.filter(k => k === 'forecast').length, 8)
})

test('буст в будущем дне остаётся видимым поверх недокрута', () => {
  // поломка: новые слои затёрли «темп размещения» — добавка буста перестала краситься (вопрос владельца 17.11.2026)
  const c = columnOf(fut(10000, 2000), 15000, { speed: 6000, future: true })
  const kinds = Array.from({ length: SEGS }, (_, k) => cellKind(k + 1, c))
  assert.deepEqual(kinds.slice(5, 11), ['forecast', 'shortfall', 'shortfall', 'boost', 'boost', 'empty'])
})

test('прошедший день не изменился: факт, выше план, выше пусто', () => {
  const c = columnOf(past(9000, 4000), 15000, { speed: 6000, future: false })
  const kinds = Array.from({ length: SEGS }, (_, k) => cellKind(k + 1, c))
  assert.deepEqual(kinds.slice(0, 10), ['fact', 'fact', 'fact', 'fact', 'plan', 'plan', 'plan', 'plan', 'plan', 'empty'])
})

test('у сводки РК своя высота столбца — правило то же', () => {
  // поломка: второй график держит свою копию правила долек и расходится с расхлопом
  const c = columnOf(past(9000, 4500), 18000, { future: false, rows: 18 })
  assert.deepEqual([c.fact, c.plan, c.boost], [5, 9, 0])
  const f = columnOf(fut(9000, 1800), 18000, { future: true, rows: 18 })   // без темпа — план и буст, как раньше
  assert.deepEqual([f.future, f.fact, f.plan, f.boost], [false, 0, 9, 2])
})

test('линия «нужно в день» — на уровне дольки, не выше графика', () => {
  assert.equal(needLevel(7000, 15000), 7)
  assert.equal(needLevel(99999, 15000), SEGS)
  assert.equal(needLevel(null, 15000), null)
})

test('точка WR — по уровню расхождения с сервера, без своих порогов', () => {
  // поломка: свой порог 10/30 % расходится с подсказкой дня и таблицей площадок (боевые пороги, владелец 17.11.2026)
  assert.equal(wrDot({ pct: -41.8, level: 'bad' }), 'var(--danger)')
  assert.equal(wrDot({ pct: 12, level: 'warn' }), 'var(--warning)')
  assert.equal(wrDot({ pct: 3, level: 'ok' }), null)
  assert.equal(wrDot(null), null)
})
