// Обязательные поля операции (владелец 27.11.2026): подсветка контуром и проверка сохранения считаются одной функцией.
// Ломается, если правило снова разъедется на два списка: подсветка покажет «всё заполнено», а сохранение откажет.
import test from 'node:test'
import assert from 'node:assert/strict'

import { requiredKeys, missingFields, FIELD_LABEL } from './opRequirements.js'

test('статуса нет — обязателен только он', () => {
  assert.deepEqual(requiredKeys(''), ['status'])
  assert.deepEqual(missingFields({}).map(x => x.key), ['status'])
})

test('«Оплачено» требует дату и банк сверх общих полей', () => {
  assert.deepEqual(requiredKeys('ОПЛАЧЕНО'), ['period', 'article_id', 'counterparty_id', 'date', 'bank'])
  assert.deepEqual(missingFields({ status: 'ОПЛАЧЕНО' }).map(x => x.label),
    ['период', 'статья', 'контрагент', 'дата', 'банк'])
})

test('планы банк и дату не требуют', () => {
  for (const s of ['ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']) {
    const keys = requiredKeys(s)
    assert.ok(keys.includes('article_id') && keys.includes('counterparty_id'), s)
    assert.ok(!keys.includes('bank') && !keys.includes('date'), s)
  }
})

test('заполненная операция ничего не просит', () => {
  assert.deepEqual(missingFields({
    status: 'ОПЛАЧЕНО', period: '2026-11', article_id: 3, counterparty_id: 4, date: '2026-11-27', bank: 'АльфаБанк',
  }), [])
})

test('ноль и пробелы — пусто, у каждой подписи есть слово', () => {
  assert.deepEqual(missingFields({ status: 'ПЛАН ОПЛАТ', period: '  ', article_id: 0, counterparty_id: '' }).map(x => x.key),
    ['period', 'article_id', 'counterparty_id'])
  for (const k of ['status', 'period', 'article_id', 'counterparty_id', 'date', 'bank']) assert.ok(FIELD_LABEL[k])
})
