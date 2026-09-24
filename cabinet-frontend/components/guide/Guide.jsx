/**
 * Руководство паблишера — окно со слайдами (владелец, 24.09.2026).
 *
 * Слайды — выгрузка Claude Design (`slides.js`, 1920×1080, стили внутри разметки).
 * Показываем их сами: редакторский скрипт выгрузки (`deck-stage.js`) умеет удалять и
 * переставлять слайды, и площадке это не нужно. Слайд рисуется в полном размере и
 * масштабируется под ширину окна — так вёрстка слайда не зависит от экрана.
 *
 * Разметка слайдов — НАШ статичный файл из репозитория, не данные пользователя, поэтому
 * `dangerouslySetInnerHTML` здесь безопасен; генератор отсекает ссылки наружу и скрипты.
 *
 * Открывается сама один раз — при первом входе в этом браузере (решение владельца), и в
 * любой момент — пиктограммой «i» в шапке.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { C, CAP, MONO, UI, btnSm } from '../../lib/ui'
import { overlayClose } from '../../lib/overlay'
import SLIDES, { W, H } from './slides'

const navBtn = (disabled) => ({
  ...btnSm(false), minWidth: 36, fontSize: 15, padding: '4px 10px',
  opacity: disabled ? 0.4 : 1, cursor: disabled ? 'default' : 'pointer',
})

export default function Guide({ onClose }) {
  const [i, setI] = useState(0)
  const [scale, setScale] = useState(0)
  const stageRef = useRef(null)
  const last = SLIDES.length - 1

  const go = useCallback((d) => setI(x => Math.min(last, Math.max(0, x + d))), [last])

  // Масштаб — от фактической ширины сцены: окно тянется под экран, слайд следом.
  useEffect(() => {
    const el = stageRef.current
    if (!el) return undefined
    const fit = () => setScale(el.clientWidth / W)
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' || e.key === 'PageDown') go(1)
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') go(-1)
      else if (e.key === 'Home') setI(0)
      else if (e.key === 'End') setI(last)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, last, onClose])

  const slide = SLIDES[i]
  return (
    <div {...overlayClose(onClose)} role="dialog" aria-modal="true" aria-label="Руководство"
      style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(20,26,38,.62)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
        fontFamily: UI }}>
      <div style={{ width: 'min(1280px, 100%, calc((100vh - 120px) * 16 / 9))',
        background: C.card, border: `1px solid ${C.border}`, borderRadius: 16,
        boxShadow: 'var(--shadow-float)', overflow: 'hidden', display: 'flex',
        flexDirection: 'column' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
          borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontSize: 14, fontWeight: 800 }}>Руководство</span>
          <span style={{ ...CAP, marginBottom: 0, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', minWidth: 0 }}>{slide.label}</span>
          <span style={{ flex: 1 }} />
          <button onClick={onClose} aria-label="Закрыть руководство"
            style={{ width: 28, height: 28, borderRadius: 8, border: 0, cursor: 'pointer',
              background: 'transparent', color: C.secondary, fontSize: 18, lineHeight: 1 }}>×</button>
        </div>

        {/* Сцена: высота из пропорции 16:9, слайд внутри — в полном размере под scale. */}
        <div ref={stageRef} onClick={(e) => {
          // Касание левой/правой половины листает — как у выгрузки; ссылки не трогаем.
          if (e.target.closest('a')) return
          const r = e.currentTarget.getBoundingClientRect()
          go(e.clientX - r.left < r.width / 2 ? -1 : 1)
        }}
          style={{ position: 'relative', width: '100%', aspectRatio: `${W} / ${H}`,
            overflow: 'hidden', background: '#EBEEF6', cursor: 'pointer' }}>
          {/* Масштаб и анимация появления — на РАЗНЫХ слоях: `.rise` анимирует
              `transform` и на своём элементе перекрывал бы `scale` — слайд рисовался в
              полный размер и обрезался окном (24.09.2026). */}
          {scale > 0 && (
            <div style={{ position: 'absolute', left: 0, top: 0, width: W, height: H,
              transform: `scale(${scale})`, transformOrigin: '0 0' }}>
              {/* Разметка — наш статичный файл из репозитория (см. шапку). */}
              <div key={i} className="rise" style={{ width: W, height: H, display: 'flex',
                fontFamily: UI, color: '#1C2433' }}
                dangerouslySetInnerHTML={{ __html: slide.html }} />
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
          borderTop: `1px solid ${C.border}` }}>
          <button style={navBtn(i === 0)} disabled={i === 0} onClick={() => go(-1)}
            aria-label="Предыдущий слайд">‹</button>
          <span style={{ fontFamily: MONO, fontSize: 12, color: C.secondary, minWidth: 54,
            textAlign: 'center' }}>{i + 1} / {SLIDES.length}</span>
          <button style={navBtn(i === last)} disabled={i === last} onClick={() => go(1)}
            aria-label="Следующий слайд">›</button>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 11.5, color: C.faint }}>стрелки ← → листают</span>
          {i === last && (
            <button style={btnSm(true)} onClick={onClose}>Понятно</button>
          )}
        </div>
      </div>
    </div>
  )
}
