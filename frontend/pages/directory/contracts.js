import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import api, { auth } from '@/lib/http'
import { useRouter } from 'next/router'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, IconBtn, inp, inpSm, selSm, btn, btnSm } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const ContractsMobile = dynamic(() => import('@/components/mobile/ContractsMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { T } from '@/lib/tokens'
import SectionTabs from '@/components/SectionTabs'


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

// формат сотрудничества → цвет чипа
const FMT_META = {
  'Клиент': { bg: 'var(--accent-tint)', fg: 'var(--accent)' },
  'Подрядчик': { bg: '#FBF0DE', fg: '#B26A0C' },
  'Агентство КЛ': { bg: '#F1EDFC', fg: T.mixed },
  'Агентство ПД': { bg: '#F1EDFC', fg: T.mixed },
  'Аптека': { bg: '#E6F5EF', fg: T.income },
  'Паблишер': { bg: '#E9F0FB', fg: '#3B6FD4' },
  'Рекламная система': { bg: '#FDEBF0', fg: '#C43C6B' },
}
const fmtMeta = (f) => FMT_META[f] || { bg: 'var(--bg-subtle)', fg: 'var(--text-muted)' }

// сетка таблицы (без sel-колонки — она добавляется отдельно при mayEdit)
const COLS = [
  ['id', '48px', 'ID', 'id'],
  ['cp', 'minmax(190px,1.5fr)', 'Контрагент', 'counterparty_name'],
  ['num', '120px', '№ договора', 'contract_number'],
  ['date', '92px', 'Дата', 'contract_date'],
  ['inn', '108px', 'ИНН', 'inn'],
  ['mkt', 'minmax(150px,1fr)', 'Назв. маркет.', 'marketing_name'],
  ['fmt', '152px', 'Формат', 'cooperation_format'],
  ['end', '100px', 'Окончание', 'end_date_text'],
  ['prol', '120px', 'Пролонгация', 'prolongation'],
  ['days', '52px', 'Дни', 'payment_term_days'],
  ['cond', '124px', 'Условие', 'payment_term_condition'],
  ['doc', '78px', 'Док.'],
  ['act', '74px', ''],
]
const RIGHT = new Set(['days'])

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
  const isMobile = useIsMobile()
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
  const [mobileLimit, setMobileLimit] = useState(50)

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

  // единый сейв для мобильной формы (create + edit)
  const mobileSave = async (f, id) => {
    if (!(f.contract_number || '').trim() && !(f.counterparty_name || f.counterparty_id)) { alert('Укажите № договора или контрагента'); return false }
    setSaving(true)
    try {
      if (id) await api.put(`/contracts/${id}`, payload(f), auth())
      else await api.post('/contracts/', payload(f), auth())
      await loadAll(); return true
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка при сохранении'); return false }
    finally { setSaving(false) }
  }

  // ── МОБИЛЬНАЯ ВЕРСИЯ ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Договора</title></Head>
        <Navbar active="directories" />
        <ContractsMobile
          total={items.length} rows={filtered} loading={loading} canEdit={mayEdit} counterparties={counterparties}
          search={search} setSearch={setSearch} formatFilter={formatFilter} setFormatFilter={setFormatFilter} formatOptions={formatOptions}
          onSave={mobileSave} saving={saving} onDownload={handleDownload} limit={mobileLimit} setLimit={setMobileLimit} />
      </div>
    )
  }

  const allSelected = filtered.length > 0 && filtered.every(c => selectedIds.includes(c.id))
  const toggleAll = () => setSelectedIds(allSelected ? [] : filtered.map(c => c.id))
  const toggleOne = (id) => setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  // стили inp/inpSm/selSm/btn/btnSm — общий модуль components/salesTableKit
  const dash = <span style={{ color: 'var(--text-faint)' }}>—</span>

  return (
    <>
      <Head><title>Договора</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SectionTabs section="directory" />

        <input ref={importRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleImportFile} />
        <input ref={uploadRef} type="file" style={{ display: 'none' }} onChange={handleUpload} />
        <input ref={newUploadRef} type="file" style={{ display: 'none' }} onChange={e => { setNewFile(e.target.files?.[0] || null) }} />

        {/* Карточка реестра */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '18px 24px 14px' }}>
        {/* Строка фильтров */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
          <h1 style={{ fontSize: 17, fontWeight: 700, margin: '0 6px 0 0', color: 'var(--text-primary)' }}>Договора</h1>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginRight: 4 }}>показано {filtered.length} из {items.length}</span>
          <input style={{ ...inp, width: 260 }} placeholder="№ договора, контрагент, ИНН…"
            value={search} onChange={e => setSearch(e.target.value)} />
          <select style={inp} value={formatFilter} onChange={e => setFormatFilter(e.target.value)}>
            <option value="">Все форматы</option>
            {formatOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <select style={inp} value={prolongFilter} onChange={e => setProlongFilter(e.target.value)}>
            <option value="">Все пролонгации</option>
            {prolongOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <IconBtn title="Сбросить фильтры" onClick={() => { setSearch(''); setFormatFilter(''); setProlongFilter('') }}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
            <IconBtn title="Экспорт в Excel" onClick={downloadExport}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg></IconBtn>
            {mayEdit && <IconBtn title="Импорт из Excel" onClick={() => importRef.current?.click()}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 21V9" /><path d="M7 13l5-5 5 5" /><path d="M4 4h16" /></svg></IconBtn>}
            {mayEdit && (
              <button style={btn(true)} onClick={() => showForm ? cancelForm() : setShowForm(true)}>
                {showForm ? 'Отмена' : '+ Договор'}
              </button>
            )}
          </span>
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
                <a href={/^https?:\/\//i.test(newForm.document_link) ? newForm.document_link : undefined} target="_blank" rel="noopener noreferrer"
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

        {loading && <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>}

        {!loading && (() => {
          const CCOLS = [
            ['sel', '26px', ''], ['id', '46px', 'ID', 'id'], ['cp', 'minmax(200px,1.4fr)', 'Контрагент', 'counterparty_name'],
            ['num', '118px', '№ договора', 'contract_number'], ['date', '92px', 'Дата', 'contract_date'], ['inn', '110px', 'ИНН', 'inn'],
            ['mkt', 'minmax(130px,1fr)', 'Назв. маркет.', 'marketing_name'], ['fmt', '132px', 'Формат', 'cooperation_format'],
            ['end', '104px', 'Окончание', 'end_date_text'], ['prol', '118px', 'Пролонгация', 'prolongation'],
            ['days', '52px', 'Дни', 'payment_term_days'], ['cond', '122px', 'Условие', 'payment_term_condition'],
            ['act', '92px', ''],
          ]
          const CRIGHT = new Set(['days'])
          const CGRID = CCOLS.map(c => c[1]).join(' ')
          const icoBtn = { width: 26, height: 26, borderRadius: 8, border: 'none', background: 'transparent', color: 'var(--text-faint)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }
          const w = (px) => ({ ...inp, width: px, padding: '6px 9px' })
          const Head = ({ k, label, sortKey }) => (
            <div onClick={() => sortKey && handleSort(sortKey)} style={{ padding: '0 8px 10px', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: sortCol === sortKey ? 'var(--accent)' : 'var(--text-faint)', textAlign: CRIGHT.has(k) ? 'right' : 'left', cursor: sortKey ? 'pointer' : 'default', userSelect: 'none', whiteSpace: 'nowrap' }}>{label}{sortCol === sortKey && <span> {sortDir === 'asc' ? '↑' : '↓'}</span>}</div>
          )
          return (
          <div style={{ overflowX: 'auto', maxWidth: '100%', margin: '4px -4px 0' }}>
            <div style={{ minWidth: 1420 }}>
              <div style={{ display: 'grid', gridTemplateColumns: CGRID, gap: 12, borderBottom: '1px solid var(--border-card)' }}>
                {CCOLS.map(([k, wd, label, sortKey]) => k === 'sel'
                  ? <div key={k} style={{ padding: '0 0 10px' }}>{mayEdit && <input type="checkbox" checked={allSelected} onChange={toggleAll} />}</div>
                  : <Head key={k} k={k} label={label} sortKey={sortKey} />)}
              </div>
              {filtered.map(c => {
                if (editId === c.id) {
                  return (
                    <div key={c.id} style={{ borderBottom: '1px solid var(--border-row)', background: 'var(--accent-tint)', borderRadius: 10, padding: '12px 10px', margin: '2px 0' }}>
                      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Контрагент</span><div style={{ width: 220 }}><CounterpartySearch counterparties={counterparties} value={editDraft.counterparty_id} onChange={id => setEditDraft(d => ({ ...d, counterparty_id: id }))} onCreateNew={createCounterparty} /></div></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>№ договора</span><input value={editDraft.contract_number || ''} onChange={e => setEditDraft(d => ({ ...d, contract_number: e.target.value }))} style={w(120)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Дата</span><input type="date" value={editDraft.contract_date || ''} onChange={e => setEditDraft(d => ({ ...d, contract_date: e.target.value }))} style={w(140)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>ИНН</span>{editDraft.counterparty_id ? <span style={{ ...w(120), color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center' }}>{(counterparties.find(cp => cp.id === editDraft.counterparty_id) || {}).inn || '—'}</span> : <input value={editDraft.inn || ''} onChange={e => setEditDraft(d => ({ ...d, inn: e.target.value }))} style={w(120)} />}</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Назв. маркет.</span><input value={editDraft.marketing_name || ''} onChange={e => setEditDraft(d => ({ ...d, marketing_name: e.target.value }))} style={w(180)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Формат</span><SelectWithOther value={editDraft.cooperation_format} options={COOPERATION_FORMATS} onChange={e => setEditDraft(d => ({ ...d, cooperation_format: e.target.value }))} style={w(170)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Окончание</span><div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>{(editDraft._end_date_mode || 'date') === 'date' ? <input type="date" value={editDraft.end_date_text || ''} onChange={e => setEditDraft(d => ({ ...d, end_date_text: e.target.value }))} style={w(140)} /> : <input type="text" placeholder="Текст" value={editDraft.end_date_text || ''} onChange={e => setEditDraft(d => ({ ...d, end_date_text: e.target.value }))} style={w(150)} />}<button type="button" onClick={() => setEditDraft(d => ({ ...d, _end_date_mode: (d._end_date_mode || 'date') === 'date' ? 'text' : 'date', end_date_text: '' }))} style={{ ...btnSm(false), padding: '4px 8px' }}>{(editDraft._end_date_mode || 'date') === 'date' ? 'Aa' : '📅'}</button></div></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Пролонгация</span><SelectWithOther value={editDraft.prolongation} options={PROLONGATION_OPTIONS} onChange={e => setEditDraft(d => ({ ...d, prolongation: e.target.value }))} style={w(160)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Дни</span><input type="number" min="0" value={editDraft.payment_term_days} onChange={e => setEditDraft(d => ({ ...d, payment_term_days: e.target.value }))} style={{ ...w(70), textAlign: 'right' }} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Условие</span><SelectWithLegacy value={editDraft.payment_term_condition} options={PAYMENT_TERM_CONDITIONS} onChange={e => setEditDraft(d => ({ ...d, payment_term_condition: e.target.value }))} style={w(170)} /></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Документ</span><div style={{ display: 'flex', gap: 4, alignItems: 'center' }}><input value={editDraft.document_link || ''} onChange={e => setEditDraft(d => ({ ...d, document_link: e.target.value }))} placeholder="Ссылка" style={{ ...w(180), fontSize: 12 }} />{c.attached_filename ? <><button onClick={() => handleDownload(c.id, c.attached_filename)} style={btnSm(false)} title={c.attached_filename}>📥</button><button onClick={() => handleDeleteDoc(c.id)} style={{ ...btnSm(false), color: 'var(--danger)' }}>✕</button></> : <button onClick={() => { setUploadTargetId(c.id); uploadRef.current?.click() }} style={btnSm(false)}>{uploadingId === c.id ? '…' : '📎'}</button>}</div></div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                        <button onClick={() => handleSave(c.id)} disabled={saving} style={btnSm(true)}>{saving ? '…' : '✓ Сохранить'}</button>
                        <button onClick={cancelEdit} disabled={saving} style={btnSm(false)}>Отмена</button>
                        {editError && <span style={{ color: 'var(--danger)', fontSize: 11.5, alignSelf: 'center' }}>{editError}</span>}
                      </div>
                    </div>
                  )
                }
                return (
                  <div key={c.id} style={{ display: 'grid', gridTemplateColumns: CGRID, gap: 12, alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-row)', borderRadius: 10 }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                    <div>{mayEdit && <input type="checkbox" checked={selectedIds.includes(c.id)} onChange={() => toggleOne(c.id)} />}</div>
                    <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)', padding: '0 8px' }}>{c.id}</div>
                    <div style={{ padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.counterparty_name || ''}><span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{c.counterparty_name || dash}</span>{!c.linked && <span title="Не привязан к реестру" style={{ marginLeft: 5, color: T.warning }}>⚠</span>}</div>
                    <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.contract_number || dash}</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', padding: '0 8px', whiteSpace: 'nowrap' }}>{fmtDate(c.contract_date)}</div>
                    <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', padding: '0 8px' }}>{c.inn || dash}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.marketing_name || ''}>{c.marketing_name || dash}</div>
                    <div style={{ padding: '0 8px', overflow: 'hidden' }}>{c.cooperation_format ? <span style={{ background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 8, padding: '3px 8px', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block', maxWidth: '100%' }} title={c.cooperation_format}>{c.cooperation_format}</span> : dash}</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', padding: '0 8px', whiteSpace: 'nowrap' }}>{fmtEndDate(c.end_date_text)}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.prolongation || ''}>{c.prolongation || dash}</div>
                    <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right', padding: '0 8px' }}>{c.payment_term_days != null ? c.payment_term_days : dash}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.payment_term_condition || ''}>{c.payment_term_condition || dash}</div>
                    <div style={{ display: 'inline-flex', gap: 2, justifyContent: 'flex-end' }}>
                      {c.document_link && <a href={/^https?:\/\//i.test(c.document_link) ? c.document_link : undefined} target="_blank" rel="noopener noreferrer" title="Ссылка на документ" style={icoBtn}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg></a>}
                      {c.attached_filename && <button onClick={() => handleDownload(c.id, c.attached_filename)} title="Скачать документ" style={icoBtn}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg></button>}
                      {mayEdit && <button onClick={() => openEdit(c)} title="Редактировать" style={icoBtn} onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-tint)'; e.currentTarget.style.color = 'var(--accent)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-faint)' }}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></button>}
                      {mayEdit && <button onClick={() => handleDelete(c)} title="Удалить" style={icoBtn} onMouseEnter={e => { e.currentTarget.style.background = 'var(--danger-tint)'; e.currentTarget.style.color = T.danger }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-faint)' }}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg></button>}
                    </div>
                  </div>
                )
              })}
              {!filtered.length && <div style={{ padding: 26, textAlign: 'center', color: 'var(--text-muted)' }}>Ничего не найдено</div>}
            </div>
          </div>
          )
        })()}
        </div>
      </div>
    </>
  )
}
