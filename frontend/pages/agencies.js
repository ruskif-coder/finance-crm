import { useState, useEffect } from 'react'
import Head from 'next/head'
import api, { auth } from '../lib/http'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'
import { MONO, UI, IconBtn } from '../components/salesTableKit'
import useIsMobile from '../components/mobile/useIsMobile'
import AgenciesMobile from '../components/mobile/AgenciesMobile'


const EMPTY = { short_name: '', name_en: '', name_ru: '', holding: '' }

export default function Agencies() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [saving, setSaving] = useState(false)
  const [mobileLimit, setMobileLimit] = useState(50)
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

  const inp = { padding: '8px 11px', border: '1px solid var(--border-card)', borderRadius: 10,
    fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', fontFamily: UI, outline: 'none' }
  const btn = (p) => ({ padding: '8px 15px', borderRadius: 10, border: p ? 'none' : '1px solid var(--border-card)', cursor: 'pointer',
    fontSize: 13, fontWeight: p ? 700 : 600, background: p ? 'var(--accent)' : 'var(--bg-card)', color: p ? '#fff' : 'var(--text-secondary)', fontFamily: UI })
  const th = { padding: '0 10px 10px', textAlign: 'left', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600,
    color: 'var(--text-faint)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '10px 10px', fontSize: 13, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-row)', verticalAlign: 'middle' }
  const dash = <span style={{ color: 'var(--text-faint)' }}>—</span>

  const formOpen = showForm && !editId

  // единый сейв для мобильной формы (create + update + СК)
  const mobileSave = async (f, id) => {
    if (!(f.short_name || '').trim() && !(f.name_en || '').trim() && !(f.name_ru || '').trim()) { alert('Заполните хотя бы одно название'); return false }
    setSaving(true)
    try {
      const body = { short_name: f.short_name, name_en: f.name_en, name_ru: f.name_ru, holding: f.holding }
      if (id) {
        await api.put(`/sales/directories/agencies/${id}`, body, auth())
        const v = parseFloat(String(f.sk_percent ?? '').replace(',', '.'))
        if (!isNaN(v) && v >= 0 && v <= 100) await api.put(`/sales/directories/agencies/${id}/sk`, { sk_percent: v }, auth())
      } else {
        await api.post('/sales/directories/agencies', body, auth())
      }
      await load(); return true
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить'); return false }
    finally { setSaving(false) }
  }

  // ── МОБИЛЬНАЯ ВЕРСИЯ ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Агентства</title></Head>
        <Navbar active="directories" />
        <AgenciesMobile
          total={items.length} rows={filtered} loading={loading} canEdit={mayEdit}
          search={search} setSearch={setSearch}
          onSave={mobileSave} saving={saving} limit={mobileLimit} setLimit={setMobileLimit} />
      </div>
    )
  }

  return (
    <>
      <Head><title>Рекламные агентства</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>

        <DirectoryTabs active="agencies" actions={
          <IconBtn title="Сбросить поиск" onClick={() => setSearch('')}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
        } />

        {/* Карточка реестра */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '18px 24px 14px' }}>
        {/* Строка фильтров */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: formOpen ? 0 : 12 }}>
          <h1 style={{ fontSize: 17, fontWeight: 700, margin: '0 6px 0 0', color: 'var(--text-primary)' }}>Агентства</h1>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginRight: 4 }}>показано {filtered.length} из {items.length}</span>
          <input style={{ ...inp, width: 280 }} placeholder="название, холдинг, юрлицо…"
            value={search} onChange={e => setSearch(e.target.value)} />
          {mayEdit && (
            <button style={{ marginLeft: 'auto', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '8px 15px', fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}
              onClick={() => formOpen ? cancelForm() : setShowForm(true)}>
              {formOpen ? 'Отмена' : '+ Агентство'}
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
        {loading && <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>}

        {!loading && (() => {
          const GGRID = '26px 64px minmax(120px,1fr) minmax(120px,1fr) minmax(120px,1fr) minmax(110px,0.9fr) 62px 56px minmax(180px,1.4fr) 210px'
          const cell = { padding: '0 8px', fontSize: 13, color: 'var(--text-primary)', minWidth: 0 }
          const headCell = (label, right) => <div style={{ padding: '0 8px 10px', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', textAlign: right ? 'right' : 'left', whiteSpace: 'nowrap' }}>{label}</div>
          return (
          <div style={{ overflowX: 'auto', maxWidth: '100%', margin: '4px -4px 0' }}>
            <div style={{ minWidth: 1320 }}>
              <div style={{ display: 'grid', gridTemplateColumns: GGRID, gap: 12, borderBottom: '1px solid var(--border-card)' }}>
                <div />{headCell('BX_ID')}{headCell('Краткое')}{headCell('ENG')}{headCell('РУС')}{headCell('Холдинг')}{headCell('Сделок', true)}{headCell('СК', true)}{headCell('Юрлица')}<div />
              </div>
                {filtered.map(a => (
                  <div key={a.id} style={{ display: 'grid', gridTemplateColumns: GGRID, gap: 12, alignItems: 'start', padding: '10px 0', borderBottom: '1px solid var(--border-row)', borderRadius: 10,
                    opacity: a.is_active ? 1 : 0.5,
                    background: selAg[a.id] ? 'var(--accent-tint)' : 'transparent' }}
                    onMouseEnter={e => { if (!selAg[a.id]) e.currentTarget.style.background = 'var(--bg-subtle)' }} onMouseLeave={e => { if (!selAg[a.id]) e.currentTarget.style.background = 'transparent' }}>
                    <div style={{ ...cell, paddingTop: 2 }}>
                      {mayEdit && editId !== a.id && (
                        <input type="checkbox" checked={!!selAg[a.id]} onChange={() => toggleAg(a)}
                          style={{ cursor: 'pointer' }} />
                      )}
                    </div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>
                      {a.bx_id
                        ? <a href={`https://simb-ad.bitrix24.ru/crm/company/details/${a.bx_id}/`}
                             target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}
                             title="Открыть агентство в Битрикс24">{a.bx_id}</a>
                        : dash}
                    </div>
                    {editId === a.id ? (
                      <>
                        <div style={cell}>
                          <input autoFocus style={{ ...inp, width: '100%', padding: '5px 8px' }} placeholder="Краткое"
                            value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </div>
                        <div style={cell}>
                          <input style={{ ...inp, width: '100%', padding: '5px 8px' }} placeholder="ENG"
                            value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                          {editFull && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>исходное: {editFull}</div>}
                        </div>
                        <div style={cell}>
                          <input style={{ ...inp, width: '100%', padding: '5px 8px' }} placeholder="РУС"
                            value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </div>
                        <div style={cell}>
                          <input style={{ ...inp, width: '100%', padding: '5px 8px' }} placeholder="Холдинг"
                            value={form.holding} onChange={e => setForm({ ...form, holding: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancelForm() }} />
                        </div>
                        <div style={{ ...cell, fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>{a.deals}</div>
                        <div style={{ ...cell, fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>{Math.round(a.sk_percent)}%</div>
                        <div style={cell}>
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                            {(a.counterparties || []).map(c => (
                              <span key={c.counterparty_id} style={{ background: 'var(--bg-subtle)',
                                borderRadius: 8, padding: '2px 8px', fontSize: 12 }}>
                                {c.name}
                              </span>
                            ))}
                            {!a.counterparties?.length && dash}
                          </div>
                        </div>
                        <div style={{ ...cell, display: 'flex', flexWrap: 'nowrap', gap: 6, justifyContent: 'flex-end', alignItems: 'flex-start' }}>
                          <button style={{ ...btn(true), padding: '5px 12px', fontSize: 12, whiteSpace: 'nowrap' }}
                            onClick={save}>Сохранить</button>
                          <button style={{ ...btn(false), padding: '5px 12px', fontSize: 12, whiteSpace: 'nowrap' }}
                            onClick={cancelForm}>Отмена</button>
                          {error && <div style={{ color: 'var(--danger)', fontSize: 11.5, marginTop: 4,
                            whiteSpace: 'normal', maxWidth: 240, textAlign: 'left' }}>{error}</div>}
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ ...cell, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.short_name || dash}</div>
                        <div style={{ ...cell, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name_en || dash}</div>
                        <div style={{ ...cell, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name_ru || dash}</div>
                        <div style={{ ...cell, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.holding || dash}</div>
                        <div style={{ ...cell, fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>
                          {a.deals > 0 ? (
                            <a href={`/sales?agency_id=${a.id}`} target="_blank" rel="noreferrer"
                              style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
                              title="Открыть сделки агентства в реестре">{a.deals}</a>
                          ) : <span style={{ color: 'var(--text-faint)' }}>0</span>}
                        </div>
                        <div style={{ ...cell, fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>
                          {mayEdit && skEditId === a.id ? (
                            <input autoFocus type="number" min="0" max="100" step="1" defaultValue={a.sk_percent}
                              onBlur={e => saveSk(a.id, e.target.value)}
                              onKeyDown={e => { if (e.key === 'Enter') saveSk(a.id, e.target.value); if (e.key === 'Escape') setSkEditId(null) }}
                              style={{ width: 48, padding: '3px 6px', textAlign: 'right', border: '1px solid var(--accent)', borderRadius: 8, background: 'var(--bg-card)', color: 'inherit', fontSize: 12, fontFamily: MONO }} />
                          ) : (
                            <span onClick={() => mayEdit && setSkEditId(a.id)}
                              title={mayEdit ? 'Клик — изменить СК' : undefined}
                              style={{ cursor: mayEdit ? 'pointer' : 'default' }}>
                              {Math.round(a.sk_percent)}%
                            </span>
                          )}
                        </div>
                        <div style={cell}>
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                            {(a.counterparties || []).map(c => (
                              <span key={c.counterparty_id} style={{
                                background: 'var(--bg-subtle)', borderRadius: 8,
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
                                  borderRadius: 12, boxShadow: 'var(--shadow-card)',
                                  maxHeight: 240, overflowY: 'auto', minWidth: 280 }}>
                                  {cps.map(c => (
                                    <div key={c.id} onClick={() => attach(a.id, c.id)}
                                      style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                                      {c.name}
                                    </div>
                                  ))}
                                  {!cps.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>не найдено</div>}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        <div style={{ ...cell, display: 'flex', flexWrap: 'nowrap', gap: 6, justifyContent: 'flex-end', alignItems: 'flex-start' }}>
                          {mayEdit && (
                            <>
                              <button style={{ ...btn(false), padding: '5px 12px', fontSize: 12, whiteSpace: 'nowrap' }}
                                onClick={() => { setAttachTo(attachTo === a.id ? null : a.id); setCpQuery('') }}>
                                + контрагент
                              </button>
                              <button style={{ ...btn(false), padding: '5px 12px', fontSize: 12, whiteSpace: 'nowrap' }}
                                onClick={() => startEdit(a)}>Изменить</button>
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}
                {!filtered.length && (
                  <div style={{ padding: 26, textAlign: 'center', color: 'var(--text-muted)' }}>Ничего не найдено</div>
                )}
            </div>
          </div>
          )
        })()}
        </div>

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
