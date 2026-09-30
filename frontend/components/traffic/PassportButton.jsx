// Кнопка «↓» — паспорт сделки: .xlsx по всей РК, без креативов (владелец 30.09.2026).
// Стоит перед «↓ ADFOX»; ошибка — в подсказке и красным цветом стрелки.
import { useState } from 'react'
import { btnSm } from '@/components/salesTableKit'
import { downloadPassport } from '@/lib/dealDocs'

export default function PassportButton({ dealId }) {
  const [busy, setBusy] = useState(false)
  const [why, setWhy] = useState('')
  const run = async () => {
    if (busy) return
    setBusy(true); setWhy('')
    let err = ''
    const ok = await downloadPassport(dealId, (m) => { err = m })
    setBusy(false)
    if (!ok) setWhy(err || 'Не удалось собрать паспорт')
  }
  return (
    <button style={{ ...btnSm(false), cursor: busy ? 'progress' : 'pointer', opacity: busy ? 0.6 : 1,
      color: why ? 'var(--danger-fg)' : undefined }}
      disabled={busy} onClick={run} title={why ? `Паспорт сделки: ${why}` : 'Паспорт сделки'}>↓</button>
  )
}
