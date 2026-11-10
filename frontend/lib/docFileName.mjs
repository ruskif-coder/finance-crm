// Номер и дата документа из имени файла 1С: «Счет на оплату № 291 от 06 ноября 2026 г..pdf», «УПД (статус 1) № 244 от
// 31 октября 2026 г.pdf», «Счёт №1247 от 5.11.2026.pdf» (владелец 10.11.2026). Нет «№» — null: угадывать не беремся.
// Без зависимостей — чтобы тест шёл голым node (`npm run test-rk`).
const MONTHS = ['январ', 'феврал', 'март', 'апрел', 'ма', 'июн', 'июл', 'август', 'сентябр', 'октябр', 'ноябр', 'декабр']

const pad = n => String(n).padStart(2, '0')

function monthOf(word) {
  const w = word.toLowerCase()
  // «ма» (мая) — короче всех, проверяем последним, чтобы «март» не попал в «ма»
  const order = MONTHS.map((m, i) => [m, i]).sort((a, b) => b[0].length - a[0].length)
  const hit = order.find(([m]) => w.startsWith(m))
  return hit ? hit[1] + 1 : null
}

function dateOf(rest) {
  const num = /от\s+(\d{1,2})[./](\d{1,2})[./](\d{4})/i.exec(rest)
  if (num) return `${pad(num[1])}.${pad(num[2])}.${num[3]}`
  const word = /от\s+(\d{1,2})\s+([а-яё]+)\s+(\d{4})/i.exec(rest)
  if (word) {
    const m = monthOf(word[2])
    if (m) return `${pad(word[1])}.${pad(m)}.${word[3]}`
  }
  return null
}

export function parseDocFileName(name) {
  const s = String(name || '')
  const no = /№\s*([0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё/-]*)/.exec(s)
  if (!no) return null
  return { no: no[1].replace(/[-/]+$/, ''), date: dateOf(s.slice(no.index + no[0].length)) }
}
