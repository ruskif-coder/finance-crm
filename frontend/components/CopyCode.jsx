/* Код, который копируется по клику: код сделки, РК, пары (владелец 25.09.2026).

   Трафик вставляет эти коды в кабинеты DSP, в переписку с площадкой, в поиск — и
   выделять мышью моноширинный текст внутри кликабельной строки неудобно: строка
   разворачивается, выделение слетает. Поэтому клик по коду копирует его и НЕ
   всплывает дальше — строка остаётся как была.

   Один компонент на все места: копия в каждом экране разошлась бы в подписи и в том,
   всплывает ли клик. */
import { useState } from 'react'

export default function CopyCode({ text, style, children }) {
  const [done, setDone] = useState(false)
  if (!text) return children || null
  const copy = async (e) => {
    e.stopPropagation()
    e.preventDefault()
    try {
      await navigator.clipboard.writeText(String(text))
      setDone(true)
      setTimeout(() => setDone(false), 1200)
    } catch (err) { /* нет доступа к буферу — просто ничего не показываем */ }
  }
  return (
    <span role="button" tabIndex={0} onClick={copy}
      onKeyDown={e => { if (e.key === 'Enter') copy(e) }}
      title={done ? 'Скопировано' : 'Скопировать'}
      style={{ cursor: 'copy', position: 'relative', ...style }}>
      {children || text}
      {done && (
        <span style={{ position: 'absolute', left: '100%', top: '50%',
          transform: 'translate(6px, -50%)', whiteSpace: 'nowrap', fontSize: 10.5,
          fontWeight: 600, color: 'var(--income-fg)', pointerEvents: 'none' }}>
          скопировано
        </span>
      )}
    </span>
  )
}
