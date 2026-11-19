/**
 * Экран «Деньги» — общие стили и мелочи, перенесены из макета хендоффа docs/design_handoff_money_navy.zip дословно
 * (размеры, радиусы, капс-подписи). Цвета — только var(--*) темы.
 */
import { MONO, UI } from '@/components/salesTableKit'

export { MONO, UI }

export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)',
  borderRadius: 20, padding: '20px 22px', display: 'flex', flexDirection: 'column', minWidth: 0 }
export const GLASS = { background: 'var(--glass-bg)', WebkitBackdropFilter: 'blur(16px)', backdropFilter: 'blur(16px)',
  border: '1px solid var(--glass-bd)', boxShadow: 'var(--shadow-card)', borderRadius: 20 }
export const STUB = { border: '1.5px dashed var(--border-hover)', borderRadius: 20, background: 'transparent', padding: '20px 22px',
  display: 'flex', flexDirection: 'column', minWidth: 0 }
export const CAPS = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
export const H = { fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }
export const NUM = { fontFamily: MONO, fontWeight: 700, whiteSpace: 'nowrap' }
export const BTN = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 12px', boxSizing: 'border-box',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600,
  color: 'var(--text-primary)', whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: UI }

const fmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
/** 1 234 567 — пробелы вместо неразрывных, как в макете. */
export const f = (n) => fmt.format(Math.round(n || 0)).replace(/ /g, ' ')
/** со знаком: +1 234 / −1 234 */
export const sg = (n) => (n > 0 ? '+' : n < 0 ? '−' : '') + f(Math.abs(n))
/** минус — типографский */
export const fs = (n) => (n < 0 ? '−' : '') + f(Math.abs(n))
export const mln2 = (n) => (n < 0 ? '−' : '') + (Math.abs(n) / 1e6).toFixed(2).replace('.', ',') + ' млн'
/** 1,16 м / 64 т — подпись остатка под днём календаря */
export const short = (n) => (Math.abs(n) >= 1e6 ? (n < 0 ? '−' : '') + (Math.abs(n) / 1e6).toFixed(2).replace('.', ',') + ' м'
  : (n < 0 ? '−' : '') + Math.round(Math.abs(n) / 1000) + ' т')
export const tys = (n) => Math.round(n / 1000).toLocaleString('ru-RU').replace(/ /g, ' ') + ' тыс'

/** «демо» — блок нарисован по макету, цифры условные; title говорит, чего не хватает в учёте. */
export function DemoTag({ why }) {
  return (
    <span title={why} style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 7px', borderRadius: 5,
      background: 'var(--attn-tint)', border: '1px solid var(--attn-border)', fontFamily: MONO, fontSize: 9, fontWeight: 700,
      letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--attn-fg)', whiteSpace: 'nowrap', cursor: 'help' }}>
      демо · цифры условные
    </span>
  )
}

/** Маленький чип: срок сегодня / обычно +N дн / сценарий. */
export function Flag({ tone = 'attn', children }) {
  const t = { signal: ['--signal-tint', '--signal-border', '--signal-text'], attn: ['--attn-tint', '--attn-border', '--attn-fg'],
    scen: ['--accent-tint', '--accent-border', '--accent-fg'], bad: ['--bad-tint', '--bad-border', '--bad-fg'] }[tone]
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, background: `var(${t[0]})`,
      border: `1px solid var(${t[1]})`, fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.04em',
      textTransform: 'uppercase', color: `var(${t[2]})`, whiteSpace: 'nowrap' }}>{children}</span>
  )
}

/** Сегментная полоса долей (обязательства, корзины долга, клиенты). parts: [{ w, c, t }] */
export function Bar({ parts, h = 10 }) {
  return (
    <div style={{ display: 'flex', height: h, borderRadius: h / 2, overflow: 'hidden', gap: 2 }}>
      {parts.filter(p => p.w > 0).map((p, i) => <span key={i} title={p.t} style={{ flex: `${p.w} 1 0`, background: p.c }} />)}
    </div>
  )
}

export const Dot = ({ c, r = 2, s = 7 }) => <span style={{ flex: `0 0 ${s}px`, width: s, height: s, borderRadius: r, background: c }} />
