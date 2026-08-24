import { useState, useEffect, useRef, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, MultiDrop, IconBtn } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const OperationsMobile = dynamic(() => import('@/components/mobile/OperationsMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { PeriodSelect } from '@/components/PeriodSelect'
import { makeApi as api } from '@/lib/http'
import { getPermissions } from '@/lib/auth'
import { T } from '@/lib/tokens'

const STATUSES = ['ОПЛАЧЕНО', 'ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const BANK_COLOR = { 'АльфаБанк': 'var(--bank-alfa)', 'ОПТ Банк': 'var(--bank-opt)', 'Совкомбанк': 'var(--bank-sovkom)', 'Наличные': 'var(--bank-cash)' }
const VAT_OPTIONS = [0, 5, 7, 10, 20, 22]
const PAGE_SIZES = [50, 100, 300, 500]
// «Незаполненные» — как в реестре сделок: выбранные дыры складываются по ИЛИ,
// потому что человек ищет, что дозаполнить, а не строку без всего сразу.
const GAP_FIELDS = [
  { value: 'article', label: 'нет статьи' },
  { value: 'counterparty', label: 'нет контрагента' },
  { value: 'period', label: 'нет периода' },
  { value: 'bank', label: 'нет банка' },
]
// статус-чип: фон / текст / точка
const STATUS_CHIP = {
  'ОПЛАЧЕНО': ['#E6F5EF', '#1F7D5E', 'var(--income)'],
  'ПЛАН ОПЛАТ': ['#EEF1FE', '#3A50BE', 'var(--dot-expense)'],
  'ПЛАН ПОСТУПЛЕНИЙ': ['var(--warning-tint)', T.warningText, 'var(--dot-current-dz)'],
  'ОЖИДАЕТ': ['var(--warning-tint)', T.warningText, 'var(--dot-current-dz)'],
}
const statusChip = (s) => STATUS_CHIP[s] || ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--text-faint)']

const fmt = (n) => (n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '')
// с копейками (для сумм выбранного): всегда 2 знака
const fmt2 = (n) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0)
const fmtDate = (d) => { if (!d) return ''; const [y, m, dd] = String(d).slice(0, 10).split('-'); return dd ? `${dd}.${m}.${y.slice(2)}` : d }
const emptyForm = () => ({ date: new Date().toISOString().slice(0, 10), status: 'ОПЛАЧЕНО', income: '', expense: '', bank: 'АльфаБанк', period: '', vat_rate: 0, article_id: '', counterparty_id: '', ds_num: '', invoice: '', invoice_date: '', description: '', document_link: '' })

// Ввод суммы с копейками: цифры + один разделитель (точка/запятая). Храним строкой во
// время ввода (чтобы курсор не прыгал и можно было набрать копейки), парсим при сохранении.
const sanMoney = (s) => {
  s = String(s ?? '').replace(/[^\d.,]/g, '')
  const i = s.search(/[.,]/)
  return i === -1 ? s : s.slice(0, i + 1) + s.slice(i + 1).replace(/[.,]/g, '')
}
const moneyNum = (v) => { const n = parseFloat(String(v ?? '').replace(',', '.')); return Number.isFinite(n) ? n : 0 }

const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const lbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 5, display: 'block' }
const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 11px', fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', fontFamily: UI }

// сегмент-переключатель (Месяц|Квартал, ставка НДС и т.п.)
function Seg({ options, value, onChange, mono }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, height: 36, alignItems: 'stretch' }}>
      {options.map(o => {
        const on = String(o.value) === String(value)
        return <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
          style={{ flex: '0 0 auto', border: 'none', borderRadius: 7, padding: '0 12px', cursor: 'pointer', fontFamily: mono ? MONO : UI, fontSize: 12, fontWeight: on ? 700 : 600, background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-secondary)' }}>{o.label}</button>
      })}
    </div>
  )
}

// Однослот с поиском в шапке (для длинных списков — Статья/Контрагент)
function SingleSelect({ value, onChange, options, placeholder, emptyLabel }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const selO = options.find(o => String(o.value) === String(value))
  const shown = options.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase())).slice(0, 300)
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ ...inp, cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: selO ? 'var(--text-primary)' : 'var(--text-faint)' }}>{selO ? selO.label : placeholder} ▾</div>
      {open && (
        <div style={{ position: 'absolute', top: '110%', left: 0, right: 0, minWidth: 210, zIndex: 50, marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', maxHeight: 300, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 8 }}><input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск" style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} /></div>
          <div style={{ overflowY: 'auto', padding: 5 }}>
            <div onClick={() => { onChange(''); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', color: 'var(--text-muted)' }}>{emptyLabel || '— не выбрано —'}</div>
            {shown.map(o => <div key={o.value} onClick={() => { onChange(o.value); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12.5, cursor: 'pointer', background: String(o.value) === String(value) ? 'var(--accent-tint)' : 'transparent', color: String(o.value) === String(value) ? 'var(--accent)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</div>)}
            {!shown.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// Единый набор полей формы (создание/редактирование)
// Обводка иконок. На модульном уровне, а не внутри Operations2: её использует и
// OpFields, объявленный здесь же снаружи, — из компонента он её не видит.
const IcoStroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round', strokeLinejoin: 'round' }

// Ячейка формы. ВЫНЕСЕНА из OpFields на модульный уровень: если объявлять её внутри
// компонента, при каждом рендере (нажатии клавиши в поле) она получает новую
// идентичность функции → React размонтирует/монтирует <Cell> с input'ом заново →
// поле теряет фокус после каждой цифры. Стабильная ссылка это устраняет.
const Cell = ({ label, opt, accent, children }) => (
  <div><span style={lbl}>{label}{opt ? <span style={{ color: accent === 'warn' ? T.warningText : 'var(--text-faint)', marginLeft: 6 }}>необяз.</span> : ''}</span>{children}</div>
)

function OpFields({ f, set, articles, counterparties, accent, mode = 'edit',
                    files = [], onAttach, onRemoveFile, busyFiles }) {
  const artOpts = articles.map(a => ({ value: a.id, label: a.name }))
  const cpOpts = counterparties.map(c => ({ value: c.id, label: c.name }))
  const cpById = Object.fromEntries(counterparties.map(c => [c.id, c]))
  const toNum = (v) => Number(String(v ?? '').replace(/[^0-9.]/g, '')) || 0
  const amt = toNum(f.income) || toNum(f.expense)
  const vatAmount = f.vat_rate > 0 && amt > 0 ? Math.round(amt * f.vat_rate / (100 + f.vat_rate)) : 0
  // Смена статуса (только при создании): «оплачено» — дата сегодня + банк по умолчанию;
  // «план оплат/поступлений» — дата и банк пустые (даже при переключении).
  const onStatus = (v) => {
    if (mode !== 'create') return set({ status: v })
    if (v === 'ОПЛАЧЕНО') set({ status: v, date: f.date || new Date().toISOString().slice(0, 10), bank: f.bank || 'АльфаБанк' })
    else set({ status: v, date: '', bank: '' })
  }
  // Выбор контрагента подтягивает его статью/НДС по умолчанию — по направлению суммы
  // (поступление → доходные, списание → расходные).
  const onCounterparty = (v) => {
    const patch = { counterparty_id: v }
    const cp = cpById[+v] || cpById[v]
    if (cp) {
      const inc = toNum(f.income) > 0, exp = toNum(f.expense) > 0
      const art = inc ? cp.default_article_income_id : exp ? cp.default_article_expense_id : null
      if (art) patch.article_id = art
      const vr = inc ? cp.vat_rate_income : exp ? cp.vat_rate_expense : null
      if (vr != null) patch.vat_rate = vr
    }
    set(patch)
  }
  const sel = (val, onCh, opts, ph) => (
    <select value={val} onChange={e => onCh(e.target.value)} style={inp}><option value="">{ph}</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="Статус">{sel(f.status, onStatus, STATUSES.map(s => ({ value: s, label: s })), 'статус')}</Cell>
        <Cell label="Дата" opt accent={accent}>{<input type="date" value={f.date} onChange={e => set({ date: e.target.value })} style={{ ...inp, ...(accent === 'warn' ? { borderColor: 'var(--dot-current-dz)' } : {}) }} />}</Cell>
        <Cell label="Поступление"><input inputMode="decimal" value={f.income ?? ''} onChange={e => set({ income: sanMoney(e.target.value) })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Списание"><input inputMode="decimal" value={f.expense ?? ''} onChange={e => set({ expense: sanMoney(e.target.value) })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Банк" opt accent={accent}>{sel(f.bank, v => set({ bank: v }), BANKS.map(b => ({ value: b, label: b })), 'не указан')}</Cell>
        <Cell label="Период"><PeriodSelect dense value={f.period} onChange={v => set({ period: v })} /></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="НДС">
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={f.vat_rate} onChange={e => set({ vat_rate: +e.target.value })} style={{ ...inp, flex: '0 0 44%', fontFamily: MONO }}>
              {VAT_OPTIONS.map(v => <option key={v} value={v}>{v}%</option>)}
            </select>
            <input readOnly value={vatAmount ? fmt(vatAmount) + ' ₽' : '—'} title="Сумма НДС по ставке (не редактируется)"
              style={{ ...inp, flex: 1, minWidth: 0, fontFamily: MONO, textAlign: 'right', background: 'var(--bg-subtle)', color: 'var(--text-muted)' }} />
          </div>
        </Cell>
        <Cell label="Статья"><SingleSelect value={f.article_id} onChange={v => set({ article_id: v })} options={artOpts} placeholder="не выбрана" emptyLabel="— не выбрано —" /></Cell>
        <Cell label="Контрагент"><SingleSelect value={f.counterparty_id} onChange={onCounterparty} options={cpOpts} placeholder="выберите или введите" emptyLabel="— не выбрано —" /></Cell>
        <Cell label="№ ДС"><input value={f.ds_num} onChange={e => set({ ds_num: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="№ счёта"><input value={f.invoice} onChange={e => set({ invoice: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Дата счёта"><input type="date" value={f.invoice_date} onChange={e => set({ invoice_date: e.target.value })} style={inp} /></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1.7fr', gap: 14 }}>
        <Cell label="Документ">
          <div style={{ display: 'flex', gap: 6 }}>
            <input value={f.document_link} onChange={e => set({ document_link: e.target.value })} placeholder="https://…"
              title="Ссылка на документ во внешнем хранилище" style={{ ...inp, flex: 1, minWidth: 0 }} />
            {/* Сканы кладём к себе: часть первички существует только на бумаге, и
                ссылке её заменить нечем. Ссылка при этом остаётся — у операции может
                быть и то, и другое. */}
            <label title="Приложить скан документа"
              style={{ ...inp, flex: '0 0 auto', width: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
                       cursor: busyFiles ? 'wait' : 'pointer', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 12,
                       fontWeight: 700, color: 'var(--accent)', borderColor: 'var(--accent)', opacity: busyFiles ? .6 : 1 }}>
              <input type="file" multiple disabled={!!busyFiles} style={{ display: 'none' }}
                onChange={e => { const list = Array.from(e.target.files || []); e.target.value = ''; if (list.length) onAttach && onAttach(list) }} />
              <svg width="13" height="13" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 5v14M5 12h14" /></svg>
              {busyFiles ? 'Загрузка…' : 'Приложить файл'}
            </label>
          </div>
          {files.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
              {files.map((fl, i) => (
                <div key={fl.id || ('p' + i)} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, minWidth: 0 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" style={{ ...IcoStroke, flex: '0 0 auto', color: 'var(--text-faint)' }}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
                  <span title={fl.original_name} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: fl.pending ? 'var(--text-muted)' : 'var(--text-primary)' }}>{fl.original_name}</span>
                  <span style={{ flex: '0 0 auto', fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{fl.pending ? 'после сохранения' : fmtSize(fl.size_bytes)}</span>
                  <span onClick={() => onRemoveFile && onRemoveFile(fl, i)} title="Убрать файл" className="op-ico op-ico-d"
                    style={{ flex: '0 0 auto', width: 18, height: 18, color: 'var(--text-faint)' }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" style={IcoStroke}><path d="M6 6l12 12M18 6L6 18" /></svg>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Cell>
        <Cell label="Описание"><input value={f.description} onChange={e => set({ description: e.target.value })} placeholder="комментарий к операции" style={inp} /></Cell>
      </div>
    </div>
  )
}

const fmtSize = (n) => !n ? '' : n < 1024 ? n + ' Б' : n < 1024 * 1024 ? Math.round(n / 1024) + ' КБ'
  : (n / 1024 / 1024).toFixed(1).replace('.', ',') + ' МБ'

// колонки таблицы (сетка из хендоффа)
// Четвёртый элемент — ключ сортировки на сервере (см. _sort_map в operations.py).
// Он есть у каждой колонки, кроме «Действий»: там сортировать нечего. «ДЗ» сортируется
// по сроку оплаты — метка (просрочка/текущая/план) это и есть возраст долга.
const COLS = [
  ['sel', '26px', ''], ['date', '78px', 'Дата', 'date'], ['status', '112px', 'Статус', 'status'], ['dz', '36px', 'ДЗ', 'dz'],
  ['income', '98px', 'Поступление', 'income'], ['expense', '98px', 'Списание', 'expense'], ['bank', '96px', 'Банк', 'bank'],
  ['period', '78px', 'Период', 'period'], ['article', '122px', 'Статья', 'article'], ['counterparty', '1.2fr', 'Контрагент', 'counterparty'],
  ['vat', '46px', 'НДС', 'vat_rate'], ['vat_amount', '84px', 'НДС сумма', 'vat_fact'], ['ds_num', '62px', '№ ДС', 'ds_num'], ['invoice', '112px', '№ счёта', 'invoice'],
  ['invoice_date', '88px', 'Дата счёта', 'invoice_date'], ['doc', '32px', 'Док', 'doc'], ['description', '0.9fr', 'Описание', 'description'], ['actions', '72px', 'Действия'],
]
const GRID = COLS.map(c => c[1]).join(' ')
const RIGHT = new Set(['income', 'expense', 'vat', 'vat_amount'])

export default function Operations2() {
  const router = useRouter()
  // Точечная ссылка на операцию — /finance/operations?op=<id>. Приходит из импорта
  // документов Диадока, где иначе на операцию сослаться нечем: у реестра нет ни
  // карточки строки, ни собственного адреса у операции.
  const focusOp = router.query.op ? String(router.query.op) : null
  const [perms, setPerms] = useState({})
  const canEdit = can(perms, 'operations', 'edit')
  const canImport = can(perms, 'import')
  const isMobile = useIsMobile()
  const [ops, setOps] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [articles, setArticles] = useState([])
  const [counterparties, setCounterparties] = useState([])
  const [periodOptions, setPeriodOptions] = useState([])
  const [updatedAt, setUpdatedAt] = useState('')

  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(300)
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')

  const [dateFrom, setDateFrom] = useState(''); const [dateTo, setDateTo] = useState('')
  const [fStatus, setFStatus] = useState([]); const [fBank, setFBank] = useState([]); const [fArticle, setFArticle] = useState([]); const [fCp, setFCp] = useState([]); const [fPeriod, setFPeriod] = useState([]); const [fOpType, setFOpType] = useState([]); const [fGaps, setFGaps] = useState([])

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState(emptyForm())
  const [editing, setEditing] = useState(null)        // { id, ...form }
  const [sel, setSel] = useState({})                  // { id: true }
  const [bulk, setBulk] = useState({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' })
  const [editFiles, setEditFiles] = useState([])   // сканы открытой на правку операции
  const [newFiles, setNewFiles] = useState([])     // выбранные в форме создания, ещё не отправленные
  const [filesBusy, setFilesBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  // Высота шапки меряется, а не задаётся числом: у шапки две строки, и их набор
  // зависит от прав пользователя — закреплённая панель массовой правки иначе то
  // наезжала бы на меню, то висела бы с зазором.
  const [navH, setNavH] = useState(60)
  const lastSelIdx = useRef(null)   // якорь для shift-выбора диапазона
  const [hidden, setHidden] = useState(new Set())   // скрытые колонки
  const [colPicker, setColPicker] = useState(false)
  const toggleCol = (k) => setHidden(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); localStorage.setItem('ops2_hidden', JSON.stringify([...n])); return n })
  const visibleCols = COLS.filter(([k]) => !hidden.has(k))
  const gridT = visibleCols.map(c => c[1]).join(' ')

  const tok = () => localStorage.getItem('token')

  useEffect(() => {
    if (!tok()) { router.push('/login'); return }
    try { setPerms(getPermissions()) } catch (e) {}
    try { const h = JSON.parse(localStorage.getItem('ops2_hidden')); if (Array.isArray(h)) setHidden(new Set(h)) } catch (e) {}
    Promise.all([api(tok()).get('/articles/'), api(tok()).get('/counterparties/?limit=1000')])
      .then(([a, c]) => { setArticles(a.data?.items || a.data || []); setCounterparties(c.data?.items || c.data || []) }).catch(() => {})
    api(tok()).get('/operations/periods').then(r => setPeriodOptions(r.data?.periods || [])).catch(() => {})
    const measure = () => { const el = document.querySelector('[data-navbar]'); if (el) setNavH(el.getBoundingClientRect().height) }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const loadOps = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ skip: page * pageSize, limit: pageSize, sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p)); fGaps.forEach(g => params.append('gaps', g))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      // ?op=<id> — точечная ссылка на операцию (из импорта документов Диадока).
      // Пока она в адресе, остальные фильтры не важны: показывается ровно эта строка.
      if (focusOp) params.append('ids', focusOp)
      const res = await api(tok()).get(`/operations/?${params}`)
      setOps(res.data?.items || []); setTotal(res.data?.total || 0)
      // Время последней загрузки данных (обновляется при любом изменении — add/edit/delete
      // зовут loadOps). Считаем на клиенте, не при рендере — без SSR-рассинхрона.
      setUpdatedAt(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }))
    } catch (e) { if (e.response?.status === 401) router.push('/login') }
    finally { setLoading(false) }
  }
  useEffect(() => { if (tok()) loadOps() }, [page, pageSize, sortCol, sortDir, fStatus, fBank, fArticle, fCp, fPeriod, fGaps, dateFrom, dateTo, focusOp])

  // op-type фильтр — клиентски по загруженной странице
  const rows = ops.filter(o => !fOpType.length || (fOpType.includes('income') && o.income > 0) || (fOpType.includes('expense') && o.expense > 0))

  const onSort = (k) => { if (!k) return; if (sortCol === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortCol(k); setSortDir('desc') }; setPage(0) }
  const resetFilters = () => { setDateFrom(''); setDateTo(''); setFStatus([]); setFBank([]); setFArticle([]); setFCp([]); setFPeriod([]); setFOpType([]); setFGaps([]); setPage(0) }

  // Приведение формы к типам бэкенда: пустые строки в id/датах → null, иначе
  // pydantic (Optional[int]/Optional[date]) отвергает '' → 422 «ошибка сохранения».
  const cleanOp = (f) => ({
    date: f.date || null, status: f.status, income: moneyNum(f.income), expense: moneyNum(f.expense),
    bank: f.bank || null, period: f.period || null, vat_rate: +f.vat_rate || 0,
    article_id: f.article_id ? +f.article_id : null, counterparty_id: f.counterparty_id ? +f.counterparty_id : null,
    ds_num: f.ds_num || '', invoice: f.invoice || '', invoice_date: f.invoice_date || null,
    description: f.description || '', document_link: f.document_link || '',
  })

  const saveCreate = async () => {
    const f = createForm
    const isPaid = f.status === 'ОПЛАЧЕНО'
    const miss = []
    if (!f.period) miss.push('период')
    if (!f.article_id) miss.push('статья')
    if (!f.counterparty_id) miss.push('контрагент')
    if (isPaid) { if (!f.date) miss.push('дата'); if (!f.bank) miss.push('банк') }
    if (miss.length) { alert('Заполните обязательные поля: ' + miss.join(', ')); return }
    setSaving(true)
    try {
      const res = await api(tok()).post('/operations/', cleanOp(createForm))
      const newId = res.data?.id
      if (newId && newFiles.length) await attachToExisting(newId, newFiles)
      setCreateForm(emptyForm()); setNewFiles([]); setCreateOpen(false); loadOps()
    }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось создать') } finally { setSaving(false) }
  }
  const downloadTemplate = async () => {
    try {
      const res = await api(tok()).get('/operations/import/template', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url; a.download = 'shablon_operaciy.xlsx'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось скачать шаблон') }
  }
  const downloadExport = async () => {
    try {
      const params = new URLSearchParams({ sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p)); fGaps.forEach(g => params.append('gaps', g))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      const res = await api(tok()).get(`/operations/export?${params}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      a.download = `operacii_${new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '')}.xlsx`
      a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось выгрузить') }
  }
  // Форма правки раскрывается прямо под своей строкой, поэтому никуда не скроллим:
  // строка уже перед глазами, а прыжок к форме наверху таблицы терял место в списке.
  const openEdit = (op) => {
    setEditFiles([]); loadOpFiles(op.id)
    setEditing({ id: op.id, date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || '', expense: op.expense || '', bank: op.bank || '', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
  }
  const saveEdit = async () => {
    setSaving(true)
    try { await api(tok()).put(`/operations/${editing.id}`, cleanOp(editing)); setEditing(null); setEditFiles([]); loadOps() }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить') } finally { setSaving(false) }
  }

  // Приложенные сканы. В правке операция уже существует — файл уходит на сервер сразу.
  // В создании id ещё нет, поэтому выбранные файлы ждут в памяти браузера и уезжают
  // сразу после того, как POST вернёт номер новой операции. Промежуточное хранилище
  // на сервере при таком порядке не нужно.
  const loadOpFiles = async (id) => {
    try { const r = await api(tok()).get(`/operations/${id}/files`); setEditFiles(r.data || []) }
    catch (e) { setEditFiles([]) }
  }
  const attachToExisting = async (id, list) => {
    setFilesBusy(true)
    try {
      for (const file of list) {
        const fd = new FormData(); fd.append('file', file)
        await api(tok()).post(`/operations/${id}/files`, fd)
      }
      await loadOpFiles(id)
    } catch (e) {
      alert(e.response?.data?.detail || 'Не удалось приложить файл')
      await loadOpFiles(id)
    } finally { setFilesBusy(false) }
  }
  const removeFromExisting = async (id, fl) => {
    if (!confirm(`Убрать файл «${fl.original_name}»?`)) return
    try { await api(tok()).delete(`/operations/${id}/files/${fl.id}`); await loadOpFiles(id) }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось удалить файл') }
  }
  // Список для формы создания: File-объекты браузера приводим к той же форме,
  // что приходит с сервера, чтобы компонент формы не различал два случая.
  const pendingAsFiles = newFiles.map(file => ({ original_name: file.name, size_bytes: file.size, pending: true }))
  // Копирование: не создаём дубль сразу, а открываем форму «Новая операция» с данными
  // копируемой — пользователь правит и подтверждает (POST на «Добавить операцию»).
  const dupOp = (op) => {
    setEditing(null)
    setCreateForm({ date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || '', expense: op.expense || '', bank: op.bank || 'АльфаБанк', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    setCreateOpen(true)
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }
  // мобильные CRUD-хендлеры (форма в OperationsMobile)
  const mobileSave = async (body, id) => {
    const b = cleanOp(body)
    try { if (id) await api(tok()).put(`/operations/${id}`, b); else await api(tok()).post('/operations/', b); loadOps(); return true }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось сохранить'); return false }
  }
  const mobileDelete = async (id) => { try { await api(tok()).delete(`/operations/${id}`); loadOps() } catch (e) { alert('Не удалось удалить') } }
  const delOp = async (id) => { if (!window.confirm('Удалить операцию?')) return; try { await api(tok()).delete(`/operations/${id}`); loadOps() } catch (e) { alert('Не удалось удалить') } }

  const selIds = Object.keys(sel).filter(k => sel[k]).map(Number)
  const selRows = rows.filter(o => sel[o.id])
  // выбор с Shift: диапазон от последнего кликнутого до текущего (в пределах страницы)
  const toggleSel = (o, shiftKey) => {
    const idx = rows.findIndex(r => r.id === o.id)
    if (shiftKey && lastSelIdx.current != null && lastSelIdx.current >= 0 && lastSelIdx.current < rows.length) {
      const [a, b] = [lastSelIdx.current, idx].sort((x, y) => x - y)
      const target = !sel[o.id]
      setSel(s => { const n = { ...s }; rows.slice(a, b + 1).forEach(r => { n[r.id] = target }); return n })
    } else {
      setSel(s => ({ ...s, [o.id]: !s[o.id] }))
    }
    lastSelIdx.current = idx
  }
  const selIncome = selRows.reduce((s, o) => s + (o.income || 0), 0)
  const selExpense = selRows.reduce((s, o) => s + (o.expense || 0), 0)
  const applyBulk = async () => {
    const body = { ids: selIds }
    Object.entries(bulk).forEach(([k, v]) => { if (v !== '') body[k] = k === 'vat_rate' ? +v : v })
    if (Object.keys(body).length <= 1) { alert('Заполните хотя бы одно поле'); return }
    setSaving(true)
    try { await api(tok()).patch('/operations/bulk', body); setSel({}); setBulk({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' }); loadOps() }
    catch (e) { alert(e.response?.data?.detail || 'Не удалось применить') } finally { setSaving(false) }
  }
  const delBulk = async () => { if (!window.confirm(`Удалить ${selIds.length} операций?`)) return; setSaving(true); try { await api(tok()).delete('/operations/bulk', { data: { ids: selIds } }); setSel({}); loadOps() } catch (e) { alert('Не удалось удалить') } finally { setSaving(false) } }

  const pageIncome = rows.reduce((s, o) => s + (o.income || 0), 0)
  const pageExpense = rows.reduce((s, o) => s + (o.expense || 0), 0)
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const cpName = Object.fromEntries(counterparties.map(c => [c.id, c.name]))
  const artName = Object.fromEntries(articles.map(a => [a.id, a.name]))
  const opt = (arr, get = x => x) => arr.map(get)

  const allOnPage = rows.length > 0 && rows.every(o => sel[o.id])
  const someOnPage = rows.some(o => sel[o.id])

  const chev = (d) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={d} /></svg>

  const cell = (o, key) => {
    switch (key) {
      case 'sel': return <input type="checkbox" checked={!!sel[o.id]} onClick={e => toggleSel(o, e.shiftKey)} onChange={() => {}} title="Shift — выбрать диапазон" style={{ width: 14, height: 14, cursor: 'pointer' }} />
      case 'date': return <span style={{ fontFamily: MONO }}>{fmtDate(o.date) || '—'}</span>
      case 'status': { const [bg, fg, dot] = statusChip(o.status); return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: bg, color: fg, borderRadius: 8, padding: '3px 8px', fontFamily: MONO, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', whiteSpace: 'nowrap' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{o.status}</span> }
      case 'dz': { const rs = o.receivable_status; const meta = { overdue: ['Просрочка', 'var(--dot-overdue)'], current: ['Текущая', 'var(--dot-current-dz)'], future: ['План', 'var(--accent)'] }[rs]; return meta ? <span title={meta[0]} style={{ width: 10, height: 10, borderRadius: '50%', background: meta[1], display: 'inline-block' }} /> : <span style={{ color: '#C3C9D8' }}>—</span> }
      case 'income': return o.income ? <span title={fmt2(o.income) + ' ₽'} style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--income)' }}>{fmt(o.income)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'expense': return o.expense ? <span title={fmt2(o.expense) + ' ₽'} style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(o.expense)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'bank': return o.bank ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}><span style={{ width: 8, height: 8, borderRadius: 2, background: BANK_COLOR[o.bank] || 'var(--text-faint)' }} />{o.bank}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'period': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.period || '—'}</span>
      case 'article': return <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{artName[o.article_id] || o.article || '—'}</span>
      case 'counterparty': {
        // Стрелка ведёт в карточку контрагента и только в новой вкладке: реестр операций
        // открыт с фильтрами и прокруткой, и уводить с него — терять рабочее место.
        // stopPropagation обязателен — иначе клик по ссылке заодно откроет строку на правку
        // (тот же приём, что у иконки документа ниже).
        const cpn = cpName[o.counterparty_id] || o.counterparty || '—'
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, minWidth: 0, fontWeight: 700 }}>
            {o.counterparty_id ? (
              <a href={`/directory/counterparties/${o.counterparty_id}`} target="_blank" rel="noreferrer"
                 onClick={e => e.stopPropagation()} title="Карточка контрагента — в новой вкладке"
                 className="op-ico" style={{ width: 18, height: 18, flex: '0 0 auto', color: 'var(--text-faint)' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" style={IcoStroke}><path d="M7 17 17 7" /><path d="M9 7h8v8" /></svg>
              </a>
            ) : null}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cpn}</span>
          </span>
        )
      }
      case 'vat': return <span style={{ fontFamily: MONO }}>{o.vat_rate ? o.vat_rate + '%' : <span style={{ color: '#C3C9D8' }}>—</span>}</span>
      case 'vat_amount': return o.vat_fact ? <span title={fmt2(o.vat_fact) + ' ₽'} style={{ fontFamily: MONO }}>{fmt(o.vat_fact)}</span> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'ds_num': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.ds_num || '—'}</span>
      case 'invoice': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.invoice || '—'}</span>
      case 'invoice_date': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{fmtDate(o.invoice_date) || '—'}</span>
      case 'doc': return o.document_link ? <a href={/^https?:\/\//i.test(o.document_link) ? o.document_link : undefined} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} title="Открыть документ" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, background: 'var(--accent-tint)', color: 'var(--accent)' }}><svg width="14" height="14" viewBox="0 0 24 24" style={IcoStroke}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg></a> : <span style={{ color: '#C3C9D8' }}>—</span>
      case 'description': return <span title={o.description} style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.description || '—'}</span>
      case 'actions': return canEdit ? <span style={{ display: 'inline-flex', gap: 4 }}>
        <span onClick={() => dupOp(o)} title="Дублировать" className="op-ico" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg></span>
        <span onClick={() => openEdit(o)} title="Редактировать" className="op-ico op-ico-w" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>
        <span onClick={() => delOp(o.id)} title="Удалить" className="op-ico op-ico-d" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M6 6l12 12M18 6L6 18" /></svg></span>
      </span> : null
      default: return null
    }
  }

  const HeadCard = ({ title, right, iconBg, iconFg, iconPath, onClose }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 24px', borderBottom: '1px solid var(--border-inner)' }}>
      <span style={{ width: 28, height: 28, borderRadius: 9, background: iconBg, color: iconFg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={IcoStroke}>{iconPath}</svg></span>
      <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{title}</span>
      {right}
      <span onClick={onClose} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1, padding: 4 }}>✕</span>
    </div>
  )

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Операции</title></Head>
        <Navbar active="operations" />
        <OperationsMobile
          total={total} rows={rows} loading={loading} articles={articles} counterparties={counterparties} canEdit={canEdit}
          dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
          fStatus={fStatus} setFStatus={setFStatus} fBank={fBank} setFBank={setFBank}
          fArticle={fArticle} setFArticle={setFArticle} fCp={fCp} setFCp={setFCp} fOpType={fOpType} setFOpType={setFOpType}
          fPeriod={fPeriod} setFPeriod={setFPeriod} periodOptions={periodOptions}
          resetFilters={resetFilters} pageSize={pageSize} setPageSize={setPageSize}
          onSave={mobileSave} onDelete={mobileDelete} downloadExport={downloadExport} emptyForm={emptyForm} />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head>
        <title>Операции</title>
      </Head>
      <Navbar active="operations" />
      <style>{`
        @keyframes opRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        .op-row:hover { background: var(--bg-subtle) !important; }
        .op-ico { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:7px; cursor:pointer; }
        .op-ico:hover { background: var(--accent-tint); color: var(--accent) !important; }
        .op-ico-w:hover { background: var(--warning-tint); color: #B26A0C !important; }
        .op-ico-d:hover { background: var(--danger-tint); color: #C93A3E !important; }
        @media (prefers-reduced-motion: reduce){ [style*="animation"]{ animation:none !important } }
      `}</style>

      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', margin: 0, color: 'var(--text-primary)' }}>Операции</h1>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{new Intl.NumberFormat('ru-RU').format(total)} записей{updatedAt ? ` · обновлено ${updatedAt}` : ''}</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {canEdit && <button onClick={() => setCreateOpen(o => !o)} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Новая операция</button>}
            {canEdit && <button onClick={downloadTemplate} style={{ background: 'var(--bg-card)', color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: 12, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Шаблон</button>}
            {canImport && <IconBtn title="Импорт из файла" onClick={() => router.push('/finance/import')}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 15V3" /><path d="M7 8l5-5 5 5" /><path d="M5 21h14" /></svg></IconBtn>}
            <IconBtn title="Выгрузить в Excel (с учётом фильтров)" onClick={downloadExport}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg></IconBtn>
          </div>
        </div>

        {/* Форма создания */}
        {createOpen && canEdit && (
          <div style={{ ...CARD, position: 'relative', zIndex: 30, border: '1px solid #D7DEFA', boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 28px rgba(79,108,230,.10)', animation: 'opRise .28s cubic-bezier(0.22,1,0.36,1) both' }}>
            <HeadCard title="Новая операция" iconBg="var(--accent-tint)" iconFg="var(--accent)" iconPath={<><path d="M12 5v14" /><path d="M5 12h14" /></>} onClose={() => setCreateOpen(false)} />
            <div style={{ padding: '20px 24px' }}><OpFields f={createForm} set={p => setCreateForm(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} mode="create"
              files={pendingAsFiles} busyFiles={filesBusy}
              onAttach={list => setNewFiles(prev => [...prev, ...list])}
              onRemoveFile={(fl, i) => setNewFiles(prev => prev.filter((_, k) => k !== i))} /></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px', background: '#FBFCFE', borderTop: '1px solid var(--border-inner)' }}>
              <button onClick={saveCreate} disabled={saving} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Добавить операцию</button>
              <button onClick={() => setCreateOpen(false)} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '9px 16px', fontSize: 13, cursor: 'pointer' }}>Отмена</button>
              <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-faint)' }}>сумма НДС считается автоматически по ставке · обязательны статус, дата, банк, статья, сумма</span>
            </div>
          </div>
        )}

        {/* Карточка таблицы */}
        <div style={{ ...CARD, padding: '18px 24px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* строка фильтров */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--border-card)', borderRadius: 10, padding: '7px 10px', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
              <input type="month" value={dateFrom.slice(0, 7)} onChange={e => setDateFrom(e.target.value ? e.target.value + '-01' : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
              <span style={{ color: '#C3C9D8' }}>—</span>
              <input type="month" value={dateTo.slice(0, 7)} onChange={e => setDateTo(e.target.value ? e.target.value + '-28' : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
            </span>
            <MultiDrop label="Статус" options={STATUSES.map(s => ({ value: s, label: s }))} selected={fStatus} onChange={setFStatus} />
            <MultiDrop label="Банк" options={BANKS.map(b => ({ value: b, label: b }))} selected={fBank} onChange={setFBank} />
            <MultiDrop label="Статья" options={articles.map(a => ({ value: a.id, label: a.name }))} selected={fArticle} onChange={setFArticle} />
            <MultiDrop label="Контрагент" options={counterparties.map(c => ({ value: c.id, label: c.name }))} selected={fCp} onChange={setFCp} />
            <MultiDrop label="Период" options={periodOptions.map(p => ({ value: p, label: p }))} selected={fPeriod} onChange={setFPeriod} />
            <MultiDrop label="Тип операции" options={[{ value: 'income', label: 'Поступления' }, { value: 'expense', label: 'Списания' }]} selected={fOpType} onChange={setFOpType} />
            <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={fGaps} onChange={v => { setFGaps(v); setPage(0) }} />
            {focusOp && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 11px', borderRadius: 20, background: 'var(--accent-tint)', color: 'var(--accent)', fontSize: 12 }}>
                Показана одна операция #{focusOp}
                <span onClick={() => router.push('/finance/operations')}
                  style={{ cursor: 'pointer', textDecoration: 'underline' }}>показать все</span>
              </div>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, position: 'relative' }}>
              <IconBtn title="Сбросить фильтры" onClick={resetFilters}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
              <IconBtn title="Настройка колонок" active={colPicker} onClick={() => setColPicker(o => !o)}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></svg></IconBtn>
              {colPicker && (<>
                <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setColPicker(false)} />
                <div style={{ position: 'absolute', right: 0, top: '120%', zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, minWidth: 200, maxHeight: 340, overflowY: 'auto' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Колонки</div>
                  {COLS.filter(([k]) => k !== 'sel' && k !== 'actions').map(([k, , label]) => (
                    <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 2px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggleCol(k)} /> {label || k}
                    </label>
                  ))}
                </div>
              </>)}
            </div>
          </div>

          {/* Массовая правка — всплывашкой, закреплённой под шапкой: выделять строки
              можно в любом месте списка, и панель не уезжает вместе с ним. В потоке
              страницы она оставалась у начала таблицы, то есть за экраном. */}
          {canEdit && selIds.length > 0 && (
              <div style={{ position: 'fixed', top: navH + 10, left: 24, right: 24, zIndex: 45, boxShadow: '0 10px 34px rgba(28,36,51,.16)', background: '#F6F8FF', border: '1px solid #D7DEFA', borderRadius: 14, padding: '16px 18px', display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap', animation: 'opRise .24s cubic-bezier(0.22,1,0.36,1) both' }}>
                <div style={{ minWidth: 150, borderRight: '1px solid #DDE3F5', paddingRight: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#3A50BE', marginBottom: 6 }}>Выбрано: {selIds.length}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--income)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)' }} />+{fmt2(selIncome)} ₽</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--text-primary)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: T.expense }} />−{fmt2(selExpense)} ₽</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, fontWeight: 700, marginTop: 4, paddingTop: 4, borderTop: '1px solid #DDE3F5', color: (selIncome - selExpense) >= 0 ? 'var(--income)' : T.danger }}><span style={{ width: 6, height: 6, borderRadius: 2, background: (selIncome - selExpense) >= 0 ? 'var(--income)' : T.danger }} />{(selIncome - selExpense) >= 0 ? '+' : '−'}{fmt2(Math.abs(selIncome - selExpense))} ₽</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', width: 148, flexShrink: 0 }}>
                  <span style={lbl}>Дата</span>
                  <input type="date" value={bulk.date} onChange={e => setBulk(b => ({ ...b, date: e.target.value }))} style={{ ...inp, width: '100%' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', width: 300, flexShrink: 0 }}>
                  <span style={lbl}>Период</span>
                  <PeriodSelect dense value={bulk.period} onChange={v => setBulk(b => ({ ...b, period: v }))} />
                </div>
                {[['Статус', 'status', STATUSES.map(s => ({ value: s, label: s })), 150], ['Банк', 'bank', BANKS.map(b => ({ value: b, label: b })), 140], ['НДС', 'vat_rate', VAT_OPTIONS.map(v => ({ value: v, label: v + '%' })), 112], ['Статья', 'article_id', articles.map(a => ({ value: a.id, label: a.name })), 160], ['Контрагент', 'counterparty_id', counterparties.map(c => ({ value: c.id, label: c.name })), 190]].map(([label, k, opts, w]) => (
                  <div key={k} style={{ display: 'flex', flexDirection: 'column', width: w, flexShrink: 0 }}>
                    <span style={lbl}>{label}</span>
                    {(k === 'article_id' || k === 'counterparty_id')
                      ? <SingleSelect value={bulk[k]} onChange={v => setBulk(b => ({ ...b, [k]: v }))} options={opts} placeholder="не менять" emptyLabel="не менять" />
                      : <select value={bulk[k]} onChange={e => setBulk(b => ({ ...b, [k]: e.target.value }))} style={{ ...inp, width: '100%' }}><option value="">не менять</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>}
                  </div>
                ))}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                  <button onClick={applyBulk} disabled={saving} style={{ height: 38, boxSizing: 'border-box', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '0 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}>Применить к {selIds.length}</button>
                  <button onClick={delBulk} disabled={saving} title={`Удалить ${selIds.length}`} aria-label="Удалить" style={{ width: 38, height: 38, flexShrink: 0, background: 'var(--bg-card)', border: '1px solid #F3C9CC', color: T.danger, borderRadius: 10, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg></button>
                  <button onClick={() => setSel({})} title="Снять выделение" aria-label="Снять выделение" style={{ width: 38, height: 38, flexShrink: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg></button>
                </div>
              </div>
          )}

          {/* показано + пагинация */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
            <span>Показано <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{total ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, total)}</b> из <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{new Intl.NumberFormat('ru-RU').format(total)}</b></span>
            <span style={{ display: 'inline-flex', gap: 14 }}>
              {[['оплачено', 'var(--income)'], ['план оплат', 'var(--dot-expense)'], ['ожидает', 'var(--dot-current-dz)']].map(([l, c]) => <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>)}
            </span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, alignItems: 'center' }}>
              <IconBtn title="В начало" onClick={() => setPage(0)}>«</IconBtn>
              <IconBtn title="Назад" onClick={() => setPage(p => Math.max(0, p - 1))}>‹</IconBtn>
              <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', padding: '0 6px' }}>{page + 1} / {totalPages}</span>
              <IconBtn title="Вперёд" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}>›</IconBtn>
              <IconBtn title="В конец" onClick={() => setPage(totalPages - 1)}>»</IconBtn>
            </div>
          </div>

          {/* таблица */}
          <div style={{ overflowX: 'auto', margin: '10px -8px 0', padding: '0 8px' }}>
            <div style={{ minWidth: 1580 }}>
              <div style={{ display: 'grid', gridTemplateColumns: gridT, gap: 10, padding: '0 0 10px', borderBottom: '1px solid var(--border-card)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                {visibleCols.map(([k, w, label, sc]) => k === 'sel'
                  ? <span key={k}><input type="checkbox" ref={el => { if (el) el.indeterminate = someOnPage && !allOnPage }} checked={allOnPage} onChange={e => setSel(e.target.checked ? Object.fromEntries(rows.map(o => [o.id, true])) : {})} style={{ width: 14, height: 14, cursor: 'pointer' }} /></span>
                  : <span key={k} onClick={() => onSort(sc)} style={{ textAlign: RIGHT.has(k) ? 'right' : 'left', cursor: sc ? 'pointer' : 'default', color: sortCol === sc ? 'var(--accent)' : undefined }}>{label}{sortCol === sc ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}</span>)}
              </div>
              {loading ? <div style={{ padding: 30, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
                : rows.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет операций по выбранным фильтрам</div>
                  : rows.map(o => (
                    <Fragment key={o.id}>
                      <div className="op-row" style={{ display: 'grid', gridTemplateColumns: gridT, gap: 10, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', fontSize: 14.4, color: 'var(--text-primary)', background: sel[o.id] ? 'var(--accent-tint)' : (editing?.id === o.id ? 'var(--warning-tint)' : 'transparent') }}>
                        {visibleCols.map(([k]) => <span key={k} style={{ textAlign: RIGHT.has(k) ? 'right' : 'left', overflow: 'hidden' }}>{cell(o, k)}</span>)}
                      </div>
                      {/* Правка раскрывается под своей строкой — форма стоит там, где
                          пользователь только что кликнул, и список не теряет место. */}
                      {editing?.id === o.id && canEdit && (
                        <div style={{ background: '#FFFCF7', border: '1px solid #F0D7AE', borderRadius: 14, padding: '18px 20px', margin: '2px 0 10px', animation: 'opRise .24s cubic-bezier(0.22,1,0.36,1) both' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                            <span style={{ width: 28, height: 28, borderRadius: 9, background: 'var(--warning-tint)', color: T.warningText, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>
                            <span style={{ fontSize: 15, fontWeight: 700, flex: 1 }}>Редактирование #{editing.id}</span>
                            <span onClick={() => setEditing(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>✕</span>
                          </div>
                          <OpFields f={editing} set={p => setEditing(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} accent="warn"
                            files={editFiles} busyFiles={filesBusy}
                            onAttach={list => attachToExisting(editing.id, list)}
                            onRemoveFile={fl => removeFromExisting(editing.id, fl)} />
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14 }}>
                            <span style={{ fontSize: 12, color: 'var(--text-faint)', flex: 1 }}>поля, отмеченные «необяз.», можно оставить пустыми</span>
                            <button onClick={saveEdit} disabled={saving} style={{ background: 'var(--dot-current-dz)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Сохранить изменения</button>
                            <button onClick={() => setEditing(null)} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 16px', fontSize: 13, cursor: 'pointer' }}>Отмена</button>
                          </div>
                        </div>
                      )}
                    </Fragment>
                  ))}
            </div>
          </div>

          {/* подвал */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', paddingTop: 14, marginTop: 6, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
            <span>выделено <b style={{ color: 'var(--text-primary)' }}>{selIds.length}</b> операций</span>
            <span>итого на странице: поступления <b style={{ color: 'var(--income)', fontFamily: MONO }}>{fmt(pageIncome)} ₽</b> · списания <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{fmt(pageExpense)} ₽</b></span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
              <span>строк на странице</span>
              <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
                {PAGE_SIZES.map(n => <button key={n} onClick={() => { setPageSize(n); setPage(0) }} style={{ border: 'none', borderRadius: 8, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, background: pageSize === n ? 'var(--accent-tint)' : 'transparent', color: pageSize === n ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: pageSize === n ? 700 : 600 }}>{n}</button>)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
