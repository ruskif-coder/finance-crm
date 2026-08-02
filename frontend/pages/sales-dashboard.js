import { useState, useEffect, useRef, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import SalesTabs from '../components/SalesTabs'
import SalesQuarterWidgets from '../components/SalesQuarterWidgets'
import DealCreateForm from '../components/DealCreateForm'
import DealBriefCell from '../components/DealBriefCell'
import ValuePopover from '../components/ValuePopover'
import api, { auth } from '../lib/api'
import { fmtMoney, fmtDate } from '../lib/salesFormat'
import { BITRIX_DEAL_URL } from '../lib/salesLayers'
import { MONO, UI, PIP, FILL, HATCH, FILTER_DROPS, GAP_FIELDS, shortLabel, MultiDrop, IconBtn } from '../components/salesTableKit'
import useIsMobile from '../components/mobile/useIsMobile'
import DealsMobileControls from '../components/sales/DealsMobileControls'
import DealCardList from '../components/mobile/DealCardList'

// Описание колонок: ширина + подпись. brief/gen — фиксированные (не скрываются).
const COLS = [
  { key: 'brief', w: '30px', label: 'Бриф', fixed: true },
  { key: 'bitrix_id', w: '62px', label: 'BX_ID', sortable: true },
  { key: 'agency', w: '92px', label: 'Агентство', sortable: true },
  { key: 'advertiser', w: '1.1fr', label: 'Рекламодатель', sortable: true },
  { key: 'brand', w: '1fr', label: 'Бренд', sortable: true },
  { key: 'product', w: '1fr', label: 'Услуга', sortable: true },
  { key: 'period', w: '78px', label: 'Период', sortable: true },
  { key: 'bitrix_stage', w: '1.15fr', label: 'Стадия', sortable: true },
  { key: 'amount', w: '88px', label: 'Сумма', sortable: true, right: true },
  { key: 'sales_rep', w: '92px', label: 'Продавец', sortable: true },
  { key: 'account_manager', w: '88px', label: 'Аккаунт', sortable: true },
  { key: 'payer', w: '1.15fr', label: 'Плательщик', sortable: true },
  { key: 'money_layer', w: '74px', label: 'Слой' },
  { key: 'pipeline', w: '92px', label: 'Воронка', sortable: true },
  { key: 'period_from', w: '84px', label: 'Старт РК', sortable: true },
  { key: 'period_to', w: '84px', label: 'Конец РК', sortable: true },
  { key: 'title', w: '1.5fr', label: 'Сделка', sortable: true },
]
// по умолчанию скрыты (доступны в меню «Колонки»)
const DEFAULT_HIDDEN = ['pipeline', 'period_from', 'period_to']
const COLS_KEY = 'sd3_hidden_cols'
const COLS_ORDER_KEY = 'sd3_col_order'
const COL_BY_KEY = Object.fromEntries(COLS.map(c => [c.key, c]))
const MIDDLE_KEYS = COLS.filter(c => !c.fixed).map(c => c.key)   // переставляемые/скрываемые (brief/gen фиксированы)

function recentQuarters(n = 6) {
  const out = []; const d = new Date()
  let y = d.getFullYear(); let q = Math.floor(d.getMonth() / 3) + 1
  for (let i = 0; i < n; i++) { out.push(`${y}-Q${q}`); q--; if (q < 1) { q = 4; y-- } }
  return out
}
const quarterRange = (qs) => {
  if (qs === 'all' || qs === 'Всё время') return 'всё время'
  const m = /(\d{4}).*?([1-4])/.exec(qs || '')
  const d = new Date(); let y = d.getFullYear(); let q = Math.floor(d.getMonth() / 3) + 1
  if (m) { y = +m[1]; q = +m[2] }
  const m0 = (q - 1) * 3
  const from = new Date(y, m0, 1), to = new Date(y, m0 + 3, 0)
  const f = (x) => `${String(x.getDate()).padStart(2, '0')}.${String(x.getMonth() + 1).padStart(2, '0')}.${String(x.getFullYear()).slice(2)}`
  return `${f(from)} — ${f(to)}`
}
// Месяцы квартала в формате YYYY-MM (для фильтра таблицы сделок по периоду РК).
// Пустой аргумент → текущий квартал.
const quarterMonths = (qs) => {
  const m = /(\d{4}).*?([1-4])/.exec(qs || '')
  const d = new Date(); let y = d.getFullYear(); let q = Math.floor(d.getMonth() / 3) + 1
  if (m) { y = +m[1]; q = +m[2] }
  const m0 = (q - 1) * 3 + 1
  const p = (mm) => `${y}-${String(mm).padStart(2, '0')}`
  return { from: p(m0), to: p(m0 + 2) }
}
export default function SalesDashboard2() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [quarter, setQuarter] = useState('')
  const [repId, setRepId] = useState('')
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [perms, setPerms] = useState({})
  const canEdit = can(perms, 'sales_registry', 'edit')
  const canDirAg = can(perms, 'dir_agencies', 'edit')
  const canDirAdv = can(perms, 'dir_advertisers', 'edit')

  const [deals, setDeals] = useState([])
  const [dealsTotal, setDealsTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [pageSize, setPageSize] = useState(50)
  const [sortKey, setSortKey] = useState('amount')
  const [sortDir, setSortDir] = useState('desc')

  const [sel, setSel] = useState(Object.fromEntries(FILTER_DROPS.map(([k]) => [k, []])))
  const [gaps, setGaps] = useState([])
  const [hideArchive, setHideArchive] = useState(true)
  const [search, setSearch] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [periodOpen, setPeriodOpen] = useState(false)

  const [fopts, setFopts] = useState({})
  const [brandsByAdv, setBrandsByAdv] = useState({})
  const [vpop, setVpop] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
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
  const [dragIdx, setDragIdx] = useState(null)
  const [colPicker, setColPicker] = useState(false)
  const [periodEdit, setPeriodEdit] = useState(null) // { dealId, rect, month } — правка периода строки
  const [genConfirm, setGenConfirm] = useState(null) // { dealId, rect, text, current } — подтверждение генерации имени
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
  const dropCol = (targetIdx) => {
    if (dragIdx === null || dragIdx === targetIdx) { setDragIdx(null); return }
    setColOrder(prev => {
      const next = [...prev]; const [moved] = next.splice(dragIdx, 1); next.splice(targetIdx, 0, moved)
      localStorage.setItem(COLS_ORDER_KEY, JSON.stringify(next)); return next
    })
    setDragIdx(null)
  }
  // brief фиксирован первым; далее — переставленные видимые колонки (кнопка генерации живёт внутри ячейки «Сделка»).
  const visibleCols = [COL_BY_KEY.brief, ...colOrder.map(k => COL_BY_KEY[k]).filter(c => c && !hidden.has(c.key))].filter(Boolean)
  const gridTemplate = visibleCols.map(c => c.w).join(' ')
  const isMobile = useIsMobile()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [mobView, setMobView] = useState('cards')       // мобильный вид: карточки | таблица
  const [mobSearchOpen, setMobSearchOpen] = useState(false)
  const activeFilterCount = Object.values(sel).filter(a => a.length).length + (gaps.length ? 1 : 0) + ((dateFrom || dateTo) ? 1 : 0) + (searchQ.trim() ? 1 : 0)
  const loadMoreMobile = () => setPageSize(p => p + 50)

  // Выгрузка текущей выборки в CSV (клиентская).
  const exportCsv = () => {
    const head = ['BX_ID', 'Агентство', 'Рекламодатель', 'Бренд', 'Услуга', 'Период', 'Стадия', 'Сумма', 'Аккаунт', 'Плательщик', 'Слой', 'Сделка']
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = deals.map(d => [d.bitrix_id, d.agency, d.advertiser, d.brand, d.product, d.period, d.bitrix_stage, d.amount, d.account_manager, d.payer, d.money_layer, d.title].map(esc).join(';'))
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
  }, [])

  const load = async () => {
    setLoading(true); setErr('')
    try {
      const params = {}
      if (quarter) params.quarter = quarter
      if (repId) params.rep_id = repId
      const r = await api.get('/sales/dashboard/bonus', { ...auth(), params })
      setData(r.data)
      loadDeals(r.data.rep_ids)
      if (r.data.can_view_others && reps.length === 0) api.get('/sales/reps', auth()).then(rr => setReps(rr.data.items || [])).catch(() => {})
    } catch (e) { if (e.response?.status === 401) return router.push('/login'); setErr(e.response?.data?.detail || 'Ошибка загрузки') }
    finally { setLoading(false) }
  }
  const buildBase = (repIds) => {
    const b = new URLSearchParams()
    ;(repIds || []).forEach(id => b.append('sales_rep_id', id))
    Object.entries(sel).forEach(([k, arr]) => arr.forEach(v => b.append(k, v)))
    gaps.forEach(g => b.append('gaps', g))
    if (hideArchive) b.append('hide_archive', 'true')
    if (searchQ.trim()) b.append('search', searchQ.trim())
    // Период таблицы: ручной диапазон С/По имеет приоритет; иначе — по выбранному
    // кварталу; «Показать все» (quarter==='all') снимает ограничение периода.
    if (dateFrom || dateTo) {
      if (dateFrom) b.append('date_from', dateFrom)
      if (dateTo) b.append('date_to', dateTo)
    } else if (quarter !== 'all') {
      const qm = quarterMonths(quarter)
      b.append('date_from', qm.from); b.append('date_to', qm.to)
    }
    return b
  }
  const dealsSeq = useRef(0)
  const loadDeals = async (repIds) => {
    const seq = ++dealsSeq.current            // защита от гонки/двойного фетча: применяем только последний
    if (!repIds || !repIds.length) { setDeals([]); setDealsTotal(0); setSummary(null); return }
    const base = buildBase(repIds)
    const dq = new URLSearchParams(base)
    dq.append('limit', String(pageSize)); dq.append('sort', sortKey); dq.append('direction', sortDir)
    try { const r = await api.get('/sales/deals?' + dq.toString(), auth()); if (seq !== dealsSeq.current) return; setDeals(r.data.items || []); setDealsTotal(r.data.total || 0) }
    catch (e) { if (seq !== dealsSeq.current) return; setDeals([]); setDealsTotal(0) }
    api.get('/sales/dashboard?' + base.toString(), auth()).then(r => { if (seq === dealsSeq.current) setSummary(r.data) }).catch(() => { if (seq === dealsSeq.current) setSummary(null) })
  }

  useEffect(() => { load() }, [quarter, repId])
  useEffect(() => { if (data?.rep_ids?.length) loadDeals(data.rep_ids) }, [sortKey, sortDir, pageSize, sel, gaps, hideArchive, searchQ, dateFrom, dateTo])
  useEffect(() => { const t = setTimeout(() => setSearchQ(search), 300); return () => clearTimeout(t) }, [search])

  const onSort = (k, sortable) => { if (!sortable) return; if (sortKey === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortKey(k); setSortDir('desc') } }
  const resetFilters = () => { setSel(Object.fromEntries(FILTER_DROPS.map(([k]) => [k, []]))); setGaps([]); setHideArchive(true); setSearch(''); setSearchQ(''); setDateFrom(''); setDateTo('') }

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
      service: { title: 'Услуга', options: (fopts.product || []).map(o => ({ value: o.value, label: o.label || o.value })), value: d.product, apply: (v) => patchCell(d.id, { product: v }, { product: v }) },
    }[field]
    if (!cfg) return
    setVpop({ rect, dealLabel: `сделка ${d.bitrix_id}`, ...cfg })
  }
  const templateTitle = (d) => [d.advertiser, d.brand, d.agency, d.product, d.period].filter(v => v != null && String(v).trim() !== '').join(' | ')
  const saveTitle = async (id, title) => { try { await api.patch(`/sales/deals/${id}`, { title }, auth()); setDeals(prev => prev.map(x => x.id === id ? { ...x, title } : x)) } catch (e) { alert('Не удалось сохранить название') } }

  const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

  // Ячейка строки по ключу колонки (для итерации по видимым колонкам).
  const cellFor = (key, d) => {
    const none = !FILL[d.money_layer]; const n = FILL[d.money_layer] || 0
    switch (key) {
      case 'brief': return <DealBriefCell deal={d} canEdit={canEdit} v2 />
      case 'bitrix_id': return String(d.bitrix_id || '').startsWith('local-')
        ? (canEdit
          ? <button onClick={() => api.post(`/sales/deals/${d.id}/push-to-bitrix`, {}, auth()).then(() => loadDeals(data.rep_ids)).catch(e => alert(e.response?.data?.detail || 'Ошибка'))} title="Отправить в Битрикс" style={{ border: '1px solid var(--accent)', background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 6, cursor: 'pointer', fontSize: 11, padding: '2px 6px', fontFamily: MONO, justifySelf: 'start' }}>→ БХ</button>
          : <span style={{ color: 'var(--text-faint)', fontSize: 11, fontFamily: MONO }}>локально</span>)
        : <a href={BITRIX_DEAL_URL(d.bitrix_id)} target="_blank" rel="noreferrer" style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>{d.bitrix_id}</a>
      case 'agency': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('agency', d, e)} style={{ fontWeight: 600 }} title={d.agency_full || d.agency || 'выбрать'}>{d.agency ?? '—'}</span>
      case 'advertiser': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('advertiser', d, e)} title={d.advertiser_full || d.advertiser || 'выбрать'}>{d.advertiser ?? '—'}</span>
      case 'brand': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('brand', d, e)} title={d.brand || 'выбрать'}>{d.brand ?? '—'}</span>
      case 'product': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => openPicker('service', d, e)} style={{ color: 'var(--text-secondary)' }} title={d.product || 'выбрать'}>{d.product ?? '—'}</span>
      case 'period': return <span className={canEdit ? 'd2-cell' : ''} onClick={e => { if (canEdit) setPeriodEdit({ dealId: d.id, rect: e.currentTarget.getBoundingClientRect(), month: d.period || '', current: d.period }) }}
        style={{ fontFamily: MONO, color: 'var(--text-secondary)' }} title={canEdit ? 'Изменить период (месяц старта РК)' : undefined}>{d.period ?? '—'}</span>
      case 'bitrix_stage': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.bitrix_stage}>{d.bitrix_stage ?? '—'}</span>
      case 'amount': return <span style={{ fontFamily: MONO, fontWeight: 700, textAlign: 'right' }} title={d.amount != null ? new Intl.NumberFormat('ru-RU').format(d.amount) + ' ₽' : ''}>{fmtMoney(d.amount)}</span>
      case 'account_manager': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.account_manager ?? '—'}</span>
      case 'payer': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.payer}>{d.payer ?? '—'}</span>
      case 'money_layer': return <span style={{ display: 'flex', gap: 2 }} title={none ? 'Без группы — требует разбора' : `${d.money_layer} · слой денег`}>{PIP.map((c, i) => <span key={i} style={{ width: 9, height: 14, borderRadius: 2, background: none ? HATCH : (i < n ? c : 'var(--border-inner)') }} />)}</span>
      case 'pipeline': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.pipeline}>{d.pipeline ?? '—'}</span>
      case 'sales_rep': return <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.sales_rep ?? '—'}</span>
      case 'period_from': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{d.period_from ? fmtDate(d.period_from) : '—'}</span>
      case 'period_to': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{d.period_to ? fmtDate(d.period_to) : '—'}</span>
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
        <title>Дашборд</title>
      </Head>
      <Navbar active="sales" />
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        .d2-row:hover { background: var(--bg-subtle) !important; }
        .d2-cell { cursor:pointer; border-radius:6px; padding:2px 4px; margin:-2px -4px; display:inline-block; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; vertical-align:bottom; }
        .d2-cell:hover { background: var(--accent-tint); color: var(--accent); }
        .d2-gen:hover, .d2-ico:hover { border-color:#C7D0E8 !important; color:var(--accent) !important; }
        @media (prefers-reduced-motion: reduce) { [style*="animation"] { animation:none !important } }
      `}</style>

      {vpop && <ValuePopover anchor={vpop.rect} title={vpop.title} dealLabel={vpop.dealLabel} options={vpop.options} value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
        onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />}
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
        <div onClick={() => setEntityModal(null)} style={{ position: 'fixed', inset: 0, zIndex: 70, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
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
        <div onClick={() => setAdvConfirm(null)} style={{ position: 'fixed', inset: 0, zIndex: 72, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
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

      <div style={{ padding: 24 }}>
        <SalesTabs active="dashboard" />
        <DealCreateForm open={createOpen} onClose={() => setCreateOpen(false)} canPickRep={!!data?.can_view_others} onCreated={() => { setSortKey('date_create'); setSortDir('desc') }} />

        {err && <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div>}
        {loading && !data && <div style={{ color: 'var(--text-muted)', padding: 40 }}>Загрузка…</div>}

        {data && (
          <div>{/* без transform-обёртки: иначе position:fixed модалок центрируется относительно неё, а не экрана */}
            <SalesQuarterWidgets data={data} summary={summary} lastSyncAt={summary?.last_sync_at}
              quarter={quarter} setQuarter={setQuarter} quarters={recentQuarters()}
              repId={repId} setRepId={setRepId} reps={reps} canViewOthers={!!data.can_view_others}
              onCreate={canEdit ? () => setCreateOpen(true) : undefined}
              onCreateAgency={canDirAg ? openAgency : undefined} onCreateAdvertiser={canDirAdv ? openAdvertiser : undefined} />

            {!data.linked ? (
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, padding: 32, textAlign: 'center', color: 'var(--text-muted)', marginTop: 16, maxWidth: 700 }}>
                {data.can_view_others ? 'Выберите сотрудника в селекторе в шапке блока.' : 'Ваш профиль не привязан к продавцу — обратитесь к админу.'}
              </div>
            ) : (
              <div style={{ marginTop: 12 }}>
                {/* заголовок блока (десктоп) */}
                {!isMobile && (
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24, padding: '0 4px', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                    <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Список сделок</span>
                    <span style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>{dealsTotal}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ position: 'relative' }}>
                      <div onClick={() => setColPicker(o => !o)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '8px 13px', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>Колонки ▾</div>
                      {colPicker && (<>
                        <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setColPicker(false)} />
                        <div style={{ position: 'absolute', right: 0, top: '110%', marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, minWidth: 210 }}>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Колонки (тащите за ⠿ для порядка)</div>
                          {colOrder.map((k, i) => {
                            const c = COL_BY_KEY[k]; if (!c) return null
                            return (
                              <div key={k} draggable
                                onDragStart={() => setDragIdx(i)} onDragOver={e => e.preventDefault()} onDrop={() => dropCol(i)} onDragEnd={() => setDragIdx(null)}
                                style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, padding: '4px 2px', borderRadius: 6, background: dragIdx === i ? 'var(--accent-tint)' : 'transparent' }}>
                                <span title="перетащить" style={{ cursor: 'grab', color: 'var(--text-faint)', userSelect: 'none' }}>⠿</span>
                                <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggleColHidden(k)} style={{ cursor: 'pointer' }} />
                                <span style={{ flex: 1 }}>{c.label || k}</span>
                              </div>
                            )
                          })}
                        </div>
                      </>)}
                    </div>
                    <div className="d2-ico" title="Скачать в CSV" onClick={exportCsv}
                      style={{ width: 36, height: 36, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
                    </div>
                  </div>
                </div>
                )}

                {/* карточка таблицы */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)', padding: '20px 24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>

                  {/* фильтры: мобильный тулбар+шторка (общий компонент) / десктопная строка */}
                  {isMobile ? (
                    <DealsMobileControls dealsTotal={dealsTotal} search={search} setSearch={setSearch} mobSearchOpen={mobSearchOpen} setMobSearchOpen={setMobSearchOpen}
                      mobView={mobView} setMobView={setMobView} filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} activeFilterCount={activeFilterCount}
                      sel={sel} setSel={setSel} gaps={gaps} setGaps={setGaps} dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
                      hideArchive={hideArchive} setHideArchive={setHideArchive} fopts={fopts} resetFilters={resetFilters} exportCsv={exportCsv} />
                  ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <div style={{ flex: '0 0 auto', width: searchFocus ? 300 : 148, display: 'inline-flex', alignItems: 'center', gap: 7, border: `1px solid ${searchFocus ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '7px 10px', transition: 'width .22s cubic-bezier(0.22,1,0.36,1), border-color .15s' }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" style={{ ...stroke, strokeWidth: 2, flex: '0 0 13px', color: 'var(--text-faint)' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
                      <input value={search} onChange={e => setSearch(e.target.value)} onFocus={() => setSearchFocus(true)} onBlur={() => setSearchFocus(false)}
                        placeholder="ID, агентство, рекл, бренд…" title="Поиск: ID, агентство, рекламодатель, бренд, плательщик, название сделки"
                        style={{ border: 'none', outline: 'none', background: 'transparent', fontSize: 12, color: 'var(--text-secondary)', width: '100%', fontFamily: UI }} />
                    </div>
                    <div style={{ position: 'relative', flex: '0 0 auto' }}>
                      <div onClick={() => setPeriodOpen(o => !o)} title="Период размещения — выбрать диапазон месяцев"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: `1px solid ${(dateFrom || dateTo || periodOpen) ? 'var(--accent)' : 'var(--border-card)'}`, background: (dateFrom || dateTo) ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontFamily: MONO, fontSize: 11, color: (dateFrom || dateTo) ? 'var(--accent)' : 'var(--text-muted)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                        {(dateFrom || dateTo) ? `${dateFrom || '…'} — ${dateTo || '…'}` : quarterRange(quarter || data.quarter)} ▾
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
                    {FILTER_DROPS.map(([k, lbl]) => (
                      <MultiDrop key={k} label={lbl} options={fopts[k]} selected={sel[k]} onChange={v => setSel(s => ({ ...s, [k]: v }))} />
                    ))}
                    <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={gaps} onChange={setGaps} />
                    <div style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                      <IconBtn title={hideArchive ? 'Архив скрыт — показать архивные' : 'Архив показан — скрыть'} active={hideArchive} onClick={() => setHideArchive(v => !v)}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M4 8h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><path d="M3 4h18v4H3z" /><path d="M10 12h4" /></svg>
                      </IconBtn>
                      <div className="d2-ico" title="Сбросить фильтры" onClick={resetFilters}
                        style={{ flex: '0 0 32px', width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 10, cursor: 'pointer', background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-muted)' }}>
                        <svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg>
                      </div>
                    </div>
                  </div>
                  )}

                  {/* таблица (десктоп) / карточки (мобайл) */}
                  {isMobile ? <DealCardList deals={deals} canEdit={canEdit} view={mobView} total={dealsTotal} onLoadMore={loadMoreMobile} fopts={fopts} onPatch={patchCell} /> : (
                  <div style={{ overflowX: 'auto' }}>
                    <div style={{ minWidth: 1180 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, padding: '0 0 10px', borderBottom: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                        {visibleCols.map(c => (
                          <span key={c.key} onClick={() => onSort(c.key, c.sortable)} style={{ textAlign: c.right ? 'right' : 'left', cursor: c.sortable ? 'pointer' : 'default', color: sortKey === c.key ? 'var(--accent)' : 'var(--text-faint)' }}>
                            {c.label}{sortKey === c.key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                          </span>
                        ))}
                      </div>

                      {deals.map(d => (
                        <div key={d.id} className="d2-row" style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', fontSize: 12, color: 'var(--text-primary)' }}>
                          {visibleCols.map(c => <Fragment key={c.key}>{cellFor(c.key, d)}</Fragment>)}
                        </div>
                      ))}
                      {!deals.length && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет сделок по выбранным фильтрам</div>}
                    </div>
                  </div>
                  )}

                  {/* подвал */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', paddingTop: 14, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
                    <span>показано {deals.length} из {dealsTotal}</span>
                    <span style={{ display: 'inline-flex', gap: 14, flexWrap: 'wrap' }}>
                      {[['фактические', 'var(--income)'], ['реализуемые', 'var(--dot-current-dz)'], ['планируемые', 'var(--text-faint)']].map(([l, c]) => (
                        <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>
                      ))}
                    </span>
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                      <span>строк на странице</span>
                      <span style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
                        {[50, 100, 300, 500].map(nn => (
                          <span key={nn} onClick={() => setPageSize(nn)}
                            style={{ borderRadius: 8, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, fontWeight: pageSize === nn ? 700 : 600,
                              background: pageSize === nn ? 'var(--accent-tint)' : 'transparent', color: pageSize === nn ? 'var(--accent)' : 'var(--text-secondary)' }}>{nn}</span>
                        ))}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
