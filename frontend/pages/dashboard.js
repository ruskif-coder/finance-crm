import Navbar, { can, firstAllowedHref } from '../components/Navbar'
import { useState, useEffect, useRef, useMemo } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { motion, useMotionValue, useTransform, animate, useReducedMotion } from 'framer-motion'
import { MONO, UI, IconBtn } from '../components/salesTableKit'
import { bankColor, signRub } from '../lib/salesFormat'
import { makeApi as api } from '../lib/http'
import { T } from '../lib/tokens'
import useIsMobile from '../components/mobile/useIsMobile'
import CashflowMobile from '../components/mobile/CashflowMobile'

// ── Форматтеры ───────────────────────────────────────────────────
const RUB = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtRub = (n) => `${RUB(n)} ₽`
// «40,37 млн»
const mln2 = (n) => (n / 1e6).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
// «27,4 млн» (одна десятая)
const mln1 = (n) => (n / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 })
// целые млн для оси
const mlnAxis = (n) => Math.round(n / 1e6)

const EASE = [0.22, 1, 0.36, 1]

const MONTH_SHORT = { '01': 'янв', '02': 'фев', '03': 'мар', '04': 'апр', '05': 'май', '06': 'июн', '07': 'июл', '08': 'авг', '09': 'сен', '10': 'окт', '11': 'ноя', '12': 'дек' }
const MONTH_FULL = { '01': 'Январь', '02': 'Февраль', '03': 'Март', '04': 'Апрель', '05': 'Май', '06': 'Июнь', '07': 'Июль', '08': 'Август', '09': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь' }

const shortMonth = (p) => { if (!p) return '—'; const [, m] = p.split('-'); return MONTH_SHORT[m] || m }
const formatPeriod = (p) => { if (!p) return '—'; const [y, m] = p.split('-'); return `${MONTH_SHORT[m] || m} ${y}` }
const rangeLabel = (from, to) => {
  const one = (p) => { if (!p) return ''; const [y, m] = p.split('-'); return `${(MONTH_FULL[m] || m)} ${y}` }
  return `${one(from)} — ${one(to)}`.toUpperCase()
}

// niceMax — «красивый» потолок шкалы
const niceMax = (value) => {
  if (!value || value <= 0 || !isFinite(value)) return 1
  const v = value * 1.05
  const exp = Math.floor(Math.log10(v))
  const base = v / Math.pow(10, exp)
  let nb
  if (base <= 1) nb = 1; else if (base <= 2) nb = 2; else if (base <= 2.5) nb = 2.5
  else if (base <= 5) nb = 5; else nb = 10
  return nb * Math.pow(10, exp)
}

// Динамический потолок графика: максимум данных + 20% запаса, вверх до целых млн
// (пол 1 млн, чтобы не делить на 0). Даёт нормальную детализацию баров под сумму.
const chartScale = (maxVal) => Math.max(1e6, Math.ceil((maxVal || 0) * 1.2 / 1e6) * 1e6)

// ── Банки ────────────────────────────────────────────────────────
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']

// ── Цвета баров ──────────────────────────────────────────────────
const INCOME = T.income
const OUTFLOW = T.expense
const EMPTY = 'var(--border-inner)'
const FACT = T.accent
const FORECAST = T.accentSoft
const WARN_TXT = T.warningText
const DANGER_TXT = T.danger

const CELLS = 14
const WEEK_OFF = [-0.375, -0.125, 0.125, 0.375]

// ── Токен-стили карточки ─────────────────────────────────────────
const card = (extra = {}) => ({
  background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 18, boxShadow: 'var(--shadow-card)', ...extra,
})

// ── Count-up с произвольным форматтером ──────────────────────────
function CountUp({ value, format, color, style }) {
  const reduced = useReducedMotion()
  const mv = useMotionValue(0)
  const out = useTransform(mv, (v) => format(v))
  const prev = useRef(0)
  useEffect(() => {
    if (reduced) { mv.set(value); return }
    const ctrl = animate(mv, value, { duration: 0.85, ease: EASE, from: prev.current })
    prev.current = value
    return () => ctrl.stop()
  }, [value, reduced])
  return <motion.span style={{ color, fontVariantNumeric: 'tabular-nums', ...style }}>{out}</motion.span>
}

// ── Линейная интерполяция по массиву ─────────────────────────────
const interp = (arr, x) => {
  const n = arr.length
  if (!n) return 0
  const c = Math.max(0, Math.min(n - 1, x))
  const lo = Math.floor(c), hi = Math.min(n - 1, lo + 1), f = c - lo
  return arr[lo] * (1 - f) + arr[hi] * f
}

// ── Двусторонний пиксельный график «Движение денег по неделям» ───
function CashWeeksChart({ weeks, scaleMax, reduced }) {
  const [hover, setHover] = useState(null)
  const total = weeks.length
  const cellsFor = (v) => v > 0 ? Math.max(1, Math.round((v / scaleMax) * CELLS)) : 0
  const yRows = [
    { top: '0%', v: mlnAxis(scaleMax) },
    { top: 'calc(25% - 5px)', v: mlnAxis(scaleMax / 2) },
    { top: 'calc(50% - 5px)', v: 0 },
    { top: 'calc(75% - 5px)', v: mlnAxis(scaleMax / 2) },
    { top: 'calc(100% - 10px)', v: mlnAxis(scaleMax) },
  ]
  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 170, position: 'relative' }}>
      {/* Ось Y */}
      <div style={{ width: 52, position: 'relative', flexShrink: 0 }}>
        {yRows.map((r, i) => (
          <div key={i} style={{ position: 'absolute', right: 8, top: r.top, fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{r.v}</div>
        ))}
      </div>
      {/* Область графика */}
      <div style={{ position: 'relative', flex: 1, height: '100%' }}
        onMouseLeave={() => setHover(null)}>
        {/* сетка */}
        {[0, 25, 50, 75, 100].map((p) => (
          <div key={p} style={{ position: 'absolute', left: 0, right: 0, top: `${p}%`, height: 1, background: p === 50 ? 'var(--border-card)' : 'var(--border-row)' }} />
        ))}
        {/* колонки недель */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', gap: 4 }}>
          {weeks.map((wk, i) => {
            const isH = hover === i
            const incN = cellsFor(wk.income), expN = cellsFor(wk.expense)
            return (
              <div key={i} style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}
                onMouseEnter={() => setHover(i)}>
                {/* верх — поступления */}
                <motion.div
                  initial={reduced ? false : { scaleY: 0 }} animate={{ scaleY: 1 }}
                  transition={{ delay: i * 0.03, duration: 0.55, ease: EASE }}
                  style={{ flex: 1, transformOrigin: 'bottom', display: 'flex', flexDirection: 'column', gap: 2, paddingBottom: 1 }}>
                  {Array.from({ length: CELLS }).map((_, c) => (
                    <div key={c} style={{ flex: 1, borderRadius: 2, background: c >= CELLS - incN ? INCOME : EMPTY, filter: isH && c >= CELLS - incN ? 'brightness(1.08)' : 'none' }} />
                  ))}
                </motion.div>
                {/* низ — списания */}
                <motion.div
                  initial={reduced ? false : { scaleY: 0 }} animate={{ scaleY: 1 }}
                  transition={{ delay: i * 0.03, duration: 0.55, ease: EASE }}
                  style={{ flex: 1, transformOrigin: 'top', display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 1 }}>
                  {Array.from({ length: CELLS }).map((_, c) => (
                    <div key={c} style={{ flex: 1, borderRadius: 2, background: c < expN ? OUTFLOW : EMPTY, filter: isH && c < expN ? 'brightness(1.08)' : 'none' }} />
                  ))}
                </motion.div>
                {isH && <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, borderLeft: '1px dashed var(--text-faint)', pointerEvents: 'none' }} />}
              </div>
            )
          })}
        </div>
        {/* тултип */}
        {hover != null && weeks[hover] && (() => {
          const wk = weeks[hover]
          const right = hover / Math.max(1, total - 1) > 0.6
          return (
            <div style={{
              position: 'absolute', top: 8, left: `${(hover + 0.5) / total * 100}%`,
              transform: right ? 'translateX(calc(-100% - 12px))' : 'translateX(12px)',
              minWidth: 184, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14,
              boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 24px rgba(28,36,51,.10)', padding: '12px 14px',
              pointerEvents: 'none', zIndex: 5,
            }}>
              <div style={{ fontFamily: UI, fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{wk.monthLabel} · неделя {wk.week}</div>
              <TipRow color={INCOME} label="поступления" value={fmtRub(wk.income)} />
              <TipRow color={OUTFLOW} label="списания" value={fmtRub(wk.expense)} />
              <div style={{ borderTop: '1px solid var(--border-row)', margin: '7px 0 6px' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>
                <span style={{ fontFamily: UI, color: 'var(--text-muted)' }}>итог недели</span>
                <span style={{ color: (wk.income - wk.expense) >= 0 ? INCOME : DANGER_TXT }}>{signRub(wk.income - wk.expense)}</span>
              </div>
            </div>
          )
        })()}
      </div>
    </div>
  )
}

const TipRow = ({ color, label, value }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '3px 0' }}>
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: UI, fontSize: 12, color: 'var(--text-secondary)' }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />{label}
    </span>
    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</span>
  </div>
)

// ── График «Накопительный остаток» (вниз от 0 — красным) ─────────
function CumWeeksChart({ weeks, reduced }) {
  const [hover, setHover] = useState(null)
  const total = weeks.length
  const posMax = chartScale(Math.max(0, ...weeks.map(w => w.value)))
  const negRaw = Math.min(0, ...weeks.map(w => w.value))
  const negMax = negRaw < 0 ? chartScale(Math.abs(negRaw)) : 0
  // Ячеек под нулём: пропорционально магнитуде, но не меньше 3 — иначе мелкая
  // просадка «схлопывается» в один пин и вариация не читается.
  const botCells = negMax > 0 ? Math.min(CELLS - 3, Math.max(3, Math.round(CELLS * negMax / (posMax + negMax)))) : 0
  const topCells = CELLS - botCells
  // Нулевая линия — ровно на границе ячеек, поэтому все ячейки одной высоты
  // (высота зоны = доля ячеек), а пины выше/ниже нуля единообразны.
  const zeroFrac = topCells / CELLS
  const posFill = (v) => v > 0 ? Math.max(1, Math.round((v / posMax) * topCells)) : 0
  const negFill = (v) => v < 0 && negMax > 0 ? Math.max(1, Math.round((Math.abs(v) / negMax) * botCells)) : 0
  const NEG = 'var(--dot-overdue)'
  const yRows = negMax > 0
    ? [{ f: 0, v: mlnAxis(posMax) }, { f: zeroFrac, v: 0 }, { f: 1, v: -mlnAxis(negMax) }]
    : [{ f: 0, v: mlnAxis(posMax) }, { f: 1 / 3, v: mlnAxis(posMax * 2 / 3) }, { f: 2 / 3, v: mlnAxis(posMax / 3) }, { f: 1, v: 0 }]
  return (
    <div style={{ display: 'flex', height: 180, position: 'relative' }}>
      <div style={{ width: 52, position: 'relative', flexShrink: 0 }}>
        {yRows.map((r, i) => (
          <div key={i} style={{ position: 'absolute', right: 8, top: `calc(${r.f * 100}% - ${r.f === 1 ? 10 : r.f === 0 ? 0 : 5}px)`, fontFamily: MONO, fontSize: 10, color: r.v < 0 ? DANGER_TXT : 'var(--text-faint)' }}>{r.v}</div>
        ))}
      </div>
      <div style={{ position: 'relative', flex: 1, height: '100%' }} onMouseLeave={() => setHover(null)}>
        {yRows.map((r, i) => (
          <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: `${r.f * 100}%`, height: 1, background: r.v === 0 ? 'var(--border-card)' : 'var(--border-row)' }} />
        ))}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', gap: 4 }}>
          {weeks.map((wk, i) => {
            const isH = hover === i
            const col = wk.isForecast ? FORECAST : FACT
            const pf = posFill(wk.value), nf = negFill(wk.value)
            return (
              <div key={i} style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }} onMouseEnter={() => setHover(i)}>
                {/* область над нулём */}
                <motion.div
                  initial={reduced ? false : { scaleY: 0 }} animate={{ scaleY: 1 }}
                  transition={{ delay: i * 0.03, duration: 0.55, ease: EASE }}
                  style={{ height: `${zeroFrac * 100}%`, transformOrigin: 'bottom', display: 'flex', flexDirection: 'column', gap: 2, paddingBottom: negMax > 0 ? 1 : 0 }}>
                  {Array.from({ length: topCells }).map((_, c) => (
                    <div key={c} style={{ flex: 1, borderRadius: 2, background: c >= topCells - pf ? col : EMPTY, filter: isH && c >= topCells - pf ? 'brightness(1.08)' : 'none' }} />
                  ))}
                </motion.div>
                {/* область под нулём (красным) */}
                {negMax > 0 && (
                  <motion.div
                    initial={reduced ? false : { scaleY: 0 }} animate={{ scaleY: 1 }}
                    transition={{ delay: i * 0.03, duration: 0.55, ease: EASE }}
                    style={{ height: `${(1 - zeroFrac) * 100}%`, transformOrigin: 'top', display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 1 }}>
                    {Array.from({ length: botCells }).map((_, c) => (
                      <div key={c} style={{ flex: 1, borderRadius: 2, background: c < nf ? NEG : EMPTY, filter: isH && c < nf ? 'brightness(1.08)' : 'none' }} />
                    ))}
                  </motion.div>
                )}
                {isH && <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, borderLeft: '1px dashed var(--text-faint)', pointerEvents: 'none' }} />}
              </div>
            )
          })}
        </div>
        {hover != null && weeks[hover] && (() => {
          const wk = weeks[hover]
          const right = hover / Math.max(1, total - 1) > 0.6
          return (
            <div style={{
              position: 'absolute', top: 6, left: `${(hover + 0.5) / total * 100}%`,
              transform: right ? 'translateX(calc(-100% - 12px))' : 'translateX(12px)',
              minWidth: 168, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14,
              boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 24px rgba(28,36,51,.10)', padding: '12px 14px', pointerEvents: 'none', zIndex: 5,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
                <span style={{ fontFamily: UI, fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>{wk.monthLabel} · неделя {wk.week}</span>
                <span style={{ fontFamily: MONO, fontSize: 10, textTransform: 'uppercase', color: wk.value < 0 ? DANGER_TXT : (wk.isForecast ? FORECAST : FACT) }}>{wk.value < 0 ? 'разрыв' : (wk.isForecast ? 'прогноз' : 'факт')}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '3px 0' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: UI, fontSize: 12, color: 'var(--text-secondary)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: wk.value < 0 ? 'var(--dot-overdue)' : (wk.isForecast ? FORECAST : FACT) }} />остаток
                </span>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: wk.value < 0 ? DANGER_TXT : 'var(--text-primary)' }}>{signRub(wk.value)}</span>
              </div>
            </div>
          )
        })()}
      </div>
    </div>
  )
}

// ── Сегментированный переключатель ───────────────────────────────
function Seg({ value, onChange, options, reduced }) {
  return (
    <div style={{ position: 'relative', display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 12, padding: 3 }}>
      {options.map(([v, label]) => (
        <div key={v} onClick={() => onChange(v)} style={{ position: 'relative', padding: '7px 14px', borderRadius: 9, cursor: 'pointer', fontFamily: UI, fontSize: 13, fontWeight: value === v ? 700 : 600, zIndex: 1, color: value === v ? 'var(--accent)' : 'var(--text-secondary)', transition: 'color .15s' }}>
          {value === v && <motion.div layoutId="ddsSeg" style={{ position: 'absolute', inset: 0, borderRadius: 9, background: 'var(--accent-tint)', zIndex: -1 }} transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 36 }} />}
          {label}
        </div>
      ))}
    </div>
  )
}

const selStyle = { fontFamily: UI, padding: '9px 14px', borderRadius: 12, background: 'var(--bg-card)', border: '1px solid var(--border-card)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }

// ═══════════════════════════════════════════════════════════════
export default function DashboardV2() {
  const router = useRouter()
  const reduced = useReducedMotion()
  const isMobile = useIsMobile()
  const [ddsData, setDdsData] = useState({ periods: [] })
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [selectedBank, setSelectedBank] = useState('all')
  const [groupBy, setGroupBy] = useState('period')
  const [dateFrom, setDateFrom] = useState(() => { const d = new Date(); d.setMonth(d.getMonth() - 11); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` })
  const [dateTo, setDateTo] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` })

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    // Нет доступа к ДДС → уводим на первый доступный экран пользователя
    let perms = {}; try { perms = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
    const role = localStorage.getItem('role') || ''
    if (!can(perms, 'dashboard')) { router.replace(firstAllowedHref(perms, role)); return }
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
      const [d, s] = await Promise.all([
        a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}&group_by=${groupBy}`),
        a.get('/reports/dds/summary'),
      ])
      setDdsData(d.data || { periods: [] })
      setSummary(s.data || null)
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
    finally { setLoading(false) }
  }

  const loadDds = async (token) => {
    try {
      const a = api(token)
      const bankParam = selectedBank !== 'all' ? `&bank=${selectedBank}` : ''
      const res = await a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}${bankParam}&group_by=${groupBy}`)
      setDdsData(res.data || { periods: [] })
    } catch (e) { }
  }

  const periods = ddsData?.periods || []

  // ── Производные данные ──
  const nowKey = useMemo(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }, [])

  const months = useMemo(() => periods.map(p => ({
    period: p.period, income: p.total_income || 0, expense: p.total_expense || 0,
    net: p.net || 0, cumulative: p.cumulative || 0, by_bank: p.by_bank || {},
    isForecast: p.period > nowKey,
  })), [periods, nowKey])

  // недельная интерполяция (N мес × 4)
  const cashWeeks = useMemo(() => {
    const inc = months.map(m => m.income), exp = months.map(m => m.expense)
    const out = []
    months.forEach((m, mi) => WEEK_OFF.forEach((off, w) => {
      out.push({ income: Math.max(0, interp(inc, mi + off)), expense: Math.max(0, interp(exp, mi + off)), monthLabel: formatPeriod(m.period), week: w + 1 })
    }))
    return out
  }, [months])

  const cumWeeks = useMemo(() => {
    const cum = months.map(m => m.cumulative)
    const out = []
    months.forEach((m, mi) => WEEK_OFF.forEach((off, w) => {
      out.push({ value: interp(cum, mi + off), monthLabel: formatPeriod(m.period), week: w + 1, isForecast: m.isForecast })
    }))
    return out
  }, [months])

  const cashScale = useMemo(() => chartScale(Math.max(0, ...cashWeeks.map(w => w.income), ...cashWeeks.map(w => w.expense))), [cashWeeks])
  const cumScale = useMemo(() => chartScale(Math.max(0, ...cumWeeks.map(w => w.value))), [cumWeeks])

  const cumStats = useMemo(() => {
    if (!months.length) return { max: null, min: null, gap: null }
    let max = months[0], min = months[0], gap = null
    months.forEach(m => { if (m.cumulative > max.cumulative) max = m; if (m.cumulative < min.cumulative) min = m; if (m.cumulative < 0 && !gap) gap = m })
    return { max, min, gap }
  }, [months])

  const actualBalance = summary?.total_balance ?? summary?.net ?? 0
  const planNet = (summary?.plan_income || 0) - (summary?.plan_expense || 0)
  const forecastBalance = actualBalance + planNet
  const forecastDelta = forecastBalance - actualBalance

  const accounts = (summary?.by_bank || [])

  const totals = useMemo(() => ({
    income: months.reduce((s, m) => s + m.income, 0),
    expense: months.reduce((s, m) => s + m.expense, 0),
    net: months.reduce((s, m) => s + m.net, 0),
    lastCum: months.length ? months[months.length - 1].cumulative : 0,
  }), [months])

  const exportCsv = () => {
    const head = ['Период', 'Поступления', 'Списания', 'Чистый поток', 'Накопит. остаток']
    const rows = months.map(m => [formatPeriod(m.period), Math.round(m.income), Math.round(m.expense), Math.round(m.net), Math.round(m.cumulative)])
    const csv = [head, ...rows, ['ИТОГО', Math.round(totals.income), Math.round(totals.expense), Math.round(totals.net), Math.round(totals.lastCum)]]
      .map(r => r.join(';')).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `dds_${dateFrom}_${dateTo}.csv`; a.click(); URL.revokeObjectURL(url)
  }

  const rise = (i) => reduced ? {} : { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { delay: i * 0.07, duration: 0.4, ease: EASE } }

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Navbar active="dds" />
        <Head><title>ДДС | Финансовый учёт</title></Head>
        {loading || !summary ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>Загрузка…</div>
        ) : (
          <CashflowMobile
            dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} groupBy={groupBy} setGroupBy={setGroupBy}
            kpi={{ actualBalance, forecastBalance, forecastDelta, planIncome: summary.plan_income || 0, planExpense: summary.plan_expense || 0, incomeCount: summary.income_count ?? 0, expenseCount: summary.expense_count ?? 0, accountsCount: accounts.length }}
            cashWeeks={cashWeeks} cashScale={cashScale} cumWeeks={cumWeeks} cumScale={cumScale}
            accounts={accounts} months={months} totals={totals}
            expanded={expanded} setExpanded={setExpanded} exportCsv={exportCsv} />
        )}
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Navbar active="dds" />
      <Head><title>ДДС | Финансовый учёт</title></Head>

      <div style={{ maxWidth: 1920, margin: '0 auto', padding: 32 }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Загрузка…</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* ── Шапка ── */}
            <motion.div {...rise(0)} style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
                <h1 style={{ margin: 0, fontSize: 30, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-.02em' }}>Движение денежных средств</h1>
                <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{rangeLabel(dateFrom, dateTo)}</span>
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={selStyle} />
                <span style={{ color: 'var(--text-faint)' }}>—</span>
                <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={selStyle} />
                <select value={selectedBank} onChange={e => setSelectedBank(e.target.value)} style={selStyle}>
                  <option value="all">Все банки</option>
                  {BANKS.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
                <Seg value={groupBy} onChange={setGroupBy} reduced={reduced} options={[['period', 'По периоду'], ['date', 'По дате']]} />
              </div>
            </motion.div>

            {/* ── KPI-карточка (4 колонки) ── */}
            {summary && (
              <motion.div {...rise(1)} style={{ ...card({ padding: '0 36px' }), display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
                {[
                  { label: 'Актуальный баланс', val: <CountUp value={actualBalance} format={RUB} color={actualBalance >= 0 ? INCOME : DANGER_TXT} />, unit: '₽', unitColor: actualBalance >= 0 ? INCOME : DANGER_TXT, sub: <span>на счетах сегодня · {accounts.length} источника</span> },
                  {
                    label: 'Прогнозный баланс', val: <CountUp value={forecastBalance} format={RUB} color={FACT} />, unit: '₽', unitColor: FACT,
                    sub: <span style={{ display: 'inline-block', background: 'var(--warning-tint)', color: WARN_TXT, borderRadius: 8, padding: '4px 8px', fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{signRub(forecastDelta)} к текущему</span>
                  },
                  { label: 'План поступлений', val: <CountUp value={summary.plan_income || 0} format={mln2} color="var(--text-primary)" />, unit: 'млн ₽', sub: <span>{summary.income_count ?? 0} операций · {RUB(summary.plan_income || 0)} ₽</span> },
                  { label: 'План расходов', val: <CountUp value={summary.plan_expense || 0} format={mln2} color="var(--text-primary)" />, unit: 'млн ₽', sub: <span>{summary.expense_count ?? 0} операций · {RUB(summary.plan_expense || 0)} ₽</span> },
                ].map((k, i) => (
                  <div key={k.label} style={{ borderRight: i < 3 ? '1px solid var(--border-inner)' : 'none', padding: i === 0 ? '28px 26px 28px 0' : i === 3 ? '28px 0 28px 26px' : '28px 26px' }}>
                    <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{k.label}</div>
                    <div style={{ fontFamily: MONO, fontWeight: 700, fontSize: 42, letterSpacing: '-.03em', lineHeight: 1, whiteSpace: 'nowrap', margin: '14px 0 10px', display: 'flex', alignItems: 'baseline', gap: 6 }}>
                      {k.val}
                      <span style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-faint)' }}>{k.unit}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{k.sub}</div>
                  </div>
                ))}
              </motion.div>
            )}

            {/* ── Ряд 2: график недель + счета ── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'stretch' }}>
              <motion.div {...rise(2)} style={{ ...card({ padding: '24px 28px 18px' }), display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Движение денег по неделям</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginTop: 4 }}>Поступления вверх · Списания вниз</div>
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-muted)' }}>
                    {[[INCOME, 'поступления'], [OUTFLOW, 'списания']].map(([c, l]) => (
                      <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                    ))}
                  </div>
                </div>
                <CashWeeksChart weeks={cashWeeks} scaleMax={cashScale} reduced={reduced} />
                <div style={{ display: 'grid', gridTemplateColumns: `52px repeat(${Math.max(1, months.length)},1fr)`, marginTop: 10 }}>
                  <span />
                  {months.map((m, i) => <span key={i} style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>{shortMonth(m.period)}</span>)}
                </div>
              </motion.div>

              {/* Счета */}
              <motion.div {...rise(3)} style={{ ...card({ padding: '24px 24px 8px' }) }}>
                <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Счета</div>
                <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginTop: 4, marginBottom: 4 }}>Остаток и обороты за период</div>
                {accounts.map((b, i) => (
                  <div key={b.bank} style={{ padding: '16px 0', borderBottom: i < accounts.length - 1 ? '1px solid var(--border-row)' : 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: bankColor(b.bank) }} />{b.bank}
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{fmtRub(b.balance)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 14, marginTop: 7, fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
                      <span>↑ {RUB(b.income)}</span><span>↓ {RUB(b.expense)}</span>
                    </div>
                  </div>
                ))}
              </motion.div>
            </div>

            {/* ── Накопительный остаток ── */}
            <motion.div {...rise(4)} style={{ ...card({ padding: '24px 28px 18px' }) }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Накопительный остаток</div>
                  <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginTop: 4 }}>Баланс на конец месяца · прогноз с апреля</div>
                </div>
                <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-muted)' }}>
                    {[[FACT, 'факт'], [FORECAST, 'прогноз']].map(([c, l]) => (
                      <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                    ))}
                  </div>
                  {cumStats.max && (
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>максимум</div>
                      <div style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{mln1(cumStats.max.cumulative)} млн · {shortMonth(cumStats.max.period)}</div>
                    </div>
                  )}
                  {cumStats.min && (
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>минимум</div>
                      <div style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: WARN_TXT }}>{mln1(cumStats.min.cumulative)} млн · {shortMonth(cumStats.min.period)}</div>
                    </div>
                  )}
                </div>
              </div>
              <CumWeeksChart weeks={cumWeeks} reduced={reduced} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 18, paddingTop: 16, marginTop: 8, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                <span>шкала до {mlnAxis(cumScale)} млн ₽</span>
                <span>факт по выпискам, далее — план операций</span>
                <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, color: cumStats.gap ? DANGER_TXT : INCOME }}>
                  <span style={{ width: 7, height: 7, borderRadius: 2, background: cumStats.gap ? 'var(--dot-overdue)' : 'var(--income)' }} />
                  {cumStats.gap ? `кассовый разрыв: ${shortMonth(cumStats.gap.period)}` : 'кассовых разрывов в периоде нет'}
                </span>
              </div>
            </motion.div>

            {/* ── Детализация по месяцам ── */}
            <motion.div {...rise(5)} style={{ ...card({ padding: '28px 30px 22px' }) }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18, gap: 12 }}>
                <div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Детализация по месяцам</div>
                  <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginTop: 4 }}>Клик по строке — разбивка по счетам</div>
                </div>
                <IconBtn title="Выгрузить в Excel" onClick={exportCsv}>⭳</IconBtn>
              </div>

              {(() => {
                const GRID = { display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr 1fr 1fr 28px', gap: 16, alignItems: 'center' }
                return (
                  <div>
                    {/* шапка */}
                    <div style={{ ...GRID, padding: '0 8px 10px', borderBottom: '1px solid var(--border-card)' }}>
                      {['Период', 'Поступления', 'Списания', 'Чистый поток', 'Накопит. остаток', ''].map((h, i) => (
                        <span key={i} style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', textAlign: i === 0 ? 'left' : i === 5 ? 'center' : 'right' }}>{h}</span>
                      ))}
                    </div>
                    {/* строки */}
                    {months.map((m) => {
                      const open = expanded === m.period
                      return (
                        <div key={m.period}>
                          <div onClick={() => setExpanded(open ? null : m.period)}
                            style={{ ...GRID, padding: '11px 8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', cursor: 'pointer', background: open ? T.tipBg : 'transparent', transition: 'background .12s' }}
                            onMouseEnter={e => { if (!open) e.currentTarget.style.background = 'var(--bg-subtle)' }}
                            onMouseLeave={e => { if (!open) e.currentTarget.style.background = 'transparent' }}>
                            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{formatPeriod(m.period)}</span>
                            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: INCOME, textAlign: 'right' }}>{RUB(m.income)}</span>
                            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', textAlign: 'right' }}>{RUB(m.expense)}</span>
                            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: m.net >= 0 ? INCOME : DANGER_TXT, textAlign: 'right' }}>{signRub(m.net)}</span>
                            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: m.cumulative >= 0 ? 'var(--accent)' : DANGER_TXT, textAlign: 'right' }}>{RUB(m.cumulative)}</span>
                            <span style={{ textAlign: 'center', fontSize: 10, color: 'var(--text-faint)' }}>{open ? '▴' : '▾'}</span>
                          </div>
                          {open && (
                            <motion.div initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24, ease: EASE }}
                              style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '2px 0 8px', padding: '10px 8px' }}>
                              {Object.entries(m.by_bank).map(([bank, d]) => (
                                <div key={bank} style={{ ...GRID, padding: '7px 8px', borderTop: '1px solid var(--border-inner)' }}>
                                  <span style={{ display: 'flex', alignItems: 'center', gap: 7, paddingLeft: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
                                    <span style={{ width: 7, height: 7, borderRadius: 2, background: bankColor(bank) }} />{bank}
                                  </span>
                                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{RUB(d.income)}</span>
                                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{RUB(d.expense)}</span>
                                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: (d.net ?? d.income - d.expense) >= 0 ? INCOME : DANGER_TXT, textAlign: 'right' }}>{signRub(d.net ?? d.income - d.expense)}</span>
                                  <span /><span />
                                </div>
                              ))}
                            </motion.div>
                          )}
                        </div>
                      )
                    })}
                    {/* итого */}
                    <div style={{ ...GRID, padding: '14px 8px 0' }}>
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-primary)' }}>Итого</span>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: INCOME, textAlign: 'right' }}>{RUB(totals.income)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', textAlign: 'right' }}>{RUB(totals.expense)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{signRub(totals.net)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{RUB(totals.lastCum)}</span>
                      <span />
                    </div>
                  </div>
                )
              })()}
            </motion.div>

          </div>
        )}
      </div>
    </div>
  )
}
