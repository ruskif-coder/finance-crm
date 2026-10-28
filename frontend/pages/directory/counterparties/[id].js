import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const CounterpartyCardMobile = dynamic(() => import('@/components/mobile/CounterpartyCardMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { T as CT } from '@/components/counterparty/CounterpartyCard'
import CpHead from '@/components/counterpartyCard/Head'
import CpContracts from '@/components/counterpartyCard/Contracts'
import CpTurnover from '@/components/counterpartyCard/Turnover'
import CpOperations from '@/components/counterpartyCard/Operations'
import { Requisites as CpRequisites, Signers as CpSigners, Defaults as CpDefaults } from '@/components/counterpartyCard/Side'
import { makeApi as api } from '@/lib/http'
import { bankColor } from '@/lib/salesFormat'
import { Z } from '@/components/salesTableKit'
import { isAdmin as isAdminRole, can, getPermissions } from '@/lib/auth'
import { overlayClose } from '@/lib/overlay'
import { fmtDate as fmtCalendarDate, daysUntil } from '@/lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { errText } from '@/lib/loadError'

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
  if (m) return `${m[1]}-${m[2]}-${m[3]}`
  m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(s)
  if (m) return `${m[3]}-${m[2]}-${m[1]}`
  return null
}

// Статус окончания договора: истёк / истекает ≤30 дн. / действует
function contractExpiry(endDateText) {
  const d = parseEndDate(endDateText)
  if (!d) return null
  const days = daysUntil(d)
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
  // Убрать сохранённый банковский счёт — право «удаление» (аудит 2.6.76, п. 1.22): то же правило проверяет сервер.
  const [mayDelete, setMayDelete] = useState(false)
  useEffect(() => { setMayDelete(can(getPermissions(), 'counterparties', 'delete')) }, [])
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
      || isAdminRole()
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
        note: d.note || '',
        bank_accounts: d.bank_accounts.length
          ? d.bank_accounts
          : [{ bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }],
      })
    } catch (e) {
      // 422 приносит в `detail` СПИСОК объектов, и React падал, рисуя его, — белый экран
      // по адресу с нечисловым id (аудит 23.09.2026, 6.L5). Текст — через общий разбор.
      setError(e.response?.status === 422 ? 'Контрагент не найден — проверьте адрес' : errText(e))
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

  // Карточка v2: сводка (договоры, расчёты, тип) и ВСЕ операции — фильтры и итоги считаются на экране по отфильтрованному.
  const [overview, setOverview] = useState(null)
  const [allOps, setAllOps] = useState([])
  const [opFilter, setOpFilter] = useState('all')
  const [opMonth, setOpMonth] = useState(null)
  const [opQ, setOpQ] = useState('')
  const [canNewContract, setCanNewContract] = useState(false)
  useEffect(() => { setCanNewContract(can(getPermissions(), 'contracts', 'create')) }, [])
  const loadOverview = useCallback(async () => {
    if (!id) return
    try { setOverview((await api(localStorage.getItem('token')).get(`/counterparties/${id}/overview`)).data) }
    catch (e) { setOverview(null) }
  }, [id])
  const loadAllOps = useCallback(async () => {
    if (!id || !canViewOps) return
    try { setAllOps((await api(localStorage.getItem('token')).get(`/counterparties/${id}/operations?skip=0&limit=5000&sort_col=date&sort_dir=desc`)).data.items || []) }
    catch (e) { setAllOps([]) }
  }, [id, canViewOps])
  useEffect(() => { loadOverview() }, [loadOverview])
  useEffect(() => { loadAllOps() }, [loadAllOps])

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

  // Справочник статей — для селектов «статья по умолчанию». Грузится при КАЖДОМ открытии окна, а не раз на карточку:
  // статья, заведённая после открытия карточки, в списке не появлялась (владелец 14.10.2026: «новых нет»).
  const loadArticles = () => {
    const token = localStorage.getItem('token')
    api(token).get('/articles/').then(r => setArticles(r.data || [])).catch(() => {})
  }
  useEffect(() => { loadArticles() }, [])

  const startDefEdit = () => {
    loadArticles()
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
    // Карточка v2 по хендоффу «контрикZ» (28.10.2026): шапка с «Расчётами», договоры, оборот, операции; справа реквизиты, подписанты,
    // условия. Ширина до 1600 и прижато к левому краю — как карточка договора (владелец 28.10.2026).
    const showPlan = () => { setOpFilter('plan'); setOpMonth(null); setOpQ('') }
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
        <Head><title>{card.name} · контрагент | SIMB-AD ERP</title></Head>
        <Navbar active="directories" />
        <div style={{ boxSizing: 'border-box', padding: '22px 28px 40px' }}>
          <div style={{ width: '100%', maxWidth: 1600, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>
              <span onClick={() => router.push('/directory/counterparties')} style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>← Контрагенты</span>
              <span>/</span><span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{card.name}</span>
            </span>
            <CpHead card={card} ov={overview} canEdit={canEdit} canContract={canNewContract}
                    onEdit={() => { setEditMode(true); setSaveErr('') }} onNewContract={() => router.push(`/directory/contracts?new=${card.id}`)} onShowPlan={showPlan} />
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 440px', gap: 14, alignItems: 'start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
                {overview && <CpContracts rows={overview.contracts} warning={overview.warning} canSk={'sk' in overview} />}
                <CpTurnover monthly={(analytics && analytics.monthly) || []} analytics={analytics} month={opMonth} onMonth={setOpMonth} />
                {canViewOps && <CpOperations rows={allOps} filter={opFilter} onFilter={setOpFilter} month={opMonth} onMonth={setOpMonth} q={opQ} onQ={setOpQ} />}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
                <CpRequisites c={card} />
                <CpSigners c={card} canEdit={canEdit} onChange={loadCard} />
                <CpDefaults c={card} sk={overview && overview.sk} showSk={!!overview && 'sk' in overview} canEdit={canEdit} onEdit={startDefEdit} />
              </div>
            </div>
          </div>
        </div>
        {/* Условия по умолчанию. startDefEdit/saveDefaults были написаны, а формы к
            ним не существовало: состояние defEdit не рисовалось нигде, и карандаш в
            карточке вёл в никуда. Ставку НДС задать было негде. */}
        {defEdit && defData && (() => {
          const setD = (k, v) => setDefData(x => ({ ...x, [k]: v }))
          const inp = { width: '100%', boxSizing: 'border-box', border: `1px solid ${CT.border}`, borderRadius: 10, padding: '9px 11px', fontSize: 13, fontFamily: CT.sans, background: CT.card, color: CT.t1, outline: 'none' }
          const lbl = { fontSize: 11, color: CT.t3, marginBottom: 3 }
          const opts = (type) => (articles || []).filter(a => a.type === type)
          return (
            <div {...overlayClose(() => setDefEdit(false))} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'rgba(28,36,51,.4)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '40px 20px', fontFamily: CT.sans }}>
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
                  {/* СК с 27.10.2026 задаётся в «Агентских условиях» — по договору в связке с агентством (рекламодателем); прежние
                      поля юрлица — история, расчёт их не читает. */}
                  <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                    СК теперь задаётся по договору в «Агентских условиях» (Продажи → Агентские условия).{' '}
                    <Link href="/sales/agency-terms" target="_blank" style={{ color: 'var(--accent)' }}>Открыть</Link>
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
            <div {...overlayClose(() => { setEditMode(false); setSaveErr('') })} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'rgba(28,36,51,.4)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '40px 20px', fontFamily: CT.sans }}>
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
                  {/* Подписанты — не здесь: с 28.10.2026 их у юрлица несколько, они правятся секцией «Подписанты» карточки. Форма
                      их полей не шлёт, поэтому подписанта по умолчанию сохранение реквизитов не трогает. */}
                  <div style={{ fontFamily: CT.mono, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: CT.t3, fontWeight: 700, margin: '10px 0 8px' }}>Банковские счета</div>
                  {(editData.bank_accounts || []).map((b, i) => (
                    <div key={i} style={{ background: CT.subtle, borderRadius: 12, padding: '12px 12px 2px', marginBottom: 10 }}>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                        <input value={b.bank_name || ''} onChange={e => setBank(i, 'bank_name', e.target.value)} placeholder="Банк" style={{ ...inpS, flex: 1 }} />
                        {(mayDelete || !b.id) && (
                          <button onClick={() => delBank(i)} title="Удалить счёт" style={{ width: 38, flexShrink: 0, border: `1px solid ${CT.dangerTint}`, background: CT.card, color: CT.danger, borderRadius: 10, cursor: 'pointer' }}>✕</button>
                        )}
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
