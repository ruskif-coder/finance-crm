/** Накопительный остаток: факт по оплаченным до сегодня + 3 сценария на 4 месяца (README хендоффа, п. 9). Геометрия —
 *  из макета: SVG с preserveAspectRatio="none", подписи HTML поверх, линии vector-effect: non-scaling-stroke. */
import { useState } from 'react'
import { CARD, CAPS, H, MONO, mln2, tys } from './kit'
import { MON, parseDate, ddmm } from './model'

const SC = [['contract', 'По сроку', 'var(--ok)', 'все платят в срок по отсрочке реестра, просроченное приходит сейчас; только заведённые плановые операции'],
  ['real', 'Как платят на деле', 'var(--attn)', 'поступление в обычную дату клиента: начало следующего периода + его среднее время оплаты'],
  ['careful', 'Осторожно', 'var(--bad)', 'как платят на деле, но опоздавшее даже против привычки клиента не вернётся']]
const AFTER = ['конец текущего месяца', 'следующий месяц', 'через месяц', 'через два месяца']

function niceStep(span) {
  for (const s of [0.5e6, 1e6, 2e6, 5e6, 10e6, 20e6, 50e6]) if (span / s <= 7) return s
  return 100e6
}

export default function Cumulative({ data, sc, thr, mode }) {
  const [cs, setCs] = useState({ contract: 1, real: 1, careful: 1 })
  const today = parseDate(data.today)
  const fact = data.months.slice(1, 12).map(m => m.balance_end)
  const TV = data.balance_total
  const TI = 10 + today.getDate() / new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  const all = [...fact, TV, ...SC.flatMap(z => sc[z[0]]), 0, thr]
  const step = niceStep(Math.max(...all) - Math.min(...all))
  const YMAX = Math.ceil(Math.max(...all) / step) * step + step * 0.3
  const YMIN = Math.floor(Math.min(...all) / step) * step - step * 0.3
  const yy = v => (YMAX - v) / (YMAX - YMIN) * 240
  const xx = i => i / 14 * 1000
  const pc = v => `${(yy(v) / 240 * 100).toFixed(2)}%`
  const pts = a => a.map(q => `${xx(q[0]).toFixed(1)},${yy(q[1]).toFixed(1)}`)
  const factP = fact.map((v, i) => [i, v]).concat([[TI, TV]])
  const scP = k => [[TI, TV]].concat(sc[k].map((v, j) => [11 + j, v]))
  const vis = SC.filter(z => cs[z[0]])
  const src = vis.length ? vis : SC
  const fanTop = [0, 1, 2, 3].map(j => [11 + j, Math.max(...src.map(z => sc[z[0]][j]))])
  const fanBot = [0, 1, 2, 3].map(j => [11 + j, Math.min(...src.map(z => sc[z[0]][j]))])
  const ticks = []
  for (let v = Math.ceil(YMIN / step) * step; v <= YMAX; v += step) ticks.push(v)
  const monthAt = i => new Date(today.getFullYear(), today.getMonth() - 11 + i, 1)
  return (
    <div data-motion="rise" style={{ ...CARD, padding: '20px 22px 16px', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={H}>Накопительный остаток</span>
        <span style={CAPS}>факт по оплаченным операциям до {ddmm(today)} · дальше — сценарии на заведённых плановых операциях</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {SC.map(z => {
            const on = !!cs[z[0]], end = sc[z[0]][3]
            return (
              <button type="button" key={z[0]} title={z[3]} onClick={() => setCs(x => ({ ...x, [z[0]]: x[z[0]] ? 0 : 1 }))}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 10px', borderRadius: 9, fontFamily: 'inherit',
                  border: `1px solid ${on ? 'var(--border-hover)' : 'var(--border-card)'}`, background: on ? 'var(--bg-card)' : 'transparent', opacity: on ? 1 : 0.45,
                  fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', color: 'var(--text-primary)' }}>
                <span style={{ width: 16, borderTop: `2.5px dashed ${z[2]}` }} />{z[1]}{' '}
                <b style={{ fontFamily: MONO, color: end < 0 ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{mln2(end)}</b>
              </button>
            )
          })}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '56px minmax(0,1fr) 92px', gap: '0 10px' }}>
        <div style={{ position: 'relative', height: 240 }}>
          {ticks.map(v => <span key={v} style={{ position: 'absolute', right: 0, top: pc(v), transform: 'translateY(-50%)', fontFamily: MONO, fontSize: 9.5,
            color: v === 0 ? 'var(--bad-fg)' : 'var(--text-faint)', whiteSpace: 'nowrap' }}>{v === 0 ? '0' : `${v < 0 ? '−' : ''}${Math.abs(v) / 1e6} млн`}</span>)}
        </div>
        <div style={{ position: 'relative', height: 240 }}>
          <svg viewBox="0 0 1000 240" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' }} aria-hidden="true">
            <rect x="0" y="0" width={xx(TI)} height="240" fill="var(--bg-subtle)" opacity="0.55" />
            <line x1="0" x2="1000" y1={yy(thr)} y2={yy(thr)} stroke="var(--bad-border)" strokeWidth="1" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
            <line x1="0" x2="1000" y1={yy(0)} y2={yy(0)} stroke="var(--bad)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            <polygon points={pts([[TI, TV]].concat(fanTop)).concat(pts(fanBot.slice().reverse())).join(' ')} fill="var(--attn-tint)" opacity="0.7" />
            {SC.map(z => <path key={z[0]} d={`M${pts(scP(z[0])).join(' L')}`} fill="none" stroke={z[2]} strokeWidth={z[0] === mode ? 3.2 : 2}
              strokeDasharray="7 5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" opacity={cs[z[0]] ? 1 : 0} />)}
            <path d={`M${pts(factP).join(' L')}`} fill="none" stroke="var(--text-primary)" strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            <line x1={xx(TI)} x2={xx(TI)} y1="0" y2="240" stroke="var(--text-primary)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          </svg>
          <span style={{ position: 'absolute', left: `${(TI / 14 * 100).toFixed(2)}%`, top: pc(TV), width: 10, height: 10, margin: '-5px 0 0 -5px', borderRadius: '50%',
            background: 'var(--text-primary)', boxShadow: '0 0 0 3px var(--bg-card)' }} />
          <span style={{ position: 'absolute', left: `${(TI / 14 * 100).toFixed(2)}%`, top: 0, transform: 'translateX(-50%)', padding: '2px 7px', borderRadius: 6,
            background: 'var(--hot)', color: 'var(--hot-fg)', fontFamily: MONO, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap' }}>сегодня · {mln2(TV)}</span>
          <span style={{ position: 'absolute', left: 4, top: pc(0), transform: 'translateY(-120%)', fontSize: 10.5, fontWeight: 700, color: 'var(--bad-fg)' }}>безубыточность · 0</span>
          <span style={{ position: 'absolute', left: 4, top: pc(thr), transform: Math.abs(yy(thr) - yy(0)) < 14 ? 'translateY(-260%)' : 'translateY(-120%)', fontSize: 10.5, color: 'var(--bad-fg)' }}>неснижаемый · {tys(thr)}</span>
          <span style={{ position: 'absolute', left: 8, bottom: 6, ...CAPS }}>факт</span>
          <span style={{ position: 'absolute', right: 8, bottom: 6, ...CAPS }}>прогноз</span>
        </div>
        <div style={{ position: 'relative', height: 240 }}>
          {SC.map(z => <span key={z[0]} style={{ position: 'absolute', left: 0, top: pc(sc[z[0]][3]), transform: 'translateY(-50%)', display: 'flex', alignItems: 'center',
            gap: 6, opacity: cs[z[0]] ? 1 : 0 }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: z[2] }} />
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: sc[z[0]][3] < 0 ? 'var(--bad-fg)' : 'var(--text-primary)', whiteSpace: 'nowrap' }}>{mln2(sc[z[0]][3])}</span></span>)}
        </div>
        <span />
        <div style={{ position: 'relative', height: 28 }}>
          {Array.from({ length: 15 }, (_, i) => {
            const m = monthAt(i)
            return (
              <span key={i} style={{ position: 'absolute', left: `${(i / 14 * 100).toFixed(2)}%`, top: 6, transform: 'translateX(-50%)', display: 'flex',
                flexDirection: 'column', alignItems: 'center', fontSize: 11, color: i > 10 ? 'var(--text-secondary)' : 'var(--text-muted)', fontWeight: i === 11 ? 700 : 500,
                whiteSpace: 'nowrap' }}>{MON[m.getMonth()]}
                <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{m.getMonth() === 0 ? m.getFullYear() : ''}</span></span>
            )
          })}
        </div>
        <span />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
        {SC.map(z => {
          const v = sc[z[0]], k = v.findIndex(x => x < 0), end = monthAt(14)
          return (
            <div key={z[0]} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ flex: '0 0 18px', marginTop: 7, borderTop: `2.5px dashed ${z[2]}` }} />
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{z[1]} · к {MON[end.getMonth()]} {mln2(v[3])}</span>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                  {k < 0 ? 'Ниже нуля не уходит. ' : `Уходит ниже нуля: ${AFTER[k]}, минимум ${mln2(Math.min(...v))}. `}{z[3][0].toUpperCase() + z[3].slice(1)}.</span>
              </span>
            </div>
          )
        })}
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Регулярных платежей (зарплата, налоги, кредит по графику) в системе пока нет шаблонами — в сценариях их нет, прогноз оптимистичнее жизни. Плановые оплаты без даты списаны сразу.</span>
    </div>
  )
}
