// node --test lib/rkAnalysis.test.mjs — расчёты «Разбора РК» на маленьком наборе, где всё считается в уме.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { indexData, kpis, sumOf, planFor, wrDiff, wrLevel, cpmOf, insights, elapsedDays } from './rkAnalysis.mjs'
import { tableModel, timeRows, dowTable, wrByDay, gapTable, prevCompare, periodDays } from './rkAnalysisSlices.mjs'

const day = n => `2026-10-${String(n).padStart(2, '0')}`

function fixture() {
  const stat = []
  for (let n = 1; n <= 5; n++) {
    stat.push({ placement_id: 1, date: day(n), source: 'dsp', shows: 1000, clicks: 10, offered: n >= 3 ? 5000 : null })
    stat.push({ placement_id: 1, date: day(n), source: 'weborama', shows: 1100 })
    stat.push({ placement_id: 2, date: day(n), source: 'adfox', shows: 500, clicks: 0 })
    stat.push({ placement_id: 2, date: day(n), source: 'weborama', shows: 700 })
  }
  stat.push({ placement_id: 1, date: day(6), source: 'dsp', shows: 999999 })   // после среза — не в счёт
  const creative_days = []
  for (let n = 1; n <= 5; n++) {
    creative_days.push({ date: day(n), placement_id: 1, set_no: 1, set_title: 'А', shows: 600, clicks: 3, spend: n === 1 ? 120 : 60 })
    creative_days.push({ date: day(n), placement_id: 1, set_no: 2, set_title: 'Б', shows: 400, clicks: 7, spend: 40 })
  }
  return {
    head: { date_start: day(1), date_end: day(10), as_of: day(5), plan_show: 30000, plan_budget: 3000, offer_from: day(3),
      wr_limit: 10, goals: { ctr: '0,8%', freq: '5', cr: '1%' } },
    placements: [
      { id: 1, domain: 'a.ru', plan_show: 20000, share: 0.667, external: false, status: 'запущен', cpm: 100 },
      { id: 2, domain: 'b.ru', plan_show: 10000, share: 0.333, external: true, status: 'запущен', cpm: 160 },
    ],
    stat, creative_days,
    model_uniques: [1, 2, 3, 4, 5].map(n => ({ placement_id: 1, date: day(n), uniques: 250 })),
    events: [{ at: day(3) + 'T10:00', kind: 'start', placement_id: 2, text: 'РК X: площадка b.ru ждёт запуска → запущен' }],
  }
}

test('итоги считают только до среза и только включённые площадки', () => {
  const ix = indexData(fixture())
  const all = kpis(ix, [1, 2])
  assert.equal(all.fact, 7500)
  assert.equal(all.plan, 30000)
  assert.equal(all.forecast, 7500 / 5 * 10)
  assert.equal(all.need, (30000 - 7500) / 5)
  const one = kpis(ix, [1])
  assert.equal(one.plan, 20000, 'план = сумма планов включённых')
  assert.equal(one.fact, 5000)
})

test('флайт закрыт — прогноз равен факту, «нужно» нет', () => {
  const d = fixture(); d.head.as_of = day(10)
  const k = kpis(indexData(d), [1, 2])
  assert.equal(k.forecast, k.fact)
  assert.equal(k.need, null)
})

test('расхождение с Weborama — наше правило: знаменатель наш факт, знак «+» — WR меньше', () => {
  assert.equal(wrDiff(1000, 900), 10)
  assert.equal(wrDiff(1000, 1100), -10)
  assert.equal(wrDiff(0, 100), null)
  assert.equal(wrLevel(-10, 10), 'ok')
  assert.equal(wrLevel(-15, 10), 'warn')
  assert.equal(wrLevel(25, 10), 'bad')
  const t = sumOf(indexData(fixture()), [1, 2], elapsedDays(indexData(fixture())))
  assert.equal(t.wrPlaces, 2)
  assert.equal(Math.round(wrDiff(t.wrOwn, t.wrVer) * 10) / 10, Math.round((7500 - 9000) / 7500 * 1000) / 10)
})

test('площадка без Weborama в сравнение с Weborama не входит', () => {
  const d = fixture(); d.stat = d.stat.filter(r => !(r.placement_id === 2 && r.source === 'weborama'))
  const k = kpis(indexData(d), [1, 2])
  assert.equal(k.wrPlaces, 1)
  assert.equal(Math.round(k.wrPct * 10) / 10, -10)
})

test('расход — показы площадки × CPM договора; CPM дня — расход всех ÷ их показы; за период — среднее дневных', () => {
  const ix = indexData(fixture())
  const t = sumOf(ix, [1, 2], elapsedDays(ix))
  assert.equal(t.spend, 5000 * 100 / 1000 + 2500 * 160 / 1000)      // 500 + 400
  // каждый день: (1000×100 + 500×160) / 1500 = 120
  assert.equal(Math.round(cpmOf(ix, [1, 2], elapsedDays(ix)) * 100) / 100, 120)
  assert.equal(cpmOf(ix, [1], elapsedDays(ix)), 100)
})

test('площадка без CPM договора в расход и CPM не входит', () => {
  const d = fixture(); d.placements[1].cpm = null
  const ix = indexData(d)
  assert.equal(sumOf(ix, [1, 2], elapsedDays(ix)).spend, 500)
  assert.equal(cpmOf(ix, [1, 2], elapsedDays(ix)), 100)
})

test('план дня: остаток на утро ÷ дни до конца, с недокрутом прошлых дней; будущие — остаток', () => {
  const ix = indexData(fixture())
  // план 30000 на 10 дней, факт 1500 в день по 5 дней (в день 6 лишнего «после среза» нет)
  assert.equal(planFor(ix, [1, 2], [day(1)]), 3000)                              // 30000 ÷ 10
  assert.equal(planFor(ix, [1, 2], [day(2)]), (30000 - 1500) / 9)                 // недокрут первого дня растёт в плане
  assert.equal(planFor(ix, [1, 2], [day(5)]), (30000 - 4 * 1500) / 6)
  assert.equal(planFor(ix, [1, 2], [day(8)]), (30000 - 7500) / 5)                 // будущее — «нужно в день»
  // сумма по набору дней — сумма дневных
  assert.equal(planFor(ix, [1, 2], [day(1), day(2)]), 3000 + (30000 - 1500) / 9)
})

test('после перекрута (например, буст на пару дней) план следующих дней снижается', () => {
  const d = fixture()
  d.stat.forEach(r => { if (r.source === 'dsp' && (r.date === day(3) || r.date === day(4))) r.shows = 5000 })   // два дня «с бустом»
  const ix = indexData(d)
  const before = planFor(ix, [1, 2], [day(3)])
  const after = planFor(ix, [1, 2], [day(5)])
  assert.ok(after < before, `план дня после буста ${after} должен быть ниже, чем до него ${before}`)
  // и ниже, чем был бы без буста (тот же день на обычном факте)
  assert.ok(after < planFor(indexData(fixture()), [1, 2], [day(5)]))
})

test('план дня не уходит в минус, если факт обогнал план', () => {
  const d = fixture()
  d.stat.forEach(r => { if (r.source === 'dsp') r.shows = 100000 })
  const ix = indexData(d)
  ix.days.forEach(dt => assert.ok(planFor(ix, [1, 2], [dt]) >= 0, dt))
})

test('при плане «в ноль» факта день 1 равен исходному, а следующий день растёт на недокрут (нулевые дни)', () => {
  const d = fixture()
  d.stat = d.stat.filter(r => r.date >= day(3))          // первые два дня без статистики
  const ix = indexData(d)
  assert.equal(planFor(ix, [1, 2], [day(1)]), 3000)
  assert.ok(planFor(ix, [1, 2], [day(2)]) > 3000)
  assert.ok(planFor(ix, [1, 2], [day(3)]) > planFor(ix, [1, 2], [day(2)]))
})

test('выводы: нет «0 из 0», знак словами, событие с площадкой', () => {
  const ix = indexData(fixture())
  const out = insights(ix, [1, 2])
  const txt = out.map(x => x.text).join('\n')
  assert.ok(!/0 из 0/.test(txt))
  assert.ok(/Weborama по ним больше Adfox на 40 %/.test(txt), txt)
  assert.ok(/ёмкость в 5,0×/.test(txt), txt)
  assert.ok(/1 площадка вне DSP даёт 33 %/.test(txt), txt)
  assert.ok(/частота 6,0/.test(txt), txt)   // 7500 факта ÷ 1250 уников модели
})

test('частота = факт ÷ уники модели по включённым', () => {
  const k = kpis(indexData(fixture()), [1])
  assert.equal(k.freq, 5000 / 1250)
})

test('креативы: без общих площадок фраза о сравнении не пишется', () => {
  const d = fixture()
  d.creative_days = d.creative_days.map(r => r.set_no === 2 ? { ...r, placement_id: 2 } : r)
  const t = insights(indexData(d), [1, 2]).find(x => x.kind === 'креативы').text
  assert.ok(!/на общих площадках/.test(t), t)
})

test('ничего не включено — выводов нет', () => {
  assert.deepEqual(insights(indexData(fixture()), []), [])
})

test('CTR — клики на весь наш факт (Adfox тоже наш)', () => {
  const k = kpis(indexData(fixture()), [1, 2])
  assert.equal(k.ctr, 50 / 7500 * 100)
})

test('таблица по площадкам: итог из сумм, Δ WR по правилу, статус «вне DSP»', () => {
  const ix = indexData(fixture())
  const m = tableModel(ix, { slice: 'placement', ids: [1, 2], days: ix.days })
  assert.equal(m.rows.length, 2)
  assert.equal(m.tot.fact, 7500)
  assert.equal(m.tot.ctr, 50 / 7500 * 100)
  const b = m.rows.find(r => r.id === 2)
  assert.equal(b.wrLevel, 'bad')
  assert.equal(b.status, 'вне DSP')
})

test('проваливание: площадка → её дни; креатив → его площадки', () => {
  const ix = indexData(fixture())
  const d = tableModel(ix, { slice: 'placement', ids: [1, 2], days: ix.days, drill: { type: 'placement', id: 1, view: 'day' } })
  assert.equal(d.view, 'day'); assert.equal(d.rows.length, 5); assert.equal(d.tot.fact, 5000)
  const c = tableModel(ix, { slice: 'creative', ids: [1, 2], days: ix.days, drill: { type: 'creative', id: 2 } })
  assert.deepEqual(c.rows.map(r => r.id), [1])
  assert.equal(c.tot.fact, 2000)
})

test('график по времени: будущие дни без факта, план будущих = «нужно»', () => {
  const ix = indexData(fixture())
  const rows = timeRows(ix, [1, 2], ix.days, { slice: 'day', metric: 'shows', source: 'our' })
  assert.equal(rows.length, 10)
  assert.equal(rows[0].value, 1500)
  assert.equal(rows[7].value, null)
  assert.equal(rows[7].plan, (30000 - 7500) / 5)
  assert.equal(rows[0].active, 2)
})

test('периоды и аналитика: считают по включённым, вне DSP в карту предложений не входит', () => {
  const ix = indexData(fixture())
  assert.equal(periodDays(ix, '7d').length, 5)
  assert.equal(dowTable(ix, [1]).rows.length, 1)
  const w = wrByDay(ix, [1, 2])
  assert.equal(w.days.length, 5)
  assert.equal(w.breaks[0].label, 'b.ru')
  assert.equal(gapTable(ix, [1, 2]).rows.length, 1)
  assert.equal(prevCompare(ix, [1], null), null)
  const prev = { plan_show: 20000, length: 10, stat: [1, 2, 3, 4, 5].map(n => ({ domain: 'a.ru', day_no: n, source: 'own', shows: 800, clicks: 8 })) }
  const pc = prevCompare(ix, [1], prev)
  assert.equal(pc.rows[0].now, 5000); assert.equal(pc.rows[0].was, 4000)
  assert.equal(Math.round(pc.rows[1].d), 10)   // 50 % против 40 % плана к дате — в п.п.
})

test('значение метрики за отрезок — то, что пишется в строке над графиком', async () => {
  const { metricValue } = await import('./rkAnalysisSlices.mjs')
  const ix = indexData(fixture())
  const el = elapsedDays(ix), t = sumOf(ix, [1, 2], el)
  assert.equal(metricValue(ix, t, [1, 2], el, 'shows', 'our'), 7500)
  assert.equal(metricValue(ix, t, [1, 2], el, 'shows', 'wr'), 9000)
  assert.equal(metricValue(ix, t, [1, 2], el, 'clicks', 'our'), 50)
  assert.equal(metricValue(ix, t, [1, 2], el, 'spend', 'our'), 900)
  assert.equal(Math.round(metricValue(ix, t, [1, 2], el, 'cpm', 'our')), 120)
  // «% плана» за отрезок — факт ÷ сумма целей дней (с недокрутом): 3000 + 28500/9 + 27000/8 + 25500/7 + 24000/6
  const goals = 3000 + 28500 / 9 + 27000 / 8 + 25500 / 7 + 24000 / 6
  assert.equal(Math.round(metricValue(ix, t, [1, 2], el, 'plan', 'our')), Math.round(7500 / goals * 100))
})

test('дни «темпа размещения»: план дня поднят на процент буста, дни помечены, до и после — обычные', () => {
  const d = fixture()
  d.boosts = [{ pct: 20, from: day(3), to: day(4) }]
  const ix = indexData(d), plain = indexData(fixture())
  assert.equal(planFor(ix, [1, 2], [day(2)]), planFor(plain, [1, 2], [day(2)]))            // до буста
  assert.equal(planFor(ix, [1, 2], [day(3)]), planFor(plain, [1, 2], [day(3)]) * 1.2)       // в день буста
  assert.equal(planFor(ix, [1, 2], [day(4)]), planFor(plain, [1, 2], [day(4)]) * 1.2)
  assert.equal(planFor(ix, [1, 2], [day(5)]), planFor(plain, [1, 2], [day(5)]))            // после
  const rows = tableModel(ix, { slice: 'day', ids: [1, 2], days: ix.days }).rows
  assert.deepEqual(rows.filter(r => r.boost).map(r => [r.label, r.boost]), [[day(3), 20], [day(4), 20]])
})

test('будущие дни действующего буста — «нужно в день» с процентом буста', () => {
  const d = fixture()
  d.boosts = [{ pct: 10, from: day(8), to: day(9) }]
  const ix = indexData(d), plain = indexData(fixture())
  assert.equal(planFor(ix, [1, 2], [day(8)]), planFor(plain, [1, 2], [day(8)]) * 1.1)
  assert.equal(planFor(ix, [1, 2], [day(10)]), planFor(plain, [1, 2], [day(10)]))
})


test('уники в разрезе по креативам — из пар модели (владелец 24.10.2026)', () => {
  const d = fixture()
  d.creative_uniques = [1, 2, 3, 4, 5].flatMap(n => [
    { date: day(n), placement_id: 1, set_no: 1, uniques: 150 },
    { date: day(n), placement_id: 1, set_no: 2, uniques: 100 }])
  d.creative_uniques.push({ date: day(6), placement_id: 1, set_no: 1, uniques: 9999 })   // после среза
  const ix = indexData(d)
  const m = tableModel(ix, { slice: 'creative', ids: [1, 2], days: ix.days })
  assert.ok(m.cols.some(c => c.key === 'uni'), 'колонка «Уники» есть')
  assert.deepEqual(m.rows.map(r => r.uni), [750, 500])
  const x = tableModel(ix, { slice: 'cxp', ids: [1, 2], days: ix.days })
  assert.equal(x.rows.reduce((a, r) => a + r.uni, 0), 1250)
})

test('разрез «по группам» складывает креативы группы и проваливается в её площадки (владелец 24.10.2026)', () => {
  const d = fixture()
  d.creative_days = d.creative_days.map(r => ({ ...r, group: r.set_no === 1 ? 'Аудитория А' : null }))
  d.creative_uniques = [1, 2, 3, 4, 5].map(n => ({ date: day(n), placement_id: 1, set_no: 1, group: 'Аудитория А', uniques: 150 }))
  const ix = indexData(d)
  const m = tableModel(ix, { slice: 'group', ids: [1, 2], days: ix.days })
  assert.deepEqual(m.rows.map(r => [r.label, r.sets, r.fact, r.clk, r.uni]), [['Аудитория А', '№1', 3000, 15, 750]])
  const dr = tableModel(ix, { slice: 'group', ids: [1, 2], days: ix.days, drill: { type: 'group', id: 'Аудитория А' } })
  assert.equal(dr.view, 'placement')
  assert.deepEqual(dr.rows.map(r => [r.label, r.fact]), [['a.ru', 3000]])
})
