import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import Navbar, { can } from '@/components/Navbar'
import MediaPlanBuilder from '@/components/mediaplan/MediaPlanBuilder'
import { downloadName, grp } from '@/lib/salesFormat'
import { DownloadOverlay } from '@/components/LogoLoader'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
import { overlayClose } from '@/lib/overlay'
const NotOnMobile = dynamic(() => import('@/components/mobile/NotOnMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })

// Редактор/генератор медиаплана. id === 'new' — новый; число — правка сохранённого.
const DEFAULT_FORMATS = ['Banners', 'Rich', 'Video', 'Native']
const num = (v) => (v === '' || v == null ? null : +v)
// Модель расчёта по умолчанию из настроек услуги (calc_form) → одна из MODELS (CPM/CPC/Fix).
const MODEL_OF = (cf) => { const m = String(cf || '').toUpperCase(); return m === 'CPM' ? 'CPM' : m === 'CPC' ? 'CPC' : 'Fix' }

export default function MpEditor() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const { id } = router.query
  const isNew = id === 'new'
  const dealParam = router.query.deal          // создание МП из сделки: /accounts/mp/new?deal=<id>
  const [prefill, setPrefill] = useState(null) // префилл нового МП из сделки
  const [loaded, setLoaded] = useState(null)   // сохранённый МП (initial)
  const [savedId, setSavedId] = useState(null)
  const [downloading, setDownloading] = useState(false)   // оверлей 1c на время выгрузки
  const [versions, setVersions] = useState([])            // история версий (для дропдауна)

  const [catalog, setCatalog] = useState(null)
  const [extraCatalog, setExtraCatalog] = useState(null)
  const [advertisers, setAdvertisers] = useState([])
  const [agencies, setAgencies] = useState([])
  const [brandsByAdv, setBrandsByAdv] = useState({})
  const [advCps, setAdvCps] = useState({})
  const [agencyCps, setAgencyCps] = useState({})
  const [geoList, setGeoList] = useState([])
  const [targetingCatalog, setTargetingCatalog] = useState({})
  const [ownCompany, setOwnCompany] = useState(null)
  const [staff, setStaff] = useState(null)   // { 'Продавец': [...], 'Аккаунт': [...] }
  const [linkOpen, setLinkOpen] = useState(false)   // модалка привязки к сделке
  const [dealQ, setDealQ] = useState('')
  const [dealHits, setDealHits] = useState([])
  const [dealSort, setDealSort] = useState('id')
  const [dealDir, setDealDir] = useState('desc')
  const [dealBrief, setDealBrief] = useState(null)   // free-text бриф связанной сделки

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
    if (!_isAdm) {
      let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
      if (!can(p, 'media_plans_editor', 'view')) { router.replace('/accounts/mp'); return }
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
    // Юрлицо, от которого оказываем услуги: оно задаёт ставку НДС по нашим услугам.
    api.get('/sales/own-company', auth()).then(r => setOwnCompany(r.data)).catch(() => {})
    if (!isNew) {
      setSavedId(+id)
      api.get(`/sales/media-plans/${id}`, auth()).then(r => { setLoaded(r.data); loadDealBrief() }).catch(() => router.replace('/accounts/mp'))
      loadVersions()
    } else if (dealParam) {
      // Создание МП из сделки — префилл реквизитов + брифа
      api.get(`/sales/media-plans/deal-prefill/${dealParam}`, auth()).then(r => {
        // Строку размещения собирает бэкенд (_prefill_rows) — по тарифу услуги, как
        // конвейер годового плана: модель/формат/инвентарь из справочника,
        // объём = сумма ÷ цену × (CPM → 1000). Здесь ничего не пересчитываем.
        setPrefill({ ...r.data, rows: r.data.rows || [] })
        setDealBrief({ has_deal: true, deal_id: +dealParam, brief: r.data.brief || '', is_local: r.data.is_local })
      }).catch(() => setPrefill({}))
    }
  }, [id, dealParam])

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
      deal_id: loaded?.deal_id ?? (dealParam ? +dealParam : null),   // привязка к сделке (сохранённая или из префилла)
      // отметка «проверено» (обе галочки в конструкторе) и комментарий о причинах
      // изменений — идут только в журнал, в самой версии МП не хранятся
      verified: !!o.verified, change_note: o.change_note || '',
      rows: (o.main || []).map(r => ({ position: r.position || null, format: r.format || null, model: r.model || null, inventory: r.inventory || null, volume: r.volume || 0, unit_price: r.unit || 0, discount: r.discount || 0, forecast: (o.fc || {})[r.id] || {} })),
      extras: (o.extras || []).map(e => ({ name: e.name || null, period: e.period || null, mode: e.mode || null, price: e.price || 0, total: e.total || 0 })),
    }
  }

  // Одно сохранение на все случаи: создание, правка и новая версия. Что именно
  // произошло, решает сервер (см. save_media_plan) — фронт больше не выбирает это
  // кнопкой, поэтому и кнопка одна.
  const onSave = async (o) => {
    const payload = toPayload(o)
    try {
      const r = await api.post('/sales/media-plans',
        { ...payload, group_id: loaded?.group_id || undefined }, auth())
      if (!savedId || String(r.data.id) !== String(savedId)) {
        router.replace(`/accounts/mp/${r.data.id}`)
        return
      }
      alert(r.data.unchanged ? 'Изменений нет — сохранена только отметка «проверено»'
        : `Сохранено, версия ${r.data.version}`)
      await reloadPlan(); loadVersions()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка сохранения') }
  }

  // Сделка из плана — второй путь её рождения, наравне с конвейером годового плана.
  // Название и реквизиты собирает сервер по тем же правилам, что конвейер, поэтому
  // здесь только подтверждение и показ результата.
  const onCreateDeal = async () => {
    if (!savedId) return
    if (!window.confirm('Создать сделку по этому медиаплану?\n\n'
      + 'Реквизиты, сумма и период возьмутся из плана, название соберётся по шаблону.\n'
      + 'Сделка встанет на первую стадию — дальше её двинет отметка «Проверено».')) return
    try {
      const r = await api.post(`/sales/media-plans/${savedId}/create-deal`, {}, auth())
      await reloadPlan(); loadDealBrief(); loadVersions()
      alert(`Сделка ${r.data.code} создана: ${r.data.title}\nСтадия: ${r.data.stage || '—'}`)
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось создать сделку') }
  }

  // ── Привязка МП к сделке ──
  const searchDeals = async (q, sort = dealSort, dir = dealDir) => {
    try { const r = await api.get(`/sales/media-plans/deals-lookup?q=${encodeURIComponent(q || '')}&sort=${sort}&direction=${dir}`, auth()); setDealHits(r.data.items || []) }
    catch (e) { setDealHits([]) }
  }
  const sortDeals = (key) => {
    const dir = dealSort === key && dealDir === 'asc' ? 'desc' : 'asc'
    setDealSort(key); setDealDir(dir); searchDeals(dealQ, key, dir)
  }
  const openLink = () => { if (!savedId) { alert('Сначала сохраните медиаплан'); return } setLinkOpen(true); setDealQ(''); searchDeals('') }
  const reloadPlan = () => api.get(`/sales/media-plans/${savedId}`, auth()).then(r => setLoaded(r.data)).catch(() => {})
  const doLink = async (dealId) => {
    try { await api.post(`/sales/media-plans/${savedId}/link-deal`, { deal_id: dealId }, auth()); await reloadPlan(); loadDealBrief(); setLinkOpen(false) }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось привязать') }
  }

  // ── Free-text бриф связанной сделки ──
  const loadDealBrief = (refresh = 0) => {
    const pid = savedId || (id && id !== 'new' ? id : null)
    if (!pid) return
    api.get(`/sales/media-plans/${pid}/deal-brief${refresh ? '?refresh=1' : ''}`, auth())
      .then(r => setDealBrief(r.data)).catch(() => {})
  }
  const onDealBriefSave = async (text) => {
    if (!savedId) { alert('Сначала сохраните медиаплан — потом бриф запишется в сделку'); return }
    try { const r = await api.put(`/sales/media-plans/${savedId}/deal-brief`, { brief: text }, auth()); setDealBrief(d => ({ ...(d || {}), ...r.data, has_deal: true })); alert(r.data.pushed_to_bitrix ? 'Бриф сохранён и отправлен в Битрикс' : 'Бриф сохранён') }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить бриф') }
  }
  const onDealBriefSync = async () => {
    if (!savedId) { alert('Сначала сохраните медиаплан'); return }
    try { const r = await api.get(`/sales/media-plans/${savedId}/deal-brief?refresh=1`, auth()); setDealBrief(r.data) }
    catch (e) { alert(e.response?.data?.detail || 'Битрикс недоступен') }
  }

  const onExportXlsx = async () => {
    if (!savedId) { alert('Сначала сохраните медиаплан'); return }
    setDownloading(true)
    try {
      const r = await api.get(`/sales/media-plans/${savedId}/export.xlsx`, { ...auth(), responseType: 'blob' })
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = downloadName(loaded?.title, 'xlsx', 'MP Simb-AD'); a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Ошибка выгрузки') } finally { setDownloading(false) }
  }

  if (isMobile) return (<><Navbar /><NotOnMobile title="Медиаплан" backHref="/accounts/mp" backLabel="К медиапланам" /></>)

  if (!isNew && !loaded) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>
  if (isNew && dealParam && !prefill) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>Подготовка медиаплана из сделки…</div>

  // В интерфейсе сделка обозначается НАШИМ кодом, а не внутренним id (см. deal-code).
  // Ссылка тоже по коду — роут /sales/deals/[id] резолвит и код, и id.
  const backRef = loaded?.deal_code || loaded?.deal_id
  const backTo = loaded?.deal_id ? `/sales/deals/${backRef}` : '/accounts/mp'
  const backLabel = loaded?.deal_id ? `Сделка ${backRef}` : 'Реестр медиапланов'

  return (
    <>
      <Head><title>Конструктор медиаплана</title></Head>
      {downloading && <DownloadOverlay />}
      <Navbar active="" />
      <MediaPlanBuilder
        key={id}
        initial={loaded || prefill || undefined}
        bound={!!(loaded?.deal_id || dealParam)}
        backLabel={backLabel}
        onBack={() => router.push(backTo)}
        versions={versions}
        onOpenVersion={(vid) => router.push(`/accounts/mp/${vid}`)}
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
        onLinkDeal={openLink} onCreateDeal={onCreateDeal}
        ownCompany={ownCompany || undefined}
        dealBrief={dealBrief} onDealBriefSave={onDealBriefSave} onDealBriefSync={onDealBriefSync}
      />
      {linkOpen && (() => {
        const COLS = [['bitrix_id', 'BX_ID'], ['advertiser', 'Рекламодатель'], ['brand', 'Бренд'], ['agency', 'Агентство'], ['sales_rep', 'Продавец'], ['account_manager', 'Аккаунт'], ['period', 'Период'], ['amount', 'Сумма'], ['our_stage', 'Наш этап'], ['has_mp', 'МП']]
        const th = { padding: '7px 9px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none', position: 'sticky', top: 0, background: 'var(--bg-card)' }
        const td = { padding: '7px 9px', fontSize: 12.5, borderBottom: '1px solid var(--border-row)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }
        const arrow = (k) => dealSort === k ? (dealDir === 'asc' ? ' ▲' : ' ▼') : ''
        const money = grp   // общий форматтер, не своя копия
        return (
        <div {...overlayClose(() => setLinkOpen(false))} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(15,23,42,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, width: 'min(1040px, 97vw)', padding: '20px 22px', boxShadow: '0 24px 64px rgba(28,36,51,.22)', display: 'flex', flexDirection: 'column', maxHeight: '88vh' }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Привязать к сделке</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 12 }}>
              Сделки до стадии «Бронь» включительно.{' '}
              {loaded?.deal_id ? <>Сейчас привязан к сделке #{loaded.deal_id}. <span onClick={() => doLink(null)} style={{ color: 'var(--danger)', cursor: 'pointer', fontWeight: 600 }}>Отвязать</span></> : 'Найдите сделку и нажмите на строку.'}
            </div>
            <input autoFocus value={dealQ} onChange={e => { setDealQ(e.target.value); searchDeals(e.target.value) }} placeholder="поиск по рекламодателю, бренду, агентству, продавцу, BX_ID…"
              style={{ width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 11px', fontSize: 14, marginBottom: 12, outline: 'none' }} />
            <div style={{ overflow: 'auto', flex: 1, border: '1px solid var(--border-card)', borderRadius: 10 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  {COLS.map(([k, lbl]) => <th key={k} style={th} onClick={() => sortDeals(k)}>{lbl}{arrow(k)}</th>)}
                  <th style={{ ...th, cursor: 'default' }}></th>
                </tr></thead>
                <tbody>
                  {dealHits.map(d => (
                    <tr key={d.id} onClick={() => doLink(d.id)} className="mp-linkrow"
                      style={{ cursor: 'pointer', background: d.id === loaded?.deal_id ? 'var(--accent-tint)' : undefined }}>
                      <td style={{ ...td, fontFamily: 'monospace', color: 'var(--accent)', fontWeight: 700 }}>{d.bitrix_id}</td>
                      <td style={{ ...td, fontWeight: 600, color: 'var(--text-primary)' }} title={d.advertiser || ''}>{d.advertiser || '—'}</td>
                      <td style={td} title={d.brand || ''}>{d.brand || '—'}</td>
                      <td style={td} title={d.agency || ''}>{d.agency || '—'}</td>
                      <td style={td}>{d.sales_rep || '—'}</td>
                      <td style={td}>{d.account_manager || '—'}</td>
                      <td style={{ ...td, fontFamily: 'monospace' }}>{d.period || '—'}</td>
                      <td style={{ ...td, fontFamily: 'monospace', textAlign: 'right' }}>{money(d.amount)}</td>
                      <td style={td}>{d.our_stage || '—'}</td>
                      <td style={td}>{d.has_mp
                        ? <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--success)', background: 'var(--success-tint, rgba(16,185,129,.12))', borderRadius: 6, padding: '2px 7px' }}>есть</span>
                        : <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>нет</span>}</td>
                      <td style={{ ...td, color: 'var(--accent)', fontWeight: 700 }}>привязать →</td>
                    </tr>
                  ))}
                  {!dealHits.length && <tr><td colSpan={11} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Ничего не найдено</td></tr>}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{dealHits.length} сделок</span>
              <button onClick={() => setLinkOpen(false)} style={{ padding: '9px 18px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Закрыть</button>
            </div>
          </div>
        </div>
      )})()}
    </>
  )
}
