// Где расходятся основание сделки и наименование услуги в XML УПД (владелец 19.11.2026).
// Поломки: подсвечивается не то слово; оформление (кавычки, тире, регистр) подсвечивается как разница; невидимая разница
// не названа — человек снова смотрит на два одинаковых текста.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { diffWords, explainDiff } from './textDiff.mjs'

const AGREED = 'Размещение рекламы по ДС №66 от 05.10.26 к Договору РМ-03-06-2024, бренд «Тест»'

test('подсвечено ровно отличающееся слово, с обеих сторон', () => {
  const d = diffWords(AGREED.replace('№66', '№67'), AGREED)
  assert.deepEqual(d.got.filter(x => x.bad).map(x => x.t), ['№67'])
  assert.deepEqual(d.want.filter(x => x.bad).map(x => x.t), ['№66'])
  assert.deepEqual(explainDiff(AGREED.replace('№66', '№67'), AGREED), ['в УПД «№67» вместо «№66» — другие цифры'])
})

test('оформление не подсвечивается', () => {
  const d = diffWords(AGREED.replace('«Тест»', '“Тест”').replace('Размещение', 'РАЗМЕЩЕНИЕ'), AGREED)
  assert.equal(d.got.some(x => x.bad), false)
})

test('невидимая разница названа символами', () => {
  assert.deepEqual(explainDiff(AGREED.replace('по ДС', 'по ДС'), AGREED), ['слова те же, в УПД другие символы: неразрывный пробел'])
  assert.deepEqual(explainDiff(AGREED.replace('бренд', 'бренд\n'), AGREED), ['слова те же, в УПД другие символы: перевод строки'])
})

test('лишнее и недостающее', () => {
  assert.deepEqual(explainDiff(AGREED + ' РК Осень', AGREED), ['в УПД лишнее: «РК Осень»'])
  // запятая у соседнего слова — оформление, недостаёт только «бренд «Тест»»
  assert.deepEqual(explainDiff(AGREED.replace(', бренд «Тест»', ''), AGREED), ['в УПД нет: «бренд «Тест»»'])
})

test('одинаковые тексты — без пояснений', () => {
  assert.deepEqual(explainDiff(AGREED, AGREED), [])
})
