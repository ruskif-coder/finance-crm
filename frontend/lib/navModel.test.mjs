// node lib/navModel.test.mjs — правила строки меню v3 (хендофф design_handoff_nav_mix, входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import test from 'node:test'
import { layoutOf, objectOf, panelCols, pinsShown, pushRecent, recentFor, sumBadge, togglePin } from './navModel.mjs'

const FIN = { key: 'finance', title: 'Финансы', items: [
  { label: 'ДДС', href: '/finance/cashflow' }, { label: 'P&L', href: '/finance/pnl' },
  { label: 'Операции', href: '/finance/operations' }] }
const TR = { key: 'traffic', title: 'Трафики', items: [
  { label: 'Дашборд', href: '/traffic/dashboard' }, { label: 'Креативы на проверку', href: '/traffic/queue', badge: '61' },
  { label: 'Премодерация', href: '/traffic/premoderation', badge: '41' }] }
const DIR = { key: 'directory', title: 'Справочники', items: [{ label: 'Контрагенты', href: '/directory/counterparties' }] }

test('«Справочники» — не контур строки, а отдельная кнопка; плоского меню нет', () => {
  // поломка: справочники попадают в строку контуров, или у роли с одним контуром строка становится другой
  assert.deepEqual(layoutOf([TR, DIR]), { mains: [TR], directory: DIR })
  assert.deepEqual(layoutOf([FIN, TR]), { mains: [FIN, TR], directory: null })
})

test('объект — первый сегмент адреса глубже экрана', () => {
  // поломка: объектом становится хвост запроса или экран без объекта получает «пустой» третий уровень
  assert.equal(objectOf('/sales/deals/2665?tab=mp', { href: '/sales/deals' }), '2665')
  assert.equal(objectOf('/traffic/dashboard', { href: '/traffic/dashboard' }), '')
  assert.equal(objectOf('/traffic/dashboard#x', { href: '/traffic/dashboard' }), '')
  assert.equal(objectOf('/directory/contracts/%D0%90-1/x', { href: '/directory/contracts' }), 'А-1')
  assert.equal(objectOf('/x', null), '')
})

test('больше семи экранов — две колонки', () => {
  assert.equal(panelCols(7), 1)
  assert.equal(panelCols(8), 2)
})

test('закрепить можно три, четвёртый не встаёт; повторный клик снимает', () => {
  // поломка: четвёртая звезда вытесняет первую — человек теряет закреп, которого не трогал
  const three = ['/a', '/b', '/c']
  assert.deepEqual(togglePin(three, '/d'), three)
  assert.deepEqual(togglePin(three, '/b'), ['/a', '/c'])
  assert.deepEqual(togglePin(['/a'], '/b'), ['/a', '/b'])
})

test('недавние: свежий первым, без дублей, не больше двенадцати', () => {
  const r = Array.from({ length: 12 }, (_, i) => `/s/${i}`)
  assert.deepEqual(pushRecent(r, '/s/5').slice(0, 3), ['/s/5', '/s/0', '/s/1'])
  assert.equal(pushRecent(r, '/new').length, 12)
  assert.equal(pushRecent(r, '/new').at(-1), '/s/10')
})

test('подвал «недавно» — два последних экрана раздела, кроме текущего', () => {
  // поломка: подвал показывает экраны чужого раздела или тот, на котором человек стоит
  const recent = ['/finance/pnl', '/traffic/dashboard', '/finance/cashflow', '/finance/operations']
  assert.deepEqual(recentFor(recent, FIN, '/finance/pnl').map(i => i.label), ['ДДС', 'Операции'])
  assert.deepEqual(recentFor(recent, TR, '/traffic/dashboard'), [])
})

test('закреплённые: только доступные роли сейчас', () => {
  // поломка: закреп экрана, к которому у роли больше нет доступа, остаётся кнопкой и ведёт в отказ
  const pins = ['/finance/operations', '/traffic/queue', '/settings/x']
  assert.deepEqual(pinsShown(pins, [FIN, TR]).map(p => p.item.label), ['Операции', 'Креативы на проверку'])
  assert.deepEqual(pinsShown(pins, [TR]).map(p => p.item.label), ['Креативы на проверку'])
  assert.equal(pinsShown(pins, [FIN, TR])[0].section.key, 'finance')
})

test('счётчик контура — сумма его экранов', () => {
  assert.equal(sumBadge(TR), 102)
  assert.equal(sumBadge(FIN), 0)
})
