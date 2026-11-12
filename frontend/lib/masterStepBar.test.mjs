// Полоса «что сделать сейчас» в расхлопе реестра (хендофф реестра v3, 12.11.2026). Поломки, которые ловит набор: главная
// кнопка отмечает и уже отправленные документы; счёт «N документов» врёт после частичной отметки; без права на правку
// видна кнопка действия; стадия без действия получает кнопку; бумага получает диадоковский текст.
import test from 'node:test'
import assert from 'node:assert/strict'
import { stepBar } from './masterStepBar.js'

const sign = (state, channel = 'ЭДО') => ({ state, channel })
const pack = (status, ds, { channel = 'ЭДО', paper = false, who = 'аккаунт' } = {}) => ({
  code: 'M-0034', status, todo: { text: 'подтвердить ДС (1)', who }, issue: { channel, paper }, docs: { ds },
})
const edo = (dsState, k1, k2) => [{ annex_id: 4, number: 'ДС № 4', sign: sign(dsState),
  kits: [{ upd_no: 1, sign: sign(k1) }, { upd_no: 2, sign: sign(k2) }] }]

test('ЭДО, ничего не отправлено — все три документа и «отправил все 3»', () => {
  const b = stepBar(pack('выставление', edo('согласован', null, null)), true)
  assert.equal(b.no, 4)
  assert.equal(b.tone, 'act')
  assert.equal(b.title, 'Отправьте клиенту через Диадок: 3 документа — ДС № 4, комплект 1, комплект 2')
  assert.equal(b.zip, true)
  assert.equal(b.btn.label, 'Отметить: отправил все 3')
  assert.deepEqual(b.btn.body, { items: [{ annex_id: 4 }, { upd_no: 1 }, { upd_no: 2 }], on: true, state: 'выставлен' })
})

test('ЭДО, ДС отправлен — главная кнопка только про оставшиеся два', () => {
  const b = stepBar(pack('выставление', edo('выставлен', null, null)), true)
  assert.equal(b.title, 'Осталось отправить клиенту через Диадок: 2 документа — комплект 1, комплект 2')
  assert.equal(b.btn.label, 'Отметить: отправил остальные 2')
  assert.deepEqual(b.btn.body.items, [{ upd_no: 1 }, { upd_no: 2 }])
  assert.match(b.sub, /Отправлено 1 из 3/)
})

test('без права на правку — объяснение без кнопки', () => {
  const b = stepBar(pack('выставление', edo('согласован', null, null)), false)
  assert.equal(b.btn, null)
  assert.equal(b.zip, true)
})

test('ждём 1С — серая полоса без действия; без канала — красная со ссылкой на договор', () => {
  const w = stepBar(pack('ждём 1С', edo('согласован', null, null)), true)
  assert.deepEqual([w.no, w.tone, w.title, w.btn, w.link], [3, 'wait', 'Ждём счёт и УПД из 1С', null, null])
  const bad = stepBar(pack('ждём 1С', edo('согласован', null, null), { channel: null }), true)
  assert.equal(bad.tone, 'bad')
  assert.equal(bad.link.label, 'Открыть договор')
})

test('бумага на выставлении — сначала «подписано у нас» для всех, потом «отправлено клиенту»', () => {
  const ours = stepBar(pack('выставление', edo('согласован', null, null), { channel: 'бумага', paper: true }), true)
  assert.equal(ours.title, 'Распечатайте и подпишите документы у нас')
  assert.deepEqual(ours.btn.body, { items: [], on: true, state: 'подписан у нас' })
  assert.equal(ours.zip, false)
  const out = stepBar(pack('выставление', edo('подписан у нас', 'подписан у нас', 'подписан у нас'), { channel: 'бумага', paper: true }), true)
  assert.equal(out.title, 'Отправьте подписанные документы клиенту')
  assert.equal(out.btn.track, true)
})

test('согласование у юриста — ждём, у аккаунта — ссылка к ДС', () => {
  assert.equal(stepBar(pack('согласование', edo('выпущен', null, null), { who: 'юрист' }), true).link, null)
  assert.equal(stepBar(pack('согласование', edo('выпущен', null, null)), true).link.href, '/accounts/master/M-0034')
})

test('архив — зелёная полоса «Пакет закрыт», шаг 6', () => {
  const b = stepBar(pack('архив', edo('подписан', 'подписан', 'подписан')), true)
  assert.deepEqual([b.no, b.tone, b.title], [6, 'ok', 'Пакет закрыт'])
})

test('остался один документ — кнопка называет его, а не «остальные 1»', () => {
  const b = stepBar(pack('выставление', edo('выставлен', 'выставлен', null)), true)
  assert.equal(b.btn.label, 'Отметить: отправил комплект 2')
})

test('отклонённый клиентом не попадает в «отправил все»', () => {
  const b = stepBar(pack('выставление', edo('отклонён', null, 'выставлен')), true)
  assert.equal(b.btn.label, 'Отметить: отправил комплект 1')
  assert.deepEqual(b.btn.body.items, [{ upd_no: 1 }])
})
