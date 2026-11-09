// Короткий номер ДС на экранах (владелец 09.11.2026: «в колонке ДС пиши кратко ДС №, ПР №», реестр операций и мастер-сделок).
// Ломается, если вернуть «Прил. №» или если сокращение начнёт трогать ручные записи вида «доп 18» / «прил.1».
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { shortAnnexNumber } from './annexNumber.js'

test('приложение и доп. соглашение — коротко', () => {
  assert.equal(shortAnnexNumber('Приложение № 17'), 'ПР № 17')
  assert.equal(shortAnnexNumber('Дополнительное соглашение № 28'), 'ДС № 28')
  assert.equal(shortAnnexNumber('Доп. соглашение №68'), 'ДС № 68')
})

test('ручные записи и пустое — как есть', () => {
  assert.equal(shortAnnexNumber('доп 18'), 'доп 18')
  assert.equal(shortAnnexNumber('прил.1'), 'прил.1')
  assert.equal(shortAnnexNumber(''), '')
  assert.equal(shortAnnexNumber(null), null)
})
