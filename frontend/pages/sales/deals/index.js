import { useState, useEffect, useRef, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can } from '@/components/Navbar'
import DealCreateForm from '@/components/DealCreateForm'
import DealDetail from '@/components/sales/DealDetail'
import DealBriefCell from '@/components/DealBriefCell'
import MoveDealDialog from '@/components/sales/MoveDealDialog'
import ValuePopover from '@/components/ValuePopover'
import api, { auth } from '@/lib/api'
import { DownloadOverlay } from '@/components/LogoLoader'
import { fmtMoney, fmtDate, mln } from '@/lib/salesFormat'
import { BITRIX_DEAL_URL } from '@/lib/salesLayers'
import { MONO, UI, PIP, FILL, HATCH, HATCH_RED, FILTER_DROPS, GAP_FIELDS, shortLabel, MultiDrop, IconBtn, StageLayerBar, DEAL_COLS, DEAL_DEFAULT_HIDDEN, DEAL_COL_BY_KEY, DEAL_MIDDLE_KEYS, ColumnsMenu, tagSm as chip, needsMp, needsMpCheck, NEEDS_MP_BG, NEEDS_MP_BORDER, UNVERIFIED_BG, UNVERIFIED_BORDER } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
import { overlayClose } from '@/lib/overlay'
const DealCardList = dynamic(() => import('@/components/mobile/DealCardList'), { ssr: false })
const DealsMobileControls = dynamic(() => import('@/components/sales/DealsMobileControls'), { ssr: false })
const BottomSheet = dynamic(() => import('@/components/mobile/BottomSheet'), { ssr: false })

// Фильтр «Продавец» — только в реестре (в дашборде смысла нет, там лишь свои сделки),
// поэтому не в общий FILTER_DROPS, а локально. Ставим рядом с «Аккаунтом» по смыслу.
const REG_FILTER_DROPS = FILTER_DROPS.flatMap(fd => fd[0] === 'account_manager_id' ? [['sales_rep_id', 'Продавец'], fd] : [fd])

// Описание колонок: ширина + подпись. brief/gen — фиксированные (не скрываются).
// Светофор вероятности сделки (наша ручная разметка): цвет лампы по вероятности.
const PROB_COLORS = { grey: 'var(--muted)', orange: 'var(--warning, #d97706)', green: 'var(--success)' }
const PROB_ORDER = ['grey', 'orange', 'green']
const PROB_LABEL = { grey: 'малая', orange: 'средняя', green: 'высокая' }

// Колонки — из общего шаблона salesTableKit (DEAL_COLS): реестр и дашборд
// настраиваются как один внешний шаблон. Служебный префикс (prob/sel/brief) —
// фиксированный, в меню «Колонки» не участвует и задаётся тут локально.
const FIXED_COLS = { prob: { key: 'prob', w: '26px' }, sel: { key: 'sel', w: '52px' }, brief: { key: 'brief', w: '46px' } }
const COLS = DEAL_COLS
const DEFAULT_HIDDEN = DEAL_DEFAULT_HIDDEN
const COLS_KEY = 'sr3_hidden_cols'
const COLS_ORDER_KEY = 'sr3_col_order'
const COL_BY_KEY = DEAL_COL_BY_KEY
const MIDDLE_KEYS = DEAL_MIDDLE_KEYS   // переставляемые/скрываемые

export default function SalesRegistry2() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [perms, setPerms] = useState({})
  const canEdit = can(perms, 'sales_registry', 'edit')
  // права под конкретные действия (бэк требует разные секции)
  const canDirAg = can(perms, 'dir_agencies', 'edit')
  const canDirAdv = can(perms, 'dir_advertisers', 'edit')
  const isAdmin = typeof window !== 'undefined' && localStorage.getItem('role') === 'admin'

  const [deals, setDeals] = useState([])
  const [dealsTotal, setDealsTotal] = useState(0)
  const [probPick, setProbPick] = useState(null)   // {dealId, rect} — пикер светофора вероятности
  const [moveDeal, setMoveDeal] = useState(null)   // сделка в диалоге движения по каталогу
  const [offset, setOffset] = useState(0)
  const [summary, setSummary] = useState(null)
  const [pageSize, setPageSize] = useState(100)
  const [sortKey, setSortKey] = useState('date_create')
  const [sortDir, setSortDir] = useState('desc')
  // массовое редактирование + чекбоксы
  const [selDeals, setSelDeals] = useState({})   // { dealId: true }
  const [lastIdx, setLastIdx] = useState(null)   // якорь Shift-выделения
  const [bulkForm, setBulkForm] = useState({ advertiser_id: '', agency_id: '', sales_rep_id: '', account_manager_id: '', product: '', our_stage_id: '', period: '' })
  const [saving, setSaving] = useState(false)
  const selDealIds = Object.keys(selDeals).map(Number)

  const [sel, setSel] = useState(Object.fromEntries(REG_FILTER_DROPS.map(([k]) => [k, []])))
  const [gaps, setGaps] = useState([])
  const [hideArchive, setHideArchive] = useState(true)
  const [onlyPlanned, setOnlyPlanned] = useState(false)   // показывать только сделки из годового плана
  const [search, setSearch] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [periodOpen, setPeriodOpen] = useState(false)

  const [fopts, setFopts] = useState({})
  const [serviceDir, setServiceDir] = useState([])   // справочник услуг (sort_order) — для списков услуг
  const [expandedId, setExpandedId] = useState(null) // раскрытая строка-детализация сделки
  const [brandsByAdv, setBrandsByAdv] = useState({})
  const [vpop, setVpop] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createMenuOpen, setCreateMenuOpen] = useState(false)   // мобильная модалка «Создать» (+Агентство/+Рекламодатель/+Сделка)
  const [entityModal, setEntityModal] = useState(null) // 'agency' | 'advertiser'
  const [entForm, setEntForm] = useState({})
  const [entSaving, setEntSaving] = useState(false)

  const openAgency = () => { setEntForm({ short_name: '', name_en: '', name_ru: '', holding: '' }); setEntityModal('agency') }
  const openAdvertiser = () => { setEntForm({ short_name: '', name_en: '', name_ru: '', website: '', inn: '' }); setEntityModal('advertiser') }
  const saveEntity = async () => {
    const f = entForm
    if (!(f.short_name || '').trim() && !(f.name_en || '').trim() && !(f.name_ru || '').trim()) { alert('Укажите хотя бы одно название'); return }
    setEntSaving(true)
    try {
      await api.post(entityModal === 'agency' ? '/sales/directories/agencies' : '/sales/directories/producers', f, auth())
      setEntityModal(null)
      api.get('/sales/filters', auth()).then(r => setFopts(r.data || {})).catch(() => {})  // обновляем опции пикеров
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось создать') }
    finally { setEntSaving(false) }
  }
  const [editTitleId, setEditTitleId] = useState(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [hidden, setHidden] = useState(new Set(DEFAULT_HIDDEN))   // скрытые колонки (Колонки ▾)
  const [colOrder, setColOrder] = useState(MIDDLE_KEYS) // порядок переставляемых колонок
  const [colPicker, setColPicker] = useState(false)
  const [periodEdit, setPeriodEdit] = useState(null) // { dealId, rect, month } — правка периода строки
  const [genConfirm, setGenConfirm] = useState(null) // { dealId, rect, text, current } — подтверждение генерации имени
  const [syncingId, setSyncingId] = useState(null)   // id сделки в процессе синхронизации из Битрикса
  const [syncResult, setSyncResult] = useState(null) // { deal, changes, files, warnings } — попап результата
  const [bulkResult, setBulkResult] = useState(null) // сводка массовой синхронизации
  const [syncBulkBusy, setSyncBulkBusy] = useState(false) // кубик-оверлей на время конвеера
  const [syncProgress, setSyncProgress] = useState(null)  // { done, total } для прогресс-бара
  const [pushPreview, setPushPreview] = useState(null) // превью/результат заливки правок в Битрикс
  const [pushBusy, setPushBusy] = useState(false)
  const [advConfirm, setAdvConfirm] = useState(null) // подтверждение смены рекламодателя со сбросом бренда

  // Смена периода сделки: только при изменении; period_from = 1-е число выбранного месяца.
  const savePeriod = async (dealId, month, current) => {
    setPeriodEdit(null)
    if (!month || month === current) return
    await patchCell(dealId, { period_from: `${month}-01` }, { period: month, period_from: `${month}-01` })
  }

  useEffect(() => {
    try { const s = JSON.parse(localStorage.getItem(COLS_KEY)); if (Array.isArray(s)) setHidden(new Set(s)) } catch (e) {}
    try {
      const o = JSON.parse(localStorage.getItem(COLS_ORDER_KEY))
      if (Array.isArray(o) && o.length) {
        const valid = o.filter(k => COL_BY_KEY[k] && !COL_BY_KEY[k].fixed)
        setColOrder([...valid, ...MIDDLE_KEYS.filter(k => !valid.includes(k))])   // новые ключи — в конец
      }
    } catch (e) {}
  }, [])
  const toggleColHidden = (k) => setHidden(prev => {
    const next = new Set(prev); next.has(k) ? next.delete(k) : next.add(k)
    localStorage.setItem(COLS_KEY, JSON.stringify([...next])); return next
  })
  const reorderCol = (from, to) => setColOrder(prev => {
    const next = [...prev]; const [moved] = next.splice(from, 1); next.splice(to, 0, moved)
    localStorage.setItem(COLS_ORDER_KEY, JSON.stringify(next)); return next
  })
  // чекбокс (при праве) → бриф → переставленные видимые колонки (генерация — внутри «Сделка»).
  const visibleCols = [FIXED_COLS.prob, canEdit ? FIXED_COLS.sel : null, FIXED_COLS.brief, ...colOrder.map(k => COL_BY_KEY[k]).filter(c => c && !hidden.has(c.key))].filter(Boolean)
  const gridTemplate = visibleCols.map(c => c.w).join(' ')
  const isMobile = useIsMobile()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [mobView, setMobView] = useState('cards')     // мобильный вид: карточки | таблица
  const [mobSearchOpen, setMobSearchOpen] = useState(false)
  const activeFilterCount = Object.values(sel).filter(a => a.length).length + (gaps.length ? 1 : 0) + ((dateFrom || dateTo) ? 1 : 0) + (searchQ.trim() ? 1 : 0)
  const loadMoreMobile = () => { const ns = pageSize + 100; setPageSize(ns); load(0, ns) }

  // Выгрузка текущей выборки в CSV (клиентская).
  const exportCsv = () => {
    const head = ['Код', 'Агентство', 'Рекламодатель', 'Бренд', 'Услуга', 'Период', 'Стадия', 'Сумма', 'Аккаунт', 'Контрагент', 'Слой', 'Сделка']
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = deals.map(d => [d.code || d.bitrix_id, d.agency, d.advertiser, d.brand, d.product, d.period, d.bitrix_stage, d.amount, d.account_manager, d.payer, d.money_layer, d.title].map(esc).join(';'))
    const csv = '﻿' + head.map(esc).join(';') + '\n' + lines.join('\n')
    const url = window.URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = `deals_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url)
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) {}
    api.get('/sales/filters', auth()).then(r => setFopts(r.data || {})).catch(() => {})
    api.get('/sales/brands-by-advertiser', auth()).then(r => setBrandsByAdv(r.data || {})).catch(() => {})
    // Справочник услуг (в порядке sort_order) — источник для всех выпадающих списков услуг.
    api.get('/sales/directories/services?only_active=true', auth()).then(r => setServiceDir(r.data.items || [])).catch(() => {})
  }, [])

  // Опции услуг для пикеров/фильтра/bulk: справочник в заданном порядке, плюс «сироты»
  // — значения product из существующих сделок, которых нет в справочнике (не теряем их).
  const productOpts = (() => {
    const dir = serviceDir.map(s => ({ value: s.name, label: s.name }))
    const known = new Set(dir.map(o => o.value))
    const orphans = (fopts.product || []).filter(o => o && !known.has(o.value))
    return [...dir, ...orphans]
  })()

  // Опции для МАССОВОЙ смены стадии — НАША лестница (id + имя, с этапом в подписи).
  // Раньше тут были имена стадий Битрикса, и в bitrix_stage сделки могло утечь
  // составное значение фильтра, плодя стадии-двойники. Теперь правится our_stage_id —
  // числовой ключ каталога, утекать нечему.
  const stageEditOpts = (fopts.our_stage_id || []).map(o => ({
    value: o.value, label: o.group ? `${o.group} · ${o.label}` : o.label,
  }))

  const buildBase = () => {
    const b = new URLSearchParams()
    Object.entries(sel).forEach(([k, arr]) => arr.forEach(v => b.append(k, v)))
    gaps.forEach(g => b.append('gaps', g))
    if (hideArchive) b.append('hide_archive', 'true')
    if (onlyPlanned) b.append('only_planned', 'true')
    if (searchQ.trim()) b.append('search', searchQ.trim())
    if (dateFrom) b.append('date_from', dateFrom)
    if (dateTo) b.append('date_to', dateTo)
    return b
  }
  const loadSeq = useRef(0)
  const load = async (newOffset = 0, size = pageSize) => {
    const seq = ++loadSeq.current            // защита от гонки: применяем только последний запрос
    setLoading(true); setErr('')
    const base = buildBase()
    const dq = new URLSearchParams(base)
    dq.append('limit', String(size)); dq.append('offset', String(newOffset)); dq.append('sort', sortKey); dq.append('direction', sortDir)
    const sumq = new URLSearchParams(base); sumq.append('scope_section', 'sales_registry')
    try {
      const [reg, sum] = await Promise.all([api.get('/sales/deals?' + dq.toString(), auth()), api.get('/sales/dashboard?' + sumq.toString(), auth())])
      if (seq !== loadSeq.current) return     // пришёл устаревший ответ — игнорируем
      setDeals(reg.data.items || []); setDealsTotal(reg.data.total || 0); setOffset(newOffset); setSummary(sum.data)
    } catch (e) { if (seq !== loadSeq.current) return; if (e.response?.status === 401) return router.push('/login'); setErr(e.response?.data?.detail || 'Не удалось загрузить') }
    finally { if (seq === loadSeq.current) setLoading(false) }
  }

  // фильтры/сортировка → перезагрузка с 1-й страницы (дебаунс 300 мс)
  useEffect(() => { const t = setTimeout(() => load(0), 300); return () => clearTimeout(t) }, [sel, gaps, hideArchive, onlyPlanned, searchQ, dateFrom, dateTo, sortKey, sortDir])

  // Диплинк из справочника (счётчик сделок): ?producer_id / ?agency_id — ставим фильтр
  // и показываем в т.ч. архивные (иначе часть сделок не видна). producer_id вместо
  // advertiser_id — иначе блокировщики рекламы режут ссылку по подстроке "advertiser".
  useEffect(() => {
    if (!router.isReady) return
    const advId = router.query.producer_id, agId = router.query.agency_id
    if (advId || agId) {
      setSel(s => ({ ...s, ...(advId ? { advertiser_id: [Number(advId)] } : {}), ...(agId ? { agency_id: [Number(agId)] } : {}) }))
      setHideArchive(false)
    }
  }, [router.isReady])
  useEffect(() => { const t = setTimeout(() => setSearchQ(search), 300); return () => clearTimeout(t) }, [search])
  useEffect(() => { setLastIdx(null) }, [deals])

  // ── массовое редактирование ──
  const toggleRow = (i, id, shift) => {
    setSelDeals(prev => {
      const next = { ...prev }
      if (shift && lastIdx != null && deals[lastIdx]) {
        const a = Math.min(lastIdx, i), b = Math.max(lastIdx, i), target = !prev[id]
        for (let k = a; k <= b; k++) { const rid = deals[k] && deals[k].id; if (rid == null) continue; if (target) next[rid] = true; else delete next[rid] }
      } else if (next[id]) { delete next[id] } else { next[id] = true }
      return next
    })
    setLastIdx(i)
  }
  const applyBulk = async () => {
    const body = { deal_ids: selDealIds }; let any = false
    const STR = ['product', 'period']
    for (const [k, v] of Object.entries(bulkForm)) {
      if (v === '__clear__') { body[k] = null; any = true }
      else if (v !== '' && v !== null) { body[k] = STR.includes(k) ? v : Number(v); any = true }
    }
    // Стадия — только простое имя: срезаем возможный составной ключ "воронка\x1fстадия".
    if (!any) { setErr('Заполните хотя бы одно поле для изменения'); return }
    setSaving(true); setErr('')
    try {
      const r = await api.post('/sales/deals/bulk-update', body, auth())
      alert(r.data.message); setSelDeals({}); setBulkForm({ advertiser_id: '', agency_id: '', sales_rep_id: '', account_manager_id: '', product: '', our_stage_id: '', period: '' }); load(offset)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось применить') } finally { setSaving(false) }
  }
  const deleteBulk = async () => {
    if (!window.confirm(`Удалить ${selDealIds.length} сделок? Действие необратимо.`)) return
    setSaving(true); setErr('')
    try { const r = await api.post('/sales/deals/bulk-delete', { deal_ids: selDealIds }, auth()); alert(r.data.message); setSelDeals({}); load(offset) }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось удалить') } finally { setSaving(false) }
  }
  const syncDeals = async () => { try { await api.post('/sales/sync', {}, auth()); load(offset) } catch (e) { setErr(e.response?.data?.detail || 'Синхронизация недоступна') } }
  const importDeals = async () => {
    try {
      const pv = (await api.post('/sales/reconcile/import-deals?commit=0', {}, auth())).data
      if (!pv.to_insert) { alert('Свежих сделок нет — всё уже загружено.'); return }
      if (!window.confirm(`Найдено ${pv.to_insert} свежих сделок${pv.skipped_untracked ? ` (пропущено вне воронок: ${pv.skipped_untracked})` : ''}.\nИмпортировать?`)) return
      const res = (await api.post('/sales/reconcile/import-deals?commit=1', {}, auth())).data
      alert(`Импортировано: ${res.inserted} сделок.`); load(offset)
    } catch (e) { setErr(e.response?.data?.detail || 'Импорт недоступен') }
  }
  const btnAcc = { background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 14px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }
  // кнопки в строке меню разделов — высота как у вкладок (padding 6×14)
  const tabBtn = (acc) => ({ padding: '6px 14px', borderRadius: 8, border: acc ? 'none' : '1px solid var(--border-card)', cursor: 'pointer', fontWeight: acc ? 700 : 600, fontSize: 13, whiteSpace: 'nowrap', fontFamily: acc ? MONO : UI, background: acc ? 'var(--accent)' : 'var(--bg-subtle)', color: acc ? '#fff' : 'var(--text-secondary)' })
  // Контурная кнопка: белый фон + синий контур (для «+ Агентство» / «+ Рекламодатель»)
  const tabBtnOutline = { padding: '6px 14px', borderRadius: 8, border: '1px solid var(--accent)', cursor: 'pointer', fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap', fontFamily: MONO, background: 'var(--bg-card)', color: 'var(--accent)' }
  const btnSec = { background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 13px', fontFamily: UI, fontSize: 13, fontWeight: 600, cursor: 'pointer' }
  const bulkInp = { padding: '7px 9px', border: '1px solid var(--border-card)', borderRadius: 8, fontSize: 12.5, background: 'var(--bg-card)', color: 'inherit', fontFamily: UI }

  const onSort = (k, sortable) => { if (!sortable) return; if (sortKey === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortKey(k); setSortDir('desc') } }
  const resetFilters = () => { setSel(Object.fromEntries(REG_FILTER_DROPS.map(([k]) => [k, []]))); setGaps([]); setHideArchive(true); setOnlyPlanned(false); setSearch(''); setSearchQ(''); setDateFrom(''); setDateTo('') }

  const patchCell = async (id, patch, localApply) => {
    try { await api.patch(`/sales/deals/${id}`, patch, auth()); setDeals(prev => prev.map(x => x.id === id ? { ...x, ...localApply } : x)); return true }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить'); return false }
  }
  const openPicker = (field, d, e) => {
    if (!canEdit) return
    const rect = e.currentTarget.getBoundingClientRect()
    const cfg = {
      agency: { title: 'Агентство', options: fopts.agency_id, value: d.agency_id, clearLabel: '— прямой договор —', apply: (v) => { const f = (fopts.agency_id || []).find(o => String(o.value) === String(v))?.label; patchCell(d.id, { agency_id: v }, { agency_id: v, agency: shortLabel(f) }) } },
      advertiser: { title: 'Рекламодатель', options: fopts.advertiser_id, value: d.advertiser_id, clearLabel: '— не указан —',
        apply: (v) => {
          const f = (fopts.advertiser_id || []).find(o => String(o.value) === String(v))?.label
          const reset = d.brand_id && String(v ?? '') !== String(d.advertiser_id ?? '')
          if (reset) { setAdvConfirm({ dealId: d.id, advId: v, full: f, advName: shortLabel(f), brandName: d.brand }); return }
          patchCell(d.id, { advertiser_id: v }, { advertiser_id: v, advertiser: shortLabel(f), advertiser_full: f })
        } },
      brand: { title: 'Бренд', options: brandsByAdv[d.advertiser_id] || [], value: d.brand_id, clearLabel: '— не указан —',
        apply: (v) => { const l = (brandsByAdv[d.advertiser_id] || []).find(o => String(o.value) === String(v))?.label; patchCell(d.id, { brand_id: v }, { brand_id: v, brand: l || null }) },
        onAddNew: d.advertiser_id ? async (name) => {
          try {
            const r = await api.post('/sales/directories/brands', { name, advertiser_id: d.advertiser_id }, auth())
            const id = r.data.id
            setBrandsByAdv(m => ({ ...m, [d.advertiser_id]: [...(m[d.advertiser_id] || []), { value: id, label: name }].sort((a, b) => String(a.label).localeCompare(String(b.label), 'ru')) }))
            patchCell(d.id, { brand_id: id }, { brand_id: id, brand: name }); setVpop(null)
          } catch (e) { alert(e.response?.data?.detail || 'Не удалось создать бренд') }
        } : undefined },
      service: { title: 'Услуга', options: productOpts.map(o => ({ value: o.value, label: o.label || o.value })), value: d.product, apply: (v) => patchCell(d.id, { product: v }, { product: v }) },
    }[field]
    if (!cfg) return
    setVpop({ rect, dealLabel: `сделка ${d.bitrix_id}`, ...cfg })
  }
  const templateTitle = (d) => [d.advertiser, d.brand, d.agency, d.product, d.period].filter(v => v != null && String(v).trim() !== '').join(' | ')
  const saveTitle = async (id, title) => { try { await api.patch(`/sales/deals/${id}`, { title }, auth()); setDeals(prev => prev.map(x => x.id === id ? { ...x, title } : x)) } catch (e) { alert('Не удалось сохранить название') } }
  const setProbability = async (id, color) => {
    setProbPick(null)
    const prev = deals.find(x => x.id === id)?.probability_color ?? null
    setDeals(ps => ps.map(x => x.id === id ? { ...x, probability_color: color } : x))
    try { await api.post(`/sales/deals/${id}/probability`, { color }, auth()) }
    catch (e) { setDeals(ps => ps.map(x => x.id === id ? { ...x, probability_color: prev } : x)); alert('Не удалось сохранить вероятность') }
  }

  // ── синхронизация одной сделки из Битрикса (кнопка ⟳ в строке) ──
  const syncDeal = async (d) => {
    setSyncingId(d.id)
    try {
      const r = await api.post(`/sales/deals/${d.id}/sync-from-bitrix`, {}, auth())
      setSyncResult({ deal: d, ...r.data })
      load(offset)
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка синхронизации') }
    finally { setSyncingId(null) }
  }
  // Массовая синхронизация выбранных сделок
  // Конвеер на клиенте: последовательно синхронизируем выбранные (пер-сделочный эндпоинт),
  // обновляя прогресс «X из N» после каждой. Так виден живой прогресс и где отвалилось.
  const syncBulk = async () => {
    const ids = selDealIds.slice(0, 50)   // кап 50 за раз
    if (!ids.length) return
    const dmap = Object.fromEntries(deals.map(d => [d.id, d]))
    const acc = { green: 0, blue: 0, red: 0, errors: 0, skipped: 0, done: 0, total: ids.length, failed: [] }
    setSaving(true); setSyncBulkBusy(true); setSyncProgress({ done: 0, total: ids.length })
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i]; const d = dmap[id]
      if (d && String(d.bitrix_id || '').startsWith('local-')) { acc.skipped++; setSyncProgress({ done: i + 1, total: ids.length }); continue }
      try {
        const r = await api.post(`/sales/deals/${id}/sync-from-bitrix`, {}, { ...auth(), timeout: 0 })
        const st = r.data && r.data.status
        if (st && acc[st] != null) acc[st]++
        acc.done++
      } catch (e) {
        acc.errors++
        acc.failed.push({ id, title: (d && d.title) || ('#' + id), error: e.response?.data?.detail || 'ошибка синхронизации' })
      }
      setSyncProgress({ done: i + 1, total: ids.length })
    }
    setSaving(false); setSyncBulkBusy(false); setSyncProgress(null)
    setBulkResult(acc); setSelDeals({}); load(offset)
  }
  // «Залить правки в Битрикс» — превью (commit=0) → подтверждение → запись (commit=1)
  const PUSH_FIELD_LABELS = { title: 'Название', advertiser_id: 'Рекламодатель', brand_id: 'Бренд', agency_id: 'Агентство', sales_rep_id: 'Продавец', account_manager_id: 'Аккаунт', payer_counterparty_id: 'Контрагент', period_from: 'Старт РК', period_to: 'Конец РК', product: 'Услуга', bitrix_stage: 'Стадия' }
  const openPushEdits = async () => {
    setPushBusy(true)
    try { const r = await api.post('/sales/push-edits?commit=0', {}, auth()); setPushPreview(r.data) }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось получить превью') }
    finally { setPushBusy(false) }
  }
  const confirmPushEdits = async () => {
    setPushBusy(true)
    try { const r = await api.post('/sales/push-edits?commit=1', {}, auth()); setPushPreview(p => ({ ...p, done: r.data })); load(offset) }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка заливки в Битрикс') }
    finally { setPushBusy(false) }
  }
  // Клик по светофору — детали последней синхронизации из сохранённого отчёта
  const openSyncReport = (d) => setSyncResult({
    deal: d, bitrix_id: d.bitrix_id, readonly: true, changes: {}, files: [],
    issues: d.sync_issues || [], warnings: (d.sync_issues || []).map(i => i.message),
    checked_at: d.sync_checked_at,
  })
  // Скачивание сохранённого файла через blob (эндпоинт под Bearer-токеном)
  const downloadDealFile = async (dealId, kind, filename) => {
    try {
      const r = await api.get(`/sales/deals/${dealId}/files/${kind}/download`, { ...auth(), responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = filename || 'file'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось скачать файл') }
  }
  const SYNC_LABELS = { amount: 'Сумма до НДС', amount_with_vat: 'Сумма с НДС', sales_rep_id: 'Продавец', account_manager_id: 'Аккаунт', advertiser_id: 'Рекламодатель', brand_id: 'Бренд', period_from: 'Старт РК' }
  // Действия карточки-детализации (раскрытие строки). Открыть — в Битрикс; правка и
  // загрузка МП — заглушки (доработаем).
  const openDeal = (d) => { if (d.bitrix_id && !String(d.bitrix_id).startsWith('local-')) window.open(BITRIX_DEAL_URL(d.bitrix_id), '_blank') }
  const editDeal = () => alert('Редактирование сделки — скоро')
  const addMp = (d) => router.push(`/accounts/mp/new?deal=${d.id}`)

  const FILE_LABEL = { mp: 'МП', contract: 'Договор' }
  const ISSUE_LABELS = { advertiser: 'Рекламодатель', brand: 'Бренд', sales_rep: 'Продавец', account_manager: 'Аккаунт', mp: 'МП', contract: 'Договор' }
  // Светофор синхронизации: зелёный — совпадает, синий — мы полнее, красный — расхождение.
  const SYNC_DOT = {
    green: ['var(--income)', 'Синхронизировано: совпадает с Битриксом'],
    blue: ['var(--accent)', 'У нас данные полнее — ещё не выгружено в Битрикс'],
    red: ['var(--dot-overdue)', 'Расхождение с Битриксом (разные справочники) — проверьте'],
  }
  const ATTN_COLS = new Set(['advertiser', 'brand', 'sales_rep', 'account_manager'])
  const renderSyncDot = (d) => {
    const status = d.sync_status
    const m = SYNC_DOT[status]
    if (!m) return <span title="Синхронизация ещё не проверялась" style={{ width: 9, height: 9, borderRadius: 2, border: '1px solid var(--text-faint)', boxSizing: 'border-box', flex: '0 0 9px' }} />
    return <span onClick={e => { e.stopPropagation(); openSyncReport(d) }} title={m[1] + ' · клик — детали'}
      style={{ width: 9, height: 9, borderRadius: 2, background: m[0], flex: '0 0 9px', cursor: 'pointer' }} />
  }

  const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

  // Ячейка строки по ключу колонки (для итерации по видимым колонкам).
  const cellFor = (key, d) => {
    const none = !FILL[d.money_layer]; const n = FILL[d.money_layer] || 0
    switch (key) {
      case 'prob': {
        const col = PROB_COLORS[d.probability_color]
        return (
          <button onClick={e => { e.stopPropagation(); if (canEdit) setProbPick({ dealId: d.id, rect: e.currentTarget.getBoundingClientRect() }) }}
            title={d.probability_color ? `Вероятность: ${PROB_LABEL[d.probability_color]}` : 'Вероятность не задана'}
            style={{ display: 'inline-block', width: 14, height: 14, borderRadius: '50%', border: col ? 'none' : '1.5px solid var(--border-card)', background: col || 'transparent', cursor: canEdit ? 'pointer' : 'default', padding: 0 }} />
        )
      }
      case 'sel': return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          {canEdit && <input type="checkbox" checked={!!selDeals[d.id]} readOnly onClick={e => { e.stopPropagation(); toggleRow(deals.indexOf(d), d.id, e.shiftKey) }} title="Shift+клик — диапазон" style={{ cursor: 'pointer' }} />}
          <button onClick={e => { e.stopPropagation(); router.push(`/sales/deals/${d.id}`) }} title="Открыть карточку сделки"
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 20, height: 20, padding: 0, border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 6, color: 'var(--accent)', cursor: 'pointer', fontSize: 12, lineHeight: 1 }}>↗</button>
        </span>
      )
      case 'brief': return (
        <span className="d2-brief" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <DealBriefCell deal={d} canEdit={canEdit} v2 />
          {renderSyncDot(d)}
        </span>
      )
      case 'bitrix_id': {
        const isLocal = String(d.bitrix_id || '').startsWith('local-')
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <a href={`/sales/deals/${encodeURIComponent(d.code || d.id)}`} title="Открыть карточку сделки"
              style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>{d.code || '—'}</a>
            {isLocal
              ? (canEdit && <button onClick={e => { e.stopPropagation(); api.post(`/sales/deals/${d.id}/push-to-bitrix`, {}, auth()).then(() => load(offset)).catch(er => alert(er.response?.data?.detail || 'Ошибка')) }} title="Отправить в Битрикс"
                  style={{ border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-faint)', borderRadius: 5, cursor: 'pointer', fontSize: 9, padding: '1px 4px', fontFamily: MONO }}>→БХ</button>)
              : (canEdit && <span onClick={e => { e.stopPropagation(); syncingId !== d.id && syncDeal(d) }} title="Обновить из Битрикса (поля + файлы)"
                  style={{ cursor: syncingId === d.id ? 'default' : 'pointer', fontSize: 12, lineHeight: 1, color: syncingId === d.id ? 'var(--text-faint)' : 'var(--accent)' }}>{syncingId === d.id ? '⏳' : '⟳'}</span>)}
          </span>
        )
      }
      case 'agency': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('agency', d, e)} style={{ fontWeight: 600 }} title={d.agency_full || d.agency || 'выбрать'}>{d.agency ?? '—'}</span>
      case 'advertiser': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('advertiser', d, e)} title={d.advertiser_full || d.advertiser || 'выбрать'}>{d.advertiser ?? '—'}</span>
      case 'brand': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('brand', d, e)} title={d.brand || 'выбрать'}>{d.brand ?? '—'}</span>
      case 'product': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('service', d, e)} style={{ color: 'var(--text-secondary)' }} title={d.product || 'выбрать'}>{d.product ?? '—'}</span>
      case 'period': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => { if (canEdit) setPeriodEdit({ dealId: d.id, rect: e.currentTarget.getBoundingClientRect(), month: d.period || '', current: d.period }) }}
        style={{ fontFamily: MONO, color: 'var(--text-secondary)' }} title={canEdit ? 'Изменить период (месяц старта РК)' : undefined}>{d.period ?? '—'}</span>
      case 'bitrix_stage': {
        const os = d.our_stage
        return (
          <span className={canEdit ? 'd2-cell' : ''} onClick={e => { e.stopPropagation(); if (canEdit) setMoveDeal(d) }}
            title={canEdit ? 'Двинуть сделку' : (os?.name || '')}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: canEdit ? 'pointer' : 'default', overflow: 'hidden' }}>
            {os ? (<>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-primary)', flex: '1 1 auto', minWidth: 0 }}>{os.name}</span>
              <StageLayerBar os={os} />
              {canEdit && <span style={{ color: 'var(--accent)', fontWeight: 700, flex: '0 0 auto' }}>▸</span>}
            </>) : <span style={{ color: 'var(--text-faint)' }}>{canEdit ? '— двинуть —' : '—'}</span>}
          </span>
        )
      }
      case 'amount': return <span style={{ fontFamily: MONO, fontWeight: 700, textAlign: 'right' }} title={d.amount != null ? new Intl.NumberFormat('ru-RU').format(d.amount) + ' ₽' : ''}>{fmtMoney(d.amount)}</span>
      case 'account_manager': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.account_manager ?? '—'}</span>
      case 'payer': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.payer}>{d.payer ?? '—'}</span>
      case 'money_layer': { const lost = /провал|не случил|отказ/i.test(d.bitrix_stage || ''); return <span style={{ display: 'flex', gap: 2 }} title={none ? (lost ? 'Сделка провалена' : 'Без группы — требует разбора') : `${d.money_layer} · слой денег`}>{PIP.map((c, i) => <span key={i} style={{ width: 9, height: 14, borderRadius: 2, background: none ? (lost ? HATCH_RED : HATCH) : (i < n ? c : 'var(--border-inner)') }} />)}</span> }
      case 'pipeline': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.pipeline}>{d.pipeline ?? '—'}</span>
      case 'sales_rep': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.sales_rep ?? '—'}</span>
      case 'period_from': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{d.period_from ? fmtDate(d.period_from) : '—'}</span>
      case 'period_to': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{d.period_to ? fmtDate(d.period_to) : '—'}</span>
      case 'files': {
        const fs = d.files || []; const ours = d.our_mps || []
        if (!fs.length && !ours.length) return <span style={{ color: 'var(--text-faint)' }}>—</span>
        return <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 3, alignItems: 'flex-start' }}>
          {fs.map(f => (
            <span key={f.kind} onClick={e => { e.stopPropagation(); downloadDealFile(d.id, f.kind, f.filename) }}
              title={f.filename || ''} style={chip({ border: '1px solid var(--accent)', color: 'var(--accent)' })}>
              ⭳ {f.kind === 'mp' ? 'МП · Битрикс' : (FILE_LABEL[f.kind] || f.kind)}
            </span>
          ))}
          {ours.map(m => (
            <span key={'mp' + m.id} onClick={e => { e.stopPropagation(); router.push(`/accounts/mp/${m.id}`) }}
              title={(m.title || 'Медиаплан') + ' · ' + (m.status || '')} style={chip({ border: '1px solid var(--income)', color: 'var(--income)', background: 'var(--income-tint)' })}>
              ↗ наш МП v{m.version}
            </span>
          ))}
        </span>
      }
      case 'title': {
        if (editTitleId === d.id) return <input autoFocus value={titleDraft} onChange={e => setTitleDraft(e.target.value)} onBlur={() => { saveTitle(d.id, titleDraft); setEditTitleId(null) }} onKeyDown={e => { if (e.key === 'Enter') { saveTitle(d.id, titleDraft); setEditTitleId(null) } else if (e.key === 'Escape') setEditTitleId(null) }} style={{ width: '100%', minWidth: 0, padding: '3px 6px', fontSize: 12, border: '1px solid var(--accent)', borderRadius: 6, outline: 'none', fontFamily: UI }} />
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            <span onDoubleClick={() => canEdit && (setEditTitleId(d.id), setTitleDraft(d.title || ''))} title={canEdit ? 'Двойной клик — правка' : d.title} style={{ flex: 1, minWidth: 0, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title || '—'}</span>
            {canEdit && (
              <span className="d2-gen" title="Сгенерировать название" onClick={e => { e.stopPropagation(); const t = templateTitle(d); if (!t) { alert('Нечего собрать: нет рекламодателя / бренда / агентства / услуги / периода.'); return } setGenConfirm({ dealId: d.id, rect: e.currentTarget.getBoundingClientRect(), text: t, current: d.title }) }}
                style={{ flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 8, color: 'var(--text-muted)', cursor: 'pointer' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" style={stroke}><path d="M5 3v4" /><path d="M3 5h4" /><path d="M17 15v4" /><path d="M15 17h4" /><path d="M12.5 4.5l1.9 4.6 4.6 1.9-4.6 1.9-1.9 4.6-1.9-4.6L6 11l4.6-1.9z" /></svg>
              </span>
            )}
          </div>
        )
      }
      default: return <span />
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head>
        <title>Реестр сделок</title>
      </Head>
      <Navbar active="sales" />
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        .d2-row:hover { background: var(--bg-subtle) !important; }
        .d2-cell { cursor:pointer; border-radius:6px; display:block; box-sizing:border-box;
          /* Кликом должна ловиться ВСЯ ячейка, а не строка текста в ней: по ширине
             грид-элемент растягивается сам, по высоте — нет (align-items:center),
             и у пустого поля мишенью оставался только прочерк. Вертикальные отступы
             с обратными полями добирают высоту строки, не сдвигая содержимое. */
          padding:8px 4px; margin:-8px -4px; width:calc(100% + 8px);
          overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .d2-cell:hover { background: var(--accent-tint); color: var(--accent); }
        .d2-gen:hover, .d2-ico:hover { border-color:#C7D0E8 !important; color:var(--accent) !important; }
        @media (prefers-reduced-motion: reduce) { [style*="animation"] { animation:none !important } }
      `}</style>

      {vpop && <ValuePopover anchor={vpop.rect} title={vpop.title} dealLabel={vpop.dealLabel} options={vpop.options} value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
        onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />}
      {probPick && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }} onClick={() => setProbPick(null)} />
        <div style={{ position: 'fixed', zIndex: 61, left: Math.min(probPick.rect.left, window.innerWidth - 160), top: Math.min(probPick.rect.bottom + 6, window.innerHeight - 70),
          background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)', padding: 8, display: 'flex', gap: 8, alignItems: 'center', fontFamily: UI }}>
          {PROB_ORDER.map(c => (
            <button key={c} onClick={() => setProbability(probPick.dealId, c)} title={PROB_LABEL[c]}
              style={{ width: 22, height: 22, borderRadius: '50%', border: '1px solid var(--border-card)', background: PROB_COLORS[c], cursor: 'pointer', padding: 0 }} />
          ))}
          <span onClick={() => setProbability(probPick.dealId, null)} title="Снять" style={{ cursor: 'pointer', color: 'var(--text-faint)', fontSize: 14, marginLeft: 2 }}>✕</span>
        </div>
      </>)}
      {moveDeal && <MoveDealDialog deal={moveDeal} onClose={() => setMoveDeal(null)}
        onMoved={(upd) => { setDeals(prev => prev.map(x => x.id === moveDeal.id ? { ...x, ...upd } : x)); setMoveDeal(null) }} />}
      {periodEdit && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }} onClick={() => setPeriodEdit(null)} />
        <div style={{ position: 'fixed', zIndex: 61, left: Math.min(periodEdit.rect.left, window.innerWidth - 248), top: Math.min(periodEdit.rect.bottom + 6, window.innerHeight - 130),
          background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)', padding: 12, width: 232, fontFamily: UI, animation: 'riseIn .22s cubic-bezier(0.22,1,0.36,1) both' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Период размещения</div>
          <input type="month" autoFocus defaultValue={periodEdit.month}
            onChange={e => savePeriod(periodEdit.dealId, e.target.value, periodEdit.current)}
            style={{ width: '100%', boxSizing: 'border-box', padding: '7px 9px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 13, outline: 'none', fontFamily: MONO }} />
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>Старт РК станет 1-м числом выбранного месяца.</div>
        </div>
      </>)}
      {entityModal && (
        <div {...overlayClose(() => setEntityModal(null))} style={{ position: 'fixed', inset: 0, zIndex: 70, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, width: 'min(440px, 96vw)', padding: '20px 22px', boxShadow: 'var(--shadow-card, 0 24px 64px rgba(28,36,51,0.22))', fontFamily: UI }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 14 }}>{entityModal === 'agency' ? 'Новое агентство' : 'Новый рекламодатель'}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                ['short_name', 'Краткое название'],
                ['name_en', 'Название ENG'],
                ['name_ru', 'Название РУС'],
                ...(entityModal === 'agency' ? [['holding', 'Холдинг (необязательно)']] : [['website', 'Сайт'], ['inn', 'ИНН']]),
              ].map(([k, ph], i) => (
                <input key={k} autoFocus={i === 0} placeholder={ph} value={entForm[k] || ''}
                  onChange={e => setEntForm(f => ({ ...f, [k]: e.target.value }))}
                  onKeyDown={e => { if (e.key === 'Enter') saveEntity() }}
                  style={{ width: '100%', boxSizing: 'border-box', padding: '9px 11px', borderRadius: 10, border: '1px solid var(--border-card)', fontSize: 13, outline: 'none', fontFamily: UI }} />
              ))}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', margin: '10px 0 4px' }}>Нужно хотя бы одно название. Появится в выпадашках сразу после создания.</div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 12 }}>
              <button onClick={() => setEntityModal(null)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'inherit', borderRadius: 10, cursor: 'pointer', fontSize: 13, padding: '8px 14px' }}>Отмена</button>
              <button onClick={saveEntity} disabled={entSaving} style={{ border: 'none', background: 'var(--accent)', color: '#fff', borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 700, padding: '8px 16px' }}>{entSaving ? 'Создание…' : 'Создать'}</button>
            </div>
          </div>
        </div>
      )}
      {advConfirm && (
        <div {...overlayClose(() => setAdvConfirm(null))} style={{ position: 'fixed', inset: 0, zIndex: 72, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, width: 'min(440px, 94vw)', padding: '20px 22px', boxShadow: 'var(--shadow-card, 0 24px 64px rgba(28,36,51,0.22))', fontFamily: UI }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>Сменить рекламодателя?</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 18 }}>
              Бренд <b>«{advConfirm.brandName}»</b> будет сброшен — он относится к текущему рекламодателю
              и не принадлежит выбранному{advConfirm.advName ? <> <b>«{advConfirm.advName}»</b></> : null}.
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setAdvConfirm(null)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'inherit', borderRadius: 10, cursor: 'pointer', fontSize: 13, padding: '8px 14px' }}>Отмена</button>
              <button onClick={() => { const c = advConfirm; setAdvConfirm(null); patchCell(c.dealId, { advertiser_id: c.advId }, { advertiser_id: c.advId, advertiser: c.advName, advertiser_full: c.full, brand_id: null, brand: null }) }}
                style={{ border: 'none', background: 'var(--danger)', color: '#fff', borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 700, padding: '8px 16px' }}>Сменить и сбросить бренд</button>
            </div>
          </div>
        </div>
      )}
      {genConfirm && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }} onClick={() => setGenConfirm(null)} />
        <div style={{ position: 'fixed', zIndex: 61, width: 300, right: Math.max(8, window.innerWidth - genConfirm.rect.right),
          ...(genConfirm.rect.bottom + 150 > window.innerHeight ? { bottom: window.innerHeight - genConfirm.rect.top + 6 } : { top: genConfirm.rect.bottom + 6 }),
          background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 12, fontFamily: UI, animation: 'riseIn .22s cubic-bezier(0.22,1,0.36,1) both' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Новое название{genConfirm.current ? ' (заменит текущее)' : ''}:</div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', marginBottom: 10, wordBreak: 'break-word' }}>{genConfirm.text}</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setGenConfirm(null)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'inherit', borderRadius: 8, cursor: 'pointer', fontSize: 13, padding: '6px 12px' }}>Отмена</button>
            <button onClick={() => { const g = genConfirm; setGenConfirm(null); saveTitle(g.dealId, g.text) }} style={{ border: 'none', background: 'var(--accent)', color: '#fff', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, padding: '6px 12px' }}>Заменить</button>
          </div>
        </div>
      </>)}

      <div style={{ padding: isMobile ? 14 : 24 }}>
        {/* Шапка страницы: заголовок со счётчиком слева, действия справа.
            Раньше слева стояло меню раздела (SalesTabs) — оно уехало в шапку приложения,
            и без левого элемента кнопки прижимались к краю, а отступ снизу давали сами табы. */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: isMobile ? 12 : 18 }}>
          {!isMobile ? (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Список сделок</span>
              <span style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>{dealsTotal}</span>
            </div>
          ) : <span />}
          {(canEdit || canDirAg || canDirAdv || isAdmin) && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {canDirAg && !isMobile && <button onClick={openAgency} style={tabBtnOutline}>+ Агентство</button>}
              {canDirAdv && !isMobile && <button onClick={openAdvertiser} style={tabBtnOutline}>+ Рекламодатель</button>}
              {canEdit && !isMobile && <button onClick={() => setCreateOpen(true)} style={tabBtn(true)}>+ Сделка</button>}
              {canEdit && !isMobile && <button onClick={openPushEdits} disabled={pushBusy} title="Залить наши ручные правки в Битрикс24" style={tabBtn(false)}>{pushBusy ? '…' : '↑ Залить правки'}</button>}
              {isAdmin && !isMobile && <button onClick={importDeals} style={tabBtn(false)}>Импорт</button>}
            </div>
          )}
        </div>
        <DealCreateForm open={createOpen} onClose={() => setCreateOpen(false)} canPickRep onCreated={() => load(0)} />
        {/* мобильная модалка «Создать» (как на дашборде сейлза) */}
        {isMobile && (
          <BottomSheet open={createMenuOpen} onClose={() => setCreateMenuOpen(false)} title="Создать">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {canDirAg && <button onClick={() => { setCreateMenuOpen(false); openAgency() }} style={{ width: '100%', background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: 12, padding: '14px', fontFamily: UI, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>+ Агентство</button>}
              {canDirAdv && <button onClick={() => { setCreateMenuOpen(false); openAdvertiser() }} style={{ width: '100%', background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: 12, padding: '14px', fontFamily: UI, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>+ Рекламодатель</button>}
              {canEdit && <button onClick={() => { setCreateMenuOpen(false); setCreateOpen(true) }} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontFamily: UI, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>+ Сделка</button>}
            </div>
          </BottomSheet>
        )}

        {err && <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div>}

        {/* Полоса портфеля — как «Сделки в работе» в виджете дашборда */}
        {summary?.totals && (() => {
          const total = summary.totals.amount || 0
          const amt = (name) => (summary.by_layer || []).find(b => b.name === name)?.amount || 0
          const cnt = (name) => (summary.by_layer || []).find(b => b.name === name)?.deals || 0
          const LAYERS = [
            { name: 'фактические', bg: 'var(--income)' }, { name: 'реализуемые', bg: 'var(--dot-current-dz)' },
            { name: 'планируемые', bg: 'var(--text-faint)' }, { name: 'Без группы', bg: HATCH },
          ]
          const recon = summary.totals.reconciles
          return (
            <div style={{ position: 'relative', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)', padding: isMobile ? '14px 16px' : '18px 22px', marginBottom: isMobile ? 12 : 14, display: 'flex', alignItems: isMobile ? 'stretch' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 12 : 36, flexWrap: 'wrap' }}>
              {isMobile && canEdit && (
                <button onClick={() => setCreateMenuOpen(true)} aria-label="Создать" style={{ position: 'absolute', top: 16, right: 16, width: 44, height: 44, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, fontSize: 26, lineHeight: 1, cursor: 'pointer', zIndex: 1 }}>+</button>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 180 }}>
                <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Всего в реестре</span>
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
                  <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: 'var(--text-primary)' }}>{mln(total)}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)' }}>млн ₽ / {summary.totals.deals} шт</span>
                </span>
              </div>
              <div style={{ flex: 1, minWidth: isMobile ? 0 : 320, display: 'flex', flexDirection: 'column', gap: isMobile ? 8 : 10 }}>
                <div style={{ display: 'flex', gap: 2, height: 10 }}>
                  {LAYERS.map(L => { const w = total > 0 ? amt(L.name) / total * 100 : 0; return w > 0 ? <div key={L.name} title={`${L.name}: ${mln(amt(L.name))} млн · ${cnt(L.name)}`} style={{ width: `${w}%`, background: L.bg }} /> : null })}
                </div>
                <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 7 : 24, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)' }}>
                  {LAYERS.map(L => (
                    <span key={L.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: L.bg }} />{L.name === 'Без группы' ? 'без группы' : L.name} <span style={{ marginLeft: isMobile ? 'auto' : 0, fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{mln(amt(L.name))} млн · {cnt(L.name)}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', color: recon ? 'var(--income)' : 'var(--danger)' }}>
                <span style={{ width: 7, height: 7, borderRadius: 999, background: recon ? 'var(--income)' : 'var(--danger)' }} />{recon ? 'сверка сходится' : 'сверка расходится'}
              </div>
            </div>
          )
        })()}

        {/* массовое редактирование выбранных */}
        {loading && !deals.length && <div style={{ color: 'var(--text-muted)', padding: 40 }}>Загрузка…</div>}

        {true && (
          <div>
              <div style={{ marginTop: 4 }}>
                {/* Заголовок «Список сделок» со счётчиком переехал в шапку страницы,
                    настройка колонок и выгрузка — в правую группу строки фильтров. */}

                {/* массовое редактирование выбранных — под заголовком, в одну строку */}
                {canEdit && selDealIds.length > 0 && (
                  <div style={{ marginBottom: 12, background: 'var(--bg-card)', border: '1px solid var(--accent)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: '10px 14px', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>Выбрано: {selDealIds.length}</span>
                    {(() => {
                      const W = { flexShrink: 0, width: 132, maxWidth: 132, textOverflow: 'ellipsis' }
                      const bsel = (k, opt, ph, optsOverride) => <select style={{ ...bulkInp, ...W }} value={bulkForm[k]} onChange={e => setBulkForm({ ...bulkForm, [k]: e.target.value })}><option value="">{ph}</option>{(optsOverride || fopts[opt] || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                      return <>
                        {bsel('our_stage_id', 'our_stage_id', 'стадия —', stageEditOpts)}
                        {bsel('product', 'product', 'услуга —', productOpts)}
                        <input type="month" style={{ ...bulkInp, flexShrink: 0, width: 120 }} value={bulkForm.period} onChange={e => setBulkForm({ ...bulkForm, period: e.target.value })} />
                        {bsel('advertiser_id', 'advertiser_id', 'рекл. —')}
                        {bsel('agency_id', 'agency_id', 'агентство —')}
                        {bsel('sales_rep_id', 'sales_rep_id', 'продавец —')}
                        {bsel('account_manager_id', 'account_manager_id', 'аккаунт —')}
                      </>
                    })()}
                    <button onClick={applyBulk} disabled={saving} style={{ ...btnAcc, flexShrink: 0 }}>Применить</button>
                    <button onClick={syncBulk} disabled={saving} title="Синхронизировать выбранные из Битрикса (до 50 за раз)" style={{ ...btnSec, color: 'var(--accent)', borderColor: 'var(--accent)', flexShrink: 0 }}>{saving ? '…' : `⟳ Синхронизировать`}</button>
                    {selDealIds.length > 25 && <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }} title="Каждая сделка ≈ 6 сек">выбрано {selDealIds.length} — займёт ≈ {Math.ceil(selDealIds.length * 6 / 60)} мин</span>}
                    <button onClick={deleteBulk} disabled={saving} style={{ ...btnSec, color: 'var(--danger)', flexShrink: 0 }}>Удалить</button>
                    <button onClick={() => setSelDeals({})} style={{ ...btnSec, flexShrink: 0 }}>Сбросить</button>
                  </div>
                )}

                {/* карточка таблицы */}
                <div style={isMobile ? { display: 'flex', flexDirection: 'column', gap: 12 } : { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)', padding: '20px 24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>

                  {/* фильтры: мобильный тулбар+шторка (общий компонент) / десктопная строка */}
                  {isMobile ? (
                    <DealsMobileControls dealsTotal={dealsTotal} search={search} setSearch={setSearch} mobSearchOpen={mobSearchOpen} setMobSearchOpen={setMobSearchOpen}
                      mobView={mobView} setMobView={setMobView} filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} activeFilterCount={activeFilterCount}
                      sel={sel} setSel={setSel} gaps={gaps} setGaps={setGaps} dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
                      hideArchive={hideArchive} setHideArchive={setHideArchive} fopts={fopts} productOpts={productOpts} resetFilters={resetFilters} exportCsv={exportCsv} filterDrops={REG_FILTER_DROPS} />
                  ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <div style={{ flex: '0 0 auto', width: searchFocus ? 300 : 148, display: 'inline-flex', alignItems: 'center', gap: 7, border: `1px solid ${searchFocus ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '7px 10px', transition: 'width .22s cubic-bezier(0.22,1,0.36,1), border-color .15s' }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" style={{ ...stroke, strokeWidth: 2, flex: '0 0 13px', color: 'var(--text-faint)' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
                      <input value={search} onChange={e => setSearch(e.target.value)} onFocus={() => setSearchFocus(true)} onBlur={() => setSearchFocus(false)}
                        placeholder="код, агентство, рекл, бренд, контрагент…" title="Поиск: ID, агентство, рекламодатель, бренд, контрагент, название сделки"
                        style={{ border: 'none', outline: 'none', background: 'transparent', fontSize: 12, color: 'var(--text-secondary)', width: '100%', fontFamily: UI }} />
                    </div>
                    <div style={{ position: 'relative', flex: '0 0 auto' }}>
                      <div onClick={() => setPeriodOpen(o => !o)} title="Период размещения — выбрать диапазон месяцев"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: `1px solid ${(dateFrom || dateTo || periodOpen) ? 'var(--accent)' : 'var(--border-card)'}`, background: (dateFrom || dateTo) ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontFamily: MONO, fontSize: 11, color: (dateFrom || dateTo) ? 'var(--accent)' : 'var(--text-muted)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                        {(dateFrom || dateTo) ? `${dateFrom || '…'} — ${dateTo || '…'}` : 'период'} ▾
                      </div>
                      {periodOpen && (<>
                        <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setPeriodOpen(false)} />
                        <div style={{ position: 'absolute', top: '110%', left: 0, marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 12, display: 'flex', flexDirection: 'column', gap: 8, minWidth: 230 }}>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Период размещения (месяц старта РК)</div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                            <span style={{ color: 'var(--text-faint)' }}>—</span>
                            <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>Пусто = по выбранному кварталу.</div>
                          {(dateFrom || dateTo) && <div onClick={() => { setDateFrom(''); setDateTo('') }} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer' }}>Сбросить период</div>}
                        </div>
                      </>)}
                    </div>
                    {REG_FILTER_DROPS.map(([k, lbl]) => (
                      <MultiDrop key={k} label={lbl} options={k === 'product' ? productOpts : fopts[k]} selected={sel[k]} onChange={v => { setSel(s => ({ ...s, [k]: v })); if (k === 'bitrix_stage' && hideArchive && v.some(x => /архив/i.test(x))) setHideArchive(false) }} />
                    ))}
                    <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={gaps} onChange={setGaps} />
                    <div style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                      <IconBtn title={onlyPlanned ? 'Показаны только плановые — показать все' : 'Показать только плановые сделки (из годового плана)'} active={onlyPlanned} onClick={() => setOnlyPlanned(v => !v)}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18" /><path d="M8 2v4" /><path d="M16 2v4" /><path d="M8.5 14.5l2 2 4-4" /></svg>
                      </IconBtn>
                      <IconBtn title={hideArchive ? 'Архив скрыт — показать архивные' : 'Архив показан — скрыть'} active={hideArchive} onClick={() => setHideArchive(v => !v)}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M4 8h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><path d="M3 4h18v4H3z" /><path d="M10 12h4" /></svg>
                      </IconBtn>
                      <div className="d2-ico" title="Сбросить фильтры" onClick={resetFilters}
                        style={{ flex: '0 0 32px', width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 10, cursor: 'pointer', background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-muted)' }}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg>
                      </div>
                      {/* Настройка колонок и выгрузка — здесь же, за кнопкой сброса:
                          обе относятся к таблице, а не к странице. */}
                      <ColumnsMenu open={colPicker} setOpen={setColPicker} colOrder={colOrder} hidden={hidden} onToggle={toggleColHidden} onReorder={reorderCol} />
                      <div className="d2-ico" title="Скачать в CSV" onClick={exportCsv}
                        style={{ flex: '0 0 32px', width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 10, cursor: 'pointer', background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-muted)' }}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
                      </div>
                    </div>
                  </div>
                  )}

                  {/* таблица (десктоп) / карточки-таблица (мобайл) */}
                  {isMobile ? <DealCardList deals={deals} canEdit={canEdit} view={mobView} total={dealsTotal} onLoadMore={loadMoreMobile} fopts={fopts} onPatch={patchCell} /> : (
                  <div style={{ overflowX: 'auto' }}>
                    <div style={{ minWidth: 1180 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, padding: '0 0 10px', borderBottom: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                        {visibleCols.map(c => c.key === 'sel' ? (
                          <span key="sel" style={{ display: 'inline-flex', alignItems: 'center' }}>
                            <input type="checkbox" checked={deals.length > 0 && deals.every(r => selDeals[r.id])}
                              onChange={e => { if (e.target.checked) setSelDeals(Object.fromEntries(deals.map(r => [r.id, true]))); else setSelDeals({}) }}
                              title="Выбрать все на странице" style={{ cursor: 'pointer' }} />
                          </span>
                        ) : (
                          <span key={c.key} onClick={() => onSort(c.key, c.sortable)} style={{ textAlign: c.right ? 'right' : 'left', cursor: c.sortable ? 'pointer' : 'default', color: sortKey === c.key ? 'var(--accent)' : 'var(--text-faint)' }}>
                            {c.label}{sortKey === c.key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                          </span>
                        ))}
                      </div>

                      {deals.map(d => (
                        <Fragment key={d.id}>
                        <div className="d2-row" title={needsMp(d) ? 'Требует расчёта: медиаплана ещё нет'
                          : (needsMpCheck(d) ? 'Медиаплан не завизирован: откройте МП, отметьте «Проверено» и сохраните' : undefined)}
                          onClick={e => { if (e.target.closest('.d2-cell, .d2-gen, .d2-brief, input, select, button, a, textarea')) return; setExpandedId(x => x === d.id ? null : d.id) }}
                          style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: `1px solid ${needsMp(d) ? NEEDS_MP_BORDER : (needsMpCheck(d) ? UNVERIFIED_BORDER : 'var(--border-row)')}`, fontSize: 12, color: 'var(--text-primary)', cursor: 'pointer', background: (expandedId === d.id || selDeals[d.id]) ? 'var(--accent-tint)' : (needsMp(d) ? NEEDS_MP_BG : (needsMpCheck(d) ? UNVERIFIED_BG : undefined)) }}>
                          {visibleCols.map(c => {
                            const attn = ATTN_COLS.has(c.key) && (d.sync_issues || []).some(i => i.field === c.key)
                            return <Fragment key={c.key}>{attn
                              ? <span title="Расхождение с Битриксом — клик по светофору покажет детали" style={{ display: 'block', minWidth: 0, background: 'var(--danger-tint)', borderRadius: 5, boxShadow: 'inset 0 0 0 1px #F3C9CC', padding: '2px 4px' }}>{cellFor(c.key, d)}</span>
                              : cellFor(c.key, d)}</Fragment>
                          })}
                        </div>
                        {expandedId === d.id && <DealDetail deal={d} canEdit={canEdit} onOpen={openDeal} onEdit={editDeal} onAddMp={addMp} onChanged={() => load(offset)} />}
                        </Fragment>
                      ))}
                      {!deals.length && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет сделок по выбранным фильтрам</div>}
                    </div>
                  </div>
                  )}

                  {/* подвал */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', paddingTop: 14, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
                    <button onClick={() => load(Math.max(0, offset - pageSize))} disabled={offset === 0} style={{ ...btnSec, padding: '5px 11px', opacity: offset === 0 ? 0.5 : 1 }}>← Назад</button>
                    <span>{dealsTotal ? `${offset + 1}–${Math.min(offset + pageSize, dealsTotal)} из ${dealsTotal}` : '0'}</span>
                    <button onClick={() => load(offset + pageSize)} disabled={offset + pageSize >= dealsTotal} style={{ ...btnSec, padding: '5px 11px', opacity: offset + pageSize >= dealsTotal ? 0.5 : 1 }}>Вперёд →</button>
                    <span style={{ display: 'inline-flex', gap: 14, flexWrap: 'wrap' }}>
                      {[['фактические', 'var(--income)'], ['реализуемые', 'var(--dot-current-dz)'], ['планируемые', 'var(--text-faint)']].map(([l, c]) => (
                        <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                      ))}
                    </span>
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                      <span>строк на странице</span>
                      <span style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
                        {[50, 100, 300, 500].map(nn => (
                          <span key={nn} onClick={() => { setPageSize(nn); load(0, nn) }}
                            style={{ borderRadius: 8, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, fontWeight: pageSize === nn ? 700 : 600,
                              background: pageSize === nn ? 'var(--accent-tint)' : 'transparent', color: pageSize === nn ? 'var(--accent)' : 'var(--text-secondary)' }}>{nn}</span>
                        ))}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
          </div>
        )}

        {/* ── Попап результата синхронизации из Битрикса ── */}
        {syncResult && (
          <div {...overlayClose(() => setSyncResult(null))} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(20,26,40,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)', width: 440, maxWidth: '92vw', maxHeight: '82vh', overflowY: 'auto', padding: '20px 22px', fontFamily: UI }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{syncResult.readonly ? 'Синхронизация' : 'Обновлено из Битрикса'} · сделка {syncResult.bitrix_id}</span>
                <span onClick={() => setSyncResult(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>✕</span>
              </div>
              {syncResult.checked_at && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 12 }}>проверено {new Date(syncResult.checked_at).toLocaleString('ru-RU')}</div>}
              {!syncResult.readonly && (Object.keys(syncResult.changes || {}).length > 0 ? (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Обновлены поля ({Object.keys(syncResult.changes).length})</div>
                  {Object.keys(syncResult.changes).map(k => (
                    <div key={k} style={{ display: 'flex', gap: 8, fontSize: 13, padding: '3px 0' }}>
                      <span style={{ color: 'var(--income)' }}>✓</span>
                      <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{SYNC_LABELS[k] || k}</span>
                    </div>
                  ))}
                </div>
              ) : <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>Поля уже актуальны — изменений нет.</div>)}
              {syncResult.readonly && (syncResult.issues || []).length === 0 && <div style={{ fontSize: 13, color: 'var(--income)', marginBottom: 12 }}>✓ Данные совпадают с Битриксом.</div>}
              {(syncResult.files || []).length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Файлы</div>
                  {syncResult.files.map(f => (
                    <div key={f.kind} onClick={() => downloadDealFile(syncResult.deal.id, f.kind, f.filename)} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 0', cursor: 'pointer', color: 'var(--accent)' }}>
                      <span>⭳</span><span style={{ fontWeight: 600 }}>{FILE_LABEL[f.kind] || f.kind}</span>
                      <span style={{ color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.filename}</span>
                    </div>
                  ))}
                </div>
              )}
              {((syncResult.issues || []).length > 0 || (syncResult.warnings || []).length > 0) && (
                <div style={{ background: 'var(--warning-tint)', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: '#B26A0C', marginBottom: 5 }}>Расхождения / требует внимания</div>
                  {(syncResult.issues && syncResult.issues.length
                    ? syncResult.issues.map((it, i) => <div key={i} style={{ fontSize: 12.5, color: '#8a5209', padding: '2px 0' }}>• <b>{ISSUE_LABELS[it.field] || it.field}:</b> {it.message}</div>)
                    : syncResult.warnings.map((w, i) => <div key={i} style={{ fontSize: 12.5, color: '#8a5209', padding: '2px 0' }}>• {w}</div>))}
                </div>
              )}
            </div>
          </div>
        )}

        {syncBulkBusy && <DownloadOverlay label="Синхронизация сделок" progress={syncProgress} />}

        {/* ── Сводка массовой синхронизации ── */}
        {bulkResult && (
          <div {...overlayClose(() => setBulkResult(null))} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(20,26,40,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)', width: 360, maxWidth: '92vw', padding: '20px 22px', fontFamily: UI }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>Обработано {bulkResult.done != null ? bulkResult.done : (bulkResult.total - (bulkResult.skipped || 0) - (bulkResult.errors || 0))} из {bulkResult.total}</span>
                <span onClick={() => setBulkResult(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>✕</span>
              </div>
              {[['green', 'Совпадает', 'var(--income)'], ['blue', 'Мы полнее', 'var(--accent)'], ['red', 'Расхождения', 'var(--dot-overdue)']].map(([k, l, c]) => (
                <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, padding: '4px 0' }}>
                  <span style={{ width: 9, height: 9, borderRadius: 2, background: c }} />
                  <span style={{ flex: 1, color: 'var(--text-secondary)' }}>{l}</span>
                  <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{bulkResult[k] || 0}</span>
                </div>
              ))}
              {(bulkResult.skipped > 0 || bulkResult.errors > 0) && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-row)', fontSize: 12, color: 'var(--text-muted)' }}>
                  {bulkResult.skipped > 0 && <span>пропущено (локальные): {bulkResult.skipped}. </span>}
                  {bulkResult.errors > 0 && <span style={{ color: '#C93A3E' }}>ошибок: {bulkResult.errors}</span>}
                </div>
              )}
              {bulkResult.failed && bulkResult.failed.length > 0 && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-row)', maxHeight: 160, overflowY: 'auto' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#C93A3E', marginBottom: 4 }}>Где отвалилось:</div>
                  {bulkResult.failed.map(f => (
                    <div key={f.id} style={{ fontSize: 12, padding: '3px 0', color: 'var(--text-secondary)' }}>
                      <span style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>#{f.id}</span> {f.title}
                      <div style={{ fontSize: 11, color: '#C93A3E' }}>{f.error}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Заливка правок в Битрикс: превью → подтверждение → результат ── */}
        {pushPreview && (
          <div {...overlayClose(() => !pushBusy && setPushPreview(null))} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(20,26,40,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)', width: 420, maxWidth: '92vw', maxHeight: '82vh', overflowY: 'auto', padding: '20px 22px', fontFamily: UI }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>Залить правки в Битрикс</span>
                <span onClick={() => !pushBusy && setPushPreview(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>✕</span>
              </div>

              {pushPreview.done ? (
                <>
                  <div style={{ fontSize: 14, color: 'var(--income)', fontWeight: 600, marginBottom: 8 }}>✓ Залито в Битрикс: {pushPreview.done.pushed}</div>
                  {(pushPreview.done.errors || []).length > 0 && (
                    <div style={{ background: 'var(--danger-tint)', borderRadius: 10, padding: '10px 12px', marginTop: 8 }}>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: '#C93A3E', marginBottom: 5 }}>Ошибки ({pushPreview.done.errors.length})</div>
                      {pushPreview.done.errors.slice(0, 8).map((e, i) => <div key={i} style={{ fontSize: 12, color: '#8a2b2f', padding: '2px 0' }}>• {e.deal}: {e.error}</div>)}
                    </div>
                  )}
                  <button onClick={() => setPushPreview(null)} style={{ marginTop: 14, ...btnAcc }}>Закрыть</button>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 14, color: 'var(--text-primary)', marginBottom: 12 }}>
                    Уйдёт в Битрикс: <b style={{ fontFamily: MONO, color: 'var(--accent)' }}>{pushPreview.total || 0}</b> правок <span style={{ color: 'var(--text-muted)' }}>(только «Название»)</span> в <b style={{ fontFamily: MONO }}>{pushPreview.deals || 0}</b> сделок.
                  </div>
                  {Object.keys(pushPreview.skipped || {}).length > 0 && (
                    <div style={{ background: 'var(--warning-tint)', borderRadius: 10, padding: '10px 12px', marginBottom: 14 }}>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: '#B26A0C', marginBottom: 6 }}>Пока не льём (нужен маппинг справочников)</div>
                      {Object.entries(pushPreview.skipped).map(([f, c]) => (
                        <div key={f} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#8a5209', padding: '2px 0' }}>
                          <span>{PUSH_FIELD_LABELS[f] || f}</span><span style={{ fontFamily: MONO }}>{c}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={confirmPushEdits} disabled={pushBusy || !(pushPreview.total > 0)} style={{ ...btnAcc, opacity: (pushBusy || !(pushPreview.total > 0)) ? 0.5 : 1 }}>{pushBusy ? 'Заливаю…' : `Залить ${pushPreview.total || 0}`}</button>
                    <button onClick={() => setPushPreview(null)} disabled={pushBusy} style={btnSec}>Отмена</button>
                  </div>
                  <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-faint)' }}>Запись идёт в живой Битрикс24. Отменить после заливки нельзя.</div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
