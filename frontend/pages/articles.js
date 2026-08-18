import { useState, useEffect } from 'react'
import Head from 'next/head'
import api, { auth } from '../lib/http'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import { inp, btn, th, td } from '../components/salesTableKit'


const TYPE_META = {
  income: { label: 'Доход', color: 'var(--success)', tint: 'var(--accent-tint)' },
  expense: { label: 'Расход', color: 'var(--danger)', tint: 'var(--danger-tint)' },
}
const EMPTY = { name: '', group: '', type: 'expense', pl_line: '' }

// Подпись «нет разметки» намеренно тревожная: статья без строки отчёта не ломается,
// но её деньги уходят в отчёте в «Требует разметки». Это состояние надо видеть.
const NO_PL_LINE = 'не размечена'

export default function Articles({ embedded = false } = {}) {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [plLines, setPlLines] = useState([])  // закрытый список строк отчёта, приходит с бэкенда
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

  const mayEdit = can(perms, 'settings_articles', 'edit')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [a, g] = await Promise.all([
        api.get('/articles/registry', auth()),
        api.get('/articles/groups', auth()),
      ])
      setItems(a.data.items)
      setPlLines(a.data.pl_lines || [])
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
      await api.post('/articles/', { name: form.name.trim(), group: form.group || null, type: form.type, pl_line: form.pl_line || null }, auth())
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

  const startEdit = (a) => { setEditId(a.id); setDraft({ name: a.name, group: a.group || '', type: a.type || 'expense', pl_line: a.pl_line || '' }); setError('') }

  const saveEdit = async (id) => {
    setError('')
    try {
      await api.put(`/articles/${id}`, { name: draft.name, group: draft.group || null, type: draft.type, pl_line: draft.pl_line || null }, auth())
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

  // стили inp/btn/th/td — общий модуль components/salesTableKit
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>
  // Неразмеченную статью подсвечиваем: это не поломка, но отчёт по ней считать нечем.
  const plLabel = (v) => {
    if (!v) return <span style={{ color: 'var(--danger)', fontSize: 12 }}>{NO_PL_LINE}</span>
    const m = plLines.find(x => x.value === v)
    return <span style={{ fontSize: 12 }}>{m ? m.label : v}</span>
  }
  const plSelect = (value, onChange, style) => (
    <select style={style} value={value} onChange={e => onChange(e.target.value)}>
      <option value="">{NO_PL_LINE}</option>
      {plLines.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
    </select>
  )
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
              {plSelect(form.pl_line, v => setForm({ ...form, pl_line: v }), inp)}
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
                <th style={th}>Строка отчёта</th>
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
                        <td style={td}>
                          {plSelect(draft.pl_line, v => setDraft({ ...draft, pl_line: v }), { ...inp, padding: '4px 7px' })}
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
                        <td style={td}>{plLabel(a.pl_line)}</td>
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
                  <tr><td colSpan={7} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>Ничего не найдено</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
