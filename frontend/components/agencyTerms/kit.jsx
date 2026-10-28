// Общие куски экрана «Агентские условия» по хендоффу 27.10.2026 (docs/_handoff_agency_terms): KPI-полоса, карточка с
// заголовком, чип-фильтр, плашка способа, сегмент. Значения — из макета; цвета — переменные globals.css.
import { MONO, sel } from '@/components/salesTableKit'
import { MODES } from '@/lib/agencyTerms.mjs'

export const CAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
export const NOTE = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }
export const NUM = { fontFamily: MONO, fontSize: 12, textAlign: 'right' }
export const fmtPct = (v) => (v == null ? '—' : `${String(v).replace('.', ',')} %`)

/** Цвета способа: постоплата — фиолетовый, скидка в счёт — синий; не действует — серый. */
export function modeTone(mode, off) {
  if (off) return ['var(--bg-subtle)', 'var(--text-muted)', 'var(--text-disabled)']
  return mode === MODES[1] ? ['var(--accent-tint)', 'var(--accent-fg)', 'var(--accent)'] : ['var(--violet-tint)', 'var(--violet-fg)', 'var(--violet-fg)']
}

export function ModePill({ mode, off }) {
  const [bg, fg, dot] = modeTone(mode, off)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, justifySelf: 'start', height: 24, padding: '0 9px', borderRadius: 7,
      background: bg, color: fg, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
      <span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{mode}</span>
  )
}

/** KPI-полоса: [label, value, fg, sub, onClick?]; `size` — 32 (вкладки сторон) или 26 (расчёты). */
export function KpiStrip({ items, size = 32, min = 220, flat = false }) {
  // `flat` — внутри карточки (расчёт спец. условий): без своей рамки и тени, как в макете
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fit,minmax(${min}px,1fr))`, rowGap: 12,
      ...(flat ? { padding: '4px 0' } : { padding: '12px 0', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
        boxShadow: 'var(--shadow-card)', borderRadius: 18 }) }}>
      {items.map(([label, value, fg, sub, onClick], i) => (
        <span key={label} onClick={onClick} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '4px 24px', minWidth: 0,
          borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}`, cursor: onClick ? 'pointer' : 'default' }}>
          <span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{label}</span>
          <span style={{ fontFamily: MONO, fontSize: size, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.1, color: fg, whiteSpace: 'nowrap',
            overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</span>
        </span>
      ))}
    </div>
  )
}

export function Card({ title, note, right, children, pad = '14px 18px 12px' }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: pad,
      display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {(title || note || right) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingBottom: 12 }}>
          {title}
          {!!note && <span style={NOTE}>{note}</span>}
          {right}
        </div>)}
      {children}
    </div>
  )
}

export const Title = ({ children }) => <span style={{ fontSize: 16, fontWeight: 700 }}>{children}</span>

/** Чип-фильтр с маркером и счётчиком. */
export function FilterChip({ on, label, dot, count, onClick, h = 32 }) {
  return (
    <span onClick={onClick} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: h, padding: '0 11px', borderRadius: 10, cursor: 'pointer',
      whiteSpace: 'nowrap', fontSize: 12, fontWeight: on ? 700 : 600, border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
      background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
      {!!dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }} />}{label}
      {count != null && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{count}</span>}
    </span>
  )
}

/** Сегмент (период, группировка): [[key, label]]. */
export function MiniSeg({ value, opts, onPick, subtle = false, h = 28 }) {
  return (
    <span style={{ display: 'inline-flex', gap: 2, padding: 3, borderRadius: 10, border: '1px solid var(--border-card)',
      background: subtle ? 'var(--bg-subtle)' : 'var(--bg-card)' }}>
      {opts.map(([k, label]) => {
        const on = value === k
        return (
          <span key={k} onClick={() => onPick(k)} style={{ display: 'inline-flex', alignItems: 'center', height: h - 2, padding: '0 11px', borderRadius: 7,
            cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 12.5, fontWeight: on ? 700 : 600,
            background: on ? (subtle ? 'var(--bg-card)' : 'var(--accent-tint)') : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>{label}</span>
        )
      })}
    </span>
  )
}

/** Таблица в карточке: прокрутка по горизонтали внутри, страница не едет. */
export function Scroll({ min, children, maxHeight }) {
  return (
    <div style={{ overflowX: 'auto', ...(maxHeight ? { maxHeight, overflowY: 'auto' } : {}) }}>
      <div style={{ minWidth: min }}>{children}</div>
    </div>
  )
}


// Поле формы и выбор из справочника по номеру — одни на все формы экрана (ревью 27.10.2026: были копии в трёх окнах)
const FIELD_CAP = { ...CAPS, fontSize: 9.5, fontWeight: 700 }
const idOf = (v) => (v === '' || v == null ? null : Number(v))

export function Field({ label, hint, children }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
      <span style={FIELD_CAP}>{label}</span>
      {children}
      {!!hint && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{hint}</span>}
    </label>
  )
}

export function Pick({ value, onChange, list, empty, disabled }) {
  return (
    <select value={value ?? ''} disabled={disabled} onChange={(e) => onChange(idOf(e.target.value))} style={{ ...sel, width: '100%' }}>
      <option value="">{empty}</option>
      {list.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  )
}
