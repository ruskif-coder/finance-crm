/**
 * Бонусный трафик — особенность РК в «Доп. параметрах РК» (владелец 15.10.2026): одно из трёх — % от плана, показы или сумма
 * без НДС (`PUT /final-recon/deal/{id}/bonus-traffic`). В МП не пишется; на «Итоговой сверке» по нему считается вывод.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, UI, inp } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'

const MODES = [['pct', '%'], ['qty', 'показы'], ['rub', '₽']]
const SHOW = { pct: (v) => `${v} % от плана`, qty: (v) => `${grp(v)} показов`, rub: (v) => `${grp(v)} ₽ без НДС` }

export default function BonusTraffic({ dealId, mode, value, canEdit, onSaved }) {
  const [edit, setEdit] = useState(false)
  const [m, setM] = useState(mode || 'pct')
  const [v, setV] = useState(value != null ? String(value) : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const save = async (clear) => {
    setBusy(true); setErr('')
    const n = parseFloat(String(v).replace(/\s/g, '').replace(',', '.'))
    try {
      await api.put(`/final-recon/deal/${dealId}/bonus-traffic`, clear ? { mode: null, value: null } : { mode: m, value: n }, auth())
      setEdit(false); onSaved()
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 10, borderTop: '1px solid var(--border-row)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, flexWrap: 'wrap' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Бонусный трафик</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
            {mode ? `Заказан: ${SHOW[mode](value)}. На итоговой сверке вывод учтёт, отдан ли бонус.`
              : 'Не заказан. Всё сверх плана на сверке считается перекрутом.'}</span>
        </span>
        {canEdit && !edit && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
            {!!mode && <button type="button" disabled={busy} onClick={() => save(true)}
              style={{ height: 32, padding: '0 14px', borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                color: 'var(--danger-fg)', fontSize: 12.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>Снять</button>}
            <button type="button" onClick={() => setEdit(true)}
              style={{ height: 32, padding: '0 14px', borderRadius: 9, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)',
                fontSize: 12.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>{mode ? 'Изменить' : 'Указать'}</button>
          </span>
        )}
      </div>
      {edit && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', border: '1px solid var(--border-card)', borderRadius: 9, overflow: 'hidden' }}>
            {MODES.map(([k, l]) => (
              <button key={k} type="button" onClick={() => setM(k)}
                style={{ border: 0, padding: '6px 12px', fontFamily: UI, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  background: m === k ? 'var(--accent)' : 'var(--bg-card)', color: m === k ? 'var(--bg-card)' : 'var(--text-secondary)' }}>{l}</button>
            ))}
          </span>
          <input value={v} onChange={e => setV(e.target.value)} placeholder={m === 'pct' ? '10' : m === 'qty' ? '200 000' : '80 000'}
            style={{ ...inp, width: 140, fontFamily: MONO, textAlign: 'right' }} />
          <button type="button" disabled={busy} onClick={() => save(false)}
            style={{ height: 34, padding: '0 14px', borderRadius: 9, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)',
              fontSize: 12.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>{busy ? '…' : 'Сохранить'}</button>
          <button type="button" onClick={() => setEdit(false)}
            style={{ height: 34, padding: '0 12px', borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
              color: 'var(--text-secondary)', fontSize: 12.5, fontFamily: UI, cursor: 'pointer' }}>Отмена</button>
        </div>
      )}
      {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
    </div>
  )
}
