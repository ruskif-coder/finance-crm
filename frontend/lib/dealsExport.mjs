// Выгрузка реестра сделок: ОДНА таблица значений на все колонки реестра (владелец 13.10.2026: «добавляли
// новые поля, а в выгрузку они не попадают»). Колонка реестра без своего экспортёра ловится тестом
// `dealsExport.test.mjs`, а не глазами. Экранирование ячеек — на странице (`lib/csv.js`): здесь только значения.

const DASH = ''
const dmy = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  return m ? `${m[3]}.${m[2]}.${m[1]}` : (iso || DASH)      // формат владельца: день.месяц.год
}
const num = (v) => (v == null || Number.isNaN(Number(v)) ? DASH : Number(v))
const priceRange = (u) => {
  if (!u || u.price_min == null) return DASH
  return u.price_min === u.price_max ? num(u.price_min) : `${u.price_min}–${u.price_max}`
}
const METRIC = { clicks: 'клики', impressions: 'показы', shows: 'показы' }

// ключ колонки реестра → заголовки и ячейки (одна колонка реестра может дать несколько колонок файла)
export const EXPORT_COLUMNS = {
  bitrix_id: { head: ['Код'], cells: d => [d.code || d.bitrix_id] },
  agency: { head: ['Агентство'], cells: d => [d.agency] },
  advertiser: { head: ['Рекламодатель'], cells: d => [d.advertiser] },
  brand: { head: ['Бренд'], cells: d => [d.brand] },
  product: { head: ['Услуга'], cells: d => [d.product] },
  period: { head: ['Период'], cells: d => [d.period] },
  bitrix_stage: { head: ['Стадия'], cells: d => [d.bitrix_stage] },
  amount: { head: ['Сумма'], cells: d => [d.amount] },
  unit_price: { head: ['Цена ед.', 'Модель закупки'], cells: d => [priceRange(d.units), d.units?.model ?? DASH] },
  plan_fact: {
    head: ['План, ед.', 'Факт, ед.', 'Выполнение, %', 'Метрика'],
    cells: (d) => {
      const u = d.units
      if (!u || !u.metric || !u.plan) return [DASH, DASH, DASH, DASH]
      return [num(u.plan), u.fact == null ? DASH : num(u.fact),
        u.fact == null ? DASH : Math.round(u.fact / u.plan * 100), METRIC[u.metric] || u.metric]
    },
  },
  sales_rep: { head: ['Продавец'], cells: d => [d.sales_rep] },
  account_manager: { head: ['Аккаунт'], cells: d => [d.account_manager] },
  payer: { head: ['Контрагент'], cells: d => [d.payer] },
  pipeline: { head: ['Воронка'], cells: d => [d.pipeline] },
  period_from: { head: ['Старт РК'], cells: d => [dmy(d.period_from)] },
  period_to: { head: ['Конец РК'], cells: d => [dmy(d.period_to)] },
  title: { head: ['Сделка'], cells: d => [d.title] },
}
// Колонки реестра без текстового значения.
export const NOT_EXPORTED = ['files']
// Было в выгрузке до этой правки и не колонка реестра — остаётся, чтобы не терять привычное.
const EXTRA = { head: ['Слой'], cells: d => [d.money_layer] }

/** Заголовки и строки для выгрузки: колонки реестра в его порядке, затем «Слой». */
export function exportTable(deals, colKeys) {
  const cols = colKeys.filter(k => !NOT_EXPORTED.includes(k)).map(k => EXPORT_COLUMNS[k]).filter(Boolean)
  return {
    head: [...cols.flatMap(c => c.head), ...EXTRA.head],
    rows: (deals || []).map(d => [...cols.flatMap(c => c.cells(d)), ...EXTRA.cells(d)]),
  }
}
