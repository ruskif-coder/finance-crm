import { useState, useEffect, useRef } from 'react'
import { Z } from '@/components/salesTableKit'

const MONO = "'JetBrains Mono', ui-monospace, monospace"

/* ПОВЕРХ ВСЕГО, ЧТО ЕГО ОТКРЫЛО.

   Было 60/61 — на голой странице это работало, а из модалки (`zIndex` подложки 10000)
   поповер уходил ПОД неё: на карточке паблишера выбор должности контакта открывался
   невидимым, и модалка добавления контакта выглядела так, будто кнопка не нажимается
   (владелец 18.09.2026).

   Поповер всегда самый верхний временный слой: он и открывается последним, и закрывается
   первым. Поэтому шкала берётся из общего кита, а не назначается числом заново — и берётся
   ступенью выше подложки. Выше остаётся только тост: уведомление вправе перекрыть выбор,
   обратное было бы неверно. */
const Z_CATCH = Z.overlay + 1
const Z_BOX = Z.overlay + 2

// Поповер выбора значения у места клика (Агентство / Рекламодатель / Бренд / Услуга).
// Дизайн-хендофф v2 дашборда сейлза: 216px, поиск, ✓ на текущем, оптимистичный выбор.
// props: anchor(DOMRect), title, dealLabel, options[{value,label}], value, onPick(value|null), onClose, clearLabel
export default function ValuePopover({ anchor, title, dealLabel, options, value, onPick, onClose, clearLabel, onAddNew }) {
  const [q, setQ] = useState('')
  const boxRef = useRef(null)
  const inputRef = useRef(null)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    // скролл внутри самого поповера не должен его закрывать — только внешний скролл/ресайз
    const onScroll = (e) => { if (boxRef.current && boxRef.current.contains(e.target)) return; onClose() }
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onClose)
    document.addEventListener('scroll', onScroll, true)
    return () => { document.removeEventListener('keydown', onKey); window.removeEventListener('resize', onClose); document.removeEventListener('scroll', onScroll, true) }
  }, [])
  const W = 216
  const x = Math.min(anchor.left, Math.max(8, window.innerWidth - W - 8))
  const y = Math.min(anchor.bottom + 6, Math.max(8, window.innerHeight - 380))
  const opts = options || []
  const shown = opts.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase()))

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: Z_CATCH }} onClick={onClose} />
      <div ref={boxRef} style={{ position: 'fixed', left: x, top: y, width: W, zIndex: Z_BOX, background: 'var(--bg-card)',
        border: '1px solid var(--border-card)', borderRadius: 16, overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)',
        animation: 'vpRise .22s cubic-bezier(0.22,1,0.36,1) both', fontFamily: "'Manrope', system-ui, sans-serif" }}>
        <style>{`@keyframes vpRise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
        <div style={{ padding: '10px 10px 8px', borderBottom: '1px solid var(--border-inner)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
            {dealLabel && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{dealLabel}</span>}
          </div>
          <input ref={inputRef} autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
            style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)',
              fontSize: 12, outline: 'none', fontFamily: 'inherit' }}
            onFocus={e => e.target.style.borderColor = 'var(--accent)'}
            onBlur={e => e.target.style.borderColor = 'var(--border-card)'} />
        </div>
        <div style={{ maxHeight: 'min(260px, 40vh)', overflowY: 'auto', padding: 5 }}>
          {clearLabel && (
            <div onClick={() => onPick(null)} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', color: 'var(--text-muted)' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              {clearLabel}
            </div>
          )}
          {shown.map(o => {
            const on = String(o.value) === String(value)
            return (
              <div key={String(o.value)} onClick={() => onPick(o.value)}
                style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center',
                  background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-primary)' }}
                onMouseEnter={e => { if (!on) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                {on && <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, flexShrink: 0 }}>✓</span>}
              </div>
            )
          })}
          {!shown.length && !onAddNew && <div style={{ padding: 10, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          {onAddNew && (() => {
            const canAdd = q.trim() && !opts.some(o => String(o.label).toLowerCase() === q.trim().toLowerCase())
            return (
              <div onClick={() => (canAdd ? onAddNew(q.trim()) : inputRef.current && inputRef.current.focus())}
                title={canAdd ? undefined : 'Введите название в поле поиска, затем нажмите'}
                style={{ padding: '7px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', fontWeight: canAdd ? 700 : 600, color: canAdd ? 'var(--accent)' : 'var(--text-muted)', borderTop: '1px solid var(--border-inner)', marginTop: 4 }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-tint)'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                {canAdd ? `+ Добавить «${q.trim()}»` : '+ Добавить новый'}
              </div>
            )
          })()}
        </div>
      </div>
    </>
  )
}
