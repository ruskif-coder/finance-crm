/**
 * Арифметика СТРОКИ медиаплана — зеркало backend/app/sales/mp_row.py.
 *
 * Одни и те же две величины считались в пяти местах фронта (конструктор, PDF-маппер,
 * карточка сделки, дашборд), и копии разъехались:
 *
 * · СУММА — `объём × цена × (1 − скидка)`, делённое на 1000 ТОЛЬКО для CPM.
 * · ПОКАЗЫ — раньше просто `volume`. Это верно для CPM (объём и есть показы), но у
 *   Фикса и Пакета в объёме лежат ШТУКИ закупки, а у CPC — клики. Строка «Polza · Фикс ·
 *   1 ед × 80 000» давала «1 показ», охват 0,25 и CPM 80 000 000 ₽.
 *
 * Решение владельца 08.09.2026: показы — собственное поле прогноза (`forecast.imp`),
 * вводит аккаунт, и это его ответственность. У CPM поле не спрашивается: там показы
 * гарантированы договором и равны объёму.
 *
 * ЗАПЯТАЯ. `num` понимает десятичную запятую, потому что человек её и вводит. Замерено
 * 08.09.2026: в 19 значениях CTR из 42 стоит запятая, а PDF-маппер считал их через `+x`
 * и получал NaN → 0. На экране конструктора CTR был, в PDF у клиента — пусто.
 */
export const isCpm = (model) => String(model || '').trim().toUpperCase() === 'CPM'

export const num = (v) => {
  if (v === null || v === undefined || v === '') return 0
  const n = parseFloat(String(v).replace(/[\s ₽%]/g, '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}

export const rowNet = (model, volume, unitPrice, discount = 0) =>
  Math.round(num(volume) * num(unitPrice) * (1 - num(discount)) / (isCpm(model) ? 1000 : 1))

/** Прогнозные показы: ручной ввод аккаунта, иначе объём — но только у CPM. */
export const rowImp = (model, volume, forecast) => {
  const v = (forecast || {}).imp
  if (v !== null && v !== undefined && v !== '') return num(v)
  return isCpm(model) ? num(volume) : 0
}
