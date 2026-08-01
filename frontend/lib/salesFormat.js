// Единые форматтеры чисел/дат раздела продаж. До выноса были размножены по
// страницам с разной разрядностью — одни данные показывались по-разному.

// Сумма сокращённо: «1.20 млн» / «640 тыс» / «512» (реестр, дашборд-таблица).
export const fmtMoney = (v) => {
  if (v === null || v === undefined) return '—'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + ' млн'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + ' тыс'
  return String(Math.round(v))
}

// Полное число с разрядами и ₽ (тултипы сумм).
export const fmtFull = (v) => (v === null || v === undefined ? '—' : new Intl.NumberFormat('ru-RU').format(v) + ' ₽')

// Дата как есть из API: ГГГГ-ММ-ДД.
export const fmtDate = (d) => (d ? String(d).slice(0, 10) : '—')

// Целое с разделителями разрядов, без ₽.
export const grp = (v) => (v == null ? '—' : new Intl.NumberFormat('ru-RU').format(Math.round(v)))

// В миллионы, ru-RU. d — число знаков после запятой (по умолчанию 1).
export const mln = (v, d = 1) => (v == null ? '—'
  : (v / 1e6).toLocaleString('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }))

// В миллионы, 0 знаков от 10 млн и 1 знак ниже — для осей/подписей.
export const mlnAuto = (v) => (v == null ? '—'
  : (v / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: Math.abs(v) >= 1e7 ? 0 : 1 }))

// Проценты, 1 знак.
export const pct = (v) => (v == null ? '—'
  : v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%')

// Округление верхней границы шкалы графика до «круглого» шага.
export const niceMax = (v) => {
  if (!v || v <= 0) return 1e6
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return step * pow
}
