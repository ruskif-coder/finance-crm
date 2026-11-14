// Три контура «Моих сделок» (дашборд аккаунта v5, 13.11.2026): Песочница — до брони, В работе — от брони до конца кампании,
// Документы — мастер-сделки. Стадия строки — по слоту сервера (`row.slot`) и подколонке «чей ход» (`row.turn.col`) для песочницы.
// «Чей ход» считает сервер (`app/sales/account_turn.py`); здесь только раскладка по контурам, стадиям и группам.

export const CONTOURS = [
  { key: 'sandbox', n: 1, title: 'Песочница', sub: 'медиапланы до брони', unit: 'МП в работе', stages: [
    { key: 'prep', label: 'Готовим МП', match: r => r.slot === 'mp_prep' },
    { key: 'client', label: 'У клиента', match: r => r.slot === 'mp_sent' && r.turn?.col === 'client' },
    { key: 'nudge', label: 'Пора напомнить', match: r => r.turn?.col === 'nudge' },
    { key: 'stuck', label: 'Зависли', match: r => r.turn?.col === 'stuck' },
  ] },
  { key: 'work', n: 2, title: 'В работе', sub: 'от брони до конца кампании', unit: 'сделка', stages: [
    { key: 'booking', label: 'Бронь', match: r => r.slot === 'booking' },
    { key: 'prep', label: 'Готовятся к старту', match: r => r.slot === 'prep' },
    { key: 'live', label: 'В размещении', match: r => r.slot === 'live' },
    { key: 'recon', label: 'Итоговая сверка', match: r => r.slot === 'recon' },
  ] },
]
const SANDBOX = ['mp_prep', 'mp_sent']
const WORK = ['booking', 'prep', 'live', 'recon', 'unmapped']

// Статусы пакета в контуре «Документы»: архив — вне экрана.
export const DOC_STAGES = [
  { key: 'черновик', label: 'Черновик' }, { key: 'согласование', label: 'Согласование' },
  { key: 'ждём 1С', label: 'Ждём 1С' }, { key: 'выставление', label: 'Выставление' },
  { key: 'ждём оплату', label: 'Ждут оплату' },
]

export const contourOf = (r) => (SANDBOX.includes(r.slot) ? 'sandbox' : WORK.includes(r.slot) ? 'work' : null)

export const hot = (r) => r.urgency === 'overdue'
export const mine = (r) => !!r.turn?.mine
export const good = (r) => !!r.turn?.good && !r.turn?.mine

/** Итоги блока контура: число, сумма, ваш ход, горит, всё хорошо и счёт по стадиям. */
export function summary(rows, contour) {
  const c = CONTOURS.find(x => x.key === contour)
  return {
    n: rows.length,
    sum: rows.reduce((s, r) => s + (r.amount || 0), 0),
    mine: rows.filter(mine).length, hot: rows.filter(hot).length, good: rows.filter(good).length,
    stages: c ? c.stages.map(st => ({ ...st, n: rows.filter(st.match).length })) : [],
  }
}

/** Строки, видимые при выбранных стадиях (ИЛИ внутри выбора). Пустой выбор — весь контур. */
export function inStages(rows, contour, picked) {
  const c = CONTOURS.find(x => x.key === contour)
  if (!c || !picked.length) return rows
  const ms = c.stages.filter(st => picked.includes(st.key)).map(st => st.match)
  return rows.filter(r => ms.some(m => m(r)))
}

/** Группы списка: «Ваш ход», «Ждём: кто» (по одному на участника), «Всё хорошо: кто». Порядок — эталона. */
export function groups(rows) {
  const out = [{ key: 'mine', title: 'Ваш ход', tone: 'mine', rows: rows.filter(mine) }]
  const by = (pred, prefix, tone) => {
    const m = new Map()
    rows.filter(pred).forEach(r => {
      const who = r.turn?.who || 'не определено'
      if (!m.has(who)) m.set(who, [])
      m.get(who).push(r)
    })
    ;[...m.entries()].sort((a, b) => b[1].length - a[1].length)
      .forEach(([who, list]) => out.push({ key: `${tone}:${who}`, title: `${prefix}: ${who}`, tone, rows: list }))
  }
  by(r => !mine(r) && !good(r), 'Ждём', 'wait')
  by(good, 'Всё хорошо', 'good')
  return out.filter(g => g.rows.length)
}

// Пакеты мастер-сделок: ход аккаунта — только до «ждём 1С» (владелец 13.11.2026: дальше ЭДО, подпись и оплата — финансов).
// Реестр пишет `todo.who = аккаунт` и у «выставления» — для «Моих сделок» это ход финансов, как и у сделок (`account_turn.py`).
const PACK_ACCOUNT = ['черновик', 'согласование']
const PACK_WHO = { 'ждём 1С': 'бухгалтер', 'выставление': 'финансы', 'ждём оплату': 'финансы' }

/** {mine, who} пакета. */
export function packTurn(p) {
  if (PACK_ACCOUNT.includes(p.status) && p.todo?.who === 'аккаунт') return { mine: true, who: 'аккаунт' }
  const who = PACK_WHO[p.status] || (p.todo?.who && p.todo.who !== 'аккаунт' ? p.todo.who : 'юрист')
  return { mine: false, who }
}
export const packMine = (p) => packTurn(p).mine

/** Группы пакетов: «Ваш ход», затем «Ждём: кто». */
export function packGroups(packs) {
  const out = [{ key: 'mine', title: 'Ваш ход', tone: 'mine', rows: packs.filter(packMine) }]
  const m = new Map()
  packs.filter(p => !packMine(p)).forEach(p => {
    const who = packTurn(p).who
    if (!m.has(who)) m.set(who, [])
    m.get(who).push(p)
  })
  ;[...m.entries()].sort((a, b) => b[1].length - a[1].length).forEach(([who, list]) => out.push({ key: `wait:${who}`, title: `Ждём: ${who}`, tone: 'wait', rows: list }))
  return out.filter(g => g.rows.length)
}
