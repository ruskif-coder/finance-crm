import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Link from 'next/link'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

const api = (token) => axios.create({
  baseURL: '/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => {
  if (!n && n !== 0) return '—'
  return new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽'
}
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'
const fmtK = (v) => {
  if (!v) return '0'
  if (v >= 1_000_000) return `${+(v / 1_000_000).toFixed(1)}М`
  if (v >= 1_000)     return `${+(v / 1_000).toFixed(0)}К`
  return String(Math.round(v))
}
const MONTHS_SHORT = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
const fmtMonth = (p) => {
  if (!p) return ''
  const [y, m] = p.split('-')
  return `${MONTHS_SHORT[parseInt(m, 10) - 1]} ${y.slice(2)}`
}
function normalizeUrl(u) {
  if (!u) return null
  return /^https?:\/\//i.test(u) ? u : 'https://' + u
}

// ── Строка реквизита ─────────────────────────────────────────────────────────
function ReqRow({ label, value, link }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
      padding: '7px 0', borderBottom: '1px solid var(--border-inner)', gap: 12, minHeight: 30,
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0, paddingTop: 1 }}>
        {label}
      </span>
      {!value
        ? <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>—</span>
        : link
          ? <a href={normalizeUrl(value)} target="_blank" rel="noopener noreferrer"
               style={{ fontSize: 13, textAlign: 'right', wordBreak: 'break-all',
                        color: 'var(--accent)', textDecoration: 'none' }}>{value}</a>
          : <span style={{ fontSize: 13, color: 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-all' }}>
              {value}
            </span>
      }
    </div>
  )
}

// ── Поле редактирования ──────────────────────────────────────────────────────
function EditInput({ label, value, onChange, placeholder, multiline }) {
  const inputStyle = {
    width: '100%', padding: '6px 10px', fontSize: 13,
    border: '1px solid var(--border-card)', borderRadius: 8,
    background: 'var(--bg-subtle)', color: 'var(--text-primary)',
    marginTop: 3, outline: 'none', resize: multiline ? 'vertical' : 'none',
    fontFamily: 'inherit',
  }
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2, fontWeight: 500 }}>{label}</div>
      {multiline
        ? <textarea rows={2} style={inputStyle} value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
        : <input style={inputStyle} value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      }
    </div>
  )
}

// ── Кнопки ───────────────────────────────────────────────────────────────────
const BTN = (extra = {}) => ({
  padding: '7px 16px', borderRadius: 10, fontSize: 13, cursor: 'pointer', fontWeight: 500,
  border: '1px solid var(--border-card)', background: 'var(--bg-subtle)', color: 'var(--text-secondary)',
  display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap', ...extra,
})
const BTN_PRIMARY = BTN({ background: 'var(--accent)', color: '#fff', borderColor: 'var(--accent)' })
const BTN_DANGER  = BTN({ background: 'var(--dot-overdue)', color: '#fff', borderColor: 'var(--dot-overdue)' })

// ── Секция-карточка ──────────────────────────────────────────────────────────
function Card({ title, action, children }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-card)',
      borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)', overflow: 'hidden',
    }}>
      <div style={{
        padding: '13px 18px', borderBottom: '1px solid var(--border-card)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
                       textTransform: 'uppercase', letterSpacing: '.06em' }}>
          {title}
        </span>
        {action}
      </div>
      {children}
    </div>
  )
}

// ── Бейдж ────────────────────────────────────────────────────────────────────
function Badge({ label, bg, color, href }) {
  const s = {
    display: 'inline-flex', alignItems: 'center', padding: '3px 10px',
    borderRadius: 8, fontSize: 12, fontWeight: 500, background: bg, color,
    textDecoration: 'none', whiteSpace: 'nowrap',
  }
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" style={s}>{label}</a>
              : <span style={s}>{label}</span>
}

// ── Select-фильтр в операциях ─────────────────────────────────────────────────
function FilterSelect({ value, onChange, options, style }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{
      fontSize: 12, padding: '5px 9px', borderRadius: 8, outline: 'none',
      border: '1px solid var(--border-card)', background: 'var(--bg-subtle)',
      color: 'var(--text-secondary)', cursor: 'pointer', ...style,
    }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

// ────────────────────────────────────────────────────────────────────────────
export default function CounterpartyCard() {
  const router = useRouter()
  const { id } = router.query

  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Операции
  const [ops, setOps] = useState([])
  const [opsTotal, setOpsTotal] = useState(0)
  const [opsPage, setOpsPage] = useState(0)
  const [opsLoading, setOpsLoading] = useState(false)
  const [opsStatus, setOpsStatus] = useState('')
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const OPS_LIMIT = 50

  // Редактирование
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')

  // Аналитика
  const [analytics, setAnalytics] = useState(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)

  // Копирование
  const [copied, setCopied] = useState(false)

  // Права
  const [canEdit, setCanEdit] = useState(false)
  const [canViewOps, setCanViewOps] = useState(false)

  useEffect(() => {
    const isAdmin = localStorage.getItem('is_admin') === '1'
      || localStorage.getItem('role') === 'admin'
    if (isAdmin) { setCanEdit(true); setCanViewOps(true); return }
    try {
      const perms = JSON.parse(localStorage.getItem('permissions') || '{}')
      setCanEdit(!!(perms['counterparties']?.edit))
      setCanViewOps(!!(perms['counterparties']?.view_operations) || !!(perms['operations']?.view))
    } catch {}
  }, [])

  const loadCard = useCallback(async () => {
    if (!id) return
    const token = localStorage.getItem('token')
    setLoading(true); setError('')
    try {
      const r = await api(token).get(`/counterparties/${id}/card`)
      setCard(r.data)
      const d = r.data
      setEditData({
        kpp: d.kpp || '', ogrn: d.ogrn || '', okpo: d.okpo || '',
        address: d.address || '', address_fact: d.address_fact || '',
        phone: d.phone || '', email: d.email || '',
        website: d.website || '', edo_id: d.edo_id || '',
        director_name: d.director_name || '', note: d.note || '',
        bank_accounts: d.bank_accounts.length
          ? d.bank_accounts
          : [{ bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }],
      })
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка загрузки')
    } finally { setLoading(false) }
  }, [id])

  // Все параметры — явно, без зависимости от замыкания
  const loadOps = useCallback(async (page, status, col, dir) => {
    if (!id) return
    const token = localStorage.getItem('token')
    setOpsLoading(true)
    try {
      const params = new URLSearchParams({
        counterparty_id: id,
        skip: (page ?? 0) * OPS_LIMIT,
        limit: OPS_LIMIT,
        sort_col: col ?? 'date',
        sort_dir: dir ?? 'desc',
      })
      if (status) params.append('status', status)
      const r = await api(token).get(`/counterparties/${id}/operations?${params}`)
      setOps(r.data.items || [])
      setOpsTotal(r.data.total || 0)
    } catch {}
    finally { setOpsLoading(false) }
  }, [id])

  const loadAnalytics = useCallback(async () => {
    if (!id) return
    const token = localStorage.getItem('token')
    setAnalyticsLoading(true)
    try {
      const r = await api(token).get(`/counterparties/${id}/analytics`)
      setAnalytics(r.data)
    } catch {}
    finally { setAnalyticsLoading(false) }
  }, [id])

  useEffect(() => { loadCard() }, [loadCard])
  useEffect(() => { if (id) loadOps(0, '', 'date', 'desc') }, [id])
  useEffect(() => { loadAnalytics() }, [loadAnalytics])

  // Обработчики фильтров/сортировки — каждый передаёт полный набор параметров
  function handleStatus(val) {
    setOpsStatus(val); setOpsPage(0)
    loadOps(0, val, sortCol, sortDir)
  }
  function handleSortCol(val) {
    setSortCol(val); setOpsPage(0)
    loadOps(0, opsStatus, val, sortDir)
  }
  function handleSortDir(val) {
    setSortDir(val); setOpsPage(0)
    loadOps(0, opsStatus, sortCol, val)
  }
  function handlePage(p) {
    setOpsPage(p)
    loadOps(p, opsStatus, sortCol, sortDir)
  }

  async function handleSave() {
    const token = localStorage.getItem('token')
    setSaving(true); setSaveErr('')
    try {
      await api(token).put(`/counterparties/${id}/requisites`, editData)
      await loadCard(); setEditMode(false)
    } catch (e) {
      const d = e.response?.data?.detail
      setSaveErr(typeof d === 'string' ? d : 'Ошибка сохранения')
    } finally { setSaving(false) }
  }

  function updateEdit(key, val) { setEditData(prev => ({ ...prev, [key]: val })) }
  function updateBank(idx, key, val) {
    setEditData(prev => {
      const ba = [...prev.bank_accounts]
      ba[idx] = { ...ba[idx], [key]: val }
      return { ...prev, bank_accounts: ba }
    })
  }
  function addBank() {
    setEditData(prev => ({ ...prev, bank_accounts: [...prev.bank_accounts, { bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }] }))
  }
  function removeBank(idx) {
    setEditData(prev => ({ ...prev, bank_accounts: prev.bank_accounts.filter((_, i) => i !== idx) }))
  }

  // Автозаполнение банковских реквизитов по БИК через справочник ЦБ РФ
  const [bicLoading, setBicLoading] = useState({})
  const [bicError, setBicError] = useState({})
  async function lookupBic(idx) {
    const token = localStorage.getItem('token')
    const bik = editData.bank_accounts[idx]?.bik?.trim()
    if (!bik || bik.length !== 9) {
      setBicError(prev => ({ ...prev, [idx]: 'Введите 9-значный БИК' }))
      return
    }
    setBicLoading(prev => ({ ...prev, [idx]: true }))
    setBicError(prev => ({ ...prev, [idx]: '' }))
    try {
      const res = await api(token).get(`/counterparties/bic/${bik}`)
      setEditData(prev => {
        const ba = [...prev.bank_accounts]
        ba[idx] = {
          ...ba[idx],
          bank_name: res.data.bank_name || ba[idx].bank_name,
          bank_city: res.data.bank_city || ba[idx].bank_city,
          ks:        res.data.ks        || ba[idx].ks,
        }
        return { ...prev, bank_accounts: ba }
      })
    } catch (e) {
      setBicError(prev => ({ ...prev, [idx]: e.response?.data?.detail || 'Не найден' }))
    } finally {
      setBicLoading(prev => ({ ...prev, [idx]: false }))
    }
  }

  function copyRequisites() {
    if (!card) return
    const lines = [card.name]
    if (card.inn || card.kpp) lines.push(`ИНН: ${card.inn || ''}  КПП: ${card.kpp || ''}`)
    if (card.ogrn)            lines.push(`ОГРН: ${card.ogrn}`)
    if (card.okpo)            lines.push(`ОКПО: ${card.okpo}`)
    if (card.address)         lines.push(`Юр. адрес: ${card.address}`)
    if (card.address_fact)    lines.push(`Факт. адрес: ${card.address_fact}`)
    if (card.phone)           lines.push(`Тел.: ${card.phone}`)
    if (card.email)           lines.push(`Email: ${card.email}`)
    if (card.website)         lines.push(`Сайт: ${card.website}`)
    if (card.director_name)   lines.push(`Ген. директор: ${card.director_name}`)
    if (card.edo_id)          lines.push(`ЭДО: ${card.edo_id}`)
    card.bank_accounts.forEach(b => {
      if (b.bank_name || b.rs) {
        lines.push('')
        if (b.bank_name) lines.push(b.bank_name)
        if (b.rs)  lines.push(`Р/С: ${b.rs}`)
        if (b.ks)  lines.push(`К/С: ${b.ks}`)
        if (b.bik) lines.push(`БИК: ${b.bik}`)
      }
    })
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    })
  }

  // ─────────────────────────────────────────────────────────────────────────
  if (loading) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar />
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>Загрузка…</div>
    </div>
  )
  if (error) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar />
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--dot-overdue)', fontSize: 14 }}>{error}</div>
    </div>
  )
  if (!card) return null

  const stats = card.stats
  const hasIncome  = stats.income_paid > 0 || stats.receivable > 0
  const hasExpense = stats.expense_paid > 0 || stats.payable > 0
  const relation   = hasIncome && hasExpense ? 'Смешанный' : hasIncome ? 'Заказчик' : hasExpense ? 'Поставщик' : null
  const isActive   = card.status === 'действующий'

  const OP_STATUS_DOT = {
    'ОПЛАЧЕНО':          'var(--income)',
    'ПЛАН ПОСТУПЛЕНИЙ':  'var(--accent)',
    'ПЛАН ОПЛАТ':        'var(--dot-current-dz)',
  }

  const RECEIVABLE_META = {
    overdue: { label: 'Просрочка', color: 'var(--dot-overdue)' },
    current: { label: 'Текущая',   color: 'var(--dot-current-dz)' },
  }

  const SORT_COL_OPTIONS = [
    { value: 'date',    label: 'Дата' },
    { value: 'period',  label: 'Период' },
    { value: 'article', label: 'Статья' },
    { value: 'income',  label: 'Приход' },
    { value: 'expense', label: 'Расход' },
    { value: 'status',  label: 'Статус' },
  ]
  const SORT_DIR_OPTIONS = [
    { value: 'desc', label: '↓ По убыванию' },
    { value: 'asc',  label: '↑ По возрастанию' },
  ]
  const STATUS_OPTIONS = [
    { value: '',                   label: 'Все статусы' },
    { value: 'ОПЛАЧЕНО',           label: 'ОПЛАЧЕНО' },
    { value: 'ПЛАН ПОСТУПЛЕНИЙ',   label: 'ПЛАН ПОСТУПЛЕНИЙ' },
    { value: 'ПЛАН ОПЛАТ',         label: 'ПЛАН ОПЛАТ' },
  ]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Head><title>Контрагент | Финансовый учёт</title></Head>

      {/* ── Стандартная шапка (без children — чтобы не ломать выравнивание) ── */}
      <Navbar active="directories" />

      {/* ── Subheader: хлебные крошки + бейджи + кнопки ─────────────────── */}
      <div style={{
        background: 'var(--bg-header)', borderBottom: '1px solid var(--border-card)',
        position: 'sticky', top: 66, zIndex: 90,
      }}>
        <div style={{
          maxWidth: 1920, margin: '0 auto', padding: '0 24px', height: 46,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}>
          {/* Левая часть — хлебные крошки + бейджи */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, overflow: 'hidden' }}>
            <Link href="/directories?tab=counterparties"
                  style={{ fontSize: 13, color: 'var(--text-muted)', textDecoration: 'none',
                           display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
              ← Контрагенты
            </Link>
            <span style={{ color: 'var(--border-card)', flexShrink: 0 }}>›</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
                           overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {card.name}
            </span>
            <Badge
              label={card.status}
              bg={isActive ? '#E8F5EE' : 'var(--bg-subtle)'}
              color={isActive ? 'var(--income)' : 'var(--text-muted)'}
            />
            {relation && <Badge label={relation} bg="var(--accent-tint)" color="var(--accent)" />}
            {card.website && (
              <Badge
                label={`🌐 ${card.website.replace(/^https?:\/\//i, '').replace(/\/$/, '')}`}
                bg="var(--bg-subtle)" color="var(--accent)"
                href={normalizeUrl(card.website)}
              />
            )}
          </div>

          {/* Правая часть — пусто (кнопки управления перенесены в блок Реквизиты) */}
          <div />
        </div>
      </div>

      {saveErr && (
        <div style={{ background: 'var(--danger-tint)', color: 'var(--dot-overdue)',
                      padding: '8px 24px', fontSize: 13 }}>{saveErr}</div>
      )}

      {/* ── Контент — max 1920px ──────────────────────────────────────────── */}
      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '20px 24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'clamp(20vw, 25vw, 480px) minmax(0,1fr)', gap: 16, alignItems: 'start' }}>

          {/* ── Левая колонка: Реквизиты ────────────────────────────────── */}
          <Card
            title="Реквизиты"
            action={
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {!editMode ? <>
                  <button onClick={copyRequisites} style={BTN({
                    padding: '4px 10px', fontSize: 11,
                    color: copied ? 'var(--income)' : 'var(--text-muted)',
                    borderColor: copied ? 'var(--income)' : 'var(--border-card)',
                  })}>
                    {copied ? '✓ Скопировано' : '📋 Копировать'}
                  </button>
                  {canEdit && (
                    <button
                      onClick={() => { setEditMode(true); setSaveErr('') }}
                      style={BTN({ padding: '4px 8px', fontSize: 14, lineHeight: 1 })}
                      title="Редактировать реквизиты"
                    >
                      ✏️
                    </button>
                  )}
                </> : <>
                  <button
                    onClick={() => { setEditMode(false); setSaveErr('') }}
                    title="Отмена"
                    style={{
                      padding: '4px 7px', borderRadius: 8, cursor: 'pointer', fontSize: 15,
                      border: '1px solid #f5c842', background: 'transparent', color: '#f5c842',
                      display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                    }}
                  >↩</button>
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    title="Сохранить"
                    style={{
                      padding: '4px 7px', borderRadius: 8, cursor: 'pointer', fontSize: 15,
                      border: '1px solid var(--income)', background: 'transparent', color: 'var(--income)',
                      display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                      opacity: saving ? 0.5 : 1,
                    }}
                  >{saving ? '…' : '✓'}</button>
                </>}
              </div>
            }
          >
            <div style={{ padding: '10px 16px' }}>
              {!editMode ? (
                <>
                  <ReqRow label="ИНН"           value={card.inn} />
                  <ReqRow label="КПП"           value={card.kpp} />
                  <ReqRow label="ОГРН"          value={card.ogrn} />
                  <ReqRow label="ОКПО"          value={card.okpo} />
                  <ReqRow label="Юр. адрес"     value={card.address} />
                  <ReqRow label="Факт. адрес"   value={card.address_fact} />
                  <ReqRow label="Телефон"       value={card.phone} />
                  <ReqRow label="Email"         value={card.email} link />
                  <ReqRow label="Сайт"          value={card.website} link />
                  <ReqRow label="Ген. директор" value={card.director_name} />
                  <ReqRow label="ЭДО"           value={card.edo_id} />
                  <ReqRow label="Примечание"    value={card.note} />

                  {card.bank_accounts.length > 0
                    ? card.bank_accounts.map((b, i) => (
                        <div key={i} style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', marginBottom: 6,
                                        textTransform: 'uppercase', letterSpacing: '.04em' }}>
                            {b.bank_name || `Счёт ${i + 1}`}
                          </div>
                          {b.bank_city && <ReqRow label="Город банка" value={b.bank_city} />}
                          <ReqRow label="Р/С" value={b.rs} />
                          <ReqRow label="К/С" value={b.ks} />
                          <ReqRow label="БИК" value={b.bik} />
                        </div>
                      ))
                    : (
                        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-faint)', marginBottom: 6,
                                        textTransform: 'uppercase', letterSpacing: '.04em' }}>
                            Банковский счёт
                          </div>
                          <ReqRow label="Р/С" value={null} />
                          <ReqRow label="К/С" value={null} />
                          <ReqRow label="БИК" value={null} />
                        </div>
                      )
                  }
                </>
              ) : (
                <>
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2, fontWeight: 500 }}>ИНН</div>
                    <div style={{ fontSize: 13, padding: '6px 10px', borderRadius: 8,
                                  background: 'var(--border-inner)', color: 'var(--text-muted)',
                                  border: '1px solid var(--border-card)' }}>
                      {card.inn || '—'}
                      <span style={{ fontSize: 11, marginLeft: 6, color: 'var(--text-faint)' }}>(изменяется в реестре)</span>
                    </div>
                  </div>
                  <EditInput label="КПП"           value={editData.kpp}           onChange={v => updateEdit('kpp', v)} />
                  <EditInput label="ОГРН"          value={editData.ogrn}          onChange={v => updateEdit('ogrn', v)} />
                  <EditInput label="ОКПО"          value={editData.okpo}          onChange={v => updateEdit('okpo', v)} />
                  <EditInput label="Юр. адрес"     value={editData.address}       onChange={v => updateEdit('address', v)} multiline />
                  <EditInput label="Факт. адрес"   value={editData.address_fact}  onChange={v => updateEdit('address_fact', v)} multiline />
                  <EditInput label="Телефон"       value={editData.phone}         onChange={v => updateEdit('phone', v)} />
                  <EditInput label="Email"         value={editData.email}         onChange={v => updateEdit('email', v)} />
                  <EditInput label="Сайт"          value={editData.website}       onChange={v => updateEdit('website', v)} placeholder="https://example.ru" />
                  <EditInput label="Ген. директор" value={editData.director_name} onChange={v => updateEdit('director_name', v)} />
                  <EditInput label="ЭДО (ID)"      value={editData.edo_id}        onChange={v => updateEdit('edo_id', v)} />
                  <EditInput label="Примечание"    value={editData.note}          onChange={v => updateEdit('note', v)} multiline />

                  <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                                  textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 10 }}>
                      Банковские счета
                    </div>
                    {editData.bank_accounts.map((b, i) => (
                      <div key={i} style={{ background: 'var(--bg-subtle)', borderRadius: 10, padding: 10,
                                            marginBottom: 8, border: '1px solid var(--border-card)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>Счёт {i + 1}</span>
                          <button onClick={() => removeBank(i)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer',
                                           color: 'var(--dot-overdue)', fontSize: 13, padding: 0 }}>✕</button>
                        </div>
                        {/* БИК с автозаполнением из справочника ЦБ РФ */}
                        <div style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2, fontWeight: 500 }}>БИК</div>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <input
                              style={{ flex: 1, padding: '6px 10px', fontSize: 13,
                                       border: '1px solid var(--border-card)', borderRadius: 8,
                                       background: 'var(--bg-subtle)', color: 'var(--text-primary)', outline: 'none' }}
                              value={b.bik || ''}
                              onChange={e => updateBank(i, 'bik', e.target.value)}
                              placeholder="044525974"
                              maxLength={9}
                            />
                            <button
                              onClick={() => lookupBic(i)}
                              disabled={bicLoading[i]}
                              style={{ padding: '6px 10px', fontSize: 12, background: 'var(--accent)',
                                       color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer',
                                       whiteSpace: 'nowrap', opacity: bicLoading[i] ? 0.6 : 1 }}
                            >
                              {bicLoading[i] ? '...' : 'Найти'}
                            </button>
                          </div>
                          {bicError[i] && <div style={{ fontSize: 11, color: 'var(--dot-overdue)', marginTop: 3 }}>{bicError[i]}</div>}
                        </div>
                        <EditInput label="Банк"       value={b.bank_name} onChange={v => updateBank(i, 'bank_name', v)} placeholder="Заполняется автоматически по БИК" />
                        <EditInput label="Город банка" value={b.bank_city} onChange={v => updateBank(i, 'bank_city', v)} placeholder="г. Москва" />
                        <EditInput label="Р/С"  value={b.rs}  onChange={v => updateBank(i, 'rs', v)}  placeholder="40702810000000000000" />
                        <EditInput label="К/С"  value={b.ks}  onChange={v => updateBank(i, 'ks', v)}  placeholder="Заполняется автоматически по БИК" />
                      </div>
                    ))}
                    <button style={BTN({ fontSize: 12, padding: '5px 12px' })} onClick={addBank}>
                      + Добавить счёт
                    </button>
                  </div>
                </>
              )}
            </div>
          </Card>

          {/* ── Правая колонка ──────────────────────────────────────────── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Взаиморасчёты */}
            <Card title="Взаиморасчёты">
              <div style={{ padding: '16px 18px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 0 }}>
                {(() => {
                  const maxVal = Math.max(stats.receivable || 0, stats.payable || 0, Math.abs(stats.saldo || 0), 1)
                  return [
                    { label: 'Операций всего', value: stats.op_count, plain: true },
                    { label: 'Дебиторка',  value: fmt(stats.receivable), color: 'var(--accent)',          bar: stats.receivable || 0, barColor: 'var(--accent)' },
                    { label: 'Кредиторка', value: fmt(stats.payable),    color: 'var(--dot-current-dz)',  bar: stats.payable || 0,   barColor: 'var(--dot-current-dz)' },
                    {
                      label: 'Сальдо', value: fmt(stats.saldo),
                      color: (stats.saldo || 0) >= 0 ? 'var(--income)' : 'var(--dot-overdue)',
                      bar: Math.abs(stats.saldo || 0),
                      barColor: (stats.saldo || 0) >= 0 ? 'var(--income)' : 'var(--dot-overdue)',
                    },
                  ].map((s, idx) => (
                    <div key={s.label} style={{
                      textAlign: 'center', padding: '10px 8px',
                      borderRight: idx < 3 ? '1px solid var(--border-inner)' : 'none',
                    }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, lineHeight: 1.4 }}>{s.label}</div>
                      <div style={{
                        fontSize: s.plain ? 28 : 16, fontWeight: 600,
                        color: s.plain ? 'var(--text-primary)' : s.color,
                        letterSpacing: s.plain ? '-1px' : 0,
                      }}>{s.value}</div>
                      {!s.plain && (
                        <div style={{ height: 4, borderRadius: 2, background: 'var(--border-card)', marginTop: 8, overflow: 'hidden' }}>
                          <div style={{ height: '100%', borderRadius: 2, background: s.barColor,
                                        width: `${Math.round((s.bar / maxVal) * 100)}%`, transition: 'width .3s' }} />
                        </div>
                      )}
                    </div>
                  ))
                })()}
              </div>
            </Card>

            {/* Аналитика */}
            <Card title="Аналитика">
              {analyticsLoading ? (
                <div style={{ padding: '20px 18px', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
              ) : !analytics ? null : (() => {
                const STATUS_COLOR = {
                  'ОПЛАЧЕНО':         'var(--income)',
                  'ПЛАН ПОСТУПЛЕНИЙ': 'var(--accent)',
                  'ПЛАН ОПЛАТ':       'var(--dot-current-dz)',
                }
                const maxArticle = analytics.top_articles[0]
                  ? analytics.top_articles[0].income + analytics.top_articles[0].expense : 1

                return (
                  <div style={{ padding: '14px 18px' }}>

                    {/* График оборота */}
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                                  textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>
                      Оборот по месяцам (весь период)
                    </div>
                    {analytics.monthly.length === 0 ? (
                      <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 16 }}>Нет данных</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={130}>
                        <BarChart data={analytics.monthly} barCategoryGap="30%" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-inner)" vertical={false} />
                          <XAxis dataKey="period" tickFormatter={fmtMonth} tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                                 axisLine={false} tickLine={false} />
                          <YAxis tickFormatter={fmtK} tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                                 axisLine={false} tickLine={false} width={36} />
                          <Tooltip
                            formatter={(v, name) => [fmt(v), name === 'income' ? 'Приход' : 'Расход']}
                            labelFormatter={fmtMonth}
                            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid var(--border-card)',
                                            background: 'var(--bg-card)', color: 'var(--text-primary)' }}
                          />
                          <Bar dataKey="income"  fill="var(--income)"      radius={[3,3,0,0]} maxBarSize={24} />
                          <Bar dataKey="expense" fill="var(--dot-overdue)" radius={[3,3,0,0]} maxBarSize={24} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}

                    {/* Средний чек */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 16, marginBottom: 16 }}>
                      {[
                        { label: 'Ср. приход', value: analytics.avg_income,  color: 'var(--income)' },
                        { label: 'Ср. расход',  value: analytics.avg_expense, color: 'var(--dot-overdue)' },
                      ].map(s => (
                        <div key={s.label} style={{ background: 'var(--bg-subtle)', borderRadius: 10,
                                                    padding: '10px 12px', border: '1px solid var(--border-card)' }}>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{s.label}</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: s.value ? s.color : 'var(--text-faint)' }}>
                            {s.value ? fmt(s.value) : '—'}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Топ статей */}
                    {analytics.top_articles.length > 0 && (
                      <>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                                      textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>
                          Топ статей
                        </div>
                        {analytics.top_articles.map((a, i) => {
                          const total = a.income + a.expense
                          const pct = Math.round((total / maxArticle) * 100)
                          return (
                            <div key={i} style={{ marginBottom: 10 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between',
                                            alignItems: 'baseline', marginBottom: 4, gap: 8 }}>
                                <span style={{ fontSize: 12, color: 'var(--text-primary)',
                                               overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {a.article}
                                </span>
                                <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                                  {fmt(total)}
                                </span>
                              </div>
                              <div style={{ height: 4, borderRadius: 2, background: 'var(--border-card)', overflow: 'hidden' }}>
                                <div style={{ height: '100%', borderRadius: 2,
                                              width: `${pct}%`, transition: 'width .4s',
                                              background: a.income >= a.expense ? 'var(--income)' : 'var(--dot-overdue)' }} />
                              </div>
                            </div>
                          )
                        })}
                      </>
                    )}

                    {/* Разбивка по статусам */}
                    {analytics.by_status.length > 0 && (
                      <>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                                      textTransform: 'uppercase', letterSpacing: '.05em',
                                      marginTop: 16, marginBottom: 10 }}>
                          По статусам
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {analytics.by_status.map(s => (
                            <div key={s.status} style={{ display: 'flex', alignItems: 'center',
                                                         justifyContent: 'space-between', gap: 8 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                                <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                                               background: STATUS_COLOR[s.status] || 'var(--text-faint)',
                                               display: 'inline-block' }} />
                                <span style={{ fontSize: 11, color: 'var(--text-secondary)',
                                               overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {s.status}
                                </span>
                              </div>
                              <div style={{ display: 'flex', gap: 10, flexShrink: 0, alignItems: 'center' }}>
                                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.cnt} оп.</span>
                                {(s.income > 0 || s.expense > 0) && (
                                  <span style={{ fontSize: 11, fontWeight: 500,
                                                 color: s.income > 0 ? 'var(--income)' : 'var(--dot-overdue)' }}>
                                    {fmt(s.income > 0 ? s.income : s.expense)}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}

                  </div>
                )
              })()}
            </Card>

            {/* Договора */}
            <Card
              title={`Договора (${card.contracts.length})`}
              action={
                <Link href="/directories?tab=contracts"
                      style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}>
                  В реестр →
                </Link>
              }
            >
              {card.contracts.length === 0 ? (
                <div style={{ padding: '16px 18px', color: 'var(--text-muted)', fontSize: 13 }}>Договоров нет</div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr>
                        {['№ договора', 'Дата', 'Формат', 'Пролонгация', 'Срок оплаты', 'Документ'].map(h => (
                          <th key={h} style={{
                            textAlign: 'left', padding: '8px 14px', fontSize: 11,
                            color: 'var(--text-faint)', fontWeight: 500, background: 'var(--bg-subtle)',
                            borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap',
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {card.contracts.map((c, i) => (
                        <tr key={c.id} style={{ background: i % 2 === 1 ? 'var(--bg-subtle)' : 'transparent' }}>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)',
                                       fontWeight: 600, color: 'var(--text-primary)' }}>{c.contract_number || '—'}</td>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)',
                                       color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{fmtDate(c.contract_date)}</td>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)', color: 'var(--text-secondary)' }}>{c.cooperation_format || '—'}</td>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)', color: 'var(--text-secondary)' }}>{c.prolongation || '—'}</td>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)', color: 'var(--text-secondary)' }}>
                            {c.payment_term_days ? `${c.payment_term_days} дн. ${c.payment_term_condition || ''}` : '—'}
                          </td>
                          <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-row)', whiteSpace: 'nowrap' }}>
                            {c.document_link && (
                              <a href={c.document_link} target="_blank" rel="noopener noreferrer"
                                 title="Открыть в ЭДО" style={{ marginRight: 6, textDecoration: 'none', fontSize: 15 }}>🔗</a>
                            )}
                            {c.attached_filename && (
                              <a href={`/api/contracts/${c.id}/document`}
                                 title={c.attached_filename} style={{ textDecoration: 'none', fontSize: 15 }}>📥</a>
                            )}
                            {!c.document_link && !c.attached_filename && '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {/* Операции */}
            {canViewOps && <Card
              title="Операции"
              action={<span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400 }}>{opsTotal} записей</span>}
            >
              {/* Фильтры — три дропдауна */}
              <div style={{
                padding: '8px 14px', borderBottom: '1px solid var(--border-card)',
                display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center',
              }}>
                <FilterSelect
                  value={opsStatus}
                  onChange={handleStatus}
                  options={STATUS_OPTIONS}
                />
                <span style={{ fontSize: 12, color: 'var(--text-muted)', flexShrink: 0 }}>Сортировка:</span>
                <FilterSelect
                  value={sortCol}
                  onChange={handleSortCol}
                  options={SORT_COL_OPTIONS}
                />
                <FilterSelect
                  value={sortDir}
                  onChange={handleSortDir}
                  options={SORT_DIR_OPTIONS}
                />
                {opsLoading && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>загрузка…</span>}
              </div>

              {/* Таблица */}
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <colgroup>
                    <col style={{ width: 88 }} /><col style={{ width: 130 }} />
                    <col style={{ width: 36 }} /><col style={{ width: 110 }} /><col style={{ width: 110 }} />
                    <col style={{ width: 90 }} /><col style={{ width: 80 }} /><col />
                    <col style={{ width: 80 }} /><col style={{ width: 90 }} /><col style={{ width: 90 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      {['Дата', 'Статус', 'ДЗ', 'Приход', 'Расход', 'Банк', 'Период', 'Статья', '№ ДС', '№ Счёта', 'Дата счёта'].map(h => (
                        <th key={h} style={{
                          textAlign: 'left', padding: '8px 12px', fontSize: 11,
                          color: 'var(--text-faint)', fontWeight: 500,
                          background: 'var(--bg-subtle)',
                          borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ops.length === 0 && !opsLoading ? (
                      <tr>
                        <td colSpan={11} style={{ padding: '24px 12px', color: 'var(--text-muted)',
                                                  textAlign: 'center', fontSize: 13 }}>
                          Операций нет
                        </td>
                      </tr>
                    ) : ops.map((op, i) => {
                      const dotColor = OP_STATUS_DOT[op.status] || 'var(--text-faint)'
                      return (
                        <tr key={op.id}
                            style={{ background: i % 2 === 1 ? 'var(--bg-subtle)' : 'transparent' }}
                            onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-tint)'}
                            onMouseLeave={e => e.currentTarget.style.background = i % 2 === 1 ? 'var(--bg-subtle)' : 'transparent'}>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       color: 'var(--text-muted)', whiteSpace: 'nowrap', fontSize: 12 }}>
                            {fmtDate(op.date)}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)', whiteSpace: 'nowrap' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5,
                                           fontSize: 11, color: 'var(--text-secondary)' }}>
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor,
                                             flexShrink: 0, display: 'inline-block' }} />
                              {op.status}
                            </span>
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)', textAlign: 'center' }}>
                            {op.receivable_status && RECEIVABLE_META[op.receivable_status]
                              ? <span title={RECEIVABLE_META[op.receivable_status].label}
                                      style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
                                               background: RECEIVABLE_META[op.receivable_status].color }} />
                              : null}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontWeight: op.income > 0 ? 600 : 400,
                                       color: op.income > 0 ? 'var(--income)' : 'var(--text-faint)' }}>
                            {op.income > 0 ? fmt(op.income) : '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontWeight: op.expense > 0 ? 600 : 400,
                                       color: op.expense > 0 ? 'var(--dot-overdue)' : 'var(--text-faint)' }}>
                            {op.expense > 0 ? fmt(op.expense) : '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                            {op.bank || '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       color: 'var(--text-secondary)', fontSize: 12 }}>
                            {op.period || '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       color: 'var(--text-primary)', overflow: 'hidden',
                                       textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
                            {op.article || '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                            {op.ds_num || '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                            {op.invoice || '—'}
                          </td>
                          <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--border-row)',
                                       fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                            {op.invoice_date ? fmtDate(op.invoice_date) : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Пагинация */}
              {opsTotal > OPS_LIMIT && (
                <div style={{ padding: '10px 14px', display: 'flex', gap: 8, alignItems: 'center',
                              borderTop: '1px solid var(--border-card)' }}>
                  <button disabled={opsPage === 0} style={BTN({ padding: '4px 12px', fontSize: 12 })}
                          onClick={() => handlePage(opsPage - 1)}>
                    ← Пред.
                  </button>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {opsPage * OPS_LIMIT + 1}–{Math.min((opsPage + 1) * OPS_LIMIT, opsTotal)} из {opsTotal}
                  </span>
                  <button disabled={(opsPage + 1) * OPS_LIMIT >= opsTotal} style={BTN({ padding: '4px 12px', fontSize: 12 })}
                          onClick={() => handlePage(opsPage + 1)}>
                    След. →
                  </button>
                </div>
              )}
            </Card>}

          </div>{/* /right col */}
        </div>{/* /grid */}
      </div>{/* /wrap */}
    </div>
  )
}
