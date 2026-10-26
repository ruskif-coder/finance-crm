// Сверка паблишера за месяц (26.10.2026): общие правила экрана «Паблишеры → Взаимодействие».
// Статус приходит с сервера (`app/publisher_recon/board.status_of`); здесь только цвет, подписи и счёт.

export const ST = {
  'ждёт закрытия': { key: 'closing', label: 'ждёт закрытия', bg: 'var(--bg-subtle)', fg: 'var(--text-muted)', dot: 'var(--text-faint)' },
  'готово': { key: 'ready', label: 'готово', bg: 'var(--accent-tint)', fg: 'var(--accent-fg)', dot: 'var(--accent)' },
  'ожидает': { key: 'wait', label: 'ожидает', bg: 'var(--warning-tint)', fg: 'var(--warning-fg)', dot: 'var(--warning)' },
  late: { key: 'late', label: 'ожидает · просрочено', bg: 'var(--danger-tint)', fg: 'var(--danger-fg)', dot: 'var(--danger)' },
  'есть ответ': { key: 'answer', label: 'есть ответ', bg: 'var(--violet-tint)', fg: 'var(--violet-fg)', dot: 'var(--violet-fg)' },
  'согласовано': { key: 'done', label: 'согласовано', bg: 'var(--income-tint)', fg: 'var(--income-fg)', dot: 'var(--income)' },
}

/** Тон строки: просроченное «ожидает» — отдельный тон, остальное по статусу. */
export const toneOf = (r) => (r.late ? ST.late : ST[r.status] || ST['ждёт закрытия'])

/** Фильтры плиток: «ожидает» включает просроченные. */
export const passes = (r, filter) => {
  if (!filter || filter === 'all') return true
  const k = toneOf(r).key
  return filter === 'waitAll' ? (k === 'wait' || k === 'late') : k === filter
}

export function counts(rows) {
  const c = { all: rows.length, answer: 0, wait: 0, late: 0, ready: 0, closing: 0, done: 0 }
  rows.forEach(r => { c[toneOf(r).key] += 1 })
  return c
}

const nf = (v) => Math.round(v).toLocaleString('ru-RU').replace(/ /g, ' ')

/** Расхождение площадки с нашей цифрой: «+1 000» и «+2,3 %», «0» при совпадении, «—» до ответа. */
export function deltaOf(ours, theirs) {
  if (theirs == null) return { text: '—', pct: '', tone: 'none' }
  const d = theirs - ours
  if (d === 0) return { text: '0', pct: '', tone: 'zero' }
  return {
    text: (d > 0 ? '+' : '−') + nf(Math.abs(d)),
    pct: ours ? (d > 0 ? '+' : '−') + Math.abs(d / ours * 100).toFixed(1).replace('.', ',') + ' %' : '',
    tone: 'diff',
  }
}

/** Соседний месяц «ГГГГ-ММ». */
export function shiftMonth(period, step) {
  const [y, m] = period.split('-').map(Number)
  const d = new Date(Date.UTC(y, m - 1 + step, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

/** «2 сверки» / «5 сверок». */
export function plural(n, one, few, many) {
  const a = n % 10, b = n % 100
  if (a === 1 && b !== 11) return one
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return few
  return many
}

/** Цифра из поля ввода итога: только цифры, пустое — null. */
export const parseShows = (s) => {
  const v = parseInt(String(s ?? '').replace(/\D/g, ''), 10)
  return Number.isNaN(v) ? null : v
}

export const money = (shows, cpm) => (cpm && shows != null ? shows * cpm / 1000 : null)
