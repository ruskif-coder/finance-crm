// Условие доп. услуги в медиаплане (владелец 07.11.2026: «произвольная скидка на доп. услугу»). Запуск: node --test lib/mpExtraMode.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { MODES, MODE_PCT, pctOf, pctMode, totalFor, isPct } from './mpExtraMode.mjs'

test('режимы: процентная скидка — между «Скидка 50 %» и «Бонусом»', () => {
  assert.deepEqual(MODES, ['Полная цена', 'Скидка 50 %', MODE_PCT, 'Бонус', 'Фикс, ₽'])
})

test('процент читается из записанного режима, в том числе дробный', () => {
  assert.equal(pctOf('Скидка 30 %'), 30)
  assert.equal(pctOf('Скидка 12,5 %'), 12.5)
  assert.equal(pctOf('Скидка 50 %'), 50)
  assert.equal(pctOf('Полная цена'), null)
  assert.equal(pctOf('Фикс, ₽'), null)
})

test('режим из процента — той же строкой, что «Скидка 50 %»', () => {
  assert.equal(pctMode(30), 'Скидка 30 %')
  assert.equal(pctMode(12.5), 'Скидка 12,5 %')
})

test('итог: цена 150 000, скидка 30 % → 105 000; полная, бонус, фикс — как раньше', () => {
  assert.equal(totalFor('Скидка 30 %', 150000, 0), 105000)
  assert.equal(totalFor('Скидка 12,5 %', 100000, 0), 87500)
  assert.equal(totalFor('Полная цена', 150000, 0), 150000)
  assert.equal(totalFor('Скидка 50 %', 150000, 0), 75000)
  assert.equal(totalFor('Бонус', 150000, 7), 0)
  assert.equal(totalFor('Фикс, ₽', 150000, 42000), 42000)
})

test('процентная — любая «Скидка N %», и пятьдесят тоже', () => {
  assert.equal(isPct('Скидка 50 %'), true)
  assert.equal(isPct('Скидка 30 %'), true)
  assert.equal(isPct('Бонус'), false)
})
