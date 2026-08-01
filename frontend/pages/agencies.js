import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const EMPTY = { short_name: '', name_en: '', name_ru: '', holding: '' }

export default function Agencies() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [cps, setCps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [editId, setEditId] = useState(null)
  const [editFull, setEditFull] = useState('')
  const [skEditId, setSkEditId] = useState(null)
  const saveSk = async (id, raw) => {
    setSkEditId(null)
    const v = parseFloat(String(raw).replace(',', '.'))
    if (isNaN(v) || v < 0 || v > 100) return
    try {
      await api.put(`/sales/directories/agencies/${id}/sk`, { sk_percent: v }, auth())
      setItems(prev => prev.map(x => (x.id === id ? { ...x, sk_percent: v } : x)))
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить СК') }
  }
  const [showForm, setShowForm] = useState(false)
  const [attachTo, setAttachTo] = useState(null)   // agency id, для которого открыт выбор контрагента
  const [cpQuery, setCpQuery] = useState('')

  const mayEdit = can(perms, 'dir_agencies', 'edit')

  // Мультивыбор и склейка дублей агентств
  const [selAg, setSelAg] = useState({})   // { id: {name, deals} }
  const selAgIds = Object.keys(selAg).map(Number)
  const toggleAg = (a) => setSelAg(s => {
    const n = { ...s }
    if (n[a.id]) delete n[a.id]; else n[a.id] = { name: a.short_name || a.name, deals: a.deals }
    return n
  })
  const mergeSelectedAgencies = async () => {
    if (selAgIds.length < 2) return
    const keepId = selAgIds.slice().sort((x, y) => selAg[y].deals - selAg[x].deals)[0]  // оставляем с макс. сделками
    const keepName = selAg[keepId].name
    const dropIds = selAgIds.filter(id => id !== keepId)
    if (!window.confirm(
      `Схлопнуть в «${keepName}»?\n\nВольются: ${dropIds.map(id => selAg[id].name).join(', ')}\n\n` +
      `Их юрлица и сделки перейдут на «${keepName}», сами записи удалятся.`)) return
    setError('')
    try {
      for (const dropId of dropIds) {   // бэкенд сливает по одному источнику
        await api.post(`/sales/directories/agencies/${keepId}/merge`, { source_id: dropId }, auth())
      }
      flash(`Схлопнуто ${dropIds.length} в «${keepName}»`)
      setSelAg({}); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось слить агентства') }
  }

  const load = async () => {
    setLoading(true); setError('')
    try {
      const a = await api.get('/sales/directories/agencies', { params: { only_active: false }, ...auth() })
      setItems(a.data.items)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить справочник') }
    finally { setLoading(false) }
  }

  // Поиск контрагентов — на сервере: их 207, а эндпойнт отдаёт страницами по 200,
  // поэтому грузить всё на клиент и фильтровать локально нельзя — часть выпадает.
  useEffect(() => {
    const q = cpQuery.trim()
    if (!q) { setCps([]); return }
    const t = setTimeout(async () => {
      try {
        const r = await api.get('/counterparties/', { params: { search: q, limit: 30 }, ...auth() })
        const list = Array.isArray(r.data) ? r.data : (r.data.items || [])
        setCps(list.map(x => ({ id: x.id, name: x.name })).filter(x => x.name))
      } catch (e) { /* поиск не критичен, молчим */ }
    }, 250)
    return () => clearTimeout(t)
  }, [cpQuery])

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const cancelForm = () => {
    setEditId(null)
    setEditFull('')
    setForm(EMPTY)
    setShowForm(false)
    setError('')
  }

  const save = async () => {
    setError('')
    if (!form.short_name.trim() && !form.name_en.trim() && !form.name_ru.trim()) {
      setError('Заполните хотя бы одно название'); return
    }
    try {
      if (editId) { await api.put(`/sales/directories/agencies/${editId}`, form, auth()); flash('Обновлено') }
      else { await api.post('/sales/directories/agencies', form, auth()); flash('Создано') }
      cancelForm(); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
  }

  const attach = async (agencyId, cpId) => {
    setError('')
    try {
      await api.post(`/sales/directories/agencies/${agencyId}/counterparties`,
        { counterparty_id: cpId }, auth())
      setAttachTo(null); setCpQuery(''); flash('Юрлицо прикреплено'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось прикрепить') }
  }

  const detach = async (agencyId, cpId) => {
    setError('')
    try {
      await api.delete(`/sales/directories/agencies/${agencyId}/counterparties/${cpId}`, auth())
      flash('Юрлицо откреплено'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось открепить') }
  }

  const startEdit = (a) => {
    setEditId(a.id)
    setEditFull(a.full_name || '')
    setForm({ short_name: a.short_name || '', name_en: a.name_en || '',
      name_ru: a.name_ru || '', holding: a.holding || '' })
    setShowForm(false)
  }

  const filtered = items.filter(a => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [a.short_name, a.name_en, a.name_ru, a.holding].some(v => (v || '').toLowerCase().includes(q))
      || (a.counterparties || []).some(c => (c.name || '').toLowerCase().includes(q))
  })

  const inp = { padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit' }
  const btn = (p) => ({ padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit' })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)', verticalAlign: 'top' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  const formOpen = showForm && !editId

  return (
    <>
      <Head><title>Рекламные агентства</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 24px 50px' }}>

        <DirectoryTabs active="agencies" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Рекламные агентства</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
        </div>

        {/* Строка поиска с кнопкой добавления */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center',
          marginBottom: formOpen ? 0 : 12 }}>
          <input style={{ ...inp, width: 320 }} placeholder="поиск по названию, холдингу или юрлицу"
            value={search} onChange={e => setSearch(e.target.value)} />
          {mayEdit && (
            <button style={btn(formOpen && !editId)}
              onClick={() => formOpen ? cancelForm() : setShowForm(true)}>
              {formOpen ? 'Отмена' : '+ Добавить'}
            </button>
          )}
        </div>

        {/* Форма — раскрывается ниже строки поиска */}
        {mayEdit && formOpen && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)',
            padding: '14px 16px', marginTop: 8, marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новое агентство</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 160 }} placeholder="Краткое" autoFocus
                value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 190 }} placeholder="Название ENG"
                value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 190 }} placeholder="Название РУС"
                value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <input style={{ ...inp, width: 160 }} placeholder="Холдинг (необяз.)"
                value={form.holding} onChange={e => setForm({ ...form, holding: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
              <button style={btn(true)} onClick={save}>{editId ? 'Сохранить' : 'Добавить'}</button>
              <button style={btn(false)} onClick={cancelForm}>Отмена</button>
            </div>
          </div>
        )}

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'visible', width: 'max-content' }}>
            <table style={{ borderCollapse: 'collapse' }}>
              <thead><tr>
                <th style={{ ...th, width: 28 }}></th>
                <th style={th}>BX_ID</th>
                <th style={th}>Краткое</th>
                <th style={th}>ENG</th>
                <th style={th}>РУС</th>
                <th style={th}>Холдинг</th>
                <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                <th style={{ ...th, textAlign: 'right' }}>СК</th>
                <th style={th}>Юрлица</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{ opacity: a.is_active ? 1 : 0.5,
                    background: selAg[a.id] ? 'var(--accent-tint)' : undefined }}>
                    <td style={{ ...td, textAlign: 'center' }}>
                      {mayEdit && editId !== a.id && (
                        <input type="checkbox" checked={!!selAg[a.id]} onChange={() => toggleAg(a)}
                          style={{ cursor: 'pointer' }} />
                      )}
                    </td>
                    <td style={{ ...td, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
                      {a.bx_id
                        ? <a href={`https://simb-ad.bitrix24.ru/crm/company/details/${a.bx_id}/`}
                             target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}
                             title="Открыть агентство в Битрикс24">{a.bx_id}</a>
                        : dash}
                    </td>
                    {editId === a.id ? (
                      <>
                        <td style={td}>
                          <input autoFocus style={{ ...inp, width: 140, padding: '3px 7px' }} placeholder="Краткое"
                            value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </td>
                        <td style={td}>
                          <input style={{ ...inp, width: 160, padding: '3px 7px' }} placeholder="ENG"
                            value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                          {editFull && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>исходное: {editFull}</div>}
                        </td>
                        <td style={td}>
                          <input style={{ ...inp, width: 160, padding: '3px 7px' }} placeholder="РУС"
                            value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </td>
                        <td style={td}>
                          <input style={{ ...inp, width: 130, padding: '3px 7px' }} placeholder="Холдинг"
                            value={form.holding} onChange={e => setForm({ ...form, holding: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </td>
                        <td style={{ ...td, textAlign: 'right', color: 'var(--muted)' }}>{a.deals}</td>
                        <td style={{ ...td, textAlign: 'right', color: 'var(--muted)' }}>{Math.round(a.sk_percent)}%</td>
                        <td style={td}>{/* юрлица не трогаем при inline-правке */}
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                            {(a.counterparties || []).map(c => (
                              <span key={c.counterparty_id} style={{ background: 'var(--bg-subtle)',
                                borderRadius: 'var(--radius-badge)', padding: '2px 8px', fontSize: 12 }}>
                                {c.name}
                              </span>
                            ))}
                            {!a.counterparties?.length && dash}
                          </div>
                        </td>
                        <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button style={{ ...btn(true), padding: '3px 10px', fontSize: 12, marginRight: 6 }}
                            onClick={save}>Сохранить</button>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }}
                            onClick={cancelForm}>Отмена</button>
                          {error && <div style={{ color: 'var(--danger)', fontSize: 11.5, marginTop: 4,
                            whiteSpace: 'normal', maxWidth: 240, textAlign: 'left' }}>{error}</div>}
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ ...td, fontWeight: 600 }}>{a.short_name || dash}</td>
                        <td style={td}>{a.name_en || dash}</td>
                        <td style={td}>{a.name_ru || dash}</td>
                        <td style={td}>{a.holding || dash}</td>
                        <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                          {a.deals > 0 ? (
                            <a href={`/sales?agency_id=${a.id}`} target="_blank" rel="noreferrer"
                              style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
                              title="Открыть сделки агентства в реестре">{a.deals}</a>
                          ) : <span style={{ color: 'var(--muted)' }}>0</span>}
                        </td>
                        <td style={{ ...td, textAlign: 'right' }}>
                          {mayEdit && skEditId === a.id ? (
                            <input autoFocus type="number" min="0" max="100" step="1" defaultValue={a.sk_percent}
                              onBlur={e => saveSk(a.id, e.target.value)}
                              onKeyDown={e => { if (e.key === 'Enter') saveSk(a.id, e.target.value); if (e.key === 'Escape') setSkEditId(null) }}
                              style={{ width: 54, padding: '3px 6px', textAlign: 'right', border: '1px solid var(--accent)', borderRadius: 'var(--radius-input)', background: 'var(--bg-card)', color: 'inherit', fontSize: 13 }} />
                          ) : (
                            <span onClick={() => mayEdit && setSkEditId(a.id)}
                              title={mayEdit ? 'Клик — изменить СК' : undefined}
                              style={{ cursor: mayEdit ? 'pointer' : 'default', fontVariantNumeric: 'tabular-nums' }}>
                              {Math.round(a.sk_percent)}%
                            </span>
                          )}
                        </td>
                        <td style={td}>
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                            {(a.counterparties || []).map(c => (
                              <span key={c.counterparty_id} style={{
                                background: 'var(--bg-subtle)', borderRadius: 'var(--radius-badge)',
                                padding: '2px 8px', fontSize: 12, display: 'inline-flex', gap: 6, alignItems: 'center',
                              }}>
                                {c.name}
                                {mayEdit && <span style={{ cursor: 'pointer', color: 'var(--danger)', fontWeight: 700 }}
                                  onClick={() => detach(a.id, c.counterparty_id)} title="Открепить">×</span>}
                              </span>
                            ))}
                            {!a.counterparties?.length && dash}
                          </div>
                          {attachTo === a.id && mayEdit && (
                            <div style={{ marginTop: 8, position: 'relative' }}>
                              <input autoFocus style={{ ...inp, width: 280 }} placeholder="поиск контрагента"
                                value={cpQuery} onChange={e => setCpQuery(e.target.value)} />
                              {cpQuery.trim() && (
                                <div style={{ position: 'absolute', top: '100%', left: 0, zIndex: 10, marginTop: 2,
                                  background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                                  borderRadius: 'var(--radius-card-sm)', boxShadow: 'var(--shadow-card)',
                                  maxHeight: 240, overflowY: 'auto', minWidth: 280 }}>
                                  {cps.map(c => (
                                    <div key={c.id} onClick={() => attach(a.id, c.id)}
                                      style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                                      {c.name}
                                    </div>
                                  ))}
                                  {!cps.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--muted)' }}>не найдено</div>}
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                        <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {mayEdit && (
                            <>
                              <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12, marginRight: 6 }}
                                onClick={() => { setAttachTo(attachTo === a.id ? null : a.id); setCpQuery('') }}>
                                + контрагент
                              </button>
                              <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }}
                                onClick={() => startEdit(a)}>Изменить</button>
                            </>
                          )}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
                {!filtered.length && (
                  <tr><td colSpan={7} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>Ничего не найдено</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Плавающая панель склейки выбранных агентств */}
        {selAgIds.length > 0 && (
          <div style={{ position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)',
            zIndex: 50, background: 'var(--bg-card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)',
            padding: '12px 16px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Выбрано агентств: {selAgIds.length}</span>
            <button style={{ ...btn(true), padding: '6px 14px', fontSize: 13 }}
              disabled={selAgIds.length < 2} onClick={mergeSelectedAgencies}>Схлопнуть в один</button>
            <button style={{ ...btn(false), padding: '6px 14px', fontSize: 13 }}
              onClick={() => setSelAg({})}>Сбросить</button>
            {selAgIds.length >= 2 && (
              <span style={{ fontSize: 11.5, color: 'var(--muted)', width: '100%' }}>
                оставим того, у кого больше сделок; юрлица и сделки перейдут на него
              </span>
            )}
          </div>
        )}
      </div>
    </>
  )
}
