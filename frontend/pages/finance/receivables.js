import Navbar, { can } from '@/components/Navbar'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const ReceivablesMobile = dynamic(() => import('@/components/mobile/ReceivablesMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { makeApi as api } from '@/lib/http'
import { getPermissions } from '@/lib/auth'
import { grp0 as fmt } from '@/lib/salesFormat'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const MONO = "'JetBrains Mono', ui-monospace, monospace"
const UI = "'Manrope', system-ui, sans-serif"

const mln = (n) => (n == null ? '0' : (n / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 }))

const MONTH_NAMES = { '01': 'Янв', '02': 'Фев', '03': 'Мар', '04': 'Апр', '05': 'Май', '06': 'Июн', '07': 'Июл', '08': 'Авг', '09': 'Сен', '10': 'Окт', '11': 'Ноя', '12': 'Дек' }
const formatPeriod = (p) => { if (!p) return '—'; const m = p.match(/^(\d{4})-(\d{2})$/); return m ? `${MONTH_NAMES[m[2]] || m[2]} ${m[1]}` : p }
const formatDate = (d) => { if (!d) return '—'; const [y, mo, da] = String(d).split('-'); return da ? `${da}.${mo}.${y}` : d }

// getPermissions + can — из lib/auth (единый источник, admin-bypass)

// Тёмные тона текста поверх пастельных подложек (нет в токенах — из хендоффа).
const T_OVERDUE = '#C93A3E'      // на danger-tint
const T_CURRENT = '#B26A0C'      // на warning-tint
const T_KPI_CURRENT = '#C27510'  // KPI «текущая»
const C_PLAN = '#5B7CF0'         // = --dot-expense

const niceMax = (v) => {
  if (!v || v <= 0) return 1e6
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return step * pow
}

// 7 дневных корзин к сроку оплаты: «−» до срока (план), «+» после (текущая→просрочка)
const AGE_BUCKETS = [
  { key: 'b1', label: '−61 и ранее', type: 'future', test: (x) => x <= -61 },
  { key: 'b2', label: '−60…−31', type: 'future', test: (x) => x >= -60 && x <= -31 },
  { key: 'b3', label: '−30…−1', type: 'future', test: (x) => x >= -30 && x <= -1 },
  { key: 'b4', label: '+1…+15', type: 'current', test: (x) => x >= 0 && x <= 15 },
  { key: 'b5', label: '+16…+30', type: 'current', test: (x) => x >= 16 && x <= 30 },
  { key: 'b6', label: '+31…+60', type: 'overdue', test: (x) => x >= 31 && x <= 60 },
  { key: 'b7', label: '+60 и более', type: 'overdue', test: (x) => x > 60 },
]
const TYPE_COLOR = { future: C_PLAN, current: 'var(--dot-current-dz)', overdue: 'var(--dot-overdue)' }
// стили чипов «Возраст» в строке таблицы (bg-подложка / цвет текста / точка)
const CHIP = {
  overdue: { bg: 'var(--danger-tint)', fg: T_OVERDUE, dot: 'var(--dot-overdue)' },
  current: { bg: 'var(--warning-tint)', fg: T_CURRENT, dot: 'var(--dot-current-dz)' },
  future: { bg: 'var(--accent-tint)', fg: C_PLAN, dot: C_PLAN },
}
const TYPE_RU = { future: 'план', current: 'текущая', overdue: 'просрочка' }
const daysPastDue = (dueDate, asOf) => Math.round((new Date(asOf) - new Date(dueDate)) / 86400000)

// Плавный счётчик суммы (уважает reduce-motion).
function useCountUp(value, ms = 850) {
  const [n, setN] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    if (typeof window === 'undefined') { setN(value); return }
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setN(value); from.current = value; return }
    const start = performance.now(); const a = from.current; const b = value
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms)
      const e = 1 - Math.pow(1 - p, 3)
      setN(a + (b - a) * e)
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = b
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return n
}
const CountUp = ({ value }) => <>{fmt(useCountUp(value))}</>

const card = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const rise = (delay) => ({ animation: 'rcvRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: `${delay}s` })

// Мини-график: пиксельный вертикальный бар из 14 ячеек
function PixelBar({ value, max, color, delay }) {
  const filled = value > 0 ? Math.max(1, Math.round(value / max * 14)) : 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column-reverse', gap: 2, height: '100%', width: '62%', margin: '0 auto',
      animation: 'rcvGrow .55s cubic-bezier(0.22,1,0.36,1) both', animationDelay: `${delay}s`, transformOrigin: 'bottom' }}>
      {Array.from({ length: 14 }, (_, i) => (
        <div key={i} style={{ flex: 1, borderRadius: 2, background: i < filled ? color : 'var(--border-inner)' }} />
      ))}
    </div>
  )
}

export default function Receivables() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filterCounterparties, setFilterCounterparties] = useState([])
  const [filterArticles, setFilterArticles] = useState([])
  const [filterPeriods, setFilterPeriods] = useState([])
  const [onlyActual, setOnlyActual] = useState(true)
  const [sortCol, setSortCol] = useState('amount')
  const [sortDir, setSortDir] = useState('desc')
  const [expanded, setExpanded] = useState({})
  const [notes, setNotes] = useState({})
  const [savedNotes, setSavedNotes] = useState({})
  const [noteStatus, setNoteStatus] = useState({})
  const [hoverBucket, setHoverBucket] = useState(null)
  const [denied, setDenied] = useState(false)
  const isMobile = useIsMobile()

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    load(token)
  }, [])

  // Возврат на экран = перечитать. Финмодуль был пропущен, когда механизм
  // актуальности заводили 13.09.2026: правка операции не появлялась здесь
  // никогда, а число на экране — утверждение о деньгах (lib/useRefreshOnReturn).
  useRefreshOnReturn(() => load(localStorage.getItem('token')))

  useEffect(() => {
    if (data && Array.isArray(data.rows)) {
      const initial = Object.fromEntries(data.rows.map(r => [r.counterparty_id, r.note || '']))
      setNotes(initial); setSavedNotes(initial)
    }
  }, [data])

  const load = async (token) => {
    setLoading(true); setDenied(false)
    try { const res = await api(token).get('/reports/receivables'); setData(res.data) }
    catch (e) {
      if (e.response?.status === 401) router.push('/login')
      else if (e.response?.status === 403) setDenied(true)
    }
    finally { setLoading(false) }
  }

  const saveNote = async (cid, value) => {
    const token = localStorage.getItem('token')
    setNoteStatus(prev => ({ ...prev, [cid]: 'saving' }))
    try {
      await api(token).patch(`/reports/receivables/${cid}/note`, { note: value })
      setSavedNotes(prev => ({ ...prev, [cid]: value }))
      setNoteStatus(prev => ({ ...prev, [cid]: 'saved' }))
      setTimeout(() => setNoteStatus(prev => ({ ...prev, [cid]: undefined })), 1500)
    } catch (e) {
      setNotes(prev => ({ ...prev, [cid]: savedNotes[cid] ?? '' }))   // откат
      setNoteStatus(prev => ({ ...prev, [cid]: undefined }))
    }
  }

  const downloadExport = async () => {
    const token = localStorage.getItem('token')
    try {
      const params = new URLSearchParams()
      filterCounterparties.forEach(c => params.append('counterparty', c))
      filterArticles.forEach(a => params.append('article', a))
      filterPeriods.forEach(p => params.append('period', p))
      if (onlyActual) params.append('overdue_only', 'true')
      const qs = params.toString()
      const res = await api(token).get(`/reports/receivables/export${qs ? '?' + qs : ''}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      a.download = `debitorka_${new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '')}.xlsx`
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url)
    } catch (e) { /* тихо */ }
  }

  if (loading) return <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Загрузка дебиторской задолженности…</div></div>
  if (denied) return <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Нет доступа к разделу «Дебиторка».</div></div>
  if (!data || !Array.isArray(data.rows)) return <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Нет данных.</div></div>

  const canEditNote = can(getPermissions(), 'receivables', 'edit')

  // ── справочники для фильтров ──
  const allCounterparties = [...new Set(data.rows.map(r => r.counterparty))].filter(Boolean).sort()
  const allArticles = [...new Set(data.rows.flatMap(r => r.operations.map(o => o.article)))].filter(Boolean).sort()
  const allPeriods = [...new Set(data.rows.flatMap(r => r.operations.map(o => o.period)))].filter(Boolean).sort()
  const toggle = (arr, set, val) => set(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val])

  // ── база для KPI и графиков: фильтры контрагент/статья/период (без «только актуальные») ──
  const allOps = data.rows.flatMap(r => r.operations.map(o => ({ ...o, cp: r.counterparty, cpid: r.counterparty_id })))
  const baseOps = allOps.filter(o =>
    (filterCounterparties.length === 0 || filterCounterparties.includes(o.cp)) &&
    (filterArticles.length === 0 || filterArticles.includes(o.article)) &&
    (filterPeriods.length === 0 || filterPeriods.includes(o.period)))

  const agg = { overdue: { a: 0, c: 0 }, current: { a: 0, c: 0 }, future: { a: 0, c: 0 }, unknown: { a: 0, c: 0 } }
  baseOps.forEach(o => { const b = agg[o.aging_bucket] || agg.unknown; b.a += o.amount; b.c++ })
  const portfolioBase = agg.overdue.a + agg.current.a + agg.future.a
  const total = portfolioBase + agg.unknown.a
  const cpCount = new Set(baseOps.filter(o => o.amount).map(o => o.cpid)).size
  const opCount = baseOps.length
  const pctOf = (a) => (portfolioBase > 0 ? Math.round(a / portfolioBase * 100) : 0)

  // 7 корзин возраста
  const buckets = AGE_BUCKETS.map(b => ({ ...b, amount: 0, count: 0, byCp: {} }))
  baseOps.forEach(o => {
    if (!o.due_date) return
    const x = daysPastDue(o.due_date, data.as_of)
    const bk = buckets.find(b => b.test(x)); if (!bk) return
    bk.amount += o.amount; bk.count++; bk.byCp[o.cp] = (bk.byCp[o.cp] || 0) + o.amount
  })
  buckets.forEach(b => { b.top = Object.entries(b.byCp).sort((x, y) => y[1] - x[1]).slice(0, 3) })
  const ageMax = niceMax(Math.max(1, ...buckets.map(b => b.amount)))

  // структура портфеля (доли)
  const structure = [
    { key: 'future', label: 'План', color: C_PLAN, a: agg.future.a, c: agg.future.c },
    { key: 'current', label: 'Текущая', color: 'var(--dot-current-dz)', a: agg.current.a, c: agg.current.c },
    { key: 'overdue', label: 'Просрочено', color: 'var(--dot-overdue)', a: agg.overdue.a, c: agg.overdue.c },
  ]
  const structTotal = portfolioBase || 1
  const structCells = []
  structure.forEach(s => { const n = Math.round(s.a / structTotal * 48); for (let i = 0; i < n; i++) structCells.push(s.color) })
  while (structCells.length < 48) structCells.push('var(--border-inner)')
  structCells.length = 48

  // ── таблица: строки + фильтр по операциям (вкл. «только актуальные») ──
  const tableRows = data.rows
    .filter(r => filterCounterparties.length === 0 || filterCounterparties.includes(r.counterparty))
    .map(r => {
      const ops = r.operations.filter(o => {
        if (onlyActual && o.aging_bucket !== 'overdue' && o.aging_bucket !== 'current') return false
        if (filterArticles.length > 0 && !filterArticles.includes(o.article)) return false
        if (filterPeriods.length > 0 && !filterPeriods.includes(o.period)) return false
        return true
      })
      if (ops.length === 0) return null
      const amount = ops.reduce((s, o) => s + o.amount, 0)
      const aging = { overdue: 0, current: 0, future: 0, unknown: 0 }
      ops.forEach(o => { aging[o.aging_bucket] += o.amount })
      return { ...r, operations: ops, amount, op_count: ops.length, aging }
    })
    .filter(Boolean)

  const handleSort = (col) => { if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc'); else { setSortCol(col); setSortDir('desc') } }
  const sortedRows = [...tableRows].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol]
    if (typeof av === 'string') av = av.toLowerCase(); if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })
  const totalFiltered = sortedRows.reduce((s, r) => s + r.amount, 0)
  const totalOpsFiltered = sortedRows.reduce((s, r) => s + r.op_count, 0)
  const toggleExpand = (cid) => setExpanded(prev => ({ ...prev, [cid]: !prev[cid] }))
  const hasActiveFilters = filterCounterparties.length || filterArticles.length || filterPeriods.length || !onlyActual

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head>
        <Navbar active="receivables" />
        <ReceivablesMobile
          asOf={data.as_of} onlyActual={onlyActual} setOnlyActual={setOnlyActual} downloadExport={downloadExport}
          kpi={{ total, cpCount, opCount, overdue: agg.overdue, current: agg.current, future: agg.future, pctOf }}
          buckets={buckets} ageMax={ageMax} structure={structure} structCells={structCells} structTotal={structTotal}
          rows={sortedRows} totalFiltered={totalFiltered} rowsCount={data.rows.length}
          expanded={expanded} toggleExpand={toggleExpand}
          notes={notes} setNotes={setNotes} savedNotes={savedNotes} saveNote={saveNote} canEditNote={canEditNote} noteStatus={noteStatus} />
      </div>
    )
  }

  const GRID = 'grid-template-columns: 2fr 128px 100px 168px 66px 1.4fr 1.5fr;'
  const DET_GRID = 'grid-template-columns: 92px 1.3fr 116px 138px 140px 150px 96px 90px 112px;'
  const monoLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
  const selBtn = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '8px 13px', fontFamily: UI, fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head>
        <title>Дебиторка · Финансы | SIMB-AD ERP</title>
      </Head>
      <Navbar active="receivables" />

      <style>{`
        @keyframes rcvRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes rcvGrow { from { transform:scaleY(0) } to { transform:scaleY(1) } }
        .rcv-grid { display:grid; ${GRID} gap:16px; }
        .rcv-det { display:grid; ${DET_GRID} gap:14px; }
        .rcv-row:hover { background:var(--bg-subtle) !important; }
        .rcv-x:hover { border-color:#C7D0E8 !important; color:var(--accent) !important; }
        .rcv-inn:hover { text-decoration:underline; color:var(--accent-hover) !important; }
        @media (prefers-reduced-motion: reduce) { [style*="animation"] { animation:none !important } }
      `}</style>

      <div style={{ padding: 32, maxWidth: 1680, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', ...rise(0) }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)', margin: 0 }}>Дебиторская задолженность</h1>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>на {formatDate(data.as_of)}</span>
          </div>
        </div>

        {/* KPI-карточка */}
        <div style={{ ...card, padding: '0 36px', ...rise(0.07) }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
            {[
              { mk: null, lbl: 'Итого дебиторка', val: total, color: 'var(--text-primary)', sub: <>{cpCount} контрагентов · {opCount} счетов</> },
              { mk: 'var(--dot-overdue)', lbl: 'Просрочено', val: agg.overdue.a, color: T_OVERDUE, badge: `${pctOf(agg.overdue.a)}% портфеля`, sub: <>{agg.overdue.c} операций</> },
              { mk: 'var(--dot-current-dz)', lbl: 'Текущая задолженность', val: agg.current.a, color: T_KPI_CURRENT, sub: <>{pctOf(agg.current.a)}% портфеля · {agg.current.c} операций</> },
              { mk: C_PLAN, lbl: 'План', val: agg.future.a, color: 'var(--accent)', sub: <>{pctOf(agg.future.a)}% портфеля · {agg.future.c} операций</> },
            ].map((k, i) => (
              <div key={i} style={{ padding: i === 0 ? '28px 26px 28px 0' : i === 3 ? '28px 0 28px 26px' : '28px 26px', borderRight: i < 3 ? '1px solid var(--border-inner)' : 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ ...monoLbl, fontSize: 11, letterSpacing: '0.1em', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 7 }}>
                  {k.mk && <span style={{ width: 8, height: 8, borderRadius: 2, background: k.mk }} />}{k.lbl}
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                  <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 42, letterSpacing: '-0.03em', lineHeight: 1, color: k.color, whiteSpace: 'nowrap' }}><CountUp value={k.val} /></span>
                  <span style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-faint)' }}>₽</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {k.badge && <span style={{ background: 'var(--danger-tint)', color: T_OVERDUE, borderRadius: 8, padding: '4px 8px', fontSize: 12, fontWeight: 700 }}>{k.badge}</span>}
                  {k.sub}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ряд: возраст задолженности + структура */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20 }}>

          {/* Возраст задолженности */}
          <div style={{ ...card, padding: '28px 30px 24px', display: 'flex', flexDirection: 'column', ...rise(0.14) }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Возраст задолженности</span>
                <span style={monoLbl}>дни к сроку оплаты · «−» до срока, «+» после</span>
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {[['план', C_PLAN], ['текущая', 'var(--dot-current-dz)'], ['просрочка', 'var(--dot-overdue)']].map(([l, c]) => (
                  <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-muted)' }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}
                  </span>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flex: 1, minHeight: 170 }}>
              {/* ось Y */}
              <div style={{ width: 44, position: 'relative', fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>
                {[1, 0.75, 0.5, 0.25, 0].map((f, i) => (
                  <span key={i} style={{ position: 'absolute', right: 0, top: `calc(${(1 - f) * 100}% - 5px)` }}>{Math.round(ageMax * f / 1e6)}</span>
                ))}
              </div>
              {/* область графика с сеткой */}
              <div style={{ flex: 1, position: 'relative',
                backgroundImage: `repeating-linear-gradient(to top, var(--border-row) 0 1px, transparent 1px 25%)`,
                borderBottom: '1px solid var(--border-card)' }}>
                <div style={{ position: 'absolute', inset: 0, display: 'flex' }}>
                  {buckets.map((b, i) => (
                    <div key={b.key} onMouseEnter={() => setHoverBucket(i)} onMouseLeave={() => setHoverBucket(null)}
                      style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'flex-end', paddingBottom: 0 }}>
                      {hoverBucket === i && (
                        <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1px dashed var(--text-faint)', pointerEvents: 'none' }} />
                      )}
                      <PixelBar value={b.amount} max={ageMax} color={TYPE_COLOR[b.type]} delay={i * 0.05} />
                      {hoverBucket === i && (
                        <div style={{ position: 'absolute', top: 8, zIndex: 5, pointerEvents: 'none',
                          ...(i >= 4 ? { right: 'calc(50% + 12px)' } : { left: 'calc(50% + 12px)' }),
                          background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14,
                          boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 24px rgba(28,36,51,.10)', padding: '12px 14px', minWidth: 190 }}>
                          <div style={{ ...monoLbl }}>{b.label} · {TYPE_RU[b.type]}</div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7, margin: '8px 0 2px' }}>
                            <span style={{ width: 8, height: 8, borderRadius: 2, background: TYPE_COLOR[b.type] }} />
                            <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{fmt(b.amount)} ₽</span>
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{b.count} операций · {pctOf(b.amount)}%</div>
                          {b.top.length > 0 && (
                            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
                              <div style={{ ...monoLbl, marginBottom: 4 }}>Крупнейшие контрагенты</div>
                              {b.top.map(([name, amt]) => (
                                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
                                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }}>{name}</span>
                                  <span style={{ fontFamily: MONO }}>{mln(amt)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {/* подписи корзин */}
            <div style={{ display: 'flex', gap: 8, marginLeft: 52 }}>
              {buckets.map(b => <div key={b.key} style={{ flex: 1, textAlign: 'center', fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', paddingTop: 8 }}>{b.label}</div>)}
            </div>
          </div>

          {/* Структура портфеля */}
          <div style={{ ...card, padding: '28px 26px 22px', display: 'flex', flexDirection: 'column', ...rise(0.21) }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 18 }}>Структура портфеля</div>
            <div style={{ display: 'flex', gap: 2, height: 26, marginBottom: 6 }}>
              {structCells.map((c, i) => <div key={i} style={{ flex: 1, borderRadius: 2, background: c }} />)}
            </div>
            <div style={{ marginTop: 8 }}>
              {structure.map(s => (
                <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 0', borderTop: '1px solid var(--border-row)' }}>
                  <span style={{ width: 10, height: 10, borderRadius: 2, background: s.color }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{s.label}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{s.c} оп</span>
                  <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: s.key === 'overdue' ? T_OVERDUE : 'var(--text-primary)', minWidth: 44, textAlign: 'right' }}>{pctOf(s.a)}%</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Текущая — до 30 дн. после срока оплаты, далее — просрочка. Договорных сроков пока нет: стандарт 60 дн.
            </div>
          </div>
        </div>

        {/* Таблица контрагентов-должников */}
        <div style={{ ...card, padding: '28px 30px 22px', display: 'flex', flexDirection: 'column', gap: 20, ...rise(0.28) }}>
          {/* шапка карточки: заголовок + фильтры */}
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Контрагенты-должники</span>
              <span style={monoLbl}>{sortedRows.length} из {data.rows.length} · по убыванию суммы</span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center' }}>
              <FilterDrop label="Все контрагенты" items={allCounterparties} selected={filterCounterparties} onToggle={v => toggle(filterCounterparties, setFilterCounterparties, v)} onClear={() => setFilterCounterparties([])} />
              <FilterDrop label="Все статьи" items={allArticles} selected={filterArticles} onToggle={v => toggle(filterArticles, setFilterArticles, v)} onClear={() => setFilterArticles([])} />
              <FilterDrop label="Все периоды" items={allPeriods} selected={filterPeriods} fmtItem={formatPeriod} onToggle={v => toggle(filterPeriods, setFilterPeriods, v)} onClear={() => setFilterPeriods([])} />
              {/* тумблер актуальные/все */}
              <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 12, padding: 3 }}>
                {[['Только актуальные', true], ['Все', false]].map(([lbl, val]) => (
                  <button key={lbl} onClick={() => setOnlyActual(val)}
                    style={{ border: 'none', borderRadius: 9, padding: '6px 13px', fontFamily: UI, fontSize: 13, cursor: 'pointer',
                      background: onlyActual === val ? 'var(--accent-tint)' : 'transparent',
                      color: onlyActual === val ? 'var(--accent)' : 'var(--text-secondary)',
                      fontWeight: onlyActual === val ? 700 : 600 }}>{lbl}</button>
                ))}
              </div>
              <button className="rcv-x" onClick={downloadExport} title="Скачать в Excel"
                style={{ width: 38, height: 38, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></svg>
              </button>
              {hasActiveFilters ? (
                <button onClick={() => { setFilterCounterparties([]); setFilterArticles([]); setFilterPeriods([]); setOnlyActual(true) }}
                  style={{ ...selBtn, color: 'var(--text-muted)' }}>Сбросить</button>
              ) : null}
            </div>
          </div>

          {/* шапка колонок */}
          <div>
            <div className="rcv-grid" style={{ paddingBottom: 10, borderBottom: '1px solid var(--border-card)' }}>
              {[['Контрагент', 'counterparty', 'left'], ['ИНН', null, 'left'], ['Отсрочка', 'term_days', 'right'], ['Сумма', 'amount', 'right'], ['Кол-во', 'op_count', 'right'], ['Возраст', null, 'left'], ['Примечание', null, 'left']].map(([lbl, col, al], i) => (
                <div key={i} onClick={() => col && handleSort(col)}
                  style={{ ...monoLbl, textAlign: al, cursor: col ? 'pointer' : 'default', color: sortCol === col ? 'var(--accent)' : 'var(--text-faint)' }}>
                  {lbl}{sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                </div>
              ))}
            </div>

            {/* строки */}
            {sortedRows.map(r => {
              const key = r.counterparty_id
              const isOpen = !!expanded[key]
              const chips = [['overdue', r.aging.overdue], ['current', r.aging.current], ['future', r.aging.future]].filter(([, v]) => v > 0)
              return (
                <div key={key}>
                  <div className="rcv-row rcv-grid" onClick={() => toggleExpand(key)}
                    style={{ alignItems: 'center', padding: '9px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', cursor: 'pointer', background: isOpen ? 'var(--bg-subtle)' : 'transparent' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{isOpen ? '▾' : '▸'}</span>
                      <span style={{ fontSize: 15.5, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.counterparty}</span>
                    </div>
                    <div onClick={e => e.stopPropagation()}>
                      {r.inn ? <a className="rcv-inn" href={`/directory/counterparties/${key}`} target="_blank" rel="noopener noreferrer"
                        style={{ color: 'var(--accent)', textDecoration: 'none', fontFamily: MONO, fontSize: 14 }} title="Карточка контрагента">{r.inn}</a>
                        : <span style={{ color: 'var(--text-muted)', fontFamily: MONO, fontSize: 14 }}>—</span>}
                    </div>
                    <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 14, color: 'var(--text-secondary)' }}>{r.term_days} дн.</div>
                    <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 15.5, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(r.amount)} ₽</div>
                    <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 14, color: 'var(--text-secondary)' }}>{r.op_count}</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {chips.map(([b, v]) => (
                        <span key={b} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, borderRadius: 8, padding: '3px 8px', fontFamily: MONO, fontSize: 13, fontWeight: 700,
                          background: CHIP[b].bg, color: CHIP[b].fg }}>
                          <span style={{ width: 6, height: 6, borderRadius: 2, background: CHIP[b].dot }} />
                          {fmt(v)} ₽
                        </span>
                      ))}
                    </div>
                    <div onClick={e => e.stopPropagation()}>
                      {canEditNote ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <input value={notes[key] ?? ''} onChange={e => setNotes(prev => ({ ...prev, [key]: e.target.value }))}
                            onBlur={e => { const val = e.target.value; if (val !== (savedNotes[key] ?? '')) saveNote(key, val) }}
                            onKeyDown={e => { if (e.key === 'Enter') e.target.blur() }} placeholder="—"
                            style={{ width: '100%', padding: '4px 7px', borderRadius: 8, border: '1px solid transparent', background: 'transparent', fontSize: 14, color: 'var(--text-secondary)', fontFamily: UI, outline: 'none' }}
                            onFocus={e => { e.target.style.border = '1px solid var(--border-card)'; e.target.style.background = 'var(--bg-card)' }}
                            onBlurCapture={e => { e.target.style.border = '1px solid transparent'; e.target.style.background = 'transparent' }} />
                          {noteStatus[key] === 'saving' && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>…</span>}
                          {noteStatus[key] === 'saved' && <span style={{ fontSize: 12, color: 'var(--income)' }}>✓</span>}
                        </div>
                      ) : <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>{r.note || '—'}</span>}
                    </div>
                  </div>

                  {isOpen && (
                    <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '2px -8px 8px', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8, animation: 'rcvRise .25s cubic-bezier(0.22,1,0.36,1) both' }}>
                      <div className="rcv-det" style={{ ...monoLbl, paddingBottom: 6 }}>
                        {['Дата', 'Статья', 'Период', 'Срок оплаты', 'Возраст', 'Сумма', '№ ДС', '№ счёта', 'Дата счёта'].map((h, i) => (
                          <div key={i} style={{ textAlign: i === 5 ? 'right' : 'left' }}>{h}</div>
                        ))}
                      </div>
                      {r.operations.map(op => {
                        const ov = op.aging_bucket === 'overdue'
                        return (
                          <div key={op.id} className="rcv-det" style={{ padding: '6px 0', borderTop: '1px solid var(--border-inner)', fontSize: 14, color: 'var(--text-secondary)', alignItems: 'center' }}>
                            <div style={{ fontFamily: MONO }}>{formatDate(op.date)}</div>
                            <div style={{ fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{op.article}</div>
                            <div style={{ fontFamily: MONO }}>{formatPeriod(op.period)}</div>
                            <div style={{ fontFamily: MONO }}>{formatDate(op.due_date)}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: ov ? T_OVERDUE : op.aging_bucket === 'current' ? T_CURRENT : 'var(--text-muted)' }}>
                              <span style={{ width: 6, height: 6, borderRadius: 2, background: ov ? 'var(--dot-overdue)' : op.aging_bucket === 'current' ? 'var(--dot-current-dz)' : C_PLAN }} />
                              {ov ? 'Просрочка' : op.aging_bucket === 'current' ? 'Текущая' : 'План'}
                            </div>
                            <div style={{ textAlign: 'right', fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(op.amount)} ₽</div>
                            <div style={{ fontFamily: MONO }}>{op.ds_num || '—'}</div>
                            <div style={{ fontFamily: MONO }}>{op.invoice || '—'}</div>
                            <div style={{ fontFamily: MONO }}>{formatDate(op.invoice_date)}</div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}

            {sortedRows.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет задолженности по выбранным фильтрам</div>
            )}

            {/* Итого */}
            {sortedRows.length > 0 && (
              <div className="rcv-grid" style={{ padding: '14px 0 0', alignItems: 'center' }}>
                <div style={{ fontSize: 15.5, fontWeight: 700, color: 'var(--text-primary)' }}>Итого ({sortedRows.length} из {data.rows.length})</div>
                <div /><div /><div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(totalFiltered)} ₽</div>
                <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-secondary)' }}>{totalOpsFiltered}</div>
                <div /><div />
              </div>
            )}
          </div>

          {/* подвал */}
          <div style={{ paddingTop: 14, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 18, flexWrap: 'wrap' }}>
            {Math.round(agg.unknown.a) === 0 ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: 'var(--income)', fontWeight: 700 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--income)' }} />суммы по срокам сходятся с итогом
              </span>
            ) : (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: T_OVERDUE, fontWeight: 700 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--dot-overdue)' }} />{agg.unknown.c} операций без срока оплаты ({mln(agg.unknown.a)} млн) — вне корзин
              </span>
            )}
            <span>{onlyActual ? 'показаны только актуальные счета' : 'показаны все счета'}</span>
            <span style={{ marginLeft: 'auto' }}>суммы без НДС, в рублях</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// Селект-фильтр в шапке таблицы (кнопка + выпадашка с поиском и мультивыбором)
function FilterDrop({ label, items, selected, onToggle, onClear, fmtItem }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  const f = fmtItem || (x => x)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const shown = items.filter(i => f(i).toLowerCase().includes(q.toLowerCase()))
  const active = selected.length > 0
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ background: active ? 'var(--accent-tint)' : 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '8px 13px', fontFamily: UI, fontSize: 13, fontWeight: 600, color: active ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
        {active ? `${label.replace('Все ', '')}: ${selected.length}` : label} ▾
      </button>
      {open && (
        <div style={{ position: 'absolute', top: '110%', right: 0, marginTop: 4, zIndex: 300, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', minWidth: 230, maxHeight: 300, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 8 }}>
            <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Поиск…"
              style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 13, outline: 'none', fontFamily: UI }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {shown.map(item => {
              const on = selected.includes(item)
              return (
                <div key={item} onClick={() => onToggle(item)}
                  style={{ padding: '4px 12px', cursor: 'pointer', fontSize: 10.5, display: 'flex', alignItems: 'center', gap: 8, background: on ? 'var(--accent-tint)' : 'transparent' }}>
                  <span style={{ width: 14, height: 14, borderRadius: 3, border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`, background: on ? 'var(--accent)' : 'transparent', color: '#fff', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{on ? '✓' : ''}</span>
                  {f(item)}
                </div>
              )
            })}
            {!shown.length && <div style={{ padding: 10, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          </div>
          {active && <div onClick={() => { onClear(); setQ('') }} style={{ padding: '8px 12px', borderTop: '1px solid var(--border-card)', fontSize: 13, color: 'var(--dot-overdue)', cursor: 'pointer' }}>Сбросить выбор</div>}
        </div>
      )}
    </div>
  )
}
