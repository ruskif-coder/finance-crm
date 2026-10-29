// node lib/agencyTerms.test.mjs — подписи и периоды экрана «Агентские условия» (входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import { featureText, isActive, namesOf, parsePct, periodLabel, periodOptions, ruleLabel, specificity } from './agencyTerms.mjs'

const rule = { contract_id: 7, agency_id: 3, brand_id: 21, advertiser_id: null, service_id: null,
  mode: 'постоплата', percent: 12.5, valid_from: '2026-01-01', valid_to: null }
assert.equal(specificity(rule), 3)
assert.equal(ruleLabel(rule), 'постоплата 12,5 % · с 01.01.2026')
assert.equal(ruleLabel({ ...rule, valid_to: '2026-12-31' }), 'постоплата 12,5 % · с 01.01.2026 по 31.12.2026')

const names = namesOf({ agencies: [{ id: 3, name: 'ОККАМ' }], brands: [{ id: 21, name: 'Нурофен' }],
  contracts: [{ id: 7, number: 'РМ-1', date: '2025-04-14' }] })
assert.equal(featureText(rule, names), 'договор РМ-1 от 14.04.2025 · агентство ОККАМ · бренд Нурофен')
assert.equal(featureText(rule, names, ['contract_id', 'agency_id']), 'бренд Нурофен')

assert.equal(isActive(rule, '2026-10-31'), true)
assert.equal(isActive({ ...rule, valid_to: '2026-09-30' }, '2026-10-31'), false)

const p = periodOptions('2026-10', 4)
assert.deepEqual(p.months, ['2026-10', '2026-09', '2026-08', '2026-07'])
assert.deepEqual(p.quarters, ['2026-Q4', '2026-Q3'])
assert.deepEqual(periodOptions('2026-01', 2).months, ['2026-01', '2025-12'])
assert.equal(periodLabel('2026-Q4'), '4 квартал 2026')
assert.equal(periodLabel('2026-10'), 'октябрь 2026')

assert.equal(parsePct('12,5'), 12.5)
assert.equal(parsePct('101'), null)
assert.equal(parsePct('десять'), null)
assert.equal(parsePct(''), null)
console.log('agencyTerms: ok')

// ── хендофф 27.10.2026: плоская таблица и группировка расчёта ──
import { filterSide, flattenSide, groupCalc, precisionCells, sideKpi } from './agencyTerms.mjs'
const tree = [
  { id: 1, name: 'ОККАМ', entities: [
    { id: 10, name: 'МЕДИАНА', contracts: [{ id: 7, rules: [{ ...rule, id: 1 }, { ...rule, id: 2, brand_id: 22, valid_to: '2026-03-31' }] }] },
    { id: 11, name: 'ДИДЖИТАЛ АЛЬЯНС', contracts: [{ id: 8, rules: [] }] }] },
  { id: 2, name: 'Adlabs', entities: [{ id: 12, name: 'АДЛАБС', contracts: [{ id: 9, rules: [{ ...rule, id: 3, mode: 'скидка в счёт' }] }] }] },
]
const flat = flattenSide(tree, '2026-10-31')
assert.equal(flat.length, 4)
assert.equal(flat.find((r) => r.rule && r.rule.id === 2).inactive, 'срок вышел')
const k = sideKpi(tree, flat)
assert.deepEqual([k.owners, k.entities, k.contracts, k.noRule, k.active, k.post, k.disc, k.inactive], [2, 3, 3, 1, 2, 1, 1, 1])
const sorted = filterSide(flat)
assert.equal(sorted[0].owner, 'ОККАМ')                     // группа с договором без условия — сверху
assert.equal(sorted[0].rule, null)                         // и внутри группы пустая строка первая
assert.equal(sorted[0].first, true)
assert.equal(filterSide(flat, { mode: 'empty' }).length, 1)
assert.equal(filterSide(flat, { mode: 'скидка в счёт' })[0].owner, 'Adlabs')
assert.equal(filterSide(flat, { q: 'альянс' }).length, 1)
assert.deepEqual(precisionCells(rule), [true, true, true, false])

const deals = [
  { deal_id: 1, period: '2026-10', side: 'ОККАМ', master_code: 'M-1', contract: 'РМ-1', entity: 'МЕДИАНА', base_net: 100, main: { amount: 10 } },
  { deal_id: 2, period: '2026-10', side: 'ОККАМ', master_code: 'M-2', contract: 'ДА-5', entity: 'ДА', base_net: 200, main: { amount: 20 } },
  { deal_id: 3, period: '2026-10', side: 'Adlabs', master_code: 'M-3', contract: 'РМ-3', entity: 'АДЛАБС', base_net: 50, main: { amount: null } },
]
const ga = groupCalc(deals, 'agency')
assert.deepEqual(ga.map((r) => r.type), ['side', 'deal', 'deal', 'side', 'deal'])   // «ОККАМ» раньше «Adlabs» в русской сортировке
assert.equal(ga[0].base, 300)
const gp = groupCalc(deals, 'pack')
assert.deepEqual(gp.map((r) => r.type), ['side', 'pack', 'deal', 'pack', 'deal', 'side', 'pack', 'deal'])
assert.equal(gp[1].contract, 'РМ-1 · МЕДИАНА')
console.log('agencyTerms (хендофф): ok')

// ── «Условия работы»: подбор под бриф ──
import { matchWork } from './agencyTerms.mjs'
const W = [
  { id: 1, agency_id: 27, valid_from: '2026-01-01', valid_to: '2026-12-31', body: 'ОККАМ общие' },
  { id: 2, agency_id: 27, advertiser_id: 195, valid_from: '2026-01-01', valid_to: null, body: 'ОККАМ + Биннофарм' },
  { id: 3, advertiser_id: 195, service_id: 5, names: { service: 'еФарм' }, valid_from: '2026-01-01', body: 'Биннофарм еФарм' },
  { id: 4, agency_id: 13, valid_from: '2026-01-01', body: 'G4M' },
  { id: 5, contract_id: 7, valid_from: '2026-01-01', body: 'по договору' },
  { id: 6, agency_id: 27, valid_from: '2025-01-01', valid_to: '2025-12-31', body: 'прошлый год' },
]
const got = (ctx) => matchWork(W, ctx).map((t) => t.id)
assert.deepEqual(got({ agency_id: 27, advertiser_id: '195', services: ['еФарм '], period: '2026-10' }), [2, 3, 1])  // точные выше
assert.deepEqual(got({ agency_id: 27, advertiser_id: 195, services: ['Polza'], period: '2026-10' }), [2, 1])         // услуга не та
assert.deepEqual(got({ agency_id: 27, period: '2025-06' }), [6])                                                    // срок
assert.deepEqual(got({ agency_id: null, advertiser_id: 195, services: [], period: '2026-10' }), [])
// Условие по рекламодателю без агентства видно сразу по рекламодателю — и без агентства в брифе, и при любом агентстве (владелец 28.10.2026)
{
  const W2 = [...W, { id: 7, advertiser_id: 192, valid_from: '2026-01-01', body: 'Bayer — без агентства' }]
  assert.deepEqual(matchWork(W2, { advertiser_id: 192, period: '2026-11' }).map((t) => t.id), [7])
  assert.deepEqual(matchWork(W2, { agency_id: 27, advertiser_id: 192, period: '2026-11' }).map((t) => t.id), [1, 7])
}
console.log('agencyTerms (условия работы): ok')

// «Расчёт»: сделка без условия СК подсвечивается, с причиной (владелец 27.10.2026)
{
  const { skGap, newRuleFor } = await import('./agencyTerms.mjs')
  assert.equal(skGap({ main: { mode: 'постоплата' }, contract_id: 7 }), null)
  assert.equal(skGap({ mode: 'скидка в счёт', contract_id: 7 }), null, 'строка «не закрыты» — способ в самой строке')
  assert.deepEqual(skGap({ main: { mode: null }, contract_id: null }), { kind: 'no_contract', label: 'нет договора закрытия' })
  assert.deepEqual(skGap({ mode: null, contract_id: 7 }), { kind: 'no_terms', label: 'нет условия к договору' })
  assert.deepEqual(newRuleFor({ contract_id: 7, agency_id: 3, advertiser_id: 11 }), { kind: 'основная', contract_id: 7, agency_id: 3 })
  assert.deepEqual(newRuleFor({ contract_id: 7, agency_id: null, advertiser_id: 11 }), { kind: 'основная', contract_id: 7, advertiser_id: 11 })
  assert.equal(newRuleFor({ contract_id: null, agency_id: 3 }), null, 'без договора правило не заводим — ждём договор')
}

// Плашка «Условия работы» в МП: период условия в углу карточки, если задан (владелец 27.10.2026)
{
  const { workPeriod } = await import('./agencyTerms.mjs')
  assert.equal(workPeriod({ valid_from: '2026-01-01', valid_to: '2026-12-31' }), '01.01.2026 – 31.12.2026')
  assert.equal(workPeriod({ valid_from: '2026-03-01', valid_to: null }), 'с 01.03.2026')
  assert.equal(workPeriod({ valid_from: null, valid_to: '2026-06-30' }), 'по 30.06.2026')
  assert.equal(workPeriod({ valid_from: null, valid_to: null }), '')
}

// Условие работы: креативы / отчёты бонусом — подписи для списка и плашки МП (владелец 27.10.2026)
{
  const { workBonuses } = await import('./agencyTerms.mjs')
  assert.deepEqual(workBonuses({ creatives_bonus: true, creatives_bonus_note: 'при бюджете от 1 млн', reports_bonus: false }),
    [{ key: 'creatives', label: 'Креативы бонусом', note: 'при бюджете от 1 млн' }])
  assert.deepEqual(workBonuses({ creatives_bonus: true, reports_bonus: true, reports_bonus_note: null }).map((b) => [b.key, b.note]),
    [['creatives', ''], ['reports', '']])
  assert.deepEqual(workBonuses({}), [])
}

// Периоды расчёта и год по умолчанию — один раз для «Расчёта» и «Спец. условий» (ревью 27.10.2026: были копии)
{
  const { calcPeriods, defaultValidFrom } = await import('./agencyTerms.mjs')
  const { periods, initial } = calcPeriods('2026-10')
  assert.equal(initial, '2026-10')
  assert.deepEqual(periods.map(([k]) => k), ['2026-08', '2026-09', '2026-10', '2026-Q4'])
  assert.equal(periods[2][1], 'октябрь 2026')
  assert.equal(periods[0][1], 'август')
  assert.equal(defaultValidFrom('2026-10-27'), '2026-01-01')
}
