// Чистые расчёты оформления строки РК дашборда v2 (17.11.2026). Пороги НЕ дублируются: тон берётся из боевого `pctTone`
// (владелец 17.11.2026: пороги боевые везде) и только переводится в имя.
import { num, pctTone } from '@/components/traffic/dashboardKit'
import { extCoverTone } from '@/components/salesTableKit'

const BY_COLOR = { 'var(--ok)': 'ok', 'var(--warning-text)': 'warn', 'var(--danger)': 'bad', 'var(--border-inner)': 'none' }

/** ok | warn | bad | none — тон РК от выполнения против флайта; факта нет — none. */
export const rkTone = (r) => (r.fact_shows == null ? 'none' : BY_COLOR[pctTone(r.done_pct, r.pace)] || 'none')

export const TONE_BAR = { ok: 'var(--ok)', warn: 'var(--warning)', bad: 'var(--danger)', none: 'var(--text-disabled)' }
export const TONE_FG = { ok: 'var(--ok-fg)', warn: 'var(--warning-fg)', bad: 'var(--danger-fg)', none: 'var(--text-disabled)' }

/** Десять штрихов «Площадки»: зелёные — крутят в темпе, жёлтые — крутят и отстают, серые — не крутят. */
export function ticksOf(r, n = 10) {
  const total = r.placements || 0
  const on = r.placements_on || 0
  const lag = (r.pips || []).filter(p => p.s === 'run' && p.pct != null && BY_COLOR[pctTone(p.pct, r.pace)] !== 'ok').length
  const onN = total ? Math.round(on / total * n) : 0
  const lagN = total ? Math.min(onN, Math.round(lag / total * n)) : 0
  const colors = Array.from({ length: n }, (_, i) => (i >= onN ? 'var(--border-card)' : i >= onN - lagN ? 'var(--warning)' : 'var(--ok)'))
  return { colors, lag }
}

/** Плашки под названием РК — боевые флаги строки, словами. `danger` — красная. */
export function chipsOf(r, tone) {
  const out = []
  if (!r.plan_show) out.push({ t: 'нет плана', hint: 'У сделки не заведён медиаплан' })
  if (!r.placements) out.push({ t: 'нет площадок', hint: 'К РК не подключена ни одна площадка' })
  else if (!r.placements_on) out.push({ t: 'ни одна не крутит', hint: 'Площадки подключены, но ни одна не запущена' })
  const noWeight = (r.placements || 0) - (r.placements_weighted || 0)
  if (noWeight > 0) out.push({ t: `${noWeight} без веса`, hint: 'Нет индекса в балансировщике — в раскладку не попадут' })
  if (r.plan_show && r.fact_shows == null) out.push({ t: 'нет статистики', hint: 'Коннектор ещё не приносил суточный срез' })
  if (r.under > 0 && r.plan_show) {
    const pct = Math.round(r.under / r.plan_show * 100)
    // NAVY (17.11.2026): сильный недокрут (≥ 50 %, предложение хендоффа) — оранжевый «действуй сейчас», слабый — внимание
    out.push({ t: `недокрут ${pct} %`, hint: `Не откручено ${num(r.under)} показов из плана`, signal: pct >= 50 })
  }
  if (r.wr_mismatch?.level === 'bad') {
    out.push({ t: r.wr_mismatch.reason === 'wr_higher' ? 'WR больше факта' : 'расхождение с WR', hint: r.wr_mismatch.hint, danger: true })
  }
  if (r.volumes?.blocked) out.push({ t: 'объёмы больше плана', hint: r.volumes.message, danger: true })
  return out
}

// Е и С приходят как {state: none|part|all, got, total}, W и D — как {done, need}.
const SYS_STATE = { all: 'ok', part: 'warn', none: 'none', ok: 'ok', wait: 'warn', bad: 'warn', off: 'off' }
const SYS_LOOK = {
  ok: { bg: 'transparent', border: 'var(--ok-border)', fg: 'var(--ok-fg)', word: 'в порядке' },
  warn: { bg: 'var(--warning-tint)', border: 'var(--warning-border)', fg: 'var(--warning-fg)', word: 'есть вопросы' },
  none: { bg: 'transparent', border: 'var(--border-card)', fg: 'var(--text-disabled)', word: 'ещё нет' },
  off: { bg: 'transparent', border: 'var(--border-inner)', fg: 'var(--text-disabled)', word: 'не нужно' },
}
const countText = (x, kind) => {
  if (!x) return ''
  if (kind === 'cover') return x.need ? ` · ${x.done} из ${x.need}` : ' · заводить нечего — все площадки крутят сами'
  return x.total ? ` · ${x.got} из ${x.total} креативов` : ''
}

/** Четыре квадрата Е · W · D · С строки РК. */
export function sysSquares(r) {
  const items = [
    ['Е', 'ЕРИД', r.erid_totals?.state || 'none', r.erid_totals, 'cr'],
    ['W', 'Пиксель Weborama', extCoverTone(r.external_totals?.weborama), r.external_totals?.weborama, 'cover'],
    ['D', 'Заведено в DSP', extCoverTone(r.external_totals?.dsp), r.external_totals?.dsp, 'cover'],
    ['С', 'Скрины запуска', r.screens_totals?.state || 'none', r.screens_totals, 'cr'],
  ]
  return items.map(([l, name, st, x, kind]) => {
    const look = SYS_LOOK[SYS_STATE[st] || 'none']
    return { l, ...look, t: `${name} — ${look.word}${countText(x, kind)}` }
  })
}

// Сортировка списка РК по заголовку колонки (просьба трафиков, 19.11.2026). Клик: первый — по направлению колонки
// (текст — А→Я, даты — раньше→позже, числа — больше→меньше), второй — обратно, третий — снова порядок сервера.
// Пустые значения — всегда в конце, в любом направлении.
const RK_SORT = {
  code: [r => r.deal_code, 'asc'],
  title: [r => r.deal_title, 'asc'],
  product: [r => r.product, 'asc'],
  sites: [r => r.placements, 'desc'],
  status: [r => r.status, 'asc'],
  period: [r => r.date_start, 'asc'],
  plan: [r => r.plan_show, 'desc'],
  fact: [r => r.fact_shows, 'desc'],
  done: [r => r.done_pct, 'desc'],
  forecast: [r => r.forecast, 'desc'],
  under: [r => r.under, 'desc'],
}

export function nextRkSort(cur, key) {
  const first = RK_SORT[key][1]
  if (!cur || cur.key !== key) return { key, dir: first }
  return cur.dir === first ? { key, dir: first === 'asc' ? 'desc' : 'asc' } : null
}

export function sortRk(rows, sort) {
  if (!sort || !RK_SORT[sort.key]) return rows
  const get = RK_SORT[sort.key][0]
  const sign = sort.dir === 'asc' ? 1 : -1
  const empty = v => v == null || v === ''
  return [...rows].sort((a, b) => {
    const va = get(a)
    const vb = get(b)
    if (empty(va) || empty(vb)) return empty(va) - empty(vb)
    const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'ru')
    return c * sign
  })
}
