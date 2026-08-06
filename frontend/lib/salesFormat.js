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

// Знаковая сумма с ₽ и типографским минусом: «+1 200 ₽» / «−1 200 ₽».
export const signRub = (n) => `${n >= 0 ? '+' : '−'}${grp(Math.abs(n || 0))} ₽`
// Знаковая сумма в млн (1 знак): «+2,3 млн» / «−2,3 млн».
export const signMln = (n) => `${n >= 0 ? '+' : '−'}${mln(Math.abs(n || 0), 1)} млн`

// Дата дд.мм.гг (список/детали) и дд.мм.гггг (форма/срез).
export const fmtDateShort = (d) => { if (!d) return '—'; const [y, m, dd] = String(d).slice(0, 10).split('-'); return dd ? `${dd}.${m}.${y.slice(2)}` : d }
export const fmtDateFull = (d) => { if (!d) return '—'; const [y, m, dd] = String(d).slice(0, 10).split('-'); return dd ? `${dd}.${m}.${y}` : d }

// Цвета банков — единый источник для десктопа (ДДС) и мобилы (ДДС, операции).
export const BANK_HEX = { 'АльфаБанк': '#E8453F', 'ОПТ Банк': '#2FB8A8', 'Совкомбанк': '#8B93A6', 'Наличные': '#8B7BE8' }
export const bankColor = (n) => BANK_HEX[n] || '#C3C9D8'

// Округление верхней границы шкалы графика до «круглого» шага.
export const niceMax = (v) => {
  if (!v || v <= 0) return 1e6
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return step * pow
}

// Имя скачиваемого файла: «<prefix> <Название РК> ДД.ММ.ГГГГ ЧЧ-ММ.<ext>» по московскому
// времени. prefix — вид документа (для МП «MP Simb-AD»). Недопустимые символы вычищаются.
export const downloadName = (title, ext = 'pdf', prefix = '') => {
  const p = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date())
  const g = (t) => (p.find((x) => x.type === t) || {}).value || ''
  const stamp = `${g('day')}.${g('month')}.${g('year')} ${g('hour')}-${g('minute')}`
  const safe = (title || 'Медиаплан').replace(/[\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim()
  const head = prefix ? `${prefix} ` : ''
  return `${head}${safe} ${stamp}.${ext}`
}
