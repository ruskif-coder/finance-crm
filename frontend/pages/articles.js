import { useState, useEffect } from 'react'
import Head from 'next/head'
import api, { auth } from '../lib/http'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'


const TYPE_META = {
  income: { label: 'Доход', color: 'var(--success)', tint: 'var(--accent-tint)' },
  expense: { label: 'Расход', color: 'var(--danger)', tint: 'var(--danger-tint)' },
}
const EMPTY = { name: '', group: '', type: 'expense' }

export default function Articles({ embedded = false } = {}) {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [editId, setEditId] = useState(null)
  const [draft, setDraft] = useState(EMPTY)
  const [newGroup, setNewGroup] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [overIdx, setOverIdx] = useState(null)
  const [showForm, setShowForm] = useState(false)

  const mayEdit = can(perms, 'articles', 'edit')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [a, g] = await Promise.all([
        api.get('/articles/registry', auth()),
        api.get('/articles/groups', auth()),
      ])
      setItems(a.data.items)
      setGroups((g.data.items || []).map(x => x.name))
    } catch (e) {
      if (e.response?.status === 401) { router.push('/login'); return }
      setError(e.response?.data?.detail || 'Не удалось загрузить статьи')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const createArticle = async () => {
    setError('')
    if (!form.name.trim()) { setError('Введите название статьи'); return }
    try {
      await api.post('/articles/', { name: form.name.trim(), group: form.group || null, type: form.type }, auth())
      setForm(EMPTY); setShowForm(false); flash('Статья создана'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось создать') }
  }

  const createGroup = async () => {
    const name = newGroup.trim()
    if (!name) return
    setError('')
    try {
      await api.post('/articles/groups', { name }, auth())
      setNewGroup(''); flash('Группа создана'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось создать группу') }
  }

  const startEdit = (a) => { setEditId(a.id); setDraft({ name: a.name, group: a.group || '', type: a.type || 'expense' }); setError('') }

  const saveEdit = async (id) => {
    setError('')
    try {
      await api.put(`/articles/${id}`, { name: draft.name, group: draft.group || null, type: draft.type }, auth())
      setEditId(null); flash('Сохранено'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
  }

  const remove = async (a) => {
    if (!window.confirm(`Удалить статью «${a.name}»?`)) return
    setError('')
    try {
      await api.delete(`/articles/${a.id}`, auth())
      flash('Статья удалена'); load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось удалить') }
  }

  // Перетаскивание строк меняет порядок. Оптимистично переставляем локально,
  // затем шлём весь порядок на /reorder (как в исходном справочнике).
  const dropReorder = async (fromIdx, toIdx) => {
    if (fromIdx == null || toIdx == null || fromIdx === toIdx) return
    const reordered = [...items]
    const [moved] = reordered.splice(fromIdx, 1)
    reordered.splice(toIdx, 0, moved)
    setItems(reordered)
    try {
      await api.put('/articles/reorder', { ids: reordered.map(a => a.id) }, auth())
    } catch (e) {
      setError(e.response?.data?.detail || 'Не удалось изменить порядок'); load()
    }
  }

  const filtered = search
    ? items.filter(a => a.name.toLowerCase().includes(search.toLowerCase()) || (a.group || '').toLowerCase().includes(search.toLowerCase()))
    : items

  const inp = { padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit' }
  const btn = (p) => ({ padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit' })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>
  const typeBadge = (t) => {
    const m = TYPE_META[t] || TYPE_META.expense
    return <span style={{ background: m.tint, color: m.color, borderRadius: 'var(--radius-badge)',
      padding: '2px 8px', fontSize: 12, fontWeight: 500 }}>{m.label}</span>
  }

  return (
    <>
      {!embedded && <Head><title>Статьи</title></Head>}
      {!embedded && <Navbar active="directories" />}
      <div style={{ padding: embedded ? 0 : '20px 24px 50px' }}>

        {!embedded && <DirectoryTabs active="articles" />}

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Статьи</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length}</span>
        </div>

        {/* Строка поиска + кнопка добавления */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: showForm ? 0 : 12 }}>
          <input style={{ ...inp, width: 300 }} placeholder="поиск по названию или группе"
            value={search} onChange={e => setSearch(e.target.value)} />
          {mayEdit && (
            <button style={btn(showForm)}
              onClick={() => { setShowForm(s => !s); setForm(EMPTY); setNewGroup(''); setError('') }}>
              {showForm ? 'Отмена' : '+ Добавить'}
            </button>
          )}
        </div>

        {/* Форма добавления — раскрывается под строкой поиска */}
        {mayEdit && showForm && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderTop: 'none', borderRadius: '0 0 var(--radius-card) var(--radius-card)',
            padding: '14px 16px', marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новая статья</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input style={{ ...inp, width: 260 }} placeholder="Название статьи" autoFocus
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                onKeyDown={e => { if (e.key === 'Enter') createArticle(); if (e.key === 'Escape') { setShowForm(false); setForm(EMPTY) } }} />
              <select style={inp} value={form.group} onChange={e => setForm({ ...form, group: e.target.value })}>
                <option value="">— группа —</option>
                {groups.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <select style={inp} value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
                <option value="expense">Расход</option>
                <option value="income">Доход</option>
              </select>
              <button style={btn(true)} onClick={createArticle}>Добавить</button>
              <span style={{ width: 1, height: 24, background: 'var(--border)' }} />
              <input style={{ ...inp, width: 160 }} placeholder="новая группа"
                value={newGroup} onChange={e => setNewGroup(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') createGroup() }} />
              <button style={btn(false)} onClick={createGroup}>+ группа</button>
            </div>
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
            borderRadius: 'var(--radius-card)', overflow: 'hidden', width: 'max-content' }}>
            <table style={{ borderCollapse: 'collapse' }}>
              <thead><tr>
                {mayEdit && !search && <th style={{ ...th, width: 28 }}></th>}
                <th style={th}>Название</th>
                <th style={th}>Группа</th>
                <th style={th}>Тип</th>
                <th style={{ ...th, textAlign: 'right' }}>Операций</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {filtered.map((a, i) => (
                  <tr key={a.id}
                    // drag работает только в полном списке (без поиска), иначе индексы не совпадают
                    draggable={mayEdit && !search && editId !== a.id}
                    onDragStart={() => setDragIdx(i)}
                    onDragOver={e => { if (dragIdx !== null) { e.preventDefault(); setOverIdx(i) } }}
                    onDrop={() => { dropReorder(dragIdx, i); setDragIdx(null); setOverIdx(null) }}
                    onDragEnd={() => { setDragIdx(null); setOverIdx(null) }}
                    style={{ borderTop: overIdx === i && dragIdx !== null ? '2px solid var(--accent)' : undefined }}>
                    {mayEdit && !search && (
                      <td style={{ ...td, textAlign: 'center', cursor: 'grab', color: 'var(--muted)' }}
                        title="Тащить для сортировки">⠿</td>
                    )}
                    {editId === a.id ? (
                      <>
                        <td style={td}><input style={{ ...inp, width: '100%', padding: '4px 7px' }} autoFocus
                          value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></td>
                        <td style={td}>
                          <select style={{ ...inp, padding: '4px 7px' }} value={draft.group} onChange={e => setDraft({ ...draft, group: e.target.value })}>
                            <option value="">— нет —</option>
                            {groups.map(g => <option key={g} value={g}>{g}</option>)}
                          </select>
                        </td>
                        <td style={td}>
                          <select style={{ ...inp, padding: '4px 7px' }} value={draft.type} onChange={e => setDraft({ ...draft, type: e.target.value })}>
                            <option value="expense">Расход</option>
                            <option value="income">Доход</option>
                          </select>
                        </td>
                        <td style={{ ...td, textAlign: 'right', color: 'var(--muted)' }}>{a.op_count}</td>
                        <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button style={{ ...btn(true), padding: '3px 10px', fontSize: 12, marginRight: 6 }} onClick={() => saveEdit(a.id)}>Сохранить</button>
                          <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12 }} onClick={() => setEditId(null)}>Отмена</button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ ...td, fontWeight: 500 }}>{a.name}</td>
                        <td style={td}>{a.group || dash}</td>
                        <td style={td}>{typeBadge(a.type)}</td>
                        <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--muted)' }}>{a.op_count}</td>
                        <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {mayEdit && (
                            <>
                              <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12, marginRight: 6 }} onClick={() => startEdit(a)}>Изменить</button>
                              <button style={{ ...btn(false), padding: '3px 10px', fontSize: 12, color: 'var(--danger)' }} onClick={() => remove(a)}>Удалить</button>
                            </>
                          )}
                        </td>
                      </>
                    )}
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
