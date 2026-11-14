/* Код, который копируется по клику: код сделки, РК, пары (владелец 25.09.2026).

   Трафик вставляет эти коды в кабинеты DSP, в переписку с площадкой, в поиск — и
   выделять мышью моноширинный текст внутри кликабельной строки неудобно: строка
   разворачивается, выделение слетает. Поэтому клик по коду копирует его и НЕ
   всплывает дальше — строка остаётся как была.

   Один компонент на все места: копия в каждом экране разошлась бы в подписи и в том,
   всплывает ли клик. */
import { useState } from 'react'

/** `swap` — «скопировано» на месте текста, а не справа: для узких колонок с обрезкой (реестр мастер-сделок, 12.11.2026). */
export default function CopyCode({ text, style, children, swap = false }) {
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
      {swap && done ? <span style={{ color: 'var(--income-fg)' }}>скопировано</span> : (children || text)}
      {done && !swap && (
        <span style={{ position: 'absolute', left: '100%', top: '50%',
          transform: 'translate(6px, -50%)', whiteSpace: 'nowrap', fontSize: 10.5,
          fontWeight: 600, color: 'var(--income-fg)', pointerEvents: 'none' }}>
          скопировано
        </span>
      )}
    </span>
  )
}

/** Иконка «скопировать» после кода (дашборд аккаунта v5, 14.11.2026): копирует `text`, клик не всплывает — строка не раскрывается. */
export function CopyIcon({ text, size = 13, title = 'Скопировать' }) {
  const [done, setDone] = useState(false)
  if (!text) return null
  const copy = async (e) => {
    e.stopPropagation()
    e.preventDefault()
    try {
      await navigator.clipboard.writeText(String(text))
      setDone(true)
      setTimeout(() => setDone(false), 1200)
    } catch (err) { /* нет доступа к буферу — молча */ }
  }
  return (
    <button type="button" onClick={copy} title={done ? 'Скопировано' : title} aria-label={title}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size + 8, height: size + 8, padding: 0, border: 0,
        borderRadius: 6, background: 'transparent', cursor: 'copy', color: done ? 'var(--income-fg)' : 'var(--text-faint)', flex: '0 0 auto' }}>
      {done
        ? <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
        : <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2" /><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5" /></svg>}
    </button>
  )
}
