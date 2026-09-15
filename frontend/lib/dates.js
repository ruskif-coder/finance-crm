/**
 * Даты и время с сервера — один модуль на весь фронт.
 *
 * ## Почему это вообще проблема
 *
 * Замер 14.09.2026: контейнеры и postgres живут в UTC (`TZ` не задана ни у одного
 * сервиса, `now()` отдаёт `+00`), а люди — в Москве. При этом FastAPI сериализует
 * наивный `datetime` БЕЗ суффикса `Z` — строкой «2026-09-14T19:30:00». `new Date()`
 * такую строку читает как МЕСТНОЕ время, и момент, случившийся секунду назад,
 * показывается как «3 ч назад».
 *
 * Ошибка правдоподобная: время выглядит настоящим, просто не тем. Поэтому её не видно
 * ни в тестах, ни глазами — пока кто-нибудь не сверит с часами.
 *
 * ## Два разных типа, и путать их нельзя
 *
 *     *_at            DateTime — МОМЕНТ в UTC: created_at, updated_at, synced_at.
 *                     Переводим в Москву. Без перевода время врёт на три часа.
 *
 *     *_date, *_from  Date — КАЛЕНДАРНЫЙ ДЕНЬ: date_from, watch_until, contract_date.
 *     *_to, period    Часового пояса у него нет вовсе. Переводить его — значит
 *                     однажды получить «договор от 31.08» вместо 01.09.
 *
 * `new Date('2026-09-14')` разбирает строку как ПОЛНОЧЬ UTC — в Москве это всё ещё
 * 14-е, а в Нью-Йорке уже 13-е. Поэтому календарный день здесь разбирается по частям
 * строки и не попадает в часовые пояса ни на одном шаге.
 *
 * ## Что делать в коде
 *
 *     fmtDateTime(row.created_at)   14.09.2026 22:31
 *     fmtTime(row.created_at)       22:31
 *     fmtDate(row.date_from)        14.09.2026
 *     fmtDateShort(row.date_from)   14.09
 *     serverDate(row.created_at)    Date — когда нужна арифметика, а не показ
 *
 * Прямой `new Date(строка_с_сервера)` в экранах запрещён гейтом `check-dates`.
 */
const MSK = 'Europe/Moscow'
const DASH = '—'

/** Момент с сервера → `Date`. Наивной строке дописывается `Z`: она UTC, просто
    сериализована без суффикса. Строка со своим смещением остаётся как есть. */
export const serverDate = (v) => {
  if (!v) return null
  const s = String(v)
  const utc = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z'
  const d = new Date(utc)
  return isNaN(d.getTime()) ? null : d
}

const partsOf = (d, opts) => new Intl.DateTimeFormat('ru-RU', { timeZone: MSK, ...opts })
  .formatToParts(d).reduce((a, p) => { a[p.type] = p.value; return a }, {})

/** Момент → «14.09.2026 22:31» по Москве. */
export const fmtDateTime = (v, dash = DASH) => {
  const d = serverDate(v)
  if (!d) return dash
  const p = partsOf(d, {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  return `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}`
}

/** Момент → «14.09.26 22:31» по Москве. Двузначный год для узких колонок — истории
    событий на карточке сделки. Отдельная функция, а не обрезка готовой строки:
    регулярка поверх формата ломается молча при первой же его правке. */
export const fmtDateTimeShort = (v, dash = DASH) => {
  const d = serverDate(v)
  if (!d) return dash
  const p = partsOf(d, {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  return `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}`
}

/** Момент → «22:31» по Москве. Для строк, где день и так понятен из контекста. */
export const fmtTime = (v, dash = DASH) => {
  const d = serverDate(v)
  if (!d) return dash
  const p = partsOf(d, { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${p.hour}:${p.minute}`
}

/** Сейчас по Москве, «22:31». Для отметок «обновлено в …»: часы БРАУЗЕРА показали бы
    иркутянину его время рядом с московским временем событий на том же экране. */
export const nowTime = () => fmtTime(new Date().toISOString())

/** Момент → «14.09.2026» по Москве. Когда время не нужно, а сдвиг суток — нужен:
    событие в 01:00 МСК произошло 14-го, хотя по UTC это ещё 13-е. */
export const fmtDateOfMoment = (v, dash = DASH) => {
  const d = serverDate(v)
  if (!d) return dash
  const p = partsOf(d, { day: '2-digit', month: '2-digit', year: 'numeric' })
  return `${p.day}.${p.month}.${p.year}`
}

/** Календарный день «2026-09-14» → `Date` МЕСТНОЙ полуночи.

    Именно местной, а не UTC: дальше у него спрашивают день недели и месяц, и `new
    Date('2026-09-14')` (полночь UTC) западнее Гринвича отдаёт предыдущие сутки.
    Возвращается `Date`, а не строка — для арифметики и `getDay()`. */
export const calendarDate = (v) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ''))
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null
}

/** Календарный день «2026-09-14» → «14.09.2026». БЕЗ часовых поясов: у даты их нет.
    Понимает и «2026-09-14T00:00:00» — так его отдаёт сериализатор для колонки Date. */
export const fmtDate = (v, dash = DASH) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ''))
  return m ? `${m[3]}.${m[2]}.${m[1]}` : dash
}

/** Сколько полных суток прошло с момента. Отрицательное — момент в будущем. */
export const daysSince = (v) => {
  const d = serverDate(v)
  return d ? Math.floor((Date.now() - d.getTime()) / 86400000) : null
}

/** «12 мин», «3 ч», «вчера», «4 дня» — относительное время для лент и панелей.

    БЕЗ слова «назад»: рядом обычно стоит число самого события («молчит 4 дн.»), и две
    длительности подряд читаются как одна путаная. */
export const ago = (v) => {
  const d = serverDate(v)
  if (!d) return ''
  const m = Math.floor((Date.now() - d.getTime()) / 60000)
  if (m < 1) return 'только что'
  if (m < 60) return `${m} мин`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} ч`
  const days = Math.floor(h / 24)
  if (days === 1) return 'вчера'
  if (days < 7) return `${days} ${days < 5 ? 'дня' : 'дней'}`
  return fmtDateOfMoment(v)
}
