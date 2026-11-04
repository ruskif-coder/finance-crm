// node lib/directoryAddCreate.test.mjs — «Заведение» окна контрагента (входит в `npm run test-rk`).
//
// Поломки, которые ловит (ревью 05.11.2026): роль без права на справочник получает полусозданного контрагента; дата
// «31.02.2026» или «60 дн» падает на последнем шаге после созданного договора; договор площадки не привязан к площадке,
// и сверка его не видит; CPM и НДС площадки молча теряются.
import assert from 'node:assert/strict'
import { createFromWizard, validateNew } from './directoryAddCreate.mjs'

const ALL = { cp: true, agency: true, advertiser: true, publisher: true, contract: true, sk: true }
const fake = () => {
  const calls = []
  let n = 100
  const reply = (m, u, b) => { calls.push([m, u, b]); return Promise.resolve({ id: ++n }) }
  return { calls, get: u => reply('GET', u), post: (u, b) => reply('POST', u, b), put: (u, b) => reply('PUT', u, b) }
}

// права — до первой записи
{
  const http = fake()
  const r = await createFromWizard(http, 'agency', { 'cp.name': 'ООО «Тест»', 'ag.short_name': 'Тест' }, { ...ALL, agency: false })
  assert.equal(http.calls.length, 0, 'без права на агентства не создаётся и контрагент')
  assert.ok(r.refused && r.steps[0].label.includes('Агентства · правка'))
}

// формат ввода — до первой записи
assert.ok(validateNew('contractor', { 'cp.name': 'x', 'ct.date': '31.02.2026' }, ALL).some(p => p.includes('дата договора')))
assert.ok(validateNew('contractor', { 'cp.name': 'x', 'cp.term_days': '60 дн' }, ALL).some(p => p.includes('отсрочка')))
assert.ok(validateNew('agency', { 'cp.name': 'x', 'ag.short_name': 'А', 'sk.percent': '20' }, ALL).some(p => p.includes('«с»')))
assert.ok(validateNew('agency', { 'cp.name': 'x', 'ag.name_ru': 'А' }, ALL).some(p => p.includes('короткое имя')))
assert.deepEqual(validateNew('contractor', { 'cp.name': 'x', 'ct.date': '29.02.2028', 'cp.term_days': '0' }, ALL), [])

// площадка: CPM в площадку, НДС — исходящий её юрлица, договор привязан к площадке
{
  const http = fake()
  const r = await createFromWizard(http, 'publisher', { 'cp.name': 'ООО «Площадка»', 'pub.domain': 'site.example', 'pub.cpm': '120',
    'pub.publisher_vat': '22', 'ct.number': 'П-1', 'ct.date': '01.11.2026' }, ALL)
  assert.equal(r.failed, false)
  const at = (m, u) => http.calls.find(([mm, uu]) => mm === m && uu === u)
  assert.equal(at('POST', '/publishers')[2].cpm_contract, 120)
  assert.deepEqual(at('PUT', '/counterparties/101/defaults')[2], { vat_rate_expense: 22 })
  assert.equal(at('POST', '/contracts/')[2].contract_date, '2026-11-01')
  const link = http.calls.find(([m, u]) => m === 'POST' && /^\/publishers\/\d+\/contracts$/.test(u))
  assert.ok(link && link[2].contract_id, 'договор площадки не привязан к площадке')
}
// «прикрепить существующее» (владелец 05.11.2026): юрлицо и его реквизиты не трогаются, права на контрагентов не нужно
{
  const http = fake()
  const rights = { ...ALL, cp: false }
  const r = await createFromWizard(http, 'agency', { 'cp.mode': 'attach', 'cp.attach_id': 55, 'cp.attach_name': 'ООО «Есть»',
    'ag.short_name': 'Есть' }, rights)
  assert.equal(r.failed, false); assert.equal(r.cpId, 55)
  assert.ok(!http.calls.some(([m, u]) => u === '/counterparties/' || u.includes('/requisites') || u.includes('/registry') || u.startsWith('/signers')),
    'прикреплённое юрлицо переписано')
  assert.deepEqual(http.calls.find(([m, u]) => /agencies\/\d+\/counterparties$/.test(u))[2], { counterparty_id: 55 })
  assert.ok(validateNew('agency', { 'cp.mode': 'attach', 'ag.short_name': 'А' }, ALL).some(p => p.includes('из списка')))
}

// «без юрлица» (вариант Б, владелец 05.11.2026): только запись справочника — роль без права на контрагентов её заводит
{
  const http = fake()
  const r = await createFromWizard(http, 'agency', { 'cp.mode': 'none', 'ag.short_name': 'Только агентство' }, { ...ALL, cp: false })
  assert.equal(r.failed, false); assert.equal(r.cpId, null)
  assert.deepEqual(http.calls.map(([m, u]) => `${m} ${u}`), ['POST /sales/directories/agencies'])
  assert.ok(validateNew('agency', { 'cp.mode': 'none', 'ag.short_name': 'А', 'ct.number': '1' }, ALL).some(p => p.includes('юрлицо')))
  assert.ok(validateNew('contractor', { 'cp.mode': 'none' }, ALL).length > 0, 'подрядчик без юрлица — пустое место')
}
console.log('directoryAddCreate: ok')
