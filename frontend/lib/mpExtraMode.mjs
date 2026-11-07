// Условие доп. услуги в медиаплане: полная цена, скидка в процентах, бонус, фикс суммой.
// Скидка в процентах (владелец 07.11.2026: «произвольная скидка на доп. услугу») хранится в самом режиме строкой
// «Скидка 30 %» — тем же видом, что давний «Скидка 50 %»: колонка `mode` текстовая, схема не меняется, сервер смотрит
// в режиме только на «бонус». СК к доп. услугам не применяется — скидка на доп задаётся только здесь.

export const MODE_FIX = 'Фикс, ₽'
export const MODE_PCT = 'Задать %'           // пункт выпадашки рядом с 50 % и бонусом (владелец 07.11.2026); пишется «Скидка N %»
export const MODES = ['Полная цена', 'Скидка 50 %', MODE_PCT, 'Бонус', MODE_FIX]
export const PCT_DEFAULT = 10

const RATE = { 'Полная цена': 1, 'Бонус': 0 }
const PCT = /^Скидка\s+(\d+(?:[.,]\d+)?)\s*%$/

export function pctOf(mode) {
  const m = PCT.exec(String(mode || '').trim())
  return m ? Number(m[1].replace(',', '.')) : null
}

export const isPct = (mode) => pctOf(mode) != null

export function pctMode(pct) {
  return `Скидка ${String(pct).replace('.', ',')} %`
}

// Итог по режиму; у фикса и у незнакомого режима итог не пересчитывается.
export function totalFor(mode, price, prevTotal) {
  const pct = pctOf(mode)
  const rate = pct != null ? 1 - pct / 100 : RATE[mode]
  return rate == null ? (prevTotal || 0) : Math.round((price || 0) * rate)
}
