import Navbar from '../components/Navbar'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { buildDivBars, buildYLabels, niceMax, buildMonthLabels } from '../helpers/ribbonChart'
import Head from 'next/head'
import { motion, AnimatePresence, useMotionValue, useTransform, animate, useReducedMotion } from 'framer-motion'

const api = (token) => axios.create({
  // См. комментарий в balance.js — относительный путь, проксируется Caddy.
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))

const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const BANK_VARS = { 'АльфаБанк': 'var(--bank-alfa)', 'ОПТ Банк': 'var(--bank-opt)', 'Совкомбанк': 'var(--bank-sovkom)', 'Наличные': 'var(--bank-cash)' }
const bankColor = (name) => BANK_VARS[name] || 'var(--text-faint)'

const MONTH_NAMES = {
  '01': 'Янв', '02': 'Фев', '03': 'Мар', '04': 'Апр',
  '05': 'Май', '06': 'Июн', '07': 'Июл', '08': 'Авг',
  '09': 'Сен', '10': 'Окт', '11': 'Ноя', '12': 'Дек'
}

const formatPeriod = (p) => {
  if (!p) return '—'
  const [year, month] = p.split('-')
  return `${MONTH_NAMES[month] || month} ${year}`
}

// ── Стили карточек ───────────────────────────────────────────────
const card = (extra = {}) => ({
  background: 'var(--bg-card)',
  borderRadius: 'var(--radius-card)',
  boxShadow: 'var(--shadow-card)',
  padding: '20px 22px',
  ...extra,
})

// ── Анимация 1: count-up число ───────────────────────────────────
function CountUp({ value, suffix = '', color }) {
  const reduced = useReducedMotion()
  const mv = useMotionValue(0)
  const formatted = useTransform(mv, v => new Intl.NumberFormat('ru-RU').format(Math.round(v)) + suffix)
  const prevRef = useRef(0)

  useEffect(() => {
    if (reduced) { mv.set(value); return }
    const ctrl = animate(mv, value, { duration: 0.85, ease: [0.22, 1, 0.36, 1], from: prevRef.current })
    prevRef.current = value
    return () => ctrl.stop()
  }, [value, reduced])

  return (
    <motion.span style={{ color, fontVariantNumeric: 'tabular-nums' }}>
      {formatted}
    </motion.span>
  )
}

export default function Dashboard() {
  const router = useRouter()
  const reduced = useReducedMotion()
  const [ddsData, setDdsData] = useState({ periods: [], banks: [] })
  const [ddsSummary, setDdsSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [hoverBar, setHoverBar] = useState(null)
  const [hoverCapsuleIdx, setHoverCapsuleIdx] = useState(null)
  const [selectedBank, setSelectedBank] = useState('all')
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 11)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [expandedPeriod, setExpandedPeriod] = useState(null)
  const [groupBy, setGroupBy] = useState('period')

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    loadAll(token)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) loadDds(token)
  }, [dateFrom, dateTo, selectedBank, groupBy])

  const loadAll = async (token) => {
    setLoading(true)
    try {
      const a = api(token)
      const [ddsRes, summaryRes] = await Promise.all([
        a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}&group_by=${groupBy}`),
        a.get('/reports/dds/summary'),
      ])
      setDdsData(ddsRes.data || { periods: [], banks: [] })
      setDdsSummary(summaryRes.data || null)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const loadDds = async (token) => {
    try {
      const a = api(token)
      const bankParam = selectedBank !== 'all' ? `&bank=${selectedBank}` : ''
      const res = await a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}${bankParam}&group_by=${groupBy}`)
      setDdsData(res.data || { periods: [], banks: [] })
    } catch (e) {}
  }

  const periods = ddsData?.periods || []

  // ── Данные для риббон-графика (из реальных периодов, без фиктивных 12 месяцев) ──
  const monthly = periods.map(p => ({ income: p.total_income || 0, expense: p.total_expense || 0 }))
  const maxVal = niceMax(Math.max(1, ...monthly.map(m => m.income), ...monthly.map(m => m.expense)))
  // height/arm должны совпадать с фактической высотой контейнера графика (height: 320, см. ниже) —
  // ribbonChart.js по умолчанию рассчитан на 400px, без этого override бары и подписи оси
  // выходят за пределы карточки (на ~62px ниже видимой области)
  const RIBBON_HEIGHT = 320
  const RIBBON_ARM = 144
  const divBars = buildDivBars(monthly, { maxVal, height: RIBBON_HEIGHT, arm: RIBBON_ARM })
  const yLabels = buildYLabels(maxVal, { height: RIBBON_HEIGHT, arm: RIBBON_ARM })
  const monthLabels = buildMonthLabels(periods.map(p => p.period))

  // ── Hover-зоны по реальным месяцам ──
  // divBars — это SUB интерполированных капсул (Catmull-Rom), а не по одной на месяц.
  // Месяц m лежит в параметре t=m/(N-1), что соответствует капсуле round(t·(SUB-1)).
  // Подпись позиционируем по кончику этой капсулы, а значение берём реальное из monthly[m].
  const SUB = divBars.length
  const N = monthly.length
  const monthHotspots = monthly.map((mo, m) => {
    const capsuleIdx = N > 1 ? Math.round((m / (N - 1)) * (SUB - 1)) : Math.round((SUB - 1) / 2)
    const bar = divBars[capsuleIdx] || { incTop: RIBBON_HEIGHT / 2, incH: 0, expTop: RIBBON_HEIGHT / 2, expH: 0 }
    return {
      m,
      capsuleIdx,
      inc: mo.income || 0,
      exp: mo.expense || 0,
      leftPct: `calc(10px + ${((capsuleIdx + 0.5) / SUB).toFixed(4)} * (100% - 20px))`,
      widthPct: `calc((100% - 20px) / ${Math.max(1, N)})`,
      incLabelTop: Math.max(0, bar.incTop - 17),
      expLabelTop: Math.min(RIBBON_HEIGHT - 15, bar.expTop + bar.expH + 3),
    }
  })

  // ── Данные для накопительного остатка ──
  const cumulativeData = periods.map(p => ({ period: formatPeriod(p.period), cumulative: Math.round(p.cumulative || 0) }))


  const actualBalance = ddsSummary?.total_balance ?? ddsSummary?.net ?? 0
  const planNet = (ddsSummary?.plan_income || 0) - (ddsSummary?.plan_expense || 0)
  const forecastBalance = actualBalance + planNet

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar active="dds" />
      <Head><title>ДДС | Финансовый учёт</title></Head>

      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '26px 30px' }}>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>Загрузка…</div>
        ) : <>

          {/* ── Заголовок + фильтры ── */}
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 300, color: 'var(--text-primary)', letterSpacing: '-.02em' }}>
              Движение <b style={{ fontWeight: 800 }}>денежных средств</b>
            </h1>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4, fontWeight: 500 }}>С периода</label>
                <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                  style={{ padding: '9px 12px', borderRadius: 'var(--radius-input)', border: '1px solid var(--border-card)', background: 'var(--bg-card)', fontSize: 13, color: 'var(--text-secondary)' }} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4, fontWeight: 500 }}>По период</label>
                <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)}
                  style={{ padding: '9px 12px', borderRadius: 'var(--radius-input)', border: '1px solid var(--border-card)', background: 'var(--bg-card)', fontSize: 13, color: 'var(--text-secondary)' }} />
              </div>
              <select value={selectedBank} onChange={e => setSelectedBank(e.target.value)} style={{
                padding: '11px 16px', borderRadius: 'var(--radius-input)', background: 'var(--bg-card)',
                border: '1px solid var(--border-card)', fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, cursor: 'pointer',
              }}>
                <option value="all">Все банки</option>
                {BANKS.map(b => <option key={b} value={b}>{b}</option>)}
              </select>

              {/* ── Анимация 4: Magic pill segmented control ── */}
              <div style={{ position: 'relative', display: 'flex', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: 4 }}>
                {[['period', 'По периоду'], ['date', 'По дате']].map(([v, label]) => (
                  <div key={v} onClick={() => setGroupBy(v)} style={{ position: 'relative', padding: '7px 14px', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 500, zIndex: 1,
                    color: groupBy === v ? '#fff' : 'var(--text-secondary)', transition: 'color .15s',
                  }}>
                    {groupBy === v && (
                      <motion.div
                        layoutId="segPill"
                        style={{ position: 'absolute', inset: 0, borderRadius: 9, background: 'var(--text-primary)', zIndex: -1 }}
                        transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 36 }}
                      />
                    )}
                    {label}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── KPI-полоса ── */}
          {ddsSummary && (
            <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
              {[
                { label: 'Актуальный баланс', rawVal: actualBalance, suffix: ' ₽', valColor: actualBalance >= 0 ? 'var(--income)' : 'var(--expense)', sub: 'На счетах сегодня' },
                { label: 'Прогнозный баланс', rawVal: forecastBalance, suffix: ' ₽', valColor: forecastBalance >= 0 ? 'var(--accent)' : 'var(--expense)', sub: `план: +${fmt(ddsSummary.plan_income || 0)} ₽ / −${fmt(ddsSummary.plan_expense || 0)} ₽` },
                { label: 'План поступлений', rawVal: ddsSummary.plan_income || 0, suffix: ' ₽', valColor: 'var(--income)', sub: `${ddsSummary.income_count ?? 0} операций` },
                { label: 'План расходов', rawVal: ddsSummary.plan_expense || 0, suffix: ' ₽', valColor: 'var(--expense)', sub: `${ddsSummary.expense_count ?? 0} операций` },
              ].map((k, i) => (
                <motion.div key={k.label}
                  initial={reduced ? false : { opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.07, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                  style={{ ...card(), flex: '1 1 200px' }}
                >
                  <div style={{ fontSize: 12.5, color: 'var(--text-muted)', fontWeight: 500 }}>{k.label}</div>
                  <div style={{ fontSize: 24, fontWeight: 700, marginTop: 9, letterSpacing: '-.01em' }}>
                    {/* Анимация 1: count-up */}
                    <CountUp value={k.rawVal} suffix={k.suffix} color={k.valColor} />
                  </div>
                  <div style={{ fontSize: 12, marginTop: 7, fontWeight: 500, color: 'var(--text-muted)' }}>{k.sub}</div>
                </motion.div>
              ))}
            </div>
          )}

          {/* ── Риббон-график + Банки ── */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'stretch', flexWrap: 'wrap' }}>

            {/* Риббон-график */}
            <div style={{ ...card(), flex: '1 1 480px', padding: '22px 26px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>Движение денег по месяцам</div>
                <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {[['linear-gradient(180deg, var(--ribbon-income-from), var(--ribbon-income-to))', 'Поступления'], ['linear-gradient(180deg, var(--ribbon-expense-from), var(--ribbon-expense-to))', 'Списания']].map(([c, l]) => (
                    <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ width: 10, height: 10, borderRadius: 3, background: c }} />{l}
                    </span>
                  ))}
                </div>
              </div>

              <div style={{ position: 'relative', height: 320, paddingLeft: 50, overflow: 'hidden' }}>
                {yLabels.map(l => (
                  <div key={l.y} style={{ position: 'absolute', left: 0, top: l.y, transform: 'translateY(-7px)', fontSize: 11, color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums' }}>{l.v}</div>
                ))}
                <div style={{ position: 'relative', height: '100%', borderLeft: '1px solid var(--border-inner)' }}>
                  {yLabels.map(l => (
                    <div key={l.y} style={{ position: 'absolute', left: 0, right: 0, top: l.y, height: 1, background: 'var(--border-inner)' }} />
                  ))}
                  <div style={{ position: 'absolute', left: 0, right: 0, top: '50%', height: 2, background: '#D7DCEA' }} />

                  {/* ── Анимация 2: ribbon bars grow from midline (декоративная сглаженная огибающая) ── */}
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', gap: 2, padding: '0 10px' }}>
                    {divBars.map((bar, i) => {
                      const isHoverCapsule = hoverCapsuleIdx === i
                      return (
                        <div key={i} style={{ flex: 1, position: 'relative', height: '100%' }}>
                          {bar.incH > 0 && (
                            <motion.div
                              initial={reduced ? false : { scaleY: 0 }}
                              animate={{ scaleY: 1 }}
                              transition={{ delay: i * 0.03, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                              style={{
                                position: 'absolute', left: '50%', transform: 'translateX(-50%)',
                                width: 9, top: bar.incTop, height: bar.incH, borderRadius: 5,
                                background: 'linear-gradient(180deg, var(--ribbon-income-from), var(--ribbon-income-mid), var(--ribbon-income-to))',
                                transformOrigin: 'bottom',
                                filter: isHoverCapsule ? 'brightness(1.12)' : 'none',
                                boxShadow: isHoverCapsule ? '0 0 0 1.5px var(--income, #16a34a)' : 'none',
                              }}
                            />
                          )}
                          {bar.expH > 0 && (
                            <motion.div
                              initial={reduced ? false : { scaleY: 0 }}
                              animate={{ scaleY: 1 }}
                              transition={{ delay: i * 0.03, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                              style={{
                                position: 'absolute', left: '50%', transform: 'translateX(-50%)',
                                width: 9, top: bar.expTop, height: bar.expH, borderRadius: 5,
                                background: 'linear-gradient(180deg, var(--ribbon-expense-from), var(--ribbon-expense-to))',
                                transformOrigin: 'top',
                                filter: isHoverCapsule ? 'brightness(1.12)' : 'none',
                                boxShadow: isHoverCapsule ? '0 0 0 1.5px var(--expense, #dc2626)' : 'none',
                              }}
                            />
                          )}
                        </div>
                      )
                    })}
                  </div>

                  {/* ── Hover-зоны по РЕАЛЬНЫМ месяцам (не по интерполированным капсулам) ── */}
                  {monthHotspots.map(h => {
                    const isHover = hoverBar === h.m
                    return (
                      <div key={h.m}
                        onMouseEnter={() => { setHoverBar(h.m); setHoverCapsuleIdx(h.capsuleIdx) }}
                        onMouseLeave={() => { setHoverBar(v => v === h.m ? null : v); setHoverCapsuleIdx(v => v === h.capsuleIdx ? null : v) }}
                        style={{ position: 'absolute', top: 0, bottom: 0, left: h.leftPct, width: h.widthPct, transform: 'translateX(-50%)', cursor: 'default', zIndex: 3 }}>
                        {isHover && (
                          <>
                            {/* поступление — над пином */}
                            {h.inc > 0 && (
                              <div style={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)', top: h.incLabelTop, fontSize: 10.5, fontWeight: 700, color: 'var(--income, #16a34a)', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', pointerEvents: 'none' }}>
                                {fmt(h.inc)}
                              </div>
                            )}
                            {/* списание — под пином */}
                            {h.exp > 0 && (
                              <div style={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)', top: h.expLabelTop, fontSize: 10.5, fontWeight: 700, color: 'var(--expense, #dc2626)', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', pointerEvents: 'none' }}>
                                {fmt(h.exp)}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 10px 0 50px', fontSize: 10.5, color: 'var(--text-faint)' }}>
                {monthLabels.map((m, i) => <span key={i}>{m}</span>)}
              </div>
            </div>

            {/* Банки — плашки */}
            <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(ddsSummary?.by_bank || []).map(b => (
                <div key={b.bank} style={{
                  ...card({ padding: '14px 18px', borderRadius: 'var(--radius-card-sm)' }),
                  flex: 1, borderLeft: `3px solid ${bankColor(b.bank)}`,
                  display: 'flex', flexDirection: 'column', justifyContent: 'center',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{b.bank}</span>
                    <span style={{ fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: bankColor(b.bank) }}>{fmt(b.balance)} ₽</span>
                  </div>
                  <div style={{ display: 'flex', gap: 14, marginTop: 8, fontSize: 11.5, color: 'var(--text-muted)' }}>
                    <span>↓ {fmt(b.income)} ₽</span>
                    <span>↑ {fmt(b.expense)} ₽</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Накопительный остаток ── */}
          <div style={{ ...card({ padding: '22px 24px 14px' }), marginBottom: 16 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>Накопительный остаток</div>
            <ResponsiveContainer width="100%" height={150}>
              <AreaChart data={cumulativeData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="dashAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.20} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="period" tick={{ fontSize: 10.5, fill: 'var(--text-faint)' }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12, color: 'var(--text-primary)' }}
                  formatter={(v) => [fmt(v) + ' ₽', 'Остаток']}
                />
                <Area dataKey="cumulative" stroke="var(--accent)" strokeWidth={2.5} fill="url(#dashAreaGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* ── Таблица по месяцам ── */}
          <div style={card({ padding: '20px' })}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>Детализация по месяцам</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-inner)', background: 'var(--bg-subtle)' }}>
                  {['Период', 'Поступления', 'Списания', 'Чистый поток', 'Накопит. остаток', ''].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 12px', color: 'var(--text-faint)', fontWeight: 700, fontSize: 10.5, letterSpacing: '.04em', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {periods.map((row, i) => (
                  <>
                    <tr key={i}
                      style={{ borderBottom: '1px solid var(--border-row)', cursor: 'pointer', background: expandedPeriod === row.period ? 'var(--accent-tint)' : (i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-subtle)') }}
                      onClick={() => setExpandedPeriod(expandedPeriod === row.period ? null : row.period)}>
                      <td style={{ padding: '10px 12px', fontWeight: 500, color: 'var(--text-primary)' }}>{formatPeriod(row.period)}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--income)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmt(row.total_income)} ₽</td>
                      <td style={{ padding: '10px 12px', color: 'var(--expense)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmt(row.total_expense)} ₽</td>
                      <td style={{ padding: '10px 12px', color: row.net >= 0 ? 'var(--income)' : 'var(--expense)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                        {row.net >= 0 ? '+' : ''}{fmt(row.net)} ₽
                      </td>
                      <td style={{ padding: '10px 12px', color: 'var(--accent)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmt(row.cumulative)} ₽</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-faint)', fontSize: 12 }}>{expandedPeriod === row.period ? '▲' : '▼'}</td>
                    </tr>
                    {expandedPeriod === row.period && Object.entries(row.by_bank || {}).map(([bank, data]) => (
                      <tr key={bank} style={{ borderBottom: '1px solid var(--border-row)', background: 'var(--bg-subtle)' }}>
                        <td style={{ padding: '7px 12px 7px 26px', color: 'var(--text-muted)', fontSize: 13 }}>
                          <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: bankColor(bank), marginRight: 7 }}></span>
                          {bank}
                        </td>
                        <td style={{ padding: '7px 12px', color: 'var(--income)', fontSize: 13 }}>{fmt(data.income)} ₽</td>
                        <td style={{ padding: '7px 12px', color: 'var(--expense)', fontSize: 13 }}>{fmt(data.expense)} ₽</td>
                        <td style={{ padding: '7px 12px', color: data.net >= 0 ? 'var(--income)' : 'var(--expense)', fontSize: 13 }}>
                          {data.net >= 0 ? '+' : ''}{fmt(data.net)} ₽
                        </td>
                        <td colSpan={2}></td>
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: '2px solid var(--border-card)', background: 'var(--bg-subtle)' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--text-primary)' }}>ИТОГО</td>
                  <td style={{ padding: '10px 12px', color: 'var(--income)', fontWeight: 700 }}>{fmt(periods.reduce((s, r) => s + (r.total_income || 0), 0))} ₽</td>
                  <td style={{ padding: '10px 12px', color: 'var(--expense)', fontWeight: 700 }}>{fmt(periods.reduce((s, r) => s + (r.total_expense || 0), 0))} ₽</td>
                  <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(periods.reduce((s, r) => s + (r.net || 0), 0))} ₽</td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            </table>
          </div>

        </>}
      </div>
    </div>
  )
}
