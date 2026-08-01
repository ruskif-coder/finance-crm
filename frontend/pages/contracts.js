import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'
const fmtEndDate = (s) => {
  if (!s) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(s).toLocaleDateString('ru-RU')
  return s
}

const EMPTY = {
  counterparty_id: null, contract_number: '', contract_date: '', inn: '',
  counterparty_name: '', marketing_name: '', cooperation_format: '',
  end_date_text: '', prolongation: '', payment_form: '',
  payment_term_days: '', payment_term_condition: '', note: '', document_link: '',
}
const COOPERATION_FORMATS = ['Агентство КЛ', 'Агентство ПД', 'Клиент', 'Подрядчик', 'Аптека', 'Паблишер', 'Рекламная система']
const PROLONGATION_OPTIONS = ['АВТО на год', 'По соглашению', 'Нет']
const PAYMENT_TERM_CONDITIONS = ['С даты УПД', 'С даты АКТ', 'По периоду']

function CounterpartySearch({ counterparties, value, onChange, onCreateNew }) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const selected = counterparties.find(c => c.id === value)
  const filtered = counterparties.filter(c => c.name.toLowerCase().includes(search.toLowerCase())).slice(0, 50)
  const handleCreate = async () => {
    if (!newName.trim()) return
    const created = await onCreateNew(newName.trim())
    if (created) { onChange(created.id); setSearch(''); setNewName(''); setCreating(false); setOpen(false) }
  }
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div onClick={() => { setOpen(o => !o); setSearch('') }}
        style={{ padding: '5px 8px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '13px', cursor: 'pointer', background: 'white', userSelect: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 200 }}>
        {selected ? selected.name : '— выберите контрагента —'}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, minWidth: '260px', marginTop: '4px', background: 'white', border: '1px solid #d1d5db', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 500, maxHeight: '280px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px', borderBottom: '1px solid #f3f4f6' }}>
            <input autoFocus placeholder="Поиск контрагента…" value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '13px', outline: 'none' }} />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            <div onClick={() => { onChange(null); setOpen(false) }}
              style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '13px', color: '#6b7280', borderBottom: '1px solid #f9fafb' }}>— не указан —</div>
            {filtered.map(c => (
              <div key={c.id} onClick={() => { onChange(c.id); setOpen(false); setSearch('') }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '13px', background: value === c.id ? '#eff6ff' : 'white' }}>
                {c.name}
              </div>
            ))}
            {search && !filtered.find(c => c.name.toLowerCase() === search.toLowerCase()) && (
              <div onClick={() => { setNewName(search); setCreating(true) }}
                style={{ padding: '7px 12px', cursor: 'pointer', fontSize: '13px', color: '#2563eb', borderTop: '1px solid #f3f4f6' }}>
                + Создать «{search}»
              </div>
            )}
          </div>
          {creating && (
            <div style={{ padding: '8px', borderTop: '1px solid #d1d5db', display: 'flex', gap: '6px' }}>
              <input value={newName} onChange={e => setNewName(e.target.value)}
                style={{ flex: 1, padding: '5px 8px', borderRadius: '6px', border: '1px solid #2563eb', fontSize: '13px', outline: 'none' }} />
              <button onClick={handleCreate}
                style={{ padding: '5px 10px', borderRadius: '6px', border: 'none', background: '#2563eb', color: 'white', fontSize: '13px', cursor: 'pointer' }}>Создать</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const SelectWithLegacy = ({ value, options, onChange, style, emptyLabel }) => (
  <select value={value || ''} onChange={onChange} style={style}>
    <option value="">{emptyLabel || '—'}</option>
    {value && !options.includes(value) && <option value={value}>{value} (старое значение)</option>}
    {options.map(o => <option key={o} value={o}>{o}</option>)}
  </select>
)

function SelectWithOther({ value, options, onChange, style, emptyLabel }) {
  const isKnownCustom = !!value && !options.includes(value)
  const [customMode, setCustomMode] = useState(isKnownCustom)
  const selectValue = customMode ? 'Прочее' : (value || '')
  return (
    <span style={{ display: 'inline-flex', gap: '6px' }}>
      <select value={selectValue} onChange={e => {
        const v = e.target.value
        if (v === 'Прочее') { setCustomMode(true); onChange({ target: { value: '' } }) }
        else { setCustomMode(false); onChange(e) }
      }} style={style}>
        <option value="">{emptyLabel || '—'}</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
        <option value="Прочее">Прочее</option>
      </select>
      {customMode && (
        <input type="text" value={value || ''} placeholder="Укажите вариант" onChange={onChange}
          style={{ ...style, width: '150px' }} />
      )}
    </span>
  )
}

export default function Contracts() {
  const router = useRouter()
  const [perms, setPerms] = useState({})
  const [role, setRole] = useState('')
  const [counterparties, setCounterparties] = useState([])
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')

  const [search, setSearch] = useState('')
  const [formatFilter, setFormatFilter] = useState('')
  const [prolongFilter, setProlongFilter] = useState('')
  const [sortCol, setSortCol] = useState('contract_date')
  const [sortDir, setSortDir] = useState('desc')

  const [showForm, setShowForm] = useState(false)
  const [newForm, setNewForm] = useState(EMPTY)
  const [newEndDateMode, setNewEndDateMode] = useState('date')
  const [newFile, setNewFile] = useState(null)
  const [creating, setCreating] = useState(false)
  const [fileUploading, setFileUploading] = useState(false)
  const [createError, setCreateError] = useState('')

  const [editId, setEditId] = useState(null)
  const [editDraft, setEditDraft] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')

  const [selectedIds, setSelectedIds] = useState([])
  const [bulkFormat, setBulkFormat] = useState('')
  const [bulkProlong, setBulkProlong] = useState('')
  const [bulkDays, setBulkDays] = useState('')
  const [bulkCondition, setBulkCondition] = useState('')
  const [bulkSaving, setBulkSaving] = useState(false)

  const [importPreview, setImportPreview] = useState(null)
  const [importFile, setImportFile] = useState(null)
  const [importApplying, setImportApplying] = useState(false)
  const [uploadTargetId, setUploadTargetId] = useState(null)
  const [uploadingId, setUploadingId] = useState(null)

  const importRef = useRef(null)
  const uploadRef = useRef(null)
  const newUploadRef = useRef(null)

  const isAdmin = role === 'admin'
  const mayEdit = isAdmin || can(perms, 'contracts', 'edit')

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const loadAll = async () => {
    setLoading(true); setError('')
    try {
      const [cp, ct] = await Promise.all([
        api.get('/counterparties/registry', auth()),
        api.get('/contracts/registry', auth()),
      ])
      setCounterparties(cp.data.items)
      setItems(ct.data.items)
    } catch (e) {
      if (e.response?.status === 401) { router.push('/login'); return }
      setError(e.response?.data?.detail || 'Не удалось загрузить данные')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try {
      setPerms(JSON.parse(localStorage.getItem('permissions') || '{}'))
      setRole(localStorage.getItem('role') || '')
    } catch (e) {}
    loadAll()
  }, [])

  const createCounterparty = async (name) => {
    try {
      const res = await api.post('/counterparties/', { name, vat_rate: 0 }, auth())
      await loadAll()
      return { id: res.data.id, name }
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при создании контрагента')
      return null
    }
  }

  const payload = (d) => {
    const { _end_date_mode, ...rest } = d
    return { ...rest, contract_date: d.contract_date || null,
      payment_term_days: d.payment_term_days !== '' && d.payment_term_days != null ? parseInt(d.payment_term_days, 10) : null }
  }

  const cancelForm = () => {
    setShowForm(false); setNewForm(EMPTY); setNewFile(null)
    setNewEndDateMode('date'); setCreateError('')
    if (newUploadRef.current) newUploadRef.current.value = ''
  }

  const handleCreate = async () => {
    if (!newForm.counterparty_id) { setCreateError('Выберите контрагента из реестра'); return }
    setCreateError(''); setCreating(true)
    try {
      const res = await api.post('/contracts/', payload(newForm), auth())
      const newId = res.data?.id
      if (newId && newFile) {
        setFileUploading(true)
        try {
          const fd = new FormData(); fd.append('file', newFile)
          await api.post(`/contracts/${newId}/upload`, fd, auth())
        } catch { alert('Договор создан, но файл не загрузился') }
        finally { setFileUploading(false) }
      }
      cancelForm(); flash('Договор создан'); loadAll()
    } catch (e) { setCreateError(e.response?.data?.detail || 'Ошибка при создании') }
    finally { setCreating(false) }
  }

  const openEdit = (c) => {
    setEditId(c.id)
    const endMode = c.end_date_text && !/^\d{4}-\d{2}-\d{2}$/.test(c.end_date_text) ? 'text' : 'date'
    setEditDraft({ ...EMPTY, ...c, contract_date: c.contract_date || '',
      payment_term_days: c.payment_term_days != null ? String(c.payment_term_days) : '',
      document_link: c.document_link || '', _end_date_mode: endMode })
    setEditError('')
  }
  const cancelEdit = () => { setEditId(null); setEditError('') }

  const handleSave = async (id) => {
    setSaving(true); setEditError('')
    try {
      await api.put(`/contracts/${id}`, payload(editDraft), auth())
      setEditId(null); loadAll()
    } catch (e) { setEditError(e.response?.data?.detail || 'Ошибка при сохранении') }
    finally { setSaving(false) }
  }

  const handleDelete = async (c) => {
    if (!confirm(`Удалить договор № ${c.contract_number || '—'} (${c.counterparty_name || '—'})?`)) return
    try { await api.delete(`/contracts/${c.id}`, auth()); loadAll() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка при удалении') }
  }

  const downloadExport = async () => {
    try {
      const res = await api.get('/contracts/export', { responseType: 'blob', ...auth() })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      a.download = `dogovory_${new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '')}.xlsx`
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch { alert('Не удалось скачать файл') }
  }

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    setImportFile(file)
    const fd = new FormData(); fd.append('file', file)
    try {
      const res = await api.post('/contracts/import/preview', fd, auth())
      setImportPreview(res.data)
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка при разборе файла') }
    e.target.value = ''
  }

  const applyImport = async () => {
    if (!importFile) return
    setImportApplying(true)
    const fd = new FormData(); fd.append('file', importFile)
    try {
      const res = await api.post('/contracts/import/apply', fd, auth())
      setImportPreview(null); setImportFile(null)
      loadAll()
      alert(`Обновлено договоров: ${res.data.updated}${res.data.skipped?.length ? '\nПропущено: ' + res.data.skipped.join('\n') : ''}`)
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка при применении импорта') }
    finally { setImportApplying(false) }
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file || !uploadTargetId) return
    const fd = new FormData(); fd.append('file', file)
    setUploadingId(uploadTargetId)
    try { await api.post(`/contracts/${uploadTargetId}/upload`, fd, auth()); loadAll() }
    catch (err) { alert(err.response?.data?.detail || 'Ошибка при загрузке файла') }
    finally { setUploadingId(null); setUploadTargetId(null) }
    e.target.value = ''
  }

  const handleDownload = async (id, storedFilename) => {
    try {
      const res = await api.get(`/contracts/${id}/download`, { responseType: 'blob', ...auth() })
      const prefix = `${id}_`
      const displayName = storedFilename.startsWith(prefix) ? storedFilename.slice(prefix.length) : storedFilename
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url; a.download = displayName
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch { alert('Не удалось скачать файл') }
  }

  const handleDeleteDoc = async (id) => {
    if (!confirm('Удалить прикреплённый документ?')) return
    try { await api.delete(`/contracts/${id}/document`, auth()); loadAll() }
    catch (err) { alert(err.response?.data?.detail || 'Ошибка при удалении документа') }
  }

  const handleBulkApply = async () => {
    const fields = {}
    if (bulkFormat) fields.cooperation_format = bulkFormat
    if (bulkProlong) fields.prolongation = bulkProlong
    if (bulkDays !== '') fields.payment_term_days = parseInt(bulkDays, 10)
    if (bulkCondition) fields.payment_term_condition = bulkCondition
    if (!Object.keys(fields).length) { alert('Выберите хотя бы одно поле'); return }
    if (!confirm(`Изменить ${selectedIds.length} договоров?`)) return
    setBulkSaving(true)
    try {
      await api.patch('/contracts/bulk', { ids: selectedIds, ...fields }, auth())
      setSelectedIds([]); setBulkFormat(''); setBulkProlong(''); setBulkDays(''); setBulkCondition('')
      loadAll()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBulkSaving(false) }
  }

  const handleBulkDelete = async () => {
    if (!confirm(`Удалить ${selectedIds.length} договоров? Необратимо.`)) return
    setBulkSaving(true)
    try {
      await api.delete('/contracts/bulk', { data: { ids: selectedIds }, ...auth() })
      setSelectedIds([]); loadAll()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBulkSaving(false) }
  }

  const handleSort = (col) => {
    setSortDir(d => sortCol === col ? (d === 'asc' ? 'desc' : 'asc') : 'asc')
    setSortCol(col)
  }
  const SortIcon = ({ col }) => sortCol !== col
    ? <span style={{ color: 'var(--border)', marginLeft: 3 }}>↕</span>
    : <span style={{ color: 'var(--accent)', marginLeft: 3 }}>{sortDir === 'asc' ? '↑' : '↓'}</span>

  const formatOptions = [...new Set(items.map(c => c.cooperation_format).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'))
  const prolongOptions = [...new Set(items.map(c => c.prolongation).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'))

  const filtered = items
    .filter(c => {
      if (formatFilter && c.cooperation_format !== formatFilter) return false
      if (prolongFilter && c.prolongation !== prolongFilter) return false
      if (search) {
        const q = search.toLowerCase()
        if (![c.contract_number, c.counterparty_name, c.marketing_name, c.inn].some(v => (v || '').toLowerCase().includes(q))) return false
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
  const selSm = (w) => ({ ...inp, width: w, padding: '5px 8px' })
  const btn = (p) => ({ padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, background: p ? 'var(--accent)' : 'var(--bg-subtle)', color: p ? '#fff' : 'inherit' })
  const btnSm = (p) => ({ ...btn(p), padding: '3px 10px', fontSize: 12 })
  const th = { padding: '9px 10px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap',
    cursor: 'pointer', userSelect: 'none' }
  const td = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-row)', verticalAlign: 'top' }
  const dash = <span style={{ color: 'var(--muted)' }}>—</span>

  return (
    <>
      <Head><title>Договора</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 24px 50px' }}>
        <DirectoryTabs active="contracts" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Договора</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length} записей</span>
        </div>

        {/* Toolbar: поиск + фильтры + кнопка добавления */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
          marginBottom: showForm ? 0 : 12 }}>
          <input style={{ ...inp, width: 280 }} placeholder="Поиск по № договора, контрагенту, ИНН"
            value={search} onChange={e => setSearch(e.target.value)} />
          <select style={inp} value={formatFilter} onChange={e => setFormatFilter(e.target.value)}>
            <option value="">Все форматы</option>
            {formatOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <select style={inp} value={prolongFilter} onChange={e => setProlongFilter(e.target.value)}>
            <option value="">Все типы пролонгации</option>
            {prolongOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <button style={btn(false)} onClick={downloadExport} title="Экспорт в Excel">⬇️</button>
          {mayEdit && (
            <>
              <input ref={importRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleImportFile} />
              <button style={btn(false)} onClick={() => importRef.current?.click()} title="Импорт из Excel">⬆️</button>
              <button style={btn(showForm)}
                onClick={() => showForm ? cancelForm() : setShowForm(true)}>
                {showForm ? 'Отмена' : '+ Добавить'}
              </button>
            </>
          )}
          <input ref={uploadRef} type="file" style={{ display: 'none' }} onChange={handleUpload} />
          <input ref={newUploadRef} type="file" style={{ display: 'none' }}
            onChange={e => { setNewFile(e.target.files?.[0] || null) }} />
        </div>

        {/* Форма нового договора */}
        {mayEdit && showForm && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderTop: 'none', borderRadius: '0 0 var(--radius-card) var(--radius-card)',
            padding: '14px 16px', marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новый договор</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <CounterpartySearch counterparties={counterparties} value={newForm.counterparty_id}
                onChange={id => setNewForm(p => ({ ...p, counterparty_id: id }))}
                onCreateNew={createCounterparty} />
              <input readOnly
                value={(counterparties.find(cp => cp.id === newForm.counterparty_id) || {}).inn || ''}
                placeholder="ИНН" title="ИНН заполняется из реестра автоматически"
                style={{ ...inpSm(120), color: 'var(--muted)', cursor: 'default' }} />
              <input placeholder="№ договора" value={newForm.contract_number}
                onChange={e => setNewForm(p => ({ ...p, contract_number: e.target.value }))}
                style={inpSm(140)} />
              <input type="date" value={newForm.contract_date}
                onChange={e => setNewForm(p => ({ ...p, contract_date: e.target.value }))}
                style={inpSm(150)} />
              <input placeholder="Название маркетинговое" value={newForm.marketing_name}
                onChange={e => setNewForm(p => ({ ...p, marketing_name: e.target.value }))}
                style={inpSm(200)} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
              <SelectWithOther value={newForm.cooperation_format} options={COOPERATION_FORMATS}
                emptyLabel="Формат сотрудничества"
                onChange={e => setNewForm(p => ({ ...p, cooperation_format: e.target.value }))}
                style={selSm(190)} />
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                {newEndDateMode === 'date'
                  ? <input type="date" value={newForm.end_date_text}
                      onChange={e => setNewForm(p => ({ ...p, end_date_text: e.target.value }))}
                      style={inpSm(150)} />
                  : <input type="text" placeholder="Напр. «Бессрочно»" value={newForm.end_date_text}
                      onChange={e => setNewForm(p => ({ ...p, end_date_text: e.target.value }))}
                      style={inpSm(220)} />}
                <button type="button"
                  onClick={() => { setNewEndDateMode(m => m === 'date' ? 'text' : 'date'); setNewForm(p => ({ ...p, end_date_text: '' })) }}
                  style={{ ...btnSm(false), padding: '3px 7px', fontSize: 12 }}
                  title={newEndDateMode === 'date' ? 'Ввести текстом' : 'Выбрать дату'}>
                  {newEndDateMode === 'date' ? 'Aa' : '📅'}
                </button>
              </div>
              <SelectWithOther value={newForm.prolongation} options={PROLONGATION_OPTIONS}
                emptyLabel="Пролонгация"
                onChange={e => setNewForm(p => ({ ...p, prolongation: e.target.value }))}
                style={selSm(170)} />
              <input type="number" min="0" placeholder="Срок оплаты, дни" value={newForm.payment_term_days}
                onChange={e => setNewForm(p => ({ ...p, payment_term_days: e.target.value }))}
                style={inpSm(140)} />
              <SelectWithLegacy value={newForm.payment_term_condition} options={PAYMENT_TERM_CONDITIONS}
                emptyLabel="Условие"
                onChange={e => setNewForm(p => ({ ...p, payment_term_condition: e.target.value }))}
                style={selSm(170)} />
              <button style={btn(true)} onClick={handleCreate}
                disabled={creating || fileUploading}>
                {fileUploading ? '📎…' : creating ? '…' : 'Создать'}
              </button>
              <button style={btn(false)} onClick={cancelForm}>Отмена</button>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
              <input placeholder="🔗 Ссылка на документ (ЭДО, облако…)" value={newForm.document_link}
                onChange={e => setNewForm(p => ({ ...p, document_link: e.target.value }))}
                style={inpSm(300)} />
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>или</span>
              <button type="button" onClick={() => newUploadRef.current?.click()}
                style={{ ...btnSm(false), background: newFile ? 'var(--accent-tint)' : undefined, color: newFile ? 'var(--accent)' : undefined }}>
                {newFile ? `📎 ${newFile.name}` : '📎 Прикрепить файл'}
              </button>
              {newFile && (
                <button type="button" onClick={() => { setNewFile(null); if (newUploadRef.current) newUploadRef.current.value = '' }}
                  style={{ ...btnSm(false), color: 'var(--danger)' }}>✕</button>
              )}
              {newForm.document_link && (
                <a href={newForm.document_link} target="_blank" rel="noopener noreferrer"
                  style={{ ...btnSm(false), textDecoration: 'none', display: 'inline-block' }}>🔗 Открыть</a>
              )}
            </div>
            {createError && <div style={{ color: 'var(--danger)', fontSize: 12.5, marginTop: 6 }}>{createError}</div>}
          </div>
        )}

        {/* Превью импорта */}
        {importPreview && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)',
              padding: 24, maxWidth: 820, width: '100%', maxHeight: '80vh', overflow: 'auto',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)', border: '1px solid var(--border-card)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 17, fontWeight: 700 }}>Превью импорта договоров</div>
                <button onClick={() => { setImportPreview(null); setImportFile(null) }}
                  style={{ border: 'none', background: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--muted)' }}>✕</button>
              </div>
              {importPreview.changes.length === 0 && importPreview.skipped.length === 0 && (
                <div style={{ color: 'var(--muted)', padding: '20px 0', textAlign: 'center' }}>Изменений не обнаружено</div>
              )}
              {importPreview.changes.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>Будет обновлено: {importPreview.changes.length}</div>
                  {importPreview.changes.map(ch => (
                    <div key={ch.id} style={{ border: '1px solid var(--border-card)', borderRadius: 'var(--radius-card-sm)', padding: '10px 14px', marginBottom: 8 }}>
                      <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13 }}>{ch.contract_number} — {ch.counterparty_name}</div>
                      {ch.diffs.map((d, i) => (
                        <div key={i} style={{ fontSize: 12.5, marginBottom: 3 }}>
                          <span style={{ color: 'var(--muted)' }}>{d.label}:</span>{' '}
                          <span style={{ color: 'var(--danger)', textDecoration: 'line-through' }}>{d.old || '—'}</span>{' → '}
                          <span style={{ color: 'var(--success)' }}>{d.new || '—'}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              {importPreview.skipped.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--warning)' }}>Пропущено строк: {importPreview.skipped.length}</div>
                  {importPreview.skipped.map((s, i) => (
                    <div key={i} style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 2 }}>{s.reason}</div>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16,
                borderTop: '1px solid var(--border)', paddingTop: 16 }}>
                <button onClick={() => { setImportPreview(null); setImportFile(null) }} style={btn(false)}>Отмена</button>
                {importPreview.changes.length > 0 && (
                  <button onClick={applyImport} disabled={importApplying} style={btn(true)}>
                    {importApplying ? 'Применяем…' : `Применить (${importPreview.changes.length})`}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Сообщения */}
        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)',
          marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}

        {/* Панель массового редактирования */}
        {mayEdit && selectedIds.length > 0 && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-card)', padding: '12px 16px', marginBottom: 12,
            display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', alignSelf: 'center' }}>
              Выбрано: {selectedIds.length}
            </span>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Формат</div>
              <SelectWithOther value={bulkFormat} options={COOPERATION_FORMATS} emptyLabel="— не менять —"
                onChange={e => setBulkFormat(e.target.value)} style={selSm(180)} />
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Пролонгация</div>
              <SelectWithOther value={bulkProlong} options={PROLONGATION_OPTIONS} emptyLabel="— не менять —"
                onChange={e => setBulkProlong(e.target.value)} style={selSm(160)} />
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Срок оплаты, дни</div>
              <input type="number" min="0" placeholder="— не менять —" value={bulkDays}
                onChange={e => setBulkDays(e.target.value)} style={inpSm(130)} />
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }}>Условие</div>
              <SelectWithLegacy value={bulkCondition} options={PAYMENT_TERM_CONDITIONS} emptyLabel="— не менять —"
                onChange={e => setBulkCondition(e.target.value)} style={selSm(160)} />
            </div>
            <button style={btn(true)} onClick={handleBulkApply} disabled={bulkSaving}>
              {bulkSaving ? '…' : `Применить к ${selectedIds.length}`}
            </button>
            {isAdmin && (
              <button style={{ ...btn(false), color: 'var(--danger)' }} onClick={handleBulkDelete} disabled={bulkSaving}>
                {bulkSaving ? '…' : `Удалить ${selectedIds.length}`}
              </button>
            )}
            <button style={btn(false)}
              onClick={() => { setSelectedIds([]); setBulkFormat(''); setBulkProlong(''); setBulkDays(''); setBulkCondition('') }}>
              Снять выделение
            </button>
          </div>
        )}

        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'auto', width: 'max-content', maxWidth: '100%' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
              <thead><tr>
                {mayEdit && <th style={{ ...th, width: 32, cursor: 'default' }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>}
                <th style={{ ...th, width: 44 }} onClick={() => handleSort('id')}>ID <SortIcon col="id" /></th>
                <th style={{ ...th, width: 255 }} onClick={() => handleSort('counterparty_name')}>Контрагент <SortIcon col="counterparty_name" /></th>
                <th style={{ ...th, width: 120 }} onClick={() => handleSort('contract_number')}>№ договора <SortIcon col="contract_number" /></th>
                <th style={{ ...th, width: 100 }} onClick={() => handleSort('contract_date')}>Дата <SortIcon col="contract_date" /></th>
                <th style={{ ...th, width: 110 }} onClick={() => handleSort('inn')}>ИНН <SortIcon col="inn" /></th>
                <th style={{ ...th, width: 170 }} onClick={() => handleSort('marketing_name')}>Назв. маркет. <SortIcon col="marketing_name" /></th>
                <th style={{ ...th, width: 130 }} onClick={() => handleSort('cooperation_format')}>Формат <SortIcon col="cooperation_format" /></th>
                <th style={{ ...th, width: 105 }} onClick={() => handleSort('end_date_text')}>Окончание <SortIcon col="end_date_text" /></th>
                <th style={{ ...th, width: 110 }} onClick={() => handleSort('prolongation')}>Пролонгация <SortIcon col="prolongation" /></th>
                <th style={{ ...th, width: 70, textAlign: 'right' }} onClick={() => handleSort('payment_term_days')}>Дни <SortIcon col="payment_term_days" /></th>
                <th style={{ ...th, width: 120 }} onClick={() => handleSort('payment_term_condition')}>Условие <SortIcon col="payment_term_condition" /></th>
                <th style={{ ...th, width: 130, cursor: 'default' }}>Действия</th>
              </tr></thead>
              <tbody>
                {filtered.map(c => {
                  const isEdit = editId === c.id
                  const w = (px) => ({ ...inp, width: px, padding: '5px 8px' })
                  const sw = (px) => ({ ...inp, width: px, padding: '5px 8px' })
                  return (
                    <tr key={c.id} style={{ background: isEdit ? 'var(--accent-tint)' : undefined }}>
                      {mayEdit && <td style={td}>
                        <input type="checkbox" checked={selectedIds.includes(c.id)} onChange={() => toggleOne(c.id)} />
                      </td>}
                      <td style={{ ...td, color: 'var(--muted)' }}>{c.id}</td>
                      <td style={{ ...td, maxWidth: 255, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={!isEdit ? (c.counterparty_name || '') : undefined}>
                        {isEdit
                          ? <div style={{ width: 200 }}><CounterpartySearch counterparties={counterparties}
                              value={editDraft.counterparty_id}
                              onChange={id => setEditDraft(d => ({ ...d, counterparty_id: id }))}
                              onCreateNew={createCounterparty} /></div>
                          : <>{c.counterparty_name || dash}{!c.linked && <span title="Не привязан к реестру" style={{ marginLeft: 5, color: 'var(--warning)' }}>⚠</span>}</>}
                      </td>
                      <td style={td}>
                        {isEdit
                          ? <input value={editDraft.contract_number || ''} onChange={e => setEditDraft(d => ({ ...d, contract_number: e.target.value }))} style={w(110)} />
                          : (c.contract_number || dash)}
                      </td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        {isEdit
                          ? <input type="date" value={editDraft.contract_date || ''} onChange={e => setEditDraft(d => ({ ...d, contract_date: e.target.value }))} style={w(130)} />
                          : fmtDate(c.contract_date)}
                      </td>
                      <td style={td}>
                        {isEdit
                          ? (editDraft.counterparty_id
                            ? <span style={{ color: 'var(--muted)' }}>{(counterparties.find(cp => cp.id === editDraft.counterparty_id) || {}).inn || '—'}</span>
                            : <input value={editDraft.inn || ''} onChange={e => setEditDraft(d => ({ ...d, inn: e.target.value }))} style={w(110)} />)
                          : (c.inn || dash)}
                      </td>
                      <td style={{ ...td, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={!isEdit ? (c.marketing_name || '') : undefined}>
                        {isEdit
                          ? <input value={editDraft.marketing_name || ''} onChange={e => setEditDraft(d => ({ ...d, marketing_name: e.target.value }))} style={w(180)} />
                          : (c.marketing_name || dash)}
                      </td>
                      <td style={{ ...td, maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={!isEdit ? (c.cooperation_format || '') : undefined}>
                        {isEdit
                          ? <SelectWithOther value={editDraft.cooperation_format} options={COOPERATION_FORMATS}
                              onChange={e => setEditDraft(d => ({ ...d, cooperation_format: e.target.value }))} style={sw(170)} />
                          : (c.cooperation_format || dash)}
                      </td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        {isEdit
                          ? <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                              {(editDraft._end_date_mode || 'date') === 'date'
                                ? <input type="date" value={editDraft.end_date_text || ''} onChange={e => setEditDraft(d => ({ ...d, end_date_text: e.target.value }))} style={w(140)} />
                                : <input type="text" placeholder="Текст" value={editDraft.end_date_text || ''} onChange={e => setEditDraft(d => ({ ...d, end_date_text: e.target.value }))} style={w(160)} />}
                              <button type="button"
                                onClick={() => setEditDraft(d => ({ ...d, _end_date_mode: (d._end_date_mode || 'date') === 'date' ? 'text' : 'date', end_date_text: '' }))}
                                style={{ ...btnSm(false), padding: '2px 6px', fontSize: 11 }}>
                                {(editDraft._end_date_mode || 'date') === 'date' ? 'Aa' : '📅'}
                              </button>
                            </div>
                          : fmtEndDate(c.end_date_text)}
                      </td>
                      <td style={td}>
                        {isEdit
                          ? <SelectWithOther value={editDraft.prolongation} options={PROLONGATION_OPTIONS}
                              onChange={e => setEditDraft(d => ({ ...d, prolongation: e.target.value }))} style={sw(160)} />
                          : (c.prolongation || dash)}
                      </td>
                      <td style={{ ...td, textAlign: 'right' }}>
                        {isEdit
                          ? <input type="number" min="0" value={editDraft.payment_term_days}
                              onChange={e => setEditDraft(d => ({ ...d, payment_term_days: e.target.value }))}
                              style={{ ...w(80), textAlign: 'right' }} />
                          : (c.payment_term_days != null ? c.payment_term_days : dash)}
                      </td>
                      <td style={td}>
                        {isEdit
                          ? <SelectWithLegacy value={editDraft.payment_term_condition} options={PAYMENT_TERM_CONDITIONS}
                              onChange={e => setEditDraft(d => ({ ...d, payment_term_condition: e.target.value }))} style={sw(170)} />
                          : (c.payment_term_condition || dash)}
                      </td>
                      <td style={td}>
                        {isEdit ? (
                          <div style={{ minWidth: 240 }}>
                            <div style={{ marginBottom: 5, display: 'flex', gap: 4, alignItems: 'center' }}>
                              <input value={editDraft.document_link || ''} onChange={e => setEditDraft(d => ({ ...d, document_link: e.target.value }))}
                                placeholder="Ссылка на документ" style={{ ...w(180), fontSize: 12 }} />
                              {editDraft.document_link && (
                                <a href={editDraft.document_link} target="_blank" rel="noopener noreferrer"
                                  style={{ ...btnSm(false), textDecoration: 'none', display: 'inline-block', fontSize: 12 }}>🔗</a>
                              )}
                            </div>
                            <div style={{ marginBottom: 5, display: 'flex', gap: 4, alignItems: 'center' }}>
                              {c.attached_filename ? (
                                <>
                                  <button onClick={() => handleDownload(c.id, c.attached_filename)}
                                    style={btnSm(false)} title={c.attached_filename}>📥</button>
                                  <span style={{ fontSize: 11.5, color: 'var(--muted)', maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                    title={c.attached_filename.replace(new RegExp(`^${c.id}_`), '')}>
                                    {c.attached_filename.replace(new RegExp(`^${c.id}_`), '')}
                                  </span>
                                  <button onClick={() => handleDeleteDoc(c.id)}
                                    style={{ ...btnSm(false), color: 'var(--danger)' }}>✕</button>
                                </>
                              ) : (
                                <button onClick={() => { setUploadTargetId(c.id); uploadRef.current?.click() }}
                                  style={btnSm(false)}>
                                  {uploadingId === c.id ? '…' : '📎 Прикрепить'}
                                </button>
                              )}
                            </div>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button onClick={() => handleSave(c.id)} disabled={saving} style={btnSm(true)}>
                                {saving ? '…' : '✓ Сохранить'}
                              </button>
                              <button onClick={cancelEdit} disabled={saving} style={btnSm(false)}>Отмена</button>
                            </div>
                            {editError && <div style={{ color: 'var(--danger)', fontSize: 11.5, marginTop: 4 }}>{editError}</div>}
                          </div>
                        ) : (
                          <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'nowrap' }}>
                            {c.document_link && (
                              <a href={c.document_link} target="_blank" rel="noopener noreferrer"
                                style={{ ...btnSm(false), textDecoration: 'none', display: 'inline-block' }}>🔗</a>
                            )}
                            {c.attached_filename && (
                              <button onClick={() => handleDownload(c.id, c.attached_filename)}
                                title={`Скачать: ${c.attached_filename.replace(new RegExp(`^${c.id}_`), '')}`}
                                style={btnSm(false)}>📥</button>
                            )}
                            {mayEdit && (
                              <>
                                <button onClick={() => openEdit(c)} style={btnSm(false)} title="Редактировать">✏️</button>
                                <button onClick={() => handleDelete(c)} style={{ ...btnSm(false), color: 'var(--danger)' }} title="Удалить">🗑️</button>
                              </>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
                {!filtered.length && (
                  <tr><td colSpan={mayEdit ? 13 : 12} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
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
