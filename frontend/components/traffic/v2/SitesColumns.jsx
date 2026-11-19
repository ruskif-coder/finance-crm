// Шестерёнка «Колонки» панели площадок (просьба трафиков, 19.11.2026): какие колонки между «Площадкой» и «Статусом»
// показывать и в каком порядке. Настройка — личная, хранится на сервере (`useUiPref`), расчёт — lib/sitesColumns.mjs.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover, Z } from '@/components/salesTableKit'
import { moveCol, orderOf, toggleCol } from '@/lib/sitesColumns.mjs'
import { COLS } from './SiteRow'
import { TOOL } from './SitesToolbar'

const LABEL = Object.fromEntries(COLS.map(c => [c[0], c[1]]))
const ARROW = { fontFamily: MONO, width: 22, height: 22, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 6, border: '1px solid var(--border-inner)', background: 'var(--bg-card)', color: 'var(--text-secondary)',
  fontSize: 10, cursor: 'pointer', padding: 0 }

export default function SitesColumns({ pref, onChange }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('click', off)
    return () => document.removeEventListener('click', off)
  }, [open])
  const order = orderOf(pref)
  const hidden = new Set(pref?.hidden || [])
  const custom = !!pref && (pref.hidden?.length > 0 || order.join() !== orderOf(null).join())
  return (
    <span data-pop-root style={{ position: 'relative', display: 'inline-flex' }}>
      <button type="button" onClick={() => setOpen(o => !o)} title="Колонки таблицы: какие показывать и в каком порядке — настройка ваша"
        style={{ ...TOOL, padding: '0 7px', ...(custom ? { color: 'var(--accent-fg)', borderColor: 'var(--accent)' } : null) }}>⚙</button>
      <PortalPopover open={open} minWidth={240} maxHeight={460} align="right" flip style={{ padding: 10, zIndex: Z.dropdown }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 4px 6px' }}>Колонки между «Площадкой» и «Статусом»</span>
          {order.map((k, i) => (
            <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 4px', borderRadius: 6 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, cursor: 'pointer', fontSize: 12.5,
                color: hidden.has(k) ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                <input type="checkbox" checked={!hidden.has(k)} onChange={() => onChange(toggleCol(pref, k))} />
                {LABEL[k]}
              </label>
              <button type="button" style={{ ...ARROW, opacity: i ? 1 : 0.3 }} disabled={!i} title="Левее"
                onClick={() => onChange(moveCol(pref, k, -1))}>▲</button>
              <button type="button" style={{ ...ARROW, opacity: i < order.length - 1 ? 1 : 0.3 }} disabled={i === order.length - 1}
                title="Правее" onClick={() => onChange(moveCol(pref, k, 1))}>▼</button>
            </span>
          ))}
          <button type="button" disabled={!custom} onClick={() => onChange({ order: orderOf(null), hidden: [] })}
            style={{ ...TOOL, marginTop: 8, justifyContent: 'center', opacity: custom ? 1 : 0.5 }}>Как было</button>
        </span>
      </PortalPopover>
    </span>
  )
}
