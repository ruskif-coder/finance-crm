/**
 * Выпадашка, которую НИЧТО не обрежет.
 *
 * Рисуется порталом в `body` и позиционируется `fixed` от прямоугольника триггера.
 * Обычный `position: absolute` внутри карточки уезжает под соседей и режется
 * `overflow` — это случилось 15.09.2026 с выбором периода на экране «Кампании» и до
 * того много раз в финмодуле; там ровно поэтому живёт `PortalPopover` в общем ките.
 *
 * ЗАКРЫТИЕ — ПО `mousedown`, а не по `click`. Клик рождается на ОБЩЕМ ПРЕДКЕ mousedown
 * и mouseup: выделил текст внутри панели, отпустил снаружи — и панель закрылась бы
 * посреди работы. Та же ловушка, что описана в `lib/overlay.js`.
 *
 * Положение считается при открытии и на прокрутке/ресайзе: панель, приклеенная к
 * координатам момента открытия, уезжает от кнопки при первом же скролле.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { C, card } from './ui'

export function Pop({ open, anchor, onClose, width = 250, children }) {
  const [pos, setPos] = useState(null)
  const box = useRef(null)

  useLayoutEffect(() => {
    if (!open || !anchor?.current) return undefined
    const place = () => {
      const r = anchor.current.getBoundingClientRect()
      // Держим панель в пределах окна: у правого края она иначе уходит за экран, а
      // горизонтальной прокрутки у страницы нет — уехавшее просто недоступно.
      setPos({
        top: Math.min(r.bottom + 6, window.innerHeight - 40),
        left: Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8)),
      })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, anchor, width])

  useEffect(() => {
    if (!open) return undefined
    const away = (e) => {
      if (box.current?.contains(e.target)) return
      if (anchor?.current?.contains(e.target)) return   // по кнопке закрывает она сама
      onClose?.()
    }
    const esc = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open, anchor, onClose])

  if (!open || !pos) return null
  return createPortal(
    <div ref={box} style={{
      ...card, position: 'fixed', top: pos.top, left: pos.left, width,
      // Выше модалок кабинета не поднимаемся, но выше карточек — обязательно.
      zIndex: 9000, padding: 12, display: 'flex', flexDirection: 'column', gap: 8,
      boxShadow: '0 10px 30px rgba(28,36,51,.16)', borderColor: C.border,
    }}>{children}</div>,
    document.body)
}

export default Pop
