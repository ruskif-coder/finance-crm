import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const CounterpartyCardMobile = dynamic(() => import('@/components/mobile/CounterpartyCardMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import CounterpartyCardDesktop, { T as CT } from '@/components/counterparty/CounterpartyCard'
import { makeApi as api } from '@/lib/http'
import { bankColor } from '@/lib/salesFormat'
import { overlayClose } from '@/lib/overlay'
import { fmtDate as fmtCalendarDate } from '@/lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const fmt = (n) => {
  if (!n && n !== 0) return '—'
  return new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽'
}
const fmtDate = (s) => fmtCalendarDate(s)
const MONTHS_SHORT = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
const fmtMonth = (p) => {
  if (!p) return ''
  const [y, m] = p.split('-')
  return `${MONTHS_SHORT[parseInt(m, 10) - 1]} ${y.slice(2)}`
}

// Дата окончания договора хранится текстом (end_date_text) — парсим ISO и dd.mm.yyyy,
// произвольный текст («Бессрочно») отдаём как null (без бейджа срока).
function parseEndDate(s) {
  if (!s) return null
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (m) return new Date(+m[1], +m[2] - 1, +m[3])
  m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(s)
  if (m) return new Date(+m[3], +m[2] - 1, +m[1])
  return null
}

// Статус окончания договора: истёк / истекает ≤30 дн. / действует
function contractExpiry(endDateText) {
  const d = parseEndDate(endDateText)
  if (!d) return null
  const days = Math.ceil((d - new Date()) / 86400000)
  if (days < 0) return { label: 'истёк', bg: 'var(--danger-tint)', color: 'var(--dot-overdue)' }
  if (days <= 30) return { label: `${days} дн.`, bg: '#FEF3C7', color: '#D97706' }
  return null
}


// ────────────────────────────────────────────────────────────────────────────
export default function CounterpartyCard() {
  const router = useRouter()
  const { id } = router.query
  const isMobile = useIsMobile()

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

  // Условия по умолчанию: НДС и статья раздельно по приходу/расходу (2026-07-16)
  const [articles, setArticles] = useState([])
  const [defEdit, setDefEdit] = useState(false)
  const [defData, setDefData] = useState(null)
  const [defSaving, setDefSaving] = useState(false)

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
        inn: d.inn || '', kpp: d.kpp || '', ogrn: d.ogrn || '', okpo: d.okpo || '',
        address: d.address || '', address_fact: d.address_fact || '',
        phone: d.phone || '', email: d.email || '',
        website: d.website || '', edo_id: d.edo_id || '',
        director_name: d.director_name || '', note: d.note || '',
        signer_position: d.signer_position || '', signer_basis: d.signer_basis || '',
        bank_accounts: d.bank_accounts.length
          ? d.bank_accounts
          : [{ bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }],
      })
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка загрузки')
    } finally { setLoading(false) }
  }, [id])

  // Все параметры — явно, без зависимости от замыкания
  // append — «Показать ещё»: дописываем страницу к списку, а не заменяем его.
  // Без этого кнопка выглядела бы как перелистывание: 50 строк сменялись следующими 50.
  const loadOps = useCallback(async (page, status, col, dir, append = false) => {
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
      const items = r.data.items || []
      setOps(prev => (append ? [...prev, ...items] : items))
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
  // Возврат на карточку = перечитать. Операции и реквизиты контрагента правят с
  // соседних экранов, а карточка показывала состояние на момент открытия
  // (найдено прибором check-freshness 16.09.2026).
  useRefreshOnReturn(() => loadCard())
  useEffect(() => { if (id) loadOps(0, '', 'date', 'desc') }, [id])
  useEffect(() => { loadAnalytics() }, [loadAnalytics])

  // Справочник статей — для селектов «статья по умолчанию»
  useEffect(() => {
    const token = localStorage.getItem('token')
    api(token).get('/articles/').then(r => setArticles(r.data || [])).catch(() => {})
  }, [])

  const startDefEdit = () => {
    setDefData({
      vat_rate_income: card.vat_rate_income ?? '',
      vat_rate_expense: card.vat_rate_expense ?? '',
      default_article_income_id: card.default_article_income_id || '',
      default_article_expense_id: card.default_article_expense_id || '',
    })
    setDefEdit(true)
  }

  const saveDefaults = async () => {
    const token = localStorage.getItem('token')
    setDefSaving(true)
    try {
      await api(token).put(`/counterparties/${id}/defaults`, {
        vat_rate_income: defData.vat_rate_income === '' ? null : Number(defData.vat_rate_income),
        vat_rate_expense: defData.vat_rate_expense === '' ? null : Number(defData.vat_rate_expense),
        default_article_income_id: defData.default_article_income_id ? Number(defData.default_article_income_id) : null,
        default_article_expense_id: defData.default_article_expense_id ? Number(defData.default_article_expense_id) : null,
      })
      setDefEdit(false)
      loadCard()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка сохранения')
    } finally { setDefSaving(false) }
  }

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
    loadOps(p, opsStatus, sortCol, sortDir, p > 0)
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
    if (card.director_name)   lines.push(`Подписант: ${card.director_name}`)
    if (card.signer_position) lines.push(`Должность подписанта: ${card.signer_position}`)
    if (card.signer_basis)    lines.push(`Основание полномочий: ${card.signer_basis}`)
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

  // ── МОБИЛЬНАЯ ВЕРСИЯ ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
        <Head><title>{card.name} · контрагент | SIMB-AD ERP</title></Head>
        <Navbar active="directories" />
        <CounterpartyCardMobile
          id={id} card={card} relation={relation} analytics={analytics} canEdit={canEdit}
          onBack={() => router.push('/directory/counterparties')}
          onEdit={() => { setEditMode(true); setSaveErr('') }}
          copyRequisites={copyRequisites} copied={copied}
          editMode={editMode} editData={editData} setEditData={setEditData}
          onSave={handleSave} saving={saving} saveErr={saveErr}
          onCancelEdit={() => { setEditMode(false); setSaveErr('') }} />
      </div>
    )
  }

  // ── ДЕСКТОП: референс-компонент дизайн-системы (правка — модалкой в том же дизайне) ──
  {
    const kmln = (v) => v ? (v / 1e6).toFixed(2).replace('.', ',') : '0'
    const pct = (v) => (v || v === 0) ? `${String(v).replace('.', ',')} %` : '—'
    const bs = analytics?.by_status || []
    const cnt = (p) => bs.filter(p).reduce((a, s) => a + (s.cnt || 0), 0)
    const planCnt = cnt(s => /ПЛАН/.test(s.status)), factCnt = cnt(s => s.status === 'ОПЛАЧЕНО'), payCnt = cnt(s => s.status === 'ПЛАН ОПЛАТ')
    const saldoV = stats.saldo || 0
    const STL = { 'ОПЛАЧЕНО': { l: 'Оплачено', c: CT.income }, 'ПЛАН ОПЛАТ': { l: 'План оплат', c: CT.warning }, 'ПЛАН ПОСТУПЛЕНИЙ': { l: 'План поступл.', c: CT.accent } }
    const monthly = analytics?.monthly || []
    const ta = analytics?.top_articles || []
    const taMax = ta[0] ? ((ta[0].income || 0) + (ta[0].expense || 0)) || 1 : 1
    const data = {
      name: card.name, state: card.status, kind: relation || '—',
      site: card.website ? card.website.replace(/^https?:\/\//i, '').replace(/\/$/, '') : null,
      brands: (card.linked_agencies || []).map(a => a.name_en || a.name).filter(Boolean),
      requisites: [
        { label: 'ИНН', value: card.inn || '—', mono: true }, { label: 'КПП', value: card.kpp || '—', mono: true },
        { label: 'ОГРН', value: card.ogrn || '—', mono: true }, { label: 'ОКПО', value: card.okpo || '—', mono: true },
        { label: 'Юр. адрес', value: card.address || '—' }, { label: 'Факт. адрес', value: card.address_fact || '—' },
        { label: 'Телефон', value: card.phone || '—', mono: true }, { label: 'Email', value: card.email || '—' },
        { label: 'Сайт', value: card.website || '—' }, { label: 'ЭДО', value: card.edo_id || '—', mono: true },
        { label: 'ФИО подписанта', value: card.director_name || '—' },
        { label: 'Должность подписанта', value: card.signer_position || '—' },
        { label: 'Основание полномочий', value: card.signer_basis || '—' },
        { label: 'Примечание', value: card.note || '—' },
      ],
      banks: (card.bank_accounts || []).filter(b => b.bank_name || b.rs).map(b => ({
        name: b.bank_name || 'Банк', rows: [{ label: 'Р/С', value: b.rs || '—' }, { label: 'К/С', value: b.ks || '—' }, { label: 'БИК', value: b.bik || '—' }],
      })),
      belonging: (card.linked_agencies || []).map(a => [
        { label: 'Краткое', value: a.name || '—' }, { label: 'Полное', value: a.name_en || a.name || '—' }, { label: 'Холдинг', value: a.holding || '—' },
      ]),
      terms: [
        { label: 'НДС приход', value: card.vat_rate_income != null ? `${card.vat_rate_income}%` : '—', mono: true },
        { label: 'НДС расход', value: card.vat_rate_expense != null ? `${card.vat_rate_expense}%` : '—', mono: true },
        { label: 'Статья прихода', value: card.default_article_income || '—' },
        { label: 'Статья расхода', value: card.default_article_expense || '—' },
      ],
      kpi: [
        { label: 'Операций всего', value: String(stats.op_count || 0), hint: `${planCnt} в плане · ${factCnt} факт`, color: CT.t1 },
        { label: 'Дебиторка', value: kmln(stats.receivable), hint: (stats.receivable || 0) > 0 ? 'есть задолженность' : 'нет просрочки', color: CT.accent },
        { label: 'Кредиторка', value: kmln(stats.payable), hint: (stats.payable || 0) > 0 ? `млн ₽ · ${payCnt} оп.` : '—', color: CT.warning },
        { label: 'Сальдо', value: (saldoV < 0 ? '−' : '') + kmln(Math.abs(saldoV)), hint: `млн ₽ · ${saldoV < 0 ? 'мы им должны' : 'нам должны'}`, color: saldoV < 0 ? CT.danger : CT.income },
      ],
      turnover: { months: monthly.map(m => fmtMonth(m.period)), income: monthly.map(m => (m.income || 0) / 1e6), expense: monthly.map(m => (m.expense || 0) / 1e6) },
      stats: [
        { label: 'Ср. приход', value: analytics?.avg_income ? fmt(analytics.avg_income) : '—', color: CT.income },
        { label: 'Ср. расход', value: analytics?.avg_expense ? fmt(analytics.avg_expense) : '—', color: CT.t2 },
        { label: 'Доля в выручке (12 мес)', value: pct(analytics?.share_income_12m), color: CT.income },
        { label: 'Доля в закупках (12 мес)', value: pct(analytics?.share_expense_12m), color: CT.t1 },
      ],
      topItems: ta.map(a => { const total = (a.income || 0) + (a.expense || 0); return { label: a.article, value: total, color: (a.income || 0) >= (a.expense || 0) ? CT.income : CT.expense, width: `${Math.round(total / taMax * 100)}%` } }),
      byStatus: (analytics?.by_status || []).map(s => { const m = STL[s.status] || { l: s.status, c: CT.t3 }; const sum = (s.income || 0) > 0 ? s.income : s.expense; return { label: m.l, color: m.c, ops: s.cnt, sum: sum || 0 } }),
      contracts: (card.contracts || []).map(c => ({
        number: c.contract_number || '—', date: fmtDate(c.contract_date), format: c.cooperation_format || '—',
        prolongation: c.prolongation || '—', payTerm: c.payment_term_days != null ? `${c.payment_term_days} дн.` : '—',
        endsAt: c.end_date_text || '—', expired: !!(contractExpiry(c.end_date_text) && contractExpiry(c.end_date_text).label === 'истёк'),
        document: (c.document_link || c.attached_filename) ? 'есть' : '—',
      })),
      opsTotal,
      ops: ops.map(o => { const m = STL[o.status] || { l: o.status, c: CT.t3 }; return { date: o.date ? fmtDate(o.date) : '—', status: m.l, statusColor: m.c, income: o.income || null, expense: o.expense || null, dz: null, bank: o.bank || 'не указан', bankColor: bankColor(o.bank), period: o.period || '—', item: o.article || '—', ds: o.ds_num || '—', account: o.invoice || '—', accountDate: o.invoice_date ? fmtDate(o.invoice_date) : '—' } }),
    }
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
        <Head><title>{card.name} · контрагент | SIMB-AD ERP</title></Head>
        <Navbar active="directories" />
        <CounterpartyCardDesktop data={data} canEdit={canEdit} copied={copied}
          onBack={() => router.push('/directory/counterparties')}
          onEdit={() => { setEditMode(true); setSaveErr('') }}
          onEditTerms={startDefEdit}
          onCopyRequisites={copyRequisites}
          onOpenContracts={() => router.push('/directory/contracts')}
          opsStatus={opsStatus} opsSortCol={sortCol} opsSortDir={sortDir} opsLoading={opsLoading}
          onOpsStatus={handleStatus} onOpsSortCol={handleSortCol} onOpsSortDir={handleSortDir}
          onOpsMore={() => handlePage(opsPage + 1)} />
        {/* Условия по умолчанию. startDefEdit/saveDefaults были написаны, а формы к
            ним не существовало: состояние defEdit не рисовалось нигде, и карандаш в
            карточке вёл в никуда. Ставку НДС задать было негде. */}
        {defEdit && defData && (() => {
          const setD = (k, v) => setDefData(x => ({ ...x, [k]: v }))
          const inp = { width: '100%', boxSizing: 'border-box', border: `1px solid ${CT.border}`, borderRadius: 10, padding: '9px 11px', fontSize: 13, fontFamily: CT.sans, background: CT.card, color: CT.t1, outline: 'none' }
          const lbl = { fontSize: 11, color: CT.t3, marginBottom: 3 }
          const opts = (type) => (articles || []).filter(a => a.type === type)
          return (
            <div {...overlayClose(() => setDefEdit(false))} style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(28,36,51,.4)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '40px 20px', fontFamily: CT.sans }}>
              <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 520, background: CT.card, borderRadius: 18, boxShadow: CT.shadow }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 24px', borderBottom: `1px solid ${CT.border}` }}>
                  <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em', color: CT.t1 }}>Условия по умолчанию</span>
                  <button onClick={() => setDefEdit(false)} style={{ marginLeft: 'auto', width: 32, height: 32, borderRadius: 9, border: `1px solid ${CT.border}`, background: CT.card, color: CT.t2, cursor: 'pointer', fontSize: 16 }}>✕</button>
                </div>
                <div style={{ padding: '18px 24px' }}>
                  {/* Ставки подставляются в форму операций при вводе суммы; у нашего
                      юрлица «НДС приход» задаёт вдобавок ставку по нашим услугам в
                      карточке сделки. Пусто — не задана; ноль означал бы «без НДС». */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
                    <div style={{ marginBottom: 10 }}>
                      <div style={lbl}>НДС приход, %</div>
                      <input value={defData.vat_rate_income} inputMode="decimal" placeholder="не задана"
                        onChange={e => setD('vat_rate_income', e.target.value.replace(',', '.'))} style={inp} />
                    </div>
                    <div style={{ marginBottom: 10 }}>
                      <div style={lbl}>НДС расход, %</div>
                      <input value={defData.vat_rate_expense} inputMode="decimal" placeholder="не задана"
                        onChange={e => setD('vat_rate_expense', e.target.value.replace(',', '.'))} style={inp} />
                    </div>
                  </div>
                  <div style={{ marginBottom: 10 }}>
                    <div style={lbl}>Статья по умолчанию — приход</div>
                    <select value={defData.default_article_income_id} style={inp}
                      onChange={e => setD('default_article_income_id', e.target.value)}>
                      <option value="">— не выбрана —</option>
                      {opts('income').map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                  </div>
                  <div style={{ marginBottom: 10 }}>
                    <div style={lbl}>Статья по умолчанию — расход</div>
                    <select value={defData.default_article_expense_id} style={inp}
                      onChange={e => setD('default_article_expense_id', e.target.value)}>
                      <option value="">— не выбрана —</option>
                      {opts('expense').map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', padding: '0 24px 20px' }}>
                  <button onClick={() => setDefEdit(false)} style={{ height: 36, padding: '0 16px', borderRadius: 10, border: `1px solid ${CT.border}`, background: CT.card, color: CT.t2, cursor: 'pointer', fontSize: 13 }}>Отмена</button>
                  <button onClick={saveDefaults} disabled={defSaving} style={{ height: 36, padding: '0 18px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontWeight: 700, cursor: defSaving ? 'default' : 'pointer', fontSize: 13, opacity: defSaving ? 0.6 : 1 }}>
                    {defSaving ? 'Сохраняю…' : 'Сохранить'}
                  </button>
                </div>
              </div>
            </div>
          )
        })()}

        {editMode && editData && (() => {
          const setF = (k, v) => setEditData(d => ({ ...d, [k]: v }))
          const setBank = (i, k, v) => setEditData(d => ({ ...d, bank_accounts: d.bank_accounts.map((b, j) => j === i ? { ...b, [k]: v } : b) }))
          const addBank = () => setEditData(d => ({ ...d, bank_accounts: [...d.bank_accounts, { bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }] }))
          const delBank = (i) => setEditData(d => ({ ...d, bank_accounts: d.bank_accounts.filter((_, j) => j !== i) }))
          const inpS = { width: '100%', boxSizing: 'border-box', border: `1px solid ${CT.border}`, borderRadius: 10, padding: '9px 11px', fontSize: 13, fontFamily: CT.sans, background: CT.card, color: CT.t1, outline: 'none' }
          const fld = (label, k, ml) => (
            <div key={k} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: CT.t3, marginBottom: 3 }}>{label}</div>
              {ml ? <textarea value={editData[k] || ''} onChange={e => setF(k, e.target.value)} rows={2} style={{ ...inpS, resize: 'vertical' }} />
                : <input value={editData[k] || ''} onChange={e => setF(k, e.target.value)} style={inpS} />}
            </div>
          )
          return (
            <div {...overlayClose(() => { setEditMode(false); setSaveErr('') })} style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(28,36,51,.4)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '40px 20px', fontFamily: CT.sans }}>
              <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 620, background: CT.card, borderRadius: 18, boxShadow: CT.shadow }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 24px', borderBottom: `1px solid ${CT.border}` }}>
                  <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em', color: CT.t1 }}>Редактирование реквизитов</span>
                  <button onClick={() => { setEditMode(false); setSaveErr('') }} style={{ marginLeft: 'auto', width: 32, height: 32, borderRadius: 9, border: `1px solid ${CT.border}`, background: CT.card, color: CT.t2, cursor: 'pointer', fontSize: 16 }}>✕</button>
                </div>
                <div style={{ padding: '18px 24px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
                    {fld('ИНН', 'inn')}{fld('КПП', 'kpp')}{fld('ОГРН', 'ogrn')}{fld('ОКПО', 'okpo')}
                    {fld('Телефон', 'phone')}
                  </div>
                  {fld('Юр. адрес', 'address', true)}{fld('Факт. адрес', 'address_fact', true)}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
                    {fld('Email', 'email')}{fld('Сайт', 'website')}
                  </div>
                  {fld('ЭДО', 'edo_id')}{fld('Примечание', 'note', true)}
                  {/* Подписант отдельным блоком: эти три поля печатаются в приложении к
                      договору («в лице Генерального директора Иванова И.И., действующего
                      на основании Устава»), и пустое из них означает прочерк в документе,
                      который уходит клиенту. */}
                  <div style={{ fontFamily: CT.mono, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: CT.t3, fontWeight: 700, margin: '10px 0 8px' }}>Подписант документов</div>
                  {fld('ФИО подписанта', 'director_name')}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
                    {fld('Должность', 'signer_position')}{fld('Основание полномочий', 'signer_basis')}
                  </div>
                  <div style={{ fontSize: 11, color: CT.t3, margin: '-4px 0 10px' }}>
                    Должность и основание — как в договоре: «Генеральный директор», «Устава»
                    или «Доверенности № 5 от 01.01.2026». Без них приложение к договору
                    не выгрузится.
                  </div>
                  <div style={{ fontFamily: CT.mono, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: CT.t3, fontWeight: 700, margin: '10px 0 8px' }}>Банковские счета</div>
                  {(editData.bank_accounts || []).map((b, i) => (
                    <div key={i} style={{ background: CT.subtle, borderRadius: 12, padding: '12px 12px 2px', marginBottom: 10 }}>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                        <input value={b.bank_name || ''} onChange={e => setBank(i, 'bank_name', e.target.value)} placeholder="Банк" style={{ ...inpS, flex: 1 }} />
                        <button onClick={() => delBank(i)} title="Удалить счёт" style={{ width: 38, flexShrink: 0, border: `1px solid ${CT.dangerTint}`, background: CT.card, color: CT.danger, borderRadius: 10, cursor: 'pointer' }}>✕</button>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 10px' }}>
                        <div style={{ marginBottom: 10 }}><input value={b.rs || ''} onChange={e => setBank(i, 'rs', e.target.value)} placeholder="Р/С" style={{ ...inpS, fontFamily: CT.mono }} /></div>
                        <div style={{ marginBottom: 10 }}><input value={b.ks || ''} onChange={e => setBank(i, 'ks', e.target.value)} placeholder="К/С" style={{ ...inpS, fontFamily: CT.mono }} /></div>
                        <div style={{ marginBottom: 10 }}><input value={b.bik || ''} onChange={e => setBank(i, 'bik', e.target.value)} placeholder="БИК" style={{ ...inpS, fontFamily: CT.mono }} /></div>
                      </div>
                    </div>
                  ))}
                  <button onClick={addBank} style={{ width: '100%', border: `1px dashed ${CT.border}`, background: CT.card, color: CT.accent, borderRadius: 10, padding: '10px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>+ Добавить счёт</button>
                  {saveErr && <div style={{ color: CT.danger, fontSize: 12.5, marginTop: 10 }}>{saveErr}</div>}
                </div>
                <div style={{ display: 'flex', gap: 8, padding: '14px 24px', borderTop: `1px solid ${CT.border}` }}>
                  <button onClick={handleSave} disabled={saving} style={{ background: CT.accent, color: '#fff', border: 'none', borderRadius: 10, padding: '11px 20px', fontSize: 14, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : 'Сохранить'}</button>
                  <button onClick={() => { setEditMode(false); setSaveErr('') }} style={{ border: `1px solid ${CT.border}`, background: CT.card, color: CT.t2, borderRadius: 10, padding: '11px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>Отмена</button>
                </div>
              </div>
            </div>
          )
        })()}
      </div>
    )
  }
}
