/**
 * Бар статусов с бегунком: маркер и счётчик у каждого пункта, подложка переезжает к выбранному.
 * Часть реестра мастер-сделок (`pages/finance/master-deals.js`), вынесено при аудите 20.10.2026.
 */
import { useLayoutEffect, useRef, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { statusDot } from '@/lib/masterStatus'
import { KEEP } from '@/components/master/registry/kit'

export default function StatusBar({ tabs, value, onPick }) {
  const box = useRef(null)
  const [pos, setPos] = useState(null)
  useLayoutEffect(() => {
    const el = box.current && box.current.querySelector(`[data-tab="${value}"]`)
    setPos(el ? { left: el.offsetLeft, width: el.offsetWidth } : null)
  }, [value, tabs])
  return (
    <span ref={box} style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', padding: 3, height: 36, boxSizing: 'border-box', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
      {pos && <span aria-hidden style={{ position: 'absolute', top: 3, bottom: 3, left: pos.left, width: pos.width, background: 'var(--accent-tint)', borderRadius: 8,
        transition: 'left 320ms cubic-bezier(0.22,1,0.36,1), width 320ms cubic-bezier(0.22,1,0.36,1)' }} />}
      {tabs.map(t => {
        const on = value === t.key
        return (
          <span key={t.key} data-tab={t.key} onClick={() => onPick(t.key)}
            style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 12px', borderRadius: 8,
              color: on ? 'var(--accent-fg)' : t.count ? 'var(--text-secondary)' : 'var(--text-disabled)', fontSize: 12.5, fontWeight: on ? 700 : 600,
              whiteSpace: 'nowrap', cursor: 'pointer', transition: 'color 200ms ease' }}>
            {t.key !== KEEP && <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: statusDot(t.key) }} />}
            {t.key}
            <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: on ? 'var(--accent)' : 'var(--text-faint)' }}>{t.count}</span>
          </span>
        )
      })}
    </span>
  )
}
