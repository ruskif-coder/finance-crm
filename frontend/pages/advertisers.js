import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'

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

  const mayEdit = can(perms, 'sales_directories', 'edit')

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

  const selIds = Object.keys(sel).map(Number)
  const toggleSel = (id, name) => setSel(s => {
    const n = { ...s }
    if (n[id]) delete n[id]; else n[id] = name
    return n
  })
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

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (msg) => { setOk(msg); setTimeout(() => setOk(''), 2500) }

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
      } else {
        await api.post('/sales/directories/producers', form, auth())
        flash('Рекламодатель создан')
      }
      setForm(EMPTY); setEditId(null); load()
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
      <Navbar active="sales" />
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '20px 24px 50px' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 16 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Рекламодатели</h1>
          {mayEdit && <button style={btn(false)} onClick={() => showDupes ? setShowDupes(false) : loadDupes()}>
            {showDupes ? 'Скрыть дубли' : 'Найти дубли'}
          </button>}
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
        </div>

        {mayEdit && !editId && (
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', padding: '14px 16px', marginBottom: 16,
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новый рекламодатель</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 170 }} placeholder="Короткое"
                value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })} />
              <input style={{ ...inp, width: 180 }} placeholder="Англ"
                value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })} />
              <input style={{ ...inp, width: 180 }} placeholder="Русское"
                value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })} />
              <input style={{ ...inp, width: 190 }} placeholder="сайт"
                value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} />
              <input style={{ ...inp, width: 130 }} placeholder="ИНН"
                value={form.inn} onChange={e => setForm({ ...form, inn: e.target.value })} />
              <button style={btn(true)} onClick={save}>Добавить</button>
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

        <input style={{ ...inp, width: 300, marginBottom: 12 }} placeholder="поиск по названию или бренду"
          value={search} onChange={e => setSearch(e.target.value)} />

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)',
          marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>
                <th style={th}>Короткое</th>
                <th style={th}>Англ</th>
                <th style={th}>Русское</th>
                <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                <th style={th}>Сайт</th>
                <th style={th}>Бренды</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{ opacity: a.is_active ? 1 : 0.5 }}>
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
                        <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{a.deals}</td>
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
                  <tr><td colSpan={7} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
                    Ничего не найдено
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Плавающая панель действий над выбранными брендами */}
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
