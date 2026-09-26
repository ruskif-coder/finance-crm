/**
 * Нижний лист мобильного кабинета (хендофф «моб версия кп», п. 5): затемнение подложки,
 * ручка, заголовок с крестом, прокрутка внутри, кнопки в подвале. Закрывается по фону,
 * кресту и кнопке.
 *
 * Порталом в `body` — по той же причине, что и окно предпросмотра: карточка с анимацией
 * создаёт свой стек, и `position: fixed` внутри неё уехал бы под соседние блоки.
 */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { overlayClose } from './overlay'
import { C, CAP, UI } from './ui'

export const SHEET_BTN = { minHeight: 44, borderRadius: 11, fontSize: 14, padding: '0 16px' }

export default function Sheet({ title, meta, onClose, footer, children }) {
  const [ready, setReady] = useState(false)
  useEffect(() => { setReady(true) }, [])
  // Под открытым листом страница не должна прокручиваться пальцем вместе с ним.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])
  if (!ready) return null

  return createPortal(
    <div style={{ position: 'fixed', inset: 0, background: 'var(--overlay)', zIndex: 10000,
      display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}
      {...overlayClose(onClose)}>
      <div role="dialog" aria-label={title}
        style={{ background: C.card, width: '100%', maxWidth: 640, maxHeight: '90vh',
          borderRadius: '18px 18px 0 0', display: 'flex', flexDirection: 'column',
          fontFamily: UI, boxShadow: 'var(--shadow-float)' }}>
        <div style={{ padding: '8px 16px 10px', borderBottom: `1px solid ${C.row}` }}>
          <div style={{ width: 38, height: 4, borderRadius: 4, background: C.inner,
            margin: '0 auto 10px' }} />
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 800 }}>{title}</div>
              {!!meta && <div style={{ ...CAP, marginBottom: 0, marginTop: 3,
                textTransform: 'none', fontSize: 11 }}>{meta}</div>}
            </div>
            <button onClick={onClose} aria-label="Закрыть"
              style={{ width: 40, height: 40, flex: '0 0 40px', borderRadius: 10,
                border: `1px solid ${C.border}`, background: C.card, color: C.secondary,
                fontSize: 17, cursor: 'pointer', lineHeight: 1 }}>×</button>
          </div>
        </div>
        <div style={{ padding: '14px 16px', overflowY: 'auto', flex: 1,
          WebkitOverflowScrolling: 'touch' }}>
          {children}
        </div>
        {!!footer && (
          <div style={{ padding: '10px 16px calc(12px + env(safe-area-inset-bottom))',
            borderTop: `1px solid ${C.row}`, display: 'flex', gap: 8 }}>
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body)
}
