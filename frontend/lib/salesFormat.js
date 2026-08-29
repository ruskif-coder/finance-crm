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

// Два поведения на ноль/пусто, и оба нужны: в остатках и реестрах ноль — это значащий
// ноль («на счету 0»), а в P&L и план-факте пустая клетка означает «строки не было»,
// и ноль там читался бы как посчитанный результат. До выноса эти две функции были
// объявлены заново в тринадцати файлах под одним именем `fmt` — с расхождениями в
// округлении и в том, что показывать вместо пустоты.
export const grp0 = (v) => grp(v || 0)          // пусто → «0»
export const grpDash = (v) => (v ? grp(v) : '—') // пусто → «—»

// Процент с ТОЧКОЙ, 1 знак — так исторически считают финансовые экраны (P&L, финотчёт,
// план-факт). Отличается от pct() выше, где разделитель — запятая, как в разделе продаж.
// Свести к одному — заметная пользователю правка, отдельным решением.
export const pctDot = (v) => (v === null || v === undefined ? '—' : v.toFixed(1) + '%')

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
/** «01.12» — день и месяц без года. Рядом с fmtDateShort/fmtDateFull, потому что это
 *  тот же вопрос «как показать дату», просто с третьим ответом.
 *
 *  Было ШЕСТЬ копий по компонентам, и они расходились ровно там, где это видно:
 *  половина возвращала «—» на пустую дату, половина пустую строку, а две не приводили
 *  вход к строке и падали на числе. Пустое значение вынесено параметром, потому что оно
 *  РАЗНОЕ по смыслу: в ячейке реестра прочерк значит «даты нет», а внутри собираемой
 *  строки («01.12 — …») он значит «здесь ошибка вёрстки». Тот же приём, что у grp0 и
 *  grpDash: два поведения названы, а не спрятаны в умолчании.
 */
export const dm = (d, empty = '—') => {
  if (!d) return empty
  const [, m, dd] = String(d).slice(0, 10).split('-')
  return dd ? `${dd}.${m}` : String(d)
}

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
