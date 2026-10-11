// Вкладки аналитики «Разбора РК»: будни/выходные, Δ Weborama по дням, предложено-не взято, прошлый флайт.
// Только визуализация для выводов: правило биддера по ним не меняется (владелец 11.10.2026).
import { useState } from 'react'
import { MONO, Seg } from '@/components/salesTableKit'
import { DOW, dowTable, wrByDay, gapTable, prevCompare } from '@/lib/rkAnalysisSlices.mjs'
import { nf, pf, sg, pp, dm, box, title14, cap, heat } from './rkUi'

const TABS = [['dow', 'будни / выходные'], ['wr', 'Δ Weborama по дням'], ['gap', 'предложено, не взято'], ['prev', 'прошлый флайт']]

export default function RkAnalytics({ ix, ids, prev, onPrev }) {
  const [tab, setTab] = useState('dow')
  const note = { dow: 'средний факт в день недели · цвет — отклонение от среднего площадки',
    wr: `наш факт против Weborama по дням · порог ±${ix.head.wr_limit || 10} % из целей сделки`,
    gap: ix.offerFrom ? `с ${dm(ix.offerFrom)} · доля предложенного сетью, которую DSP не взяла` : 'DSP ещё не отдавала «предложено»',
    prev: 'по номеру дня флайта, те же площадки' }[tab]
  return (
    <div style={{ ...box, padding: '12px 16px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={title14}>Аналитика</span>
        <Seg value={tab} opts={TABS} onPick={setTab} />
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{note}</span>
      </div>
      {!ids.length && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Нет включённых площадок.</span>}
      {!!ids.length && tab === 'dow' && <Dow ix={ix} ids={ids} />}
      {!!ids.length && tab === 'wr' && <Wr ix={ix} ids={ids} />}
      {!!ids.length && tab === 'gap' && <Gap ix={ix} ids={ids} />}
      {!!ids.length && tab === 'prev' && <Prev ix={ix} ids={ids} prev={prev} onPrev={onPrev} />}
    </div>
  )
}

function Dow({ ix, ids }) {
  const t = dowTable(ix, ids)
  const g = '150px repeat(7, minmax(0,1fr))'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'grid', gridTemplateColumns: g, gap: 3, paddingBottom: 4 }}>
        <span style={cap}>вся РК</span>
        {t.head.map((h, i) => (
          <span key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
            <span style={{ ...cap, color: i >= 5 ? 'var(--warning-fg)' : 'var(--text-cap)' }}>{DOW[i]}</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{nf(h.v)}</span>
            <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-muted)' }}>{h.k == null ? '' : sg(h.k * 100)}</span>
          </span>
        ))}
      </div>
      <div style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {t.rows.map(r => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: g, gap: 3, alignItems: 'center' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
            {r.cells.map((c, i) => (
              <span key={i} title={`${DOW[i]} · ${c.v == null ? 'нет факта' : 'в среднем ' + nf(c.v) + ' · ' + sg(c.k * 100) + ' к среднему'}`}
                style={{ height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4, fontFamily: MONO, fontSize: 10,
                  background: c.v == null ? 'var(--bg-subtle)' : c.k < 0 ? heat(-c.k * 2.5, 'bad') : heat(c.k * 2.5, 'ok'),
                  color: c.v == null ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{nf(c.v)}</span>
            ))}
          </div>
        ))}
      </div>
      {t.weTot != null && <span style={{ paddingTop: 6, fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
        Выходные по РК {sg(t.weTot * 100)} к будням. Для выводов: «нужно в день» на сб–вс с этой поправкой было бы другим (правило биддера пока не меняем).</span>}
    </div>
  )
}

function Wr({ ix, ids }) {
  const w = wrByDay(ix, ids)
  const max = Math.max(w.limit * 2, ...w.days.map(d => Math.abs(d.v || 0))) * 1.1
  const band = w.limit / max * 50
  const g = 'minmax(0,1fr) 56px 64px 46px 64px'
  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      <div style={{ flex: '1 1 600px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ position: 'relative', height: 160, display: 'flex', gap: 3, borderTop: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ position: 'absolute', left: 0, right: 0, top: `calc(50% - ${band}%)`, height: `${band * 2}%`, background: 'var(--bg-subtle)' }} />
          <span style={{ position: 'absolute', left: 0, right: 0, top: '50%', height: 1, background: 'var(--border-hover)' }} />
          {w.days.map(d => (
            <span key={d.x} title={`${dm(d.x)} · ${d.v == null ? 'нет данных WR' : sg(d.v)}`} style={{ position: 'relative', flex: '1 1 0', minWidth: 0 }}>
              {d.v != null && <span style={{ position: 'absolute', left: '15%', right: '15%', borderRadius: 2,
                ...(d.v > 0 ? { bottom: '50%' } : { top: '50%' }), height: `${Math.abs(d.v) / max * 50}%`,
                background: d.level === 'ok' ? 'var(--bank-sovkom)' : d.level === 'warn' ? 'var(--warning)' : 'var(--danger)' }} />}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 3 }}>{w.days.map(d => <span key={d.x} style={{ flex: '1 1 0', minWidth: 0, textAlign: 'center', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{d.x.slice(8, 10)}</span>)}</div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>вверх — Weborama меньше нашего факта, вниз — больше; жёлтый — за порогом, красный — за двумя порогами</span>
      </div>
      <div style={{ flex: '0 1 420px', minWidth: 320, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div style={{ display: 'grid', gridTemplateColumns: g, gap: 8, paddingBottom: 5, borderBottom: '1px solid var(--border-card)', ...cap }}>
          <span>площадка за порогом</span><span style={{ textAlign: 'right' }}>с какого</span><span style={{ textAlign: 'right' }}>в тот день</span><span style={{ textAlign: 'right' }}>дней</span><span style={{ textAlign: 'right' }}>за флайт</span>
        </div>
        {w.breaks.slice(0, 10).map(b => (
          <div key={b.id} style={{ display: 'grid', gridTemplateColumns: g, gap: 8, padding: '5px 0', borderBottom: '1px solid var(--border-row)', fontFamily: MONO, fontSize: 11 }}>
            <span style={{ fontFamily: 'inherit', fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.label}</span>
            <span style={{ textAlign: 'right', fontWeight: 700, color: 'var(--danger-fg)' }}>{dm(b.since)}</span>
            <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>{sg(b.first)}</span>
            <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>{b.cnt}</span>
            <span style={{ textAlign: 'right', fontWeight: 700 }}>{sg(b.tot)}</span>
          </div>
        ))}
        {w.breaks.length ? <span style={{ paddingTop: 6, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>«С какого» — первый день за порогом: обычно это смена кода или сломанный пиксель.</span>
          : <span style={{ paddingTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>Все площадки в пределах порога.</span>}
      </div>
    </div>
  )
}

function Gap({ ix, ids }) {
  const t = gapTable(ix, ids)
  if (!t.days.length) return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>DSP ещё не отдавала «предложено» по этой РК.</span>
  const g = `150px repeat(${t.days.length}, minmax(0,1fr)) 70px 52px`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'grid', gridTemplateColumns: g, gap: 3, paddingBottom: 4, fontFamily: MONO, fontSize: 9, color: 'var(--text-cap)' }}>
        <span style={cap}>площадка DSP</span>
        {t.days.map(x => <span key={x} style={{ textAlign: 'center' }}>{x.slice(8, 10)}</span>)}
        <span style={{ ...cap, textAlign: 'right' }}>не взято</span><span style={{ textAlign: 'right' }}>%</span>
      </div>
      <div style={{ maxHeight: 340, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {t.rows.map(r => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: g, gap: 3, alignItems: 'center' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
            {r.cells.map(c => <span key={c.x} title={`${r.label} · ${dm(c.x)} · предложено ${nf(c.off)} · взято ${nf(c.got)}`}
              style={{ height: 18, borderRadius: 3, background: c.k == null ? 'var(--bg-subtle)' : heat(c.k, 'bad') }} />)}
            <span style={{ textAlign: 'right', fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{nf(r.left)}</span>
            <span style={{ textAlign: 'right', fontFamily: MONO, fontSize: 10.5, color: 'var(--danger-fg)' }}>{pf(r.k * 100, 0)}</span>
          </div>
        ))}
      </div>
      <span style={{ paddingTop: 6, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>Чем краснее клетка, тем больше сеть предлагала и тем меньше мы взяли: упор в лимит, ставку или креатив, а не в ёмкость площадки. Сортировка — по доле невзятого.</span>
    </div>
  )
}

function Prev({ ix, ids, prev, onPrev }) {
  const opts = prev?.options || []
  if (!opts.length) return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>У этой связки «рекламодатель + бренд» нет более ранних РК со статистикой. Боевой сбор идёт с 01.10.2026 — сравнение появится со следующего флайта.</span>
  const pc = prevCompare(ix, ids, prev.flight)
  const sel = opts.find(o => o.campaign_id === prev.selected) || opts[0]
  const head = (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={cap}>сравнить с</span>
      <select value={sel.campaign_id} onChange={e => onPrev(Number(e.target.value))} style={{ height: 28, borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, padding: '0 8px', background: 'var(--bg-card)' }}>
        {opts.map(o => <option key={o.campaign_id} value={o.campaign_id}>{o.code} · {dm(o.date_start)}–{dm(o.date_end)}</option>)}
      </select>
    </span>
  )
  if (!pc) return <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{head}<span style={{ fontSize: 12, color: 'var(--text-muted)' }}>У выбранной РК нет факта по этим площадкам.</span></div>
  const max = Math.max(1, ...pc.now, ...pc.was) * 1.1
  const P = (arr) => arr.map((v, i) => `${((i + 0.5) / pc.days * 1000).toFixed(1)},${(120 - v / max * 120).toFixed(1)}`).join(' ')
  const fmt = (r, v) => (r.kind === 'pp' ? pf(v, 0) : r.kind === 'ctr' ? pf(v, 2) : nf(v))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {head}
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 560px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <svg viewBox="0 0 1000 120" preserveAspectRatio="none" style={{ width: '100%', height: 150, overflow: 'visible', borderBottom: '1px solid var(--border-inner)' }}>
            <polyline points={P(pc.was)} fill="none" stroke="var(--text-faint)" strokeWidth="2" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
            <polyline points={P(pc.now)} fill="none" stroke="var(--income)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
          </svg>
          <span style={{ display: 'flex', gap: 14, fontSize: 11, color: 'var(--text-muted)' }}>
            <span>— текущий флайт</span><span>- - {sel.code}, по дню флайта</span></span>
        </div>
        <div style={{ flex: '0 1 460px', minWidth: 340, display: 'flex', flexDirection: 'column' }}>
          {pc.rows.map(r => (
            <div key={r.label} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 100px 100px 72px', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border-row)', fontFamily: MONO, fontSize: 11.5 }}>
              <span style={{ fontFamily: 'inherit', fontSize: 12, fontWeight: 600 }}>{r.label}</span>
              <span style={{ textAlign: 'right', fontWeight: 700 }}>{fmt(r, r.now)}</span>
              <span style={{ textAlign: 'right', color: 'var(--text-muted)' }}>{fmt(r, r.was)}</span>
              <span style={{ textAlign: 'right', fontWeight: 700, color: r.d == null ? 'var(--text-faint)' : r.d >= 0 ? 'var(--income-fg)' : 'var(--danger-fg)' }}>{r.kind === 'pp' ? pp(r.d) : sg(r.d)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
