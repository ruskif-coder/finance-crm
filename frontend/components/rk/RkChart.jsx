// График «Разбора РК»: по времени — линия выбранной метрики, сравнение, клики (правая шкала), уники по модели,
// «площадок в работе» ступенькой и события под осью; по площадкам/креативам — горизонтальный рейтинг.
import { useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { niceMax } from '@/lib/salesFormat'
import { nf, rub, pf, sg, dm, cap, EV_COLOR, WR_TONE, pctTone, Dot } from './rkUi'

const H = 220
const fmtAxis = (v, metric, isPct) => (isPct ? Math.round(v) + '%' : metric === 'spend' || metric === 'cpm' ? nf(v) : v >= 1000 ? Math.round(v / 1000) + 'k' : nf(v))

export function fmtMetric(v, metric, source) {
  if (v == null) return '—'
  if (metric === 'shows' && source === 'diff') return sg(v)
  if (metric === 'ctr') return pf(v, 2)
  if (metric === 'plan') return pf(v, 0)
  if (metric === 'spend' || metric === 'cpm') return rub(v)
  return nf(v)
}

export function TimeChart({ rows, metric, source, cmp, events, on, tech, setTech, onDay, pickNote, inRange, nPlaces, wrLimit, total }) {
  const [hover, setHover] = useState(null)
  const isPct = metric === 'ctr' || metric === 'plan' || (metric === 'shows' && source === 'diff')
  const showsOur = metric === 'shows' && source === 'our'
  const cmpOf = (r) => {
    if (cmp === 'plan') return showsOur || (metric === 'shows' && source === 'wr') ? r.plan : metric === 'plan' ? 100 : null
    if (cmp === 'need') return showsOur ? r.need : null
    if (cmp === 'week') return r.prev
    if (cmp === 'wr') return showsOur ? (r.t.wr || null) : null
    return null
  }
  const vals = rows.flatMap(r => [Math.abs(r.value || 0), Math.abs(cmpOf(r) || 0), cmp === 'onoff' ? (r.value || 0) + (r.off || 0) : 0])
  const max = niceMax(Math.max(1, ...vals) * 1.08)
  const n = rows.length
  const X = (i) => ((i + 0.5) / n * 1000).toFixed(1)
  const Y = (v, m = max) => (H - Math.min(1, Math.abs(v) / m) * H).toFixed(1)
  const pts = (f, m) => rows.map((r, i) => { const v = f(r); return v == null ? null : `${X(i)},${Y(v, m)}` }).filter(Boolean).join(' ')
  const line = pts(r => (r.future ? null : r.value))
  const past = rows.map((r, i) => (r.future || r.value == null ? null : i)).filter(i => i != null)
  const area = past.length > 1 ? `${X(past[0])},${H} ${line} ${X(past[past.length - 1])},${H}` : ''
  const dspLine = showsOur ? pts(r => (r.future ? null : r.t.dsp)) : ''
  const cmpLine = pts(cmpOf)
  const offLine = cmp === 'onoff' ? pts(r => (r.future ? null : r.off)) : ''
  const clkMax = showsOur ? niceMax(Math.max(1, ...rows.map(r => (r.future ? 0 : r.t.clk))) * 1.15) : 0
  const clkLine = showsOur ? pts(r => (r.future ? null : r.t.clk), clkMax) : ''
  const uniLine = showsOur ? pts(r => (r.future || !r.t.uni ? null : r.t.uni)) : ''
  const NP = Math.max(1, nPlaces)
  const step = rows.flatMap((r, i) => (r.active == null ? [] : [`${(i / n * 1000).toFixed(1)},${(H - r.active / NP * H * 0.92).toFixed(1)}`, `${((i + 1) / n * 1000).toFixed(1)},${(H - r.active / NP * H * 0.92).toFixed(1)}`])).join(' ')
  const lastA = rows.filter(r => r.active != null).slice(-1)[0]
  const lineColor = source === 'diff' ? 'var(--danger)' : metric === 'spend' || metric === 'cpm' ? 'var(--accent)' : 'var(--income)'
  const cmpColor = cmp === 'wr' ? 'var(--bank-sovkom)' : cmp === 'week' ? 'var(--violet-fg)' : 'var(--accent)'
  const evOf = (r) => events.filter(e => r.days.includes(e.date))
  const hr = rows.find(r => r.key === hover)
  const yAxis = [0, 0.25, 0.5, 0.75, 1]
  const freq = (() => { const f = rows.reduce((a, r) => a + (r.future ? 0 : r.t.fact), 0), u = rows.reduce((a, r) => a + (r.future ? 0 : r.t.uni), 0); return u ? f / u : null })()
  const legend = [
    showsOur ? ['факт DSP + Adfox', 'var(--income)', 14, 3] : [fmtLegend(metric, source), lineColor, 14, 3],
    showsOur && ['в т. ч. DSP', 'var(--income-border)', 14, 2],
    cmpLine && [cmp === 'plan' ? (metric === 'plan' ? '100 % плана' : 'план') : cmp === 'need' ? 'нужно в день' : cmp === 'week' ? 'неделей раньше' : 'Weborama', cmpColor, 12, 2],
    offLine && ['выключенные', 'var(--border-hover)', 14, 2],
    uniLine && [`уники по модели${freq ? ' · частота ' + freq.toFixed(1).replace('.', ',') : ''}`, 'var(--accent-soft)', 14, 2],
    clkLine && ['клики · правая шкала', 'var(--accent)', 14, 2],
    step && [`площадок в работе · шкала 0–${NP}`, 'var(--text-muted)', 14, 2],
  ].filter(Boolean)
  const R = hr ? hr.t : null
  // Строка над графиком: ПЕРВОЙ — выбранная метрика (за день под курсором или за весь отрезок), рядом сравнение,
  // дальше разбивка без повтора той же величины (владелец 12.10.2026: «при наведении — значение метрики»).
  const cmpLabel = { plan: metric === 'plan' ? '100 % плана' : 'план', need: 'нужно', week: 'неделей раньше', wr: 'Weborama', onoff: 'выключенные' }[cmp]
  const cmpVal = hr ? (cmp === 'onoff' ? hr.off : cmpOf(hr)) : null
  const fmtCmp = (v) => (cmp === 'wr' || ((cmp === 'plan' || cmp === 'need') && showsOur) ? nf(v) : fmtMetric(v, metric, source))
  const skip = { shows: source === 'our' ? 'факт' : source === 'wr' ? 'WR' : null, clicks: 'клики', offered: 'предл.', spend: 'расход' }[metric]
  const rest = R ? [['факт', nf(R.fact), 'var(--income-fg)'], ['DSP', nf(R.dsp)], ['Adfox', nf(R.adf)], ['WR', nf(R.wr), 'var(--text-secondary)'],
    ['план', nf(hr.plan), 'var(--accent)'], ['площадок', hr.active != null ? `${hr.active} из ${nPlaces}` : '—'], ['клики', nf(R.clk), 'var(--accent)'],
    ['уники', nf(R.uni), 'var(--accent-fg)'], ['предл.', R.off ? nf(R.off) : '—', 'var(--text-secondary)'], ['расход', rub(R.spend), 'var(--text-secondary)']]
    .filter(([k]) => k !== skip && !(k === 'план' && cmp === 'plan' && showsOur)) : []
  return (
    <>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end', marginTop: -6 }}>
        {legend.map(([l, c, w, h]) => (
          <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            <span style={{ width: w, height: h, borderRadius: 2, background: c }} />{l}</span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, minHeight: 18, padding: '6px 10px', background: 'var(--bg-tint)', borderRadius: 9, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent-fg)' }}>{hr ? (hr.days.length > 1 ? `${dm(hr.days[0])}–${dm(hr.days[hr.days.length - 1])}` : dm(hr.key)) : 'период'}</span>
        {(!hr || !hr.future) && (
          <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{fmtLegend(metric, source)}{' '}
            <b style={{ fontSize: 13, color: lineColor }}>{fmtMetric(hr ? hr.value : total, metric, source)}</b></span>
        )}
        {hr && !hr.future && cmpVal != null && (
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{cmpLabel} <b style={{ color: cmpColor }}>{fmtCmp(cmpVal)}</b></span>
        )}
        {hr && !hr.future && rest.map(([k, v, c]) => (
          <span key={k} style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{k} <b style={{ color: c || 'var(--text-primary)' }}>{v}</b></span>
        ))}
        {hr && hr.future && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>план <b style={{ color: 'var(--accent)' }}>{nf(hr.plan)}</b> · нужно <b style={{ color: 'var(--accent)' }}>{nf(hr.need)}</b></span>}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '46%' }}>
          {hr ? (evOf(hr).filter(e => tech || e.kind !== 'tech').map(e => e.text).join(' · ') || 'событий нет') : 'наведите на день — разбивка и события'}</span>
      </div>
      <div onMouseLeave={() => setHover(null)} style={{ display: 'grid', gridTemplateColumns: '52px minmax(0,1fr) 44px', gap: 8 }}>
        <div style={{ position: 'relative', height: 280 }}>
          {yAxis.map(f => <span key={f} style={{ position: 'absolute', right: 0, bottom: `${f * 100}%`, transform: 'translateY(50%)', ...{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' } }}>{fmtAxis(f * max, metric, isPct)}</span>)}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <div style={{ position: 'relative', height: 280, display: 'flex', alignItems: 'flex-end', borderBottom: '1px solid var(--border-inner)' }}>
            {yAxis.map(f => <span key={f} style={{ position: 'absolute', left: 0, right: 0, bottom: `${f * 100}%`, height: 1, background: 'var(--border-row)' }} />)}
            {source === 'diff' && metric === 'shows' && (
              <span title={`порог ±${wrLimit} %`} style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${Math.min(100, wrLimit / max * 100)}%`, background: 'var(--bg-subtle)' }} />
            )}
            <svg viewBox={`0 0 1000 ${H}`} preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible', pointerEvents: 'none' }}>
              {area && <polygon points={area} fill="var(--income)" fillOpacity="0.08" />}
              {offLine && <polyline points={offLine} fill="none" stroke="var(--border-hover)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
              {cmpLine && <polyline points={cmpLine} fill="none" stroke={cmpColor} strokeWidth="2" strokeDasharray={cmp === 'plan' ? '0' : '5 4'} vectorEffect="non-scaling-stroke" />}
              {dspLine && <polyline points={dspLine} fill="none" stroke="var(--income)" strokeWidth="1.5" strokeOpacity="0.45" vectorEffect="non-scaling-stroke" />}
              {step && <polyline points={step} fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />}
              {uniLine && <polyline points={uniLine} fill="none" stroke="var(--accent-soft)" strokeWidth="2" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />}
              {clkLine && <polyline points={clkLine} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
              {line && <polyline points={line} fill="none" stroke={lineColor} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
            </svg>
            {lastA && (
              <span style={{ position: 'absolute', right: 4, bottom: `${lastA.active / NP * 92}%`, transform: 'translateY(-4px)', fontFamily: MONO, fontSize: 9, fontWeight: 700,
                color: 'var(--text-muted)', background: 'var(--bg-card)', padding: '0 3px', borderRadius: 3, pointerEvents: 'none', zIndex: 1 }}>{lastA.active} из {NP} площ.</span>
            )}
            {rows.map(r => {
              const hot = hover === r.key
              return (
                <span key={r.key} onMouseEnter={() => setHover(r.key)} onClick={() => onDay(r)}
                  style={{ position: 'relative', flex: '1 1 0', minWidth: 0, height: '100%', cursor: pickNote ? 'crosshair' : 'pointer',
                    background: inRange(r.key) ? 'var(--accent-tint)' : 'transparent', borderRadius: 3 }}>
                  {hot && <span style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1px dashed var(--accent-soft)' }} />}
                  {!r.future && r.value != null && (hot || n <= 6) && (
                    <span style={{ position: 'absolute', left: '50%', bottom: `${Math.min(100, Math.abs(r.value) / max * 100)}%`, width: hot ? 9 : 7, height: hot ? 9 : 7,
                      transform: 'translate(-50%,50%)', borderRadius: 2, background: lineColor, boxShadow: '0 0 0 2px var(--bg-card)' }} />
                  )}
                  {/* Значение метрики у точки под курсором (владелец 12.10.2026) */}
                  {hot && !r.future && r.value != null && (
                    <span style={{ position: 'absolute', left: '50%', bottom: `calc(${Math.min(100, Math.abs(r.value) / max * 100)}% + 10px)`,
                      transform: 'translateX(-50%)', padding: '1px 6px', borderRadius: 5, background: 'var(--bg-card)', border: `1px solid ${lineColor}`,
                      fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 2 }}>
                      {fmtMetric(r.value, metric, source)}</span>
                  )}
                </span>
              )
            })}
          </div>
          <div style={{ display: 'flex' }}>
            {rows.map((r, i) => {
              const ev = evOf(r)
              const imp = ev.filter(e => e.kind !== 'tech'), tk = ev.filter(e => e.kind === 'tech')
              const hot = hover === r.key
              const label = r.days.length > 1 ? `${dm(r.days[0])}–${dm(r.days[r.days.length - 1])}` : i === 0 || hot ? dm(r.key) : r.key.slice(8, 10)
              return (
                <span key={r.key} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                  <span style={{ fontFamily: MONO, fontSize: 9, color: hot ? 'var(--accent)' : r.future ? 'var(--text-disabled)' : 'var(--text-faint)', fontWeight: hot ? 700 : 400,
                    whiteSpace: 'nowrap', background: 'var(--bg-card)', padding: '0 2px', position: 'relative', zIndex: 1 }}>{label}</span>
                  <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, minHeight: 24 }}>
                    {imp.slice(0, 3).map((e, j) => <span key={j} title={e.text} style={{ width: 8, height: 8, borderRadius: 2, background: EV_COLOR[e.kind], opacity: !e.placement_id || on[e.placement_id] ? 1 : 0.3 }} />)}
                    {tech && tk.length > 0 && <span title={tk.map(e => e.text).join('\n')} style={{ fontFamily: MONO, fontSize: 8, color: 'var(--text-faint)' }}>+{tk.length}</span>}
                  </span>
                </span>
              )
            })}
          </div>
        </div>
        <div style={{ position: 'relative', height: 280 }}>
          {clkLine && yAxis.map(f => <span key={f} style={{ position: 'absolute', left: 0, bottom: `${f * 100}%`, transform: 'translateY(50%)', fontFamily: MONO, fontSize: 9, color: 'var(--accent)' }}>{nf(f * clkMax)}</span>)}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', paddingTop: 2 }}>
        {[['запуск', EV_COLOR.start], ['пауза', EV_COLOR.pause], ['статус РК', EV_COLOR.campaign], ['ночной пересчёт', EV_COLOR.bidder], ['темп размещения', EV_COLOR.boost]].map(([l, c]) => (
          <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}><Dot c={c} s={8} />{l}</span>
        ))}
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }}>
          <input type="checkbox" checked={tech} onChange={e => setTech(e.target.checked)} />
          технические · ссылки нацеливания ({events.filter(e => e.kind === 'tech').length})</label>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{pickNote || 'клик по дню — его площадки'}</span>
      </div>
    </>
  )
}

const fmtLegend = (metric, source) => ({ shows: source === 'wr' ? 'показы Weborama' : source === 'diff' ? 'расхождение с Weborama' : 'показы, наш факт',
  clicks: 'клики', ctr: 'CTR', offered: 'предложено сетью', plan: '% плана', spend: 'расход, ₽', cpm: 'CPM, ₽' }[metric])

/** Рейтинг для разрезов площадка / креатив: горизонтальные полосы с тиком плана. */
export function RankChart({ rows, metric, source, onRow, focus }) {
  const key = { shows: source === 'wr' ? 'wr' : source === 'diff' ? 'wrd' : 'fact', clicks: 'clk', ctr: 'ctr', offered: 'off', plan: 'pct', spend: 'spend', cpm: 'cpm' }[metric]
  const showsOur = metric === 'shows' && source === 'our'
  const max = Math.max(1, ...rows.map(r => Math.abs(r[key] || 0)), ...rows.map(r => (showsOur ? r.plan || 0 : 0)))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 340, overflowY: 'auto' }}>
      {rows.map(r => {
        const v = r[key]
        const neg = source === 'diff' && v < 0
        return (
          <span key={r.id} onClick={() => r.drill && onRow(r.drill)}
            style={{ display: 'grid', gridTemplateColumns: '170px minmax(0,1fr) 100px', gap: 10, alignItems: 'center', padding: '3px 6px', borderRadius: 7,
              background: focus === r.id ? 'var(--accent-tint)' : 'transparent', cursor: r.drill ? 'pointer' : 'default' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.set ? `${r.set} · ${r.label}` : r.label}</span>
            <span style={{ position: 'relative', height: 12, background: 'var(--bg-subtle)', borderRadius: 3 }}>
              <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, Math.abs(v || 0) / max * 100)}%`, borderRadius: 3,
                background: neg ? 'var(--danger)' : metric === 'spend' || metric === 'cpm' ? 'var(--accent)' : metric === 'offered' ? 'var(--border-hover)' : 'var(--income)' }} />
              {metric === 'offered' && r.offPct != null && (
                <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, r.offPct / 100 * (r.off / max) * 100)}%`, borderRadius: 3, background: 'var(--income)' }} />
              )}
              {showsOur && !!r.plan && <span style={{ position: 'absolute', top: -2, bottom: -2, left: `${Math.min(99, r.plan / max * 100)}%`, width: 2, borderRadius: 1, background: 'var(--accent)' }} />}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap',
              color: metric === 'plan' ? pctTone(v) : source === 'diff' ? WR_TONE[r.wrLevel] || 'var(--text-primary)' : 'var(--text-primary)' }}>{fmtMetric(v, metric, source)}</span>
          </span>
        )
      })}
      {!rows.length && <span style={{ ...cap, padding: 20, textAlign: 'center' }}>в этом срезе нет данных</span>}
    </div>
  )
}
