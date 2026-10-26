// Мелкие общие куски экрана сверок: подпись капсом, квадратный маркер, плашка статуса, переключатель месяца/года, тост.
import { useCallback, useEffect, useRef, useState } from 'react'
import { MONO, Z } from '@/components/salesTableKit'

export const CAPS = { fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }

/** Кнопка окна сверки: `p` — основная, `ok` — «Согласовать», иначе вторичная; `off` — погашена. */
export const actBtn = (kind, off) => ({
  display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 16px', borderRadius: 10, fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap',
  background: off ? 'var(--bg-subtle)' : kind === 'p' ? 'var(--accent)' : kind === 'ok' ? 'var(--income)' : 'var(--bg-card)',
  border: `1px solid ${off ? 'var(--border-card)' : kind === 'p' ? 'var(--accent)' : kind === 'ok' ? 'var(--income)' : 'var(--border-card)'}`,
  color: off ? 'var(--text-disabled)' : kind === 'p' || kind === 'ok' ? 'var(--on-accent)' : 'var(--text-secondary)',
  cursor: off ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
})

export const Dot = ({ c, size = 6 }) => (
  <span style={{ width: size, height: size, borderRadius: 2, background: c, flex: `0 0 ${size}px`, display: 'inline-block' }} />
)

export const StatusPill = ({ t }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, justifySelf: 'start', height: 24, padding: '0 9px', borderRadius: 8,
    background: t.bg, color: t.fg, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
    <Dot c={t.dot} />{t.label}
  </span>
)

const arrow = (on) => ({ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8,
  color: on ? 'var(--text-secondary)' : 'var(--text-disabled)', fontSize: 14, cursor: on ? 'pointer' : 'default', userSelect: 'none' })

/** ‹ Октябрь 2026 › — стрелки гаснут на границах. */
export function MonthSwitch({ title, canPrev, canNext, onPrev, onNext, minWidth = 118, mono }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', padding: 3, gap: 2, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
      <span title="Назад" onClick={canPrev ? onPrev : undefined} style={arrow(canPrev)}>‹</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 26, minWidth, padding: '0 10px', borderRadius: 8,
        background: 'var(--bg-card)', boxShadow: 'var(--shadow-card)', fontSize: mono ? 12 : 12.5, fontWeight: 700, whiteSpace: 'nowrap',
        fontFamily: mono ? MONO : undefined }}>{title}</span>
      <span title="Вперёд" onClick={canNext ? onNext : undefined} style={arrow(canNext)}>›</span>
    </span>
  )
}

export function useToast() {
  const [text, setText] = useState('')
  const t = useRef(null)
  useEffect(() => () => clearTimeout(t.current), [])
  const flash = useCallback((s) => {
    setText(s)
    clearTimeout(t.current)
    t.current = setTimeout(() => setText(''), 2600)
  }, [])
  return [text, flash]
}

export const Toast = ({ text }) => (!text ? null : (
  <span style={{ position: 'fixed', left: '50%', bottom: 28, transform: 'translateX(-50%)', zIndex: Z.toast, padding: '10px 16px',
    background: 'var(--text-primary)', color: 'var(--bg-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, boxShadow: 'var(--shadow-modal)' }}>{text}</span>
))
