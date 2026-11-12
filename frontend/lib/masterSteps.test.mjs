// Строка ДС в карточке мастер-сделки (прод 12.11.2026, M-0036): у стартового пакета после «Отправить в ДО» его подписанный ДС
// старта остаётся в пакете, а сам пакет — черновик. Карточка считала этот ДС «ДС пакета созданы» и прятала «В конструктор ДС →» —
// закрыть пакет было нечем. Ломается, если строку снова строить по одному наличию ДС, без статуса пакета.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createdAnnexes } from './masterSteps.js'

const START_DS = { id: 71, number: 'Приложение № 95', confirmed: true, primary: true }

test('черновик пакета: ДС старта не прячет кнопку конструктора', () => {
  assert.deepEqual(createdAnnexes({ status: 'черновик', annexes: [START_DS] }), [])
})

test('после «В конструктор ДС» — ДС пакета видны', () => {
  const draft = { id: 80, number: 'Приложение № 96', confirmed: false, primary: false }
  assert.deepEqual(createdAnnexes({ status: 'согласование', annexes: [draft] }), [draft])
  assert.deepEqual(createdAnnexes({ status: 'ждём 1С', annexes: [START_DS] }), [START_DS])
})

test('нет пакета или ДС — пусто', () => {
  assert.deepEqual(createdAnnexes(null), [])
  assert.deepEqual(createdAnnexes({ status: 'черновик', annexes: [] }), [])
})

test('кнопка строки «Отправить» считает оставшиеся документы (реестр v3)', async () => {
  const { STEP, stepLabel } = await import('./masterSteps.js')
  assert.equal(stepLabel(STEP.send, 'send', { left: 3, total: 3 }), 'Отправить · 3')
  assert.equal(stepLabel(STEP.send, 'send', { left: 2, total: 3 }), 'Отправить · ещё 2')
  assert.equal(stepLabel(STEP.docs, 'docs', null), 'Документы')
})
