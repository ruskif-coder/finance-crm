/**
 * Аналитика РК в расхлопе дашборда трафика v2 (хендофф design_handoff_traffic_expand_v2, раздел 9) — чистые расчёты.
 *
 * Числа приходят посчитанными с сервера, здесь только раскладка для экрана:
 *   · недокрут площадки — `p.under` с бэкенда (от ПРОГНОЗА, `app/ad/flight.py`), а не формула макета «к календарю»
 *     (решение владельца 17.11.2026); итог блока «Откуда недокрут» — их сумма;
 *   · уровень расхождения с Weborama — `p.wr_mismatch.level` с бэкенда (ok/warn/bad по пределу из цели сделки,
 *     по умолчанию 10 %, warn — до двух пределов); пороги макета 5/10 % не вводим.
 *
 * Функции не меняют вход.
 */
import { dm, grp } from '@/lib/salesFormat'

// Группа площадки — ОДНА на экран, из модели таблицы площадок (`lib/sitesModel.mjs`); здесь только оформление долей.
import { groupOf } from '@/lib/sitesModel.mjs'

export const GROUPS = [
  { key: 'act', label: 'Требуют действия', bg: 'var(--warning)' },
  { key: 'lag', label: 'Отстают', bg: 'var(--warning-border)' },
  { key: 'ok', label: 'В темпе', bg: 'var(--ok-border)' },
  { key: 'over', label: 'План выбран', bg: 'var(--accent-border)' },
]

export const siteName = (p) => p.domain || p.publisher || `#${p.id}`

const comma = (v, d) => v.toFixed(d).replace('.', ',')

/** «−38,4 %» / «+6,2 %»: знак со стороны сервера (плюс — Weborama насчитала меньше нашего). */
export const signedPct = (pct) => (pct == null ? '—'
  : `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${comma(Math.abs(pct), 1)} %`)

export const ctrText = (v) => (v == null ? '—' : `${comma(v, 2)} %`)

/**
 * «Откуда недокрут»: итог, доли групп и топ-5 площадок. `rkUnder` — недокрут РК из строки реестра:
 * сумма по площадкам обязана с ним сходиться, и когда не сходится, экран говорит об этом в подсказке.
 */
export function underSource(placements, rkUnder) {
  const rows = (placements || []).filter(p => (p.under || 0) > 0)
  const total = rows.reduce((s, p) => s + p.under, 0)
  const mix = GROUPS.map(g => {
    const u = rows.filter(p => groupOf(p) === g.key).reduce((s, p) => s + p.under, 0)
    return { key: g.key, bg: g.bg, w: u, title: `${g.label} · −${grp(u)}`,
      label: `${g.label.toLowerCase()} ${total ? Math.round(u / total * 100) : 0} %`, amount: u }
  }).filter(m => m.amount > 0)
  const sorted = [...rows].sort((a, b) => b.under - a.under).slice(0, 5)
  const top = sorted.map(p => ({ id: p.id, name: siteName(p), amount: p.under,
    w: `${Math.max(2, Math.round(p.under / sorted[0].under * 100))}%`,
    pct: total ? `${Math.round(p.under / total * 100)} %` : '', bg: 'var(--warning)' }))
  const diverges = rkUnder != null && Math.abs(Math.round(total) - Math.round(rkUnder)) > 1
  return { total, mix, top, diverges }
}

const LEVEL_BG = { bad: 'var(--warning)', warn: 'var(--warning-border)', ok: 'var(--ok-border)' }
const LEVEL_TOP = { bad: 'var(--warning)', warn: 'var(--warning-border)', ok: 'var(--text-faint)' }

/** «Расхождение с Weborama»: площадки по уровню сервера и топ-5 по модулю расхождения. */
export function wrSource(placements) {
  const rows = (placements || []).filter(p => p.wr_mismatch && p.wr_mismatch.pct != null)
  const lim = rows.find(p => p.wr_mismatch.limit)?.wr_mismatch.limit || 10
  const g = (n) => String(n).replace('.', ',')
  const mix = [['bad', `больше ${g(2 * lim)} %`], ['warn', `${g(lim)}–${g(2 * lim)} %`], ['ok', `до ${g(lim)} %`]]
    .map(([lvl, label]) => {
      const n = rows.filter(p => p.wr_mismatch.level === lvl).length
      return { key: lvl, bg: LEVEL_BG[lvl], w: n, label: `${label} · ${n} пл.`, title: `${label} — площадок: ${n}`, amount: n }
    }).filter(m => m.amount > 0)
  const sorted = [...rows].sort((a, b) => Math.abs(b.wr_mismatch.pct) - Math.abs(a.wr_mismatch.pct)).slice(0, 5)
  const max = sorted.length ? Math.abs(sorted[0].wr_mismatch.pct) || 1 : 1
  const top = sorted.map(p => ({ id: p.id, name: siteName(p), pct: p.wr_mismatch.pct,
    w: `${Math.max(2, Math.round(Math.abs(p.wr_mismatch.pct) / max * 100))}%`, bg: LEVEL_TOP[p.wr_mismatch.level] || 'var(--text-faint)',
    title: [p.wr_mismatch.hint, `факт ${grp(p.fact_shows)} · WR ${grp(p.wr)}`].filter(Boolean).join(' · ') }))
  return { mix, top, measured: rows.length, limit: lim }
}

/**
 * Итог текущей недели — столбец, в который попадает день среза (`as_of`), а не календарное сегодня: факт приходит
 * за вчера (владелец 02.10.2026). WR и расхождения у недели нет: сервер сверяет за день и за период.
 */
export function weekTotals(st, fallbackDay) {
  const day = String(st.totals?.as_of || fallbackDay)
  const b = (st.buckets || []).find(x => String(x.date_from) <= day && day <= String(x.date_to))
  if (!b) return { shows: 0, clicks: 0, ctr: null }
  return { shows: b.shows, clicks: b.clicks, ctr: b.shows ? Math.round(b.clicks / b.shows * 10000) / 100 : null }
}

/** Индекс столбца с календарным «сегодня»; −1 — сегодня вне окна графика. */
export const todayIndex = (buckets, today) =>
  (buckets || []).findIndex(b => String(b.date_from) <= today && today <= String(b.date_to))

/** Подписи оси: шаг по длине окна, у «сегодня» соседние подписи убираются, чтобы не слиплись. */
export function axisTicks(buckets, ti) {
  const n = buckets.length
  const every = n > 20 ? 5 : n > 10 ? 3 : 1
  const near = Math.max(1, Math.ceil(every / 2))
  const out = []
  buckets.forEach((b, i) => {
    if (i === ti) out.push({ i, label: `сегодня ${dm(b.date_from)}`, today: true })
    else if ((i % every === 0 || i === n - 1) && (ti < 0 || Math.abs(i - ti) >= near)) out.push({ i, label: dm(b.date_from) })
  })
  return out.map(t => ({ ...t, n }))
}
