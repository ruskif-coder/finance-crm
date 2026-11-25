/**
 * Дата ДС в шапке пункта 1 (владелец 14.10.2026): по умолчанию — начало РК, аккаунт ставит другую через календарь.
 * Смена — только после «Уверены?»; сервер пишет в журнал, какая дата была и какая стала.
 *
 * Дата не может быть позже начала РК (владелец 25.11.2026): проверка стоит и здесь, и на сервере — здесь, чтобы
 * человек увидел причину сразу в календаре, на сервере, чтобы правило держалось для любого входа (подтверждение,
 * «подписан вне системы», прямой вызов ручки).
 */
import { useState } from 'react'
import { Modal, btn, primaryBtn, inp, MONO } from '@/components/salesTableKit'
import { fmtDate } from '@/lib/dates'
import { detailText } from '@/lib/loadError'

export default function AnnexDateField({ value, periodFrom, rkStart, canEdit, onSave }) {
  const [next, setNext] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const iso = value ? String(value).slice(0, 10) : ''
  const rk = rkStart ? String(rkStart).slice(0, 10) : ''
  const isDefault = !!periodFrom && iso === String(periodFrom).slice(0, 10)
  const tooLate = !!next && !!rk && next > rk

  const apply = async () => {
    if (tooLate) { setErr(`Дата позже начала РК (${fmtDate(rk)}) — так нельзя`); return }
    setBusy(true); setErr('')
    try { await onSave(next); setNext(null) } catch (e) { setErr(detailText(e, 'Не удалось сменить дату')) }
    finally { setBusy(false) }
  }

  return (
    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Дата ДС</span>
      <input type="date" value={iso} disabled={!canEdit} max={rk || undefined}
             onChange={e => { if (e.target.value && e.target.value !== iso) { setErr(''); setNext(e.target.value) } }}
             title={rk ? `Не позже начала РК — ${fmtDate(rk)}` : (isDefault ? 'По умолчанию — начало РК' : 'Дата изменена вручную')}
             style={{ ...inp, height: 30, width: 150, fontFamily: MONO, fontSize: 12.5 }} />
      {isDefault && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>начало РК</span>}
      {next && (
        <Modal title="Сменить дату ДС?" width={440} onClose={() => !busy && setNext(null)}
               footer={<>
                 <button type="button" style={btn(false)} disabled={busy} onClick={() => setNext(null)}>Отмена</button>
                 <button type="button" style={primaryBtn} disabled={busy || tooLate} onClick={apply}>{busy ? 'Меняю…' : 'Да, уверен'}</button>
               </>}>
          <div style={{ fontSize: 13.5, lineHeight: 1.6 }}>
            Дата ДС: <b>{fmtDate(iso) || 'без даты'}</b> → <b>{fmtDate(next)}</b>.<br />
            Изменение попадёт в журнал действий.
          </div>
          {tooLate && <div style={{ marginTop: 8, fontSize: 12.5, lineHeight: 1.5, color: 'var(--warning-fg)' }}>
            Позже начала РК ({fmtDate(rk)}) дату ставить нельзя: ДС закрывает размещение, которое начинается {fmtDate(rk)}.
          </div>}
          {!!err && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
        </Modal>
      )}
    </span>
  )
}
