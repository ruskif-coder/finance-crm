// node lib/reallocView.test.mjs — расчёты окна «Перераспределить объём» (входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import { balance, changedRows, chart, movedOf, nextSort, parsePlan, passes, sortRows, tempoOf } from './reallocView.mjs'

const rows = [
  { id: 1, plan: 29_235, fact: 9_496, pace: 'мало трафика', capacity: 719, shows_day: 728 },
  { id: 2, plan: 292_354, fact: 222_304, pace: 'в темпе', capacity: 8_359, shows_day: 11_718 },
  { id: 3, plan: 175_412, fact: 98_942, pace: 'трафик есть, не открутили', capacity: 6_332, shows_day: 4_850 },
]
const edits = { 1: 21_415, 2: 300_174 }      // донор −7 820, получатель +7 820

assert.deepEqual(balance(rows, edits).diff, 0)
assert.equal(balance(rows, { 1: 20_000 }).diff, -9_235)
assert.equal(movedOf(rows, edits), 7_820)
assert.equal(changedRows(rows, edits).length, 2)
assert.equal(rows.filter(r => passes(r, 'problem', edits)).length, 2)
assert.equal(rows.filter(r => passes(r, 'ok', edits)).length, 1)
assert.equal(rows.filter(r => passes(r, 'changed', edits)).length, 2)
assert.equal(tempoOf('трафик есть, не открутили')[0], 'не открутили')
assert.equal(parsePlan('300 174'), 300_174)
assert.equal(parsePlan(''), null)

const daily = { dates: ['2026-10-01', '2026-10-02', '2026-10-03'], as_of: '2026-10-02',
  facts: { 1: { '2026-10-01': 100, '2026-10-02': 10 }, 2: { '2026-10-01': 50 } } }
const c = chart([rows[0]], {}, daily, 1)
assert.equal(c.bars.length, 3)
assert.equal(c.bars[0].fact, 100)
assert.equal(c.bars[1].low, true)                       // 10 при суточном плане ~9 745 — ниже 90 %
assert.equal(c.bars[2].future, true)
assert.equal(Math.round(c.bars[2].before), 19_739)       // остаток 19 739 за 1 день
assert.equal(c.bars[2].over, true)                       // нужно больше, чем сеть может (719)

// Сортировка по клику на заголовок: числа по убыванию первым кликом, пустое — всегда внизу
const ids = (s) => sortRows(rows, s, edits, 1).map(r => r.id).join()
assert.equal(ids(null), '1,2,3')                                     // без сортировки — порядок сервера
assert.equal(ids({ key: 'plan', dir: 'desc' }), '2,3,1')
assert.equal(ids({ key: 'plan', dir: 'asc' }), '1,3,2')
assert.equal(ids({ key: 'pace', dir: 'asc' }), '1,3,2')              // от худшего темпа к лучшему
assert.equal(ids({ key: 'delta', dir: 'desc' }), '2,3,1')            // берёт +7 820, без правки 0, отдаёт −7 820
assert.equal(ids({ key: 'newplan', dir: 'desc' }), '2,3,1')
const withNull = [...rows, { id: 4, plan: 1, fact: 0, pace: 'в темпе', capacity: null }]
assert.equal(sortRows(withNull, { key: 'capacity', dir: 'asc' }, {}, 1).map(r => r.id).join(), '1,3,2,4')
assert.equal(sortRows(withNull, { key: 'capacity', dir: 'desc' }, {}, 1).map(r => r.id).join(), '2,3,1,4')
assert.deepEqual(nextSort(null, 'plan'), { key: 'plan', dir: 'desc' })
assert.deepEqual(nextSort(null, 'name'), { key: 'name', dir: 'asc' })
assert.deepEqual(nextSort({ key: 'plan', dir: 'desc' }, 'plan'), { key: 'plan', dir: 'asc' })
assert.deepEqual(nextSort({ key: 'plan', dir: 'asc' }, 'need'), { key: 'need', dir: 'desc' })
console.log('reallocView: ok')
