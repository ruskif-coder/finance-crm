// Кнопка «Темп размещения» — вилка (владелец 24.10.2026): «Поднять темп» (буст остатка, как с 08.10) или
// «Перераспределить» (недобор площадок, упёршихся в сеть, — площадкам с запасом). Подсказка у второго пункта —
// из того же расчёта, что окно перераспределения.
import { useEffect, useState } from 'react'
import { Modal, MONO } from '@/components/salesTableKit'
import api from '@/lib/api'
import { grp } from '@/lib/salesFormat'
import BoostModal from './BoostModal'
import ReallocModal from './ReallocModal'

const card = { display: 'flex', flexDirection: 'column', gap: 6, padding: '16px 18px', borderRadius: 14, textAlign: 'left',
  border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontFamily: 'inherit' }

export default function TempoModal({ row, auth, canEdit, onClose, onDone }) {
  const [mode, setMode] = useState(null)
  const [hint, setHint] = useState(null)

  useEffect(() => {
    let alive = true
    api.get(`/traffic-dashboard/campaign/${row.id}/realloc`, auth()).then(r => { if (alive) setHint(r.data) }).catch(() => {})
    return () => { alive = false }
  }, [row.id, auth])

  if (mode === 'boost') return <BoostModal row={row} auth={auth} canEdit={canEdit} onClose={onClose} onDone={onDone} />
  if (mode === 'realloc') return <ReallocModal row={row} auth={auth} canEdit={canEdit} onClose={onClose} onDone={onDone} onBack={() => setMode(null)} />

  const reallocNote = !hint ? 'считаю…' : hint.boost_live ? 'сначала снимите буст'
    : hint.moved ? `перенести можно ${grp(hint.moved)}` + (hint.unplaced ? `, ещё ${grp(hint.unplaced)} — некому` : '')
      : hint.shortfall ? `недобор ${grp(hint.shortfall)}, но запаса у площадок в темпе нет` : 'площадок, упёршихся в сеть, нет'
  return (
    <Modal width={620} onClose={onClose}
      title={<span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>Темп размещения</span>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>{row.deal_code}</span></span>}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '6px 0 8px' }}>
        <button type="button" style={card} onClick={() => setMode('boost')}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>Поднять темп</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Остаток запущенных площадок выше на X % на N дней — когда трафик
            есть, а площадки откручивают меньше нужного.</span>
          {!!hint?.has_manual && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>площадки с ручным планом не поднимаются</span>}
        </button>
        <button type="button" style={card} onClick={() => setMode('realloc')}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>Перераспределить</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Недобор площадок, которым сеть не даёт трафика, — площадкам
            в темпе с запасом предложения. Сумма планов та же.</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: hint?.moved ? 'var(--income-fg)' : 'var(--text-muted)' }}>{reallocNote}</span>
        </button>
      </div>
    </Modal>
  )
}
