/**
 * Сделки на брони, у которых ячейка годового плана изменилась (владелец 14.11.2026: «бронь не трогаем и дальше — с
 * уведомлением: переписать или нет»). Конвейер их не переписывает; решение здесь, в окне конвейера, у того, кто его запустил:
 * «Переписать из плана» — та же пересборка, что у конвейера, только этой сделки (`/create-deals/rewrite`); «Оставить» — убрать
 * из списка. Сервер решает, можно ли (бронь, месяц не под замком), и говорит причину отказа.
 */
import { useState } from 'react'
import { detailText } from '@/lib/loadError'
import { grp0 } from '@/lib/salesFormat'
import { MONO } from '@/components/salesTableKit'

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const BTN = { padding: '4px 10px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap', border: '1px solid var(--border-card)' }

export default function BookingDiverged({ items, onRewrite }) {
  const [st, setSt] = useState({})
  const shown = items.filter(c => st[c.deal_id] !== 'kept')
  if (!shown.length) return null
  const rewrite = async (c) => {
    setSt(s => ({ ...s, [c.deal_id]: 'busy' }))
    try {
      const r = await onRewrite(c.deal_id)
      setSt(s => ({ ...s, [c.deal_id]: r?.rewritten === false ? (r.message || 'уже совпадает с планом') : 'done' }))
    } catch (e) {
      setSt(s => ({ ...s, [c.deal_id]: { err: detailText(e, 'Не удалось переписать') } }))
    }
  }
  return (
    <div style={{ border: '1px solid var(--warning)', background: 'var(--warning-bg)', borderRadius: 10, padding: '10px 12px', maxHeight: 240, overflowY: 'auto' }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--warning-fg)' }}>
        Сделки на брони — план изменился. Конвейер их не трогает; переписать из плана?
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
        {shown.map(c => {
          const s = st[c.deal_id]
          return (
            <div key={c.deal_id} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)', flex: '1 1 220px' }}>
                {c.code ? `${c.code} · ` : ''}{c.brand} · {MONTHS[c.month]}: <span style={{ color: 'var(--text-faint)' }}>{grp0(c.old_amount)}</span> → <b style={{ color: 'var(--text-primary)' }}>{grp0(c.amount)}</b> ₽
              </span>
              {s === 'done' && <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--income-fg)' }}>переписано</span>}
              {typeof s === 'string' && !['done', 'busy', 'kept'].includes(s) && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{s}</span>}
              {s?.err && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>{s.err}</span>}
              {(!s || s?.err) && <>
                <span onClick={() => rewrite(c)} style={{ ...BTN, background: 'var(--accent)', color: 'var(--bg-card)', borderColor: 'var(--accent)' }}>Переписать из плана</span>
                <span onClick={() => setSt(x => ({ ...x, [c.deal_id]: 'kept' }))} style={{ ...BTN, background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>Оставить</span>
              </>}
              {s === 'busy' && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>переписываем…</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
