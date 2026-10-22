// «Статусы продаж» — правила экрана (хендофф docs/статусы продаж.zip, владелец 22.10.2026).
// Колонка сделки = светофор реестра: green — факт, orange — средняя, grey — низкая; не задан — по стадии (Бронь —
// средняя, остальное — низкая). Запущенные (после Брони) — всегда факт и не двигаются; сорванные — вне сумм.
import { MONTHS_FULL } from '@/lib/salesFormat'

export const COLS = ['fact', 'mid', 'low']
export const COL_LABEL = { fact: 'Факт (брони)', mid: 'Средняя вероятность', low: 'Низкая вероятность' }
export const COL_SHORT = { fact: 'Факт (брони)', mid: 'Средняя', low: 'Низкая' }
export const COL_WORD = { fact: 'факт', mid: 'средняя', low: 'низкая' }
export const COL_LIGHT = { fact: 'green', mid: 'orange', low: 'grey' }
export const GROUP = {
  fact: { dot: 'var(--income)', fg: 'var(--income-fg)', bg: 'var(--income-bg)', cell: 'var(--income-bg)', pin: 'var(--income-tint)', border: 'var(--income-border)' },
  mid:  { dot: 'var(--warning)', fg: 'var(--warning-fg)', bg: 'var(--warning-bg)', cell: 'var(--warning-bg)', pin: 'var(--warning-tint)', border: 'var(--warning-border)' },
  low:  { dot: 'var(--danger)', fg: 'var(--danger-fg)', bg: 'var(--danger-bg)', cell: 'var(--danger-bg)', pin: 'var(--danger-tint)', border: 'var(--danger-border)' },
}
export const STAGE_DOT = {
  booking: 'var(--warning)', media_plan: 'var(--text-disabled)', launch_prep: 'var(--income)', launch: 'var(--income)',
  closing: 'var(--income)', closing_fact: 'var(--income)', archive: 'var(--income)',
}

export function colOf(d) {
  if (d.lost) return null
  if (d.locked) return 'fact'
  if (d.light === 'green') return 'fact'
  if (d.light === 'orange') return 'mid'
  if (d.light === 'grey') return 'low'
  return d.stage_key === 'booking' ? 'mid' : 'low'
}

/** «2026-10» → «октябрь». */
export const monthName = (m) => MONTHS_FULL[Number(String(m).slice(5, 7)) - 1] || m

/** Сдвиг месяца ГГГГ-ММ на n. */
export function shiftMonth(m, n) {
  const [y, mo] = m.split('-').map(Number)
  const t = y * 12 + (mo - 1) + n
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`
}

export const window3 = (first) => [first, shiftMonth(first, 1), shiftMonth(first, 2)]

/** Квартал месяца: «2026 Q4». */
export const quarterOf = (m) => `${m.slice(0, 4)} Q${Math.floor((Number(m.slice(5, 7)) - 1) / 3) + 1}`
export const quarterStart = (q) => `${q.slice(0, 4)}-${String((Number(q.slice(-1)) - 1) * 3 + 1).padStart(2, '0')}`

/** Кварталы, которые есть в диапазоне сделок, плюс текущий. */
export function quarterList(range, current) {
  const lo = range?.min || current, hi = range?.max || current
  const out = []
  for (let m = quarterStart(quarterOf(lo < current ? lo : current)); m <= (hi > current ? hi : current); m = shiftMonth(m, 3)) {
    out.push(quarterOf(m))
  }
  return out
}

/** Подпись окна месяцев: «окт — дек 2026», через год — «ноя — янв 2026–27». */
export function windowLabel(w) {
  const cap = (m) => monthName(m).slice(0, 3)
  const a = w[0].slice(0, 4), b = w[2].slice(0, 4)
  return `${cap(w[0])} — ${cap(w[2])} ${a === b ? a : `${a}–${b.slice(2)}`}`
}

/** «2026-10-21» → «21.10». */
export const dm = (s) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : '—')

export const cellSum = (list, m, c) => list.reduce((a, d) => (d.month === m && d.col === c ? a + d.amount : a), 0)

// Встреча: в базе «предложена» / «подтверждена» / пусто; на экране — цикл по клику.
export const MEET_NEXT = { '': 'предложена', 'предложена': 'подтверждена', 'подтверждена': '' }
export function meetLook(v) {
  return {
    bg: v === 'подтверждена' ? 'var(--income)' : v === 'предложена' ? 'linear-gradient(90deg,var(--warning) 50%,transparent 50%)' : 'transparent',
    border: v === 'подтверждена' ? '1.5px solid var(--income)' : v === 'предложена' ? '1.5px solid var(--warning)' : '1.5px dashed var(--text-disabled)',
    word: v || 'нет',
  }
}

/** Ключ заметки: бренд рекламодателя или клиент из таблицы без сделки. */
export const noteKey = (n) => (n.client_name ? `c:${n.client_name.toLowerCase()}` : `a:${n.advertiser_id}|b:${n.brand_id ?? ''}`)
