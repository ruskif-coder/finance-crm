/**
 * Стена дней v2 — расчёт без вёрстки (хендофф «расхлоп v2», README 5.2).
 *
 * Состояние клетки берётся из `cellState` боевого кита: пороги дня (0,95 / 0,8 от нужного темпа)
 * одни на весь экран — решение владельца «везде боевые пороги». Здесь только раскладка.
 *
 * Столбец — ДЕНЬ ФЛАЙТА, а не дата календаря (владелец 17.11.2026, как на бою): у каждой РК её дни подряд с первого,
 * без общей оси дат. Иначе одна РК с декабрьским флайтом растягивала стену на два месяца. Столбцов — по самому
 * длинному флайту; у короткого хвост пустой. Итог «по дням» — по номеру дня флайта.
 */
import { cellState } from '../dashboardKit'
import { shortName } from '@/lib/dealTitle'

export const WALL_SHOWN = 15
// Отставание от флайта, п.п. — тон подписи (макет): хуже −8 — красным, хуже −4 — жёлтым.
const LAG_BAD = -8
const LAG_WARN = -4

export const STATE_BG = {
  ok: 'var(--ok)', warn: 'var(--warning)', bad: 'var(--danger)',
  none: 'var(--border-card)', future: 'transparent',
}
export const STATE_BORDER = { ...STATE_BG, future: 'var(--border-inner)' }

export const WALL_LEGEND_V2 = [
  ['норма', 'ok'], ['просадка', 'warn'], ['провал', 'bad'], ['нет данных', 'none'], ['впереди', 'future'],
]

const comma1 = (v) => Math.abs(v).toFixed(1).replace('.', ',')
export const pctText = (v) => (v == null ? '—' : `${comma1(v)} %`)

/** «Рекламодатель · бренд»: рекламодатель — первая часть имени сделки (`lib/dealTitle`), повтор схлопывается. */
const nameOf = (row, item) => {
  const adv = shortName(row?.deal_title)
  const brand = (row?.brand || '').trim()
  const parts = [adv, brand].filter(Boolean)
  const uniq = parts.filter((p, i) => parts.indexOf(p) === i)
  return uniq.length ? uniq.join(' · ') : (item.product || '')
}

const lagOf = (fact, pace) => {
  if (fact == null || pace == null) return { text: '—', fg: 'var(--text-faint)', value: null }
  const d = fact - pace * 100
  const fg = d < LAG_BAD ? 'var(--danger-fg)' : d < LAG_WARN ? 'var(--warning-fg)' : 'var(--text-muted)'
  return { text: `${d < 0 ? '−' : '+'}${comma1(d)} п.п.`, fg, value: d }
}

/** Провал среди трёх последних прошедших дней С ФАКТОМ. */
const recentBad = (cells) => cells
  .filter(c => !c.ahead && c.shows != null)
  .slice(-3)
  .some(c => cellState(c) === 'bad')

/**
 * Модель стены: строки, сетка дней, итог по дням.
 * `wall` — `data.wall` дашборда; `rows` — `data.rows` (для имени и доли флайта, по id).
 */
export function buildWall(wall, rows) {
  const items = wall || []
  const byId = Object.fromEntries((rows || []).map(r => [r.id, r]))
  const len = Math.max(0, ...items.map(w => w.cells.length))
  const dates = Array.from({ length: len }, (_, i) => String(i + 1))   // номера дней флайта — подписи и ключи столбцов

  const all = items.map(w => {
    const row = byId[w.id]
    const slots = dates.map((_, i) => (w.cells[i] ? { ...w.cells[i], state: cellState(w.cells[i]) } : null))
    const n = (s) => w.cells.filter(c => cellState(c) === s).length
    const lag = lagOf(w.done_pct, row?.pace)
    return {
      id: w.id, code: w.deal_code, product: w.product, name: nameOf(row, w),
      fact: w.done_pct, pace: row?.pace ?? null, lag, slots, recent: recentBad(w.cells),
      counts: { bad: n('bad'), warn: n('warn'), ok: n('ok') },
    }
  })

  const per = dates.map((_, i) => {
    const inFlight = all.filter(r => r.slots[i] && r.slots[i].state !== 'future')
    return {
      bad: inFlight.filter(r => r.slots[i].state === 'bad').length,
      warn: inFlight.filter(r => r.slots[i].state === 'warn').length,
      of: inFlight.length,
      future: !inFlight.length,
    }
  })
  const max = Math.max(1, ...per.map(x => x.bad + x.warn))
  const worstIdx = per.reduce((m, x, i) => (x.bad + x.warn > (m < 0 ? 0 : per[m].bad + per[m].warn) ? i : m), -1)
  const worstRk = [...all].filter(r => r.fact != null).sort((a, b) => a.fact - b.fact)[0] || null

  return {
    all, dates, per, max, todayIdx: -1, worstIdx, worstRk,
    worstDay: worstIdx < 0 ? null : dayLabel(worstIdx),
    worstDayBelow: worstIdx < 0 ? 0 : per[worstIdx].bad + per[worstIdx].warn,
    recentCount: all.filter(r => r.recent).length,
    totalRows: (rows || []).length,
  }
}

/** «12-й день флайта» — подпись столбца в подсказках и сводке. */
const dayLabel = (i) => `${i + 1}-й день флайта`

/** Порядок и фильтр — до обрезки до 15. */
export function visibleRows(model, { sort, onlyRecent, expanded }) {
  let list = onlyRecent ? model.all.filter(r => r.recent) : model.all
  list = sort === 'code'
    ? [...list].sort((a, b) => String(a.code).localeCompare(String(b.code), 'ru'))
    : [...list].sort((a, b) => (a.fact == null) - (b.fact == null) || (a.fact ?? 0) - (b.fact ?? 0))
  return { rows: expanded ? list : list.slice(0, WALL_SHOWN), full: list.length }
}

/** Подпись оси: номер дня флайта — первый, каждый пятый и последний. Общего «сегодня» нет: у каждой РК своё. */
export function axisLabels(model) {
  const n = model.dates.length
  return model.dates.map((d, i) => {
    const tail = i === n - 1 && (n - 1) % 5 >= 3
    return { t: i % 5 === 0 || tail ? d : '', today: false }
  })
}

export const dayTitle = (model, i) => {
  const x = model.per[i]
  const day = dayLabel(i)
  return x.future ? `${day} · впереди у всех` : `${day} · провал ${x.bad}, просадка ${x.warn} из ${x.of} РК`
}

export const dayHint = (model, i) => {
  if (i < 0 || !model.per[i] || model.per[i].future) return 'наведите на день'
  const x = model.per[i]
  return `${i + 1}-й день · ${x.bad + x.warn} из ${x.of}`
}
