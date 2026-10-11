// Общие мелочи страницы «Разбор РК»: форматы и цвета. Цвета — только токены (макет 11.10.2026).
import { MONO } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'

export const nf = (v) => (v == null || !isFinite(v) ? '—' : grp(v))
export const rub = (v) => (v == null || !isFinite(v) ? '—' : grp(v) + ' ₽')
export const pf = (v, d = 1) => (v == null || !isFinite(v) ? '—' : v.toFixed(d).replace('.', ',') + ' %')
export const sg = (v) => (v == null || !isFinite(v) ? '—' : (v < 0 ? '−' : '+') + Math.abs(v).toFixed(1).replace('.', ',') + ' %')
export const pp = (v) => (v == null || !isFinite(v) ? '—' : (v < 0 ? '−' : '+') + Math.abs(v).toFixed(1).replace('.', ',') + ' п.п.')
export const dm = (s) => (s ? s.slice(8, 10) + '.' + s.slice(5, 7) : '—')

export const box = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
export const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)', whiteSpace: 'nowrap' }
export const title14 = { fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }
export const mono = (size = 11, weight = 400, color = 'var(--text-primary)') => ({ fontFamily: MONO, fontSize: size, fontWeight: weight, color })

export const pctTone = (v) => (v == null ? 'var(--text-faint)' : v >= 95 ? 'var(--income-fg)' : v >= 80 ? 'var(--warning-fg)' : 'var(--danger-fg)')
export const WR_TONE = { ok: 'var(--text-secondary)', warn: 'var(--warning-fg)', bad: 'var(--danger-fg)' }
export const EV_COLOR = { start: 'var(--income)', pause: 'var(--warning)', campaign: 'var(--accent)', bidder: 'var(--violet-fg)',
  boost: 'var(--warning-fg)', tech: 'var(--text-faint)' }
export const CHECK_COLOR = { red: 'var(--danger)', yellow: 'var(--warning)', green: 'var(--income)', skip: 'var(--text-disabled)' }

/** Тепловая клетка: смесь цвета состояния с фоном карточки, без хексов. */
export const heat = (k, tone) => {
  const a = Math.round((0.08 + Math.max(0, Math.min(1, k)) * 0.62) * 100)
  return `color-mix(in srgb, var(${tone === 'bad' ? '--danger' : '--income'}) ${a}%, var(--bg-card))`
}

export const Dot = ({ c, s = 7 }) => <span style={{ width: s, height: s, borderRadius: 2, background: c, flex: `0 0 ${s}px`, display: 'inline-block' }} />
