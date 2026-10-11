// Площадки с галочками: выключение пересчитывает всю страницу. Быстрые наборы — в шапке блока.
import { MONO } from '@/components/salesTableKit'
import { nf, dm, box, title14, Dot } from './rkUi'

const dotOf = (p) => (p.status === 'пауза' ? 'var(--warning)' : p.external ? 'var(--violet-fg)' : 'var(--income)')

export default function RkPlacements({ placements, on, facts, focus, onToggle, presets }) {
  const count = placements.filter(p => on[p.id]).length
  return (
    <div style={{ ...box, padding: '10px 14px 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '0 2px' }}>
        <span style={title14}>Площадки</span>
        <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: count < placements.length ? 'var(--warning-fg)' : 'var(--text-faint)' }}>
          {count} из {placements.length}</span>
        <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {presets.map(p => (
            <button key={p.label} type="button" onClick={p.pick} style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 8px', borderRadius: 6,
              border: `1px solid ${p.match ? 'var(--accent-border)' : 'var(--border-card)'}`, background: p.match ? 'var(--accent-tint)' : 'var(--bg-card)',
              color: p.match ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>{p.label}</button>
          ))}
        </span>
        <span style={{ display: 'inline-flex', gap: 10, fontSize: 10.5, color: 'var(--text-muted)' }}>
          {[['DSP', 'var(--income)'], ['вне DSP', 'var(--violet-fg)'], ['пауза', 'var(--warning)']].map(([l, c]) => (
            <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Dot c={c} s={6} />{l}</span>
          ))}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>доля % · факт к дате · клик — вкл/выкл</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(208px, 1fr))', gap: '0 10px' }}>
        {placements.map(p => {
          const isOn = !!on[p.id], f = facts[p.id] || 0
          return (
            <span key={p.id} onClick={() => onToggle(p.id)}
              title={`${p.domain} · план ${nf(p.plan_show)}${p.first_started_at ? ' · запущена ' + dm(p.first_started_at) : ''} · ${p.status === 'пауза' ? 'пауза' : p.external ? 'вне DSP · не наш код' : 'DSP'}`}
              style={{ display: 'grid', gridTemplateColumns: '13px 6px minmax(0,1fr) 34px 56px', gap: 6, alignItems: 'center', height: 24, padding: '0 6px',
                borderRadius: 7, background: focus === p.id ? 'var(--accent-tint)' : 'transparent', cursor: 'pointer' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 12, height: 12, borderRadius: 3,
                border: `1px solid ${isOn ? 'var(--accent)' : 'var(--border-hover)'}`, background: isOn ? 'var(--accent)' : 'var(--bg-card)',
                color: 'var(--bg-card)', fontSize: 8, fontWeight: 700 }}>{isOn ? '✓' : ''}</span>
              <Dot c={dotOf(p)} s={6} />
              <span style={{ fontSize: 11.5, fontWeight: 600, color: isOn ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.domain}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', textAlign: 'right' }}>{(p.share * 100).toFixed(1).replace('.', ',')}</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, textAlign: 'right', color: !isOn || !f ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{f ? nf(f) : '—'}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
