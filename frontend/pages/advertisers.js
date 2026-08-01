import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const EMPTY = { short_name: '', name_en: '', name_ru: '', website: '', inn: '' }

export default function Advertisers() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [editId, setEditId] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [brandName, setBrandName] = useState('')
  const [dupes, setDupes] = useState([])
  const [showDupes, setShowDupes] = useState(false)
  const [showForm, setShowForm] = useState(false)

  const mayEdit = can(perms, 'dir_advertisers', 'edit')

  const loadDupes = async () => {
    try {
      const r = await api.get('/sales/directories/producers/duplicates', auth())
      setDupes(r.data.pairs); setShowDupes(true)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить дубли') }
  }

  // keepId остаётся, dropId вливается и исчезает
  const merge = async (keepId, dropId, keepName, dropName) => {
    if (!window.confirm(`Влить «${dropName}» в «${keepName}»?\n\nБренды и сделки перейдут на «${keepName}», «${dropName}» будет удалён.`)) return
    setError('')
    try {
      const r = await api.post(`/sales/directories/producers/${keepId}/merge`, { source_id: dropId }, auth())
      flash(r.data.message)
      setDupes(dupes.filter(p => !(p.keep.id === keepId && p.drop.id === dropId) && !(p.keep.id === dropId && p.drop.id === keepId)))
      load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось слить') }
  }

  const deleteBrand = async (brandId, name) => {
    if (!window.confirm(`Удалить бренд «${name}»? Сделки, ссылавшиеся на него, потеряют бренд.`)) return
    setError('')
    try {
      const r = await api.delete(`/sales/directories/brands/${brandId}/hard`, auth())
      flash(r.data.message); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось удалить бренд') }
  }

  // Переименование и перенос — один эндпойнт PUT /brands/{id} (name + advertiser_id)
  const saveBrand = async (brandId, name, advertiserId) => {
    setError('')
    try {
      await api.put(`/sales/directories/brands/${brandId}`, { name, advertiser_id: advertiserId }, auth())
      setEditBrand(null); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить бренд') }
  }

  const [editBrand, setEditBrand] = useState(null)   // { id, name } — правка имени
  const [moveBrand, setMoveBrand] = useState(null)   // { id, name } — одиночный перенос
  const [moveQuery, setMoveQuery] = useState('')
  const [sel, setSel] = useState({})                 // { brandId: name } — мультивыбор
  const [bulkMove, setBulkMove] = useState(false)    // открыт поиск для пакетного переноса
  const [bulkQuery, setBulkQuery] = useState('')

  const [attachToAdv, setAttachToAdv] = useState(null)  // id рекламодателя, к которому прикрепляем контрагента
  const [cpQueryAdv, setCpQueryAdv] = useState('')
  const [cpsAdv, setCpsAdv] = useState([])

  // Выбор рекламодателей (производителей) для схлопывания — отдельно от брендов
  const [selAdv, setSelAdv] = useState({})   // { id: {name, deals} }
  const selAdvIds = Object.keys(selAdv).map(Number)
  const toggleAdv = (a) => {
    setSel({})   // взаимоисключение: либо производители, либо бренды
    setSelAdv(s => {
      const n = { ...s }
      if (n[a.id]) delete n[a.id]; else n[a.id] = { name: a.short_name || a.name, deals: a.deals }
      return n
    })
  }

  const mergeSelectedProducers = async () => {
    if (selAdvIds.length < 2) return
    // оставляем того, у кого больше сделок — обычно это основная запись
    const keepId = selAdvIds.slice().sort((x, y) => (selAdv[y].deals) - (selAdv[x].deals))[0]
    const keepName = selAdv[keepId].name
    const dropIds = selAdvIds.filter(id => id !== keepId)
    const dropNames = dropIds.map(id => selAdv[id].name).join(', ')
    if (!window.confirm(
      `Схлопнуть в «${keepName}»?\n\nВольются: ${dropNames}\n\n` +
      `Их бренды и сделки перейдут на «${keepName}», сами записи удалятся.`)) return
    setError('')
    try {
      // бэкенд сливает по одному источнику; идём последовательно
      for (const dropId of dropIds) {
        await api.post(`/sales/directories/producers/${keepId}/merge`, { source_id: dropId }, auth())
      }
      flash(`Схлопнуто ${dropIds.length} в «${keepName}»`)
      setSelAdv({}); load()
    } catch (e) {
      const d = e.response?.data?.detail
      setError((Array.isArray(d) ? JSON.stringify(d) : d) || (e.response ? `HTTP ${e.response.status}` : `Сеть: ${e.message}`))
    }
  }

  const selIds = Object.keys(sel).map(Number)
  const toggleSel = (id, name) => {
    setSelAdv({})   // взаимоисключение с выбором производителей
    setSel(s => {
      const n = { ...s }
      if (n[id]) delete n[id]; else n[id] = name
      return n
    })
  }
  const clearSel = () => { setSel({}); setBulkMove(false); setBulkQuery('') }

  const moveSelected = async (advertiserId) => {
    setError('')
    try {
      const r = await api.post('/sales/directories/brands/move',
        { brand_ids: selIds, advertiser_id: advertiserId }, auth())
      flash(r.data.message); clearSel(); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось перенести') }
  }

  const mergeSelected = async () => {
    if (selIds.length < 2) return
    // оставляем бренд с самым коротким именем (обычно каноничное написание)
    const keepId = selIds.slice().sort((a, b) => sel[a].length - sel[b].length)[0]
    const keepName = sel[keepId]
    if (!window.confirm(`Схлопнуть ${selIds.length} брендов в «${keepName}»?\n\nОстальные удаляются, их сделки переходят на «${keepName}».`)) return
    setError('')
    try {
      const r = await api.post('/sales/directories/brands/merge',
        { keep_id: keepId, drop_ids: selIds.filter(id => id !== keepId) }, auth())
      flash(r.data.message); clearSel(); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось схлопнуть') }
  }

  const load = async () => {
    setLoading(true); setError('')
    try {
      const res = await api.get('/sales/directories/producers', { params: { only_active: false }, ...auth() })
      setItems(res.data.items)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить справочник') }
    finally { setLoading(false) }
  }

  // Поиск контрагентов для прикрепления к рекламодателю
  useEffect(() => {
    const q = cpQueryAdv.trim()
    if (!q) { setCpsAdv([]); return }
    const t = setTimeout(async () => {
      try {
        const r = await api.get('/counterparties/', { params: { search: q, limit: 30 }, ...auth() })
        const list = Array.isArray(r.data) ? r.data : (r.data.items || [])
        setCpsAdv(list.map(x => ({ id: x.id, name: x.name })).filter(x => x.name))
      } catch (e) { /* молчим */ }
    }, 250)
    return () => clearTimeout(t)
  }, [cpQueryAdv])

  const attachCp = async (advId, cpId) => {
    setError('')
    try {
      await api.post(`/sales/directories/producers/${advId}/counterparties`,
        { counterparty_id: cpId }, auth())
      setAttachToAdv(null); setCpQueryAdv(''); flash('Юрлицо прикреплено'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось прикрепить') }
  }

  const detachCp = async (advId, cpId) => {
    setError('')
    try {
      await api.delete(`/sales/directories/producers/${advId}/counterparties/${cpId}`, auth())
      flash('Юрлицо откреплено'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось открепить') }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (msg) => { setOk(msg); setTimeout(() => setOk(''), 2500) }

  const cancelForm = () => { setEditId(null); setForm(EMPTY); setShowForm(false); setError('') }

  const save = async () => {
    setError('')
    // достаточно любого из трёх названий
    if (!form.short_name.trim() && !form.name_en.trim() && !form.name_ru.trim()) {
      setError('Заполните хотя бы одно название')
      return
    }
    try {
      if (editId) {
        await api.put(`/sales/directories/producers/${editId}`, form, auth())
        flash('Рекламодатель обновлён')
        setEditId(null); setForm(EMPTY)
      } else {
        await api.post('/sales/directories/producers', form, auth())
        flash('Рекламодатель создан')
        cancelForm()
      }
      load()
    } catch (e) {
      // диагностический текст: показываем статус и настоящую причину,
      // а не общую заглушку — чтобы было видно, HTTP-ошибка это или сетевая
      const d = e.response?.data?.detail
      const detail = Array.isArray(d) ? JSON.stringify(d) : d
      setError(detail || (e.response ? `HTTP ${e.response.status}` : `Сеть: ${e.message}`))
    }
  }

  const addBrand = async (advertiserId) => {
    if (!brandName.trim()) return
    setError('')
    try {
      await api.post('/sales/directories/brands', { name: brandName, advertiser_id: advertiserId }, auth())
      setBrandName(''); flash('Бренд добавлен'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось добавить бренд') }
  }

  const startEdit = (a) => {
    setEditId(a.id)
    setForm({
      short_name: a.short_name || a.name || '',
      name_en: a.name_en || '', name_ru: a.name_ru || '',
      website: a.website || '', inn: a.inn || '',
    })
    // без прокрутки в шапку — правка идёт прямо в строке
  }

  const filtered = items.filter(a => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [a.short_name, a.name, a.name_en, a.name_ru].some(v => (v || '').toLowerCase().includes(q))
      || (a.brands || []).some(b => b.name.toLowerCase().includes(q))
  })

  const inp = {
    padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit',
  }
  const btn = (primary) => ({
    padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500,
    background: primary ? 'var(--accent)' : 'var(--bg-subtle)', color: primary ? '#fff' : 'inherit',
  })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)', verticalAlign: 'top' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  return (
    <>
      <Head><title>Рекламодатели</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 24px 50px' }}>

        <DirectoryTabs active="advertisers" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 16 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Рекламодатели</h1>
          {mayEdit && <button style={btn(false)} onClick={() => showDupes ? setShowDupes(false) : loadDupes()}>
            {showDupes ? 'Скрыть дубли' : 'Найти дубли'}
          </button>}
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
        </div>

        {/* Строка поиска + кнопка добавления */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: showForm ? 0 : 12 }}>
          <input style={{ ...inp, width: 300 }} placeholder="поиск по названию или бренду"
            value={search} onChange={e => setSearch(e.target.value)} />
          {mayEdit && !editId && (
            <button style={btn(showForm)}
              onClick={() => showForm ? cancelForm() : setShowForm(true)}>
              {showForm ? 'Отмена' : '+ Добавить'}
            </button>
          )}
        </div>

        {/* Форма добавления — раскрывается под строкой поиска */}
        {mayEdit && showForm && !editId && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderTop: 'none', borderRadius: '0 0 var(--radius-card) var(--radius-card)',
            padding: '14px 16px', marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новый рекламодатель</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 170 }} placeholder="Короткое" autoFocus
                value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 180 }} placeholder="Англ"
                value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 180 }} placeholder="Русское"
                value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 190 }} placeholder="сайт"
                value={form.website} onChange={e => setForm({ ...form, website: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 130 }} placeholder="ИНН"
                value={form.inn} onChange={e => setForm({ ...form, inn: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <button style={btn(true)} onClick={save}>Добавить</button>
              <button style={btn(false)} onClick={cancelForm}>Отмена</button>
            </div>
          </div>
        )}

        {showDupes && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', padding: '12px 14px', marginBottom: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Возможные дубли ({dupes.length}) — проверьте каждую пару, направление можно поменять
            </div>
            {!dupes.length && <div style={{ fontSize: 13, color: 'var(--muted)' }}>Дублей не найдено</div>}
            {dupes.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                padding: '6px 0', borderBottom: '1px solid var(--border-row)', fontSize: 13 }}>
                <span style={{ flex: 1, minWidth: 260 }}>
                  оставить <b>{p.keep.name}</b> <span style={{ color: 'var(--muted)' }}>({p.keep.brands} бр.)</span>
                  {' ← '}
                  влить <b>{p.drop.name}</b> <span style={{ color: 'var(--muted)' }}>({p.drop.brands} бр.)</span>
                </span>
                <button style={{ ...btn(true), padding: '4px 12px', fontSize: 12 }}
                  onClick={() => merge(p.keep.id, p.drop.id, p.keep.name, p.drop.name)}>Слить →</button>
                <button style={{ ...btn(false), padding: '4px 12px', fontSize: 12 }}
                  onClick={() => merge(p.drop.id, p.keep.id, p.drop.name, p.keep.name)}
                  title="Поменять направление: оставить другого">⇄</button>
              </div>
            ))}
          </div>
        )}

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)',
          marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'visible' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>
                <th style={{ ...th, width: 28 }}></th>
                <th style={th}>BX_ID</th>
                <th style={th}>Короткое</th>
                <th style={th}>Англ</th>
                <th style={th}>Русское</th>
                <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                <th style={th}>Сайт</th>
                <th style={th}>Бренды</th>
                <th style={th}>Юрлица</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{
                    opacity: a.is_active ? 1 : 0.5,
                    background: selAdv[a.id] ? 'var(--accent-tint)' : undefined,
                  }}>
                    <td style={{ ...td, textAlign: 'center' }}>
                      {mayEdit && editId !== a.id && (
                        <input type="checkbox" checked={!!selAdv[a.id]} onChange={() => toggleAdv(a)}
                          style={{ cursor: 'pointer' }} />
                      )}
                    </td>
                    <td style={{ ...td, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
                      {a.bx_id
                        ? <a href={`https://simb-ad.bitrix24.ru/crm/company/details/${a.bx_id}/`}
                             target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}
                             title="Открыть рекламодателя в Битрикс24">{a.bx_id}</a>
                        : dash}
                    </td>
                    {editId === a.id ? (
                      <>
                        <td style={td}>
                          <input style={{ ...inp, width: 140, padding: '3px 7px' }} placeholder="Короткое" autoFocus
                            value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })} />
                        </td>
                        <td style={td}>
                          <input style={{ ...inp, width: 140, padding: '3px 7px' }} placeholder="Англ"
                            value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })} />
                        </td>
                        <td style={td}>
                          <input style={{ ...inp, width: 140, padding: '3px 7px' }} placeholder="Русское"
                            value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })} />
                        </td>
                        <td style={{ ...td, textAlign: 'right', color: 'var(--muted)' }}>{a.deals}</td>
                        <td style={td}>
                          <input style={{ ...inp, width: 140, padding: '3px 7px' }} placeholder="сайт"
                            value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} />
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ ...td, fontWeight: 600 }}>{a.short_name || a.name || dash}</td>
                        <td style={td}>{a.name_en || dash}</td>
                        <td style={td}>{a.name_ru || dash}</td>
                        <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                          {a.deals > 0
                            ? <a href={`/sales?advertiser_id=${a.id}`} target="_blank" rel="noreferrer"
                                 style={{ color: 'var(--accent)', textDecoration: 'none' }}
                                 title="Открыть сделки рекламодателя в реестре">{a.deals}</a>
                            : a.deals}
                        </td>
                        <td style={td}>
                          {a.website
                            ? <a href={a.website.startsWith('http') ? a.website : `https://${a.website}`}
                                 target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{a.website}</a>
                            : dash}
                        </td>
                      </>
                    )}
                    <td style={td}>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                        {(a.brands || []).map(b => (
                          editBrand?.id === b.id ? (
                            <input key={b.id} autoFocus defaultValue={b.name}
                              style={{ ...inp, width: 150, padding: '2px 6px', fontSize: 12 }}
                              onBlur={e => saveBrand(b.id, e.target.value, a.id)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') saveBrand(b.id, e.target.value, a.id)
                                if (e.key === 'Escape') setEditBrand(null)
                              }} />
                          ) : (
                            <span key={b.id}
                              onDoubleClick={() => mayEdit && setEditBrand({ id: b.id, name: b.name })}
                              title={mayEdit ? 'Двойной клик — переименовать, галочка — выбрать' : b.name}
                              style={{
                                background: sel[b.id] ? 'var(--accent-tint)' : 'var(--bg-subtle)',
                                border: sel[b.id] ? '1px solid var(--accent)' : '1px solid transparent',
                                borderRadius: 'var(--radius-badge)',
                                padding: '2px 8px', fontSize: 12, display: 'inline-flex', gap: 6, alignItems: 'center',
                              }}>
                              {mayEdit && <input type="checkbox" checked={!!sel[b.id]}
                                onChange={() => toggleSel(b.id, b.name)} style={{ cursor: 'pointer', margin: 0 }} />}
                              {b.name}
                              {mayEdit && <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 700 }}
                                onClick={() => { setMoveBrand({ id: b.id, name: b.name }); setMoveQuery('') }}
                                title="Перенести к другому рекламодателю">⇄</span>}
                              {mayEdit && <span style={{ cursor: 'pointer', color: 'var(--danger)', fontWeight: 700 }}
                                onClick={() => deleteBrand(b.id, b.name)} title="Удалить бренд">×</span>}
                            </span>
                          )
                        ))}
                        {!a.brands?.length && dash}
                      </div>
                      {moveBrand && (a.brands || []).some(b => b.id === moveBrand.id) && (
                        <div style={{ marginTop: 8, position: 'relative' }}>
                          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 4 }}>
                            Перенести «{moveBrand.name}» к рекламодателю:
                          </div>
                          <input autoFocus style={{ ...inp, width: 280 }} placeholder="поиск рекламодателя"
                            value={moveQuery} onChange={e => setMoveQuery(e.target.value)} />
                          <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--muted)', cursor: 'pointer' }}
                            onClick={() => setMoveBrand(null)}>отмена</span>
                          {moveQuery.trim() && (
                            <div style={{ position: 'absolute', top: '100%', left: 0, zIndex: 10, marginTop: 2,
                              background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                              borderRadius: 'var(--radius-card-sm)', boxShadow: 'var(--shadow-card)',
                              maxHeight: 260, overflowY: 'auto', minWidth: 300 }}>
                              {items.filter(x => x.id !== a.id &&
                                  [x.name, x.name_en, x.name_ru].some(v => (v || '').toLowerCase().includes(moveQuery.trim().toLowerCase())))
                                .slice(0, 30).map(x => (
                                <div key={x.id} onClick={() => { saveBrand(moveBrand.id, moveBrand.name, x.id); setMoveBrand(null) }}
                                  style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                                  {[x.name_en, x.name_ru].filter(Boolean).join(' / ') || x.name}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {expanded === a.id && mayEdit && (
                        <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                          <input style={{ ...inp, width: 190 }} placeholder="название бренда" autoFocus
                            value={brandName} onChange={e => setBrandName(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') addBrand(a.id) }} />
                          <button style={btn(true)} onClick={() => addBrand(a.id)}>Добавить</button>
                        </div>
                      )}
                    </td>
                    {/* Юрлица — прямой договор */}
                    <td style={td}>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                        {(a.counterparties || []).map(c => (
                          <span key={c.counterparty_id} style={{
                            background: 'var(--bg-subtle)', borderRadius: 'var(--radius-badge)',
                            padding: '2px 8px', fontSize: 12, display: 'inline-flex', gap: 6, alignItems: 'center',
                          }}>
                            {c.name}
                            {mayEdit && editId !== a.id && (
                              <span style={{ cursor: 'pointer', color: 'var(--danger)', fontWeight: 700 }}
                                onClick={() => detachCp(a.id, c.counterparty_id)} title="Открепить">×</span>
                            )}
                          </span>
                        ))}
                        {!a.counterparties?.length && dash}
                      </div>
                      {attachToAdv === a.id && editId !== a.id && mayEdit && (
                        <div style={{ marginTop: 8, position: 'relative' }}>
                          <input autoFocus style={{ ...inp, width: 280 }} placeholder="поиск контрагента"
                            value={cpQueryAdv} onChange={e => setCpQueryAdv(e.target.value)} />
                          {cpQueryAdv.trim() && (
                            <div style={{ position: 'absolute', top: '100%', left: 0, zIndex: 10, marginTop: 2,
                              background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                              borderRadius: 'var(--radius-card-sm)', boxShadow: 'var(--shadow-card)',
                              maxHeight: 240, overflowY: 'auto', minWidth: 280 }}>
                              {cpsAdv.map(c => (
                                <div key={c.id} onClick={() => attachCp(a.id, c.id)}
                                  style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                                  {c.name}
                                </div>
                              ))}
                              {!cpsAdv.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--muted)' }}>не найдено</div>}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {mayEdit && editId === a.id ? (
                        <>
                          <button style={{ ...btn(true), padding: '3px 10px', fontSize: 12, marginRight: 6 }}
                            onClick={save}>Сохранить</button>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }}
                            onClick={() => { setEditId(null); setForm(EMPTY); setError('') }}>Отмена</button>
                          {/* ошибка сохранения — прямо у строки, а не только вверху страницы */}
                          {error && <div style={{ color: 'var(--danger)', fontSize: 11.5, marginTop: 4,
                            whiteSpace: 'normal', maxWidth: 260, textAlign: 'left' }}>{error}</div>}
                        </>
                      ) : mayEdit && (
                        <>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12, marginRight: 6 }}
                            onClick={() => { setAttachToAdv(attachToAdv === a.id ? null : a.id); setCpQueryAdv('') }}>
                            + контрагент
                          </button>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12, marginRight: 6 }}
                            onClick={() => { setExpanded(expanded === a.id ? null : a.id); setBrandName('') }}>
                            + бренд
                          </button>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }}
                            onClick={() => startEdit(a)}>Изменить</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr><td colSpan={9} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
                    Ничего не найдено
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Плавающая панель действий над выбранными брендами */}
        {selAdvIds.length > 0 && (
          <div style={{ position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)',
            zIndex: 50, background: 'var(--bg-card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)',
            padding: '12px 16px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Выбрано производителей: {selAdvIds.length}</span>
            <button style={{ ...btn(true), padding: '6px 14px', fontSize: 13 }}
              disabled={selAdvIds.length < 2} onClick={mergeSelectedProducers}>Схлопнуть в один</button>
            <button style={{ ...btn(false), padding: '6px 14px', fontSize: 13 }}
              onClick={() => setSelAdv({})}>Сбросить</button>
            {selAdvIds.length >= 2 && (
              <span style={{ fontSize: 11.5, color: 'var(--muted)', width: '100%' }}>
                оставим того, у кого больше сделок
              </span>
            )}
          </div>
        )}

        {selIds.length > 0 && (
          <div style={{ position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)',
            zIndex: 50, background: 'var(--bg-card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)',
            padding: '12px 16px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Выбрано брендов: {selIds.length}</span>
            <button style={{ ...btn(true), padding: '6px 14px', fontSize: 13 }}
              onClick={() => { setBulkMove(true); setBulkQuery('') }}>Перенести пачкой</button>
            <button style={{ ...btn(true), padding: '6px 14px', fontSize: 13 }}
              disabled={selIds.length < 2} onClick={mergeSelected}>Схлопнуть в один</button>
            <button style={{ ...btn(false), padding: '6px 14px', fontSize: 13 }} onClick={clearSel}>Сбросить</button>

            {bulkMove && (
              <div style={{ position: 'relative', width: '100%', marginTop: 8 }}>
                <input autoFocus style={{ ...inp, width: 300 }} placeholder="перенести к рекламодателю — поиск"
                  value={bulkQuery} onChange={e => setBulkQuery(e.target.value)} />
                {bulkQuery.trim() && (
                  <div style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: 2, zIndex: 60,
                    background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                    borderRadius: 'var(--radius-card-sm)', boxShadow: 'var(--shadow-card)',
                    maxHeight: 240, overflowY: 'auto', minWidth: 300 }}>
                    {items.filter(x => [x.name, x.name_en, x.name_ru].some(v =>
                        (v || '').toLowerCase().includes(bulkQuery.trim().toLowerCase())))
                      .slice(0, 30).map(x => (
                      <div key={x.id} onClick={() => moveSelected(x.id)}
                        style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                        {[x.name_en, x.name_ru].filter(Boolean).join(' / ') || x.name}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
