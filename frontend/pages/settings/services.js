import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { MONO, UI, card, inp, sel, ci, cs, th, td, primaryBtn, PortalPopover } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import { overlayClose } from '@/lib/overlay'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

// ── Справочник услуг (конструктор) — отдельная страница раздела «Настройки» ──
// Услуга: тип размещения + форма расчёта + единая/раздельная (web/app) цена + базовые
// константы под форму (CTR/VTR…). Порядок — drag-n-drop. Плюс блок «Доп. услуги».
const CALC_FORMS = ['CPM', 'CPC', 'CPV', 'CPI', 'CPD', 'Фикс', 'Пакет']
const PLACEMENT_TYPES = [
  { cat: 'Медийка', items: ['Banners', 'Rich Media', 'Native', 'Interstitial'] },
  { cat: 'Видео', items: ['OLV In-stream', 'OLV Out-stream', 'Rewarded video', 'CTV/OTT'] },
  { cat: 'Аудио', items: ['Audio'] },
  { cat: 'In-App', items: ['Playable', 'App install'] },
  { cat: 'Наружка', items: ['DOOH'] },
  { cat: 'Прочее', items: ['Push', 'Pop-under', 'Соцсети'] },
]
const ALL_PLACEMENTS = PLACEMENT_TYPES.flatMap(g => g.items)
const CONSTANTS_BY_FORM = {
  CPM: [{ key: 'ctr', label: 'CTR', unit: '%' }],
  CPC: [{ key: 'ctr', label: 'CTR', unit: '%' }],
  CPV: [{ key: 'vtr', label: 'VTR', unit: '%' }],
}
const constsFor = (f) => CONSTANTS_BY_FORM[f] || []
const numOrNull = (v) => (v === '' || v == null) ? null : Number(v)
const NEW_SVC = { name: '', placement_type: '', calc_form: '', separate_price: false, unit_price: '', unit_price_web: '', unit_price_app: '', constants: {}, revenue_article_id: '' }

export default function SettingsServices() {
  const router = useRouter()
  const [services, setServices] = useState([])
  const [addons, setAddons] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingServices, setEditingServices] = useState({})
  const [editingAddons, setEditingAddons] = useState({})
  const [newService, setNewService] = useState(NEW_SVC)
  const [newAddon, setNewAddon] = useState({ name: '', unit_price: '', period: '', can_be_bonus: false })
  const [dragSvc, setDragSvc] = useState(null)
  const [confirmDel, setConfirmDel] = useState(null)   // {kind:'service'|'addon', id, name}
  const [busy, setBusy] = useState(false)
  const [bxOptions, setBxOptions] = useState([])       // услуги Битрикса (СП 1050) для привязки
  const [bxErr, setBxErr] = useState(false)            // Битрикс недоступен → селект работает по кэшу
  const [formats, setFormats] = useState([])           // справочник форматов размещения
  const [palette, setPalette] = useState([])           // допустимые цвета маркера услуги
  const [articles, setArticles] = useState([])         // реестр статей (для маппинга услуга→статья выручки)
  const [newFormat, setNewFormat] = useState({ name: '', group: '' })
  const [fmtOpen, setFmtOpen] = useState(null)         // id услуги с открытым пикером форматов

  useRefreshOnReturn(() => load(), { enabled: !Object.keys(editingServices).length && !Object.keys(editingAddons).length })
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('services')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
    load()
    loadBx()
  }, [])

  // Список битрикс-услуг для селекта привязки. Живой вызов Битрикса — грузим отдельно
  // и терпимо к ошибке: если недоступен, селект всё равно показывает текущую привязку.
  const loadBx = async () => {
    try { const r = await api.get('/sales/directories/services/bitrix', auth()); setBxOptions(r.data.items || []); setBxErr(false) }
    catch (e) { setBxErr(true) }
  }

  const load = async () => {
    setLoading(true)
    try {
      const [s, a, f, art] = await Promise.all([
        api.get('/sales/directories/services?only_active=false', auth()),
        api.get('/sales/directories/services/addons', auth()),
        api.get('/sales/directories/services/formats', auth()),
        api.get('/articles/', auth()),
      ])
      setServices(s.data.items || []); setAddons(a.data.items || []); setFormats(f.data.items || [])
      setPalette(s.data.palette || [])
      setArticles(Array.isArray(art.data) ? art.data : (art.data.items || []))
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
    finally { setLoading(false) }
  }

  // ── услуги ──
  const svcSeed = (s) => ({ name: s.name, group: s.group || '', placement_type: s.placement_type || '', calc_form: s.calc_form || '', separate_price: !!s.separate_price, unit_price: s.unit_price ?? '', unit_price_web: s.unit_price_web ?? '', unit_price_app: s.unit_price_app ?? '', constants: s.constants || {}, bx_id: s.bx_id || '', bx_title: s.bx_title || '', format_ids: (s.formats || []).map(f => f.id), revenue_article_id: s.revenue_article_id ?? '', color: s.color || '', doc_position: s.doc_position || '', rotation_type: s.rotation_type || '' })
  const bxTitleFor = (id) => (id ? (bxOptions.find(o => o.id === id)?.title || null) : null)
  const svcEd = (s) => editingServices[s.id] || svcSeed(s)
  const svcSet = (s, f, v) => setEditingServices(p => ({ ...p, [s.id]: { ...(p[s.id] || svcSeed(s)), [f]: v } }))
  const svcSetConst = (s, k, v) => setEditingServices(p => { const cur = p[s.id] || svcSeed(s); return { ...p, [s.id]: { ...cur, constants: { ...(cur.constants || {}), [k]: v } } } })
  const svcDirty = (id) => !!editingServices[id]
  const svcPayload = (ed) => ({ name: ed.name, group: ed.group || null, placement_type: ed.placement_type || null, calc_form: ed.calc_form || null, separate_price: !!ed.separate_price, unit_price: ed.separate_price ? null : numOrNull(ed.unit_price), unit_price_web: ed.separate_price ? numOrNull(ed.unit_price_web) : null, unit_price_app: ed.separate_price ? numOrNull(ed.unit_price_app) : null, constants: ed.constants || {}, bx_id: ed.bx_id || null, bx_title: ed.bx_id ? (bxTitleFor(ed.bx_id) || ed.bx_title || null) : null, format_ids: ed.format_ids ?? null, revenue_article_id: ed.revenue_article_id ? Number(ed.revenue_article_id) : null, color: ed.color || null, doc_position: ed.doc_position || null, rotation_type: ed.rotation_type || null })
  const saveService = async (id) => {
    const ed = editingServices[id]; if (!ed) return
    try { await api.put(`/sales/directories/services/${id}`, svcPayload(ed), auth()); setEditingServices(p => { const n = { ...p }; delete n[id]; return n }); await load(); loadBx() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка сохранения') }
  }
  const createService = async () => {
    if (!newService.name.trim()) { alert('Введите название услуги'); return }
    try { await api.post('/sales/directories/services', svcPayload({ ...newService, name: newService.name.trim() }), auth()); setNewService(NEW_SVC); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка создания') }
  }
  const toggleUse = async (id, on) => { try { await api.put(`/sales/directories/services/${id}/use`, { on }, auth()); await load() } catch (e) { alert('Ошибка') } }
  const reorder = async (toId) => {
    if (!dragSvc || dragSvc === toId) { setDragSvc(null); return }
    const ids = services.map(s => s.id); const from = ids.indexOf(dragSvc), to = ids.indexOf(toId)
    if (from < 0 || to < 0) { setDragSvc(null); return }
    ids.splice(to, 0, ids.splice(from, 1)[0])
    const byId = Object.fromEntries(services.map(s => [s.id, s])); setServices(ids.map(id => byId[id])); setDragSvc(null)
    try { await api.put('/sales/directories/services/reorder', { ids }, auth()) } catch (e) { load() }
  }

  // ── доп. услуги ──
  const addonSeed = (a) => ({ name: a.name, unit_price: a.unit_price ?? '', period: a.period || '', can_be_bonus: !!a.can_be_bonus })
  const addonEd = (a) => editingAddons[a.id] || addonSeed(a)
  const addonSet = (a, f, v) => setEditingAddons(p => ({ ...p, [a.id]: { ...(p[a.id] || addonSeed(a)), [f]: v } }))
  const addonDirty = (id) => !!editingAddons[id]
  const saveAddon = async (id) => {
    const ed = editingAddons[id]; if (!ed) return
    try { await api.put(`/sales/directories/services/addons/${id}`, { name: ed.name, unit_price: numOrNull(ed.unit_price), period: ed.period || null, can_be_bonus: !!ed.can_be_bonus }, auth()); setEditingAddons(p => { const n = { ...p }; delete n[id]; return n }); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
  }
  const createAddon = async () => {
    if (!newAddon.name.trim()) { alert('Введите название доп. услуги'); return }
    try { await api.post('/sales/directories/services/addons', { name: newAddon.name.trim(), unit_price: numOrNull(newAddon.unit_price), period: newAddon.period || null, can_be_bonus: !!newAddon.can_be_bonus }, auth()); setNewAddon({ name: '', unit_price: '', period: '', can_be_bonus: false }); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
  }
  const refreshFromBitrix = async () => {
    setBusy(true)
    try { const r = await api.post('/sales/directories/services/refresh', {}, auth()); alert(`Синхронизация с Битриксом:\n• добавлено новых: ${r.data.added}\n• привязано по имени: ${r.data.linked}\n• в Битриксе всего: ${r.data.bitrix_total}`); await load(); loadBx() }
    catch (e) { alert(e.response?.data?.detail || 'Обновление недоступно') }
    finally { setBusy(false) }
  }
  const runDel = async () => {
    if (!confirmDel) return
    try {
      if (confirmDel.kind === 'service') await api.delete(`/sales/directories/services/${confirmDel.id}/hard`, auth())
      else await api.delete(`/sales/directories/services/addons/${confirmDel.id}`, auth())
      setConfirmDel(null); await load()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка удаления') }
  }

  // ── форматы (справочник + M2M с услугой) ──
  const createFormat = async () => {
    if (!newFormat.name.trim()) { alert('Введите название формата'); return }
    try { await api.post('/sales/directories/services/formats', { name: newFormat.name.trim(), group: newFormat.group || null }, auth()); setNewFormat({ name: '', group: '' }); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
  }
  const deleteFormat = async (f) => {
    try { await api.delete(`/sales/directories/services/formats/${f.id}`, auth()); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка удаления') }
  }
  const toggleFormatActive = async (f) => {
    try { await api.put(`/sales/directories/services/formats/${f.id}`, { name: f.name, group: f.group, is_active: !f.is_active }, auth()); await load() }
    catch (e) { alert('Ошибка') }
  }
  // группировка форматов по категории (для пикеров и блока управления)
  const grouped = (list) => Object.entries(list.reduce((acc, f) => { const g = f.group || 'Прочее'; (acc[g] = acc[g] || []).push(f); return acc }, {})).map(([group, items]) => ({ group, items }))
  const fmtGroupsActive = grouped(formats.filter(f => f.is_active))
  const fmtGroupsAll = grouped(formats)
  // переключить формат у услуги (+ поправить дефолт placement_type)
  const toggleFmt = (s, fid) => {
    const ed = svcEd(s); const cur = ed.format_ids || []
    const f = formats.find(x => x.id === fid)
    const next = cur.includes(fid) ? cur.filter(x => x !== fid) : [...cur, fid]
    let def = ed.placement_type
    if (!cur.includes(fid) && !def) def = f?.name || ''                 // добавили первый → дефолт
    if (cur.includes(fid) && f && f.name === def) {                     // убрали дефолт → берём другой
      def = next.map(id => formats.find(x => x.id === id)?.name).filter(Boolean)[0] || ''
    }
    setEditingServices(p => ({ ...p, [s.id]: { ...(p[s.id] || svcSeed(s)), format_ids: next, placement_type: def } }))
  }
  const setDefaultFmt = (s, f) => { const ed = svcEd(s); if ((ed.format_ids || []).includes(f.id)) svcSet(s, 'placement_type', f.name) }

  // стили — общий модуль components/salesTableKit
  const placeOpts = (val) => (<>
    <option value="">— тип —</option>
    {PLACEMENT_TYPES.map(g => <optgroup key={g.cat} label={g.cat}>{g.items.map(it => <option key={it} value={it}>{it}</option>)}</optgroup>)}
    {val && !ALL_PLACEMENTS.includes(val) && <option value={val}>{val}</option>}
  </>)
  const formOpts = (val) => (<>
    <option value="">форма</option>
    {CALC_FORMS.map(f => <option key={f} value={f}>{f}</option>)}
    {val && !CALC_FORMS.includes(val) && <option value={val}>{val}</option>}
  </>)
  // статьи выручки из реестра статей, сгруппированы по группе (ВЫРУЧКА первой)
  const artGroups = Object.entries(articles.reduce((acc, a) => { const g = a.group || 'Без группы'; (acc[g] = acc[g] || []).push(a); return acc }, {}))
    .sort(([g1], [g2]) => (g1 === 'ВЫРУЧКА' ? -1 : g2 === 'ВЫРУЧКА' ? 1 : g1.localeCompare(g2)))
    .map(([group, items]) => ({ group, items }))
  const articleOpts = () => (<>
    <option value="">— статья —</option>
    {artGroups.map(g => <optgroup key={g.group} label={g.group}>{g.items.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</optgroup>)}
  </>)

  return (
    <>
      <Head><title>Услуги | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="services" />

        {/* Создание услуги */}
        <div style={{ ...card, padding: '14px 18px', marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="Название услуги" value={newService.name} onChange={e => setNewService(p => ({ ...p, name: e.target.value }))} style={{ ...inp, width: 220 }} />
          <select value={newService.placement_type} onChange={e => { const nm = e.target.value; const f = formats.find(x => x.name === nm); setNewService(p => ({ ...p, placement_type: nm, format_ids: f ? [f.id] : [] })) }} style={{ ...sel, width: 170 }} title="Дефолтный формат (остальные добавите в строке)">
            <option value="">— формат —</option>
            {fmtGroupsActive.map(g => <optgroup key={g.group} label={g.group}>{g.items.map(f => <option key={f.id} value={f.name}>{f.name}</option>)}</optgroup>)}
          </select>
          <select value={newService.calc_form} onChange={e => setNewService(p => ({ ...p, calc_form: e.target.value }))} style={{ ...sel, width: 100 }}>{formOpts(newService.calc_form)}</select>
          <select value={newService.revenue_article_id} onChange={e => setNewService(p => ({ ...p, revenue_article_id: e.target.value }))} style={{ ...sel, width: 170 }} title="Статья выручки">{articleOpts()}</select>
          <label style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
            <input type="checkbox" checked={newService.separate_price} onChange={e => setNewService(p => ({ ...p, separate_price: e.target.checked }))} />раздельный прайс
          </label>
          {newService.separate_price ? (<>
            <input type="number" placeholder="web цена" value={newService.unit_price_web} onChange={e => setNewService(p => ({ ...p, unit_price_web: e.target.value }))} style={{ ...inp, width: 100, textAlign: 'right' }} />
            <input type="number" placeholder="IN-App цена" value={newService.unit_price_app} onChange={e => setNewService(p => ({ ...p, unit_price_app: e.target.value }))} style={{ ...inp, width: 100, textAlign: 'right' }} />
          </>) : (
            <input type="number" placeholder="цена / ед" value={newService.unit_price} onChange={e => setNewService(p => ({ ...p, unit_price: e.target.value }))} style={{ ...inp, width: 110, textAlign: 'right' }} />
          )}
          {constsFor(newService.calc_form).map(c => (
            <span key={c.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--text-secondary)' }}>
              <span style={{ fontSize: 12 }}>{c.label}</span>
              <input type="number" value={newService.constants[c.key] ?? ''} onChange={e => setNewService(p => ({ ...p, constants: { ...p.constants, [c.key]: e.target.value } }))} style={{ ...inp, width: 70, textAlign: 'right' }} />
              <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{c.unit}</span>
            </span>
          ))}
          <button onClick={createService} style={primaryBtn}>+ Добавить</button>
          <button onClick={refreshFromBitrix} disabled={busy} style={{ ...primaryBtn, marginLeft: 'auto', background: 'var(--bg-card)', color: 'var(--accent)', border: '1px solid var(--border-card)', fontWeight: 600 }}>{busy ? 'Обновление…' : 'Обновить из Битрикса'}</button>
        </div>

        {/* Таблица услуг */}
        {loading ? <div style={{ color: 'var(--text-muted)', padding: 20 }}>Загрузка…</div> : (
          <div style={{ ...card, padding: '14px 18px', marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
              <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Услуги</h1>
              <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{services.length}</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1210 }}>
              <thead><tr>
                <th style={{ ...th, width: 24 }}></th>
                <th style={th}>Услуга</th>
                <th style={{ ...th, width: 210 }}>Услуга в Битриксе</th>
                <th style={{ ...th, width: 180 }}>Форматы</th>
                <th style={{ ...th, width: 90 }}>Форма</th>
                <th style={{ ...th, width: 110 }}>Конст.</th>
                <th style={{ ...th, textAlign: 'center', width: 56 }}>Разд.</th>
                <th style={{ ...th, width: 200 }}>Цена / ед</th>
                <th style={{ ...th, width: 120 }}>Группа</th>
                <th style={{ ...th, textAlign: 'center', width: 52 }} title="Цвет-маркер услуги на дашборде, в реестре и в МП">Цвет</th>
                <th style={{ ...th, width: 190 }}>Статья выручки</th>
                {/* Печатается в приложении к договору, в интерфейсе больше нигде не
                    показывается — отсюда и подписи «в ДС». */}
                <th style={{ ...th, width: 110 }} title="Тип ротации для медийных форматов — колонка документа">Ротация</th>
                <th style={{ ...th, width: 220 }} title="Текст колонки «Позиция» в приложении к договору">Позиция в ДС</th>
                <th style={{ ...th, textAlign: 'center', width: 44 }}>Исп.</th>
                <th style={{ ...th, width: 84 }}></th>
              </tr></thead>
              <tbody>
                {services.map(s => {
                  const ed = svcEd(s); const pt = ed.placement_type, cf = ed.calc_form
                  return (
                    <tr key={s.id} draggable onDragStart={() => setDragSvc(s.id)} onDragOver={e => e.preventDefault()} onDrop={() => reorder(s.id)}
                      style={{ opacity: s.is_active ? 1 : 0.5, background: dragSvc === s.id ? 'var(--accent-tint)' : undefined }}>
                      <td style={{ ...td, textAlign: 'center', cursor: 'grab', color: 'var(--text-faint)', userSelect: 'none' }} title="Перетащить">☰</td>
                      <td style={td}><input value={ed.name} onChange={e => svcSet(s, 'name', e.target.value)} style={{ ...ci, fontWeight: 600 }} /></td>
                      <td style={td}>
                        <select value={ed.bx_id || ''} onChange={e => svcSet(s, 'bx_id', e.target.value)} style={cs} title={ed.bx_title || ''}>
                          <option value="">— не привязано —</option>
                          {ed.bx_id && !bxOptions.some(o => o.id === ed.bx_id) && <option value={ed.bx_id}>{ed.bx_title || ed.bx_id} (тек.)</option>}
                          {bxOptions.map(o => {
                            const takenByOther = o.linked_to && o.id !== ed.bx_id
                            return <option key={o.id} value={o.id} disabled={takenByOther}>{o.title}{takenByOther ? ` — занята: ${o.linked_to}` : ''}</option>
                          })}
                        </select>
                        {bxErr && <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>Битрикс недоступен — по кэшу</div>}
                      </td>
                      <td style={td}>
                        <div onClick={() => setFmtOpen(s.id)} title="Выбрать форматы" style={{ ...cs, minHeight: 30, height: 'auto', display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center', cursor: 'pointer' }}>
                          {(ed.format_ids || []).length === 0 && <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>форматы…</span>}
                          {(ed.format_ids || []).map(fid => {
                            const f = formats.find(x => x.id === fid); if (!f) return null
                            const isDef = f.name === ed.placement_type
                            return <span key={fid} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11, padding: '1px 6px', borderRadius: 6, background: isDef ? 'var(--accent-tint)' : 'var(--bg-subtle)', color: isDef ? 'var(--accent)' : 'var(--text-secondary)' }}>{isDef && '★'}{f.name}</span>
                          })}
                        </div>
                      </td>
                      <td style={td}><select value={cf} onChange={e => svcSet(s, 'calc_form', e.target.value)} style={cs}><option value="">—</option>{CALC_FORMS.map(f => <option key={f} value={f}>{f}</option>)}{cf && !CALC_FORMS.includes(cf) && <option value={cf}>{cf}</option>}</select></td>
                      <td style={td}>{constsFor(cf).map(c => (
                        <span key={c.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
                          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{c.label}</span>
                          <input type="number" value={ed.constants?.[c.key] ?? ''} onChange={e => svcSetConst(s, c.key, e.target.value)} style={{ ...ci, textAlign: 'right', width: 52 }} />
                          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{c.unit}</span>
                        </span>
                      ))}</td>
                      <td style={{ ...td, textAlign: 'center' }}><input type="checkbox" checked={!!ed.separate_price} onChange={e => svcSet(s, 'separate_price', e.target.checked)} style={{ cursor: 'pointer' }} /></td>
                      <td style={td}>{ed.separate_price ? (
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>WEB</span>
                          <input type="number" value={ed.unit_price_web} onChange={e => svcSet(s, 'unit_price_web', e.target.value)} style={{ ...ci, textAlign: 'right', width: 70 }} />
                          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>IN-App</span>
                          <input type="number" value={ed.unit_price_app} onChange={e => svcSet(s, 'unit_price_app', e.target.value)} style={{ ...ci, textAlign: 'right', width: 70 }} />
                        </div>
                      ) : (
                        <input type="number" value={ed.unit_price} onChange={e => svcSet(s, 'unit_price', e.target.value)} style={{ ...ci, textAlign: 'right' }} />
                      )}</td>
                      <td style={td}><input value={ed.group} onChange={e => svcSet(s, 'group', e.target.value)} style={ci} /></td>
                      <td style={{ ...td, textAlign: 'center' }}>
                        <ColorPick value={ed.color} auto={s.color_effective} palette={palette}
                          onPick={v => svcSet(s, 'color', v)} />
                      </td>
                      <td style={td}><select value={ed.revenue_article_id ?? ''} onChange={e => svcSet(s, 'revenue_article_id', e.target.value)} style={cs} title="Статья выручки для моста сделка→операция">{articleOpts()}</select></td>
                      <td style={td}><select value={ed.rotation_type ?? ''} onChange={e => svcSet(s, 'rotation_type', e.target.value)} style={cs}><option value="">—</option><option value="Динамика">Динамика</option><option value="Статика">Статика</option></select></td>
                      <td style={td}><input value={ed.doc_position ?? ''} onChange={e => svcSet(s, 'doc_position', e.target.value)} title={ed.doc_position || 'Описание услуги для колонки «Позиция» документа'} placeholder="описание для документа" style={ci} /></td>
                      <td style={{ ...td, textAlign: 'center' }}><input type="checkbox" checked={!!s.is_active} onChange={e => toggleUse(s.id, e.target.checked)} style={{ cursor: 'pointer' }} /></td>
                      <td style={{ ...td, textAlign: 'center', whiteSpace: 'nowrap' }}>
                        {svcDirty(s.id) && <button onClick={() => saveService(s.id)} style={{ padding: '6px 10px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'var(--accent)', color: '#fff', marginRight: 6 }}>✓</button>}
                        <button onClick={() => setConfirmDel({ kind: 'service', id: s.id, name: s.name })} title="Удалить" style={{ padding: '6px 9px', borderRadius: 7, border: '1px solid var(--danger-tint)', cursor: 'pointer', fontSize: 13, background: 'var(--bg-card)', color: 'var(--danger)' }}>✕</button>
                      </td>
                    </tr>
                  )
                })}
                {!services.length && <tr><td colSpan={15} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Услуг нет — добавьте или нажмите «Обновить из Битрикса»</td></tr>}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {/* Форматы размещения (справочник) */}
        <div style={{ ...card, padding: '14px 18px', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Форматы</h2>
            <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{formats.length}</span>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>привязываются к услугам, выбираются в строке медиаплана</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
            <input placeholder="Новый формат" value={newFormat.name} onChange={e => setNewFormat(p => ({ ...p, name: e.target.value }))} style={{ ...inp, width: 200 }} />
            <input placeholder="Категория" list="fmt-groups" value={newFormat.group} onChange={e => setNewFormat(p => ({ ...p, group: e.target.value }))} style={{ ...inp, width: 160 }} />
            <datalist id="fmt-groups">{[...new Set(formats.map(f => f.group).filter(Boolean))].map(g => <option key={g} value={g} />)}</datalist>
            <button onClick={createFormat} style={primaryBtn}>+ Добавить формат</button>
          </div>
          {fmtGroupsAll.map(g => (
            <div key={g.group} style={{ marginBottom: 10 }}>
              <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>{g.group}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {g.items.map(f => (
                  <span key={f.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border-card)', background: f.is_active ? 'var(--bg-card)' : 'var(--bg-subtle)', opacity: f.is_active ? 1 : 0.55, fontSize: 12, color: 'var(--text-primary)' }}>
                    {f.name}
                    <span onClick={() => toggleFormatActive(f)} title={f.is_active ? 'Скрыть из выбора' : 'Вернуть в выбор'} style={{ cursor: 'pointer', color: 'var(--text-faint)', fontSize: 11 }}>{f.is_active ? 'скрыть' : 'вкл'}</span>
                    <span onClick={() => deleteFormat(f)} title="Удалить" style={{ cursor: 'pointer', color: 'var(--danger)', fontSize: 13 }}>✕</span>
                  </span>
                ))}
              </div>
            </div>
          ))}
          {!formats.length && <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Форматов нет — добавьте.</div>}
        </div>

        {/* Доп. услуги */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Доп. услуги</h2>
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>бонусные позиции идут со скидкой 100% (условия — позже)</span>
        </div>
        <div style={{ ...card, padding: '14px 18px', marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="Название доп. услуги" value={newAddon.name} onChange={e => setNewAddon(p => ({ ...p, name: e.target.value }))} style={{ ...inp, width: 280 }} />
          <input type="number" placeholder="цена / ед" value={newAddon.unit_price} onChange={e => setNewAddon(p => ({ ...p, unit_price: e.target.value }))} style={{ ...inp, width: 120, textAlign: 'right' }} />
          <input placeholder="период (напр. по итогам РК)" value={newAddon.period} onChange={e => setNewAddon(p => ({ ...p, period: e.target.value }))} style={{ ...inp, width: 200 }} />
          <label style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
            <input type="checkbox" checked={newAddon.can_be_bonus} onChange={e => setNewAddon(p => ({ ...p, can_be_bonus: e.target.checked }))} />может быть бонусом
          </label>
          <button onClick={createAddon} style={primaryBtn}>+ Добавить</button>
        </div>
        <div style={{ ...card, padding: '14px 18px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>
              <th style={th}>Доп. услуга</th>
              <th style={{ ...th, width: 140, textAlign: 'right' }}>Цена / ед</th>
              <th style={{ ...th, width: 190 }}>Период</th>
              <th style={{ ...th, width: 170, textAlign: 'center' }}>Может быть бонусом</th>
              <th style={{ ...th, width: 110 }}></th>
            </tr></thead>
            <tbody>
              {addons.map(a => {
                const ed = addonEd(a)
                return (
                  <tr key={a.id}>
                    <td style={td}><input value={ed.name} onChange={e => addonSet(a, 'name', e.target.value)} style={{ ...ci, fontWeight: 600 }} /></td>
                    <td style={{ ...td, textAlign: 'right' }}><input type="number" value={ed.unit_price} onChange={e => addonSet(a, 'unit_price', e.target.value)} style={{ ...ci, textAlign: 'right' }} /></td>
                    <td style={td}><input value={ed.period} onChange={e => addonSet(a, 'period', e.target.value)} placeholder="—" style={ci} /></td>
                    <td style={{ ...td, textAlign: 'center' }}><input type="checkbox" checked={!!ed.can_be_bonus} onChange={e => addonSet(a, 'can_be_bonus', e.target.checked)} style={{ cursor: 'pointer' }} /></td>
                    <td style={{ ...td, textAlign: 'center', whiteSpace: 'nowrap' }}>
                      {addonDirty(a.id) && <button onClick={() => saveAddon(a.id)} style={{ padding: '6px 10px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'var(--accent)', color: '#fff', marginRight: 6 }}>✓</button>}
                      <button onClick={() => setConfirmDel({ kind: 'addon', id: a.id, name: a.name })} title="Удалить" style={{ padding: '6px 9px', borderRadius: 7, border: '1px solid var(--danger-tint)', cursor: 'pointer', fontSize: 13, background: 'var(--bg-card)', color: 'var(--danger)' }}>✕</button>
                    </td>
                  </tr>
                )
              })}
              {!addons.length && <tr><td colSpan={5} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Доп. услуг нет</td></tr>}
            </tbody>
          </table>
        </div>

        {fmtOpen != null && (() => {
          const s = services.find(x => x.id === fmtOpen); if (!s) return null
          const ed = svcEd(s)
          return (
            <div {...overlayClose(() => setFmtOpen(null))} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
              <div onClick={e => e.stopPropagation()} style={{ ...card, padding: '20px 22px', maxWidth: 460, width: '100%', maxHeight: '80vh', overflowY: 'auto' }}>
                <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>Форматы услуги</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>«{s.name}»</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 14 }}>Отметьте форматы · ★ — дефолтный (подставляется в строку МП)</div>
                {fmtGroupsActive.map(g => (
                  <div key={g.group} style={{ marginBottom: 8 }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', padding: '4px 0 2px' }}>{g.group}</div>
                    {g.items.map(f => {
                      const on = (ed.format_ids || []).includes(f.id); const isDef = f.name === ed.placement_type
                      return (
                        <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 8, cursor: 'pointer', background: on ? 'var(--accent-tint)' : 'transparent' }}>
                          <input type="checkbox" checked={on} onChange={() => toggleFmt(s, f.id)} />
                          <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{f.name}</span>
                          <span onClick={e => { e.preventDefault(); e.stopPropagation(); setDefaultFmt(s, f) }} title={on ? 'Сделать дефолтом' : 'Сначала отметьте формат'} style={{ cursor: on ? 'pointer' : 'default', color: isDef ? 'var(--accent)' : 'var(--text-faint)', fontSize: 15, opacity: on ? 1 : 0.35 }}>★</span>
                        </label>
                      )
                    })}
                  </div>
                ))}
                {!formats.length && <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: 8 }}>Форматов нет — добавьте в блоке «Форматы» ниже.</div>}
                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
                  <button onClick={() => setFmtOpen(null)} style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Готово</button>
                  {svcDirty(s.id) && <button onClick={() => { saveService(s.id); setFmtOpen(null) }} style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 700 }}>Сохранить</button>}
                </div>
              </div>
            </div>
          )
        })()}

        {confirmDel && (
          <div {...overlayClose(() => setConfirmDel(null))} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <div onClick={e => e.stopPropagation()} style={{ ...card, padding: '24px 26px', maxWidth: 420, width: '100%' }}>
              <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>Точно удалить?</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20 }}>Удалить {confirmDel.kind === 'addon' ? 'доп. услугу' : 'услугу'} «<b>{confirmDel.name}</b>»? Действие необратимо — точно надо?</div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button onClick={() => setConfirmDel(null)} style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Отмена</button>
                <button onClick={runDel} style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--danger)', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 700 }}>Удалить</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}


// Пикер цвета услуги: выбор из палитры, а не свободный hex — иначе через год
// в справочнике будет сорок оттенков серого и маркеры перестанут различаться.
// «Авто» — пустое значение: цвет раздаётся по порядку справочника на бэкенде.
// Компонент объявлен на модульном уровне: внутри страницы он пересоздавался бы
// на каждый рендер и закрывался бы при первом же клике.
function ColorPick({ value, auto, palette, onPick }) {
  const [open, setOpen] = useState(false)
  const shown = value || auto || 'var(--text-faint)'
  // Закрытие по клику мимо: без него открытая палитра висела, пока не выберут цвет,
  // и можно было открыть сразу несколько. Клик внутри портала гасится самим
  // PortalPopover, поэтому проверка на data-pop-root здесь не нужна.
  useEffect(() => {
    if (!open) return
    const off = (e) => { if (!e.target.closest('[data-color-pick]')) setOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [open])
  return (
    // PortalPopover, а не position:absolute: панель в ячейке таблицы с overflow
    // обрезалась бы краем таблицы (правило кита про дропдауны).
    <span data-color-pick style={{ position: 'relative', display: 'inline-block' }}>
      <span onClick={() => setOpen(o => !o)} title={value ? `выбран ${value}` : `авто ${auto || ''}`}
        style={{ display: 'inline-block', width: 18, height: 18, borderRadius: 5, cursor: 'pointer',
          background: shown, border: value ? '2px solid var(--text-primary)' : '1px solid var(--border-card)' }} />
      <PortalPopover open={open} minWidth={168} align="left"
        style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 20px)', gap: 6, padding: 8 }}>
        {(palette || []).map(c => (
          <span key={c} onClick={() => { onPick(c); setOpen(false) }} title={c}
            style={{ width: 20, height: 20, borderRadius: 5, background: c, cursor: 'pointer',
              border: value === c ? '2px solid var(--text-primary)' : '1px solid var(--border-inner)' }} />
        ))}
        <span onClick={() => { onPick(''); setOpen(false) }} title="Авто по порядку справочника"
          style={{ gridColumn: '1 / -1', textAlign: 'center', fontSize: 11, color: 'var(--accent)', cursor: 'pointer', paddingTop: 2 }}>авто</span>
      </PortalPopover>
    </span>
  )
}
