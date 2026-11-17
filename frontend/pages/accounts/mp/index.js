import MonthInput from '@/components/MonthInput'
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { isAdmin as isAdminFn, canDelete as canDeleteRight } from '@/lib/auth'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { MONO, UI, card, primaryBtn, MultiDrop, LoadError, PortalPopover } from '@/components/salesTableKit'
import { errText, isAuth, detailText } from '@/lib/loadError'
import api, { auth } from '@/lib/api'
import { downloadMp } from '@/lib/mpDownload'
import { DownloadOverlay } from '@/components/LogoLoader'
import ValuePopover from '@/components/ValuePopover'
import { buildTitle, separatePriceSet, TITLE_EMPTY_HINT } from '@/lib/dealTitle'
import { monthMsk } from '@/lib/dates'
import { bucketCounts, cellsOpen, closedByDefault, filterRows, pageView } from '@/lib/mpRegistryModel.mjs'
import RegistryRow, { RowDetail, GRID, TABLE_MIN_W } from '@/components/accounts/mpRegistry/RegistryRow'
import { GroupHead, RegistryFooter, SortBlock, StageChips, Toggle } from '@/components/accounts/mpRegistry/controls'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

// Реестр медиапланов (контур аккаунта), v2 — хендофф design_handoff_mp_registry (17.11.2026): расхлоп строки
// с планом (как в карточке сделки), колонки «Услуга» и «Обновлён», замок и виза у ID, группы по месяцам, чипы этапов
// и «Мои», блок «Порядок», липкие шапка и первая колонка, страницы. Правка ячеек, права, выгрузки и удаление — как были.
// Данные приходят пачкой (последние версии), фильтр/сортировка/страницы — клиентские (lib/mpRegistryModel.mjs).

// Шапка таблицы: [ключ сортировки, подпись, вправо]. Первая колонка — «ID» и «Сделка» отдельными кликами.
const HEAD = [
  ['product_label', 'Услуга'], ['agency', 'Агентство'], ['advertiser', 'Рекламодатель'], ['brand', 'Бренд'],
  ['period', 'Период'], ['amount_gross', 'Сумма', true], ['sales_rep', 'Продавец'], ['account_manager', 'Аккаунт'],
  ['payer', 'Плательщик'], ['deal_code', 'Сделка · стадия'], ['updated_at', 'Обновлён'], [null, 'Действия', true],
]
const capHead = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap' }
const EMPTY_SEL = { agency_id: [], advertiser_id: [], brand_id: [], sales_rep_id: [], account_manager_id: [] }

const periodOptions = () => {
  const now = new Date(); const out = []
  for (let i = 0; i < 12; i++) { const d = new Date(now.getFullYear(), now.getMonth() - i, 1); const v = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; out.push({ value: v, label: v }) }
  return out
}

export default function MpRegistry() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [perms, setPerms] = useState({})
  const [isAdmin, setIsAdmin] = useState(false)
  const [vpop, setVpop] = useState(null)
  const [pdfBusy, setPdfBusy] = useState(null)
  const [downloading, setDownloading] = useState(false)   // оверлей 1c на время выгрузки

  // тулбар: поиск / период / фильтры; над таблицей — этап, «Мои», порядок, группы; внизу — страницы
  const [search, setSearch] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [periodOpen, setPeriodOpen] = useState(false)
  const [sel, setSel] = useState(EMPTY_SEL)
  const [bucket, setBucket] = useState('all')
  const [mine, setMine] = useState(false)
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('desc')
  const [grouped, setGrouped] = useState(true)
  const [toggled, setToggled] = useState({})     // месяц → свёрнут/развёрнут вопреки умолчанию
  const [size, setSize] = useState(100)
  const [page, setPage] = useState(0)
  const [openRows, setOpenRows] = useState({})   // id → раскрыта
  const [details, setDetails] = useState({})     // id → { status, data } — план для расхлопа, грузится один раз
  const [meta, setMeta] = useState({ own_only: false, can_edit_locked: false, buckets: [] })

  // справочники для пикеров
  const [agencies, setAgencies] = useState([])
  const [advertisers, setAdvertisers] = useState([])
  const [brandsByAdv, setBrandsByAdv] = useState({})
  const [advCps, setAdvCps] = useState({})
  const [agencyCps, setAgencyCps] = useState({})
  const [sellers, setSellers] = useState([])
  const [accounts, setAccounts] = useState([])

  const canEdit = isAdmin || can(perms, 'media_plans', 'edit')
  const canCreate = isAdmin || can(perms, 'media_plans_editor', 'edit')
  const canDelete = canDeleteRight(perms, 'media_plans')

  // Сбой — не «Медиапланов нет» (аудит 23.09.2026, 7.M5): `.catch(() => {})` оставлял
  // пустой список с приглашением создать первый медиаплан. Фоновая перечитка — тихая.
  const [err, setErr] = useState('')
  const load = useCallback(({ quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    api.get('/sales/media-plans', auth())
      .then(r => {
        setItems(r.data.items || []); setErr('')
        setMeta({ own_only: !!r.data.own_only, can_edit_locked: !!r.data.can_edit_locked, buckets: r.data.buckets || [] })
      })
      .catch(e => { if (!isAuth(e)) setErr(errText(e)) })
      .finally(() => setLoading(false))
  }, [])

  // Вернулись на вкладку или пришли «Назад» из карточки — перечитать реестр. Без этого
  // экран показывает снимок, сделанный при открытии: переименовали медиаплан в карточке,
  // вернулись — и видите старое имя (13.09.2026).
  useRefreshOnReturn(() => load({ quiet: true }))

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
    const admin = isAdminFn()
    setPerms(p); setIsAdmin(admin)
    if (!admin && !can(p, 'media_plans', 'view')) { router.push(firstAllowedHref(p, admin)); return }
    load()
    // Справочники — из ОТКРЫТЫХ эндпоинтов (аккаунт-кабинет не требует прав продаж).
    api.get('/sales/directories/brands', auth()).then(r => { const m = {}; (r.data.items || []).forEach(b => { (m[b.advertiser_id] = m[b.advertiser_id] || []).push({ value: b.id, label: b.name }) }); setBrandsByAdv(m) }).catch(() => {})
    api.get('/sales/directories/producers', auth()).then(r => { const items = r.data.items || []; setAdvertisers(items.map(a => ({ value: a.id, label: a.short_name || a.name }))); const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); setAdvCps(m) }).catch(() => {})
    api.get('/sales/directories/agencies', auth()).then(r => { const items = r.data.items || []; setAgencies(items.map(a => ({ value: a.id, label: a.short_name }))); const m = {}; items.forEach(a => { m[a.id] = (a.counterparties || []).map(c => ({ value: c.counterparty_id, label: c.name })) }); setAgencyCps(m) }).catch(() => {})
    const mapStaff = (r) => (r.data.items || []).map(u => ({ value: u.id, label: u.name + (u.is_master ? ' ★' : '') }))
    api.get('/sales/directories/staff?group=seller&only_active=true', auth()).then(r => setSellers(mapStaff(r))).catch(() => {})
    api.get('/sales/directories/staff?group=account&only_active=true', auth()).then(r => setAccounts(mapStaff(r))).catch(() => {})
  }, [])

  // Опции фильтров — из значений, реально присутствующих в списке.
  const distinct = (idKey, labelKey) => {
    const m = new Map()
    items.forEach(it => { if (it[idKey] != null) m.set(it[idKey], it[labelKey] || '—') })
    return [...m].map(([value, label]) => ({ value, label })).sort((a, b) => String(a.label).localeCompare(String(b.label), 'ru'))
  }
  // «Стадия сделки» из тулбара ушла в чипы этапов над таблицей (хендофф §1).
  const DROPS = [
    ['agency_id', 'Агентство', distinct('agency_id', 'agency')],
    ['advertiser_id', 'Рекламодатель', distinct('advertiser_id', 'advertiser')],
    ['brand_id', 'Бренд', distinct('brand_id', 'brand')],
    ['sales_rep_id', 'Продавец', distinct('sales_rep_id', 'sales_rep')],
    ['account_manager_id', 'Аккаунт', distinct('account_manager_id', 'account_manager')],
  ]
  const filters = useMemo(() => ({ q: search, from: dateFrom, to: dateTo, sel, bucket, mine }), [search, dateFrom, dateTo, sel, bucket, mine])
  const activeFilters = Object.values(sel).some(a => a.length) || dateFrom || dateTo || search.trim() || bucket !== 'all' || mine
  const counts = useMemo(() => bucketCounts(items, filters), [items, filters])
  const mineCount = useMemo(() => items.filter(i => i.mine).length, [items])
  const rows = useMemo(() => filterRows(items, filters), [items, filters])
  const current = monthMsk()
  const isClosed = (k) => (toggled[k] != null ? toggled[k] : closedByDefault(k, current))
  const view = pageView(rows, { grouped, current, sortKey, dir: sortDir, page, size, isClosed })

  // Любая смена набора или порядка — на первую страницу: иначе человек остаётся на «странице 4» другого списка.
  useEffect(() => { setPage(0) }, [search, dateFrom, dateTo, sel, bucket, mine, sortKey, sortDir, grouped, size])
  // Выпадашка периода закрывается кликом вне неё (портал и триггер помечены data-pop-root).
  useEffect(() => {
    if (!periodOpen) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setPeriodOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [periodOpen])

  const onSort = (k) => { if (sortKey === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortKey(k); setSortDir('desc') } }
  const resetFilters = () => { setSel(EMPTY_SEL); setDateFrom(''); setDateTo(''); setSearch(''); setBucket('all'); setMine(false) }

  // Видимая ширина таблицы — для расхлопа и заголовков месяцев, которые держатся на месте при прокрутке вбок.
  // `100cqw` включает полосу прокрутки, и они уезжали на её ширину; меряем `clientWidth`.
  const scroller = useRef(null)
  useEffect(() => {
    const el = scroller.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const put = () => el.style.setProperty('--mpr-vw', `${el.clientWidth}px`)
    put()
    const ro = new ResizeObserver(put)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const loadDetail = (id) => {
    setDetails(d => ({ ...d, [id]: { status: 'loading' } }))
    api.get(`/sales/media-plans/${id}`, auth())
      .then(r => setDetails(d => ({ ...d, [id]: { status: 'ok', data: r.data } })))
      .catch(() => setDetails(d => ({ ...d, [id]: { status: 'error' } })))
  }
  const toggleRow = (id) => {
    setOpenRows(o => ({ ...o, [id]: !o[id] }))
    if (!details[id] || details[id].status === 'error') loadDetail(id)
  }

  const patchCell = async (id, patch, localApply) => {
    try {
      await api.patch(`/sales/media-plans/${id}`, patch, auth())
      setItems(prev => prev.map(x => x.id === id ? { ...x, ...localApply } : x))
      // Раскрытый план показывает шапку — перечитать, иначе в расхлопе осталось бы старое значение.
      if (openRows[id]) loadDetail(id); else setDetails(d => { const n = { ...d }; delete n[id]; return n })
      return true
    }
    catch (e) { alert(detailText(e, 'Не удалось сохранить')); return false }
  }
  const lbl = (opts, v) => (opts || []).find(o => String(o.value) === String(v))?.label

  const openPicker = (field, it, e) => {
    if (!canEdit) return
    const rect = e.currentTarget.getBoundingClientRect()
    const cfg = {
      agency: { title: 'Агентство', options: agencies, value: it.agency_id, clearLabel: '— прямой договор —',
        // плательщик привязан к агентству → при смене агентства сбрасываем его
        apply: (v) => patchCell(it.id, { agency_id: v, payer_counterparty_id: null }, { agency_id: v, agency: lbl(agencies, v) || null, payer_counterparty_id: null, payer: null }) },
      advertiser: { title: 'Рекламодатель', options: advertisers, value: it.advertiser_id, clearLabel: '— не указан —',
        apply: (v) => patchCell(it.id, { advertiser_id: v, brand_id: null }, { advertiser_id: v, advertiser: lbl(advertisers, v) || null, brand_id: null, brand: null }) },
      brand: { title: 'Бренд', options: brandsByAdv[it.advertiser_id] || [], value: it.brand_id, clearLabel: '— не указан —',
        apply: (v) => patchCell(it.id, { brand_id: v }, { brand_id: v, brand: lbl(brandsByAdv[it.advertiser_id], v) || null }),
        onAddNew: it.advertiser_id ? async (name) => {
          try {
            const r = await api.post('/sales/directories/brands', { name, advertiser_id: it.advertiser_id }, auth())
            setBrandsByAdv(m => ({ ...m, [it.advertiser_id]: [...(m[it.advertiser_id] || []), { value: r.data.id, label: name }] }))
            patchCell(it.id, { brand_id: r.data.id }, { brand_id: r.data.id, brand: name }); setVpop(null)
          } catch (e) { alert(detailText(e, 'Не удалось создать бренд')) }
        } : undefined },
      period: { title: 'Период', options: periodOptions(), value: it.period, clearLabel: '— не указан —',
        apply: (v) => patchCell(it.id, { period: v }, { period: v }) },
      seller: { title: 'Продавец', options: sellers, value: it.sales_rep_id, clearLabel: '— не назначен —',
        apply: (v) => patchCell(it.id, { sales_rep_id: v }, { sales_rep_id: v, sales_rep: (lbl(sellers, v) || '').replace(' ★', '') || null }) },
      account: { title: 'Аккаунт', options: accounts, value: it.account_manager_id, clearLabel: '— не назначен —',
        apply: (v) => patchCell(it.id, { account_manager_id: v }, { account_manager_id: v, account_manager: (lbl(accounts, v) || '').replace(' ★', '') || null }) },
      payer: { title: 'Контрагент (плательщик)', value: it.payer_counterparty_id, clearLabel: '— не указан —',
        options: it.agency_id ? (agencyCps[it.agency_id] || []) : (advCps[it.advertiser_id] || []),
        apply: (v) => { const src = it.agency_id ? agencyCps[it.agency_id] : advCps[it.advertiser_id]; patchCell(it.id, { payer_counterparty_id: v }, { payer_counterparty_id: v, payer: lbl(src, v) || null }) } },
    }[field]
    if (!cfg) return
    setVpop({ rect, dealLabel: `МП #${it.id}`, ...cfg })
  }

  const saveTitle = (id, t) => patchCell(id, { title: t }, { title: t })

  /* Название медиаплана собирается ТЕМ ЖЕ модулем, что имя сделки (lib/dealTitle.js), и
     той же кнопкой. Раньше имя плана собирал только конструктор, по своей маске — без
     услуги и через « · », — а в реестре его можно было лишь править руками.
     Услуга и поверхность приходят строкой плана (их считает сервер из его же строк). */
  const [serviceDir, setServiceDir] = useState([])
  useEffect(() => { api.get('/sales/directories/services?only_active=true', auth())
    .then(r => setServiceDir(r.data.items || [])).catch(() => {}) }, [])
  const separate = useMemo(() => separatePriceSet(serviceDir), [serviceDir])
  const genTitle = async (it) => {
    const t = buildTitle({ ...it, separate })
    if (!t) { alert(TITLE_EMPTY_HINT); return }
    if (t === (it.title || '')) return
    await patchCell(it.id, { title: t }, { title: t })
  }

  const del = async (it) => {
    if (!confirm(`Удалить медиаплан «${it.title || it.id}» со всеми версиями?`)) return
    try { await api.delete(`/sales/media-plans/${it.id}?whole_group=true`, auth()); load() } catch (e) { alert('Ошибка удаления') }
  }
  const exportXlsx = async (it) => {
    setDownloading(true)
    try { await downloadMp(it, 'xlsx') } finally { setDownloading(false) }
  }
  const downloadPdf = async (it) => {
    setPdfBusy(it.id); setDownloading(true)
    try { await downloadMp(it, 'pdf') } finally { setPdfBusy(null); setDownloading(false) }
  }

  const headCell = (key, label, right) => {
    const on = key && sortKey === key
    return (
      <span key={label} onClick={key ? () => onSort(key) : undefined} title={key ? `Сортировать: ${label.toLowerCase()}` : undefined}
        className={key ? 'mpr-sort' : undefined}
        style={{ ...capHead, display: 'flex', alignItems: 'center', justifyContent: right ? 'flex-end' : 'flex-start', gap: 4, height: '100%',
          color: on ? 'var(--accent-fg)' : 'var(--text-cap)', cursor: key ? 'pointer' : 'default', background: 'var(--bg-card)' }}>
        {label}<span style={{ fontSize: 10 }}>{on ? (sortDir === 'desc' ? '↓' : '↑') : ''}</span>
      </span>
    )
  }
  const countLabel = rows.length !== items.length ? `${rows.length} / ${items.length}` : String(items.length)
  const tb = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 13px', boxSizing: 'border-box', background: 'var(--bg-card)',
    border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }

  return (
    <>
      <Head><title>Медиапланы · Аккаунты | SIMB-AD ERP</title></Head>
      {downloading && <DownloadOverlay />}
      <Navbar active="" />
      {/* Строки и липкая первая колонка: фон наследует строку — обычная, под курсором и раскрытая. */}
      <style>{`
        .mpr-row, .mpr-row .mpr-stick { background: var(--bg-card); transition: background 150ms ease }
        .mpr-row:hover, .mpr-row:hover .mpr-stick, .mpr-open, .mpr-open .mpr-stick { background: var(--bg-subtle) }
        .mpr-row .mpr-gen { display: none } .mpr-row:hover .mpr-gen { display: inline-flex }
        .mpr-sort:hover { color: var(--accent-fg) !important }
        @keyframes mprOpen { from { opacity: 0; transform: translateY(-4px) } to { opacity: 1; transform: none } }
        @keyframes mprPulse { 0%, 100% { opacity: .55 } 50% { opacity: 1 } }
        @media (prefers-reduced-motion: reduce) { .mpr-row, .mpr-row * { animation-duration: 1ms !important; transition: none !important } }
      `}</style>
      {/* Таблица занимает остаток окна и прокручивается сама — так держатся её шапка и низ со страницами (хендофф §7). */}
      <div style={{ height: 'calc(100vh - var(--navbar-h))', boxSizing: 'border-box', padding: '22px 26px', display: 'flex', flexDirection: 'column', gap: 12,
        background: 'var(--bg-canvas)', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em', margin: 0, color: 'var(--text-primary)' }}>Медиапланы</h1>
          <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>{countLabel}</span>
          {canCreate && <button onClick={() => router.push('/accounts/mp/new')} style={{ ...primaryBtn, marginLeft: 'auto' }}>+ Новый медиаплан</button>}
        </div>

        {/* Тулбар: поиск · период · фильтры · сброс — как на проде */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ flex: '0 0 auto', width: searchFocus ? 300 : 160, display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, boxSizing: 'border-box',
            border: `1px solid ${searchFocus ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '0 10px',
            transition: 'width .22s cubic-bezier(0.22,1,0.36,1), border-color .15s' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>⌕</span>
            <input value={search} onChange={e => setSearch(e.target.value)} onFocus={() => setSearchFocus(true)} onBlur={() => setSearchFocus(false)}
              placeholder="поиск: название, код, контрагент…" style={{ flex: 1, minWidth: 0, width: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 12.5, color: 'inherit', fontFamily: UI }} />
          </div>
          <span data-pop-root style={{ display: 'inline-flex' }}>
            <button type="button" onClick={() => setPeriodOpen(o => !o)}
              style={{ ...tb, fontFamily: MONO, fontSize: 11.5, borderColor: (dateFrom || dateTo || periodOpen) ? 'var(--accent)' : 'var(--border-card)',
                background: (dateFrom || dateTo) ? 'var(--accent-tint)' : 'var(--bg-card)', color: (dateFrom || dateTo) ? 'var(--accent-fg)' : 'var(--text-muted)' }}>
              {(dateFrom || dateTo) ? `${dateFrom || '…'} — ${dateTo || '…'}` : 'период'} ▾
            </button>
            <PortalPopover open={periodOpen} minWidth={250}>
              <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MonthInput clearable value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                  <span style={{ color: 'var(--text-muted)' }}>—</span>
                  <MonthInput clearable value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                </div>
                {(dateFrom || dateTo) && <div onClick={() => { setDateFrom(''); setDateTo('') }} style={{ fontSize: 12, color: 'var(--accent-fg)', cursor: 'pointer' }}>Сбросить период</div>}
              </div>
            </PortalPopover>
          </span>
          {DROPS.map(([k, label, opts]) => (
            <MultiDrop key={k} label={label} options={opts} selected={sel[k]} onChange={v => setSel(s => ({ ...s, [k]: v }))} />
          ))}
          {activeFilters && <button type="button" onClick={resetFilters} title="Сбросить фильтры" style={{ ...tb, color: 'var(--text-muted)' }}>Сбросить ✕</button>}
        </div>

        {/* Этапы и «Мои» | порядок и группы */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <StageChips buckets={meta.buckets} counts={counts} value={bucket} onPick={setBucket} />
          {/* У роли с областью «свои» переключатель не нужен — у неё и так только свои. */}
          {!meta.own_only && <Toggle on={mine} label="Мои" n={mineCount} title="Планы, где вы продавец, аккаунт или трафик" onClick={() => setMine(m => !m)} />}
          <SortBlock sortKey={sortKey} dir={sortDir} onSort={k => { if (k !== sortKey) { setSortKey(k); setSortDir('desc') } }}
            onDir={() => setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))} />
          <Toggle on={grouped} label="По месяцам" title="Разбить список по месяцу периода размещения" onClick={() => setGrouped(g => !g)} />
        </div>

        {!!err && <LoadError text={err} onRetry={() => load()} />}
        <div style={{ ...card, flex: '1 1 auto', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div ref={scroller} style={{ flex: '1 1 auto', minHeight: 0, overflow: 'auto', containerType: 'inline-size' }}>
            <div style={{ minWidth: TABLE_MIN_W }}>
              {/* шапка — липкая сверху; первая колонка — липкая слева */}
              <div style={{ position: 'sticky', top: 0, zIndex: 4, display: 'grid', gridTemplateColumns: GRID, alignItems: 'center', gap: '0 10px', height: 40,
                paddingRight: 14, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-inner)', boxShadow: '0 1px 0 var(--border-inner)' }}>
                <span style={{ ...capHead, position: 'sticky', left: 0, zIndex: 2, display: 'flex', alignItems: 'center', gap: 8, height: '100%', paddingLeft: 14,
                  paddingRight: 10, background: 'var(--bg-card)', boxShadow: '1px 0 0 var(--border-inner)', color: 'var(--text-cap)' }}>
                  <span style={{ flex: '0 0 14px' }} />
                  <span style={{ flex: '0 0 64px', display: 'flex' }}>{headCell('id', 'ID')}</span>
                  {headCell('title', 'Сделка')}
                </span>
                {HEAD.map(([k, label, right]) => headCell(k, label, right))}
              </div>

              {loading ? (
                <div style={{ position: 'sticky', left: 0, width: 'var(--mpr-vw, 100cqw)', padding: 40, boxSizing: 'border-box', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
              ) : view.entries.map(e => (e.type === 'group'
                ? <GroupHead key={`g${e.key}${e.continued ? 'c' : ''}`} g={e} buckets={meta.buckets}
                    onToggle={() => setToggled(t => ({ ...t, [e.key]: !isClosed(e.key) }))} />
                : (
                  <div key={e.item.id}>
                    <RegistryRow it={e.item} open={!!openRows[e.item.id]} onToggle={() => toggleRow(e.item.id)}
                      cellsOpen={cellsOpen(e.item, meta.can_edit_locked)} canEditLocked={meta.can_edit_locked}
                      canEdit={canEdit} canDelete={canDelete} pdfBusy={pdfBusy === e.item.id}
                      onPick={openPicker} onSaveTitle={t => saveTitle(e.item.id, t)} onGenTitle={() => genTitle(e.item)}
                      onOpenPlan={() => router.push(`/accounts/mp/${e.item.id}`)} onExcel={() => exportXlsx(e.item)}
                      onPdf={() => downloadPdf(e.item)} onDelete={() => del(e.item)} />
                    {!!openRows[e.item.id] && <RowDetail it={e.item} detail={details[e.item.id]} onRetry={() => loadDetail(e.item.id)} />}
                  </div>
                )))}
              {!loading && !rows.length && (
                <div style={{ position: 'sticky', left: 0, width: 'var(--mpr-vw, 100cqw)', padding: '40px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
                  {err && !items.length ? 'Реестр не загрузился — см. сообщение выше' : items.length ? 'Ничего не найдено — измените фильтры' : 'Медиапланов нет — нажмите «+ Новый медиаплан»'}
                </div>
              )}
            </div>
          </div>
          <RegistryFooter view={view} size={size} onSize={setSize} onPage={setPage} />
        </div>
      </div>

      {vpop && <ValuePopover anchor={vpop.rect} title={vpop.title} dealLabel={vpop.dealLabel} options={vpop.options} value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
        onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />}
    </>
  )
}
