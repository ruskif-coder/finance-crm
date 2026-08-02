import { useState, useEffect } from 'react'
import { MONO, UI, MultiDrop } from '../salesTableKit'
import { grp, signRub, fmtDateShort, bankColor } from '../../lib/salesFormat'
import { CARD, monoLbl, Marker } from './kit'
import BottomSheet from './BottomSheet'

const fmt = (n) => grp(Math.abs(n || 0))

const MONTH_UP = ['', 'ЯНВАРЬ', 'ФЕВРАЛЬ', 'МАРТ', 'АПРЕЛЬ', 'МАЙ', 'ИЮНЬ', 'ИЮЛЬ', 'АВГУСТ', 'СЕНТЯБРЬ', 'ОКТЯБРЬ', 'НОЯБРЬ', 'ДЕКАБРЬ']
const fmtPeriodGroup = (p) => { if (!p) return 'БЕЗ ПЕРИОДА'; const m = String(p).match(/^(\d{4})-(\d{2})$/); if (m) return `${MONTH_UP[+m[2]] || m[2]} ${m[1]}`; return String(p).toUpperCase() }

const STATUSES = ['ОПЛАЧЕНО', 'ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const VAT_OPTIONS = [0, 5, 7, 10, 20, 22]

const STATUS_META = {
  'ОПЛАЧЕНО': { label: 'исполнено', bg: '#E6F5EF', fg: '#1F7D5E', dot: '#2FA37C' },
  'ПЛАН ОПЛАТ': { label: 'план оплат', bg: '#ECEFFD', fg: '#4F6CE6', dot: '#4F6CE6' },
  'ПЛАН ПОСТУПЛЕНИЙ': { label: 'план поступл.', bg: '#FBF0DE', fg: '#B26A0C', dot: '#E89020' },
}
const statusMeta = (s) => STATUS_META[s] || { label: (s || '').toLowerCase(), bg: 'var(--bg-subtle)', fg: 'var(--text-secondary)', dot: 'var(--text-faint)' }

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

function DocIco() { return <svg width="13" height="13" viewBox="0 0 24 24" style={stroke}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg> }
function EditIco() { return <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg> }

// ── Карточка операции (аккордеон) ──
function OpCard({ o, artName, cpName, open, onToggle, onEdit, onCopy }) {
  const st = statusMeta(o.status)
  const isIncome = (o.income || 0) > 0
  const amount = isIncome ? o.income : -(o.expense || 0)
  return (
    <div style={{ ...CARD, padding: '13px 14px', fontFamily: UI }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {/* строка 1: банк + статус */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            <Marker c={bankColor(o.bank)} />
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.bank || 'не указан'}</span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {o.document_link && <span style={{ width: 22, height: 22, borderRadius: 6, background: 'var(--accent-tint)', color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><DocIco /></span>}
            <span style={{ background: st.bg, color: st.fg, borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{st.label}</span>
          </span>
        </div>
        {/* строка 2: контрагент + сумма */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cpName[o.counterparty_id] || o.counterparty || '—'}</span>
          <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: isIncome ? 'var(--income)' : 'var(--text-primary)', whiteSpace: 'nowrap' }}>{signRub(amount)}</span>
        </div>
        {/* строка 3: статья + дата */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{artName[o.article_id] || o.article || '—'}</span>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{fmtDateShort(o.date)}</span>
        </div>
      </div>
      {open && (
        <div style={{ animation: 'opRise .24s ease both' }}>
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-row)', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 10px', fontSize: 12.5 }}>
            <span style={{ color: 'var(--text-muted)' }}>НДС</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', fontFamily: MONO }}>{o.vat_rate ? `${o.vat_rate}% · ${fmt(o.vat_amount || 0)} ₽` : '—'}</span>
            <span style={{ color: 'var(--text-muted)' }}>№ счёта</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', fontFamily: MONO }}>{o.invoice || '—'}</span>
            <span style={{ color: 'var(--text-muted)' }}>Доп. соглашение</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', fontFamily: MONO }}>{o.ds_num || '—'}</span>
            <span style={{ color: 'var(--text-muted)' }}>Описание</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-word' }}>{o.description || '—'}</span>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={() => onEdit(o)} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Редактировать</button>
            <button onClick={() => onCopy(o)} aria-label="Копировать" title="Копировать в новую операцию" style={{ width: 46, height: 44, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
            </button>
            {o.document_link
              ? <a href={o.document_link} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} aria-label="Документ" style={{ width: 46, height: 44, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg></a>
              : <span style={{ width: 46, height: 44, borderRadius: 12, border: '1px dashed var(--border-card)', color: 'var(--text-faint)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>—</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Форма операции (создание/редактирование) — полноэкранная ──
function OperationForm({ initial, editId, articles, counterparties, onClose, onSave, onDelete }) {
  const [f, setF] = useState(initial)
  const [saving, setSaving] = useState(false)
  const set = (p) => setF(s => ({ ...s, ...p }))
  const amount = (f.income || 0) > 0 ? f.income : (f.expense || 0)
  const vatAmount = f.vat_rate ? Math.round(amount * f.vat_rate / (100 + f.vat_rate)) : 0

  const setAmount = (v) => {
    const n = +String(v).replace(/\D/g, '') || 0
    if (f.status === 'ПЛАН ПОСТУПЛЕНИЙ') set({ income: n, expense: 0 })
    else if (f.status === 'ПЛАН ОПЛАТ') set({ expense: n, income: 0 })
    else { if ((f.expense || 0) > 0) set({ expense: n, income: 0 }); else set({ income: n, expense: 0 }) }
  }
  const setStatus = (s) => {
    if (s === 'ПЛАН ПОСТУПЛЕНИЙ') set({ status: s, income: amount, expense: 0 })
    else if (s === 'ПЛАН ОПЛАТ') set({ status: s, expense: amount, income: 0 })
    else set({ status: s })
  }

  const TILES = [
    { s: 'ПЛАН ОПЛАТ', l1: 'План', l2: 'оплат', dot: '#4F6CE6' },
    { s: 'ПЛАН ПОСТУПЛЕНИЙ', l1: 'План', l2: 'поступлений', dot: '#E89020' },
    { s: 'ОПЛАЧЕНО', l1: 'Испол-', l2: 'нено', dot: '#2FA37C' },
  ]
  const fieldRow = { display: 'flex', alignItems: 'center', gap: 10, minHeight: 42, borderBottom: '1px solid var(--border-row)', padding: '4px 0' }
  const flbl = { fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', flex: '0 0 auto' }
  const fval = { flex: 1, minWidth: 0, textAlign: 'right', border: 'none', outline: 'none', background: 'transparent', fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }
  const selVal = { ...fval, appearance: 'none', cursor: 'pointer', direction: 'rtl' }

  const save = async () => {
    setSaving(true)
    const body = { date: f.date || null, status: f.status, income: f.income || 0, expense: f.expense || 0, bank: f.bank || '', period: f.period || '', vat_rate: f.vat_rate || 0, article_id: f.article_id || null, counterparty_id: f.counterparty_id || null, ds_num: f.ds_num || '', invoice: f.invoice || '', invoice_date: f.invoice_date || '', description: f.description || '', document_link: f.document_link || '' }
    const ok = await onSave(body, editId)
    setSaving(false)
    if (ok !== false) onClose()
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 500, background: 'var(--bg-canvas)', overflowY: 'auto', fontFamily: UI, paddingBottom: 96 }}>
      {/* шапка */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-inner)', position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 3 }}>
        <button onClick={onClose} aria-label="Закрыть" style={{ width: 32, height: 32, borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>✕</button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{editId ? `Операция #${editId}` : 'Новая операция'}</div>
          <div style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{editId ? 'редактирование' : 'черновик не сохранён'}</div>
        </div>
      </div>

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* статус — 3 плитки */}
        <div>
          <div style={{ ...monoLbl, marginBottom: 8 }}>Статус операции</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            {TILES.map(t => {
              const on = f.status === t.s
              return (
                <button key={t.s} onClick={() => setStatus(t.s)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '12px 4px', borderRadius: 12, cursor: 'pointer', border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`, background: on ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
                  <Marker c={t.dot} />
                  <span style={{ fontSize: 12.5, fontWeight: on ? 700 : 600, color: on ? 'var(--accent)' : 'var(--text-secondary)', textAlign: 'center', lineHeight: 1.15 }}>{t.l1}<br />{t.l2}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* сумма */}
        <div style={{ ...fieldRow }}>
          <span style={flbl}>Сумма</span>
          <input inputMode="numeric" value={amount ? fmt(amount) : ''} onChange={e => setAmount(e.target.value)} placeholder="0 ₽" style={{ ...fval, fontSize: 17 }} />
        </div>

        {/* НДС пара */}
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0, ...fieldRow, borderBottom: '1px solid var(--border-row)' }}>
            <span style={flbl}>Ставка НДС</span>
            <select value={f.vat_rate} onChange={e => set({ vat_rate: +e.target.value })} style={selVal}>{VAT_OPTIONS.map(v => <option key={v} value={v}>{v}%</option>)}</select>
          </div>
          <div style={{ flex: 1, minWidth: 0, ...fieldRow }}>
            <span style={flbl}>НДС ₽</span>
            <span style={{ ...fval, color: 'var(--text-muted)' }}>{fmt(vatAmount)}</span>
          </div>
        </div>

        {/* строки-поля */}
        <div>
          <div style={fieldRow}><span style={flbl}>Дата</span><input type="date" value={f.date || ''} onChange={e => set({ date: e.target.value })} style={{ ...fval, direction: 'rtl' }} /></div>
          <div style={fieldRow}><span style={flbl}>Банк</span><select value={f.bank || ''} onChange={e => set({ bank: e.target.value })} style={selVal}><option value="">не выбран</option>{BANKS.map(b => <option key={b} value={b}>{b}</option>)}</select></div>
          <div style={fieldRow}><span style={flbl}>Период</span><input type="month" value={/^\d{4}-\d{2}$/.test(f.period || '') ? f.period : ''} onChange={e => set({ period: e.target.value })} style={{ ...fval, direction: 'rtl' }} /></div>
          <div style={fieldRow}><span style={flbl}>Статья</span><select value={f.article_id || ''} onChange={e => set({ article_id: e.target.value })} style={selVal}><option value="">не выбрана</option>{articles.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
          <div style={fieldRow}><span style={flbl}>Контрагент</span><select value={f.counterparty_id || ''} onChange={e => set({ counterparty_id: e.target.value })} style={selVal}><option value="">не выбран</option>{counterparties.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div style={fieldRow}><span style={flbl}>№ счёта</span><input value={f.invoice || ''} onChange={e => set({ invoice: e.target.value })} placeholder="не указан" style={fval} /></div>
          <div style={fieldRow}><span style={flbl}>Доп. соглашение</span><input value={f.ds_num || ''} onChange={e => set({ ds_num: e.target.value })} placeholder="нет" style={fval} /></div>
        </div>

        {/* документ + комментарий */}
        <input value={f.document_link || ''} onChange={e => set({ document_link: e.target.value })} placeholder="ссылка на документ" style={{ width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 13, fontFamily: UI, outline: 'none', color: 'var(--text-secondary)' }} />
        <textarea value={f.description || ''} onChange={e => set({ description: e.target.value })} placeholder="комментарий к операции" style={{ width: '100%', boxSizing: 'border-box', minHeight: 60, resize: 'vertical', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 13, fontFamily: UI, outline: 'none', color: 'var(--text-secondary)', lineHeight: 1.4 }} />
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Статус задаёт колонку: план оплат и исполненное списание — в расход, план поступлений и исполненный приход — в приход. Сумма НДС считается автоматически.</div>
      </div>

      {/* липкий подвал */}
      <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 14px', background: 'var(--bg-card)', borderTop: '1px solid var(--border-inner)', display: 'flex', gap: 8, alignItems: 'center' }}>
        <button onClick={save} disabled={saving} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : editId ? 'Сохранить' : 'Добавить операцию'}</button>
        {editId
          ? <button onClick={async () => { if (window.confirm('Удалить операцию?')) { await onDelete(editId); onClose() } }} aria-label="Удалить" style={{ width: 52, borderRadius: 12, border: '1px solid #F3C9CC', background: 'var(--bg-card)', color: '#C93A3E', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg></button>
          : <button onClick={onClose} style={{ flex: '0 0 auto', padding: '14px 18px', borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>Отмена</button>}
      </div>
    </div>
  )
}

const FILTER_DROPS = [
  ['status', 'Статус', STATUSES.map(s => ({ value: s, label: s }))],
  ['bank', 'Банк', BANKS.map(b => ({ value: b, label: b }))],
  ['optype', 'Тип', [{ value: 'income', label: 'Поступления' }, { value: 'expense', label: 'Списания' }]],
]

export default function OperationsMobile({
  total, rows, loading, articles, counterparties, canEdit,
  dateFrom, setDateFrom, dateTo, setDateTo, fStatus, setFStatus, fBank, setFBank,
  fArticle, setFArticle, fCp, setFCp, fOpType, setFOpType, resetFilters,
  pageSize, setPageSize, onSave, onDelete, downloadExport, emptyForm,
}) {
  const [expandedId, setExpandedId] = useState(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(null)   // { initial, editId } | null
  useEffect(() => { if (pageSize > 100) setPageSize(100) }, [])   // мобиль: меньшая начальная загрузка + «Показать ещё»

  const artName = Object.fromEntries(articles.map(a => [a.id, a.name]))
  const cpName = Object.fromEntries(counterparties.map(c => [c.id, c.name]))
  const activeFilterCount = fStatus.length + fBank.length + fArticle.length + fCp.length + fOpType.length + ((dateFrom || dateTo) ? 1 : 0)

  // клиентский поиск по загруженной странице
  const q = search.trim().toLowerCase()
  const shown = q ? rows.filter(o => [cpName[o.counterparty_id], o.counterparty, artName[o.article_id], o.article, o.description, o.invoice].some(v => String(v || '').toLowerCase().includes(q))) : rows

  // группировка по периоду (сохраняя порядок появления — бэк уже сортирует по дате)
  const groups = []
  const gmap = {}
  shown.forEach(o => {
    const key = o.period || '—'
    if (!gmap[key]) { gmap[key] = { key, ops: [], turnover: 0 }; groups.push(gmap[key]) }
    gmap[key].ops.push(o); gmap[key].turnover += (o.income || 0) + (o.expense || 0)
  })

  const opToForm = (o) => ({ date: o.date || '', status: o.status || 'ОПЛАЧЕНО', income: o.income || 0, expense: o.expense || 0, bank: o.bank || '', period: o.period || '', vat_rate: o.vat_rate || 0, article_id: o.article_id || '', counterparty_id: o.counterparty_id || '', ds_num: o.ds_num || '', invoice: o.invoice || '', invoice_date: o.invoice_date || '', description: o.description || '', document_link: o.document_link || '' })
  const openEdit = (o) => setForm({ editId: o.id, initial: opToForm(o) })
  const openCopy = (o) => setForm({ editId: null, initial: opToForm(o) })   // копия → «Новая операция» с данными (POST при сохранении)
  const openCreate = () => setForm({ editId: null, initial: emptyForm() })

  const seg = (active) => ({ border: 'none', borderRadius: 8, padding: '6px 12px', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 12, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, paddingBottom: 90 }}>
      <style>{`@keyframes opRise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@media (prefers-reduced-motion:reduce){[style*="animation"]{animation:none!important}}`}</style>

      {/* тулбар */}
      {searchOpen ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--accent)', background: 'var(--bg-card)', borderRadius: 12, padding: '10px 12px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" style={{ ...stroke, color: 'var(--text-faint)' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
            <input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder="контрагент, статья, назначение…" style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, color: 'var(--text-secondary)', fontFamily: UI }} />
            {search && <span onClick={() => setSearch('')} style={{ color: 'var(--text-faint)', cursor: 'pointer', fontSize: 16 }}>✕</span>}
          </div>
          <button onClick={() => setSearchOpen(false)} style={{ border: 'none', background: 'transparent', color: 'var(--accent)', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Готово</button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 19, fontWeight: 700, color: 'var(--text-primary)' }}>Операции</span>
          <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{new Intl.NumberFormat('ru-RU').format(total)}</span>
          <div style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => setSearchOpen(true)} aria-label="Поиск" style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${search ? 'var(--accent)' : 'var(--border-card)'}`, background: search ? 'var(--accent-tint)' : 'var(--bg-card)', color: search ? 'var(--accent)' : 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
            </button>
            <button onClick={() => setFiltersOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${activeFilterCount > 0 ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '0 13px', height: 40, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" style={stroke}><path d="M3 5h18M6 12h12M10 19h4" /></svg>
              Фильтры{activeFilterCount > 0 && <span style={{ background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 8, padding: '0 6px', fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{activeFilterCount}</span>}
            </button>
            <button onClick={downloadExport} aria-label="Выгрузить" style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
            </button>
          </div>
        </div>
      )}

      {/* список по группам */}
      {loading && !rows.length ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
        : groups.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет операций по фильтрам</div>
          : groups.map(g => (
            <div key={g.key} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '2px 4px' }}>
                <span style={{ ...monoLbl, fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700 }}>{fmtPeriodGroup(g.key)}</span>
                <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{g.ops.length} оп. · {fmt(g.turnover)} ₽</span>
              </div>
              {g.ops.map(o => (
                <OpCard key={o.id} o={o} artName={artName} cpName={cpName} open={expandedId === o.id}
                  onToggle={() => setExpandedId(id => id === o.id ? null : o.id)} onEdit={openEdit} onCopy={openCopy} />
              ))}
            </div>
          ))}

      {/* показать ещё */}
      {rows.length < total && (
        <button onClick={() => setPageSize(p => (p < 100 ? 100 : p < 300 ? 300 : p < 500 ? 500 : p + 500))} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '13px', fontSize: 13, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer', fontFamily: UI }}>Показать ещё · {rows.length} из {new Intl.NumberFormat('ru-RU').format(total)}</button>
      )}

      {/* плавающая кнопка + */}
      {canEdit && (
        <button onClick={openCreate} aria-label="Новая операция" style={{ position: 'fixed', right: 18, bottom: 18, width: 56, height: 56, borderRadius: 18, background: 'var(--accent)', color: '#fff', border: 'none', boxShadow: '0 6px 20px rgba(79,108,230,.4)', fontSize: 30, lineHeight: 1, cursor: 'pointer', zIndex: 200 }}>+</button>
      )}

      {/* шторка фильтров */}
      <BottomSheet open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Фильтры"
        footer={<button onClick={() => setFiltersOpen(false)} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>Показать {new Intl.NumberFormat('ru-RU').format(total)}</button>}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{activeFilterCount > 0 ? `выбрано ${activeFilterCount}` : 'фильтры не заданы'}</span>
          <span onClick={resetFilters} style={{ fontSize: 13, fontWeight: 600, color: activeFilterCount > 0 ? 'var(--accent)' : 'var(--text-faint)', cursor: 'pointer' }}>Сбросить</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <input type="month" value={dateFrom.slice(0, 7)} onChange={e => setDateFrom(e.target.value ? e.target.value + '-01' : '')} style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', fontSize: 13, fontFamily: MONO, outline: 'none' }} />
          <span style={{ color: 'var(--text-faint)' }}>—</span>
          <input type="month" value={dateTo.slice(0, 7)} onChange={e => setDateTo(e.target.value ? e.target.value + '-28' : '')} style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', fontSize: 13, fontFamily: MONO, outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <MultiDrop label="Статус" options={STATUSES.map(s => ({ value: s, label: s }))} selected={fStatus} onChange={setFStatus} block />
          <MultiDrop label="Банк" options={BANKS.map(b => ({ value: b, label: b }))} selected={fBank} onChange={setFBank} block />
          <MultiDrop label="Статья" options={articles.map(a => ({ value: a.id, label: a.name }))} selected={fArticle} onChange={setFArticle} block />
          <MultiDrop label="Контрагент" options={counterparties.map(c => ({ value: c.id, label: c.name }))} selected={fCp} onChange={setFCp} block />
          <MultiDrop label="Тип" options={[{ value: 'income', label: 'Поступления' }, { value: 'expense', label: 'Списания' }]} selected={fOpType} onChange={setFOpType} block />
        </div>
      </BottomSheet>

      {/* форма создания/редактирования */}
      {form && (
        <OperationForm initial={form.initial} editId={form.editId} articles={articles} counterparties={counterparties}
          onClose={() => setForm(null)} onSave={onSave} onDelete={onDelete} />
      )}
    </div>
  )
}
