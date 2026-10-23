// Светофор вероятности сделки — один вид в дашборде продаж и реестре (владелец 23.10.2026).
// Цвет считает сервер тем же правилом, что колонку «Статусов продаж» (backend/app/sales/probability.py):
// `probability_auto` — что показать, `probability_color` — что записано, `probability_locked` — сделка в работе.
export const PROB_COLORS = { grey: 'var(--muted)', orange: 'var(--warning)', green: 'var(--success)' }
export const PROB_ORDER = ['grey', 'orange', 'green']
export const PROB_LABEL = { grey: 'малая', orange: 'средняя', green: 'высокая' }

export function probView(d) {
  const shown = d.probability_auto ?? d.probability_color ?? null
  const set = !!d.probability_color
  const title = d.probability_locked ? 'Сделка в работе — вероятность «факт», меняется только стадией'
    : !shown ? 'Вероятность не задана'
    : set ? `Вероятность: ${PROB_LABEL[shown]}`
    : `Вероятность по стадии: ${PROB_LABEL[shown]} — не задана вручную`
  return { color: PROB_COLORS[shown], auto: !set, locked: !!d.probability_locked, title }
}
