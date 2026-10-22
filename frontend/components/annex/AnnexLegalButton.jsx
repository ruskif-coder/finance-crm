/**
 * «Отправить юристу» в шапке «Документа по шаблону» (владелец 14.10.2026): кнопка открывает окно заявки и истории заявок этого ДС.
 * Пункты после таблицы МП правит только юрист; правка ложится в шаблон ДС договора. Пока заявка открыта, ДС нельзя подтвердить и выгрузить чистовик.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { fmtDateTime } from '@/lib/dates'
import { Modal, btn, primaryBtn, sel, inp, MONO } from '@/components/salesTableKit'

const OPEN = ['открыта', 'в работе']

export default function AnnexLegalButton({ annexId, lawBlocks, canEdit, onChange }) {
  const [rows, setRows] = useState([])
  const [show, setShow] = useState(false)
  const [blockId, setBlockId] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try { setRows((await api.get(`/legal-requests/annex/${annexId}`, auth())).data) } catch (_) { setRows([]) }
  }, [annexId])
  useEffect(() => { load() }, [load])

  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.post('/legal-requests', { annex_id: annexId, block_id: blockId || null, text }, auth())
      setText(''); setBlockId(''); setShow(false); await load(); if (onChange) onChange()
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось отправить заявку') }
    finally { setBusy(false) }
  }

  const open = rows.filter(r => OPEN.includes(r.status)).length
  if (!canEdit && !rows.length) return null
  return (
    <>
      <span onClick={() => setShow(true)}
            title={open ? `Открыто заявок юристу: ${open} — подтверждение и чистовик ждут ответа` : 'Попросить юриста поправить пункт после таблицы медиаплана'}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 9, border: `1px solid ${open ? 'var(--danger-fg)' : 'var(--border-card)'}`,
                     background: open ? 'var(--danger-tint)' : 'var(--bg-card)', color: open ? 'var(--danger-fg)' : 'var(--text-secondary)', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>
        {open ? `У юриста: ${open}` : 'Отправить юристу'}
      </span>
      {show && (
        <Modal title="Запрос юристу" width={560} onClose={() => !busy && setShow(false)}
               footer={canEdit ? <>
                 <button type="button" style={btn(false)} disabled={busy} onClick={() => setShow(false)}>Закрыть</button>
                 <button type="button" style={text.trim() ? primaryBtn : { ...btn(false), cursor: 'not-allowed' }} disabled={busy || !text.trim()} onClick={send}>
                   {busy ? 'Отправляю…' : 'Отправить юристу'}</button>
               </> : null}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {canEdit && <>
              <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Юрист внесёт правку в шаблон ДС этого договора — она коснётся и следующих ДС. Пока заявка открыта, подтверждение и чистовик недоступны.
              </div>
              <select value={blockId} onChange={e => setBlockId(e.target.value)} style={sel}>
                <option value="">Новый пункт (добавить)</option>
                {lawBlocks.map(b => <option key={b.id} value={b.id}>Пункт {b.num} {b.title || ''}</option>)}
              </select>
              <textarea value={text} onChange={e => setText(e.target.value)} rows={4} placeholder="Что поправить и почему"
                        style={{ ...inp, width: '100%', resize: 'vertical' }} />
              {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
            </>}
            {rows.map(r => (
              <div key={r.id} style={{ padding: '8px 12px', background: 'var(--bg-subtle)', borderRadius: 10, fontSize: 13, lineHeight: 1.5 }}>
                <b>{r.status}</b> · {r.block} · <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{fmtDateTime(r.created_at)} {r.created_by || ''}</span>
                <div style={{ whiteSpace: 'pre-wrap' }}>{r.text}</div>
                {!!r.answer && <div style={{ color: 'var(--text-secondary)' }}>Юрист: {r.answer}</div>}
              </div>
            ))}
          </div>
        </Modal>
      )}
    </>
  )
}
