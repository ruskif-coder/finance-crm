// node lib/mpRegistryModel.test.mjs — реестр медиапланов v2 (хендофф design_handoff_mp_registry, входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import test from 'node:test'
import { bucketCounts, cellsOpen, dayKind, filterRows, monthLabel, monthOrder, pageView, shortMoney, shortName,
  sortRows } from './mpRegistryModel.mjs'

const R = (id, o = {}) => ({ id, period: '2026-11', amount_gross: 1000, stage_bucket: 'sent', mine: false, ...o })

test('короткие суммы и имена', () => {
  assert.equal(shortMoney(679479), '679 тыс')
  assert.equal(shortMoney(1220000), '1,22 млн')
  assert.equal(shortMoney(820), '820')
  assert.equal(shortMoney(null), '—')
  assert.equal(shortName('Денис Галактионов'), 'Денис Г.')
  assert.equal(shortName('Админ'), 'Админ')
  assert.equal(monthLabel('2026-11'), 'Ноябрь 2026')
  assert.equal(monthLabel(null), 'Без периода')
})

test('сегодня / вчера — по календарным дням', () => {
  assert.equal(dayKind('2026-11-17', '2026-11-17'), 'today')
  assert.equal(dayKind('2026-11-16', '2026-11-17'), 'yesterday')
  assert.equal(dayKind('2026-10-31', '2026-11-01'), 'yesterday')   // через границу месяца
  assert.equal(dayKind('2026-11-15', '2026-11-17'), null)
})

test('числа у чипов — без учёта самого этапа, но с «Мои»', () => {
  // поломка: выбранный чип обнуляет соседние, или «Мои» не влияет на числа
  const items = [R(1), R(2, { stage_bucket: 'launch', mine: true }), R(3, { stage_bucket: 'launch' })]
  assert.deepEqual(bucketCounts(items, { bucket: 'launch' }), { all: 3, sent: 1, launch: 2 })
  assert.deepEqual(bucketCounts(items, { mine: true, bucket: 'sent' }), { all: 1, launch: 1 })
  assert.equal(filterRows(items, { bucket: 'launch', mine: true }).length, 1)
})

test('поиск по коду сделки и услуге', () => {
  const items = [R(1, { deal_code: 'RCM5TT' }), R(2, { product_label: 'еФарм' })]
  assert.deepEqual(filterRows(items, { q: 'rcm5' }).map(x => x.id), [1])
  assert.deepEqual(filterRows(items, { q: 'ЕФАРМ' }).map(x => x.id), [2])
})

test('сортировка: при равенстве — id по убыванию; стадия — по месту в справочнике', () => {
  const rows = [R(1, { amount_gross: 5 }), R(3, { amount_gross: 5 }), R(2, { amount_gross: 9 })]
  assert.deepEqual(sortRows(rows, 'amount_gross', 'desc').map(x => x.id), [2, 3, 1])
  assert.deepEqual(sortRows(rows, 'amount_gross', 'asc').map(x => x.id), [3, 1, 2])
  const st = [R(1, { stage_pos: 7, deal_code: 'B' }), R(2, { stage_pos: -1 }), R(3, { stage_pos: 1, deal_code: 'A' })]
  assert.deepEqual(sortRows(st, 'deal_code', 'asc').map(x => x.id), [2, 3, 1])
})

test('порядок месяцев: текущий, будущие по возрастанию, прошедшие от свежих; по периоду — строго', () => {
  const keys = ['2026-09', '2027-01', '2026-11', '2026-12', '2026-10', '']
  assert.deepEqual(monthOrder(keys, '2026-11', 'id', 'desc'), ['2026-11', '2026-12', '2027-01', '2026-10', '2026-09', ''])
  assert.deepEqual(monthOrder(keys, '2026-11', 'period', 'asc'), ['2026-09', '2026-10', '2026-11', '2026-12', '2027-01', ''])
  assert.deepEqual(monthOrder(keys, '2026-11', 'period', 'desc'), ['2027-01', '2026-12', '2026-11', '2026-10', '2026-09', ''])
})

test('страница режется по строкам; месяц на стыке — «продолжение», итоги по всему месяцу', () => {
  // поломка: заголовок месяца считает сумму по странице, или на второй странице месяц теряет заголовок
  const rows = [R(1), R(2), R(3), R(4, { period: '2026-12', needs_visa: true })]
  const p1 = pageView(rows, { current: '2026-11', size: 2, page: 1 })
  assert.equal(p1.total, 4)
  assert.equal(p1.pages, 2)
  assert.deepEqual(p1.entries.map(e => e.type), ['group', 'row', 'group', 'row'])
  assert.equal(p1.entries[0].continued, true)
  assert.equal(p1.entries[0].n, 3)              // весь ноябрь, а не одна строка этой страницы
  assert.equal(p1.entries[0].gross, 3000)
  assert.equal(p1.entries[2].continued, false)
  assert.equal(p1.entries[2].visa, 1)
  assert.equal(p1.from, 3)
  assert.equal(p1.to, 4)
})

test('свёрнутый месяц — заголовок без строк и без места на странице; без группировки — без заголовков', () => {
  // поломка: «Показаны 1–24» над тремя видимыми строками — строки свёрнутых месяцев съедали страницу
  const rows = [R(1, { period: '2026-10' }), R(5, { period: '2026-10' }), R(2)]
  const v = pageView(rows, { current: '2026-11', isClosed: k => k === '2026-10' })
  assert.deepEqual(v.entries.map(e => e.type + (e.key ?? '')), ['group2026-11', 'row', 'group2026-10'])
  assert.equal(v.total, 1)
  assert.equal(v.entries[2].n, 2)                // в заголовке — весь месяц
  assert.deepEqual(pageView(rows, { grouped: false }).entries.map(e => e.type), ['row', 'row', 'row'])
})

test('свёрнутый месяц в конце порядка — на последней странице', () => {
  const rows = [R(1), R(2), R(3), R(9, { period: '2026-09' })]
  const isClosed = k => k === '2026-09'
  assert.deepEqual(pageView(rows, { current: '2026-11', size: 2, page: 0, isClosed }).entries.map(e => e.type), ['group', 'row', 'row'])
  assert.deepEqual(pageView(rows, { current: '2026-11', size: 2, page: 1, isClosed }).entries.map(e => e.type + (e.continued ? '+' : '')),
    ['group+', 'row', 'group'])
})

test('ячейки: отданный клиенту закрыт всем, зафиксированный — открыт админу и мастер-аккаунту', () => {
  // поломка: экран пускает в правку, которую сервер отклонит 409, или закрывает открытое мастеру
  assert.equal(cellsOpen({ lock: '' }, false), true)
  assert.equal(cellsOpen({ lock: 'sent' }, true), false)
  assert.equal(cellsOpen({ lock: 'fixed' }, false), false)
  assert.equal(cellsOpen({ lock: 'fixed' }, true), true)
})
