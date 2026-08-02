import { useState } from 'react'
import { UI, MONO } from '../salesTableKit'
import BottomSheet from './BottomSheet'

// Селект мобильного слоя (§6): поле открывает вложенный bottom sheet со строкой
// поиска и списком строк ≥ 44px. Замена ValuePopover/SingleSelect на мобиле.
export default function SheetSelect({ value, onChange, options, placeholder = 'Выбрать', label, emptyLabel = '— не выбрано —' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const sel = options.find(o => String(o.value) === String(value))
  const f = q.trim().toLowerCase()
  const shown = options.filter(o => !f || String(o.label).toLowerCase().includes(f)).slice(0, 400)

  const field = {
    width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12,
    padding: '11px 12px', minHeight: 44, fontSize: 14, background: 'var(--bg-card)', fontFamily: UI,
    color: sel ? 'var(--text-primary)' : 'var(--text-faint)', display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 8, cursor: 'pointer',
  }
  const row = (active) => ({
    padding: '12px 10px', minHeight: 44, boxSizing: 'border-box', borderRadius: 8, cursor: 'pointer',
    fontSize: 14, display: 'flex', alignItems: 'center',
    background: active ? 'var(--accent-tint)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-primary)',
    borderBottom: '1px solid var(--border-row)',
  })

  return (
    <>
      <div onClick={() => setOpen(true)} style={field}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sel ? sel.label : placeholder}</span>
        <span style={{ color: 'var(--text-faint)', flexShrink: 0 }}>▾</span>
      </div>
      <BottomSheet open={open} onClose={() => { setOpen(false); setQ('') }} title={label || 'Выбор'}>
        <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
          style={{ width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', fontSize: 14, fontFamily: UI, outline: 'none', marginBottom: 8 }} />
        <div>
          <div onClick={() => { onChange(''); setOpen(false); setQ('') }} style={{ ...row(false), color: 'var(--text-muted)' }}>{emptyLabel}</div>
          {shown.map(o => (
            <div key={o.value} onClick={() => { onChange(o.value); setOpen(false); setQ('') }} style={row(String(o.value) === String(value))}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
            </div>
          ))}
          {!shown.length && <div style={{ padding: 14, fontSize: 13, color: 'var(--text-muted)', fontFamily: MONO }}>ничего не найдено</div>}
        </div>
      </BottomSheet>
    </>
  )
}
