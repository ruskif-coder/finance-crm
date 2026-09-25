import { useState, useEffect } from 'react'
import Head from 'next/head'
import api, { auth } from '@/lib/http'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, IconBtn } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const CounterpartiesMobile = dynamic(() => import('@/components/mobile/CounterpartiesMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { T } from '@/lib/tokens'
import { grp0 as fmt } from '@/lib/salesFormat'
import SectionTabs from '@/components/SectionTabs'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fmtDate as fmtCalendarDate } from '@/lib/dates'
import { csvCell } from '@/lib/csv'


const fmtDate = (s) => fmtCalendarDate(s)
const DEFAULT_TERM_DAYS = 60

// тип контрагента (relation) → чип
const REL_META = {
  'заказчик': { label: 'Заказчик', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
  'поставщик': { label: 'Поставщик', bg: '#FBF0DE', fg: '#B26A0C' },
  'смешенный': { label: 'Смешанный', bg: '#F1EDFC', fg: T.mixed },
}
const relMeta = (r) => REL_META[r] || { label: 'не заполнен', bg: 'var(--bg-subtle)', fg: 'var(--text-faint)' }

// сетка таблицы (одна для шапки и строк)
const COLS = [
  ['sel', '26px', ''], ['id', '52px', 'ID', 'id'], ['name', 'minmax(230px,1.5fr)', 'Название', 'name'],
  ['inn', '110px', 'ИНН', 'inn'], ['contracts', '62px', 'Дог.'], ['term', '46px', 'Отс.', 'term_days'],
  ['relation', '112px', 'Статус', 'relation'], ['group', '132px', 'Группа', 'group'], ['vid', '40px', 'Вид'],
  ['op', '52px', 'Опе.', 'op_count'], ['receivable', '104px', 'Дебиторка', 'receivable'],
  ['payable', '104px', 'Кредиторка', 'payable'], ['income', '112px', 'Поступления', 'income_paid'],
  ['expense', '104px', 'Выплаты', 'expense_paid'], ['diff', '112px', 'Разница', 'diff'],
  ['date', '88px', 'Дата', 'last_op_date'], ['actions', '40px', ''],
]
const RIGHT = new Set(['term', 'op', 'receivable', 'payable', 'income', 'expense', 'diff'])

export default function Counterparties() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [perms, setPerms] = useState({})
  const [role, setRole] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState('действующий')
  const [relFilter, setRelFilter] = useState('')
  const [sortCol, setSortCol] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [pageSize, setPageSize] = useState(100)
  const [mobileLimit, setMobileLimit] = useState(50)

  const [showForm, setShowForm] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', inn: '', status: 'действующий' })
  const [newError, setNewError] = useState('')
  const [newSaving, setNewSaving] = useState(false)

  const [editId, setEditId] = useState(null)
  const [editDraft, setEditDraft] = useState({ name: '', inn: '', status: 'действующий', term_days: '', is_own_company: false })
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')

  const [selectedIds, setSelectedIds] = useState([])

  const isAdmin = role === 'admin'
  const mayEdit = isAdmin || can(perms, 'counterparties', 'edit')

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

  useRefreshOnReturn(() => load())
  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try {
      setPerms(JSON.parse(localStorage.getItem('permissions') || '{}'))
      setRole(localStorage.getItem('role') || '')
    } catch (e) {}
    load()
  }, [])

  // единый сейв для мобильной формы (create + edit)
  const mobileSave = async (f, id) => {
    const name = (f.name || '').trim()
    if (!name) { alert('Название обязательно'); return false }
    setSaving(true)
    try {
      let targetId = id
      if (!id) {
        const res = await api.post('/counterparties/', { name, vat_rate: 0 }, auth())
        targetId = res.data.id
      }
      await api.put(`/counterparties/${targetId}/registry`, {
        name, inn: (f.inn || '').trim() || null, status: f.status,
        term_days: f.term_days !== '' && f.term_days != null ? parseInt(f.term_days, 10) : null,
        is_own_company: !!f.is_own_company,
      }, auth())
      await load()
      return true
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка при сохранении'); return false }
    finally { setSaving(false) }
  }

  const handleCreate = async () => {
    const ok = await mobileSave(newForm, null)
    if (ok) { setShowForm(false); setNewForm({ name: '', inn: '', status: 'действующий' }); setNewError('') }
  }

  const openEdit = (c) => {
    setEditId(c.id)
    setEditDraft({ name: c.name, inn: c.inn || '', status: c.status, term_days: c.term_days != null ? String(c.term_days) : '', is_own_company: !!c.is_own_company })
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

  const handleSort = (col) => {
    if (!col) return
    setSortDir(d => sortCol === col ? (d === 'asc' ? 'desc' : 'asc') : 'asc')
    setSortCol(col)
  }

  const filtered = items
    .filter(c => {
      if (statusFilter && c.status !== statusFilter) return false
      if (relFilter && c.relation !== relFilter) return false
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

  const resetFilters = () => { setSearch(''); setStatusFilter(''); setRelFilter(''); setSortCol('name'); setSortDir('asc') }

  const exportCsv = () => {
    const head = ['ID', 'Название', 'ИНН', 'Договоров', 'Отсрочка', 'Тип', 'Группа', 'Вид', 'Операций', 'Дебиторка', 'Кредиторка', 'Поступления', 'Выплаты', 'Разница', 'Дата']
    const rows = filtered.map(c => [c.id, c.name, c.inn || '', c.contracts_count || 0, c.term_days_effective, relMeta(c.relation).label, c.group || '', c.status, c.op_count, c.receivable, c.payable, c.income_paid, c.expense_paid, c.diff, fmtDate(c.last_op_date)])
    // Формулы в ячейках — текстом (lib/csv): название вида «=HYPERLINK(…)» сработало бы в Excel.
    const csv = [head, ...rows].map(r => r.map(csvCell).join(';')).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'counterparties.csv'; a.click()
  }

  // ── МОБИЛЬНАЯ ВЕРСИЯ ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Контрагенты · Справочники | SIMB-AD ERP</title></Head>
        <Navbar active="directories" />
        <CounterpartiesMobile
          total={items.length} rows={filtered} loading={loading} canEdit={mayEdit} isAdmin={isAdmin}
          search={search} setSearch={setSearch} statusFilter={statusFilter} setStatusFilter={setStatusFilter}
          onSave={mobileSave} saving={saving} limit={mobileLimit} setLimit={setMobileLimit} />
      </div>
    )
  }

  const GRID = COLS.map(c => c[1]).join(' ')
  const allSelected = filtered.length > 0 && filtered.every(c => selectedIds.includes(c.id))
  const toggleAll = () => setSelectedIds(allSelected ? [] : filtered.map(c => c.id))
  const toggleOne = (id) => setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  const shown = filtered.slice(0, pageSize)

  const chipSel = { appearance: 'none', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '7px 26px 7px 12px', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: UI, outline: 'none', backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%278%27 height=%275%27%3E%3Cpath d=%27M0 0l4 5 4-5z%27 fill=%27%23A3ABBD%27/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center' }
  const HeadCell = ({ k, w, label, sortKey }) => (
    <div onClick={() => handleSort(sortKey)} style={{ padding: '0 8px 10px', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: sortCol === sortKey ? 'var(--accent)' : 'var(--text-faint)', textAlign: RIGHT.has(k) ? 'right' : 'left', cursor: sortKey ? 'pointer' : 'default', userSelect: 'none', whiteSpace: 'nowrap' }}>
      {label}{sortCol === sortKey && <span> {sortDir === 'asc' ? '↑' : '↓'}</span>}
    </div>
  )

  return (
    <>
      <Head><title>Контрагенты · Справочники | SIMB-AD ERP</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SectionTabs section="directory" />

        {error && <div style={{ background: 'var(--danger-tint)', color: T.danger, padding: '10px 14px', borderRadius: 12, marginBottom: 12, fontSize: 13 }}>{error}</div>}

        {/* Карточка реестра */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '18px 24px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* строка фильтров */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Контрагенты</h1>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${searchOpen || search ? 'var(--accent)' : 'var(--border-card)'}`, borderRadius: 10, padding: '0 10px', height: 34, width: searchOpen || search ? 260 : 150, transition: 'width 200ms ease' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'var(--text-faint)', strokeWidth: 1.8, strokeLinecap: 'round' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
              <input value={search} onFocus={() => setSearchOpen(true)} onBlur={() => setSearchOpen(false)} onChange={e => setSearch(e.target.value)} placeholder="Название, ИНН…" style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 13, fontFamily: UI, color: 'var(--text-primary)' }} />
            </div>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={chipSel}>
              <option value="">Все виды</option>
              <option value="действующий">Действующий</option>
              <option value="виртуальный">Виртуальный</option>
            </select>
            <select value={relFilter} onChange={e => setRelFilter(e.target.value)} style={chipSel}>
              <option value="">Все типы</option>
              <option value="заказчик">Заказчик</option>
              <option value="поставщик">Поставщик</option>
              <option value="смешенный">Смешанный</option>
            </select>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <IconBtn title="Сбросить фильтры" onClick={resetFilters}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
              <IconBtn title="Выгрузить в CSV" onClick={exportCsv}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg></IconBtn>
              {mayEdit && (
                <button onClick={() => setShowForm(s => !s)} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>{showForm ? 'Отмена' : '+ Контрагент'}</button>
              )}
            </span>
          </div>

          {/* строка-счётчик + легенда */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '2px 0 6px' }}>
            <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>показано {shown.length} из {items.length}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 12, fontSize: 11.5, color: 'var(--text-muted)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--income)' }} />действующий</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--text-faint)' }} />виртуальный</span>
            </span>
          </div>

          {/* форма нового контрагента */}
          {mayEdit && showForm && (
            <div style={{ border: '1px solid var(--border-card)', borderRadius: 14, padding: '14px 16px', margin: '4px 0 10px', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', background: 'var(--bg-subtle)' }}>
              <div><div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Название *</div><input autoFocus value={newForm.name} onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') handleCreate() }} placeholder="ООО Контрагент" style={{ border: '1px solid var(--border-card)', borderRadius: 10, padding: '8px 10px', fontSize: 13, width: 260, fontFamily: UI, outline: 'none' }} /></div>
              <div><div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>ИНН</div><input value={newForm.inn} onChange={e => setNewForm(f => ({ ...f, inn: e.target.value }))} placeholder="1234567890" style={{ border: '1px solid var(--border-card)', borderRadius: 10, padding: '8px 10px', fontSize: 13, width: 150, fontFamily: MONO, outline: 'none' }} /></div>
              <div><div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Вид</div><select value={newForm.status} onChange={e => setNewForm(f => ({ ...f, status: e.target.value }))} style={chipSel}><option value="действующий">Действующий</option><option value="виртуальный">Виртуальный</option></select></div>
              <button onClick={handleCreate} disabled={newSaving || saving} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>{newSaving || saving ? '…' : 'Создать'}</button>
              {newError && <span style={{ color: T.danger, fontSize: 12.5 }}>{newError}</span>}
            </div>
          )}

          {/* таблица */}
          {loading ? <div style={{ padding: 30, color: 'var(--text-muted)' }}>Загрузка…</div> : (
            <div style={{ overflowX: 'auto' }}>
              <div style={{ minWidth: 1560 }}>
                <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, borderBottom: '1px solid var(--border-card)' }}>
                  {COLS.map(([k, w, label, sortKey]) => k === 'sel'
                    ? <div key={k} style={{ padding: '0 0 10px' }}>{mayEdit && <input type="checkbox" checked={allSelected} onChange={toggleAll} />}</div>
                    : <HeadCell key={k} k={k} w={w} label={label} sortKey={sortKey} />)}
                </div>
                {shown.map(c => {
                  const rel = relMeta(c.relation)
                  const isEdit = editId === c.id
                  return (
                    <div key={c.id} onClick={() => !isEdit && router.push(`/directory/counterparties/${c.id}`)} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-row)', borderRadius: 10, cursor: isEdit ? 'default' : 'pointer', background: isEdit ? 'var(--accent-tint)' : 'transparent' }} onMouseEnter={e => { if (!isEdit) e.currentTarget.style.background = 'var(--bg-subtle)' }} onMouseLeave={e => { if (!isEdit) e.currentTarget.style.background = 'transparent' }}>
                      <div onClick={e => e.stopPropagation()} style={{ paddingLeft: 0 }}>{mayEdit && <input type="checkbox" checked={selectedIds.includes(c.id)} onChange={() => toggleOne(c.id)} />}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)', padding: '0 8px' }}>{c.id}</div>
                      <div style={{ padding: '0 8px', overflow: 'hidden' }}>
                        {isEdit
                          ? <input autoFocus value={editDraft.name} onClick={e => e.stopPropagation()} onChange={e => setEditDraft(d => ({ ...d, name: e.target.value }))} style={{ width: 220, border: '1px solid var(--border-card)', borderRadius: 8, padding: '5px 8px', fontSize: 13, fontFamily: UI }} />
                          : <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                              {/* Стрелка — карточка в НОВОЙ вкладке, как в реестре
                                  операций. Клик по самой строке открывает карточку в этой
                                  же, и обе дороги нужны: из реестра ходят и «посмотреть,
                                  вернуться», и «оставить открытым рядом».
                                  stopPropagation обязателен — иначе клик по ссылке заодно
                                  сработает как клик по строке. */}
                              <a href={`/directory/counterparties/${c.id}`} target="_blank" rel="noreferrer"
                                 onClick={e => e.stopPropagation()} title="Карточка юрлица — в новой вкладке"
                                 style={{ display: 'inline-flex', flex: '0 0 auto', color: 'var(--text-faint)' }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                  strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M7 17 17 7" /><path d="M9 7h8v8" />
                                </svg>
                              </a>
                              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                              {c.is_own_company && <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', background: 'var(--accent-tint)', borderRadius: 6, padding: '1px 5px', whiteSpace: 'nowrap' }}>НАША</span>}
                            </span>}
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', padding: '0 8px' }}>{isEdit ? <input value={editDraft.inn} onClick={e => e.stopPropagation()} onChange={e => setEditDraft(d => ({ ...d, inn: e.target.value }))} style={{ width: 96, border: '1px solid var(--border-card)', borderRadius: 8, padding: '5px 8px', fontSize: 12, fontFamily: MONO }} /> : (c.inn || <span style={{ color: 'var(--text-faint)' }}>—</span>)}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.contracts_count ? 'var(--text-primary)' : 'var(--text-faint)', textAlign: 'center' }}>{c.contracts_count || 0}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.term_days_is_default ? 'var(--text-faint)' : 'var(--text-primary)', textAlign: 'right', padding: '0 8px' }}>{isEdit ? <input value={editDraft.term_days} onClick={e => e.stopPropagation()} onChange={e => setEditDraft(d => ({ ...d, term_days: e.target.value.replace(/\D/g, '') }))} placeholder={String(DEFAULT_TERM_DAYS)} style={{ width: 42, border: '1px solid var(--border-card)', borderRadius: 8, padding: '5px 6px', fontSize: 12, fontFamily: MONO, textAlign: 'right' }} /> : c.term_days_effective}</div>
                      <div style={{ padding: '0 8px' }}>{isEdit
                        ? <select value={editDraft.status} onClick={e => e.stopPropagation()} onChange={e => setEditDraft(d => ({ ...d, status: e.target.value }))} style={{ border: '1px solid var(--border-card)', borderRadius: 8, padding: '4px 6px', fontSize: 12 }}><option value="действующий">Действ.</option><option value="виртуальный">Виртуал.</option></select>
                        : <span style={{ background: rel.bg, color: rel.fg, borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{rel.label}</span>}</div>
                      <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.04em', color: 'var(--text-muted)', padding: '0 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.group || ''}>{c.group_is_override && <span style={{ color: T.warning, marginRight: 3 }}>✎</span>}{c.group || <span style={{ color: 'var(--text-faint)' }}>—</span>}</div>
                      <div style={{ textAlign: 'center' }}><span title={c.status} style={{ width: 8, height: 8, borderRadius: 2, display: 'inline-block', background: c.status === 'действующий' ? 'var(--income)' : 'var(--text-faint)' }} /></div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right', padding: '0 8px' }}>{c.op_count || 0}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.receivable > 0 ? 'var(--accent)' : 'var(--text-faint)', textAlign: 'right', padding: '0 8px' }}>{c.receivable > 0 ? fmt(c.receivable) : '—'}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.payable > 0 ? T.warning : 'var(--text-faint)', textAlign: 'right', padding: '0 8px' }}>{c.payable > 0 ? fmt(c.payable) : '—'}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.income_paid > 0 ? 'var(--income)' : 'var(--text-faint)', textAlign: 'right', padding: '0 8px' }}>{c.income_paid > 0 ? fmt(c.income_paid) : '—'}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, color: c.expense_paid > 0 ? 'var(--text-secondary)' : 'var(--text-faint)', textAlign: 'right', padding: '0 8px' }}>{c.expense_paid > 0 ? fmt(c.expense_paid) : '—'}</div>
                      <div style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: c.diff > 0 ? 'var(--income)' : c.diff < 0 ? T.danger : 'var(--text-faint)', textAlign: 'right', padding: '0 8px' }}>{c.diff ? (c.diff > 0 ? '+' : '−') + fmt(Math.abs(c.diff)) : '—'}</div>
                      <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', padding: '0 8px' }}>{fmtDate(c.last_op_date)}</div>
                      <div onClick={e => e.stopPropagation()} style={{ textAlign: 'center' }}>
                        {mayEdit && (isEdit
                          ? <span style={{ display: 'inline-flex', gap: 4 }}><button onClick={() => handleSave(c.id)} disabled={saving} style={{ width: 26, height: 26, borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer' }}>✓</button><button onClick={cancelEdit} style={{ width: 26, height: 26, borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer' }}>✕</button></span>
                          : <button onClick={() => openEdit(c)} title="Редактировать" style={{ width: 26, height: 26, borderRadius: 8, border: 'none', background: 'transparent', color: 'var(--text-faint)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-tint)'; e.currentTarget.style.color = 'var(--accent)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-faint)' }}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></button>)}
                      </div>
                    </div>
                  )
                })}
                {!shown.length && <div style={{ padding: 26, textAlign: 'center', color: 'var(--text-muted)' }}>Ничего не найдено</div>}
                {editError && <div style={{ color: T.danger, fontSize: 12.5, padding: '8px' }}>{editError}</div>}
              </div>
            </div>
          )}

          {/* подвал: показать ещё + размер страницы */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 12 }}>
            {filtered.length > pageSize && <button onClick={() => setPageSize(p => p + 100)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '7px 14px', fontSize: 13, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>Показать ещё</button>}
            <div style={{ marginLeft: 'auto', display: 'inline-flex', gap: 3, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
              {[50, 100, 300, 500].map(n => <button key={n} onClick={() => setPageSize(n)} style={{ border: 'none', borderRadius: 8, padding: '5px 11px', fontFamily: MONO, fontSize: 12, fontWeight: pageSize === n ? 700 : 600, background: pageSize === n ? 'var(--accent-tint)' : 'transparent', color: pageSize === n ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer' }}>{n}</button>)}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
