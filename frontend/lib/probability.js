// Светофор вероятности сделки — один вид в дашборде продаж и реестре (владелец 23.10.2026).
// Цвет считает сервер тем же правилом, что колонку «Статусов продаж» (backend/app/sales/probability.py):
// `probability_auto` — что показать, `probability_color` — что записано, `probability_locked` — сделка в работе.
// Цвета — из «Статусов продаж», они эталон (владелец 27.10.2026): здесь низкая была серой, там красной — одна сделка
// выглядела по-разному в реестре и в матрице. Берём оттуда, чтобы палитры не разошлись снова.
import { COL_LIGHT, COL_WORD, GROUP } from './salesStatus'
const COL_OF_LIGHT = Object.fromEntries(Object.entries(COL_LIGHT).map(([col, light]) => [light, col]))
export const PROB_COLORS = Object.fromEntries(Object.entries(COL_OF_LIGHT).map(([light, col]) => [light, GROUP[col].dot]))
export const PROB_ORDER = ['grey', 'orange', 'green']
export const PROB_LABEL = Object.fromEntries(Object.entries(COL_OF_LIGHT).map(([light, col]) => [light, COL_WORD[col]]))

export function probView(d) {
  const shown = d.probability_auto ?? d.probability_color ?? null
  const set = !!d.probability_color
  const title = d.probability_locked ? 'Сделка в работе — вероятность «факт», меняется только стадией'
    : !shown ? 'Вероятность не задана'
    : set ? `Вероятность: ${PROB_LABEL[shown]}`
    : `Вероятность по стадии: ${PROB_LABEL[shown]} — не задана вручную`
  return { color: PROB_COLORS[shown], auto: !set, locked: !!d.probability_locked, title }
}
