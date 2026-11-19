// Колонки таблицы площадок в расхлопе дашборда трафика — выбор и порядок человека (19.11.2026).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MOVABLE, gridOf, moveCol, shownCols, toggleCol } from './sitesColumns.mjs'

const ALL = ['cr', 'weight', 'share', 'plan', 'fact', 'clk', 'ctr', 'exec', 'under', 'wr', 'pace']

test('без настройки — все колонки в прежнем порядке', () => {
  // поломка: пустая настройка прячет колонки — у тех, кто ничего не выбирал, таблица пустая
  assert.deepEqual(MOVABLE.map(c => c.key), ALL)
  assert.deepEqual(shownCols(null), ALL)
})

test('скрытые выпадают, порядок — из настройки', () => {
  assert.deepEqual(shownCols({ order: ['fact', 'plan'], hidden: ['wr', 'cr'] }),
    ['fact', 'plan', 'weight', 'share', 'clk', 'ctr', 'exec', 'under', 'pace'])
})

test('колонка, появившаяся после сохранения, видна, а неизвестная из настройки — молча пропадает', () => {
  // поломка: новая колонка не попадает в сохранённый order — её никто никогда не увидит
  assert.deepEqual(shownCols({ order: ['pace', 'gone'], hidden: [] })[0], 'pace')
  assert.equal(shownCols({ order: ['pace', 'gone'], hidden: [] }).length, 11)
})

test('сетка: площадка слева, статус-системы-действия справа, между — выбранные', () => {
  assert.equal(gridOf(['fact', 'exec']), 'minmax(184px,1.4fr) 60px minmax(70px,1fr) 74px 68px 54px')
})

test('перестановка и скрытие возвращают новую настройку, не трогая старую', () => {
  const p = { order: [...ALL], hidden: [] }
  const up = moveCol(p, 'plan', -1)
  assert.deepEqual(up.order.slice(0, 4), ['cr', 'weight', 'plan', 'share'])
  assert.deepEqual(p.order, ALL)
  assert.deepEqual(moveCol(p, 'cr', -1).order, ALL)          // выше первой некуда
  const off = toggleCol(p, 'wr')
  assert.deepEqual(off.hidden, ['wr'])
  assert.deepEqual(toggleCol(off, 'wr').hidden, [])
  assert.deepEqual(moveCol(null, 'pace', -1).order.slice(-2), ['pace', 'wr'])   // от умолчания
})
