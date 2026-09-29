// Диплинк пары «креатив × площадка» — для app-площадок с режимом ссылок «обе»
// (владелец 29.09.2026). Встаёт в <a href> креатива; веб-посадочная уходит в DSP как
// url и домен. Пока он не вписан, пара трафику не уходит — поэтому пустой чип красный.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover } from '@/components/salesTableKit'

export default function DeeplinkChip({ r, setId, canEdit, onSave }) {
  const [open, setOpen] = useState(false)
  const [val, setVal] = useState(r.deeplink_url || '')
  const [err, setErr] = useState('')
  useEffect(() => { setVal(r.deeplink_url || '') }, [r.deeplink_url])
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  if (!r.needs_deeplink) return null
  const has = !!r.deeplink_url
  const save = async () => {
    const why = await onSave(r, val.trim(), setId)
    if (why) setErr(why); else { setErr(''); setOpen(false) }
  }
  return (
    <span data-pop-root style={{ position: 'relative', flex: '0 0 auto' }}>
      <span onClick={e => { e.stopPropagation(); if (canEdit) setOpen(o => !o) }}
        title={has ? `Диплинк: ${r.deeplink_url}` : 'Площадка требует диплинк — без него пара не уйдёт трафику'}
        style={{ cursor: canEdit ? 'pointer' : 'default', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 9.5,
          fontWeight: 700, padding: '3px 6px', borderRadius: 7,
          border: `1px solid ${has ? 'var(--income-border)' : 'var(--danger-border)'}`,
          background: has ? 'var(--income-tint)' : 'var(--danger-tint)',
          color: has ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
        {has ? 'DL ✓' : 'нужен диплинк'}
      </span>
      <PortalPopover open={open} minWidth={340} align="right">
        <div style={{ padding: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Диплинк встанет в код креатива; веб-посадочная уйдёт в DSP как url и домен.</div>
          <input autoFocus value={val} placeholder="app://… или https://…"
            onChange={e => { setVal(e.target.value); if (err) setErr('') }}
            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setOpen(false) }}
            style={{ height: 30, padding: '0 9px', border: '1px solid var(--border-card)', borderRadius: 8,
              fontFamily: MONO, fontSize: 11.5, outline: 'none' }} />
          {!!err && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>{err}</span>}
          <span style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            {has && <button type="button" onClick={() => { setVal(''); onSave(r, '', setId).then(w => { if (!w) setOpen(false) }) }}
              style={{ height: 28, padding: '0 10px', borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 12 }}>Снять</button>}
            <button type="button" onClick={save}
              style={{ height: 28, padding: '0 12px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', cursor: 'pointer', fontSize: 12, fontWeight: 700 }}>Сохранить</button>
          </span>
        </div>
      </PortalPopover>
    </span>
  )
}
