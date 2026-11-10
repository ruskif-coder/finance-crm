// Номер и дата счёта/УПД из имени файла 1С (владелец 10.11.2026: «если счет и упд имеют дату и номер в название при подгрузке —
// можешь их считывать и подставлять?»). Ломается, если месяц словом или «дд.мм.гггг» перестанут читаться, или имя без номера
// начнёт что-то подставлять.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseDocFileName } from './docFileName.mjs'

test('счёт из 1С: номер и дата месяцем словом', () => {
  assert.deepEqual(parseDocFileName('Счет на оплату № 291 от 06 ноября 2026 г..pdf'), { no: '291', date: '06.11.2026' })
})
test('УПД со статусом в скобках', () => {
  assert.deepEqual(parseDocFileName('УПД (статус 1) № 244 от 31 октября 2026 г.pdf'), { no: '244', date: '31.10.2026' })
})
test('дата цифрами и номер без пробела', () => {
  assert.deepEqual(parseDocFileName('Счёт №1247 от 5.11.2026.pdf'), { no: '1247', date: '05.11.2026' })
})
test('номер с буквами и дефисом', () => {
  assert.deepEqual(parseDocFileName('УПД № АБ-17 от 1 декабря 2026.pdf'), { no: 'АБ-17', date: '01.12.2026' })
})
test('нет номера — ничего не подставляем', () => {
  assert.equal(parseDocFileName('scan_0001.pdf'), null)
  assert.equal(parseDocFileName(''), null)
})
test('номер есть, даты нет — только номер', () => {
  assert.deepEqual(parseDocFileName('Счет № 300.pdf'), { no: '300', date: null })
})
