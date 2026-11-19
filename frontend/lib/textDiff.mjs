/**
 * Где расходятся два текста — для сверки XML УПД со сделкой в «Закрывающих документах» (владелец 19.11.2026: «подсвечивать кусок,
 * который не сходится, и комментарий, если это не очевидно»). Без зависимостей: проверяется `node --test`.
 *
 * Сравнение — по словам. Оформление (кавычки, тире, ё, регистр, невидимые символы) словами НЕ считается разницей — так же, как
 * сервер (`app/onec_desk/xmlparse.text_key`). Если слова совпали, а строки нет — разница невидимая, и пояснение называет символы.
 */

const INVISIBLE = /[­​-‏⁠﻿]/g
const CHAR_NAMES = {
  ' ': 'неразрывный пробел', '­': 'мягкий перенос', '​': 'символ нулевой ширины', '‌': 'символ нулевой ширины',
  '‍': 'символ нулевой ширины', '⁠': 'символ нулевой ширины', '﻿': 'невидимый символ BOM', '\t': 'табуляция',
  '\n': 'перевод строки', '–': 'среднее тире', '—': 'длинное тире', '−': 'знак минуса', '‑': 'неразрывный дефис',
  '«': 'кавычки «»', '»': 'кавычки «»', '“': 'кавычки “”', '”': 'кавычки “”', '„': 'кавычки „“', '‘': 'кавычки ‘’', '’': 'кавычки ‘’',
}

/** Слово без оформления — ключ сравнения. */
export const looseKey = (w) => String(w || '').normalize('NFC').replace(INVISIBLE, '')
  .replace(/[«»“”„‟‘’‚‛"'`]/g, '"').replace(/[‐-―−]/g, '-').replace(/ё/gi, 'е')
  .replace(/[.,;:]+$/, '').toLowerCase()

const words = (s) => String(s || '').split(/\s+/).filter(Boolean)

/** LCS по ключам слов → две разметки: { got: [{t, bad}], want: [{t, bad}] }. bad — слова нет на другой стороне. */
export function diffWords(got, want) {
  const a = words(got), b = words(want)
  const ka = a.map(looseKey), kb = b.map(looseKey)
  const n = a.length, m = b.length
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) {
    L[i][j] = ka[i] && ka[i] === kb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  }
  const g = [], w = []
  let i = 0, j = 0
  while (i < n || j < m) {
    if (i < n && j < m && ka[i] === kb[j]) { g.push({ t: a[i], bad: false }); w.push({ t: b[j], bad: false }); i += 1; j += 1 }
    else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) { w.push({ t: b[j], bad: true }); j += 1 }
    else { g.push({ t: a[i], bad: true }); i += 1 }
  }
  return { got: g, want: w }
}

/* Подряд идущие «плохие» слова одной стороны — одним куском. */
const chunks = (marks) => marks.reduce((acc, x, i) => {
  if (x.bad && i > 0 && marks[i - 1].bad) acc[acc.length - 1] += ' ' + x.t
  else if (x.bad) acc.push(x.t)
  return acc
}, [])

const shorten = (s, n = 60) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

/** Пояснение словами: что не совпало. Пусто — тексты совпадают. */
export function explainDiff(got, want) {
  const a = String(got || ''), b = String(want || '')
  if (a === b) return []
  const d = diffWords(a, b)
  const extra = chunks(d.got), miss = chunks(d.want)
  const out = []
  if (!extra.length && !miss.length) {
    // слова те же — разница в оформлении: назвать символы, которые есть только с одной стороны
    const only = (x, y) => [...new Set([...x].filter(c => CHAR_NAMES[c] && !y.includes(c)).map(c => CHAR_NAMES[c]))]
    const inGot = only(a, b), inWant = only(b, a)
    if (inGot.length) out.push(`слова те же, в УПД другие символы: ${inGot.join(', ')}`)
    if (inWant.length) out.push(`слова те же, в сделке другие символы: ${inWant.join(', ')}`)
    if (!out.length) out.push('слова те же — разница только в оформлении (пробелы, регистр, знаки препинания)')
    return out
  }
  const pairs = Math.min(extra.length, miss.length)
  for (let k = 0; k < pairs && out.length < 3; k += 1) {
    const x = extra[k], y = miss[k]
    const digitsOnly = x.replace(/\d/g, '') === y.replace(/\d/g, '')
    out.push(`в УПД «${shorten(x)}» вместо «${shorten(y)}»${digitsOnly ? ' — другие цифры' : ''}`)
  }
  extra.slice(pairs).forEach(x => out.length < 3 && out.push(`в УПД лишнее: «${shorten(x)}»`))
  miss.slice(pairs).forEach(y => out.length < 3 && out.push(`в УПД нет: «${shorten(y)}»`))
  return out
}
