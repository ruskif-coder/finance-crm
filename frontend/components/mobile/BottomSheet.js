import { useEffect, useRef, useState } from 'react'
import { UI } from '../salesTableKit'

// Bottom sheet (§6 хендоффа): формы/списки открываются снизу на всю ширину.
// Ручка-полоска, подложка, свайп-вниз для закрытия, Esc, блокировка скролла body.
// Переиспользуется всеми формами и вложенными селектами мобильного слоя.
export default function BottomSheet({ open, onClose, title, children, footer, maxHeight = '90vh' }) {
  const [drag, setDrag] = useState(0)
  const startY = useRef(null)

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose() }
    document.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', onKey) }
  }, [open, onClose])

  if (!open) return null

  const onTouchStart = (e) => { startY.current = e.touches[0].clientY }
  const onTouchMove = (e) => {
    if (startY.current == null) return
    const d = e.touches[0].clientY - startY.current
    if (d > 0) setDrag(d)                       // тянем только вниз
  }
  const onTouchEnd = () => {
    if (drag > 90 && onClose) onClose()          // свайп вниз > 90px — закрыть
    setDrag(0); startY.current = null
  }

  return (
    <div onClick={onClose} role="dialog" aria-modal="true"
      style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(28,36,51,.35)',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center', animation: 'sheetFade .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
        style={{ width: '100%', maxWidth: 540, margin: '0 auto', maxHeight, overflowY: 'auto', background: 'var(--bg-card)',
          borderRadius: '18px 18px 0 0', padding: '10px 14px 20px', fontFamily: UI,
          transform: drag ? `translateY(${drag}px)` : undefined,
          transition: drag ? 'none' : 'transform .2s',
          animation: drag ? undefined : 'sheetUp .28s cubic-bezier(0.22,1,0.36,1) both' }}>
        {/* ручка + свайп-зона */}
        <div style={{ padding: '4px 0 10px', cursor: 'grab' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--border-card)', margin: '0 auto' }} />
        </div>
        {title && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{title}</span>
            <span onClick={onClose} aria-label="Закрыть" style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1, padding: 4 }}>✕</span>
          </div>
        )}
        {children}
        {footer && <div style={{ marginTop: 14 }}>{footer}</div>}
      </div>
    </div>
  )
}
