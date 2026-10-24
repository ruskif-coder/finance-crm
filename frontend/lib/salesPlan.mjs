// «План продаж» — расчёты экрана (владелец 24.10.2026, docs/ПЛАН_план_продаж.md). Сервер (`app/sales/plan.py`) отдаёт
// по каждой строке 12 месяцев: цель (null — не задана), факт, в работе, планируемые по светофору, выполнено и прогноз.
// Здесь — только свёртка в кварталы и год, проценты, подсветка, формат и разложение года. Формулы выполнения и прогноза
// живут на сервере: здесь они лишь суммируются.

export const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const KEYS = ['fact', 'work', 'green', 'orange', 'grey', 'done', 'forecast']

/** Сумма ячеек. Цель — null, если ни в одной не задана (прочерк ≠ ноль); так же прогноз неделю назад. */
export function sumCells(cells) {
  const out = Object.fromEntries(KEYS.map(k => [k, cells.reduce((a, c) => a + (c[k] || 0), 0)]))
  const goals = cells.map(c => c.goal).filter(v => v != null)
  out.goal = goals.length ? goals.reduce((a, b) => a + b, 0) : null
  const wk = cells.map(c => c.forecast_week_ago).filter(v => v != null)
  out.forecast_week_ago = wk.length ? wk.reduce((a, b) => a + b, 0) : null
  return out
}

/** Колонки: 12 месяцев или 4 квартала. m0/m1 — месяцы (0-based) включительно. */
export function buckets(months, grain) {
  if (grain === 'q') return [0, 1, 2, 3].map(q => ({ key: `q${q + 1}`, label: `${q + 1} кв.`, m0: q * 3, m1: q * 3 + 2, c: sumCells(months.slice(q * 3, q * 3 + 3)) }))
  return months.map((c, m) => ({ key: `m${m}`, label: MONTHS[m], m0: m, m1: m, c }))
}

/** Положение колонки относительно сегодня: past | now | future. `cur` — индекс текущего месяца (−1 — год прошёл, 12 — не начался). */
export function phase(b, cur) {
  if (b.m1 < cur) return 'past'
  if (b.m0 > cur) return 'future'
  return 'now'
}

/** Индекс текущего месяца для года экрана. */
export function currentMonth(year, today) {
  const [y, m] = today.split('-').map(Number)
  return y === year ? m - 1 : y > year ? 12 : -1
}

export const pct = (v, goal) => (goal ? Math.round(v / goal * 100) : null)

/** Подсветка по % к цели: < 80 — красный, 80–99 — жёлтый, ≥ 100 — зелёный, ≥ 110 — насыщенный зелёный. */
export function heat(p) {
  if (p == null) return null
  return p >= 110 ? 'over' : p >= 100 ? 'ok' : p >= 80 ? 'mid' : 'bad'
}

/** Значение ячейки по выбранной метрике. Прошлое и текущий месяц — выполнено к цели, будущее — прогноз к цели. */
export function cellValue(c, metric, ph) {
  const base = ph === 'future' ? c.forecast : c.done
  const p = pct(base, c.goal)
  const v = metric === 'done' ? base : metric === 'pct' ? p : metric === 'forecast' ? c.forecast
    : metric === 'gap' ? (c.goal == null ? null : c.forecast - c.goal) : c.goal
  return { v, p, base, future: ph === 'future' && metric !== 'goal' }
}

/** Рубли → тыс. ₽ с шагом 100 тыс.: 34 312 000 → «34 300». Прочерк — для пустого. */
export function fmtK(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return (Math.round(v / 100000) * 100).toLocaleString('ru-RU')
}
export const fmtSigned = (v) => (v == null ? '—' : (v >= 0 ? '+' : '−') + fmtK(Math.abs(v)))

/** Год экрана: «к сегодняшнему дню» — выполнено ÷ сумма целей месяцев до текущего включительно. */
export function toDate(row, cur) {
  const upTo = Math.max(-1, Math.min(11, cur))
  const s = sumCells(row.months.slice(0, upTo + 1))
  return { done: s.done, goal: s.goal, p: pct(s.done, s.goal) }
}

/** Услуги по группам (поле «группа» услуги): [{group, rows}] в порядке сервера. */
export function groupServices(rows) {
  const out = []
  rows.forEach(r => {
    const g = r.group || '—'
    let e = out.find(x => x.group === g)
    if (!e) out.push(e = { group: g, rows: [] })
    e.rows.push(r)
  })
  return out
}

// ── разложение года (режим «Цели»), рубли ──────────────────────────────────
/** Поровну: 12 значений, остаток — первым месяцам, сумма точно равна году. */
export function spreadEven(total) {
  const cents = Math.round(total * 100), base = Math.floor(cents / 12), rest = cents - base * 12
  return Array.from({ length: 12 }, (_, m) => (base + (m < rest ? 1 : 0)) / 100)
}

/** По сезонности прошлого года: доли месяцев по выполненному; нет данных — поровну. */
export function spreadBySeason(total, prevDone) {
  const sum = (prevDone || []).reduce((a, b) => a + (b || 0), 0)
  if (!sum) return spreadEven(total)
  const raw = prevDone.map(v => Math.round(total * (v || 0) / sum * 100) / 100)
  const drift = Math.round((total - raw.reduce((a, b) => a + b, 0)) * 100) / 100
  const top = raw.indexOf(Math.max(...raw))
  raw[top] = Math.round((raw[top] + drift) * 100) / 100
  return raw
}

/** Как в прошлом году ± процент: пустые цели прошлого года остаются пустыми. */
export function copyPrev(prevGoals, pctUp) {
  return (prevGoals || Array(12).fill(null)).map(v => (v == null ? null : Math.round(v * (1 + pctUp / 100) * 100) / 100))
}

// ── ввод целей: полные рубли с разбивкой на тройки (владелец 24.10.2026: «полными, показывай как сейчас») ──
/** Текст поля → рубли. Пусто — null (цель не задана); копейки через запятую или точку допускаются. */
export function parseRub(s) {
  const t = String(s ?? '').replace(/[\s ]/g, '').replace(',', '.')
  return t === '' ? null : Number(t)
}
/** Рубли → текст поля: «10 000 000». Пусто — пустая строка. */
export function fmtRub(v) {
  if (v == null || Number.isNaN(v)) return ''
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}
/** Набор в поле: оставить цифры и запятую, разбить целую часть на тройки на лету. */
export function typeRub(s) {
  const clean = String(s).replace(/[^\d,.]/g, '').replace('.', ',')
  const [int, frac] = clean.split(',')
  const grouped = (int || '').replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return frac === undefined ? grouped : `${grouped},${frac.slice(0, 2)}`
}
