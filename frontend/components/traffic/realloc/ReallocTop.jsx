// Окно «Перераспределить объём» (хендофф 26.10.2026): KPI и четыре действия.
import { MONO } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'

const nf = (v) => (v < 0 ? '−' : '') + grp(Math.abs(Math.round(v || 0)))

/** Четыре KPI — по эталону ДДС, ужатые: цифра 32px, единица — в подписи. */
export function ReallocKpis({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', padding: '0 0 8px', borderBottom: '1px solid var(--border-inner)' }}>
      {items.map(([label, value, fg, sub, subFg], i) => (
        <div key={label} style={{ padding: '2px 22px', display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0,
          borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}` }}>
          <span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
          <span style={{ fontFamily: MONO, fontSize: 32, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.1, color: fg, whiteSpace: 'nowrap' }}>{nf(value)}</span>
          <span style={{ fontSize: 11.5, color: subFg || 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</span>
        </div>
      ))}
    </div>
  )
}

/** Карточка действия: доступная — белая с синей кнопкой, недоступная — `--bg-subtle`, кнопка погашена. */
export function ReallocActions({ acts, busy }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 10 }}>
      {acts.map(a => {
        const on = a.on && !busy
        return (
          <div key={a.key} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', borderRadius: 14, minWidth: 0,
            background: a.on ? 'var(--bg-card)' : 'var(--bg-subtle)',
            border: `1px solid ${a.urgent ? 'var(--danger-border)' : a.on ? 'var(--border-card)' : 'var(--border-inner)'}` }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, flex: '0 0 7px', background: a.on ? a.tone : 'var(--text-disabled)' }} />
              <span style={{ fontSize: 13.5, fontWeight: 700, color: a.on ? 'var(--text-primary)' : 'var(--text-muted)' }}>{a.title}</span>
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45, flex: 1 }}>{a.text}</span>
            {a.btn && (
              <button type="button" disabled={!on} onClick={a.run}
                style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 13px', borderRadius: 10,
                  fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', fontFamily: 'inherit', cursor: on ? 'pointer' : 'default',
                  background: a.on ? 'var(--accent)' : 'var(--bg-card)', border: `1px solid ${a.on ? 'var(--accent)' : 'var(--border-card)'}`,
                  color: a.on ? 'var(--on-accent)' : 'var(--text-disabled)', opacity: busy && a.on ? 0.6 : 1 }}>{a.btn}</button>)}
          </div>
        )
      })}
    </div>
  )
}
