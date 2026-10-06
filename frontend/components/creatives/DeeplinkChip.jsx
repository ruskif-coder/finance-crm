// Ссылка В ПРИЛОЖЕНИИ пары «креатив × площадка» — у каждой app-площадки (владелец
// 06.10.2026; до того — диплинк режима «обе», 29.09.2026). Своя схема площадки
// (storefront://… у kuper), диплинк SDK (deeplink+://…) или та же https, что веб-ссылка.
// Веб-ссылка — отдельно, она уходит в ОРД и в DSP. В код баннера ссылка встаёт, только
// если в ней кликовый макрос DSP. Пустой чип красный: без неё запрос ссылки не закрыт.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover } from '@/components/salesTableKit'
import { APP_LINK_FORMATS } from '@/lib/appLinkFormats'

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
        title={has ? `Ссылка в приложении: ${r.deeplink_url}` : 'Нужна ссылка в приложении — можно ту же, что веб-ссылка'}
        style={{ cursor: canEdit ? 'pointer' : 'default', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 9.5,
          fontWeight: 700, padding: '3px 6px', borderRadius: 7,
          border: `1px solid ${has ? 'var(--income-border)' : 'var(--danger-border)'}`,
          background: has ? 'var(--income-tint)' : 'var(--danger-tint)',
          color: has ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
        {has ? 'прил. ✓' : 'ссылка в прил.'}
      </span>
      <PortalPopover open={open} minWidth={340} align="right">
        <div style={{ padding: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Ссылка в приложении — в одном из форматов (веб-ссылка — отдельно, она уходит в ОРД и DSP):
            {APP_LINK_FORMATS.map(([what, ex]) => (
              <div key={what} style={{ marginTop: 3 }}>· {what}: <span style={{ fontFamily: MONO,
                fontSize: 11, wordBreak: 'break-all' }}>{ex}</span></div>
            ))}</div>
          <input autoFocus value={val} placeholder="storefront://…, deeplink+://… или https://…"
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
