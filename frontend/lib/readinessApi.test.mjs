// node lib/readinessApi.test.mjs — окно контрагента: куда уходит «Сохранить» блока (входит в `npm run test-rk`).
//
// Поломки, которые ловит: правка реквизитов зовёт лишнюю ручку или не перечитывает окно; новый договор уходит без
// контрагента; отказ ручки теряется вместо подсказки у поля; новая доверенность не отправляет старую в архив;
// примечание юрлица стирается (ручка реквизитов перезаписывает его целиком).
import assert from 'node:assert/strict'
import { createReadinessApi, mapReadiness } from './readinessApi.mjs'

const RAW = {
  kinds: ['agency'], blocks: ['cp', 'sg', 'ct'], checks: [], total: 3, headline: 'всё готово к документам и ОРД',
  counterparty: { id: 7, name: 'ООО «Тест»', legal_form: null, inn: '7707083893', kpp: '770701001', ogrn: null, okpo: null,
    address: null, fact_address: null, phone: null, email: null, site: null, edo_id: null, term_days: 60, status: 'действующий',
    note: 'важное примечание' },
  banks: [{ id: 1, bank: 'Банк', bik: '044525000', ks: '30101810000000000000', rs: '40702810000000000001', city: 'Москва', main: true }],
  signers: [{ id: 12, name: 'Петрова А. С.', role: 'директор', basis: 'Доверенность № 15', poa_until: '2026-11-20', is_default: true, archived: false, where: [] }],
  contracts: [{ id: 501, number: 'РМ-01/25', date: '2025-01-15', format: null, annex_word: 'ДС' }],
  options: { signers: [{ id: 12, label: 'Петрова А. С. — директор' }], ourSigners: [] },
  permissions: { view: ['counterparties', 'contracts'], edit: ['counterparties', 'contracts'] },
}

function fakeHttp(fail) {
  const calls = []
  const reply = (method, url, body) => {
    calls.push([method, url, body])
    if (fail && fail(method, url)) return Promise.reject({ response: { status: 400, data: { detail: fail(method, url) } } })
    if (method === 'GET' && url.startsWith('/directory-add/readiness/7/history')) return Promise.resolve({ items: [] })
    if (method === 'GET') return Promise.resolve(RAW)
    return Promise.resolve({ id: 900 })
  }
  return { calls, get: u => reply('GET', u), post: (u, b) => reply('POST', u, b), put: (u, b) => reply('PUT', u, b) }
}
const writes = calls => calls.filter(([m]) => m !== 'GET')

// реквизиты: ровно одна ручка с полным набором, примечание и счёт возвращаются как были, затем перечитка
{
  const http = fakeHttp(); const api = createReadinessApi(http)
  const data = await api.load(7)
  const draft = { counterparty: { ...data.counterparty, kpp: '770702001', legal_form: 'ООО' }, banks: data.banks }
  http.calls.length = 0
  const res = await api.saveBlock(7, 'cp', draft)
  const w = writes(http.calls)
  assert.equal(w.length, 1)
  assert.equal(w[0][0], 'PUT'); assert.equal(w[0][1], '/counterparties/7/requisites')
  assert.equal(w[0][2].kpp, '770702001'); assert.equal(w[0][2].legal_form, 'ООО')
  assert.equal(w[0][2].note, 'важное примечание')
  assert.equal(w[0][2].bank_accounts[0].rs, '40702810000000000001')
  assert.ok(http.calls.some(([m, u]) => m === 'GET' && u === '/directory-add/readiness/7'), 'после записи окно перечитывается')
  assert.ok(res.data)
}

// новый договор — POST с контрагентом
{
  const http = fakeHttp(); const api = createReadinessApi(http)
  const data = await api.load(7)
  http.calls.length = 0
  await api.saveBlock(7, 'ct', { contracts: [...data.contracts, { id: null, _new: true, number: 'РМ-03/26', annex_word: 'ДС' }] })
  const w = writes(http.calls)
  assert.equal(w.length, 1)
  assert.deepEqual([w[0][0], w[0][1]], ['POST', '/contracts/'])
  assert.equal(w[0][2].counterparty_id, 7); assert.equal(w[0][2].contract_number, 'РМ-03/26')
}

// отказ ручки → подсказка у поля, перечитки нет
{
  const http = fakeHttp((m, u) => (m === 'PUT' && u.endsWith('/requisites') ? 'КПП — 9 цифр' : null))
  const api = createReadinessApi(http)
  const data = await api.load(7)
  http.calls.length = 0
  const res = await api.saveBlock(7, 'cp', { counterparty: { ...data.counterparty, kpp: '1' }, banks: data.banks })
  assert.deepEqual(res, { errors: { kpp: 'КПП — 9 цифр' } })
  assert.ok(!http.calls.some(([m]) => m === 'GET'))
}

// новая доверенность вместо старой: новая строка и старая — в архив
{
  const http = fakeHttp(); const api = createReadinessApi(http)
  const data = await api.load(7)
  http.calls.length = 0
  await api.saveBlock(7, 'sg', { signers: [...data.signers,
    { id: null, _new: true, _replaces: 12, name: 'Петрова А. С.', role: 'директор', basis: 'Доверенность № 16', poa_until: '20.11.2027' }] })
  const w = writes(http.calls)
  // старый — подписант по умолчанию: архив такого ручка отклоняет (409), поэтому сперва новый становится основным (ревью 05.11)
  assert.deepEqual(w.map(([m, u]) => `${m} ${u}`), ['POST /signers/counterparty/7', 'PUT /signers/900/default', 'PUT /signers/12/archive'])
  assert.equal(w[0][2].valid_until, '2027-11-20'); assert.equal(w[0][2].signer_basis, 'Доверенность № 16')
  assert.deepEqual(w[2][2], { on: true })
}

// просмотр: даты по-русски, подписанты договора — подписями
{
  const v = mapReadiness(RAW, {})
  assert.equal(v.signers[0].poa_until, '20.11.2026')
  assert.equal(v.contracts[0].date, '15.01.2025')
  assert.deepEqual(v.options.signers, ['Петрова А. С. — директор'])
}
// новое правило СК: договор — по точному номеру, а не по вхождению («договор 12» ≠ договор «1»); пустой процент — отказ, не 0 %
{
  const RAW2 = { ...RAW, blocks: ['ct', 'sk'], agency: { id: 3, short_name: 'Аг' }, sk: [],
    contracts: [{ id: 1, number: '1' }, { id: 12, number: '12' }] }
  const http = fakeHttp(); http.get = u => (http.calls.push(['GET', u]), Promise.resolve(u.includes('history') ? { items: [] } : RAW2))
  const api = createReadinessApi(http)
  await api.load(7)
  http.calls.length = 0
  await api.saveBlock(7, 'sk', { sk: [{ id: null, _new: true, target: 'договор 12', mode: 'постоплата', percent: '20 %', from: '01.01.2026', till: '' }] })
  const w = writes(http.calls)
  assert.deepEqual([w[0][1], w[0][2].contract_id, w[0][2].agency_id, w[0][2].percent], ['/agency-terms/rules', 12, 3, 20])
  http.calls.length = 0
  const res = await api.saveBlock(7, 'sk', { sk: [{ id: null, _new: true, target: '12', mode: 'постоплата', percent: '', from: '01.01.2026' }] })
  assert.equal(writes(http.calls).length, 0); assert.ok(res.errors._)
}
console.log('readinessApi: ok')
