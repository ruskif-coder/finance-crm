import { useState, useEffect, useCallback, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import { downloadName } from '@/lib/salesFormat'
import Navbar, { can } from '@/components/Navbar'
import YearPlan from '@/components/plan/YearPlan'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const NotOnMobile = dynamic(() => import('@/components/mobile/NotOnMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })

// Годовой план продаж: план по рекламодателям/брендам × 12 месяцев, персональный по сейлзам.
// Мастер (year_plan:edit scope=all / admin) выбирает чей план смотреть + режим «Показать все».
const CUR_YEAR = new Date().getFullYear()

const linesToGroups = (lines, advertisers) => {
  const advById = Object.fromEntries(advertisers.map(a => [a.id, a]))
  const brandName = {}
  advertisers.forEach(a => (a.brands || []).forEach(b => { brandName[b.id] = b.name }))
  const groups = []
  const byAdv = new Map()
  let gid = 1, bid = 1
  const mkBrand = (l) => ({
    id: bid++, line_id: l.id || null, plan_id: l.plan_id || null,
    brand: l.brand_id ? (brandName[l.brand_id] || '') : '', brand_id: l.brand_id || null,
    plan: l.plan_amount || 0,
    on: (l.months_on || []).slice(0, 12).concat(Array(12).fill(0)).slice(0, 12),
    sums: l.sums || {}, locks: l.locks || {}, products: l.products || {}, deals: l.deals || {},
    brief: l.brief || {}, service_forecast: l.service_forecast || {},
  })
  for (const l of lines) {
    if (l.advertiser_id == null) { groups.push({ id: gid++, adv: '', adv_id: null, open: true, brands: [mkBrand(l)] }); continue }
    let g = byAdv.get(l.advertiser_id)
    if (!g) {
      const a = advById[l.advertiser_id]
      g = { id: gid++, adv: a ? a.name : `#${l.advertiser_id}`, adv_id: l.advertiser_id, open: true, brands: [] }
      byAdv.set(l.advertiser_id, g); groups.push(g)
    }
    g.brands.push(mkBrand(l))
  }
  return groups
}

const groupsToLines = (groups) => {
  const lines = []
  groups.forEach((g, gi) => g.brands.forEach((b, bi) => {
    lines.push({
      id: b.line_id || undefined, plan_id: b.plan_id || null,
      advertiser_id: g.adv_id || null, brand_id: b.brand_id || null, plan_amount: b.plan || 0,
      months_on: b.on.map(v => (v ? 1 : 0)),
      sums: b.sums || {}, locks: b.locks || {}, products: b.products || {}, deals: b.deals || {},
      brief: b.brief || {}, service_forecast: b.service_forecast || {},
      sort_order: gi * 100 + bi,
    })
  }))
  return lines
}

export default function YearPlanPage() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [perms, setPerms] = useState(null)
  const [year, setYear] = useState(CUR_YEAR)
  const [view, setView] = useState(null)        // null=свой | number=сейлз | 'all'=показать все
  const [groups, setGroups] = useState([])
  const [advertisers, setAdvertisers] = useState([])
  const [services, setServices] = useState([])
  const [addons, setAddons] = useState([])
  const [briefCatalogs, setBriefCatalogs] = useState({})
  const [years, setYears] = useState([])
  const [me, setMe] = useState({ is_master: false, rep_id: null, own_rep_id: null })
  const [reps, setReps] = useState([])
  const [allData, setAllData] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [matching, setMatching] = useState(false)
  const [savedAt, setSavedAt] = useState('')

  useEffect(() => {
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch { setPerms({}) }
    api.get('/sales/year-plan/years', auth()).then(r => setYears(r.data.years || [])).catch(() => {})
  }, [])

  // Диплинк «Открыть план» из карточки сделки: ?year=&rep= — открываем нужный год и план сейлза.
  useEffect(() => {
    if (!router.isReady) return
    const y = Number(router.query.year), rep = Number(router.query.rep)
    if (y) setYear(y)
    if (rep) setView(rep)
  }, [router.isReady])

  const canEdit = useMemo(() => {
    if (!perms) return false
    try { return localStorage.getItem('is_admin') === 'true' || can(perms, 'year_plan', 'edit') } catch { return can(perms, 'year_plan', 'edit') }
  }, [perms])

  const allMode = view === 'all'

  const load = useCallback((y, v) => {
    setLoading(true)
    setSavedAt('')
    if (v === 'all') {
      api.get(`/sales/year-plan/all?year=${y}`, auth())
        .then(r => setAllData(r.data.reps || []))
        .catch(() => setAllData([]))
        .finally(() => setLoading(false))
      return
    }
    const q = typeof v === 'number' ? `&rep_id=${v}` : ''
    api.get(`/sales/year-plan?year=${y}${q}`, auth()).then(r => {
      const advs = r.data.catalog?.advertisers || []
      setAdvertisers(advs)
      setServices(r.data.catalog?.services || [])
      setAddons(r.data.catalog?.addons || [])
      setGroups(linesToGroups(r.data.lines || [], advs))
      setMe(r.data.me || { is_master: false, rep_id: null, own_rep_id: null })
      setReps(r.data.reps || [])
    }).catch(() => { setGroups([]) }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { if (perms) load(year, view) }, [perms, year, view, load])

  // каталоги брифа (агентства/юрлица/гео/таргетинг/ответственные) — из открытых справочников, как в конструкторе МП
  useEffect(() => {
    if (!perms) return
    const g = {}
    Promise.all([
      api.get('/sales/directories/producers', auth()).then(r => { const items = r.data.items || []; const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); g.advCps = m }).catch(() => {}),
      api.get('/sales/directories/agencies', auth()).then(r => { const items = r.data.items || []; g.agencies = items.map(a => ({ value: a.id, label: a.short_name })); const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); g.agencyCps = m }).catch(() => {}),
      api.get('/sales/directories/geo', auth()).then(r => { g.geoList = r.data.items || [] }).catch(() => {}),
      api.get('/sales/directories/targeting', auth()).then(r => { g.targeting = r.data.groups || {} }).catch(() => {}),
      api.get('/sales/directories/staff?group=seller&only_active=true', auth()).then(r => { g.sellers = r.data.items || [] }).catch(() => {}),
      api.get('/sales/directories/staff?group=account&only_active=true', auth()).then(r => { g.accounts = r.data.items || [] }).catch(() => {}),
    ]).then(() => setBriefCatalogs(g))
  }, [perms])

  // сейлз для записи: явно выбранный сейлз, иначе свой (бэк сам прижмёт не-мастера)
  const saveRepId = typeof view === 'number' ? view : (me.own_rep_id ?? null)

  const onSave = useCallback(async (curGroups) => {
    // у мастера без своего SalesRep (напр. админ) нет «своего» плана — нужен явный выбор сейлза
    if (saveRepId == null) {
      alert('Выберите сейлза в шапке (в чей план сохранять) — у вашей учётки нет собственного плана.')
      return
    }
    setSaving(true)
    try {
      const r = await api.post('/sales/year-plan', { year, rep_id: saveRepId, lines: groupsToLines(curGroups) }, auth())
      setGroups(linesToGroups(r.data.lines || [], advertisers))
      setSavedAt(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }))
      api.get('/sales/year-plan/years', auth()).then(r2 => setYears(r2.data.years || [])).catch(() => {})
    } catch (e) {
      console.error('year-plan save failed', e)
      const d = e.response?.data?.detail
      alert(d ? `Ошибка сохранения: ${typeof d === 'string' ? d : JSON.stringify(d)}` : `Не удалось сохранить (${e.response?.status || e.message || 'нет ответа от сервера'})`)
    }
    finally { setSaving(false) }
  }, [year, advertisers, saveRepId])

  const onAddTargeting = useCallback(async (group, value) => {
    try {
      await api.post('/sales/directories/targeting', { group, value }, auth())
      const r = await api.get('/sales/directories/targeting', auth())
      setBriefCatalogs(c => ({ ...c, targeting: r.data.groups || c.targeting }))
    } catch (e) { /* нет прав на каталог — значение всё равно добавится разово в бриф */ }
  }, [])

  const onConveyorPreview = useCallback(async (target) => {
    const r = await api.post('/sales/year-plan/create-deals/preview', { year, rep_id: saveRepId, ...target }, auth())
    return r.data
  }, [year, saveRepId])

  const onConveyorApply = useCallback(async (target) => {
    const r = await api.post('/sales/year-plan/create-deals', { year, rep_id: saveRepId, ...target }, auth())
    // подтянуть факт/бронь по жёсткому линку и перезагрузить план, чтобы сделки появились в ячейках
    try { await api.post('/sales/year-plan/match-deals', { year, rep_id: saveRepId }, auth()) } catch {}
    load(year, view)
    return r.data
  }, [year, saveRepId, view, load])

  // Годовой МП в Excel: книга целиком собирается на бэке (сводная + бриф + месяцы).
  // Единица выгрузки — рекламодатель со всеми брендами, как он показан на странице:
  // бренды одного рекламодателя могут лежать в разных планах-пакетах, и выгрузка по
  // плану дала бы только часть брендов.
  const onExport = useCallback(async (advId, advName) => {
    try {
      const q = typeof view === 'number' ? `&rep_id=${view}` : ''
      const res = await api.get(
        `/sales/year-plan/export.xlsx?year=${year}&advertiser_id=${advId}${q}`,
        { responseType: 'blob', ...auth() })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      // Имя с датой и временем — общим хелпером, как у выгрузок МП: две выгрузки
      // одного плана за день иначе называются одинаково и затирают друг друга в «Загрузках».
      a.download = downloadName(`${advName || 'план'} ${year}`, 'xlsx', 'Годовой МП Simb-AD')
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      // detail приходит blob'ом (responseType), поэтому читаем текстом
      let msg = ''
      try { msg = JSON.parse(await e.response?.data?.text()).detail } catch {}
      alert(msg || 'Не удалось выгрузить годовой медиаплан')
    }
  }, [year, view])

  const onVerifyPassword = useCallback(async (password) => {
    try { await api.post('/auth/verify-password', { password }, auth()); return true }
    catch { return false }
  }, [])

  const onMatch = useCallback(async (pairs) => {
    if (!pairs.length) { alert('Нет заведённых строк для сверки со сделками'); return null }
    setMatching(true)
    try {
      const r = await api.post('/sales/year-plan/match-deals', { year, rep_id: saveRepId, pairs }, auth())
      if (!(r.data.deals_count || 0)) alert('Сделок под заведённые планы не найдено')
      return r.data.matched || []
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка сверки'); return null }
    finally { setMatching(false) }
  }, [year, saveRepId])

  if (isMobile) return (<><Navbar /><NotOnMobile title="Годовой план" backHref="/sales" backLabel="К продажам" /></>)

  if (perms && !can(perms, 'year_plan', 'view') && localStorage.getItem('is_admin') !== 'true') {
    return (<><Navbar /><div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>Нет доступа к разделу «Годовой план».</div></>)
  }

  return (
    <>
      <Head><title>Годовой план · {year}</title></Head>
      <Navbar />
      <div style={{ background: '#EBEEF6', minHeight: 'calc(100vh - 56px)' }}>
        {loading
          ? <div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>Загрузка…</div>
          : <YearPlan
              year={year} years={years} onYear={setYear}
              groups={groups} advertisers={advertisers} services={services} addons={addons} briefCatalogs={briefCatalogs}
              onSave={onSave} onMatch={onMatch} saving={saving} matching={matching}
              savedAt={savedAt} readOnly={!canEdit || allMode}
              reps={reps} repValue={me.rep_id} onRep={setView}
              ownRepId={me.own_rep_id} isMaster={me.is_master}
              mode={allMode ? 'all' : 'edit'} allData={allData}
              onVerifyPassword={onVerifyPassword} onAddTargeting={onAddTargeting}
              onConveyorPreview={onConveyorPreview} onConveyorApply={onConveyorApply}
              onExport={onExport} />}
      </div>
    </>
  )
}
