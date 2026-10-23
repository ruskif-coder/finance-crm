// «Статусы продаж»: шапка (Квартал / Месяц, окно), KPI с разбивкой по продажникам, панель «В реестр запишется».
// Вёрстка — из хендоффа docs/статусы продаж.zip («Статусы продаж.dc.html»), данные — пропсами.
import { grp } from '@/lib/salesFormat'
import { windowLabel } from '@/lib/salesStatus'

const MONO = "'JetBrains Mono', monospace"
const CAP = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const RISE = (d) => ({ animation: `ssRise .4s cubic-bezier(.22,1,.36,1) ${d}s both` })
const seg = { display: 'inline-flex', alignItems: 'center', padding: 3, height: 34, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10 }
const segItem = (on, mono) => ({
  display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 11px', borderRadius: 8, cursor: 'pointer', whiteSpace: 'nowrap',
  background: on ? (mono ? 'var(--accent-tint)' : 'var(--bg-card)') : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)',
  fontWeight: on ? 700 : 600, fontSize: mono ? 11.5 : 12, fontFamily: mono ? MONO : undefined, transition: 'background-color 150ms ease',
})

export function Header({ mode, setMode, quarters, q, setQ, win, canPrev, canNext, step, onNew, canEdit }) {
  const arrow = (on) => ({ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 26, borderRadius: 8,
    color: on ? 'var(--text-secondary)' : 'var(--text-disabled)', cursor: on ? 'pointer' : 'default', fontSize: 13 })
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap', ...RISE(0) }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.025em' }}>Статусы продаж</span>
        <span style={CAP}>матрица клиент × месяц × вероятность · все суммы без НДС</span>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ ...seg, background: 'var(--bg-subtle)' }}>
          {[['q', 'Квартал'], ['m', 'Месяц']].map(([k, label]) => (
            <span key={k} onClick={() => setMode(k)} style={segItem(mode === k)}>{label}</span>
          ))}
        </span>
        {mode === 'm' ? (
          <span style={{ ...seg, background: 'var(--bg-card)' }}>
            <span onClick={() => canPrev && step(-1)} title="На месяц назад" style={arrow(canPrev)}>‹</span>
            <span style={{ ...segItem(true, true), minWidth: 132, justifyContent: 'center' }}>{windowLabel(win)}</span>
            <span onClick={() => canNext && step(1)} title="На месяц вперёд" style={arrow(canNext)}>›</span>
          </span>
        ) : (
          <span style={{ ...seg, background: 'var(--bg-card)' }}>
            {quarters.map(x => <span key={x} onClick={() => setQ(x)} style={segItem(q === x, true)}>{x}</span>)}
          </span>
        )}
        {canEdit && (
          <button onClick={onNew} style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 15px', background: 'var(--accent)',
            color: 'var(--on-accent)', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Сделка</button>
        )}
      </div>
    </div>
  )
}

/** Четыре карточки: факт, средняя, низкая, прогноз (факт + средняя). Всё — по видимым месяцам. */
export function Kpi({ cards }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18,
      padding: '4px 10px', display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', ...RISE(0.05) }}>
      {cards.map((k, i) => (
        <div key={k.label} style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 7,
          borderRight: `1px solid ${i === 3 ? 'transparent' : 'var(--border-inner)'}` }}>
          <span style={{ ...CAP, fontSize: 9.5, display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: k.dot }} />{k.label}
          </span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1, color: k.color, whiteSpace: 'nowrap' }}>{grp(k.value)}</span>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-muted)' }}>₽</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-faint)' }}>
            <span style={{ flex: '1 1 auto', display: 'flex', gap: 2, height: 5 }}>
              {k.bars.map((b, j) => <span key={j} title={b.title} style={{ width: b.w, borderRadius: 2, background: b.bg }} />)}
            </span>
            <span style={{ whiteSpace: 'nowrap' }}>{k.hint}</span>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingTop: 7, marginTop: 2, borderTop: '1px solid var(--border-row)' }}>
            {k.sales.map(p => (
              <span key={p.name} title={p.title} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 46px auto', gap: 8, alignItems: 'center', fontSize: 11 }}>
                <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                <span style={{ display: 'block', height: 4, borderRadius: 2, background: 'var(--border-inner)', overflow: 'hidden' }}>
                  <span style={{ display: 'block', height: 4, width: p.w, borderRadius: 2, background: k.bar }} />
                </span>
                <span style={{ fontFamily: MONO, fontWeight: 700, color: p.empty ? 'var(--text-disabled)' : k.fg, textAlign: 'right', whiteSpace: 'nowrap' }}>{p.value}</span>
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  )
}

/** «В реестр запишется»: переносы сделок; ничего не уходит без «Сохранить». Новая сделка пишется сразу — стандартной формой. */
export function Pending({ items, saving, onReset, onSave, onRemove }) {
  if (!items.length) return null
  return (
    <div style={{ background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 14, padding: '10px 16px',
      display: 'flex', flexDirection: 'column', gap: 6, animation: 'ssPop .2s cubic-bezier(.22,1,.36,1) both' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} />
        <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--accent-fg)' }}>
          В реестр запишется · {items.length}
        </span>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>период и светофор меняются в сделке, новые создаются обычным путём</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
          <button onClick={onReset} disabled={saving} style={{ height: 28, padding: '0 11px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 9, fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }}>Сбросить всё</button>
          <button onClick={onSave} disabled={saving} style={{ height: 28, padding: '0 13px', background: 'var(--accent)', color: 'var(--on-accent)', border: 'none',
            borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: saving ? 'wait' : 'pointer' }}>{saving ? 'Сохраняю…' : 'Сохранить'}</button>
        </span>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {items.map(p => (
          <span key={p.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 26, padding: '0 9px', background: 'var(--bg-card)',
            border: '1px solid var(--accent-border)', borderRadius: 8, fontSize: 11.5, whiteSpace: 'nowrap' }}>
            <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--accent)' }}>{p.code}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{p.text}</span>
            <span onClick={() => onRemove(p)} title="Отменить перенос"
              style={{ color: 'var(--text-faint)', cursor: 'pointer', fontSize: 12 }}>✕</span>
          </span>
        ))}
      </div>
    </div>
  )
}
