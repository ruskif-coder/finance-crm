import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const EMPTY = { name_en: '', name_ru: '', website: '', inn: '', exclude_from_revenue: false }

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
      const r = await api.get('/sales/directories/advertisers/duplicates', auth())
      setDupes(r.data.pairs); setShowDupes(true)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить дубли') }
  }

  // keepId остаётся, dropId вливается и исчезает
  const merge = async (keepId, dropId, keepName, dropName) => {
    if (!window.confirm(`Влить «${dropName}» в «${keepName}»?\n\nБренды и сделки перейдут на «${keepName}», «${dropName}» будет удалён.`)) return
    setError('')
    try {
      const r = await api.post(`/sales/directories/advertisers/${keepId}/merge`, { source_id: dropId }, auth())
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

  const [editBrand, setEditBrand] = useState(null)   // { id, name }
  const [drag, setDrag] = useState(null)             // перетаскиваемый бренд
  const [dragOver, setDragOver] = useState(null)     // id рекламодателя-цели

  const dropOnAdvertiser = (advertiserId) => {
    if (!drag || drag.advertiserId === advertiserId) { setDrag(null); setDragOver(null); return }
    saveBrand(drag.id, drag.name, advertiserId)
    setDrag(null); setDragOver(null)
  }

  const load = async () => {
    setLoading(true); setError('')
    try {
      const res = await api.get('/sales/directories/advertisers', { params: { only_active: false }, ...auth() })
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
    if (!form.name_en.trim() && !form.name_ru.trim()) {
      setError('Заполните хотя бы одно название — английское или русское')
      return
    }
    try {
      if (editId) {
        await api.put(`/sales/directories/advertisers/${editId}`, form, auth())
        flash('Рекламодатель обновлён')
      } else {
        await api.post('/sales/directories/advertisers', form, auth())
        flash('Рекламодатель создан')
      }
      setForm(EMPTY); setEditId(null); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
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
      name_en: a.name_en || '', name_ru: a.name_ru || '', website: a.website || '',
      inn: a.inn || '', exclude_from_revenue: !!a.exclude_from_revenue,
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const filtered = items.filter(a => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [a.name, a.name_en, a.name_ru].some(v => (v || '').toLowerCase().includes(q))
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

        {mayEdit && (
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', padding: '14px 16px', marginBottom: 16,
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
              {editId ? 'Редактирование' : 'Новый рекламодатель'}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 200 }} placeholder="Название ENG"
                value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })} />
              <input style={{ ...inp, width: 200 }} placeholder="Название РУС"
                value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })} />
              <input style={{ ...inp, width: 210 }} placeholder="сайт"
                value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} />
              <input style={{ ...inp, width: 130 }} placeholder="ИНН"
                value={form.inn} onChange={e => setForm({ ...form, inn: e.target.value })} />
              <label style={{ fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 6 }}>
                <input type="checkbox" checked={form.exclude_from_revenue}
                  onChange={e => setForm({ ...form, exclude_from_revenue: e.target.checked })} />
                исключить из выручки
              </label>
              <button style={btn(true)} onClick={save}>{editId ? 'Сохранить' : 'Добавить'}</button>
              {editId && <button style={btn(false)} onClick={() => { setEditId(null); setForm(EMPTY) }}>Отмена</button>}
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
                <th style={th}>Название ENG</th>
                <th style={th}>Название РУС</th>
                <th style={th}>Сайт</th>
                <th style={th}>Бренды</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{ opacity: a.is_active ? 1 : 0.5 }}>
                    {/* Ячейка имени — зона сброса бренда: перетащил бренд сюда → он переехал */}
                    <td style={{ ...td,
                        background: dragOver === a.id ? 'var(--accent-tint)' : undefined,
                        outline: dragOver === a.id ? '2px dashed var(--accent)' : undefined }}
                      onDragOver={e => { if (drag) { e.preventDefault(); setDragOver(a.id) } }}
                      onDragLeave={() => setDragOver(d => d === a.id ? null : d)}
                      onDrop={() => dropOnAdvertiser(a.id)}>
                      {a.name_en || dash}
                      {a.exclude_from_revenue && (
                        <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--danger)' }}>не в выручке</span>
                      )}
                    </td>
                    <td style={td}>{a.name_ru || dash}</td>
                    <td style={td}>
                      {a.website
                        ? <a href={a.website.startsWith('http') ? a.website : `https://${a.website}`}
                             target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{a.website}</a>
                        : dash}
                    </td>
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
                              draggable={mayEdit}
                              onDragStart={() => setDrag({ id: b.id, name: b.name, advertiserId: a.id })}
                              onDragEnd={() => { setDrag(null); setDragOver(null) }}
                              onDoubleClick={() => mayEdit && setEditBrand({ id: b.id, name: b.name })}
                              title={mayEdit ? 'Двойной клик — переименовать, тащить — перенести' : b.name}
                              style={{
                                background: 'var(--bg-subtle)', borderRadius: 'var(--radius-badge)',
                                padding: '2px 8px', fontSize: 12, display: 'inline-flex', gap: 6, alignItems: 'center',
                                cursor: mayEdit ? 'grab' : 'default',
                              }}>
                              {b.name}
                              {mayEdit && <span style={{ cursor: 'pointer', color: 'var(--danger)', fontWeight: 700 }}
                                onClick={() => deleteBrand(b.id, b.name)} title="Удалить бренд">×</span>}
                            </span>
                          )
                        ))}
                        {!a.brands?.length && dash}
                      </div>
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
                      {mayEdit && (
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
                  <tr><td colSpan={5} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
                    Ничего не найдено
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
