// Кнопка «↓ ADFOX» (выгрузка для площадок без нашего кода) в строке РК дашборда трафика (владелец 29.09.2026).
// Сборка архива идёт на сервере секунды: пока она идёт — крутилка и кнопка заперта
// (повторные нажатия собирали бы тот же архив ещё раз), итог — рядом с кнопкой:
// «скачано» или причина отказа словами сервера.
import { useState } from 'react'
import { btnSm } from '@/components/salesTableKit'
import { downloadOffsite } from '@/lib/dealDocs'
import { Cube } from '@/components/LogoLoader'

export default function OffsiteButton({ dealId }) {
  const [state, setState] = useState('idle')      // idle | busy | done | error
  const [why, setWhy] = useState('')

  const run = async () => {
    if (state === 'busy') return
    setState('busy'); setWhy('')
    let err = ''
    const ok = await downloadOffsite(dealId, (m) => { err = m })
    if (ok) {
      setState('done')
      setTimeout(() => setState(s => (s === 'done' ? 'idle' : s)), 4000)
    } else {
      setWhy(err || 'Не удалось собрать архив'); setState('error')
    }
  }

  const busy = state === 'busy'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      {state === 'error' && (
        <span title={why} style={{ fontSize: 11.5, color: 'var(--danger-fg)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          ⚠ {why}</span>
      )}
      {state === 'done' && <span style={{ fontSize: 11.5, color: 'var(--income-fg)' }}>архив скачан ✓</span>}
      <button style={{ ...btnSm(false), display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
        cursor: busy ? 'progress' : 'pointer', opacity: busy ? 0.75 : 1 }}
        disabled={busy} onClick={run}
        title="Баннеры и паспорт для площадок без нашего кода — заводить у них вручную">
        {busy && <Cube variant="spinner" size={12} />}
        {busy ? 'собираю архив…' : '↓ ADFOX'}
      </button>
    </span>
  )
}
