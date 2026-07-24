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
  const [attachTo, setAttachTo] = useState(null)   // agency id, для которого открыт выбор контрагента
  const [cpQuery, setCpQuery] = useState('')

  const mayEdit = can(perms, 'sales_directories', 'edit')

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

  const save = async () => {
    setError('')
    if (!form.short_name.trim() && !form.name_en.trim() && !form.name_ru.trim()) {
      setError('Заполните хотя бы одно название'); return
    }
    try {
      if (editId) { await api.put(`/sales/directories/agencies/${editId}`, form, auth()); flash('Обновлено') }
      else { await api.post('/sales/directories/agencies', form, auth()); flash('Создано') }
      setForm(EMPTY); setEditId(null); load()
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

  const [editFull, setEditFull] = useState('')

  const startEdit = (a) => {
    setEditId(a.id)
    setEditFull(a.full_name || '')
    setForm({ short_name: a.short_name || '', name_en: a.name_en || '',
      name_ru: a.name_ru || '', holding: a.holding || '' })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const filtered = items.filter(a => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [a.short_name, a.name_en, a.name_ru, a.holding].some(v => (v || '').toLowerCase().includes(q))
      || (a.counterparties || []).some(c => (c.name || '').toLowerCase().includes(q))
  })

  const cpShown = cps   // уже отфильтрованы сервером по cpQuery

  const inp = { padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit' }
  const btn = (p) => ({ padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit' })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)', verticalAlign: 'top' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  return (
    <>
      <Head><title>Рекламные агентства</title></Head>
      <Navbar active="directories" />
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '20px 24px 50px' }}>

        <DirectoryTabs active="agencies" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Рекламные агентства</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
        </div>

        {mayEdit && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', padding: '14px 16px', marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
              {editId ? 'Редактирование' : 'Новое агентство'}
              {editId && editFull && (
                <span style={{ fontWeight: 400, color: 'var(--muted)', marginLeft: 10 }}>
                  исходное: {editFull}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 160 }} placeholder="Краткое"
                value={form.short_name} onChange={e => setForm({ ...form, short_name: e.target.value })} />
              <input style={{ ...inp, width: 190 }} placeholder="Название ENG"
                value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })} />
              <input style={{ ...inp, width: 190 }} placeholder="Название РУС"
                value={form.name_ru} onChange={e => setForm({ ...form, name_ru: e.target.value })} />
              <input style={{ ...inp, width: 160 }} placeholder="Холдинг (необяз.)"
                value={form.holding} onChange={e => setForm({ ...form, holding: e.target.value })} />
              <button style={btn(true)} onClick={save}>{editId ? 'Сохранить' : 'Добавить'}</button>
              {editId && <button style={btn(false)} onClick={() => { setEditId(null); setForm(EMPTY) }}>Отмена</button>}
            </div>
          </div>
        )}

        <input style={{ ...inp, width: 320, marginBottom: 12 }} placeholder="поиск по названию, холдингу или юрлицу"
          value={search} onChange={e => setSearch(e.target.value)} />

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>
                <th style={th}>Краткое</th>
                <th style={th}>Название (ENG / РУС)</th>
                <th style={th}>Холдинг</th>
                <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                <th style={th}>Юрлица</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{ opacity: a.is_active ? 1 : 0.5 }}>
                    <td style={{ ...td, fontWeight: 600 }}>{a.short_name || dash}</td>
                    <td style={td}>
                      {/* Размеченные ENG/РУС, а пока их нет — исходное полное имя,
                          чтобы агентство всегда можно было опознать */}
                      {[a.name_en, a.name_ru].filter(Boolean).join(' / ') || a.full_name || dash}
                    </td>
                    <td style={td}>{a.holding || dash}</td>
                    <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {a.deals > 0 ? (
                        // клик открывает реестр сделок, отфильтрованный по этому агентству
                        <a href={`/sales?agency_id=${a.id}`} target="_blank" rel="noreferrer"
                          style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
                          title="Открыть сделки агентства в реестре">{a.deals}</a>
                      ) : <span style={{ color: 'var(--muted)' }}>0</span>}
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
                              {cpShown.map(c => (
                                <div key={c.id} onClick={() => attach(a.id, c.id)}
                                  style={{ padding: '6px 10px', fontSize: 12.5, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                                  {c.name}
                                </div>
                              ))}
                              {!cpShown.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--muted)' }}>не найдено</div>}
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
                  </tr>
                ))}
                {!filtered.length && (
                  <tr><td colSpan={6} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>Ничего не найдено</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
