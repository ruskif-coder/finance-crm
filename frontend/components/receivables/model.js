/**
 * Дебиторка NAVY (хендофф docs/design_handoff_receivables_navy.zip, 19.11.2026) — расчёт на клиенте из ответа /reports/receivables.
 * Формулы — из макета: корзины возраста, «по риску», отборы, концентрация, «ждём на деле».
 *
 * Привычка клиента: «обычно +N дн» = среднее время оплаты (от 1-го числа следующего периода, колонка «Опл.» реестра) минус
 * отсрочка из карточки, не меньше 0. «Ждём на деле» = срок + привычка.
 */
const DAY = 86400000
const MON = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
export const MONTH_LONG = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

export const parseDate = (s) => { if (!s) return null; const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d) }
export const fd = (d) => (d ? `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}` : '—')
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
const days = (a, b) => Math.round((a - b) / DAY)
export const pl = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c)
export const invL = (n) => `${n} ${pl(n, 'счёт', 'счёта', 'счетов')}`
export const cpL = (n) => `${n} ${pl(n, 'контрагент', 'контрагента', 'контрагентов')}`
// правовая форма отдельным словом и кавычки; \b в JS кириллицу не видит — границы слова пробелами
const LEGAL = /(^|\s)(ООО|АО|ПАО|ЗАО|ОАО|ИП|НКО|АНО)(?=\s|$)|["«»“”]/g
export const shortName = (n) => (n || '—').replace(LEGAL, ' ').replace(/\s+/g, ' ').trim() || (n || '—')
const perLabel = (p) => { const m = /^(\d{4})-(\d{2})$/.exec(p || ''); return m ? `${MON[+m[2] - 1]} ${m[1]}` : (p || 'без периода') }

/** Статус счёта по дням после срока: до срока / текущая (до 30 дн) / просрочка — как в «Операциях». */
export const clsOf = (dd) => (dd <= 0 ? 'due' : dd <= 30 ? 'cur' : 'over')
export const STC = {
  due: { c: 'var(--ok)', fg: 'var(--text-secondary)', bg: 'var(--ok-tint)', bd: 'var(--ok-border)', tfg: 'var(--ok-fg)' },
  cur: { c: 'var(--attn)', fg: 'var(--attn-fg)', bg: 'var(--attn-tint)', bd: 'var(--attn-border)', tfg: 'var(--attn-fg)' },
  over: { c: 'var(--bad)', fg: 'var(--bad-fg)', bg: 'var(--bad-tint)', bd: 'var(--bad-border)', tfg: 'var(--bad-fg)' },
}

export const BK = [['−61 и ранее', -9999, -61], ['−60…−31', -60, -31], ['−30…−1', -30, -1], ['+1…+15', 0, 15], ['+16…+30', 16, 30],
  ['+31…+60', 31, 60], ['+61 и более', 61, 9999]]

/** Сузить ответ сервера: выбранные контрагенты (пусто — все) и «факт» — только счета, срок которых наступил
 *  (просрочка и текущая; aging_bucket сервера — тот же отбор, что overdue_only выгрузки). */
export function narrow(data, cps, fact) {
  const rows = data.rows
    .filter(r => !cps.length || cps.includes(r.counterparty))
    .map(r => (fact ? { ...r, operations: r.operations.filter(o => o.aging_bucket === 'overdue' || o.aging_bucket === 'current') } : r))
    .filter(r => r.operations.length)
  return { ...data, rows }
}

/** Строки сервера → клиенты экрана. notes — правки примечаний поверх сервера. */
export function clients(data, notes) {
  const today = parseDate(data.as_of)
  return data.rows.map(r => {
    const def = r.term_days ?? 60
    const usual = r.operations.find(o => o.usual_days != null)?.usual_days
    const delta = usual != null ? Math.max(0, usual - def) : 0
    const its = r.operations.map(o => {
      const srok = parseDate(o.due_date)
      return { id: o.id, art: o.article, doc: o.ds_num, inv: o.invoice, idate: parseDate(o.invoice_date), v: o.amount, per: perLabel(o.period),
        perKey: o.period || '', srok, dd: srok ? days(today, srok) : 0, docs: o.docs }
    })
    const b = [0, 0, 0]
    its.forEach(it => { b[{ over: 0, cur: 1, due: 2 }[clsOf(it.dd)]] += it.v })
    const sum = b[0] + b[1] + b[2]
    const we = r.mutual || 0
    const note = notes[r.counterparty_id] ?? r.note ?? ''
    const late = b[0] > 0
    return { id: r.counterparty_id, who: shortName(r.counterparty), full: r.counterparty, inn: r.inn, mgr: r.manager, def, delta, its, b, sum, we,
      net: Math.min(we, sum), note, late, act: late && !note.trim(), risk: b[0] * 3 + b[1] * 1.5 + b[2] * delta / 30 }
  })
}

/** Индекс корзины «по договору» (7 корзин дней к сроку) или «на деле» (5 корзин: когда придут деньги). */
export function bucketer(today, real) {
  const eom = (k) => new Date(today.getFullYear(), today.getMonth() + k + 1, 0)
  const mIdx = (d) => (d < today ? 0 : d <= eom(0) ? 1 : d <= eom(1) ? 2 : d <= eom(2) ? 3 : 4)
  const labels = real
    ? ['ждём уже сейчас', `до ${fd(eom(0))}`, MONTH_LONG[eom(1).getMonth()], MONTH_LONG[eom(2).getMonth()], `${MONTH_LONG[eom(3).getMonth()]} и позже`]
    : BK.map(q => q[0])
  const of = (x, it) => {
    if (!it.srok) return -1
    if (real) return mIdx(addDays(it.srok, x.delta))
    return BK.findIndex(q => it.dd >= q[1] && it.dd <= q[2])
  }
  return { labels, of, mIdx, eom }
}

export const FILTERS = [
  ['', 'Все', '', 'все должники'],
  ['over', 'С просрочкой', 'var(--bad)', 'есть счета, просроченные больше 30 дней'],
  ['soon', 'Срок оплаты в 7 дней', 'var(--attn)', 'срок оплаты одного из счетов наступает в ближайшие 7 дней'],
  ['nonote', 'Просрочка без примечания', 'var(--signal)', 'есть просрочка, а в примечании пусто — по долгу никто ничего не отметил'],
  ['net', 'Можно зачесть', 'var(--money)', 'мы тоже должны этому контрагенту — можно зачесть встречные обязательства'],
]
export const FILTER_FN = {
  over: x => x.late,
  soon: x => x.its.some(it => it.dd <= 0 && it.dd >= -7),
  nonote: x => x.act,
  net: x => x.net > 0,
}

/** Группы раскрытия: по периоду, с подитогом; only — оставить только счета этой корзины. */
export function groupsOf(x, only) {
  const by = {}
  x.its.forEach(it => {
    if (only && !only(it)) return
    const g = by[it.perKey] || (by[it.perKey] = { key: it.perKey, p: it.per, srok: it.srok, items: [], s: 0 })
    g.items.push(it); g.s += it.v
  })
  return Object.values(by).sort((a, b) => (a.key < b.key ? -1 : 1))
}

export { addDays }
