import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'
const DEFAULT_TERM_DAYS = 60

const RELATION_LABELS = { 'заказчик': 'Заказчик', 'поставщик': 'Поставщик', 'смешенный': 'Смешенный' }
const RELATION_COLORS = {
  'заказчик': { bg: '#dbeafe', color: '#2563eb' },
  'поставщик': { bg: '#fef9c3', color: '#d97706' },
  'смешенный': { bg: '#f3e8ff', color: '#7c3aed' },
}

export default function Counterparties() {
  const router = useRouter()
  const [perms, setPerms] = useState({})
  const [role, setRole] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [ok, setOk] = useState('')
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('действующий')
  const [sortCol, setSortCol] = useState('name')
  const [sortDir, setSortDir] = useState('asc')

  const [showForm, setShowForm] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', inn: '', status: 'действующий' })
  const [newError, setNewError] = useState('')
  const [newSaving, setNewSaving] = useState(false)

  const [editId, setEditId] = useState(null)
  const [editDraft, setEditDraft] = useState({ name: '', inn: '', status: 'действующий', term_days: '', is_own_company: false })
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')

  const [selectedIds, setSelectedIds] = useState([])
  const [bulkStatus, setBulkStatus] = useState('')
  const [bulkGroup, setBulkGroup] = useState('')
  const [bulkSaving, setBulkSaving] = useState(false)
  const [deleteConfirming, setDeleteConfirming] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteError, setDeleteError] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)

  const isAdmin = role === 'admin'
  const mayEdit = isAdmin || can(perms, 'counterparties', 'edit')

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/counterparties/registry', auth())
      setItems(res.data.items)
    } catch (e) {
      if (e.response?.status === 401) { router.push('/login'); return }
      setError(e.response?.data?.detail || 'Не удалось загрузить')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try {
      setPerms(JSON.parse(localStorage.getItem('permissions') || '{}'))
      setRole(localStorage.getItem('role') || '')
    } catch (e) {}
    load()
  }, [])

  const cancelForm = () => {
    setShowForm(false)
    setNewForm({ name: '', inn: '', status: 'действующий' })
    setNewError('')
  }

  const handleCreate = async () => {
    const name = newForm.name.trim()
    if (!name) { setNewError('Название обязательно'); return }
    setNewSaving(true); setNewError('')
    try {
      const res = await api.post('/counterparties/', { name, vat_rate: 0 }, auth())
      const newId = res.data.id
      await api.put(`/counterparties/${newId}/registry`, {
        name, inn: newForm.inn.trim() || null, status: newForm.status, term_days: null,
      }, auth())
      cancelForm(); flash('Контрагент создан'); load()
    } catch (e) { setNewError(e.response?.data?.detail || 'Ошибка при создании') }
    finally { setNewSaving(false) }
  }

  const openEdit = (c) => {
    setEditId(c.id)
    setEditDraft({ name: c.name, inn: c.inn || '', status: c.status,
      term_days: c.term_days != null ? String(c.term_days) : '',
      is_own_company: !!c.is_own_company })
    setEditError('')
  }
  const cancelEdit = () => { setEditId(null); setEditError('') }

  const handleSave = async (id) => {
    setSaving(true); setEditError('')
    try {
      await api.put(`/counterparties/${id}/registry`, {
        name: editDraft.name, inn: editDraft.inn, status: editDraft.status,
        term_days: editDraft.term_days !== '' ? parseInt(editDraft.term_days, 10) : null,
        is_own_company: editDraft.is_own_company,
      }, auth())
      setEditId(null); load()
    } catch (e) { setEditError(e.response?.data?.detail || 'Ошибка при сохранении') }
    finally { setSaving(false) }
  }

  const handleBulkApply = async () => {
    const fields = {}
    if (bulkStatus) fields.status = bulkStatus
    if (bulkGroup) fields.group_override = bulkGroup === '__reset__' ? '' : bulkGroup
    if (!Object.keys(fields).length) { alert('Выберите хотя бы одно поле'); return }
    if (!confirm(`Изменить ${selectedIds.length} контрагентов?`)) return
    setBulkSaving(true)
    try {
      await api.patch('/counterparties/bulk', { ids: selectedIds, ...fields }, auth())
      setSelectedIds([]); setBulkStatus(''); setBulkGroup(''); load()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBulkSaving(false) }
  }

  const handleBulkDelete = async () => {
    if (!deletePassword) { setDeleteError('Введите пароль'); return }
    setDeleteLoading(true); setDeleteError('')
    try {
      await api.delete('/counterparties/bulk', { data: { ids: selectedIds, password: deletePassword }, ...auth() })
      setSelectedIds([]); setDeleteConfirming(false); setDeletePassword(''); load()
    } catch (e) {
      const d = e.response?.data?.detail
      setDeleteError(typeof d === 'string' ? d : (JSON.stringify(d) || 'Ошибка при удалении'))
    } finally { setDeleteLoading(false) }
  }

  const handleSort = (col) => {
    setSortDir(d => sortCol === col ? (d === 'asc' ? 'desc' : 'asc') : 'asc')
    setSortCol(col)
  }
  const SortIcon = ({ col }) => sortCol !== col
    ? <span style={{ color: 'var(--border)', marginLeft: 3 }}>↕</span>
    : <span style={{ color: 'var(--accent)', marginLeft: 3 }}>{sortDir === 'asc' ? '↑' : '↓'}</span>

  const filtered = items
    .filter(c => {
      if (statusFilter && c.status !== statusFilter) return false
      if (search) {
        const q = search.toLowerCase()
        if (!c.name.toLowerCase().includes(q) && !(c.inn || '').includes(q)) return false
      }
      return true
    })
    .sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol]
      let cmp
      if (typeof av === 'number' || typeof bv === 'number') cmp = (av || 0) - (bv || 0)
      else cmp = String(av || '').localeCompare(String(bv || ''), 'ru')
      return sortDir === 'asc' ? cmp : -cmp
    })

  const allSelected = filtered.length > 0 && filtered.every(c => selectedIds.includes(c.id))
  const toggleAll = () => setSelectedIds(allSelected ? [] : filtered.map(c => c.id))
  const toggleOne = (id) => setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const inp = { padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit' }
  const inpSm = (w) => ({ ...inp, width: w, padding: '5px 8px' })
  const btn = (p) => ({ padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit' })
  const btnSm = (p) => ({ ...btn(p), padding: '3px 10px', fontSize: 12 })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap',
    cursor: 'pointer', userSelect: 'none', background: 'var(--bg-card)', position: 'sticky', top: 0, zIndex: 10 }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)', verticalAlign: 'middle' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  return (
    <>
      <Head><title>Контрагенты</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 24px 50px' }}>
        <DirectoryTabs active="counterparties" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Контрагенты</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{filtered.length} из {items.length}</span>
        </div>

        {/* Строка поиска + кнопка добавления */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
          marginBottom: showForm ? 0 : 12 }}>
          <input style={{ ...inp, width: 260 }} placeholder="Поиск по названию или ИНН"
            value={search} onChange={e => setSearch(e.target.value)} />
          <select style={inp} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">Все виды</option>
            <option value="действующий">Действующий</option>
            <option value="виртуальный">Виртуальный</option>
          </select>
          {mayEdit && (
            <button style={btn(showForm)} onClick={() => showForm ? cancelForm() : setShowForm(true)}>
              {showForm ? 'Отмена' : '+ Добавить'}
            </button>
          )}
        </div>

        {/* Форма нового контрагента */}
        {mayEdit && showForm && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderTop: 'none', borderRadius: '0 0 var(--radius-card) var(--radius-card)',
            padding: '14px 16px', marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новый контрагент</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Название *</div>
                <input style={inpSm(260)} placeholder="ООО Контрагент" autoFocus
                  value={newForm.name} onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))}
                  onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') cancelForm() }} />
              </div>
              <div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>ИНН</div>
                <input style={inpSm(150)} placeholder="1234567890"
                  value={newForm.inn} onChange={e => setNewForm(f => ({ ...f, inn: e.target.value }))}
                  onKeyDown={e => { if (e.key === 'Enter') handleCreate() }} />
              </div>
              <div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Вид</div>
                <select style={inp} value={newForm.status} onChange={e => setNewForm(f => ({ ...f, status: e.target.value }))}>
                  <option value="действующий">Действующий</option>
                  <option value="виртуальный">Виртуальный</option>
                </select>
              </div>
              <button style={btn(true)} onClick={handleCreate} disabled={newSaving}>
                {newSaving ? '…' : 'Создать'}
              </button>
              <button style={btn(false)} onClick={cancelForm}>Отмена</button>
            </div>
            {newError && <div style={{ color: 'var(--danger)', fontSize: 12.5, marginTop: 6 }}>{newError}</div>}
          </div>
        )}

        {/* Панель массового редактирования */}
        {mayEdit && selectedIds.length > 0 && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-card)', padding: '12px 16px', marginBottom: 12,
            display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', alignSelf: 'center' }}>
              Выбрано: {selectedIds.length}
            </span>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Вид</div>
              <select style={inp} value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}>
                <option value="">— не менять —</option>
                <option value="действующий">Действующий</option>
                <option value="виртуальный">Виртуальный</option>
              </select>
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Группа</div>
              <input style={inpSm(180)} placeholder="Новая группа"
                value={bulkGroup === '__reset__' ? '' : bulkGroup}
                onChange={e => setBulkGroup(e.target.value)} />
            </div>
            <button onClick={() => setBulkGroup('__reset__')}
              style={{ ...btn(false), color: bulkGroup === '__reset__' ? 'var(--accent)' : undefined,
                border: bulkGroup === '__reset__' ? '1px solid var(--accent)' : '1px solid var(--border)' }}
              title="Вернуть автоматический расчёт группы (самая частая статья)">
              Сбросить группу на авто
            </button>
            <button style={btn(true)} onClick={handleBulkApply} disabled={bulkSaving}>
              {bulkSaving ? '…' : `Применить к ${selectedIds.length}`}
            </button>
            {isAdmin && (
              deleteConfirming ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <input type="password" placeholder="Ваш пароль" autoFocus
                    value={deletePassword} onChange={e => setDeletePassword(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleBulkDelete()}
                    style={inpSm(180)} />
                  <button style={{ ...btn(true), background: 'var(--danger)' }}
                    onClick={handleBulkDelete} disabled={deleteLoading}>
                    {deleteLoading ? '…' : 'Подтвердить удаление'}
                  </button>
                  <button style={btn(false)}
                    onClick={() => { setDeleteConfirming(false); setDeletePassword(''); setDeleteError('') }}>
                    Отмена
                  </button>
                  {deleteError && <span style={{ color: 'var(--danger)', fontSize: 12.5 }}>{deleteError}</span>}
                </div>
              ) : (
                <button style={{ ...btn(false), color: 'var(--danger)' }}
                  onClick={() => { setDeleteConfirming(true); setDeletePassword(''); setDeleteError('') }}>
                  Удалить {selectedIds.length}
                </button>
              )
            )}
            <button style={btn(false)}
              onClick={() => { setSelectedIds([]); setBulkStatus(''); setBulkGroup('');
                setDeleteConfirming(false); setDeletePassword(''); setDeleteError('') }}>
              Снять выделение
            </button>
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
            borderRadius: 'var(--radius-card)', overflow: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
              <thead><tr>
                {mayEdit && <th style={{ ...th, width: 32, cursor: 'default' }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>}
                <th style={{ ...th, width: 44 }} onClick={() => handleSort('id')}>ID <SortIcon col="id" /></th>
                <th style={th} onClick={() => handleSort('name')}>Название <SortIcon col="name" /></th>
                <th style={th} onClick={() => handleSort('inn')}>ИНН <SortIcon col="inn" /></th>
                <th style={{ ...th, width: 90, textAlign: 'center', cursor: 'default' }}
                  title="Кол-во договоров, привязанных к контрагенту">Договоров</th>
                <th style={{ ...th, width: 64, textAlign: 'right' }} onClick={() => handleSort('term_days')}
                  title="Отсрочка, дн.">Отс. <SortIcon col="term_days" /></th>
                <th style={th} onClick={() => handleSort('relation')}>Статус <SortIcon col="relation" /></th>
                <th style={th} onClick={() => handleSort('group')}>Группа <SortIcon col="group" /></th>
                <th style={{ ...th, width: 34, textAlign: 'center', cursor: 'default' }}
                  title="Вид контрагента">Вид</th>
                <th style={{ ...th, textAlign: 'right', width: 64 }} onClick={() => handleSort('op_count')}
                  title="Операции">Опе. <SortIcon col="op_count" /></th>
                <th style={{ ...th, textAlign: 'right' }} onClick={() => handleSort('receivable')}>Дебиторка <SortIcon col="receivable" /></th>
                <th style={{ ...th, textAlign: 'right' }} onClick={() => handleSort('payable')}>Кредиторка <SortIcon col="payable" /></th>
                <th style={{ ...th, textAlign: 'right' }} onClick={() => handleSort('income_paid')}>Поступления <SortIcon col="income_paid" /></th>
                <th style={{ ...th, textAlign: 'right' }} onClick={() => handleSort('expense_paid')}>Выплаты <SortIcon col="expense_paid" /></th>
                <th style={{ ...th, textAlign: 'right' }} onClick={() => handleSort('diff')}>Разница <SortIcon col="diff" /></th>
                <th style={{ ...th, width: 90 }} onClick={() => handleSort('last_op_date')}>Дата <SortIcon col="last_op_date" /></th>
                <th style={{ ...th, cursor: 'default' }}>Действия</th>
              </tr></thead>
              <tbody>
                {filtered.map(c => {
                  const isEdit = editId === c.id
                  const relColor = RELATION_COLORS[c.relation] || { bg: 'var(--bg-subtle)', color: 'var(--muted)' }
                  return (
                    <tr key={c.id} style={{ background: isEdit ? 'var(--accent-tint)' : undefined }}>
                      {mayEdit && <td style={td}>
                        <input type="checkbox" checked={selectedIds.includes(c.id)} onChange={() => toggleOne(c.id)} />
                      </td>}
                      <td style={{ ...td, color: 'var(--muted)' }}>{c.id}</td>
                      <td style={td}>
                        {isEdit ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <input autoFocus value={editDraft.name}
                              onChange={e => setEditDraft(d => ({ ...d, name: e.target.value }))}
                              style={{ ...inp, width: 220, padding: '5px 8px' }} />
                            {isAdmin && (
                              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12.5, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                                <input type="checkbox" checked={editDraft.is_own_company}
                                  onChange={e => setEditDraft(d => ({ ...d, is_own_company: e.target.checked }))} />
                                🏢 Наша
                              </label>
                            )}
                          </div>
                        ) : (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Link href={`/counterparty/${c.id}`}
                              style={{ color: 'var(--accent)', textDecoration: 'none' }}>{c.name}</Link>
                            {c.is_own_company && (
                              <span style={{ fontSize: 11.5, padding: '1px 6px', borderRadius: 10,
                                background: '#dbeafe', color: '#1d4ed8', fontWeight: 500, whiteSpace: 'nowrap' }}>
                                🏢 Наша
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                      <td style={td}>
                        {isEdit
                          ? <input value={editDraft.inn} onChange={e => setEditDraft(d => ({ ...d, inn: e.target.value }))}
                              style={{ ...inp, width: 120, padding: '5px 8px' }} />
                          : (c.inn || dash)}
                      </td>
                      <td style={{ ...td, textAlign: 'center' }}>
                        {c.contracts_count > 0 ? c.contracts_count : <span style={{ color: 'var(--muted)' }}>0</span>}
                      </td>
                      <td style={{ ...td, textAlign: 'right' }}>
                        {isEdit
                          ? <input type="number" min="0" value={editDraft.term_days}
                              onChange={e => setEditDraft(d => ({ ...d, term_days: e.target.value }))}
                              placeholder={String(DEFAULT_TERM_DAYS)}
                              style={{ ...inp, width: 70, padding: '5px 8px', textAlign: 'right' }} />
                          : (c.term_days_is_default
                              ? <span style={{ color: 'var(--muted)' }} title="Значение по умолчанию">{c.term_days_effective}</span>
                              : <span title="Задано вручную">{c.term_days_effective}</span>)}
                      </td>
                      <td style={td}>
                        {c.relation
                          ? <span style={{ fontSize: 12.5, padding: '2px 8px', borderRadius: 20,
                              whiteSpace: 'nowrap', background: relColor.bg, color: relColor.color }}>
                              {RELATION_LABELS[c.relation]}
                            </span>
                          : dash}
                      </td>
                      <td style={{ ...td, color: 'var(--muted)', maxWidth: 160,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={c.group_is_override ? `${c.group} (задано вручную)` : (c.group || '')}>
                        {c.group_is_override && <span style={{ color: '#d97706', marginRight: 3 }}>✎</span>}
                        {c.group || dash}
                      </td>
                      <td style={{ ...td, textAlign: 'center' }}>
                        {isEdit ? (
                          <select value={editDraft.status}
                            onChange={e => setEditDraft(d => ({ ...d, status: e.target.value }))}
                            style={{ ...inp, padding: '5px 8px' }}>
                            <option value="действующий">Действующий</option>
                            <option value="виртуальный">Виртуальный</option>
                          </select>
                        ) : (
                          <span title={c.status === 'действующий' ? 'Действующий' : 'Виртуальный'}
                            style={{ width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
                              background: c.status === 'действующий' ? '#16a34a' : '#2563eb' }} />
                        )}
                      </td>
                      <td style={{ ...td, textAlign: 'right' }}>{c.op_count}</td>
                      <td style={{ ...td, textAlign: 'right', color: '#2563eb', whiteSpace: 'nowrap' }}>
                        {c.receivable > 0 ? fmt(c.receivable) : dash}
                      </td>
                      <td style={{ ...td, textAlign: 'right', color: '#d97706', whiteSpace: 'nowrap' }}>
                        {c.payable > 0 ? fmt(c.payable) : dash}
                      </td>
                      <td style={{ ...td, textAlign: 'right', color: '#16a34a', whiteSpace: 'nowrap' }}>
                        {c.income_paid > 0 ? fmt(c.income_paid) : dash}
                      </td>
                      <td style={{ ...td, textAlign: 'right', color: '#dc2626', whiteSpace: 'nowrap' }}>
                        {c.expense_paid > 0 ? fmt(c.expense_paid) : dash}
                      </td>
                      <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 500,
                        color: c.diff >= 0 ? '#16a34a' : '#dc2626' }}>
                        {fmt(c.diff)}
                      </td>
                      <td style={{ ...td, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                        {fmtDate(c.last_op_date)}
                      </td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        {mayEdit && isEdit ? (
                          <>
                            <button style={btnSm(true)} onClick={() => handleSave(c.id)} disabled={saving}>
                              {saving ? '…' : '✓'}
                            </button>
                            {' '}
                            <button style={btnSm(false)} onClick={cancelEdit} disabled={saving}>✕</button>
                            {editError && <div style={{ color: 'var(--danger)', fontSize: 12, marginTop: 4, maxWidth: 200 }}>{editError}</div>}
                          </>
                        ) : mayEdit ? (
                          <button style={btnSm(false)} onClick={() => openEdit(c)}>✏️</button>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
                {!filtered.length && (
                  <tr><td colSpan={mayEdit ? 17 : 16}
                    style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
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
