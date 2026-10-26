// node lib/publisherRecon.test.mjs — правила экрана сверок (входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import { counts, deltaOf, passes, plural, shiftMonth, parseShows, toneOf } from './publisherRecon.mjs'

const rows = [
  { status: 'есть ответ' }, { status: 'ожидает', late: true }, { status: 'ожидает' },
  { status: 'готово' }, { status: 'ждёт закрытия' }, { status: 'согласовано' },
]
assert.deepEqual(counts(rows), { all: 6, answer: 1, wait: 1, late: 1, ready: 1, closing: 1, done: 1 })
assert.equal(rows.filter(r => passes(r, 'waitAll')).length, 2)      // «ожидает» включает просроченные
assert.equal(rows.filter(r => passes(r, null)).length, 6)
assert.equal(toneOf({ status: 'ожидает', late: true }).label, 'ожидает · просрочено')

assert.deepEqual(deltaOf(1000, null), { text: '—', pct: '', tone: 'none' })
assert.deepEqual(deltaOf(1000, 1000), { text: '0', pct: '', tone: 'zero' })
assert.equal(deltaOf(1000, 1023).pct, '+2,3 %')
assert.equal(deltaOf(1000, 900).text, '−100')

assert.equal(shiftMonth('2026-01', -1), '2025-12')
assert.equal(shiftMonth('2026-12', 1), '2027-01')
assert.equal(plural(2, 'сверка', 'сверки', 'сверок'), 'сверки')
assert.equal(plural(11, 'сверка', 'сверки', 'сверок'), 'сверок')
assert.equal(parseShows('6 104 000'), 6104000)
assert.equal(parseShows(''), null)
console.log('publisherRecon: ok')
