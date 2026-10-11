// Расчёты страницы «Разбор РК» (владелец 11.10.2026). Без зависимостей и без React — чтобы
// проверяться `node --test lib/rkAnalysis.test.mjs` и считать одинаково на графике, в таблице и в выводах.
// Данные приходят с сервера в мелком зерне (`/api/rk-analysis/{код}`); всё, что зависит от набора
// включённых площадок, считается здесь. Правила — НАШИ, повторены один в один:
//   * план дня: прошедшие дни держат исходный план (план ÷ длина флайта), будущие — остаток ÷ дни
//     (`backend/app/ad/flight.daily_buckets`);
//   * расхождение с Weborama: (наш − WR) ÷ наш × 100, сравниваются только площадки, которые мерят обе
//     системы; шкала по модулю, порог из целей сделки (`stat_sources.comparable / mismatch_pct / mismatch_level`);
//   * расход площадки = её показы (DSP + Adfox) × CPM договора площадки (`cpm_contract`, закуп до НДС) ÷ 1000;
//     CPM дня = расход всех площадок дня ÷ их показы × 1000, за период — среднее дневных (владелец 11.10.2026).
//     Площадка без CPM в расход и CPM не входит — её показы не размывают среднее;
//   * уники — модель SIMB ID (как в отчёте клиенту с поправкой), частота = факт ÷ уники.

export const DAY_MS = 86400000

export const addDays = (iso, n) => new Date(Date.parse(iso + 'T00:00:00Z') + n * DAY_MS).toISOString().slice(0, 10)

export function flightDays(head) {
  const out = []
  if (!head?.date_start || !head?.date_end) return out
  for (let d = head.date_start.slice(0, 10); d <= head.date_end.slice(0, 10); d = addDays(d, 1)) out.push(d)
  return out
}

/** Индекс: площадка → день → {dsp, adf, wr, clk, off, uni}; креативы; события с датой. */
export function indexData(d) {
  const days = flightDays(d.head)
  const asOf = d.head.as_of
  const P = {}
  const pById = {}
  d.placements.forEach(p => { P[p.id] = {}; pById[p.id] = p })
  const cell = (pid, dt) => (P[pid][dt] = P[pid][dt] || { dsp: 0, adf: 0, wr: 0, clk: 0, off: 0, uni: 0 })
  d.stat.forEach(r => {
    if (!P[r.placement_id] || r.date > asOf) return
    const c = cell(r.placement_id, r.date)
    if (r.source === 'dsp') { c.dsp += r.shows; c.clk += r.clicks || 0; c.off += r.offered || 0 }
    else if (r.source === 'adfox') { c.adf += r.shows; c.clk += r.clicks || 0 }
    else if (r.source === 'weborama') c.wr += r.shows
  })
  ;(d.model_uniques || []).forEach(r => { if (P[r.placement_id] && r.date <= asOf) cell(r.placement_id, r.date).uni += r.uniques })
  // Расход креатива — тоже по CPM договора его площадки, а не расход DSP.
  const C = (d.creative_days || []).filter(r => r.date <= asOf && P[r.placement_id]).map(r => {
    const cpm = pById[r.placement_id].cpm
    return { ...r, spend: cpm ? r.shows * cpm / 1000 : 0, priced: !!cpm }
  })
  const ev = (d.events || []).map(e => {
    let date = (e.at || '').slice(0, 10)
    if (days.length && date < days[0]) date = days[0]
    return { ...e, date }
  })
  return { days, asOf, P, C, ev, pById, head: d.head, offerFrom: d.head.offer_from }
}

export const elapsedDays = (ix) => ix.days.filter(x => x <= ix.asOf)

/** Сумма по набору площадок и дней. `wrOwn/wrVer` — СОПОСТАВИМЫЕ: только площадки, у которых за эти дни есть и наш факт, и WR. */
export function sumOf(ix, pids, dates) {
  const t = { dsp: 0, adf: 0, wr: 0, clk: 0, off: 0, offDsp: 0, spend: 0, priced: 0, uni: 0, wrOwn: 0, wrVer: 0, wrPlaces: 0 }
  pids.forEach(id => {
    let own = 0, ver = 0
    const cpm = ix.pById[id]?.cpm
    dates.forEach(dt => {
      const c = ix.P[id]?.[dt]
      if (!c) return
      t.dsp += c.dsp; t.adf += c.adf; t.wr += c.wr; t.clk += c.clk; t.off += c.off; t.uni += c.uni
      if (c.off) t.offDsp += c.dsp
      if (cpm) { t.spend += (c.dsp + c.adf) * cpm / 1000; t.priced += c.dsp + c.adf }
      own += c.dsp + c.adf; ver += c.wr
    })
    if (own > 0 && ver > 0) { t.wrOwn += own; t.wrVer += ver; t.wrPlaces += 1 }
  })
  t.fact = t.dsp + t.adf
  return t
}

/** Расхождение с Weborama, наше правило: знаменатель — наш факт; + — Weborama меньше, − — больше. */
export const wrDiff = (own, wr) => (own && wr != null ? (own - wr) / own * 100 : null)

/** Уровень расхождения: по модулю, до порога ok, до двух — warn, дальше bad. */
export function wrLevel(pct, limit = 10) {
  if (pct == null) return null
  const m = Math.abs(pct)
  return m <= limit ? 'ok' : m <= 2 * limit ? 'warn' : 'bad'
}

/** CPM: по каждому дню — расход всех площадок ÷ их показы × 1000 (только площадки с CPM договора),
 *  за период — среднее дневных (дни без показов не в счёт). */
export function cpmOf(ix, pids, dates) {
  const daily = dates.map(dt => {
    const t = sumOf(ix, pids, [dt])
    return t.priced ? t.spend / t.priced * 1000 : null
  }).filter(v => v != null)
  return daily.length ? daily.reduce((a, b) => a + b, 0) / daily.length : null
}

export const planTotal = (ix, pids) => pids.reduce((a, id) => a + (ix.pById[id]?.plan_show || 0), 0)

/** Итоги шапки по включённым площадкам. Флайт закрыт — прогноз равен факту, «нужно» нет. */
export function kpis(ix, pids) {
  const el = elapsedDays(ix)
  const D = ix.days.length, E = el.length, REST = D - E
  const t = sumOf(ix, pids, el)
  const plan = planTotal(ix, pids)
  const forecast = E ? (REST ? t.fact / E * D : t.fact) : null
  return {
    plan, fact: t.fact, dsp: t.dsp, adf: t.adf, wr: t.wr, clicks: t.clk, spend: t.spend, uni: t.uni,
    forecast, under: forecast == null ? null : Math.max(0, plan - forecast),
    need: REST ? Math.max(0, plan - t.fact) / REST : null,
    avg: E ? t.fact / E : null, days: D, elapsed: E, rest: REST,
    spendForecast: E ? t.spend / E * D : null,
    cpm: cpmOf(ix, pids, el),
    cpmPlan: ix.head.plan_show ? ix.head.plan_budget / ix.head.plan_show * 1000 : null,
    ctr: t.fact ? t.clk / t.fact * 100 : null,   // клики Adfox тоже наши — делим на весь факт
    freq: t.uni ? t.fact / t.uni : null,
    wrPct: wrDiff(t.wrOwn, t.wrPlaces ? t.wrVer : null), wrPlaces: t.wrPlaces,
  }
}

/** План набора площадок на дни: прошедшие — исходный (план ÷ длина), будущие — остаток ÷ дни остатка. */
export function planFor(ix, pids, dates) {
  const plan = planTotal(ix, pids)
  const D = ix.days.length || 1
  const el = elapsedDays(ix)
  const rest = D - el.length
  const factAll = sumOf(ix, pids, el).fact
  const need = rest ? Math.max(0, plan - factAll) / rest : 0
  return dates.reduce((a, dt) => a + (dt <= ix.asOf ? plan / D : need), 0)
}

/** Неделя (пн) для дня. */
export function weekKey(iso) {
  const t = Date.parse(iso + 'T00:00:00Z')
  const dow = (new Date(t).getUTCDay() + 6) % 7
  return new Date(t - dow * DAY_MS).toISOString().slice(0, 10)
}

// ── выводы ─────────────────────────────────────────────────────────────────
// Свой форматтер, а не lib/salesFormat: модуль без зависимостей, чтобы гоняться `node --test` (salesFormat — не ESM).
const nf = v => (v == null || !isFinite(v) ? '—' : Math.round(v).toLocaleString('ru-RU'))
const pf = (v, d = 1) => (v == null || !isFinite(v) ? '—' : v.toFixed(d).replace('.', ',') + ' %')
const dm = s => s.slice(8, 10) + '.' + s.slice(5, 7)
const signed = v => (v < 0 ? '−' : '+') + Math.abs(v).toFixed(1).replace('.', ',') + ' %'

/** Набор автоматических выводов по включённым площадкам. Каждый — {kind, level, text, target}.
 *  Фраза не выводится, если сравнивать нечего (никаких «0 из 0»). */
export function insights(ix, pids) {
  const out = []
  if (!pids.length) return out
  const el = elapsedDays(ix)
  const K = kpis(ix, pids)
  const offDays = ix.offerFrom ? el.filter(x => x >= ix.offerFrom) : []
  const per = pids.map(id => ({ id, p: ix.pById[id], all: sumOf(ix, [id], el), off: sumOf(ix, [id], offDays) }))

  // 1. ёмкость: сеть предлагает в разы больше, чем площадка откручивает
  const cap = per.filter(x => x.off.off > 0 && x.off.dsp > 0).map(x => ({ ...x, k: x.off.off / x.off.dsp }))
    .filter(x => x.k >= 3).sort((a, b) => b.k - a.k)[0]
  if (cap) out.push({ kind: 'ёмкость', level: 'info', target: { type: 'placement', id: cap.id },
    text: `${cap.p.domain}: с ${dm(ix.offerFrom)} предложено ${nf(cap.off.off)}, открутила ${nf(cap.off.dsp)} (${pf(cap.off.dsp / cap.off.off * 100, 0)}) при доле ${pf(cap.p.share * 100)} — ёмкость в ${cap.k.toFixed(1).replace('.', ',')}× больше факта, кандидат на добавку объёма.` })

  // 2. недобор не из-за сети
  if (K.rest && offDays.length) {
    const under = per.map(x => {
      const need = Math.max(0, (x.p.plan_show || 0) - x.all.fact) / K.rest
      return { ...x, need, fact: x.off.dsp / offDays.length, offer: x.off.off / offDays.length }
    }).filter(x => x.offer > 0 && x.fact < x.need * 0.8 && x.offer >= x.need).sort((a, b) => (b.need - b.fact) - (a.need - a.fact))[0]
    if (under) out.push({ kind: 'недобор', level: 'warn', target: { type: 'placement', id: under.id },
      text: `${under.p.domain}: нужно ~${nf(under.need)} в день по плану, факт ~${nf(under.fact)} при предложении ~${nf(under.offer)} — недобор не из-за сети, упор в лимит или креатив.` })
  }

  // 3. событие: самый резкий суточный скачок и что было в тот день
  const daily = el.map(dt => ({ dt, v: sumOf(ix, pids, [dt]).fact }))
  let jump = null
  for (let i = 1; i < daily.length; i++) {
    const a = daily[i - 1].v, b = daily[i].v
    if (a > 0 && Math.abs(b - a) / a >= 0.3 && (!jump || Math.abs(b - a) > Math.abs(jump.b - jump.a))) jump = { i, a, b, dt: daily[i].dt }
  }
  if (jump) {
    const evs = ix.ev.filter(e => e.date === jump.dt && e.kind !== 'tech')
    const tech = ix.ev.filter(e => e.date === jump.dt && e.kind === 'tech').length
    const next = daily[jump.i + 1]
    const why = evs.length ? `совпало с: ${evs.slice(0, 3).map(e => e.text.replace(/^РК \w+: /, '')).join('; ')}` + (tech ? ` и ссылками нацеливания (${tech})` : '')
      : tech ? `в этот день были ссылки нацеливания (${tech})` : 'событий в журнале в этот день нет'
    const tail = next ? (Math.abs(next.v - jump.a) / jump.a <= 0.2 ? ` На следующий день ${nf(next.v)} — всплеск, а не новый уровень.` : ` На следующий день ${nf(next.v)}.`) : ''
    out.push({ kind: 'событие', level: 'info', target: { type: 'day', id: jump.dt },
      text: `${dm(jump.dt)}: факт ${nf(jump.a)} → ${nf(jump.b)}, ${why}.${tail}` })
  }

  // 4. креативы: CTR комплектов и сравнение на общих площадках (только где у обоих ≥ 1000 показов)
  const ps = new Set(pids)
  const sets = {}
  ix.C.forEach(r => {
    if (!ps.has(r.placement_id)) return
    const s = (sets[r.set_no] = sets[r.set_no] || { no: r.set_no, title: r.set_title, shows: 0, clicks: 0, pl: {} })
    s.shows += r.shows; s.clicks += r.clicks
    const q = (s.pl[r.placement_id] = s.pl[r.placement_id] || { shows: 0, clicks: 0 })
    q.shows += r.shows; q.clicks += r.clicks
  })
  const sl = Object.values(sets).filter(s => s.shows > 0).sort((a, b) => a.clicks / a.shows - b.clicks / b.shows)
  if (sl.length >= 2) {
    const lo = sl[0], hi = sl[sl.length - 1]
    const common = Object.keys(lo.pl).filter(id => hi.pl[id] && lo.pl[id].shows >= 1000 && hi.pl[id].shows >= 1000)
    const worse = common.filter(id => lo.pl[id].clicks / lo.pl[id].shows < hi.pl[id].clicks / hi.pl[id].shows).length
    out.push({ kind: 'креативы', level: 'info', target: { type: 'slice', id: 'creative' },
      text: `Комплект №${lo.no} даёт CTR ${pf(lo.clicks / lo.shows * 100, 2)} против ${pf(hi.clicks / hi.shows * 100, 2)} у №${hi.no}`
        + (common.length ? `; на общих площадках №${lo.no} ниже в ${worse} из ${common.length}.` : '.') })
  }

  // 5. не наш код: доля факта и расхождение Weborama с Adfox по ним (наше правило, со знаком словами)
  const ext = per.filter(x => x.p.external && x.all.fact > 0)
  if (ext.length && K.fact) {
    const share = ext.reduce((a, x) => a + x.all.fact, 0) / K.fact * 100
    const diffs = ext.filter(x => x.all.wr > 0).map(x => wrDiff(x.all.fact, x.all.wr))
    let tail = ''
    if (diffs.length) {
      const hi = diffs.every(v => v < 0), lo = diffs.every(v => v > 0)
      const mags = diffs.map(Math.abs), a = Math.min(...mags), b = Math.max(...mags)
      const range = a === b || diffs.length === 1 ? pf(a, 0) : `${a.toFixed(0)}–${pf(b, 0)}`
      tail = hi ? `; Weborama по ним больше Adfox на ${range}` : lo ? `; Weborama по ним меньше Adfox на ${range}` : `; расхождение Weborama с Adfox по ним от ${pf(a, 0)} до ${pf(b, 0)} в обе стороны`
    }
    out.push({ kind: 'не наш код', level: 'info', target: { type: 'preset', id: 'ext' },
      text: `${ext.length} ${ext.length === 1 ? 'площадка' : ext.length < 5 ? 'площадки' : 'площадок'} вне DSP ${ext.length === 1 ? 'даёт' : 'дают'} ${pf(share, 0)} факта${tail}.` })
  }

  // 6. Weborama по РК и худшая площадка за порогом
  const limit = ix.head.wr_limit || 10
  if (K.wrPct != null) {
    const worst = per.filter(x => x.all.fact > 0 && x.all.wr > 0).map(x => ({ ...x, d: wrDiff(x.all.fact, x.all.wr) }))
      .filter(x => wrLevel(x.d, limit) !== 'ok').sort((a, b) => Math.abs(b.d) - Math.abs(a.d))[0]
    const side = K.wrPct < 0 ? 'Weborama больше' : 'Weborama меньше'
    out.push({ kind: 'Weborama', level: wrLevel(K.wrPct, limit) === 'ok' ? 'info' : 'warn', target: { type: 'source', id: 'diff' },
      text: `Расхождение по РК ${signed(K.wrPct)} (${side}, по ${K.wrPlaces} площ., порог ${limit} %)` + (worst ? `; хуже всех ${worst.p.domain} ${signed(worst.d)}.` : '; все площадки в пределах порога.') })
  }

  // 7. деньги
  if (K.spend) out.push({ kind: 'деньги', level: 'info', target: { type: 'metric', id: 'spend' },
    text: `Расход по CPM площадок ${nf(K.spend)} ₽ за ${K.elapsed} дн., средний CPM в день ${nf(K.cpm)} ₽` + (K.rest ? `; при текущем темпе к концу флайта — ${nf(K.spendForecast)} ₽.` : '.') })

  // 8. цели
  const g = ix.head.goals || {}
  const goalNum = v => { const m = String(v || '').replace(',', '.').match(/\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null }
  const parts = []
  if (goalNum(g.ctr) != null && K.ctr != null) parts.push(`CTR ${pf(K.ctr, 2)} при цели ${pf(goalNum(g.ctr), 1)}`)
  if (goalNum(g.freq) != null && K.freq != null) parts.push(`частота ${K.freq.toFixed(1).replace('.', ',')} (уники по модели) при цели ${goalNum(g.freq)}`)
  if (g.cr) parts.push('CR фактом не меряется — конверсий DSP не отдаёт')
  if (parts.length) out.push({ kind: 'цели', level: 'info', target: { type: 'metric', id: 'ctr' }, text: parts.join('; ') + '.' })
  return out
}
