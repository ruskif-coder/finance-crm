import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const EMPTY = { name: '', holding: '', legal_entity: '', counterparty_id: '' }

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

  const mayEdit = can(perms, 'sales_directories', 'edit')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [a, c] = await Promise.all([
        api.get('/sales/directories/agencies', { params: { only_active: false }, ...auth() }),
        api.get('/counterparties/', auth()).catch(() => ({ data: [] })),
      ])
      setItems(a.data.items)
      // Реестр контрагентов финмодуля — источник истины по юрлицам.
      const list = Array.isArray(c.data) ? c.data : (c.data.items || [])
      setCps(list.map(x => ({ id: x.id, name: x.name })).filter(x => x.name))
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить справочник') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const save = async () => {
    setError('')
    if (!form.name.trim()) { setError('Название обязательно'); return }
    const body = { ...form, counterparty_id: form.counterparty_id ? Number(form.counterparty_id) : null }
    try {
      if (editId) {
        await api.put(`/sales/directories/agencies/${editId}`, body, auth()); flash('Агентство обновлено')
      } else {
        await api.post('/sales/directories/agencies', body, auth()); flash('Агентство создано')
      }
      setForm(EMPTY); setEditId(null); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
  }

  const startEdit = (a) => {
    setEditId(a.id)
    setForm({
      name: a.name || '', holding: a.holding || '',
      legal_entity: a.legal_entity || '', counterparty_id: a.counterparty_id || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const filtered = items.filter(a => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [a.name, a.holding, a.legal_entity, a.counterparty]
      .some(v => (v || '').toLowerCase().includes(q))
  })

  const inp = {
    padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit',
  }
  const btn = (p) => ({
    padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500,
    background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit',
  })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  const noHolding = items.filter(a => !a.holding).length
  const noLegal = items.filter(a => !a.legal_entity).length

  return (
    <>
      <Head><title>Рекламные агентства</title></Head>
      <Navbar active="sales" />
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '20px 24px 50px' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14, flexWrap: 'wrap' }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Рекламные агентства</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
          {/* Пробелы видны сразу: справочник наполнен из сделок, холдинг и юрлицо там не размечены */}
          <span style={{ fontSize: 12, color: noHolding ? 'var(--danger)' : 'var(--muted)' }}>
            без холдинга: {noHolding}
          </span>
          <span style={{ fontSize: 12, color: noLegal ? 'var(--danger)' : 'var(--muted)' }}>
            без юрлица: {noLegal}
          </span>
        </div>

        {mayEdit && (
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', padding: '14px 16px', marginBottom: 16,
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
              {editId ? 'Редактирование' : 'Новое агентство'}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 170 }} placeholder="Холдинг"
                value={form.holding} onChange={e => setForm({ ...form, holding: e.target.value })} />
              <input style={{ ...inp, width: 220 }} placeholder="Название"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
              <input style={{ ...inp, width: 220 }} placeholder="Юрлицо (текстом)"
                value={form.legal_entity} onChange={e => setForm({ ...form, legal_entity: e.target.value })} />
              <select style={{ ...inp, maxWidth: 280 }} value={form.counterparty_id}
                onChange={e => setForm({ ...form, counterparty_id: e.target.value })}>
                <option value="">— контрагент не выбран —</option>
                {cps.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button style={btn(true)} onClick={save}>{editId ? 'Сохранить' : 'Добавить'}</button>
              {editId && <button style={btn(false)} onClick={() => { setEditId(null); setForm(EMPTY) }}>Отмена</button>}
            </div>
          </div>
        )}

        <input style={{ ...inp, width: 320, marginBottom: 12 }} placeholder="поиск по названию, холдингу или юрлицу"
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
                <th style={th}>Холдинг</th>
                <th style={th}>Название</th>
                <th style={th}>Юрлицо</th>
                <th style={th}>Контрагент в финмодуле</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id} style={{ opacity: a.is_active ? 1 : 0.5 }}>
                    <td style={td}>{a.holding || dash}</td>
                    <td style={td}>{a.name}</td>
                    <td style={td}>{a.legal_entity || dash}</td>
                    <td style={td}>{a.counterparty || dash}</td>
                    <td style={{ ...td, textAlign: 'right' }}>
                      {mayEdit && <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }}
                        onClick={() => startEdit(a)}>Изменить</button>}
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
