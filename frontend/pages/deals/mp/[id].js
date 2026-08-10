import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '../../../lib/api'
import Navbar, { can } from '../../../components/Navbar'
import MediaPlanBuilder from '../../../components/mediaplan/MediaPlanBuilder'
import { downloadName } from '../../../lib/salesFormat'
import { DownloadOverlay } from '../../../components/LogoLoader'

// Редактор/генератор медиаплана. id === 'new' — новый; число — правка сохранённого.
const DEFAULT_FORMATS = ['Banners', 'Rich', 'Video', 'Native']
const num = (v) => (v === '' || v == null ? null : +v)
// Модель расчёта по умолчанию из настроек услуги (calc_form) → одна из MODELS (CPM/CPC/Fix).
const MODEL_OF = (cf) => { const m = String(cf || '').toUpperCase(); return m === 'CPM' ? 'CPM' : m === 'CPC' ? 'CPC' : 'Fix' }

export default function MpEditor() {
  const router = useRouter()
  const { id } = router.query
  const isNew = id === 'new'
  const [loaded, setLoaded] = useState(null)   // сохранённый МП (initial)
  const [savedId, setSavedId] = useState(null)
  const [downloading, setDownloading] = useState(false)   // оверлей 1c на время выгрузки
  const [versions, setVersions] = useState([])            // история версий (для дропдауна)
  const [canApprove, setCanApprove] = useState(false)     // право media_plans:approve

  const [catalog, setCatalog] = useState(null)
  const [extraCatalog, setExtraCatalog] = useState(null)
  const [advertisers, setAdvertisers] = useState([])
  const [agencies, setAgencies] = useState([])
  const [brandsByAdv, setBrandsByAdv] = useState({})
  const [advCps, setAdvCps] = useState({})
  const [agencyCps, setAgencyCps] = useState({})
  const [geoList, setGeoList] = useState([])
  const [targetingCatalog, setTargetingCatalog] = useState({})
  const [staff, setStaff] = useState(null)   // { 'Продавец': [...], 'Аккаунт': [...] }

  const loadTargeting = useCallback(() => api.get('/sales/directories/targeting', auth()).then(r => setTargetingCatalog(r.data.groups || {})).catch(() => {}), [])
  const loadGeo = useCallback(() => api.get('/sales/directories/geo', auth()).then(r => setGeoList(r.data.items || [])).catch(() => {}), [])
  // Бренды из открытого справочника (не sales-гейченного), сгруппированы по рекламодателю.
  const loadBrands = useCallback(() => api.get('/sales/directories/brands', auth()).then(r => {
    const m = {}; (r.data.items || []).forEach(b => { (m[b.advertiser_id] = m[b.advertiser_id] || []).push({ value: b.id, label: b.name }) }); setBrandsByAdv(m)
  }).catch(() => {}), [])
  const loadVersions = useCallback(() => { if (!id || id === 'new') return; api.get(`/sales/media-plans/${id}/versions`, auth()).then(r => setVersions(r.data.items || [])).catch(() => setVersions([])) }, [id])

  useEffect(() => {
    if (typeof window === 'undefined' || !id) return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    const _isAdm = localStorage.getItem('role') === 'admin'
    { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
      setCanApprove(_isAdm || can(p, 'media_plans', 'approve')) }
    if (!_isAdm) {
      let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
      if (!can(p, 'media_plans_editor', 'view')) { router.replace('/deals/mp'); return }
    }
    api.get('/sales/directories/services?only_active=true', auth())
      .then(r => setCatalog((r.data.items || []).map(s => {
        const names = (s.formats || []).map(f => f.name); const def = s.default_format
        const ordered = def && names.includes(def) ? [def, ...names.filter(n => n !== def)] : names
        return {
          position: s.name, formats: ordered.length ? ordered : (s.placement_type ? [s.placement_type] : DEFAULT_FORMATS),
          unit: s.unit_price || 0, separate: !!s.separate_price, unitWeb: s.unit_price_web || 0, unitApp: s.unit_price_app || 0,
          model: MODEL_OF(s.calc_form),   // модель расчёта по умолчанию из настроек услуги
        }
      }))).catch(() => setCatalog([]))
    api.get('/sales/directories/services/addons?only_active=true', auth())
      .then(r => setExtraCatalog((r.data.items || []).map(a => ({ name: a.name, period: a.period || '', price: a.unit_price || 0 })))).catch(() => setExtraCatalog([]))
    loadBrands()
    // Рекламодатели/агентства — из ОТКРЫТЫХ справочников (аккаунт-кабинет не требует прав продаж).
    api.get('/sales/directories/producers', auth()).then(r => {
      const items = r.data.items || []
      setAdvertisers(items.map(a => ({ value: a.id, label: a.short_name || a.name })))
      const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); setAdvCps(m)
    }).catch(() => {})
    api.get('/sales/directories/agencies', auth()).then(r => {
      const items = r.data.items || []
      setAgencies(items.map(a => ({ value: a.id, label: a.short_name })))
      const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); setAgencyCps(m)
    }).catch(() => {})
    loadTargeting(); loadGeo()
    // Ответственные: пользователи по рабочей группе их роли (Роли → рабочая группа).
    const staffOf = (g) => api.get(`/sales/directories/staff?group=${g}&only_active=true`, auth()).then(r => r.data.items || []).catch(() => [])
    Promise.all([staffOf('seller'), staffOf('account'), staffOf('traffic')]).then(([sellers, accounts, traffic]) => {
      const s = { 'Продавец': sellers, 'Аккаунт': accounts }
      if (traffic.length) s['Трафик'] = traffic   // группа появляется, только когда есть кого показать
      setStaff(s)
    })
    if (!isNew) {
      setSavedId(+id)
      api.get(`/sales/media-plans/${id}`, auth()).then(r => setLoaded(r.data)).catch(() => router.replace('/deals/mp'))
      loadVersions()
    }
  }, [id])

  const onAddTargeting = async (group, value) => { try { await api.post('/sales/directories/targeting', { group, value }, auth()); loadTargeting() } catch (e) { alert(e.response?.data?.detail || 'Ошибка') } return value }
  const onAddGeo = async (name) => { try { const r = await api.post('/sales/directories/geo', { name }, auth()); loadGeo(); return r.data.id } catch (e) { alert(e.response?.data?.detail || 'Ошибка'); return null } }
  const onCreateBrand = async (advertiserId, name) => { if (!advertiserId) return null; try { const r = await api.post('/sales/directories/brands', { name, advertiser_id: +advertiserId }, auth()); loadBrands(); return r.data.id } catch (e) { alert(e.response?.data?.detail || 'Ошибка'); return null } }

  const toPayload = (o) => {
    const b = o.brief || {}
    const ow = o.owners || {}
    return {
      title: b.title || null, advertiser_id: num(b.advertiser_id), brand_id: num(b.brand_id), agency_id: num(b.agency_id),
      payer_counterparty_id: num(b.payer_id), period: b.period || null, geo_id: num(b.geo_id),
      date_from: b.date_from || null, date_to: b.date_to || null, targeting: b.targeting || {}, goals: o.goals || {},
      sales_rep_id: num(ow['Продавец']), account_manager_id: num(ow['Аккаунт']), traffic_manager_id: num(ow['Трафик']),
      status: o.action === 'submit' ? 'review' : 'draft',
      rows: (o.main || []).map(r => ({ position: r.position || null, format: r.format || null, model: r.model || null, inventory: r.inventory || null, volume: r.volume || 0, unit_price: r.unit || 0, discount: r.discount || 0, forecast: (o.fc || {})[r.id] || {} })),
      extras: (o.extras || []).map(e => ({ name: e.name || null, period: e.period || null, mode: e.mode || null, price: e.price || 0, total: e.total || 0 })),
    }
  }

  const onSave = async (o) => {
    const payload = toPayload(o)
    try {
      if (o.action === 'submit') {
        const r = await api.post('/sales/media-plans', { ...payload, group_id: loaded?.group_id || undefined }, auth())
        alert(r.data.unchanged ? `Без изменений — версия ${r.data.version} осталась` : `Отправлено на согласование (версия ${r.data.version})`)
        router.replace(`/deals/mp/${r.data.id}`)
      } else if (savedId) {
        await api.put(`/sales/media-plans/${savedId}`, payload, auth()); alert('Черновик сохранён'); loadVersions()
      } else {
        const r = await api.post('/sales/media-plans', payload, auth()); router.replace(`/deals/mp/${r.data.id}`)
      }
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка сохранения') }
  }

  const onTransition = async (to, comment) => {
    if (!savedId) return
    try {
      await api.post(`/sales/media-plans/${savedId}/status`, { to, comment }, auth())
      const r = await api.get(`/sales/media-plans/${savedId}`, auth()); setLoaded(r.data); loadVersions()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка смены статуса') }
  }

  const onExportXlsx = async () => {
    if (!savedId) { alert('Сначала сохраните медиаплан'); return }
    setDownloading(true)
    try {
      const r = await api.get(`/sales/media-plans/${savedId}/export.xlsx`, { ...auth(), responseType: 'blob' })
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = downloadName(loaded?.title, 'xlsx', 'MP Simb-AD'); a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Ошибка выгрузки') } finally { setDownloading(false) }
  }

  if (!isNew && !loaded) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>

  const backTo = loaded?.deal_id ? `/deals/${loaded.deal_id}` : '/deals/mp'
  const backLabel = loaded?.deal_id ? `Сделка #${loaded.deal_id}` : 'Реестр медиапланов'

  return (
    <>
      <Head><title>Конструктор медиаплана</title></Head>
      {downloading && <DownloadOverlay />}
      <Navbar active="" />
      <MediaPlanBuilder
        key={id}
        initial={loaded || undefined}
        bound={!!loaded?.deal_id}
        backLabel={backLabel}
        onBack={() => router.push(backTo)}
        versions={versions}
        onOpenVersion={(vid) => router.push(`/deals/mp/${vid}`)}
        canApprove={canApprove}
        onTransition={onTransition}
        catalog={catalog || undefined} extraCatalog={extraCatalog || undefined}
        advertisers={advertisers} agencies={agencies} brandsByAdv={brandsByAdv} advCps={advCps} agencyCps={agencyCps}
        geoList={geoList} targetingCatalog={targetingCatalog} staff={staff || { 'Продавец': [], 'Аккаунт': [] }}
        onAddTargeting={onAddTargeting} onAddGeo={onAddGeo} onCreateBrand={onCreateBrand}
        onSave={onSave} onExportXlsx={onExportXlsx}
        onPreviewPdf={async () => {
          if (!savedId) { alert('Сначала сохраните медиаплан'); return }
          setDownloading(true)
          try {
            const r = await api.get(`/sales/media-plans/${savedId}/pdf`, { ...auth(), responseType: 'blob' })
            const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = downloadName(loaded?.title, 'pdf', 'MP Simb-AD'); a.click(); URL.revokeObjectURL(url)
          } catch (e) { alert('Ошибка генерации PDF') } finally { setDownloading(false) }
        }}
        onLinkDeal={() => alert('Привязка к сделке — позже')} onCreateDeal={() => alert('Создание сделки — позже')}
      />
    </>
  )
}
