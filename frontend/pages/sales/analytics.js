import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import api from '@/lib/api'
import { mln, mlnAuto, grp, pct, niceMax } from '@/lib/salesFormat'

const MONO = "'JetBrains Mono', ui-monospace, monospace"
const UI = "'Manrope', system-ui, sans-serif"
const NO_GROUP = 'Без группы'

// Цвета слоёв денег (v2): факт зелёный, реализуемые жёлтые, планируемые серые, сорванные красные.
const LC = { fact: 'var(--income)', real: 'var(--dot-current-dz)', plan: 'var(--text-faint)', lost: 'var(--dot-overdue)' }
const EMPTY = 'var(--border-inner)'
const HATCH = 'repeating-linear-gradient(135deg,#C3C9D8 0 3px,#FFFFFF 3px 6px)'
const C = { text: 'var(--text-primary)', sec: 'var(--text-muted)', faint: 'var(--text-faint)', accent: 'var(--accent)', card: 'var(--bg-card)', border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)' }

const DIMS = [
  { key: 'by_sales_rep', label: 'Сейлзы' }, { key: 'by_account_manager', label: 'Аккаунты' },
  { key: 'by_agency', label: 'Агентства' }, { key: 'by_advertiser', label: 'Рекламодатели' },
  { key: 'by_product', label: 'Продукты' }, { key: 'by_pipeline', label: 'Воронки' },
]
const monthStr = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
const defaultRange = () => { const n = new Date(); return { date_from: monthStr(new Date(n.getFullYear(), n.getMonth() - 6, 1)), date_to: monthStr(new Date(n.getFullYear(), n.getMonth() + 5, 1)) } }

const plural = (n, f) => { const a = Math.abs(n) % 100, b = a % 10; if (a > 10 && a < 20) return f[2]; if (b > 1 && b < 5) return f[1]; if (b === 1) return f[0]; return f[2] }
const nDeals = (n) => `${n} ${plural(n, ['сделка', 'сделки', 'сделок'])}`
const cellsOf = (v, scale, n) => (v > 0 ? Math.max(1, Math.round(v / scale * n)) : 0)

const CARD = { background: C.card, border: `1px solid ${C.border}`, borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const monoLbl = { fontFamily: MONO, fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: C.sec }
const subLbl = { fontFamily: MONO, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.sec }
const rise = (d) => ({ animation: `a2rise .4s cubic-bezier(0.22,1,0.36,1) both`, animationDelay: `${d}s` })

function useCountUp(value, ms = 850) {
  const [n, setN] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    if (typeof window === 'undefined') { setN(value); from.current = value; return }
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setN(value); from.current = value; return }
    const start = performance.now(); const a = from.current
    let raf; const tick = (t) => { const p = Math.min(1, (t - start) / ms); const e = 1 - Math.pow(1 - p, 3); setN(a + (value - a) * e); if (p < 1) raf = requestAnimationFrame(tick); else from.current = value }
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf)
  }, [value])
  return n
}
const Num = ({ v, d = 1 }) => { const n = useCountUp(v); return <>{mln(n, d)}</> }

export default function Analytics2() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dim, setDim] = useState('by_sales_rep')
  const [f, setF] = useState({ date_from: '', date_to: '' })
  const [myRep, setMyRep] = useState('')
  const [hoverM, setHoverM] = useState(null)
  const rankRef = useRef(null)
  const [nCells, setNCells] = useState(48)   // ячеек в баре разреза: адаптивно, до 100 на широком экране

  const loadWith = async (period = f) => {
    setLoading(true); setError('')
    try {
      const params = {}; if (period.date_from) params.date_from = period.date_from; if (period.date_to) params.date_to = period.date_to
      const r = await api.get('/sales/dashboard', { params, headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
      setData(r.data)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить') } finally { setLoading(false) }
  }
  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    const v = defaultRange(); setF(v); loadWith(v)
    api.get('/sales/dashboard/bonus', { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }).then(r => setMyRep(r.data?.rep || '')).catch(() => {})
  }, [])

  // Адаптивное число ячеек в баре разреза: ~8px на ячейку, максимум 100, минимум 20.
  useEffect(() => {
    const el = rankRef.current; if (!el || typeof ResizeObserver === 'undefined') return
    const measure = () => { const barW = el.clientWidth - 330 - 64; setNCells(Math.max(20, Math.min(100, Math.floor(barW / 8)))) }
    measure(); const ro = new ResizeObserver(measure); ro.observe(el)
    return () => ro.disconnect()
  }, [data, dim])

  const t = data?.totals
  const byLayer = data?.by_layer || []
  const layerAmt = (name) => (byLayer.find(b => b.name === name)?.amount) || 0
  const selBox = { border: `1px solid ${C.border}`, background: C.card, borderRadius: 12, padding: '9px 14px', fontFamily: UI, fontSize: 13, fontWeight: 600, color: C.text }
  const syncTime = data?.last_sync_at ? new Date(data.last_sync_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : null
  const periodLabel = (f.date_from || f.date_to) ? `${f.date_from || '…'} — ${f.date_to || '…'}` : '12 месяцев'

  // ── данные ──
  // Сорванные сделки: бэкенд ещё не отдаёт — поля предусмотрены (lostAmount/lostCount), пока 0.
  const num = (v) => (typeof v === 'number' && !isNaN(v) ? v : 0)
  const months = (data?.by_month || []).map(b => ({ name: b.name, fact: num(b.fact), real: num(b.real), plan: num(b.plan), count: b.deals || 0, total: num(b.fact) + num(b.real) + num(b.plan), lostAmount: num(b.lost_amount ?? b.lostAmount), lostCount: num(b.lost_count ?? b.lostCount) }))
  const monthMax = niceMax(Math.max(1, ...months.map(m => m.total)))
  const lostMax = niceMax(Math.max(1, ...months.map(m => m.lostAmount)))

  const layerDeals = (name) => (byLayer.find(b => b.name === name)?.deals) || 0
  const layerRows = [
    { key: 'fact', name: 'фактические', amount: layerAmt('фактические'), deals: layerDeals('фактические'), color: LC.fact },
    { key: 'plan', name: 'планируемые', amount: layerAmt('планируемые'), deals: layerDeals('планируемые'), color: LC.plan },
    { key: 'real', name: 'реализуемые', amount: layerAmt('реализуемые'), deals: layerDeals('реализуемые'), color: LC.real },
    { key: 'none', name: 'без группы', amount: layerAmt(NO_GROUP), deals: layerDeals(NO_GROUP), color: HATCH },
    { key: 'lost', name: 'сорванные', amount: (t?.lost_amount || 0), deals: (t?.lost_count || 0), color: LC.lost, ref: true },
  ]
  // масштаб — только реальные слои; «сорванные» справочные, в шкалу не входят
  const layerScale = niceMax(Math.max(1, ...layerRows.filter(r => r.key !== 'lost').map(r => r.amount)))

  const products = (data?.by_product || []).map(b => ({ ...b, total: b.fact + b.real + b.plan })).sort((a, b) => b.total - a.total).slice(0, 8)
  const productScale = niceMax(Math.max(1, ...products.map(p => p.total)))

  const dimAll = data?.[dim] || []
  const dimTop = dimAll.slice(0, 15)
  const rest = dimAll.slice(15).reduce((a, b) => ({ fact: a.fact + (b.fact || 0), real: a.real + (b.real || 0), plan: a.plan + (b.plan || 0) }), { fact: 0, real: 0, plan: 0 })
  const dimRows = rest.fact > 0 ? [...dimTop, { name: 'остальные', ...rest, rest: true }] : dimTop
  // масштаб по полному составу (факт+реализ+план) от самого большого значения, но не менее 100 млн
  const dimScale = niceMax(Math.max(100e6, ...dimRows.map(r => (r.fact || 0) + (r.real || 0) + (r.plan || 0))))
  const factTotal = t?.fact || 0

  const UP = 14, DOWN = 4

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head>
        <title>Аналитика продаж</title>
      </Head>
      <Navbar active="sales" />
      <style>{`
        @keyframes a2rise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes a2up { from { transform:scaleY(0) } to { transform:scaleY(1) } }
        @media (prefers-reduced-motion: reduce){ [style*="animation"]{ animation:none !important } }
      `}</style>

      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', marginTop: -20, ...rise(0) }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', color: C.text, margin: 0 }}>Аналитика продаж</h1>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.sec }}>{periodLabel}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {syncTime && <span style={{ fontFamily: MONO, fontSize: 12, color: C.sec, marginRight: 4 }}>обновлено {syncTime}</span>}
            <input type="month" style={selBox} value={f.date_from} onChange={e => { const v = { ...f, date_from: e.target.value }; setF(v); loadWith(v) }} />
            <span style={{ color: C.faint }}>—</span>
            <input type="month" style={selBox} value={f.date_to} onChange={e => { const v = { ...f, date_to: e.target.value }; setF(v); loadWith(v) }} />
            <button onClick={() => { const v = defaultRange(); setF(v); loadWith(v) }} style={{ ...selBox, background: 'var(--bg-subtle)', color: C.sec, cursor: 'pointer' }}>Сбросить к 12 мес</button>
          </div>
        </div>

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)', color: 'var(--danger)', padding: '10px 14px', borderRadius: 12, fontSize: 13 }}>{error}</div>}
        {loading && !data && <div style={{ color: C.sec, padding: 8 }}>Загрузка…</div>}

        {data && t && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* KPI */}
            <div style={{ ...CARD, padding: '0 36px', ...rise(0.07) }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
                {[
                  { mk: 'var(--income)', lbl: 'Реализованная выручка', node: <span style={{ color: 'var(--income)' }}><Num v={t.fact} /></span>, unit: 'млн ₽', cap: <>закрытые и архивные, без «МП»</> },
                  { lbl: 'В работе', node: <Num v={t.work} />, unit: 'млн ₽', cap: <>реализуемые <b style={{ ...bMono, color: '#C27510' }}>{mln(layerAmt('реализуемые'))}</b> + планируемые <b style={bMono}>{mln(layerAmt('планируемые'))}</b></> },
                  { lbl: 'Сделок в периоде', node: <span style={{ fontFamily: MONO, fontWeight: 700 }}>{grp(t.deals)}</span>, unit: 'шт', cap: <>средний чек <b style={bMono}>{t.deals ? mln(t.amount / t.deals, 2) : '—'} млн ₽</b></> },
                  { lbl: 'Сверка', recon: t.reconciles, cap: t.reconciles ? 'слои дают сумму витрины' : 'слои не сходятся с суммой витрины' },
                ].map((k, i) => (
                  <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '28px 26px', borderRight: i < 3 ? `1px solid ${C.inner}` : 'none', paddingLeft: i === 0 ? 0 : 26, paddingRight: i === 3 ? 0 : 26 }}>
                    <div style={{ ...monoLbl, display: 'flex', alignItems: 'center', gap: 7 }}>{k.mk && <span style={{ width: 8, height: 8, borderRadius: 2, background: k.mk }} />}{k.lbl}</div>
                    {k.recon !== undefined ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ width: 10, height: 10, borderRadius: 2, background: k.recon ? 'var(--income)' : 'var(--dot-overdue)' }} />
                        <span style={{ fontSize: 30, fontWeight: 700, color: k.recon ? 'var(--income)' : '#C93A3E' }}>{k.recon ? 'сходится' : 'расхождение'}</span>
                      </span>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                        <span style={{ fontFamily: MONO, fontSize: 42, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: C.text }}>{k.node}</span>
                        <span style={{ fontSize: 17, fontWeight: 600, color: C.faint }}>{k.unit}</span>
                      </div>
                    )}
                    <div style={{ fontSize: 12, color: C.sec }}>{k.cap}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Ряд виджетов 2fr / 1fr / 1fr */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 20, alignItems: 'stretch' }}>

              {/* Динамика по месяцам — двусторонний пиксельный график */}
              <div style={{ ...CARD, padding: '28px 30px 20px', display: 'flex', flexDirection: 'column', ...rise(0.14) }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, gap: 12 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <span style={{ fontSize: 17, fontWeight: 700, color: C.text }}>Динамика по месяцам</span>
                    <span style={subLbl}>месяц старта РК · вверх слои денег, вниз сорванные</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {[['факт', LC.fact], ['реализ', LC.real], ['план', LC.plan], ['сорвано', LC.lost]].map(([l, c]) => (
                      <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: C.sec }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                    ))}
                  </div>
                </div>
                {months.length === 0 ? <Empty /> : (
                  <div style={{ display: 'flex', gap: 8, flex: 1 }}>
                    {/* Ось Y */}
                    <div style={{ width: 52, display: 'flex', flexDirection: 'column', fontFamily: MONO, fontSize: 10, color: C.faint }}>
                      <div style={{ flex: UP, position: 'relative' }}>
                        {[1, 0.75, 0.5, 0.25].map(fr => <span key={fr} style={{ position: 'absolute', right: 0, top: `calc(${(1 - fr) * 100}% - 5px)` }}>{Math.round(monthMax * fr / 1e6)}</span>)}
                        <span style={{ position: 'absolute', right: 0, bottom: -5, color: C.sec, fontWeight: 700 }}>0</span>
                      </div>
                      <div style={{ flex: DOWN, position: 'relative' }}><span style={{ position: 'absolute', right: 0, bottom: 2, color: '#C93A3E' }}>{Math.round(lostMax / 1e6)} млн</span></div>
                      <div style={{ height: 22 }} />
                    </div>
                    {/* Плот */}
                    <div style={{ flex: 1, display: 'flex', gap: 0 }}>
                      {months.map((m, i) => {
                        const nF = cellsOf(m.fact, monthMax, UP), nR = cellsOf(m.real, monthMax, UP), nP = cellsOf(m.plan, monthMax, UP)
                        const up = [...Array(nF).fill(LC.fact), ...Array(nR).fill(LC.real), ...Array(nP).fill(LC.plan)].slice(0, UP)
                        const upCells = [...up, ...Array(Math.max(0, UP - up.length)).fill(EMPTY)]
                        const nL = cellsOf(m.lostAmount, lostMax, DOWN)
                        const down = [...Array(nL).fill(LC.lost), ...Array(Math.max(0, DOWN - nL)).fill(EMPTY)]
                        const hov = hoverM === i
                        return (
                          <div key={m.name} onMouseEnter={() => setHoverM(i)} onMouseLeave={() => setHoverM(null)}
                            style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}>
                            {hov && <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 22, borderLeft: '1px dashed var(--text-faint)', pointerEvents: 'none' }} />}
                            {/* верх */}
                            <div style={{ flex: UP, display: 'flex', alignItems: 'flex-end', borderBottom: `1px solid #C3C9D8`,
                              backgroundImage: `repeating-linear-gradient(to top, ${C.row} 0 1px, transparent 1px 25%)` }}>
                              <div style={{ width: '58%', height: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column-reverse', gap: 2, animation: 'a2up .55s cubic-bezier(0.22,1,0.36,1) both', animationDelay: `${i * 0.04}s`, transformOrigin: 'bottom' }}>
                                {upCells.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}
                              </div>
                            </div>
                            {/* низ (сорванные) */}
                            <div style={{ flex: DOWN, display: 'flex', alignItems: 'flex-start', paddingTop: 2 }}>
                              <div style={{ width: '58%', height: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 2, animation: 'a2up .55s cubic-bezier(0.22,1,0.36,1) both', animationDelay: `${i * 0.04}s`, transformOrigin: 'top' }}>
                                {down.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}
                              </div>
                            </div>
                            {/* подпись месяца */}
                            <div style={{ height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 10, color: C.sec }}>{m.name.slice(5)}</div>
                            {/* тултип */}
                            {hov && (
                              <div style={{ position: 'absolute', top: 4, zIndex: 5, pointerEvents: 'none', ...(i >= 7 ? { right: 'calc(50% + 12px)' } : { left: 'calc(50% + 12px)' }),
                                background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 24px rgba(28,36,51,.10)', padding: '12px 14px', minWidth: 196 }}>
                                <div style={{ ...monoLbl, fontSize: 10 }}>{m.name} · {nDeals(m.count)}</div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, margin: '8px 0' }}>
                                  {[['фактические', m.fact, LC.fact], ['реализуемые', m.real, LC.real], ['планируемые', m.plan, LC.plan]].filter(([, v]) => v > 0).map(([l, v, c]) => (
                                    <div key={l} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, color: C.sec }}>
                                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                                      <span style={{ fontFamily: MONO, color: C.text, fontWeight: 700 }}>{mln(v)}</span>
                                    </div>
                                  ))}
                                </div>
                                <div style={{ borderTop: `1px solid ${C.row}`, paddingTop: 6, display: 'flex', justifyContent: 'space-between', fontSize: 12, color: C.sec }}>
                                  <span>итог месяца</span><span style={{ fontFamily: MONO, color: C.text, fontWeight: 700 }}>{mln(m.total)} млн</span>
                                </div>
                                {m.lostAmount > 0 && (
                                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.row}`, display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#C93A3E' }}>
                                    <span>сорвано · {nDeals(m.lostCount)}</span><span style={{ fontFamily: MONO, fontWeight: 700 }}>{mln(m.lostAmount)}</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Слои денег */}
              <div style={{ ...CARD, padding: '28px 26px 20px', display: 'flex', flexDirection: 'column', ...rise(0.21) }}>
                <div style={{ fontSize: 17, fontWeight: 700, color: C.text, marginBottom: 16 }}>Слои денег</div>
                <div>
                  {layerRows.map((r, ri) => {
                    const n = cellsOf(r.amount, layerScale, 16)
                    return (
                      <div key={r.key} style={{ padding: '16px 0', borderTop: ri ? `1px solid ${C.row}` : 'none' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: C.text }}>
                            <span style={{ width: 10, height: 10, borderRadius: 2, background: r.color }} />{r.name}
                            <span style={{ fontFamily: MONO, fontSize: 11, color: C.faint }}>{r.deals} сд.</span>
                            {r.ref && <span style={{ fontSize: 10, color: C.faint }}>справочно</span>}
                          </span>
                          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8 }}>
                            <span style={{ fontFamily: MONO, fontSize: 11, color: C.sec }}>{layerScale ? pct(r.amount / (factTotal || layerScale) * 100) : ''}</span>
                            <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: r.key === 'lost' ? '#C93A3E' : C.text }}>{mln(r.amount)}</span>
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: 2, height: 12, animation: 'a2up .55s both', animationDelay: `${ri * 0.05}s`, transformOrigin: 'left' }}>
                          {Array.from({ length: 16 }, (_, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: j < n ? r.color : EMPTY }} />)}
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: `1px solid ${C.inner}`, fontSize: 12, color: C.sec }}>Шкала до <b style={bMono}>{mlnAuto(layerScale)} млн ₽</b>. «Сорванные» не входят в выручку.</div>
              </div>

              {/* Продукты */}
              <div style={{ ...CARD, padding: '28px 26px 20px', display: 'flex', flexDirection: 'column', ...rise(0.28) }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 16 }}>
                  <span style={{ fontSize: 17, fontWeight: 700, color: C.text }}>Продукты</span>
                  <span style={subLbl}>топ-8 · деление по слоям</span>
                </div>
                {products.length === 0 ? <Empty /> : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {products.map(p => {
                      const nF = cellsOf(p.fact, productScale, 16), nR = cellsOf(p.real, productScale, 16), nP = cellsOf(p.plan, productScale, 16)
                      const cells = [...Array(nF).fill(LC.fact), ...Array(nR).fill(LC.real), ...Array(nP).fill(LC.plan)].slice(0, 16)
                      const full = [...cells, ...Array(Math.max(0, 16 - cells.length)).fill(EMPTY)]
                      return (
                        <div key={p.name}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
                            <span style={{ fontSize: 13, color: C.sec, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: C.text }}>{mln(p.total)}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 2, height: 10 }}>{full.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}</div>
                        </div>
                      )
                    })}
                  </div>
                )}
                <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: `1px solid ${C.inner}`, fontSize: 12, color: C.sec }}>шкала до <b style={bMono}>{mlnAuto(productScale)} млн ₽</b> · значения в млн ₽</div>
              </div>
            </div>

            {/* Разрез по факту */}
            <div style={{ ...CARD, padding: '28px 30px 20px', ...rise(0.35) }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <span style={{ fontSize: 17, fontWeight: 700, color: C.text }}>Разрез по факту</span>
                  <span style={subLbl}>реализованная выручка · шкала до {mlnAuto(dimScale)} млн ₽</span>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {DIMS.map(d => { const on = dim === d.key; return (
                    <button key={d.key} onClick={() => setDim(d.key)} style={{ borderRadius: 999, padding: '7px 13px', fontSize: 13, cursor: 'pointer', fontWeight: on ? 700 : 600, background: on ? 'var(--accent-tint)' : C.card, color: on ? C.accent : C.sec, border: on ? '1px solid #D7DEFA' : `1px solid ${C.border}` }}>{d.label}</button>
                  ) })}
                </div>
              </div>
              {dimRows.length === 0 ? <Empty /> : (
                <div ref={rankRef} style={{ display: 'flex', flexDirection: 'column' }}>
                  {dimRows.map((r, i) => {
                    const mine = !r.rest && myRep && r.name === myRep
                    const none = r.name === NO_GROUP
                    const share = factTotal > 0 ? r.fact / factTotal * 100 : 0
                    // Стековая полоса по слоям: цвет отражает состав суммы (факт/реализ/план).
                    // «Без группы» — штриховкой; своя строка подсвечивается фоном/текстом, полоса — по составу.
                    let cells
                    if (none) cells = Array(cellsOf((r.fact || 0) + (r.real || 0) + (r.plan || 0), dimScale, nCells)).fill(HATCH).slice(0, nCells)
                    else cells = [...Array(cellsOf(r.fact, dimScale, nCells)).fill(LC.fact), ...Array(cellsOf(r.real, dimScale, nCells)).fill(LC.real), ...Array(cellsOf(r.plan, dimScale, nCells)).fill(LC.plan)].slice(0, nCells)
                    const full = [...cells, ...Array(Math.max(0, nCells - cells.length)).fill(EMPTY)]
                    return (
                      <div key={r.name + i} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: mine ? 8 : '11px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: `1px solid ${C.row}`, background: mine ? '#F6F8FF' : 'transparent' }}>
                        <span style={{ width: 24, textAlign: 'right', fontFamily: MONO, fontSize: 11, color: mine ? '#8F9BE8' : C.faint }}>{r.rest ? '' : i + 1}</span>
                        <span style={{ width: 176, fontSize: 13, fontWeight: mine ? 700 : 600, color: mine ? '#3A50BE' : (r.rest ? C.sec : C.text), overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{none ? 'без группы' : r.name}</span>
                        <div style={{ flex: 1, display: 'flex', gap: 2, height: 16 }}>{full.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}</div>
                        <span style={{ width: 78, textAlign: 'right', fontFamily: MONO, fontSize: 13, fontWeight: 700, color: mine ? '#3A50BE' : C.text }}>{mln(r.fact)}</span>
                        <span style={{ width: 52, textAlign: 'right', fontFamily: MONO, fontSize: 11, color: mine ? '#6E7BD8' : C.sec }}>{r.rest ? '' : pct(share)}</span>
                      </div>
                    )
                  })}
                </div>
              )}
              <div style={{ paddingTop: 16, marginTop: 6, borderTop: `1px solid ${C.inner}`, display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', fontSize: 12, color: C.sec }}>
                <span>значения — млн ₽ реализованной выручки · текущий сейлз выделен акцентом</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: 'var(--income)', fontWeight: 700 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--income)' }} />сумма разреза = {mlnAuto(factTotal)} млн</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const bMono = { fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }
function Empty() { return <div style={{ padding: '40px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет данных за период</div> }
