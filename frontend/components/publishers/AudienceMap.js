import { useEffect, useRef, useState } from 'react'
import { MONO, UI } from '@/components/salesTableKit'
import { shortNum } from '@/lib/salesFormat'

// Карта «охват × стикинесс» (макет Claude Design 09.10.2026). Нарисована руками, а не Recharts:
// квадранты, подписи и полые точки в Scatter не ложатся. x — уники под рекламой (лог. шкала),
// y — DAU/MAU линейно 0–0,2, размер — наши показы. Площадка без уников стоит по показам
// (×EST_K — ОЦЕНКА, полая пунктирная точка); без MAU или DAU или без показов — не на карте.
const H_MIN = 260, PAD_B = 26, TOP = 14, Y_MAX = 0.2, EST_K = 0.22

const cap = { position: 'absolute', fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }

export default function AudienceMap({ publishers, selectedId, onSelect }) {
  // Высота поля — по соседней карточке (владелец 09.10.2026): поле растягивается во flex-колонке,
  // а геометрия считается от измеренной высоты, а не от константы.
  const plotRef = useRef(null)
  const [H, setH] = useState(330)
  useEffect(() => {
    const el = plotRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([e]) => setH(Math.max(H_MIN, Math.round(e.contentRect.height))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [publishers.length])
  const withX = publishers
    .map(p => ({ p, est: p.measured.uniques == null,
      x: p.measured.uniques ?? (p.measured.shows ? p.measured.shows * EST_K : null) }))
    .filter(d => d.x > 0 && d.p.declared.mau && d.p.stickiness != null)
  const maxShows = Math.max(1, ...publishers.map(p => p.measured.shows || 0))
  const xs = withX.map(d => Math.log10(d.x))
  const xmin = (xs.length ? Math.min(...xs) : 0) - 0.1, xmax = (xs.length ? Math.max(...xs) : 1) + 0.1
  const posX = (v) => ((Math.log10(v) - xmin) / (xmax - xmin)) * 100
  const sizeOf = (p) => 10 + Math.sqrt((p.measured.shows || 0) / maxShows) * 36
  const yOf = (p) => PAD_B + (Math.min(p.stickiness, Y_MAX) / Y_MAX) * (H - PAD_B - TOP)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(t => shortNum(Math.round(10 ** (xmin + (xmax - xmin) * t))))
  const top5 = [...withX].sort((a, b) => (b.p.measured.shows || 0) - (a.p.measured.shows || 0)).slice(0, 5).map(d => d.p.id)
  const estCount = withX.filter(d => d.est).length

  const dot = (label, style) => <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}><span style={{ width: 9, height: 9, borderRadius: '50%', boxSizing: 'border-box', ...style }} />{label}</span>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontFamily: UI, flex: 1, minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-.02em' }}>Карта · охват × стикинесс</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12, flexWrap: 'wrap' }}>
          {dot('уники измерены', { background: 'var(--accent-soft)' })}
          {dot('оценка по показам', { border: '1.5px dashed var(--accent-soft)' })}
          {dot('выбрана', { background: 'var(--accent)' })}
        </span>
      </div>
      {withX.length ? (
        <div ref={plotRef} style={{ position: 'relative', flex: 1, minHeight: H_MIN }}>
          <span style={{ ...cap, left: 0, top: 0 }}>редкие, но ёмкие</span>
          <span style={{ ...cap, right: 0, top: 0 }}>частые и ёмкие</span>
          <span style={{ ...cap, left: 0, bottom: PAD_B }}>малые</span>
          <span style={{ ...cap, right: 0, bottom: PAD_B }}>большие, но ленивые</span>
          <span style={{ position: 'absolute', left: 0, right: 0, top: '50%', borderTop: '1px dashed var(--border-card)' }} />
          <span style={{ position: 'absolute', top: 0, bottom: PAD_B, left: '50%', borderLeft: '1px dashed var(--border-card)' }} />
          <span style={{ position: 'absolute', left: 0, right: 0, bottom: PAD_B, borderBottom: '1px solid var(--border-card)' }} />
          {withX.map(({ p, est, x }) => {
            const size = sizeOf(p), on = p.id === selectedId
            return (
              <span key={p.id} onClick={() => onSelect?.(p.id)}
                title={`${p.name} · ${est ? 'уников нет, по показам' : `уники ${shortNum(p.measured.uniques)}`} · DAU/MAU ${p.stickiness} · показы ${shortNum(p.measured.shows)}`}
                style={{ position: 'absolute', left: `${posX(x)}%`, bottom: yOf(p), width: size, height: size,
                  marginLeft: -size / 2, marginBottom: -size / 2, borderRadius: '50%', boxSizing: 'border-box', cursor: 'pointer',
                  background: on ? 'var(--accent)' : est ? 'transparent' : 'var(--accent-soft)',
                  border: est ? `1.5px dashed ${on ? 'var(--accent)' : 'var(--accent-soft)'}` : 'none',
                  zIndex: on ? 5 : 2, transition: 'background-color 150ms ease' }} />
            )
          })}
          {withX.filter(d => top5.includes(d.p.id)).map(({ p, x }) => (
            <span key={`l${p.id}`} style={{ position: 'absolute', left: `${posX(x)}%`, bottom: yOf(p) + sizeOf(p) / 2 + 3,
              fontFamily: MONO, fontSize: 9.5, fontWeight: 700, whiteSpace: 'nowrap', pointerEvents: 'none', transform: 'translate(-50%, 0)',
              color: p.id === selectedId ? 'var(--accent-fg)' : 'var(--text-muted)' }}>{p.name}</span>
          ))}
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, display: 'flex', justifyContent: 'space-between' }}>
            {ticks.map((t, i) => <span key={i} style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{t}</span>)}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, minHeight: H_MIN, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12.5, textAlign: 'center', padding: 20 }}>
          Карте нужны наши показы за окно и заявленные MAU/DAU. Пока нет ни одной площадки с тем и другим.
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
          x — уники под рекламой, лог. шкала · y — DAU/MAU · размер — наши показы</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
          полые ({estCount}) — уников нет, стоят по показам · не на карте: {publishers.length - withX.length}</span>
      </div>
    </div>
  )
}
