// Срезы «Разбора РК»: строки графика по времени, модель таблицы в разрезе, вкладки аналитики.
// Чистые функции над индексом из `rkAnalysis.mjs`; проверяются `node --test lib/rkAnalysis.test.mjs`.
import { sumOf, planFor, wrDiff, wrLevel, cpmOf, elapsedDays, weekKey, addDays } from './rkAnalysis.mjs'

export const SLICES = [['day', 'день'], ['week', 'неделя'], ['placement', 'площадка'], ['creative', 'креатив'], ['group', 'группа'], ['cxp', 'креатив × площадка']]
export const METRICS = [['shows', 'показы'], ['clicks', 'клики'], ['ctr', 'CTR'], ['offered', 'предложено'], ['plan', '% плана'], ['spend', 'расход ₽'], ['cpm', 'CPM ₽']]
export const SOURCES = [['our', 'наш факт'], ['wr', 'Weborama'], ['diff', 'расхождение %']]
export const PERIODS = [['all', 'весь флайт'], ['7d', '7 дн.'], ['custom', 'свой отрезок']]
export const COMPARES = [['plan', 'с планом'], ['need', 'с «нужно в день»'], ['week', 'с прошлой неделей'], ['wr', 'с Weborama'], ['onoff', 'вкл / выкл']]

export function periodDays(ix, period, range) {
  if (period === '7d') return elapsedDays(ix).slice(-7)
  if (period === 'custom' && range) return ix.days.filter(x => x >= range[0] && x <= range[1])
  return ix.days
}

/** Значение метрики для суммы `t` по набору площадок `ids` и дней `days`. */
export function metricValue(ix, t, ids, days, metric, source) {
  const fact = source === 'wr' ? t.wr : t.fact
  if (metric === 'shows') return source === 'diff' ? wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null) : fact
  if (metric === 'clicks') return t.clk
  if (metric === 'ctr') return t.fact ? t.clk / t.fact * 100 : null
  if (metric === 'offered') return t.off || null
  if (metric === 'plan') { const p = planFor(ix, ids, days.filter(x => x <= ix.asOf)); return p ? fact / p * 100 : null }
  if (metric === 'spend') return t.spend
  if (metric === 'cpm') return cpmOf(ix, ids, days)
  return null
}

const bucketsOf = (days, slice) => {
  if (slice !== 'week') return days.map(x => ({ key: x, days: [x] }))
  const wk = {}
  days.forEach(x => { (wk[weekKey(x)] = wk[weekKey(x)] || []).push(x) })
  return Object.keys(wk).sort().map(k => ({ key: k, days: wk[k] }))
}

/** Строки графика по времени: факт, план (наше правило), «нужно», неделя раньше, выключенные, уники модели. */
export function timeRows(ix, ids, days, { slice, metric, source, offIds = [] }) {
  const el = new Set(elapsedDays(ix))
  const need = (() => {
    const rest = ix.days.length - el.size
    if (!rest) return 0
    const plan = ids.reduce((a, id) => a + (ix.pById[id]?.plan_show || 0), 0)
    return Math.max(0, plan - sumOf(ix, ids, [...el]).fact) / rest
  })()
  return bucketsOf(days, slice).map(b => {
    const fd = b.days.filter(x => el.has(x))
    const t = sumOf(ix, ids, fd)
    const prevDays = b.days.map(x => addDays(x, -7)).filter(x => el.has(x))
    const prev = prevDays.length ? sumOf(ix, ids, prevDays) : null
    const active = fd.length ? ids.filter(id => fd.some(x => { const c = ix.P[id]?.[x]; return c && c.dsp + c.adf > 0 })).length : null
    return {
      key: b.key, days: b.days, future: !fd.length, t, active,
      value: fd.length ? metricValue(ix, t, ids, fd, metric, source) : null,
      plan: planFor(ix, ids, b.days),
      need: need * b.days.length,
      prev: prev ? metricValue(ix, prev, ids, prevDays, metric, source) : null,
      off: offIds.length && fd.length ? metricValue(ix, sumOf(ix, offIds, fd), offIds, fd, metric, source) : null,
    }
  })
}

// ── таблица ───────────────────────────────────────────────────────────────
const crSum = (ix, f) => {
  const t = { dsp: 0, clk: 0, spend: 0, off: 0, pl: new Set() }
  ix.C.forEach(r => { if (!f(r)) return; t.dsp += r.shows; t.clk += r.clicks; t.spend += r.spend || 0; t.off += r.offered || 0; t.pl.add(r.placement_id) })
  // Уники креатива — модель SIMB ID по паре «креатив × площадка × день» (владелец 24.10.2026)
  t.uni = (ix.CU || []).reduce((a, r) => a + (f(r) ? r.uniques : 0), 0)
  return t
}
const cpmCr = (ix, f) => {   // CPM креативной строки — среднее дневных
  const by = {}
  ix.C.forEach(r => { if (!f(r) || !r.priced) return; const d = (by[r.date] = by[r.date] || [0, 0]); d[0] += r.spend; d[1] += r.shows })
  const v = Object.values(by).filter(d => d[1]).map(d => d[0] / d[1] * 1000)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}
const crRow = (ix, f, extra) => {
  const t = crSum(ix, f)
  return { fact: t.dsp, clk: t.clk, ctr: t.dsp ? t.clk / t.dsp * 100 : null, uni: t.uni, off: t.off || null, spend: t.spend, cpm: cpmCr(ix, f), pl: t.pl.size, ...extra }
}

/** Модель таблицы: колонки (ключ, подпись, вид) и строки для разреза и проваливания. */
export function tableModel(ix, { slice, ids, days, drill }) {
  const el = new Set(elapsedDays(ix))
  const fd = days.filter(x => el.has(x))
  const sD = new Set(fd), sI = new Set(ids)
  const limit = ix.head.wr_limit || 10
  const ext = id => ix.pById[id]?.external
  let view = slice, scopeIds = ids, scopeDays = fd, setNo = null, grp = null
  if (drill?.type === 'placement') { scopeIds = [drill.id]; view = drill.view || 'day' }
  if (drill?.type === 'creative') { setNo = drill.id; view = 'placement' }
  // Группа креативов (владелец 24.10.2026) — проваливается в площадки, как креатив
  if (drill?.type === 'group') { grp = drill.id; view = 'placement' }
  const own = setNo != null ? (r => r.set_no === setNo) : grp != null ? (r => r.group === grp) : null
  if (drill?.type === 'day') { scopeDays = [drill.id]; view = 'placement' }
  const sets = {}
  ix.C.forEach(r => { sets[r.set_no] = r.set_title })
  const placementRow = (id, dd) => {
    const p = ix.pById[id], t = sumOf(ix, [id], dd), pv = planFor(ix, [id], dd)
    const offT = sumOf(ix, [id], dd.filter(x => ix.offerFrom && x >= ix.offerFrom))
    const d = wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null)
    return { id, label: p.domain, status: p.status === 'пауза' ? 'пауза' : ext(id) ? 'вне DSP' : 'DSP', share: p.share * 100,
      plan: pv, fact: t.fact, pct: pv ? t.fact / pv * 100 : null, wr: t.wr, wrd: d, wrLevel: wrLevel(d, limit),
      clk: t.clk, ctr: t.fact ? t.clk / t.fact * 100 : null, off: t.off || null, offPct: offT.off ? offT.dsp / offT.off * 100 : null,
      spend: t.spend, cpm: cpmOf(ix, [id], dd), uni: t.uni }
  }
  let cols, rows
  if (view === 'day' || view === 'week') {
    rows = bucketsOf(scopeDays, view).map(b => {
      const t = sumOf(ix, scopeIds, b.days), pv = planFor(ix, scopeIds, b.days)
      const d = wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null)
      return { id: b.key, label: b.key, days: b.days, dsp: t.dsp, adf: t.adf, fact: t.fact, plan: pv, pct: pv ? t.fact / pv * 100 : null,
        wr: t.wr, wrd: d, wrLevel: wrLevel(d, limit), clk: t.clk, ctr: t.fact ? t.clk / t.fact * 100 : null, uni: t.uni,
        off: t.off || null, spend: t.spend, cpm: cpmOf(ix, scopeIds, b.days),
        boost: view === 'day' ? (ix.boostPct && ix.boostPct[b.key]) || null : null,
        drill: view === 'day' && drill?.type !== 'placement' ? { type: 'day', id: b.key } : null }
    })
    cols = [['label', view === 'day' ? 'День' : 'Неделя', 'date'], ['dsp', 'DSP', 'num'], ['adf', 'Adfox', 'num'], ['fact', 'Факт', 'num'],
      ['plan', 'План', 'num'], ['pct', '% плана', 'pct'], ['wr', 'Weborama', 'num'], ['wrd', 'Δ WR', 'wrd'], ['clk', 'Клики', 'num'],
      ['ctr', 'CTR', 'ctr'], ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
  } else if (view === 'placement') {
    const pids = own ? [...crSum(ix, r => own(r) && sD.has(r.date)).pl].filter(id => sI.has(id)) : scopeIds
    rows = pids.map(id => own
      ? { id, label: ix.pById[id].domain, ...crRow(ix, r => own(r) && r.placement_id === id && sD.has(r.date)) }
      : { ...placementRow(id, scopeDays), drill: drill ? null : { type: 'placement', id, view: 'day' } })
    cols = own
      ? [['label', 'Площадка', 'text'], ['fact', 'Показы DSP', 'num'], ['clk', 'Клики', 'num'], ['ctr', 'CTR', 'ctr'], ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
      : [['label', 'Площадка', 'text'], ['status', 'Код', 'text'], ['share', 'Доля', 'pct1'], ['plan', 'План к дате', 'num'], ['fact', 'Факт', 'num'],
        ['pct', '% плана', 'pct'], ['wr', 'Weborama', 'num'], ['wrd', 'Δ WR', 'wrd'], ['clk', 'Клики', 'num'], ['ctr', 'CTR', 'ctr'],
        ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['offPct', 'Взято', 'pct'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
  } else if (view === 'creative') {
    const only = drill?.type === 'placement' ? new Set([drill.id]) : sI
    rows = Object.keys(sets).map(Number).sort((a, b) => a - b)
      .map(n => ({ id: n, label: `№${n} · ${sets[n]}`, ...crRow(ix, r => r.set_no === n && only.has(r.placement_id) && sD.has(r.date)),
        drill: drill ? null : { type: 'creative', id: n } }))
      .filter(r => r.fact > 0)
    cols = [['label', 'Комплект', 'text'], ['pl', 'Площадок', 'num'], ['fact', 'Показы DSP', 'num'], ['clk', 'Клики', 'num'], ['ctr', 'CTR', 'ctr'],
      ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
  } else if (view === 'group') {
    const only = drill?.type === 'placement' ? new Set([drill.id]) : sI
    const names = [...new Set(ix.C.map(r => r.group).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'))
    rows = names.map(g => {
      const nos = [...new Set(ix.C.filter(r => r.group === g).map(r => r.set_no))].sort((a, b) => a - b)
      return { id: g, label: g, sets: nos.map(n => `№${n}`).join(', '),
        ...crRow(ix, r => r.group === g && only.has(r.placement_id) && sD.has(r.date)),
        drill: drill ? null : { type: 'group', id: g } }
    }).filter(r => r.fact > 0)
    cols = [['label', 'Группа', 'text'], ['sets', 'Креативы', 'text'], ['pl', 'Площадок', 'num'], ['fact', 'Показы DSP', 'num'], ['clk', 'Клики', 'num'],
      ['ctr', 'CTR', 'ctr'], ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
  } else {
    const keys = new Set()
    ix.C.forEach(r => { if (sI.has(r.placement_id) && sD.has(r.date)) keys.add(r.set_no + '|' + r.placement_id) })
    rows = [...keys].map(k => {
      const [n, id] = k.split('|').map(Number)
      return { id: k, set: `№${n}`, label: ix.pById[id].domain, ...crRow(ix, r => r.set_no === n && r.placement_id === id && sD.has(r.date)),
        drill: { type: 'placement', id, view: 'creative' } }
    })
    cols = [['set', 'Комплект', 'text'], ['label', 'Площадка', 'text'], ['fact', 'Показы DSP', 'num'], ['clk', 'Клики', 'num'], ['ctr', 'CTR', 'ctr'],
      ['uni', 'Уники', 'num'], ['off', 'Предложено', 'num'], ['spend', 'Расход', 'rub'], ['cpm', 'CPM', 'rub']]
  }
  // Итог считается из своих сумм, а не складывает проценты строк.
  const tot = {}
  ;['dsp', 'adf', 'fact', 'plan', 'wr', 'clk', 'off', 'spend', 'uni'].forEach(k => { tot[k] = rows.reduce((a, r) => a + (r[k] || 0), 0) })
  tot.pct = tot.plan ? tot.fact / tot.plan * 100 : null
  const allT = sumOf(ix, scopeIds, scopeDays)
  tot.wrd = wrDiff(allT.wrOwn, allT.wrPlaces ? allT.wrVer : null)
  tot.wrLevel = wrLevel(tot.wrd, limit)
  tot.ctr = tot.fact ? tot.clk / tot.fact * 100 : null
  tot.cpm = view === 'day' || view === 'week' || (view === 'placement' && setNo == null) ? cpmOf(ix, scopeIds, scopeDays)
    : cpmCr(ix, r => sI.has(r.placement_id) && sD.has(r.date) && (setNo == null || r.set_no === setNo))
  return { view, cols: cols.map(([key, label, kind]) => ({ key, label, kind })), rows, tot }
}

// ── аналитика ─────────────────────────────────────────────────────────────
export const DOW = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
const dowOf = x => (new Date(Date.parse(x + 'T00:00:00Z')).getUTCDay() + 6) % 7

/** Будни/выходные: средний факт в день недели по площадке и по РК. */
export function dowTable(ix, ids) {
  const el = elapsedDays(ix)
  const rows = ids.map(id => {
    const by = DOW.map(() => ({ s: 0, n: 0 }))
    el.forEach(x => { const c = ix.P[id]?.[x]; if (!c || c.dsp + c.adf === 0) return; const b = by[dowOf(x)]; b.s += c.dsp + c.adf; b.n++ })
    const avgs = by.map(b => (b.n ? b.s / b.n : null))
    const base = avgs.filter(v => v != null)
    const mean = base.length ? base.reduce((a, v) => a + v, 0) / base.length : 0
    const we = [avgs[5], avgs[6]].filter(v => v != null), wd = avgs.slice(0, 5).filter(v => v != null)
    const weK = we.length && wd.length ? (we.reduce((a, v) => a + v, 0) / we.length) / (wd.reduce((a, v) => a + v, 0) / wd.length) - 1 : null
    return { id, label: ix.pById[id].domain, weK, cells: avgs.map(v => ({ v, k: v != null && mean ? v / mean - 1 : null })) }
  }).sort((a, b) => (a.weK == null ? 1 : b.weK == null ? -1 : a.weK - b.weK))
  const head = DOW.map((_, i) => { const xs = el.filter(x => dowOf(x) === i); return xs.length ? sumOf(ix, ids, xs).fact / xs.length : null })
  const known = head.filter(v => v != null)
  const mean = known.length ? known.reduce((a, v) => a + v, 0) / known.length : 0
  const wd = head.slice(0, 5).filter(v => v != null), we = head.slice(5).filter(v => v != null)
  const weTot = wd.length && we.length ? (we.reduce((a, v) => a + v, 0) / we.length) / (wd.reduce((a, v) => a + v, 0) / wd.length) - 1 : null
  return { rows, head: head.map(v => ({ v, k: v != null && mean ? v / mean - 1 : null })), weTot }
}

/** Δ Weborama по дням (наше правило, только площадки, мерившие обе системы) и первый день выхода за порог. */
export function wrByDay(ix, ids) {
  const el = elapsedDays(ix)
  const limit = ix.head.wr_limit || 10
  const days = el.map(x => { const t = sumOf(ix, ids, [x]); const v = wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null); return { x, v, level: wrLevel(v, limit) } })
  const breaks = ids.map(id => {
    let first = null, cnt = 0
    el.forEach(x => {
      const c = ix.P[id]?.[x]
      if (!c || !c.wr || c.dsp + c.adf < 300) return
      const v = wrDiff(c.dsp + c.adf, c.wr)
      if (wrLevel(v, limit) !== 'ok') { cnt++; if (!first) first = { x, v } }
    })
    if (!first) return null
    const t = sumOf(ix, [id], el)
    return { id, label: ix.pById[id].domain, since: first.x, first: first.v, cnt, tot: wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null) }
  }).filter(Boolean).sort((a, b) => b.cnt - a.cnt)
  return { days, breaks, limit }
}

/** Предложено, но не взято: (предложено − DSP) ÷ предложено, площадка × день, с первого дня `offered`. */
export function gapTable(ix, ids) {
  const days = elapsedDays(ix).filter(x => ix.offerFrom && x >= ix.offerFrom)
  const rows = ids.filter(id => !ix.pById[id].external).map(id => {
    let off = 0, got = 0
    const cells = days.map(x => { const c = ix.P[id]?.[x] || {}; const o = c.off || 0, g = c.dsp || 0; off += o; got += g; return { x, off: o, got: g, k: o ? Math.max(0, o - g) / o : null } })
    return { id, label: ix.pById[id].domain, cells, left: Math.max(0, off - got), k: off ? (off - got) / off : null }
  }).filter(r => r.k != null).sort((a, b) => b.k - a.k)
  return { days, rows }
}

/** Прошлый флайт по номеру дня: тот же набор доменов, те же первые N дней. */
export function prevCompare(ix, ids, prev) {
  if (!prev?.stat?.length) return null
  const el = elapsedDays(ix)
  const N = el.length
  const doms = new Set(ids.map(id => ix.pById[id].domain))
  const nowByDay = el.map(x => sumOf(ix, ids, [x]))
  const was = Array.from({ length: N }, () => ({ fact: 0, clk: 0, wr: 0 }))
  prev.stat.forEach(r => {
    if (!doms.has(r.domain) || r.day_no < 1 || r.day_no > N) return
    const w = was[r.day_no - 1]
    if (r.source === 'own') { w.fact += r.shows; w.clk += r.clicks } else w.wr += r.shows
  })
  const nowF = nowByDay.reduce((a, t) => a + t.fact, 0), wasF = was.reduce((a, w) => a + w.fact, 0)
  const nowC = nowByDay.reduce((a, t) => a + t.clk, 0), wasC = was.reduce((a, w) => a + w.clk, 0)
  const plan = ids.reduce((a, id) => a + (ix.pById[id].plan_show || 0), 0)
  const nowPct = plan ? nowF / (plan / ix.days.length * N) * 100 : null
  const wasPct = prev.plan_show && prev.length ? wasF / (prev.plan_show / prev.length * N) * 100 : null
  return {
    days: N, now: nowByDay.map(t => t.fact), was: was.map(w => w.fact),
    rows: [
      { label: 'Факт за первые ' + N + ' дн.', now: nowF, was: wasF, d: wasF ? (nowF / wasF - 1) * 100 : null, kind: 'num' },
      { label: '% плана к дате', now: nowPct, was: wasPct, d: nowPct != null && wasPct != null ? nowPct - wasPct : null, kind: 'pp' },
      { label: 'Темп, в день', now: nowF / (N || 1), was: wasF / (N || 1), d: wasF ? (nowF / wasF - 1) * 100 : null, kind: 'num' },
      { label: 'CTR', now: nowF ? nowC / nowF * 100 : null, was: wasF ? wasC / wasF * 100 : null,
        d: nowF && wasF && wasC ? (nowC / nowF) / (wasC / wasF) * 100 - 100 : null, kind: 'ctr' },
    ],
  }
}
