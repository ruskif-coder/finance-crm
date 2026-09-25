import { useState, useEffect, useCallback, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { MONO, UI, card, primaryBtn, GenTitleBtn, MultiDrop, LoadError } from '@/components/salesTableKit'
import { errText, isAuth } from '@/lib/loadError'
import api, { auth } from '@/lib/api'
import { fmtFull, fmtMoney, grp } from '@/lib/salesFormat'
import { downloadMp } from '@/lib/mpDownload'
import { DownloadOverlay } from '@/components/LogoLoader'
import ValuePopover from '@/components/ValuePopover'
import { buildTitle, separatePriceSet, surfaceTag, TITLE_EMPTY_HINT } from '@/lib/dealTitle'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

// Реестр медиапланов (контур аккаунта). Тулбар (поиск/период/фильтры/сортировка) и
// клик-редактирование ячеек — как в реестре сделок. Данные приходят пачкой (последние
// версии), поэтому фильтрация/сортировка — клиентские.
// Деньги — общим `grp`: см. lib/salesFormat, там же `grp0`/`grpDash` на случай,
// когда ноль значащий, а когда пустой.
const rub = (n) => (n == null ? '—' : `${grp(n)} ₽`)
// Колонки CSS-grid — ширины/раскладка как в реестре сделок (sales.js). edit — поле пикера.
const COLS = [
  { key: 'id', w: '52px', label: 'ID' },
  { key: 'title', w: '1.5fr', label: 'Сделка' },
  { key: 'agency', w: '96px', label: 'Агентство', edit: 'agency' },
  { key: 'advertiser', w: '1.1fr', label: 'Рекламодатель', edit: 'advertiser' },
  { key: 'brand', w: '1fr', label: 'Бренд', edit: 'brand' },
  { key: 'period', w: '80px', label: 'Период', edit: 'period' },
  { key: 'amount_gross', w: '92px', label: 'Сумма', right: true },
  { key: 'sales_rep', w: '100px', label: 'Продавец', edit: 'seller' },
  { key: 'account_manager', w: '96px', label: 'Аккаунт', edit: 'account' },
  { key: 'payer', w: '1.15fr', label: 'Плательщик', edit: 'payer' },
  { key: 'deal_code', w: '132px', label: 'Сделка' },
  { key: 'actions', w: '162px', label: '', right: true },
]
const GRID = COLS.map(c => c.w).join(' ')
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
  const [editTitleId, setEditTitleId] = useState(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [pdfBusy, setPdfBusy] = useState(null)
  const [downloading, setDownloading] = useState(false)   // оверлей 1c на время выгрузки

  // тулбар: поиск / период / фильтры / сортировка
  const [search, setSearch] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [periodOpen, setPeriodOpen] = useState(false)
  const [sel, setSel] = useState({ deal_stage: [], agency_id: [], advertiser_id: [], brand_id: [], sales_rep_id: [], account_manager_id: [] })
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('desc')

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
  const canDelete = isAdmin || can(perms, 'media_plans', 'edit')

  // Сбой — не «Медиапланов нет» (аудит 23.09.2026, 7.M5): `.catch(() => {})` оставлял
  // пустой список с приглашением создать первый медиаплан. Фоновая перечитка — тихая.
  const [err, setErr] = useState('')
  const load = useCallback(({ quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    api.get('/sales/media-plans', auth())
      .then(r => { setItems(r.data.items || []); setErr('') })
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
    const admin = localStorage.getItem('role') === 'admin'
    setPerms(p); setIsAdmin(admin)
    if (!admin && !can(p, 'media_plans', 'view')) { router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
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
  // Фильтр по стадии сделки: состояние плана это состояние его сделки, и фильтровать
  // реестр планов имеет смысл именно по ней. План без сделки — своя строка списка.
  const stageOpts = useMemo(() => [...new Set(items.map(i => i.deal_stage || '— без сделки'))]
    .map(v => ({ value: v, label: v })), [items])
  const DROPS = [
    ['deal_stage', 'Стадия сделки', stageOpts],
    ['agency_id', 'Агентство', distinct('agency_id', 'agency')],
    ['advertiser_id', 'Рекламодатель', distinct('advertiser_id', 'advertiser')],
    ['brand_id', 'Бренд', distinct('brand_id', 'brand')],
    ['sales_rep_id', 'Продавец', distinct('sales_rep_id', 'sales_rep')],
    ['account_manager_id', 'Аккаунт', distinct('account_manager_id', 'account_manager')],
  ]
  const activeFilters = Object.values(sel).some(a => a.length) || dateFrom || dateTo || search.trim()

  const view = useMemo(() => {
    const q = search.trim().toLowerCase()
    let out = items.filter(it => {
      if (q) {
        const hay = [it.id, it.title, it.agency, it.advertiser, it.brand, it.period, it.payer, it.sales_rep, it.account_manager].map(v => String(v ?? '').toLowerCase()).join(' ')
        if (!hay.includes(q)) return false
      }
      if (dateFrom && String(it.period || '') < dateFrom) return false
      if (dateTo && String(it.period || '') > dateTo) return false
      for (const [k] of DROPS) {
        const v = k === 'deal_stage' ? (it.deal_stage || '— без сделки') : it[k]
        if (sel[k].length && !sel[k].some(x => String(x) === String(v))) return false
      }
      return true
    })
    const val = (it) => {
      if (sortKey === 'amount_gross' || sortKey === 'id') return it[sortKey] || 0
      if (sortKey === 'deal_code') return it.deal_code || ''
      return String(it[sortKey] ?? '')
    }
    out = [...out].sort((a, b) => {
      const va = val(a), vb = val(b)
      const c = typeof va === 'number' ? va - vb : va.localeCompare(vb, 'ru')
      return sortDir === 'desc' ? -c : c
    })
    return out
  }, [items, search, dateFrom, dateTo, sel, sortKey, sortDir])

  const onSort = (k) => { if (sortKey === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortKey(k); setSortDir('desc') } }
  const resetFilters = () => { setSel({ deal_stage: [], agency_id: [], advertiser_id: [], brand_id: [], sales_rep_id: [], account_manager_id: [] }); setDateFrom(''); setDateTo(''); setSearch('') }

  const patchCell = async (id, patch, localApply) => {
    try { await api.patch(`/sales/media-plans/${id}`, patch, auth()); setItems(prev => prev.map(x => x.id === id ? { ...x, ...localApply } : x)); return true }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить'); return false }
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
          } catch (e) { alert(e.response?.data?.detail || 'Не удалось создать бренд') }
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

  const saveTitle = async (id) => {
    const t = titleDraft.trim(); setEditTitleId(null)
    if (t && t !== (items.find(x => x.id === id)?.title || '')) await patchCell(id, { title: t }, { title: t })
  }

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

  const act = { padding: '4px 8px', borderRadius: 7, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 11.5, color: 'var(--text-secondary)' }
  const clip = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
  // Ячейка-грид с клик-редактированием (пикер у места клика), как в реестре сделок.
  // Кликабельна ВСЯ ячейка, а не строка текста: по ширине грид-элемент растягивается
  // сам, по высоте нет — вертикальные отступы с обратными полями добирают высоту строки.
  // Без этого у пустого поля мишенью был один прочерк.
  const EditCell = ({ it, field, mono, children }) => (
    <span onClick={canEdit ? (e) => openPicker(field, it, e) : undefined}
      style={{ ...clip, display: 'block', boxSizing: 'border-box', borderRadius: 6,
        padding: '8px 4px', margin: '-8px -4px', width: 'calc(100% + 8px)',
        cursor: canEdit ? 'pointer' : 'default', fontFamily: mono ? MONO : undefined,
        fontSize: mono ? 12 : undefined, color: children ? 'var(--text-primary)' : 'var(--text-faint)' }}>
      {children || '—'}</span>
  )

  return (
    <>
      <Head><title>Медиапланы · Аккаунты | SIMB-AD ERP</title></Head>
      {downloading && <DownloadOverlay />}
      <Navbar active="" />
      <style>{`.d2-row:hover{background:var(--bg-subtle)!important}`}</style>
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Медиапланы</h1>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{view.length}{view.length !== items.length ? ` / ${items.length}` : ''}</span>
          {canCreate && <button onClick={() => router.push('/accounts/mp/new')} style={{ ...primaryBtn, marginLeft: 'auto' }}>+ Новый медиаплан</button>}
        </div>

        {/* ── Тулбар: поиск · период · фильтры · сброс ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          <div style={{ flex: '0 0 auto', width: searchFocus ? 300 : 160, display: 'inline-flex', alignItems: 'center', gap: 7, border: `1px solid ${searchFocus ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '7px 10px', transition: 'width .22s cubic-bezier(0.22,1,0.36,1), border-color .15s' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>⌕</span>
            <input value={search} onChange={e => setSearch(e.target.value)} onFocus={() => setSearchFocus(true)} onBlur={() => setSearchFocus(false)}
              placeholder="поиск: название, контрагент, продавец…" style={{ flex: 1, minWidth: 0, width: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 12.5, color: 'inherit', fontFamily: UI }} />
          </div>

          <div style={{ position: 'relative' }}>
            <div onClick={() => setPeriodOpen(o => !o)} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: `1px solid ${(dateFrom || dateTo || periodOpen) ? 'var(--accent)' : 'var(--border-card)'}`, background: (dateFrom || dateTo) ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontFamily: MONO, fontSize: 11, color: (dateFrom || dateTo) ? 'var(--accent)' : 'var(--text-muted)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
              {(dateFrom || dateTo) ? `${dateFrom || '…'} — ${dateTo || '…'}` : 'период'} ▾
            </div>
            {periodOpen && (<>
              <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setPeriodOpen(false)} />
              <div style={{ position: 'absolute', top: '110%', left: 0, marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8, minWidth: 230 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                  <span style={{ color: 'var(--text-muted)' }}>—</span>
                  <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ flex: 1, padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
                </div>
                {(dateFrom || dateTo) && <div onClick={() => { setDateFrom(''); setDateTo('') }} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer' }}>Сбросить период</div>}
              </div>
            </>)}
          </div>

          {DROPS.map(([k, label, opts]) => (
            <MultiDrop key={k} label={label} options={opts} selected={sel[k]} onChange={v => setSel(s => ({ ...s, [k]: v }))} />
          ))}

          {activeFilters && <div onClick={resetFilters} title="Сбросить фильтры" style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer', whiteSpace: 'nowrap' }}>Сбросить ✕</div>}
        </div>

        {!!err && <div style={{ marginBottom: 12 }}><LoadError text={err} onRetry={() => load()} /></div>}
        {loading ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
          <div style={{ ...card, padding: '12px 16px', overflowX: 'auto' }}>
            <div style={{ minWidth: 1180 }}>
              {/* шапка */}
              <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, padding: '0 8px 10px', borderBottom: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                {COLS.map(c => c.key === 'actions'
                  ? <span key="actions" style={{ textAlign: 'right' }}>Действия</span>
                  : <span key={c.key} onClick={() => onSort(c.key)} style={{ textAlign: c.right ? 'right' : 'left', cursor: 'pointer', userSelect: 'none', color: sortKey === c.key ? 'var(--accent)' : 'var(--text-faint)' }}>
                    {c.label}{sortKey === c.key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}</span>)}
              </div>
              {/* строки */}
              {view.map(it => {
                return (
                  <div key={it.id} className="d2-row" style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', fontSize: 12, color: 'var(--text-primary)' }}>
                    <span style={{ ...clip, fontFamily: MONO, color: 'var(--text-muted)' }}>{it.id}<span style={{ fontSize: 10, color: 'var(--text-faint)' }}> v{it.version}</span></span>
                    {editTitleId === it.id
                      ? <input autoFocus value={titleDraft} onChange={e => setTitleDraft(e.target.value)}
                        onBlur={() => saveTitle(it.id)} onKeyDown={e => { if (e.key === 'Enter') saveTitle(it.id); if (e.key === 'Escape') setEditTitleId(null) }}
                        style={{ minWidth: 0, padding: '3px 6px', border: '1px solid var(--accent)', borderRadius: 6, fontSize: 12.5, fontFamily: UI, background: 'var(--bg-card)', color: 'inherit' }} />
                      : <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                        <span onClick={canEdit ? () => { setEditTitleId(it.id); setTitleDraft(it.title || '') } : undefined}
                          style={{ ...clip, flex: 1, fontWeight: 600, cursor: canEdit ? 'text' : 'default', color: it.title ? 'var(--text-primary)' : 'var(--text-faint)' }}>{it.title || 'без названия'}</span>
                        {!!surfaceTag(it.inventory) && (
                          <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em', color: 'var(--text-faint)', flexShrink: 0 }}>{surfaceTag(it.inventory)}</span>
                        )}
                        {canEdit && <GenTitleBtn onClick={() => genTitle(it)} size={22} />}
                      </span>}
                    <EditCell it={it} field="agency">{it.agency}</EditCell>
                    <EditCell it={it} field="advertiser">{it.advertiser}</EditCell>
                    <EditCell it={it} field="brand">{it.brand}</EditCell>
                    <EditCell it={it} field="period" mono>{it.period}</EditCell>
                    <span style={{ ...clip, fontFamily: MONO, fontWeight: 700, textAlign: 'right' }}
                      title={`с НДС ${fmtFull(it.amount_gross)}\nдо НДС ${fmtFull(it.amount_net)}`}>{fmtMoney(it.amount_gross)}</span>
                    <EditCell it={it} field="seller">{it.sales_rep}</EditCell>
                    <EditCell it={it} field="account">{it.account_manager}</EditCell>
                    <EditCell it={it} field="payer">{it.payer}</EditCell>
                    <span style={clip}>{it.deal_code
                      ? <a href={`/sales/deals/${it.deal_code}`} onClick={e => e.stopPropagation()}
                          title={it.deal_stage || ''}
                          style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>{it.deal_code}</a>
                      : <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>без сделки</span>}</span>
                    <span style={{ display: 'inline-flex', gap: 4, justifyContent: 'flex-end' }}>
                      <button onClick={() => router.push(`/accounts/mp/${it.id}`)} style={act}>Открыть</button>
                      <button onClick={() => exportXlsx(it)} style={act}>Excel</button>
                      <button onClick={() => downloadPdf(it)} disabled={pdfBusy === it.id} style={act}>{pdfBusy === it.id ? '…' : 'PDF'}</button>
                      {canDelete && <button onClick={() => del(it)} style={{ ...act, color: 'var(--danger)', borderColor: 'var(--danger-tint)' }}>✕</button>}
                    </span>
                  </div>
                )
              })}
              {!view.length && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>{err && !items.length ? 'Реестр не загрузился — см. сообщение выше' : items.length ? 'Ничего не найдено — измените фильтры' : 'Медиапланов нет — нажмите «+ Новый медиаплан»'}</div>}
            </div>
          </div>
        )}
      </div>

      {vpop && <ValuePopover anchor={vpop.rect} title={vpop.title} dealLabel={vpop.dealLabel} options={vpop.options} value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
        onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />}
    </>
  )
}
