// Ответ GET /api/traffic-dashboard/platforms → контракт хендоффа «Площадки × РК» (components/traffic/platforms,
// `sampleData.js` в docs/design_handoff_platforms_report.zip). Только перекладка: вердикты, счётчики и медианы
// считает сервер (backend/app/traffic/platform_report.py), здесь — имена полей и единицы.
//
// Единицы: темп и сутки в контракте — доли (0.97), у сервера — проценты (97.0); расхождение WR — целые проценты.

const ru = (d) => (d ? String(d).slice(0, 10).split('-').reverse().join('.') : '')
const frac = (v) => (v == null ? null : v / 100)

// Коды вердикта сервера → коды макета
const VERDICT = { system_fail: 'fail', system_under: 'sysund', spot: 'spot', ok: 'ok', no_data: 'nodata' }

const keyOf = (x) => x.publisher_id || x.domain

export function toReport(api) {
  if (!api) return null
  const byCampaign = {}
  const rks = (api.rks || []).map(r => {
    const rk = {
      code: r.deal_code, title: r.deal_title || r.deal_code, start: ru(r.date_start), end: ru(r.date_end),
      traffic: r.traffic || '—', deal: r.deal_code, wr_threshold: r.wr_threshold,
    }
    byCampaign[r.campaign_id] = rk
    return rk
  })
  const cells = {}
  for (const c of api.cells || []) (cells[keyOf(c)] = cells[keyOf(c)] || []).push(c)
  const platforms = (api.platforms || []).map(p => ({
    name: p.domain,
    code: p.code || p.domain,
    kind: p.in_dsp,
    verdict: VERDICT[p.verdict?.code] || 'nodata',
    wr_systemic: p.wr_verdict === 'системно',
    stats: {
      rated: p.rated, under_n: p.bad_count, fail_n: p.fail_count,
      median_tempo: frac(p.median_pace), median_day: frac(p.median_day), under_total: p.under || 0,
      wr_measured: p.wr_count, wr_over: p.wr_bad, wr_median: p.median_wr,
      day_with_plan: p.day_rated, day_below: p.day_bad,
    },
    pairs: (cells[keyOf(p)] || []).filter(c => byCampaign[c.campaign_id]).map(c => ({
      rk: byCampaign[c.campaign_id].code,
      share: c.share_pct, plan: c.plan, fact: c.fact, forecast: c.forecast,
      tempo: frac(c.pace_pct), under: c.under || 0,
      plan_day: c.day_plan, fact_day: c.day_fact, day: frac(c.day_pct),
      weborama: c.wr, wr: c.wr_pct == null ? null : Math.round(c.wr_pct),
      need_per_day: c.need_per_day, dsp: c.in_dsp === 'DSP', status: c.status,
    })),
  }))
  return { slice_date: ru(api.as_of), no_fact: !!api.no_fact, rks, platforms }
}

// Фильтр трафика — тем же списком, что у дашборда: «Мои», «Все», «Не распределено», затем учётки трафика (мастера со звёздочкой).
export function trafficOptions(api) {
  return [
    { value: 'mine', label: 'Мои' }, { value: 'all', label: 'Все трафики' }, { value: 'none', label: 'Не распределено' },
    ...(api?.reps || []).filter(r => r.user_id !== api?.my_user_id)
      .map(r => ({ value: String(r.user_id), label: `${r.is_master ? '★ ' : ''}${r.name}` })),
  ]
}
