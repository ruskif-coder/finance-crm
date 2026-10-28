/**
 * Примитивы карточки договора (хендофф «договорZ», 28.10.2026): карточка блока, подпись-капс, плашка с квадратным маркером,
 * кнопки. Цвета — только переменные `var(--*)`; суммы — JetBrains Mono, `ru-RU`, с копейками.
 */
import { MONO } from '@/components/salesTableKit'
import { grpDec } from '@/lib/salesFormat'

export const box = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, minWidth: 0 }
export const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
export const h2 = { fontSize: 16, fontWeight: 700 }
export const count = { fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }
export const note = { fontSize: 11.5, color: 'var(--text-muted)' }
export const btnGhost = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, textDecoration: 'none', padding: '0 13px', border: '1px solid var(--border-card)', borderRadius: 9, background: 'var(--bg-card)', fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap', flex: '0 0 auto', cursor: 'pointer', fontFamily: 'inherit' }
export const btnPrimary = { ...btnGhost, background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--on-accent)' }
export const btnSm = { ...btnGhost, height: 28, padding: '0 11px', fontSize: 12, fontWeight: 600 }
/** Поле ввода в режиме правки карточки (шапка договора, подписант в «Сторонах»). */
export const fieldInp = { width: '100%', boxSizing: 'border-box', height: 32, padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 8, fontFamily: 'inherit', fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }
/** Блок правой колонки карточки. */
export const panel = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, minWidth: 0, padding: '16px 18px', display: 'flex', flexDirection: 'column' }

/** Ссылка без подчёркивания, как в макете. */
export const link = { color: 'var(--accent)', textDecoration: 'none' }

export const money = (v) => (v == null ? '—' : `${grpDec(v, 2)} ₽`)

/** Тон плашки: фон, текст, маркер. */
export const TONE = {
  accent: ['var(--accent-tint)', 'var(--accent-fg)', 'var(--accent)'],
  income: ['var(--income-tint)', 'var(--income-fg)', 'var(--income)'],
  violet: ['var(--violet-tint)', 'var(--violet-fg)', 'var(--violet-fg)'],
  warning: ['var(--warning-tint)', 'var(--warning-fg)', 'var(--warning)'],
  danger: ['var(--danger-tint)', 'var(--danger-fg)', 'var(--danger)'],
  muted: ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--text-faint)'],
}

export function Pill({ tone = 'muted', children, small }) {
  const [bg, fg, dot] = TONE[tone] || TONE.muted
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: small ? 18 : 22, padding: small ? '0 6px' : '0 8px', borderRadius: small ? 5 : 6, background: bg, color: fg, fontSize: small ? 10 : 11, fontWeight: 700, whiteSpace: 'nowrap', flex: '0 0 auto' }}>
      {!small && <span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />}{children}
    </span>
  )
}

export function Notice({ tone = 'warning', children }) {
  const [, fg, dot] = TONE[tone] || TONE.warning
  const bg = tone === 'danger' ? 'var(--danger-bg)' : tone === 'warning' ? 'var(--warning-bg)' : 'var(--bg-tint)'
  const border = tone === 'danger' ? 'var(--danger-border)' : tone === 'warning' ? 'var(--warning-border)' : 'var(--accent-border)'
  return (
    <span style={{ display: 'flex', gap: 7, padding: '8px 10px', background: bg, border: `1px solid ${border}`, borderRadius: 9, fontSize: 11.5, color: fg, lineHeight: 1.4 }}>
      <span style={{ width: 6, height: 6, borderRadius: 2, background: dot, flex: '0 0 6px', marginTop: 4 }} />{children}
    </span>
  )
}

/** Карточка блока: заголовок, счётчик, подпись, справа — действие. */
export function Block({ id, title, n, hint, aside, pad = '16px 20px', gap = 10, children }) {
  return (
    <section id={id} style={{ ...box, padding: pad, display: 'flex', flexDirection: 'column', gap }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={h2}>{title}</span>
        {n != null && <span style={count}>{n}</span>}
        {hint && <span style={note}>{hint}</span>}
        {aside && <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>{aside}</span>}
      </div>
      {children}
    </section>
  )
}


export { plural } from '@/lib/publisherRecon.mjs'
