/**
 * Подтверждение шага мастер-сделки — поповер от кнопки, у низа окна раскрывается вверх. Общий для строки реестра и карточки.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { PortalPopover, MONO, UI } from '@/components/salesTableKit'

const CAPS = { fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }

export default function StepConfirm({ code, step, onClose, onDone }) {
  const [track, setTrack] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async () => {
    if (busy) return
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/master-deals/${code}/${step.url}`, step.body || (step.track ? { track_no: track } : {}), auth())
      onDone(r.data)
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось отметить') } finally { setBusy(false) }
  }
  return (
    <PortalPopover open minWidth={300} maxHeight={260} offset={6} flip style={{ width: 300, padding: 14, gap: 10, borderRadius: 14, boxShadow: 'var(--shadow-float)' }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)' }}>{code}</span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{step.title}</span>
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{step.text}</span>
      {step.track && (
        <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={CAPS}>Трек-номер · необязательно</span>
          <input value={track} onChange={e => setTrack(e.target.value)} placeholder="RA123456789RU"
            style={{ height: 34, boxSizing: 'border-box', padding: '0 10px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 12, outline: 'none', color: 'var(--text-primary)' }} />
        </span>
      )}
      {!!err && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)', lineHeight: 1.4 }}>{err}</span>}
      <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 2 }}>
        <button type="button" onClick={onClose} style={{ height: 32, padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: UI }}>Отмена</button>
        <button type="button" onClick={run} disabled={busy}
          style={{ height: 32, padding: '0 14px', background: 'var(--accent)', opacity: busy ? 0.45 : 1, color: 'var(--on-accent)', border: 0, borderRadius: 9, fontSize: 12, fontWeight: 700, cursor: busy ? 'not-allowed' : 'pointer', fontFamily: UI }}>
          {busy ? '…' : step.run || 'Отметить'}</button>
      </span>
    </PortalPopover>
  )
}
