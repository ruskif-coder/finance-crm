// События и сроки «Моих сделок» (модалка, хендофф v5 экран 14). Поломки: бронь без срока «за 15 дн. до старта»; сверка, стоящая
// дольше 3 дней, не попадает в «просрочено»; событие вне окна «просрочено + 11 дней» мешает ленте; конец периода у брони.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildEvents, DAYS_AHEAD } from './dealEvents.mjs'

const TODAY = '2026-11-14'

test('бронь: срок по норме — за 15 дней до старта, и старт РК', () => {
  const ev = buildEvents([{ id: 1, slot: 'booking', period_from: '2026-11-20', period_to: '2026-11-30' }], TODAY)
  assert.deepEqual(ev.map(e => [e.type, e.date]), [['norm', '2026-11-05'], ['start', '2026-11-20']])
  assert.equal(ev[0].overdue, true)
  assert.equal(ev[0].what, 'подтвердить бронь')
})

test('сверка: 3 дня на стадии — стоит 5 дней, срок прошёл 2 дня назад', () => {
  const [e] = buildEvents([{ id: 2, slot: 'recon', stage_days: 5, period_from: '2026-10-01', period_to: '2026-10-31' }], TODAY)
  assert.deepEqual([e.type, e.date, e.overdue, e.what], ['norm', '2026-11-12', true, 'закрыть итоговую сверку'])
})

test('конец периода — только у размещения; вне окна событий нет', () => {
  const ev = buildEvents([
    { id: 3, slot: 'live', period_from: '2026-11-01', period_to: '2026-11-20' },
    { id: 4, slot: 'live', period_from: '2026-11-01', period_to: '2026-12-31' },
    { id: 5, slot: 'booking', period_from: '2027-02-01', period_to: '2027-02-28' },
  ], TODAY)
  assert.deepEqual(ev.map(e => [e.row.id, e.type, e.date]), [[3, 'end', '2026-11-20']])
  assert.equal(DAYS_AHEAD, 10)
})
