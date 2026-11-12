/**
 * «Вернуть стадию» (владелец 12.11.2026): штатный возврат пакета назад с причиной — по праву «Мастер-сделки · возврат стадии».
 * Куда можно — сервер (`revert_targets` карточки), что при этом сбрасывается — `REVERT_NOTE`. Бухгалтеру и аккаунту уходит
 * уведомление почтой и в телеграм.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { can, getPermissions } from '@/lib/auth'
import { REVERT_NOTE } from '@/lib/masterNext'
import { Modal, UI } from '@/components/salesTableKit'
import { lineBtn } from '@/components/master/kit'

export default function RevertStage({ m, onDone }) {
  const [may, setMay] = useState(false)
  const [open, setOpen] = useState(false)
  const [to, setTo] = useState(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // сервер требует и правку мастер-сделок, и право возврата (ревью 12.11.2026: иначе кнопка вела бы к 403)
  useEffect(() => { const p = getPermissions(); setMay(can(p, 'master_deals_revert', 'edit') && can(p, 'master_deals', 'edit')) }, [])
  const targets = [...(m.revert_targets || [])].reverse()          // ближайшая стадия — первой
  if (!may || !targets.length) return null
  const start = () => { setTo(targets[0]); setReason(''); setErr(''); setOpen(true) }
  const send = async () => {
    setBusy(true); setErr('')
    try { onDone((await api.post(`/master-deals/${m.code}/back`, { to, reason: reason.trim() }, auth())).data); setOpen(false) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось вернуть') } finally { setBusy(false) }
  }
  const btn = lineBtn({ tone: 'secondary', size: 'sm', busy })
  return (
    <>
      <button type="button" style={btn} onClick={start} title="Вернуть пакет на более раннюю стадию — с причиной">← Вернуть стадию</button>
      {open && (
        <Modal title={`Вернуть ${m.code} на стадию`} width={560} onClose={() => setOpen(false)}
          footer={<>
            {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)', marginRight: 'auto' }}>{err}</span>}
            <button type="button" style={{ ...btn, marginLeft: err ? 0 : 'auto' }} onClick={() => setOpen(false)}>Отмена</button>
            <button type="button" disabled={busy || !reason.trim()} onClick={send}
              style={{ ...btn, border: 0, background: 'var(--accent)', color: 'var(--on-accent)', opacity: reason.trim() ? 1 : 0.5 }}>Вернуть в «{to}»</button>
          </>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontFamily: UI }}>
            {targets.map(t => {
              const on = t === to
              return (
                <label key={t} style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 10, cursor: 'pointer',
                  border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`, background: on ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
                  <input type="radio" name="revert-to" checked={on} onChange={() => setTo(t)} style={{ marginTop: 3 }} />
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <b style={{ fontSize: 13, color: on ? 'var(--accent-fg)' : 'var(--text-primary)' }}>«{t}»</b>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{REVERT_NOTE[t] || ''}</span>
                  </span>
                </label>
              )
            })}
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} maxLength={500}
              placeholder="Причина — что переделываем (уйдёт бухгалтеру и аккаунту)"
              style={{ marginTop: 4, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-card)', fontFamily: UI, fontSize: 13, resize: 'vertical' }} />
          </div>
        </Modal>
      )}
    </>
  )
}
