// Светофор вероятности в строке сделки — один на дашборд продаж и реестр (владелец 23.10.2026). Цвет — тем же правилом, что
// колонка «Статусов продаж» (`lib/probability.probView`): не заданный вручную — бледнее, у сделки в работе — заперт.
import api, { auth } from '@/lib/api'
import { probView } from '@/lib/probability'

export default function ProbDot({ d, canEdit, onPick }) {
  const pv = probView(d)
  const editable = canEdit && !pv.locked
  return (
    <button onClick={e => { e.stopPropagation(); if (editable) onPick(e.currentTarget.getBoundingClientRect()) }} title={pv.title}
      style={{ display: 'inline-block', width: 14, height: 14, borderRadius: '50%', border: pv.color ? 'none' : '1.5px solid var(--border-card)',
        background: pv.color || 'transparent', opacity: pv.auto && !pv.locked ? 0.4 : 1, cursor: editable ? 'pointer' : 'default', padding: 0 }} />
  )
}

/** Сохранить светофор: сразу на экране, после ответа — цвет, посчитанный сервером; отказ (сделка в работе) — откат и текст. */
export async function saveProbability(id, color, deals, setDeals) {
  const prev = deals.find(x => x.id === id)
  setDeals(ps => ps.map(x => (x.id === id ? { ...x, probability_color: color, probability_auto: color || x.probability_auto } : x)))
  try {
    const r = await api.post(`/sales/deals/${id}/probability`, { color }, auth())
    setDeals(ps => ps.map(x => (x.id === id ? { ...x, probability_auto: r.data.probability_auto } : x)))
  } catch (e) {
    setDeals(ps => ps.map(x => (x.id === id ? { ...x, probability_color: prev?.probability_color ?? null, probability_auto: prev?.probability_auto } : x)))
    alert(e.response?.data?.detail || 'Не удалось сохранить вероятность')
  }
}
