// «Разбор РК» (трафик, владелец 11.10.2026, макет «Разбор РК»): одна кампания, данные в мелком зерне с
// сервера (`/api/rk-analysis/{код}`), всё остальное считает страница — выключение площадки пересчитывает
// план, факт, прогноз, Weborama, расход, выводы и аналитику мгновенно. Расчёты — lib/rkAnalysis*.mjs (с тестами).
// Право — дашборда трафика; деньги видны по нему же. Только десктоп.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { MONO, UI, Seg } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { indexData, kpis, sumOf, insights as buildInsights, elapsedDays, planTotal } from '@/lib/rkAnalysis.mjs'
import { SLICES, METRICS, SOURCES, PERIODS, COMPARES, periodDays, timeRows, tableModel, metricValue } from '@/lib/rkAnalysisSlices.mjs'
import { downloadName } from '@/lib/salesFormat'
import RkHead from '@/components/rk/RkHead'
import RkPlacements from '@/components/rk/RkPlacements'
import { TimeChart, RankChart } from '@/components/rk/RkChart'
import RkTable, { cellText } from '@/components/rk/RkTable'
import RkInsights, { cmpGroups } from '@/components/rk/RkInsights'
import RkAnalytics from '@/components/rk/RkAnalytics'
import { box, cap, title14, dm } from '@/components/rk/rkUi'

const SL_NAME = { day: 'по дням', week: 'по неделям', placement: 'по площадкам', creative: 'по креативам', cxp: 'креатив × площадка' }
const MNAME = { shows: 'показы', clicks: 'клики', ctr: 'CTR', offered: 'предложено сетью', plan: '% плана', spend: 'расход, ₽', cpm: 'CPM, ₽' }

export default function RkAnalysisPage() {
  const router = useRouter()
  const code = String(router.query.code || '')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [prevId, setPrevId] = useState(null)
  const [on, setOn] = useState({})
  const [st, setSt] = useState({ slice: 'day', metric: 'shows', source: 'our', period: 'all', cmp: 'plan' })
  const [range, setRange] = useState(null)
  const [pick, setPick] = useState(null)
  const [tech, setTech] = useState(false)
  const [sort, setSort] = useState(null)
  const [drill, setDrill] = useState(null)
  const [focus, setFocus] = useState(null)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(async (pid) => {
    if (!code) return
    try {
      const r = await api.get(`/rk-analysis/${encodeURIComponent(code)}`, { ...auth(), params: pid ? { prev_id: pid } : {} })
      setData(r.data)
      setOn(o => (Object.keys(o).length ? o : Object.fromEntries(r.data.placements.map(p => [p.id, true]))))
      setErr('')
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить разбор РК') }
  }, [code])
  useEffect(() => { load(prevId) }, [load, prevId])
  const reload = useCallback(() => load(prevId), [load, prevId])
  useRefreshOnReturn(reload)

  // Esc — выйти из проваливания (слушатель снимается при уходе со страницы).
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') { setDrill(null); setSort(null); setFocus(null) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const ix = useMemo(() => (data ? indexData(data) : null), [data])
  const set = (k, v) => { setSt(s => ({ ...s, [k]: v })); setDrill(null); setSort(null); setFocus(null); setPick(null) }

  if (err) return <Shell><div style={{ ...box, padding: 20, color: 'var(--danger-fg)' }}>{err}</div></Shell>
  if (!ix) return <Shell><div style={{ ...box, padding: 40, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Загружаю факт по площадкам…</div></Shell>

  const all = data.placements
  const onIds = all.filter(p => on[p.id]).map(p => p.id)
  const offIds = all.filter(p => !on[p.id]).map(p => p.id)
  const el = elapsedDays(ix)
  const k = kpis(ix, onIds)
  const facts = Object.fromEntries(all.map(p => [p.id, sumOf(ix, [p.id], el).fact]))
  const pDays = periodDays(ix, st.period, range)
  const isTime = !drill ? st.slice === 'day' || st.slice === 'week' : drill.type === 'placement' && (drill.view || 'day') === 'day'
  const model = tableModel(ix, { slice: st.slice, ids: onIds, days: pDays, drill })
  const tRows = isTime ? timeRows(ix, drill?.type === 'placement' ? [drill.id] : onIds, pDays,
    { slice: model.view === 'week' ? 'week' : 'day', metric: st.metric, source: st.source, offIds: st.cmp === 'onoff' && !drill ? offIds : [] }) : []
  const ins = buildInsights(ix, onIds)
  // Значение выбранной метрики за весь показанный отрезок — в строке над графиком, пока курсор не на дне.
  const chartIds = drill?.type === 'placement' ? [drill.id] : onIds
  const chartFact = pDays.filter(x => x <= ix.asOf)
  const chartTotal = metricValue(ix, sumOf(ix, chartIds, chartFact), chartIds, chartFact, st.metric, st.source)
  const offT = sumOf(ix, offIds, el)
  const ext = (p) => p.external
  const setOnBy = (f) => () => { setOn(Object.fromEntries(all.map(p => [p.id, !!f(p)]))); setDrill(null); setFocus(null) }
  const presetDefs = [['все', () => true], ['только крутят', p => p.status === 'запущен' && facts[p.id] > 0], ['наша DSP', p => !ext(p)], ['вне DSP', ext], ['снять всё', () => false]]
  const presets = presetDefs.map(([label, f]) => ({ label, pick: setOnBy(f), match: all.every(p => !!on[p.id] === !!f(p)) }))
  const sourceOff = v => v !== 'our' && !['shows', 'plan'].includes(st.metric)
  const cmpOff = v => !(st.slice === 'day' || st.slice === 'week') && (v === 'need' || v === 'week')
  const crumb = { base: SL_NAME[st.slice], drill: drill ? (drill.type === 'placement' ? ix.pById[drill.id]?.domain : drill.type === 'creative' ? `комплект №${drill.id}` : dm(drill.id)) : '' }
  const periodLabel = st.period === 'all' ? 'весь флайт' : st.period === '7d' ? '7 дн.' : range ? `${dm(range[0])}–${dm(range[1])}` : 'свой отрезок'
  const weekLabel = (r) => `${dm(r.days[0])}–${dm(r.days[r.days.length - 1])}`

  const onDay = (r) => {
    if (st.period === 'custom') {
      if (!pick) { setPick(r.key); setRange([r.key, r.key]) } else { setRange(pick < r.key ? [pick, r.key] : [r.key, pick]); setPick(null) }
      return
    }
    if (!r.future && r.days.length === 1 && !drill) { setDrill({ type: 'day', id: r.key }); setSort(null) }
  }
  const go = (t) => {
    if (!t) return
    if (t.type === 'placement') { setSt(s => ({ ...s, slice: 'placement', source: 'our' })); setDrill(null); setFocus(t.id) }
    if (t.type === 'day') { setSt(s => ({ ...s, slice: 'day' })); setDrill(null); setFocus(t.id) }
    if (t.type === 'slice') { setSt(s => ({ ...s, slice: t.id, metric: 'ctr' })); setDrill(null) }
    if (t.type === 'preset') setOnBy(ext)()
    if (t.type === 'source') { setSt(s => ({ ...s, slice: 'placement', metric: 'shows', source: t.id })); setSort({ key: 'wrd', dir: 1 }); setDrill(null) }
    if (t.type === 'metric') { setSt(s => ({ ...s, slice: 'day', metric: t.id })); setDrill(null) }
  }
  const exportXlsx = async () => {
    setExporting(true)
    try {
      const title = `Отчёт по РК ${data.head.code} · ${crumb.base}${drill ? ' · ' + crumb.drill : ''} · ${periodLabel} · площадок ${onIds.length} из ${all.length}`
      const rows = model.rows.map(r => Object.fromEntries(model.cols.map(c => [c.key, typeof r[c.key] === 'number' ? Math.round(r[c.key] * 100) / 100 : (c.kind === 'date' ? cellText(c, r[c.key]) : r[c.key])])))
      const r = await api.post(`/rk-analysis/${encodeURIComponent(data.head.code)}/export.xlsx`, { title, columns: model.cols.map(c => ({ key: c.key, label: c.label })), rows },
        { ...auth(), responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = downloadName(`Отчёт по РК ${data.head.code}`, 'xlsx'); a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr('Не удалось выгрузить срез') }
    setExporting(false)
  }

  return (
    <Shell code={data.head.code}>
      <RkHead head={data.head} k={k} ix={ix} checks={data.checks} partial={offIds.length ? ` · по ${onIds.length} из ${all.length}` : ''} onExport={exportXlsx} exporting={exporting} />

      <div style={{ ...box, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        {[['Разрез', 'slice', SLICES], ['Метрика', 'metric', METRICS],
          ['Источник', 'source', SOURCES, sourceOff], ['Период', 'period', PERIODS], ['Сравнение', 'cmp', COMPARES, cmpOff]].map(([label, key, opts, dis]) => (
          <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            <span style={cap}>{label}</span>
            <Seg value={st[key]} opts={opts} onPick={v => set(key, v)} disabled={dis || undefined} />
          </span>
        ))}
      </div>

      <div style={{ ...box, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          {!!drill && (
            <button type="button" onClick={() => { setDrill(null); setSort(null); setFocus(null) }} title="Вернуться к динамике · Esc"
              style={{ height: 26, padding: '0 10px', background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', borderRadius: 8, color: 'var(--accent-fg)',
                fontSize: 11.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>← к динамике</button>
          )}
          <span style={title14}>{isTime ? 'Динамика' : 'Сравнение'} · {MNAME[st.metric]}{st.metric === 'shows' && st.source !== 'our' ? (st.source === 'wr' ? ' Weborama' : ' · расхождение с Weborama') : ''}</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
            {SL_NAME[model.view]}{drill ? ' · ' + crumb.drill : ''} · {periodLabel}</span>
        </div>
        {!onIds.length ? (
          <div style={{ height: 250, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, background: 'var(--bg-subtle)', borderRadius: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>Все площадки выключены</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Включите хотя бы одну ниже — график, итоги и выводы пересчитаются.</span>
          </div>
        ) : isTime ? (
          <TimeChart rows={tRows} metric={st.metric} source={st.source} cmp={st.cmp} events={ix.ev} on={on} tech={tech} setTech={setTech}
            onDay={onDay} pickNote={st.period === 'custom' ? (pick ? 'выберите второй день' : 'кликните начало и конец отрезка') : ''}
            inRange={x => st.period === 'custom' && range && range[0] <= x && x <= range[1]}
            nPlaces={drill?.type === 'placement' ? 1 : onIds.length} wrLimit={data.head.wr_limit || 10} total={chartTotal} />
        ) : (
          <RankChart rows={model.rows} metric={st.metric} source={st.source} focus={focus} onRow={d => { setDrill(d); setSort(null) }} />
        )}
      </div>

      <RkPlacements placements={all} on={on} facts={facts} focus={focus} presets={presets}
        onToggle={id => { setOn(o => ({ ...o, [id]: !o[id] })); setFocus(null) }} />

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <RkTable model={model} metric={st.metric} sort={sort} setSort={setSort} drill={drill} crumb={crumb} focus={focus} weekLabel={weekLabel}
          onDrill={d => { setDrill(d); setSort(null); setFocus(null) }} onUndrill={() => { setDrill(null); setSort(null); setFocus(null) }}
          drillView={drill?.view || 'day'} setDrillView={v => { setDrill(d => ({ ...d, view: v })); setSort(null) }} />
        <RkInsights items={onIds.length ? ins : []} onGo={go} onCount={onIds.length} offCount={offIds.length}
          cmp={cmpGroups({ n: onIds.length, fact: k.fact }, { n: offIds.length, fact: offT.fact, plan: planTotal(ix, offIds) }, k, k.plan)} />
      </div>

      <RkAnalytics ix={ix} ids={onIds} prev={data.prev} onPrev={setPrevId} />
    </Shell>
  )
}

function Shell({ code, children }) {
  // Открыт из расхлопа дашборда аккаунта — шапка остаётся в контуре «Аккаунты», «Дашборд» ведёт туда же (владелец 15.10.2026).
  const fromAccounts = useRouter().query.from === 'accounts'
  return (
    <>
      <Head><title>{code ? `Отчёт по РК ${code}` : 'Отчёт по РК'} · Трафики | SIMB-AD ERP</title></Head>
      <Navbar asPath={fromAccounts ? '/accounts/dashboard' : undefined} />
      <div style={{ maxWidth: 2500, margin: '0 auto', padding: '18px 24px 40px', fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {children}
      </div>
    </>
  )
}
