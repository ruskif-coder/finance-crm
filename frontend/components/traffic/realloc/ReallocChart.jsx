// Окно «Перераспределить объём» (хендофф 26.10.2026): «Динамика по дням» и история перераспределений РК.
import { MONO } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'
import { fmtDayTime } from '@/lib/dates'

const nf = (v) => grp(Math.round(v || 0))
const pct1 = (v) => (v == null ? '—' : `${v.toFixed(1).replace('.', ',')} %`)
const dd = (iso) => iso.slice(8, 10)
const ddmm = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`
const LEG = [['var(--accent)', 'факт'], ['var(--danger)', 'ниже плана'], ['var(--border-hover)', 'нужно до'], ['var(--accent-border)', 'нужно после']]

export function ReallocChart({ c, scopeName, onClear, changed }) {
  const hp = (v) => `${Math.min(100, (v || 0) / c.max * 100).toFixed(1)}%`
  const note = c.cNA > c.cCan
    ? `После переноса нужно ${nf(c.cNA)} в сутки — выше, чем сеть может (${nf(c.cCan)})`
    : changed ? `Нужно в сутки ${nf(c.cNB)} → ${nf(c.cNA)}, сеть может ${nf(c.cCan)}` : 'Изменений нет — внесите правки, чтобы увидеть эффект'
  const now = c.pctNow
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', border: '1px solid var(--border-card)', borderRadius: 14, minWidth: 0 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13.5, fontWeight: 700 }}>Динамика по дням · {scopeName || 'вся РК'}</span>
        {scopeName ? <span onClick={onClear} style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>← вся РК</span>
          : <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>клик по площадке в таблице — её данные</span>}
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontSize: 10.5, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
          {LEG.map(([col, t]) => <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: col }} />{t}</span>)}
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 10, borderTop: '2px dashed var(--text-secondary)' }} />план в сутки</span>
        </span>
      </span>
      <div style={{ display: 'flex', gap: 2, height: 120, alignItems: 'flex-end' }}>
        {c.bars.map(b => (
          <span key={b.dt} title={b.future
            ? `${ddmm(b.dt)} · остаток флайта · нужно до ${nf(b.before)} · после ${nf(b.after)} · сеть может ${nf(c.cCan)}`
            : `${ddmm(b.dt)} · план дня ${nf(b.goal)} · факт ${nf(b.fact)} · выполнение ${b.goal ? Math.round(b.fact / b.goal * 100) : 0} %`}
            style={{ position: 'relative', flex: '1 1 0', minWidth: 0, height: '100%', display: 'flex', gap: 1, alignItems: 'flex-end',
              background: b.future ? 'var(--bg-tint)' : 'transparent', borderRadius: 2 }}>
            <span style={{ flex: 1, height: hp(b.future ? b.before : b.fact), borderRadius: '2px 2px 0 0',
              background: b.future ? 'var(--border-hover)' : b.low ? 'var(--danger)' : 'var(--accent)' }} />
            {b.future && <span style={{ flex: 1, height: hp(b.after), borderRadius: '2px 2px 0 0', background: b.over ? 'var(--danger-border)' : 'var(--accent-border)' }} />}
            {/* план дня: прошедшие — цель по остатку (как стена дней дашборда), будущие — ровный план РК для ориентира */}
            <span style={{ position: 'absolute', left: 0, right: 0, bottom: hp(b.future ? c.dayPlan : b.goal), borderTop: '2px dashed var(--text-secondary)', opacity: 0.55 }} />
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 2 }}>
        {c.bars.map(b => (
          <span key={b.dt} style={{ flex: '1 1 0', minWidth: 0, textAlign: 'center', fontFamily: MONO, fontSize: 8.5,
            color: b.future ? 'var(--accent-fg)' : 'var(--text-faint)', fontWeight: b.future ? 700 : 500 }}>{dd(b.dt)}</span>))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', paddingTop: 6, borderTop: '1px solid var(--border-row)' }}>
        {[['план в сутки', nf(c.dayPlan), 'var(--text-primary)'], ['факт в среднем', nf(c.avg), 'var(--accent-fg)'],
          ['выполнение на сегодня', pct1(now), now == null ? 'var(--text-muted)' : now < 90 ? 'var(--danger-fg)' : now < 97 ? 'var(--warning-fg)' : 'var(--income-fg)'],
          ['прогноз к концу', pct1(c.forecast), 'var(--text-primary)']].map(([k, v, fg]) => (
          <span key={k} style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>{k}</span>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: fg }}>{v}</span>
          </span>))}
      </div>
      <span style={{ fontSize: 11.5, color: c.cNA > c.cCan ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{note}</span>
    </div>
  )
}

// Высоту ряда задаёт график: история лежит поверх ячейки и прокручивается внутри, иначе длинный журнал
// раздувает неподвижный низ окна и съедает место у таблицы площадок.
export function ReallocHistory({ code, items }) {
  return (
    <div style={{ position: 'relative', minWidth: 0, minHeight: 160 }}>
    <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, padding: '12px 14px',
      border: '1px solid var(--border-card)', borderRadius: 14 }}>
      <span style={{ fontSize: 13.5, fontWeight: 700 }}>История перераспределений · {code}</span>
      {!items.length && <span style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 6 }}>Перераспределений ещё не было</span>}
      {items.map((h, i) => (
        <span key={i} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{fmtDayTime(h.at)}</span>
            <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>{h.who || '—'}</span>
            {h.moved != null && <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{nf(h.moved)}</span>}
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{h.what}</span>
          {!!h.why && <span style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>«{h.why}»</span>}
        </span>
      ))}
    </div>
    </div>
  )
}
