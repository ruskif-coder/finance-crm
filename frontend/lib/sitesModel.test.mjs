// node lib/sitesModel.test.mjs — раскладка таблицы площадок в расхлопе РК (входит в `npm run test-rk`).
import assert from 'node:assert/strict'
import { creativeResults, creativeSystemsOf, ctrTone, goalCtr, groupOf, groupRows, groupTotals, layout, nextSort, noShows,
  sortRows, systemsOf } from './sitesModel.mjs'

const EXT = { 'есть': 'ok', 'крутится': 'ok', 'заведён': 'wait', 'нет': 'none', '—': 'off' }
const pace = (status, day = '2026-11-13', shows = 100) => ({ status, day, shows, chronic: false })

const P = [
  { id: 1, domain: 'a.ru', status: 'запущен', ext_mode: 'external', plan_show: 1000, fact_shows: 300, fact_clicks: 3, under: 200, share: 0.1, pace: pace('в темпе') },
  { id: 2, domain: 'b.ru', status: 'у площадки', plan_show: null, fact_shows: null, under: null, share: 0 },
  { id: 3, domain: 'c.ru', status: 'запущен', plan_show: 1000, fact_shows: 1000, fact_clicks: 10, under: 0, share: 0.2, pace: pace('перебор') },
  { id: 4, domain: 'd.ru', status: 'запущен', plan_show: 2000, fact_shows: 500, fact_clicks: 4, under: 700, share: 0.3, pace: pace('мало трафика'),
    wr_mismatch: { pct: -12.4, level: 'bad', limit: 10 } },
  { id: 5, domain: 'e.ru', status: 'запущен', plan_show: 2000, fact_shows: 600, fact_clicks: 6, under: 900, share: 0.3, pace: pace('недобор', '2026-11-12'),
    wr_mismatch: { pct: 6, level: 'warn', limit: 10 } },
  { id: 6, domain: 'f.ru', status: 'пауза', plan_show: 500, fact_shows: 100, fact_clicks: 1, under: 50, share: 0.1, pace: pace('в темпе', '2026-11-13', 0) },
]

// группы: чужой код и «у площадки» — сверху; выбравшая план — «план выбран»; темп ниже нужного — «отстают»
assert.deepEqual(P.map(groupOf), ['act', 'act', 'over', 'lag', 'lag', 'ok'])
const g = groupRows(P)
assert.deepEqual(g.map(x => x.key), ['act', 'lag', 'ok', 'over'])
assert.deepEqual(g[1].rows.map(r => r.id), [5, 4], 'внутри группы — по недокруту от большего')
assert.deepEqual(g[0].rows.map(r => r.id), [1, 2], 'недокрут null — в конец')
assert.deepEqual(groupRows(P.filter(p => p.id !== 3)).map(x => x.key), ['act', 'lag', 'ok'], 'пустая группа не показывается')

// итоги группы
const t = groupTotals(g[1].rows)
assert.equal(t.plan, 4000); assert.equal(t.fact, 1100); assert.equal(t.clicks, 10)
assert.equal(t.ctr, 0.91); assert.equal(t.under, 1600); assert.equal(t.wrBad, 1); assert.equal(t.wrLimit, 10)
assert.ok(Math.abs(t.share - 0.6) < 1e-9)

// сортировка: по умолчанию большее/худшее первым, повтор — переворот, пустые всегда в конце
assert.deepEqual(sortRows(P, 'under', 'desc').map(r => r.id), [5, 4, 1, 6, 3, 2])
assert.deepEqual(sortRows(P, 'under', 'asc').map(r => r.id), [3, 6, 1, 4, 5, 2])
assert.deepEqual(sortRows(P, 'wr', 'desc').map(r => r.id).slice(0, 2), [4, 5])
assert.deepEqual(sortRows(P, 'pace', 'desc').map(r => r.id), [4, 5, 1, 6, 3, 2])
assert.deepEqual(sortRows(P, 'status', 'desc').map(r => r.id)[0], 2)
assert.deepEqual(sortRows(P, 'name', 'desc').map(r => r.id), [1, 2, 3, 4, 5, 6])
assert.deepEqual(nextSort({ key: 'attn', dir: 'desc' }, 'ctr'), { key: 'ctr', dir: 'desc' })
assert.deepEqual(nextSort({ key: 'ctr', dir: 'desc' }, 'ctr'), { key: 'ctr', dir: 'asc' })
assert.deepEqual(nextSort({ key: 'ctr', dir: 'asc' }, 'attn'), { key: 'attn', dir: 'desc' })
assert.equal(layout(P, { key: 'fact', dir: 'desc' }, EXT).length, 1, 'по столбцу — без групп')
assert.equal(layout(P, { key: 'attn', dir: 'desc' }, EXT).length, 4)

// цель CTR и тон
assert.equal(goalCtr({ ctr: '0,8' }), 0.8)
assert.equal(goalCtr({ ctr: 'от 1.2 %' }), 1.2)
assert.equal(goalCtr({ freq: '5' }), null)
assert.equal(ctrTone(0.8, 0.8), 'good'); assert.equal(ctrTone(0.59, 0.8), 'low')
assert.equal(ctrTone(0.7, 0.8), 'mid'); assert.equal(ctrTone(0.3, null), 'mid'); assert.equal(ctrTone(null, 0.8), 'none')

// системы
const sys = systemsOf({ erid: { state: 'all', got: 1, total: 1 }, screens: { state: 'all', got: 1, total: 1 },
  external: { weborama: { state: 'есть' }, dsp: { state: '—', why: 'внешняя DSP' } } }, EXT)
assert.equal(sys.label, 'нет D'); assert.deepEqual(sys.marks.map(m => m.tone), ['ok', 'ok', 'off', 'ok'])
assert.equal(systemsOf({}, EXT).label, '—')

// без показов за последние сутки: e.ru (последний день раньше), f.ru на паузе — не в счёт
assert.deepEqual(noShows(P), { day: '2026-11-13', ids: [5] })
assert.equal(noShows([{ id: 1, status: 'запущен' }]), null)

// по креативам: CTR = клики / показы по всем парам, «лучший» — только когда креативов с показами больше одного
const cr = creativeResults([
  { key: 1, places: [{ fact: 1000, clicks: 5 }, { fact: 1000, clicks: 15 }] },
  { key: 2, places: [{ fact: 500, clicks: 2 }] },
  { key: 3, places: [{ fact: null, clicks: null }] },
])
assert.deepEqual(cr.map(c => c.ctr), [1, 0.4, null])
assert.deepEqual(cr.map(c => c.best), [true, false, false])
assert.equal(creativeResults([{ key: 1, places: [{ fact: 10, clicks: 1 }] }])[0].best, false)

console.log('sitesModel: ok')

// Системы креатива (владелец 17.11.2026: «в расхлопе по креативу аналогичный статус, только к креативу»)
{
  const place = { ext_mode: 'dsp', external: { weborama: { state: 'есть' }, dsp: { state: 'крутится' } } }
  const s1 = creativeSystemsOf({ erid: 'X1', ms_creative_xxhash: 'H', screens_done_at: '2026-11-10' }, place, EXT)
  assert.deepEqual(s1.marks.map(m => [m.l, m.tone]), [['Е', 'ok'], ['W', 'ok'], ['D', 'ok'], ['С', 'ok']])
  assert.equal(s1.label, 'ок')
  // поломка: D креатива берётся от площадки — площадка в DSP, а сам креатив не заведён, и «нет D» не видно
  const s2 = creativeSystemsOf({ erid: null, ms_creative_xxhash: null, screens_done_at: null }, place, EXT)
  assert.equal(s2.label, 'нет Е D С')
  // внешняя площадка: D — как у площадки («—», вне нашей DSP), а не «нет» по пустому хешу
  const s3 = creativeSystemsOf({ erid: 'X', ms_creative_xxhash: null, screens_done_at: null },
    { ext_mode: 'external', external: { weborama: { state: 'нет' }, dsp: { state: '—', why: 'внешняя DSP' } } }, EXT)
  assert.equal(s3.marks[2].tone, 'off')
  assert.match(s3.marks[1].title, /площадки/)
}
