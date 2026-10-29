/* Выгрузка экрана «Кампании» в Excel (владелец 29.10.2026): ровно то, что на экране после площадки и фильтров, в том
   же порядке месяцев и строк. CSV с BOM и «;» — Excel в русской локали открывает его двойным щелчком как таблицу; своей
   библиотеки xlsx у кабинета нет намеренно. Чистый модуль — без DOM, проверяется `node --test`. */

const COLUMNS = ['Месяц', 'Площадка', 'Рекламодатель', 'Бренд', 'Услуга', 'Поверхность', 'Флайт', 'План показов',
  'Факт показов', 'Биллинг до НДС, ₽', 'ЕРИД', 'Статус']

// Биллинг по факту показов и CPM договора площадки — одна формула на экран и на выгрузку.
export const billing = (fact, cpm) => Math.round(fact / 1000 * cpm)

/* Текст, начинающийся с = + - @ (или с таба/CR перед ними), Excel принял бы за формулу (CSV-инъекция): имена брендов и рекламодателей приходят из
   нашего справочника, но «правильный» ввод — не защита. Апостроф Excel не показывает, а значение остаётся текстом. */
function cell(v) {
  if (v == null) return ''
  if (typeof v === 'number') return String(v)
  let s = String(v)
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s
  return /[;"\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

/** `months` — [{ key: 'YYYY-MM', list: [кампания] }] в порядке экрана. */
export function campaignsCsv(months) {
  const lines = [COLUMNS.join(';')]
  for (const m of months) {
    for (const c of m.list) {
      lines.push([m.key, c.site, c.advertiser, c.brand_name, c.service, c.surface, c.flight, c.plan, c.fact,
        c.fact ? billing(c.fact, c.cpm) : '', c.erid, c.status].map(cell).join(';'))
    }
  }
  return '﻿' + lines.join('\r\n') + '\r\n'
}
