import { useState, useEffect, useCallback, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import Navbar, { can } from '../../components/Navbar'
import SalesTabs from '../../components/SalesTabs'
import YearPlan from '../../components/plan/YearPlan'

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
    id: bid++, brand: l.brand_id ? (brandName[l.brand_id] || '') : '', brand_id: l.brand_id || null,
    plan: l.plan_amount || 0,
    on: (l.months_on || []).slice(0, 12).concat(Array(12).fill(0)).slice(0, 12),
    sums: l.sums || {}, locks: l.locks || {}, products: l.products || {}, deals: l.deals || {},
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
      advertiser_id: g.adv_id || null, brand_id: b.brand_id || null, plan_amount: b.plan || 0,
      months_on: b.on.map(v => (v ? 1 : 0)),
      sums: b.sums || {}, locks: b.locks || {}, products: b.products || {}, deals: b.deals || {},
      sort_order: gi * 100 + bi,
    })
  }))
  return lines
}

export default function YearPlanPage() {
  const [perms, setPerms] = useState(null)
  const [year, setYear] = useState(CUR_YEAR)
  const [view, setView] = useState(null)        // null=свой | number=сейлз | 'all'=показать все
  const [groups, setGroups] = useState([])
  const [advertisers, setAdvertisers] = useState([])
  const [services, setServices] = useState([])
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
      setGroups(linesToGroups(r.data.lines || [], advs))
      setMe(r.data.me || { is_master: false, rep_id: null, own_rep_id: null })
      setReps(r.data.reps || [])
    }).catch(() => { setGroups([]) }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { if (perms) load(year, view) }, [perms, year, view, load])

  // сейлз для записи: явно выбранный сейлз, иначе свой (бэк сам прижмёт не-мастера)
  const saveRepId = typeof view === 'number' ? view : (me.own_rep_id ?? null)

  const onSave = useCallback(async (curGroups) => {
    setSaving(true)
    try {
      const r = await api.post('/sales/year-plan', { year, rep_id: saveRepId, lines: groupsToLines(curGroups) }, auth())
      setGroups(linesToGroups(r.data.lines || [], advertisers))
      setSavedAt(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }))
      api.get('/sales/year-plan/years', auth()).then(r2 => setYears(r2.data.years || [])).catch(() => {})
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить') }
    finally { setSaving(false) }
  }, [year, advertisers, saveRepId])

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

  if (perms && !can(perms, 'year_plan', 'view') && localStorage.getItem('is_admin') !== 'true') {
    return (<><Navbar /><div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>Нет доступа к разделу «Годовой план».</div></>)
  }

  return (
    <>
      <Head><title>Годовой план · {year}</title></Head>
      <Navbar />
      <div style={{ background: '#EBEEF6', minHeight: 'calc(100vh - 56px)' }}>
        <div style={{ padding: '18px 32px 0' }}><SalesTabs active="year_plan" /></div>
        {loading
          ? <div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>Загрузка…</div>
          : <YearPlan
              year={year} years={years} onYear={setYear}
              groups={groups} advertisers={advertisers} services={services}
              onSave={onSave} onMatch={onMatch} saving={saving} matching={matching}
              savedAt={savedAt} readOnly={!canEdit || allMode}
              reps={reps} repValue={me.rep_id} onRep={setView}
              ownRepId={me.own_rep_id} isMaster={me.is_master}
              mode={allMode ? 'all' : 'edit'} allData={allData}
              onVerifyPassword={onVerifyPassword} />}
      </div>
    </>
  )
}
