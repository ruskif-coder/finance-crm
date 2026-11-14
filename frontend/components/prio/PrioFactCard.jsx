/**
 * Факт приоритезации на закрытии — только «Итог по площадкам» (шаблон, загрузка итога, источник по площадкам), без настройки
 * запроса. Для расхлопа «Моих сделок» на «Итоговой сверке» (владелец 13.11.2026); в карточке тот же `PrioFactTotals` живёт
 * внутри `PrioAssembly`.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'
import PrioFactTotals from '@/components/prio/PrioFactTotals'

export default function PrioFactCard({ dealId, canEdit, cardStyle }) {
  const [s, setS] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const base = `/prio/deal/${dealId}`
  const load = useCallback(() => {
    api.get(base, auth()).then(r => { setS(r.data); setErr('') }).catch(e => setErr(detailText(e, 'Приоритезация не загрузилась')))
  }, [base])
  useEffect(() => { load() }, [load])
  const call = async (fn) => {
    setBusy(true); setErr('')
    try { const r = await fn(); if (r?.data?.placements) setS(r.data); else load(); return true }
    catch (e) { setErr(detailText(e, 'Не удалось')); return false }
    finally { setBusy(false) }
  }
  if (!s) return err ? <div style={{ ...cardStyle, color: 'var(--danger-fg)', fontSize: 12.5 }}>{err}</div> : null
  return (
    <div style={cardStyle}>
      {!!err && <div style={{ color: 'var(--danger-fg)', fontSize: 12.5, marginBottom: 8 }}>{err}</div>}
      <PrioFactTotals s={s} base={base} canEdit={canEdit} busy={busy} call={call} />
    </div>
  )
}
