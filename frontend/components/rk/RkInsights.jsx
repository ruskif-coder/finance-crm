// Выводы (фраза с цифрой → клик ведёт к строке/дню, откуда она взята) и «включённые против выключенных».
import { MONO } from '@/components/salesTableKit'
import { nf, pf, box, title14, cap, Dot } from './rkUi'

const TONE = { bad: ['var(--danger)', 'var(--danger-border)'], warn: ['var(--warning)', 'var(--warning-border)'],
  ok: ['var(--income)', 'var(--income-border)'], info: ['var(--accent)', 'var(--border-card)'] }
const LINK = { placement: 'площадка в таблице', day: 'день на графике', slice: 'разрез по креативам', preset: 'выбрать вне DSP',
  source: 'расхождение по площадкам', metric: 'показать в срезе' }

export default function RkInsights({ items, onGo, onCount, offCount, cmp }) {
  return (
    <div style={{ flex: '0 0 380px', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ ...box, padding: '14px 14px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '0 2px 2px' }}>
          <span style={title14}>Выводы</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{onCount ? `по ${onCount} включённым` : 'нет включённых площадок'}</span>
        </div>
        {items.map((i, n) => {
          const [dot, border] = TONE[i.level] || TONE.info
          return (
            <button key={n} type="button" onClick={() => onGo(i.target)} style={{ display: 'flex', gap: 9, padding: 8, borderRadius: 10, border: `1px solid ${border}`,
              background: 'var(--bg-card)', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}>
              <span style={{ marginTop: 4 }}><Dot c={dot} /></span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                <span style={cap}>{i.kind}</span>
                <span style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.42 }}>{i.text}</span>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--accent)' }}>{LINK[i.target?.type] || 'показать'} →</span>
              </span>
            </button>
          )
        })}
        {!items.length && <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: 6 }}>Выводов нет: включите площадки или дождитесь данных.</span>}
      </div>
      <div style={{ ...box, padding: '14px 14px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span style={title14}>Включённые против выключенных</span>
        {cmp.map(g => (
          <span key={g.label} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <Dot c={g.dot} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>{g.label}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{nf(g.fact)}</span>
            </span>
            <span style={{ display: 'block', height: 6, borderRadius: 3, background: 'var(--bg-subtle)' }}>
              <span style={{ display: 'block', height: 6, width: `${g.share}%`, borderRadius: 3, background: g.dot }} /></span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-muted)' }}>{g.note}</span>
          </span>
        ))}
        {!offCount && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Все площадки включены — снимите галочки, чтобы увидеть вклад группы.</span>}
      </div>
    </div>
  )
}

export const cmpGroups = (on, off, k, plan) => {
  const both = (on.fact + off.fact) || 1
  return [
    { label: `Включено · ${on.n}`, dot: 'var(--income)', fact: on.fact, share: on.fact / both * 100,
      note: `план ${nf(plan)} · прогноз ${pf(plan && k.forecast ? k.forecast / plan * 100 : null, 0)} · CTR ${pf(k.ctr, 2)}` },
    { label: `Выключено · ${off.n}`, dot: 'var(--border-hover)', fact: off.fact, share: off.fact / both * 100,
      note: off.n ? `вклад ${pf(off.fact / both * 100, 0)} факта · план ${nf(off.plan)}` : 'все площадки включены' },
  ]
}
