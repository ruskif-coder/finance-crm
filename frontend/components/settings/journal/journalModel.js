// Логика ленты журнала (макет design_handoff_journal, 16.11.2026) — без React.
//
// Сворачивание повторов: подряд идущие записи ОДНОГО человека с ОДНИМ действием за ОДИН день, от трёх штук, — одна
// строка «× N». Считается по всему подгруженному (а не по странице), поэтому на стыке страниц группа не рвётся:
// «Показать ещё» дописывает записи и группы пересчитываются заново.
import { calendarDate, fmtDateOfMoment, fmtTime, todayMsk } from '@/lib/dates'

export const COLLAPSE_FROM = 3
const WD = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']

export const plural = (n, a, b, c) => {
  const m = n % 10, h = n % 100
  return `${n} ${h >= 11 && h <= 14 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c}`
}

const dayKey = (at) => fmtDateOfMoment(at)              // «16.11.2026» по Москве
const isoOf = (dmy) => dmy.split('.').reverse().join('-')

export function dayTitle(dmy) {
  const wd = WD[calendarDate(isoOf(dmy)).getDay()]
  return isoOf(dmy) === todayMsk() ? `сегодня · ${wd}` : wd
}

export const whoOf = (it) => (it.actor.kind === 'cabinet' && it.actor.site ? `${it.actor.site} · ${it.actor.name}` : it.actor.name) || '—'

// [{ day, title, count, rows: [{ kind: 'one', item } | { kind: 'group', key, items }] }]
export function daysOf(items) {
  const days = []
  let cur = null
  items.forEach(it => {
    const d = dayKey(it.at)
    if (!cur || cur.day !== d) { cur = { day: d, title: dayTitle(d), n: 0, runs: [] }; days.push(cur) }
    cur.n += 1
    const last = cur.runs[cur.runs.length - 1]
    if (last && last.actor === it.actor.id && last.action === it.action) last.items.push(it)
    else cur.runs.push({ actor: it.actor.id, action: it.action, items: [it] })
  })
  return days.map(d => ({
    day: d.day, title: d.title, count: plural(d.n, 'запись', 'записи', 'записей'),
    rows: d.runs.flatMap(r => (r.items.length >= COLLAPSE_FROM
      ? [{ kind: 'group', key: `${d.day}|${r.items[0].id}`, items: r.items }]
      : r.items.map(item => ({ kind: 'one', item })))),
  }))
}

// Строка группы: время «с–по», число сделок, первая запись «и ещё N−1».
export function groupSummary(items) {
  const first = items[0], last = items[items.length - 1]
  const t1 = fmtTime(first.at), t0 = fmtTime(last.at)
  const codes = [...new Set(items.map(i => i.object?.code).filter(Boolean))]
  return {
    time: t0 === t1 ? t1 : `${t0}–${t1}`,
    object: codes.length ? plural(codes.length, 'сделка', 'сделки', 'сделок') : '—',
    details: `${first.details || first.object?.label || ''} · и ещё ${items.length - 1}`,
  }
}

// Период пинами → даты запроса (по Москве). «Период» — два поля дд.мм[.гггг].
export function periodDates(period, from, to) {
  const today = todayMsk()
  const back = (n) => { const d = calendarDate(today); d.setDate(d.getDate() - n); return d.toLocaleDateString('sv-SE') }
  if (period === 'today') return { date_from: today, date_to: today }
  if (period === '7') return { date_from: back(6), date_to: today }
  if (period === '30') return { date_from: back(29), date_to: today }
  if (period === 'range') return { date_from: parseDmy(from), date_to: parseDmy(to) }
  return {}
}

export function parseDmy(s) {
  const m = /^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?\s*$/.exec(String(s || ''))
  if (!m) return undefined
  const y = m[3] ? (m[3].length === 2 ? `20${m[3]}` : m[3]) : todayMsk().slice(0, 4)
  return `${y}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`
}
