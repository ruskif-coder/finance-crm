/**
 * Модалка сделки режима «Карточки» «Моих сделок» (экран 12 хендоффа v5): шапка — код, услуга, бренд, сумма и период, ↑ ↓ ×;
 * тело — `DealNow` в раскладке `modal` (то же содержимое, что расхлоп строки). ↑ ↓ и стрелки клавиатуры листают сделки текущего
 * списка, Esc закрывает.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, Z } from '@/components/salesTableKit'
import { CopyIcon } from '@/components/CopyCode'
import { dm } from '@/lib/salesFormat'
import { overlayClose } from '@/lib/overlay'
import { mln } from '@/components/accounts/dashboard/ladder'
import DealNow from '@/components/accounts/deals/DealNow'

const NAV = { width: 30, height: 30, borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13 }

export default function DealModal({ rows, row, canEdit, onClose, onMove, onAction, onSnooze, onReload }) {
  const [deal, setDeal] = useState(null)
  const i = rows.findIndex(x => x.id === row.id)
  useEffect(() => {
    let alive = true
    setDeal(null)
    api.get(`/sales/deals/${row.code || row.id}`, auth()).then(r => alive && setDeal(r.data)).catch(() => {})
    return () => { alive = false }
  }, [row.id, row.code])
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.target?.closest?.('input, textarea, select')) return
      if (e.key === 'ArrowDown' && i < rows.length - 1) { e.preventDefault(); onMove(rows[i + 1]) }
      if (e.key === 'ArrowUp' && i > 0) { e.preventDefault(); onMove(rows[i - 1]) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [i, rows, onClose, onMove])

  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '6vh 16px', overflowY: 'auto' }}>
      <div style={{ width: 'min(1040px, 100%)', background: 'var(--bg-card)', borderRadius: 16, border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-modal)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 18px', borderBottom: '1px solid var(--border-inner)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent-fg)' }}>{row.code}</span>
            <CopyIcon text={row.code} size={13} title="Скопировать код сделки" />
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, fontWeight: 600 }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: row.product_color || 'var(--accent)' }} />{row.product || '—'}
            {!!row.inventory && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', textTransform: 'uppercase' }}>{row.inventory}</span>}
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <b style={{ fontSize: 16 }}>{row.brand || row.title || '—'}</b>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{row.advertiser || '—'}{row.agency ? <> · агентство <b style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{row.agency}</b></> : ''}</span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <b style={{ fontFamily: MONO, fontSize: 15 }}>{mln(row.amount)}</b>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{row.period_from ? `${dm(row.period_from)}–${dm(row.period_to)}` : ''}</span>
          </span>
          <span style={{ display: 'inline-flex', gap: 6 }}>
            <button type="button" disabled={i <= 0} onClick={() => onMove(rows[i - 1])} title="Предыдущая сделка" style={{ ...NAV, opacity: i <= 0 ? 0.4 : 1 }}>↑</button>
            <button type="button" disabled={i >= rows.length - 1} onClick={() => onMove(rows[i + 1])} title="Следующая сделка" style={{ ...NAV, opacity: i >= rows.length - 1 ? 0.4 : 1 }}>↓</button>
            <button type="button" onClick={onClose} title="Закрыть" style={NAV}>×</button>
          </span>
        </div>
        <DealNow row={row} deal={deal} canEdit={canEdit} onAction={onAction} onSnooze={onSnooze} onReload={onReload} layout="modal" />
      </div>
    </div>
  )
}
