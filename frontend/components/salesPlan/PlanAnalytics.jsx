// Аналитика «Плана продаж» (хендофф 24.10.2026, docs/план продаж.zip §5): сворачиваемая карточка между плитками и таблицей.
// Собрана из тех же «пиксельных» баров, что раздел «Продажи → Аналитика» (`components/charts/PixelBars`, владелец 24.10.2026):
// величина — число ячеек. «Выполнение»: нарастающим итогом, кто держит разрыв, из чего прогноз, прогноз по неделям;
// «Цели»: сезонность целей против факта прошлого года. Расчёты — lib/salesPlan.mjs. Цвета — токены, как в макете.
import { useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { EMPTY, PixelBar, PixelColumn, cellsOf, stack } from '@/components/charts/PixelBars'
import { MONTHS, composition, cumulative, fmtK, fmtSigned, seasonality, weekDelta, whoHolds } from '@/lib/salesPlan.mjs'

const cap = { fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const h = { fontSize: 13.5, fontWeight: 700, color: 'var(--text-primary)' }
const note = { fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }
const MON = { fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', textAlign: 'center' }
const C = { fact: 'var(--income)', work: 'var(--warning)', extra: 'var(--accent-soft)', green: 'var(--accent)', orange: 'var(--accent-soft)' }
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const UP = 14                      // ячеек в столбце — как «Динамика по месяцам»
const tipBox = { position: 'absolute', top: 0, zIndex: 5, pointerEvents: 'none', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 12, boxShadow: 'var(--shadow-modal)', padding: '10px 12px', minWidth: 190, fontSize: 12, color: 'var(--text-secondary)' }

const Legend = ({ items }) => (
  <span style={{ display: 'inline-flex', gap: 12, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-secondary)' }}>
    {items.map(([c, l]) => <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <i style={{ width: 9, height: 9, borderRadius: 2, background: c }} />{l}</span>)}
  </span>
)
const TipRow = ({ c, l, v }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>{c && <i style={{ width: 8, height: 8, borderRadius: 2, background: c }} />}{l}</span>
    <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{v}</b>
  </div>
)

function Cumulative({ total, cur }) {
  const [hov, setHov] = useState(null)
  const { bars, behindFrom, short } = cumulative(total, cur)
  const top = Math.max(1, ...bars.map(b => Math.max(b.fact + b.work + b.extra, b.goal || 0)))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={h}>Нарастающим итогом</span>
        <span style={{ marginLeft: 'auto' }}><Legend items={[[C.fact, 'факт'], [C.work, 'в работе'], [C.extra, 'прогноз'], ['var(--text-primary)', 'цель']]} /></span>
      </div>
      <div style={{ display: 'flex', height: 150 }}>
        {bars.map((b, i) => (
          <div key={b.m} onMouseEnter={() => setHov(i)} onMouseLeave={() => setHov(null)}
            style={{ flex: 1, position: 'relative', background: b.m === cur ? 'var(--accent-tint)' : 'transparent', borderRadius: 6 }}>
            <PixelColumn cells={stack([[b.fact, C.fact], [b.work, C.work], [b.extra, C.extra]], top, UP)} width="62%" />
            {b.goal != null && <i style={{ position: 'absolute', left: '14%', right: '14%', bottom: `calc(${b.goal / top * 100}% - 1px)`, height: 2, background: 'var(--text-primary)', pointerEvents: 'none' }} />}
            {hov === i && (
              <div style={{ ...tipBox, ...(i >= 7 ? { right: 'calc(50% + 10px)' } : { left: 'calc(50% + 10px)' }) }}>
                <div style={{ ...cap, marginBottom: 6 }}>{MONTHS[b.m]} · нарастающим</div>
                <TipRow c={C.fact} l="факт" v={fmtK(b.fact)} /><TipRow c={C.work} l="в работе" v={fmtK(b.work)} />
                {!!b.extra && <TipRow c={C.extra} l="прогноз" v={`+${fmtK(b.extra)}`} />}
                <div style={{ borderTop: '1px solid var(--border-inner)', marginTop: 6, paddingTop: 6 }}><TipRow l="цель" v={fmtK(b.goal)} /></div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex' }}>
        {MONTHS.map((l, m) => <span key={l} style={{ ...MON, flex: 1, color: m === cur ? 'var(--accent-fg)' : 'var(--text-faint)', fontWeight: m === cur ? 700 : 400 }}>{l}</span>)}
      </div>
      <span style={note}>
        {bars[11].goal == null ? 'Цели не заданы — сравнивать не с чем.' : <>
          {behindFrom == null ? 'По прошедшим месяцам идём не ниже накопленной цели.' : `Отстаём от накопленной цели с ${MONTHS_GEN[behindFrom]}.`}{' '}
          {short > 0 ? `С прогнозом к декабрю не хватает ${fmtK(short)} тыс. ₽.` : 'С прогнозом выходим на цель года.'}</>}
      </span>
    </div>
  )
}

const HALF = 12                    // ячеек в каждую сторону от нуля
function WhoHolds({ rows, scope }) {
  const list = whoHolds(rows.filter(r => r.scope === (scope === 'svc' ? 'услуга' : 'продажник')))
  const top = Math.max(1, ...list.map(x => Math.abs(x.gap)))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}><span style={h}>Кто держит разрыв</span>
        <span style={{ ...cap, marginLeft: 'auto', fontWeight: 400 }}>{scope === 'svc' ? 'услуги' : 'продажники'} · прогноз к цели года</span></span>
      {!list.length && <span style={note}>Целей по {scope === 'svc' ? 'услугам' : 'продажникам'} нет.</span>}
      {list.map(x => {
        const n = Math.min(HALF, cellsOf(Math.abs(x.gap), top, HALF))
        const left = Array.from({ length: HALF }, (_, j) => (x.gap < 0 && j >= HALF - n ? 'var(--danger)' : EMPTY))
        const right = Array.from({ length: HALF }, (_, j) => (x.gap > 0 && j < n ? 'var(--income)' : EMPTY))
        return (
          <div key={`${x.scope}${x.key_id}`} title={`${x.name}: ${fmtSigned(x.gap)} тыс. ₽ к цели года`}
            style={{ display: 'grid', gridTemplateColumns: 'minmax(80px, 150px) minmax(80px, 1fr) 72px', gap: 10, alignItems: 'center', fontSize: 12.5 }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.name}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <PixelBar cells={left} height={10} style={{ flex: 1 }} />
              <i style={{ width: 1, height: 14, background: 'var(--text-faint)' }} />
              <PixelBar cells={right} height={10} style={{ flex: 1 }} />
            </span>
            <b style={{ fontFamily: MONO, textAlign: 'right', color: x.gap < 0 ? 'var(--danger-fg)' : 'var(--income-fg)' }}>{fmtSigned(x.gap)}</b>
          </div>
        )
      })}
      <span style={note}>тыс. ₽ · слева недобор, справа перевыполнение</span>
    </div>
  )
}

const LINE = 32                    // ячеек в полосе «из чего прогноз»
function Composition({ total }) {
  const { parts, forecast, goal } = composition(total)
  const scale = Math.max(forecast, goal || 0) || 1
  const look = { fact: [C.fact, 'факт'], work: [C.work, 'в работе'], green: [C.green, 'зелёные'], orange: [C.orange, 'оранжевые × 50 %'] }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={h}>Из чего прогноз</span>
      <span style={{ position: 'relative' }}>
        <PixelBar cells={stack(parts.map(p => [p.v, look[p.k][0]]), scale, LINE)} height={14} />
        {goal != null && <i title={`цель года ${fmtK(goal)}`} style={{ position: 'absolute', left: `calc(${Math.min(1, goal / scale) * 100}% - 1px)`, top: -3, bottom: -3, width: 2, background: 'var(--text-primary)' }} />}
      </span>
      <span style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '4px 24px', fontSize: 11.5, color: 'var(--text-secondary)' }}>
        {parts.map(p => <span key={p.k} title={`${fmtK(p.v)} тыс. ₽`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <i style={{ width: 9, height: 9, borderRadius: 2, background: look[p.k][0] }} />{look[p.k][1]}
          <b style={{ marginLeft: 'auto', fontFamily: MONO, color: 'var(--text-primary)' }}>{Math.round(p.share * 100)} %</b></span>)}
      </span>
    </div>
  )
}

const WK = 8                        // ячеек в столбце недели
function Weeks({ weeks, goal }) {
  const d = weekDelta(weeks)
  const top = Math.max(1, ...(weeks || []).map(w => w.forecast), goal || 0)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--border-inner)', paddingTop: 12 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={h}>Прогноз по неделям</span>
        {d != null && <b style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, color: d >= 0 ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
          {d >= 0 ? '▲' : '▼'} {fmtSigned(d)} за месяц</b>}</span>
      {!weeks?.length ? <span style={note}>Копится с первого ночного снимка — через неделю появится первая точка.</span> : (
        <span style={{ position: 'relative', display: 'flex', height: 64 }}>
          {goal != null && <i title={`цель года ${fmtK(goal)}`} style={{ position: 'absolute', left: 0, right: 0, bottom: `${goal / top * 100}%`, borderTop: '1px dashed var(--text-muted)' }} />}
          {weeks.map((w, i) => (
            <span key={w.week} title={`неделя с ${w.week.slice(8, 10)}.${w.week.slice(5, 7)}: прогноз года ${fmtK(w.forecast)}`} style={{ flex: 1 }}>
              <PixelColumn cells={stack([[w.forecast, i === weeks.length - 1 ? 'var(--accent)' : 'var(--accent-soft)']], top, WK)} width="70%" />
            </span>))}
        </span>
      )}
      <span style={note}>прогноз года на каждый понедельник · пунктир — цель</span>
    </div>
  )
}

const SEA = 10                      // ячеек в столбце сезонности
function Seasonality({ goals, prevDone, year }) {
  const s = seasonality(goals, prevDone)
  const top = Math.max(0.01, ...s.rows.map(r => Math.max(r.goal, r.prev || 0)))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={h}>Сезонность целей</span>
        <Legend items={[['var(--accent)', `цели ${year}`], ['var(--accent-soft)', `факт ${year - 1}`], ['var(--warning)', 'перекос > 2 п. п.']]} />
        <span style={{ ...note, marginLeft: 'auto' }}>{!s.hasGoals ? 'целей пока нет' : !s.hasPrev ? `факта ${year - 1} нет — сравнивать не с чем`
          : s.worst ? `сильнее всего расходится ${MONTHS[s.worst.m]}: ${Math.round(s.worst.goal * 100)} % цели против ${Math.round(s.worst.prev * 100)} % факта`
            : 'распределение близко к прошлому году'}</span>
      </div>
      <div style={{ display: 'flex', gap: 10, height: 110 }}>
        {s.rows.map(r => (
          <span key={r.m} title={`${MONTHS[r.m]}: цель ${Math.round(r.goal * 1000) / 10} % года` + (r.prev == null ? '' : ` · факт ${year - 1} ${Math.round(r.prev * 1000) / 10} %`)}
            style={{ flex: 1, display: 'flex', gap: 3 }}>
            <PixelColumn cells={stack([[r.goal, r.skew ? 'var(--warning)' : 'var(--accent)']], top, SEA)} width="100%" />
            {r.prev != null && <PixelColumn cells={stack([[r.prev, 'var(--accent-soft)']], top, SEA)} width="100%" />}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        {MONTHS.map(l => <span key={l} style={{ ...MON, flex: 1 }}>{l}</span>)}
      </div>
    </div>
  )
}

export default function PlanAnalytics({ open, onToggle, mode, rows, scope, cur, year, weeks, goalsOfTotal, prevTotal }) {
  const total = rows.find(r => r.scope === 'общий')
  if (!total) return null
  const yearGoal = (() => { const g = total.months.filter(m => m.goal != null); return g.length ? g.reduce((a, m) => a + m.goal, 0) : null })()
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16 }}>
      <button type="button" onClick={onToggle} style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', border: 0, background: 'transparent',
        padding: '12px 18px', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}>
        <span style={cap}>{open ? '▾' : '▸'}&nbsp; аналитика</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{mode === 'run' ? `общая цель · ${year}` : 'доля каждого месяца в цели года'}</span>
      </button>
      {open && (mode === 'run' ? (
        // Колонки переносятся на узком экране (1.7 : 1 : 1 на широком, как в макете) — иначе числа наезжают на соседнюю
        <div style={{ display: 'flex', flexWrap: 'wrap', borderTop: '1px solid var(--border-inner)' }}>
          <div style={{ flex: '1.7 1 520px', minWidth: 0, padding: '14px 18px' }}><Cumulative total={total} cur={cur} /></div>
          <div style={{ flex: '1 1 340px', minWidth: 0, padding: '14px 18px', borderLeft: '1px solid var(--border-inner)' }}><WhoHolds rows={rows} scope={scope} /></div>
          <div style={{ flex: '1 1 320px', minWidth: 0, padding: '14px 18px', borderLeft: '1px solid var(--border-inner)', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Composition total={total} /><Weeks weeks={weeks} goal={yearGoal} />
          </div>
        </div>
      ) : (
        <div style={{ padding: '14px 18px', borderTop: '1px solid var(--border-inner)' }}>
          <Seasonality goals={goalsOfTotal} prevDone={prevTotal?.months.map(c => c.done)} year={year} />
        </div>
      ))}
    </div>
  )
}
