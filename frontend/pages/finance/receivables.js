import Navbar, { can } from '@/components/Navbar'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const ReceivablesMobile = dynamic(() => import('@/components/mobile/ReceivablesMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { makeApi as api } from '@/lib/http'
import { getPermissions } from '@/lib/auth'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fileStamp } from '@/lib/dates'
import useLatest from '@/lib/useLatest'
import { errText, isAuth } from '@/lib/loadError'
import { LoadError, LoadErrorScreen } from '@/components/salesTableKit'
import { downloadFile } from '@/lib/download'
import DsViewer from '@/components/onecDesk/DsViewer'
import InvoiceViewer from '@/components/onecDesk/InvoiceViewer'
import ReceivablesNavy from '@/components/receivables/ReceivablesNavy'

const UI = "'Manrope', system-ui, sans-serif"



// getPermissions + can — из lib/auth (единый источник, admin-bypass)

const C_PLAN = 'var(--dot-expense)'         // = --dot-expense

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
const daysPastDue = (dueDate, asOf) => Math.round((new Date(asOf) - new Date(dueDate)) / 86400000)



export default function Receivables() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  // отбор по контрагенту/статье/периоду был в старой настольной вёрстке; мобильная и выгрузка его не задают
  const filterCounterparties = [], filterArticles = [], filterPeriods = []
  const [onlyActual, setOnlyActual] = useState(true)
  const sortCol = 'amount', sortDir = 'desc'   // мобильная — по убыванию суммы
  const [expanded, setExpanded] = useState({})
  const [notes, setNotes] = useState({})
  const [savedNotes, setSavedNotes] = useState({})
  const [noteStatus, setNoteStatus] = useState({})
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
  useRefreshOnReturn(() => load(localStorage.getItem('token'), { quiet: true }))

  useEffect(() => {
    if (data && Array.isArray(data.rows)) {
      const initial = Object.fromEntries(data.rows.map(r => [r.counterparty_id, r.note || '']))
      setNotes(initial); setSavedNotes(initial)
    }
  }, [data])

  // Сбой — это сбой, а не «Нет данных» (аудит 23.09.2026, 6.M5): 500 или обрыв раньше
  // показывали пустой экран с «Нет данных», и человек видел отсутствие долгов там, где
  // сервер просто не ответил. Фоновая перечитка — тихая (6.M6), устаревший ответ не
  // пишется поверх нового (lib/useLatest).
  const [err, setErr] = useState('')
  const [dsView, setDsView] = useState(null)   // ДС/ПР окном просмотра
  const [invView, setInvView] = useState(null) // счёт окном просмотра
  const latest = useLatest()
  const load = async (token, { quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    setDenied(false); setErr('')
    const fresh = latest()
    try {
      const res = await api(token).get('/reports/receivables')
      if (fresh()) setData(res.data)
    } catch (e) {
      if (!fresh()) return
      if (e.response?.status === 401) router.push('/login')
      else if (e.response?.status === 403) setDenied(true)
      else setErr(errText(e))
    } finally { if (fresh()) setLoading(false) }
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
      // Введённый текст НЕ откатываем: раньше сбой молча стирал его, и человек думал,
      // что сохранилось (аудит, 6.M5). Текст остаётся, поле помечено, причина названа.
      setNoteStatus(prev => ({ ...prev, [cid]: 'error' }))
      if (!isAuth(e)) setErr('Примечание не сохранено: ' + errText(e))
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
      a.download = `debitorka_${fileStamp()}.xlsx`
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url)
    } catch (e) {
      // Выгрузка молчала при сбое — человек ждал файл, которого не будет (аудит, 6.M5).
      if (!isAuth(e)) setErr('Выгрузка не удалась: ' + errText(e))
    }
  }

  if (loading) return <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Загрузка дебиторской задолженности…</div></div>
  if (denied) return <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Нет доступа к разделу «Дебиторка».</div></div>
  if ((!data || !Array.isArray(data.rows)) && err) return (
    <LoadErrorScreen title="Дебиторка не загрузилась" text={err}
      nav={<><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /></>}
      onRetry={() => load(localStorage.getItem('token'))} />
  )
  if (!data || !Array.isArray(data.rows)) return <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed' }}><Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head><Navbar active="receivables" /><div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>Нет данных.</div></div>

  const canEditNote = can(getPermissions(), 'receivables', 'edit')


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

  const sortedRows = [...tableRows].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol]
    if (typeof av === 'string') av = av.toLowerCase(); if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })
  const totalFiltered = sortedRows.reduce((s, r) => s + r.amount, 0)
  const toggleExpand = (cid) => setExpanded(prev => ({ ...prev, [cid]: !prev[cid] }))

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed', fontFamily: UI }}>
        <Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head>
        <Navbar active="receivables" />
      {/* Цифры ниже — от прошлой удачной загрузки; полоса говорит, что обновление или
          действие не прошло (аудит, 6.M5). */}
      {!!err && <div style={{ padding: '12px 24px 0' }}>
        <LoadError text={err} onRetry={() => { setErr(''); load(localStorage.getItem('token')) }} /></div>}
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

  // Настольная версия — NAVY по хендоффу 19.11.2026 (components/receivables). Примечание сохраняется сразу, как и раньше.
  const saveNoteNavy = (cid, value) => { setNotes(prev => ({ ...prev, [cid]: value })); saveNote(cid, value) }
  return (
    <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed', fontFamily: UI, color: 'var(--text-primary)' }}>
      <Head><title>Дебиторка · Финансы | SIMB-AD ERP</title></Head>
      <Navbar active="receivables" />
      {dsView && <DsViewer annexId={dsView.annexId} title={dsView.title} onClose={() => setDsView(null)} onError={m => setErr(m)} />}
      {invView && <InvoiceViewer kitId={invView.kitId} pdfId={invView.pdfId} title={invView.title} onClose={() => setInvView(null)} onError={m => setErr(m)} />}
      {!!err && <div style={{ maxWidth: 1880, margin: '0 auto', padding: '12px 26px 0' }}>
        <LoadError text={err} onRetry={() => { setErr(''); load(localStorage.getItem('token')) }} /></div>}
      <ReceivablesNavy data={data} notes={notes} saveNote={saveNoteNavy} noteStatus={noteStatus} canEditNote={canEditNote} onExport={downloadExport}
        onDs={(d, title) => (d.annex_external
          ? downloadFile(`/annexes/${d.annex_id}/external-file`, null, m => setErr(m))
          : setDsView({ annexId: d.annex_id, title: title || 'ДС' }))}
        onInv={(d, no) => setInvView({ kitId: d.kit_id, pdfId: d.inv_pdf_id, title: `Счёт № ${no}` })} />
    </div>
  )
}
