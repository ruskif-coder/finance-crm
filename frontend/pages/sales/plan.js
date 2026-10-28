// «План продаж» (владелец 24.10.2026, docs/ПЛАН_план_продаж.md, макет docs/план продаж.zip): цели по месяцам — общая,
// по услугам, по продажникам — и их выполнение из сделок. Режим «Выполнение» — контроль, режим «Цели» — ввод цифр.
// Расчёт выполнения — сервер (`app/sales/plan.py`), свёртка и формат — lib/salesPlan.mjs.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import useLatest from '@/lib/useLatest'
import Head from 'next/head'
import api, { auth } from '@/lib/api'
import Navbar, { can as canDo } from '@/components/Navbar'
import { MONO, UI, Seg, Z, LoadErrorScreen, IconBtn, XlsxIcon } from '@/components/salesTableKit'
import PlanGrid, { editKey, editable, layout } from '@/components/salesPlan/PlanGrid'
import CellPanel from '@/components/salesPlan/CellPanel'
import ImportPreview from '@/components/salesPlan/ImportPreview'
import PlanAnalytics from '@/components/salesPlan/PlanAnalytics'
import { downloadFile } from '@/lib/download'
import { copyPrev, currentMonth, fmtK, fmtRub, fmtSigned, parseRub, pct, spreadBySeason, spreadEven, sumCells, toDate, typeRub } from '@/lib/salesPlan.mjs'
import { todayMsk } from '@/lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const cap = { fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const box = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16 }
const btn = (primary, off) => ({ height: 34, padding: '0 14px', borderRadius: 10, fontFamily: UI, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap',
  cursor: off ? 'default' : 'pointer', opacity: off ? 0.5 : 1, border: primary ? 'none' : '1px solid var(--border-card)',
  background: primary ? 'var(--accent)' : 'var(--bg-card)', color: primary ? 'var(--on-accent)' : 'var(--text-secondary)' })
const METRICS = [['done', 'выполнено'], ['pct', '% цели'], ['forecast', 'прогноз'], ['gap', 'разрыв'], ['goal', 'цель']]
const HINT = { done: 'выполнено: факт + в работе (со «Сборки»), рядом — % к цели; будущие месяцы — прогноз курсивом',
  pct: 'выполнено ÷ цель; будущие месяцы — прогноз ÷ цель', forecast: 'прогноз: выполнено + планируемые (зелёный 100 %, оранжевый 50 %)',
  gap: 'прогноз − цель: минус — не хватает', goal: 'цель месяца' }
// Правки — полные рубли («10 000 000»), показ — в тыс. ₽ как везде (владелец 24.10.2026)
const parseK = parseRub

function Kpis({ total, cur, year }) {
  const y = sumCells(total.months), td = toDate(total, cur), gap = y.goal == null ? null : y.forecast - y.goal
  const wk = y.forecast_week_ago == null ? null : y.forecast - y.forecast_week_ago
  const tone = (p) => (p == null ? 'var(--text-primary)' : p >= 100 ? 'var(--income-fg)' : p >= 80 ? 'var(--warning-fg)' : 'var(--danger-fg)')
  const items = [
    [`цель ${year}`, fmtK(y.goal), 'тыс. ₽ без НДС', 'var(--text-primary)'],
    ['к сегодняшнему дню', td.p == null ? '—' : `${td.p} %`, td.goal == null ? `выполнено ${fmtK(td.done)} · цели нет` : `выполнено ${fmtK(td.done)} из ${fmtK(td.goal)}`, tone(td.p)],
    ['выполнено за год', fmtK(y.done), `${y.goal == null ? 'цель не задана' : `${pct(y.done, y.goal)} % цели`} · факт ${fmtK(y.fact)} + в работе ${fmtK(y.work)}`, 'var(--income-fg)'],
    ['прогноз на год', fmtK(y.forecast), (wk == null ? '' : `${wk >= 0 ? '▲' : '▼'} ${fmtSigned(wk)} за 7 дней · `) + (y.goal == null ? 'цель не задана' : `${pct(y.forecast, y.goal)} % цели`), 'var(--accent-fg)'],
    ['разрыв к цели', gap == null ? '—' : fmtSigned(gap), gap == null ? 'цель года не задана' : gap < 0 ? 'не хватает до цели года' : 'прогноз выше цели', gap == null ? 'var(--text-muted)' : gap < 0 ? 'var(--danger-fg)' : 'var(--income-fg)'],
  ]
  return (
    <div style={{ ...box, display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))' }}>
      {items.map(([l, v, s, c], i) => (
        <div key={l} style={{ padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: 4, borderLeft: i ? '1px solid var(--border-inner)' : 'none' }}>
          <span style={cap}>{l}</span>
          <b style={{ fontFamily: MONO, fontSize: 22, color: c }}>{v}</b>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{s}</span>
        </div>
      ))}
    </div>
  )
}

export default function SalesPlanPage() {
  const today = todayMsk()
  const [year, setYear] = useState(Number(today.slice(0, 4)))
  const [data, setData] = useState(null)
  const [prev, setPrev] = useState(null)
  const [err, setErr] = useState('')
  const [mode, setMode] = useState('run')
  const [grain, setGrain] = useState('m')
  const [metric, setMetric] = useState('done')
  const [scope, setScope] = useState('all')
  const [collapsed, setCollapsed] = useState({})
  const [edits, setEdits] = useState({})
  const [open, setOpen] = useState(null)
  const [spread, setSpread] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [mayEdit, setMayEdit] = useState(false)
  const [imp, setImp] = useState(null)        // предпросмотр загрузки из Excel
  const [weeks, setWeeks] = useState(null)    // прогноз года по неделям — из ночных снимков
  const [anaOpen, setAnaOpen] = useState(true)
  const fileRef = useRef(null)
  useEffect(() => { setMayEdit(canDo('sales_plan', 'edit')) }, [])
  // Поповер «разложить год» закрывается кликом мимо — как остальные поповеры (data-pop-root)
  useEffect(() => {
    if (!spread) return
    const close = (e) => { if (!e.target.closest('[data-pop-root]')) setSpread(null) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [spread])

  const latest = useLatest()
  const latestPrev = useLatest()
  const load = useCallback(() => {
    const fresh = latest()     // пропускаем ответ на прошлый выбор (ревью 27.10.2026): быстро сменил год — старый ответ приходил последним
    api.get('/sales-plan', { ...auth(), params: { year } }).then(r => { if (fresh()) { setData(r.data); setErr('') } })
      .catch(e => { if (fresh()) setErr(e.response?.data?.detail || 'Не удалось загрузить план продаж') })
  }, [year, latest])
  useEffect(() => { setData(null); setEdits({}); load() }, [load])
  useEffect(() => {
    setWeeks(null)
    api.get('/sales-plan/weeks', { ...auth(), params: { year } }).then(r => setWeeks(r.data.weeks))
      .catch(e => { setWeeks([]); setMsg(e.response?.data?.detail || 'Не удалось загрузить прогноз по неделям') })
  }, [year])
  useRefreshOnReturn(load, { enabled: !Object.keys(edits).length })
  // Прошлый год — для «по сезонности» и «как в прошлом году»: только в режиме «Цели»
  useEffect(() => {
    setPrev(null)              // прошлый год СМЕНИЛСЯ: «+10 %» и сезонность не должны взять цели года до переключения
    if (mode !== 'goals') return
    const fresh = latestPrev()
    api.get('/sales-plan', { ...auth(), params: { year: year - 1 } }).then(r => { if (fresh()) setPrev(r.data) })
      .catch(e => { if (fresh()) { setPrev(null); setMsg(e.response?.data?.detail || `Не удалось загрузить ${year - 1} год — разложение по прошлому году недоступно`) } })
  }, [mode, year, latestPrev])

  const canEdit = mayEdit && !!data?.can_edit
  const cur = currentMonth(year, today)
  const rows = useMemo(() => data?.rows || [], [data])
  const prevOf = useCallback((row) => prev?.rows?.find(r => r.scope === row.scope && r.key_id === row.key_id), [prev])
  const goalOf = useCallback((row, m) => {
    const k = editKey(row, m)
    return k in edits ? parseK(edits[k]) : row.months[m].goal
  }, [edits])

  // Сверка разрезов с общей целью — по месяцам и за год (предупреждение, не запрет)
  const checks = useMemo(() => {
    const { total, reps, groups } = layout(rows)
    if (!total) return {}
    const sumGoals = (list, m) => list.filter(editable).reduce((a, r) => a + (goalOf(r, m) || 0), 0)
    const make = (title, list) => {
      const diffs = Array.from({ length: 12 }, (_, m) => sumGoals(list, m) - (goalOf(total, m) || 0))
      const yearDiff = diffs.reduce((a, b) => a + b, 0)
      const note = Math.abs(yearDiff) < 1 ? <span style={{ color: 'var(--income-fg)' }}>цели сходятся с общей</span>
        : <span style={{ color: 'var(--warning-fg)', fontWeight: 600 }}>цели в сумме {yearDiff > 0 ? 'больше' : 'меньше'} общей на {fmtK(Math.abs(yearDiff))}</span>
      const row = (
        <tr key={`chk-${title}`}>
          <td style={{ position: 'sticky', left: 0, background: 'var(--bg-subtle)', padding: '8px 12px', fontSize: 11.5, color: 'var(--text-secondary)',
            borderBottom: '1px solid var(--border-inner)' }}>{title} против общей цели</td>
          {(grain === 'm' ? diffs.map((d, m) => [m, d]) : [0, 1, 2, 3].map(q => [q, diffs.slice(q * 3, q * 3 + 3).reduce((a, b) => a + b, 0)])).map(([i, d]) => (
            <td key={i} style={{ background: 'var(--bg-subtle)', textAlign: 'right', padding: '0 10px', fontFamily: MONO, fontSize: 11.5,
              borderBottom: '1px solid var(--border-inner)', color: Math.abs(d) < 1 ? 'var(--income-fg)' : 'var(--warning-fg)' }}>{Math.abs(d) < 1 ? '=' : fmtSigned(d)}</td>))}
          <td style={{ background: 'var(--bg-subtle)', textAlign: 'right', padding: '0 10px', fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
            borderBottom: '1px solid var(--border-inner)', borderLeft: '2px solid var(--border-card)' }}>{Math.abs(yearDiff) < 1 ? '=' : fmtSigned(yearDiff)}</td>
        </tr>
      )
      return { note, row }
    }
    const r = make('Продажники', reps), s = make('Услуги', groups.flatMap(g => g.rows))
    return { repsNote: r.note, reps: r.row, svcNote: s.note, svc: s.row }
  }, [rows, goalOf, grain])

  const setRowGoals = (row, values) => setEdits(e => {
    const n = { ...e }
    values.forEach((v, m) => { n[editKey(row, m)] = fmtRub(v) })
    return n
  })
  const copyAll = () => rows.filter(editable).forEach(r => { const p = prevOf(r); if (p) setRowGoals(r, copyPrev(p.months.map(c => c.goal), 10)) })
  const changes = Object.entries(edits).filter(([k, v]) => {
    const [sc, key, m] = k.split('|'); const r = rows.find(x => x.scope === sc && String(x.key_id) === key)
    return r && parseK(v) !== r.months[Number(m)].goal
  })
  const save = async () => {
    setBusy(true); setMsg('')
    try {
      const items = changes.map(([k, v]) => { const [sc, key, m] = k.split('|'); return { month: Number(m) + 1, scope: sc, key_id: Number(key) || null, amount: parseK(v) } })
      if (items.some(i => i.amount != null && (Number.isNaN(i.amount) || i.amount < 0))) throw new Error('Цель — число в рублях, не меньше нуля')
      const r = await api.put('/sales-plan/targets', { year, items }, auth())
      setData(r.data); setEdits({}); setMsg(`сохранено: ${r.data.changed}`)
    } catch (e) { setMsg(e.response?.data?.detail || e.message || 'Не удалось сохранить') }
    setBusy(false)
  }

  // Excel: выгрузка — шаблон целей + лист выполнения; загрузка — сначала «было → станет», запись — кнопкой в окне
  const exportXlsx = () => { setMsg(''); downloadFile(`/sales-plan/export.xlsx?year=${year}`, `План продаж ${year}.xlsx`, setMsg) }
  const pickFile = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setMsg('')
    const form = new FormData()
    form.append('file', f)
    try {
      const r = await api.post('/sales-plan/import', form, { ...auth(), params: { year }, headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      setImp(r.data)
    } catch (e2) { setMsg(e2.response?.data?.detail || 'Не удалось прочитать файл') }
  }
  const applyImport = async () => {
    setBusy(true)
    try {
      const items = imp.changes.map(c => ({ month: c.month, scope: c.scope, key_id: c.key_id || null, amount: c.now }))
      const r = await api.put('/sales-plan/targets', { year, items }, auth())
      setData(r.data); setEdits({}); setImp(null); setMsg(`загружено из Excel: ${r.data.changed}`)
    } catch (e) { setMsg(e.response?.data?.detail || 'Не удалось сохранить') }
    setBusy(false)
  }

  if (err && !data) return <LoadErrorScreen title="План продаж" text={err} onRetry={load} />
  const total = rows.find(r => r.scope === 'общий')
  return (
    <>
      <Head><title>План продаж · Продажи | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1760, margin: '0 auto', padding: '18px 24px 40px', fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ ...box, display: 'flex', alignItems: 'center', gap: 12, padding: '14px 20px', flexWrap: 'wrap' }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-.02em', margin: '0 6px 0 0' }}>План продаж</h1>
          <Seg value={mode} opts={[['run', 'Выполнение'], ['goals', 'Цели']]} onPick={setMode} />
          <Seg value={year} opts={[year - 1, year, year + 1].map(y => [y, String(y)])} onPick={setYear} />
          <Seg value={grain} opts={[['m', 'Месяцы'], ['q', 'Кварталы']]} onPick={setGrain} />
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            {!!msg && <span style={{ fontSize: 12, color: /^(сохранено|загружено)/.test(msg) ? 'var(--income-fg)' : 'var(--danger-fg)' }}>{msg}</span>}
            <IconBtn title={`Выгрузить в Excel: отчёт о выполнении и цели ${year} для правки`} onClick={exportXlsx}><XlsxIcon dir="down" /></IconBtn>
            {mode === 'goals' && canEdit && <>
              <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={pickFile} />
              <IconBtn title="Загрузить цели из Excel — файла, выгруженного соседней кнопкой; сначала покажется, что изменится"
                onClick={() => fileRef.current?.click()}><XlsxIcon dir="up" /></IconBtn>
              <button type="button" style={btn(false, !prev)} disabled={!prev} onClick={copyAll}
                title={prev ? `Цели ${year - 1} с прибавкой 10 % — в несохранённые правки` : 'загружаю прошлый год…'}>Скопировать {year - 1} +10 %</button>
              <button type="button" style={btn(true, busy || !changes.length)} disabled={busy || !changes.length} onClick={save}>
                {busy ? 'Сохраняю…' : `Сохранить${changes.length ? ` (${changes.length})` : ''}`}</button>
            </>}
            {mode === 'goals' && !canEdit && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>цели правит руководитель продаж</span>}
          </span>
        </div>

        {!data && <div style={{ ...box, padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Считаю план…</div>}
        {!!total && <Kpis total={total} cur={cur} year={year} />}
        {!!total && (
          <PlanAnalytics open={anaOpen} onToggle={() => setAnaOpen(o => !o)} mode={mode} rows={rows} scope={scope} cur={cur} year={year}
            weeks={weeks} goalsOfTotal={total.months.map((_, m) => goalOf(total, m))} prevTotal={prevOf(total)} />
        )}
        {!!total && (
          <div style={box}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border-inner)', flexWrap: 'wrap' }}>
              {mode === 'run' ? <>
                <span style={cap}>Показывать</span><Seg value={metric} opts={METRICS} onPick={setMetric} />
                <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{HINT[metric]}</span>
              </> : <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                вводятся полные рубли без НДС («10 000 000»), показ — в тыс. ₽ · по месяцам, год и кварталы считаются · пусто — цель не задана · ⇶ — разложить год</span>}
              {!data.own && <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                <span style={cap}>Разрез</span><Seg value={scope} opts={[['all', 'все'], ['rep', 'продажники'], ['svc', 'услуги']]} onPick={setScope} />
              </span>}
            </div>
            <div style={{ overflow: 'auto', maxHeight: '66vh' }}>
              <PlanGrid rows={rows} mode={mode} grain={grain} metric={metric} cur={cur} scope={scope} year={year}
                collapsed={collapsed} onToggle={id => setCollapsed(c => ({ ...c, [id]: !c[id] }))}
                onCell={(row, b) => setOpen({ row, b })} edits={edits} onEdit={(k, v) => setEdits(e => ({ ...e, [k]: typeRub(v) }))}
                canEdit={canEdit} onSpread={(row, rect) => setSpread({ row, rect, total: '' })} checkRows={checks} />
            </div>
            {mode === 'run' && (
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', padding: '10px 16px', fontSize: 11.5, color: 'var(--text-secondary)', borderTop: '1px solid var(--border-inner)' }}>
                {[['var(--danger-tint)', '< 80 %'], ['var(--warning-tint)', '80–99 %'], ['var(--income-tint)', '≥ 100 %'], ['var(--income-border)', '≥ 110 %']].map(([c, l]) => (
                  <span key={l}><i style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 3, background: c, marginRight: 5, verticalAlign: -2 }} />{l}</span>))}
                <span>прошлые и текущий месяц — выполнено и % к цели; будущие — прогноз курсивом</span>
                <span style={{ marginLeft: 'auto' }}>тыс. ₽ без НДС · клик по ячейке — разбор и сделки</span>
              </div>
            )}
          </div>
        )}
      </div>

      {!!imp && <ImportPreview data={imp} busy={busy} onApply={applyImport} onClose={() => setImp(null)} />}
      {!!open && <CellPanel year={year} row={open.row} b={open.b} onClose={() => setOpen(null)} />}
      {!!spread && (
        <div style={{ position: 'fixed', left: Math.min(spread.rect.left, window.innerWidth - 300), top: spread.rect.bottom + 6, zIndex: Z.dropdown,
          background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-modal)', padding: 10, width: 280 }}
          data-pop-root>
          <div style={{ ...cap, marginBottom: 8 }}>разложить год · {spread.row.name}</div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginBottom: 8 }}>сумма за год, ₽
            <input autoFocus value={spread.total} placeholder="120 000 000" onChange={e => setSpread(s => ({ ...s, total: typeRub(e.target.value) }))}
              style={{ width: 130, height: 28, textAlign: 'right', fontFamily: MONO, border: '1px solid var(--border-card)', borderRadius: 7, padding: '0 7px' }} /></label>
          {[['Поровну по месяцам', () => spreadEven(parseK(spread.total))],
            [`По сезонности ${year - 1}`, () => spreadBySeason(parseK(spread.total), prevOf(spread.row)?.months.map(c => c.done))],
            [`Как в ${year - 1} +10 %`, () => copyPrev(prevOf(spread.row)?.months.map(c => c.goal), 10)]].map(([l, f], i) => {
            const off = i < 2 ? !parseK(spread.total) : !prevOf(spread.row)
            return <button key={l} type="button" disabled={off} onClick={() => { setRowGoals(spread.row, f()); setSpread(null) }}
              style={{ display: 'block', width: '100%', textAlign: 'left', border: 0, background: 'transparent', padding: '7px 8px', borderRadius: 8,
                fontFamily: UI, fontSize: 12.5, cursor: off ? 'default' : 'pointer', color: off ? 'var(--text-faint)' : 'var(--text-primary)' }}>{l}</button>
          })}
          <button type="button" onClick={() => setSpread(null)} style={{ ...btn(false), height: 28, marginTop: 4 }}>Отмена</button>
        </div>
      )}
    </>
  )
}
