// События и сроки «Моих сделок» (модалка «События и сроки», хендофф design_handoff_account_dashboard_v5, экран 14).
// Даты — из строки очереди, своих правил нет:
//   · Старт РК — `period_from` (песочница, бронь, сборка);
//   · Конец периода — `period_to` у сделки в размещении;
//   · Срок по норме — бронь подтверждают за 15 дней до старта; итоговая сверка — 3 дня на стадии (как «норма 3» в строке).
// Окно — «просрочено» (только сроки по норме: срок прошёл, дело не закрыто) и сегодня + DAYS_AHEAD дней.
// «Документы» и «Оплата» сюда не входят: у пакетов дат выставления и оплаты в данных нет (README хендоффа, допущение 2).

export const DAYS_AHEAD = 10
export const BOOKING_DAYS = 15
export const RECON_NORM = 3
export const TYPES = [
  { key: 'start', label: 'Старт РК' },
  { key: 'end', label: 'Конец периода' },
  { key: 'norm', label: 'Срок по норме' },
]

const iso = (d) => d.toISOString().slice(0, 10)
const shift = (s, n) => { const d = new Date(`${s}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return iso(d) }

function eventsOf(r, today) {
  const out = []
  if (r.slot === 'booking' && r.period_from) {
    out.push({ type: 'norm', date: shift(r.period_from, -BOOKING_DAYS), what: 'подтвердить бронь', norm: `норма: за ${BOOKING_DAYS} дн. до старта` })
  }
  if (r.slot === 'recon' && r.stage_days != null) {
    out.push({ type: 'norm', date: shift(today, RECON_NORM - r.stage_days), what: 'закрыть итоговую сверку', norm: `норма ${RECON_NORM} дн. · на стадии ${r.stage_days} дн.` })
  }
  if (['mp_prep', 'mp_sent', 'booking', 'prep'].includes(r.slot) && r.period_from) {
    out.push({ type: 'start', date: r.period_from, what: 'старт РК', norm: r.period_to ? `до ${r.period_to.slice(8, 10)}.${r.period_to.slice(5, 7)}` : '' })
  }
  if (r.slot === 'live' && r.period_to) {
    out.push({ type: 'end', date: r.period_to, what: 'конец периода', norm: 'РК завершает трафик или аккаунт' })
  }
  return out
}

/** [{type, date, overdue, what, norm, row}] по дате; вне окна — нет. */
export function buildEvents(rows, today) {
  const last = shift(today, DAYS_AHEAD)
  return rows.flatMap(r => eventsOf(r, today).map(e => ({ ...e, row: r, overdue: e.date < today })))
    .filter(e => (e.overdue ? e.type === 'norm' : e.date <= last))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
}

/** Дни ленты: сегодня и DAYS_AHEAD вперёд. */
export function daysOf(today) {
  return Array.from({ length: DAYS_AHEAD + 1 }, (_, i) => shift(today, i))
}
