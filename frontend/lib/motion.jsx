/**
 * Стандарт движения — сторона JS (владелец 18.11.2026). Токены и анимации живут в styles/globals.css («Стандарт движения»); здесь —
 * то, что CSS одной строкой не даёт:
 *   · DUR — те же длительности числами, для таймеров, которые ждут конца анимации (удаление строки после «уезда»). Меняешь
 *     --dur-* в globals.css — меняй и здесь: сторож check-motion сверяет значения;
 *   · <Collapse> — раскрытие на любую высоту (grid 0fr → 1fr), закрытие мгновенное;
 *   · <Segmented> — переключатель с переезжающей подложкой выбранного пункта, как индикатор меню v3.
 */
import { useLayoutEffect, useRef, useState } from 'react'

export const DUR = { fast: 120, base: 200, slow: 320 }

/** Раскрытие расхлопа: содержимое плавно вырастает до своей высоты. Монтируйте при открытии — анимация играет на появлении.
 *  Обрезка (`overflow: hidden`) — только на время анимации: в расхлопах есть выпадашки и закреплённые колонки. */
export function Collapse({ children, style }) {
  const [done, setDone] = useState(false)
  return (
    <div onAnimationEnd={e => { if (e.target === e.currentTarget) setDone(true) }}
      style={{ display: 'grid', animation: done ? 'none' : 'm-expand var(--dur-slow) var(--ease-out) both', ...style }}>
      <div style={{ minHeight: 0, overflow: done ? 'visible' : 'hidden' }}>{children}</div>
    </div>
  )
}

/**
 * Сегментный переключатель — ОДИН на проект (было три: кит продаж, кит отчёта трафика, кит премодерации, плюс самодельные).
 * options: [[ключ, подпись, хвост?]] или [{ value, label }]; хвост — число после подписи. Подложка выбранного переезжает (--ease-move).
 * tone: 'card' — выбранный белым с тенью; 'hot' — тёмной «таблеткой» (трафик); 'tint' — подсветкой акцентом на белом (кит продаж).
 * size: 'md' 30 px · 'sm' 28 · 'xs' 24.
 */
const SEG_H = { md: 30, sm: 28, xs: 24 }
const SEG_TONE = {
  card: { track: 'var(--bg-subtle)', trackBd: 'var(--border-inner)', thumb: 'var(--bg-card)', shadow: 'var(--shadow-card)', on: 'var(--accent-fg)' },
  hot: { track: 'var(--bg-subtle)', trackBd: 'var(--border-inner)', thumb: 'var(--hot)', shadow: 'var(--shadow-card)', on: 'var(--hot-fg)' },
  tint: { track: 'var(--bg-card)', trackBd: 'var(--border-card)', thumb: 'var(--accent-tint)', shadow: 'none', on: 'var(--accent-fg)' },
}
export function Segmented({ options, value, onChange, tone = 'card', size = 'md', disabled = false, title, titleOf }) {
  const box = useRef(null)
  const [rect, setRect] = useState(null)
  const opts = options.map(o => (Array.isArray(o) ? o : [o.value, o.label, o.tail]))
  useLayoutEffect(() => {
    const el = box.current?.querySelector(`[data-seg="${CSS.escape(String(value))}"]`)
    if (!el) { setRect(null); return undefined }
    const measure = () => setRect({ x: el.offsetLeft, w: el.offsetWidth })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [value, opts.length])
  const h = SEG_H[size] || SEG_H.md
  const t = SEG_TONE[tone] || SEG_TONE.card
  return (
    <span ref={box} role="radiogroup" title={title} style={{ position: 'relative', display: 'inline-flex', background: t.track, border: `1px solid ${t.trackBd}`, borderRadius: 10, padding: 2 }}>
      {rect && <span aria-hidden style={{ position: 'absolute', top: 2, left: rect.x, width: rect.w, height: h, borderRadius: 8, background: t.thumb, boxShadow: t.shadow,
        transition: 'left var(--dur-base) var(--ease-move), width var(--dur-base) var(--ease-move)' }} />}
      {opts.map(([k, label, tail]) => {
        const on = k === value
        return (
          <button key={String(k)} type="button" role="radio" aria-checked={on} data-seg={String(k)} disabled={disabled}
            onClick={() => { if (!on && !disabled) onChange(k) }} title={titleOf ? titleOf(k) : undefined}
            style={{ position: 'relative', zIndex: 1, display: 'inline-flex', alignItems: 'center', gap: 5, height: h, padding: size === 'md' ? '0 14px' : '0 10px',
              border: 0, borderRadius: 8, background: 'transparent', cursor: disabled || on ? 'default' : 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
              fontSize: size === 'xs' ? 11.5 : 12.5, fontWeight: on ? 700 : 600,
              color: on ? t.on : disabled ? 'var(--text-disabled)' : 'var(--text-secondary)', transition: 'color var(--dur-fast) var(--ease-out)' }}>
            {label}{tail != null && tail !== '' && <span style={{ fontSize: 10, fontWeight: 600, color: on && tone === 'hot' ? 'var(--hot-fg)' : 'var(--text-faint)',
              opacity: on && tone === 'hot' ? 0.7 : 1 }}>{tail}</span>}
          </button>
        )
      })}
    </span>
  )
}
