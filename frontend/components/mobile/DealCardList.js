import { useState, useEffect } from 'react'
import { MONO, UI, PIP, FILL, shortLabel } from '../salesTableKit'
import { grp } from '../../lib/salesFormat'
import { T } from '../../lib/tokens'
import { CARD, PeriodSelect } from './kit'
import DealBriefCell from '../DealBriefCell'

const rub = grp
// Деньги: млн (2 знака) / тыс / рубли — как в макете (2,10 млн ₽ · 500 тыс ₽)
const money = (n) => {
  if (n == null || n === '') return '—'
  const a = Math.abs(n)
  if (a >= 1e6) return (n / 1e6).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' млн'
  if (a >= 1e3) return Math.round(n / 1e3).toLocaleString('ru-RU') + ' тыс'
  return rub(n)
}
const amountOf = (d) => (d.amount_with_vat != null ? d.amount_with_vat : d.amount)

// money_layer → чип статуса (метка + цвет + фон)
const LAYER_CHIP = {
  'фактические': ['Фактические', '#1F7D5E', '#E6F5EF'],
  'реализуемые': ['Реализуется', T.warningText, 'var(--warning-tint)'],
  'планируемые': ['Планируется', 'var(--text-secondary)', 'var(--bg-subtle)'],
}
function StatusChip({ layer, stage }) {
  // если у сделки есть человекочитаемая стадия — показываем её, иначе слой денег
  const c = LAYER_CHIP[layer]
  const label = stage || (c ? c[0] : null)
  if (!label) return null
  const col = c ? c[1] : 'var(--text-secondary)'
  const bg = c ? c[2] : 'var(--bg-subtle)'
  return <span style={{ fontSize: 11, fontWeight: 700, color: col, background: bg, borderRadius: 8, padding: '3px 9px', whiteSpace: 'nowrap' }}>{label}</span>
}
function LayerStrip({ layer }) {
  const n = FILL[layer] || 0
  return (
    <span style={{ display: 'inline-flex', gap: 3 }}>
      {PIP.map((c, i) => <span key={i} style={{ width: 5, height: 9, borderRadius: 1, background: i < n ? c : 'var(--border-inner)' }} />)}
    </span>
  )
}

const HDR = { fontFamily: MONO, fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }

// поля-опции по имени → массив {value,label}
const optsFor = (field, fopts, d) => {
  if (field === 'product') return (fopts.product || []).map(o => ({ value: o.value, label: o.label || o.value }))
  if (field === 'payer_counterparty_id') return d.agency_legals || []
  return fopts[field] || []
}
const labelOf = (opts, v) => (opts || []).find(o => String(o.value) === String(v))?.label

const fieldStyle = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', appearance: 'auto' }

// ВНЕ компонента: если объявлять внутри, при каждом вводе символа функция получает
// новую идентичность → React ремоунтит <input> → поле теряет фокус после каждой буквы.
const EditField = ({ label, field, clear, type, form, setForm, fopts, d }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
    {type === 'text' ? (
      <input value={form[field]} onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))} style={fieldStyle} />
    ) : type === 'month' ? (
      <PeriodSelect value={form[field] || ''} onChange={v => setForm(f => ({ ...f, [field]: v }))} allowQuarter={false} />
    ) : (
      <select value={form[field] ?? ''} onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))} style={fieldStyle}>
        <option value="">{clear || '— не указано —'}</option>
        {optsFor(field, fopts, d).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    )}
  </div>
)

// ── Полноэкранная карточка сделки (§7 / макет 390px): шапка+табы, Обзор, Бриф, Оплаты + правка ──
function DealDetail({ deal, onClose, canEdit, fopts = {}, onPatch }) {
  const [tab, setTab] = useState('overview')
  const [d, setD] = useState(deal)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const local = String(d.bitrix_id || '').startsWith('local-')
  const TABS = [['overview', 'Обзор'], ['finance', 'Финансы'], ['docs', 'Документы'], ['history', 'История']]
  const withVat = d.amount_with_vat != null ? d.amount_with_vat : d.amount
  const layerLabel = (LAYER_CHIP[d.money_layer] || [])[0] || d.money_layer || '—'

  const mkForm = (x) => ({
    title: x.title || '', agency_id: x.agency_id ?? '', advertiser_id: x.advertiser_id ?? '',
    product: x.product ?? '', bitrix_stage: x.bitrix_stage ?? '', sales_rep_id: x.sales_rep_id ?? '',
    account_manager_id: x.account_manager_id ?? '', payer_counterparty_id: x.payer_counterparty_id ?? '', period: x.period ?? '',
  })
  const [form, setForm] = useState(mkForm(deal))
  const startEdit = () => { setForm(mkForm(d)); setEditing(true) }

  const save = async () => {
    const api = {}, merge = {}
    const eq = (a, b) => String(a ?? '') === String(b ?? '')
    if (!eq(form.title, d.title)) { api.title = form.title; merge.title = form.title }
    if (!eq(form.agency_id, d.agency_id)) { const v = form.agency_id || null; api.agency_id = v; merge.agency_id = v; merge.agency = v ? shortLabel(labelOf(fopts.agency_id, v)) : null }
    if (!eq(form.advertiser_id, d.advertiser_id)) { const v = form.advertiser_id || null; const l = labelOf(fopts.advertiser_id, v); api.advertiser_id = v; merge.advertiser_id = v; merge.advertiser = v ? shortLabel(l) : null; merge.advertiser_full = l || null }
    if (!eq(form.product, d.product)) { api.product = form.product || null; merge.product = form.product || null }
    if (!eq(form.bitrix_stage, d.bitrix_stage)) { api.bitrix_stage = form.bitrix_stage || null; merge.bitrix_stage = form.bitrix_stage || null }
    if (!eq(form.sales_rep_id, d.sales_rep_id)) { const v = form.sales_rep_id || null; api.sales_rep_id = v; merge.sales_rep_id = v; merge.sales_rep = v ? labelOf(fopts.sales_rep_id, v) : null }
    if (!eq(form.account_manager_id, d.account_manager_id)) { const v = form.account_manager_id || null; api.account_manager_id = v; merge.account_manager_id = v; merge.account_manager = v ? labelOf(fopts.account_manager_id, v) : null }
    if (!eq(form.payer_counterparty_id, d.payer_counterparty_id)) { const v = form.payer_counterparty_id || null; api.payer_counterparty_id = v; merge.payer_counterparty_id = v; merge.payer = v ? labelOf(d.agency_legals, v) : null }
    if (!eq(form.period, d.period)) { api.period_from = form.period ? `${form.period}-01` : null; merge.period = form.period || null }
    if (!Object.keys(api).length) { setEditing(false); return }
    setSaving(true)
    try {
      const ok = await onPatch?.(d.id, api, merge)
      if (ok === false) return          // ошибка сохранения — форму не закрываем (alert уже показан)
      setD(x => ({ ...x, ...merge })); setEditing(false)
    } finally { setSaving(false) }
  }

  const Row = ({ k, v, strong, last }) => (
    <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '12px 0', borderBottom: last ? 'none' : '1px solid var(--border-row)' }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)', flex: '0 0 38%' }}>{k}</span>
      <span style={{ fontSize: 13.5, fontWeight: strong ? 700 : 600, color: 'var(--text-primary)', flex: 1, textAlign: 'right', wordBreak: 'break-word', fontFamily: strong ? MONO : UI }}>{v ?? '—'}</span>
    </div>
  )
  const ef = { form, setForm, fopts, d }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 500, background: 'var(--bg-canvas)', overflowY: 'auto', fontFamily: UI, paddingBottom: 84 }}>
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* шапка + табы */}
        <div style={{ ...CARD, padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={onClose} aria-label="Назад" style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 18, lineHeight: 1, flexShrink: 0 }}>‹</button>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: local ? 'var(--text-faint)' : 'var(--accent)' }}>{local ? 'локально' : d.bitrix_id}</span>
            <StatusChip layer={d.money_layer} stage={d.bitrix_stage} />
            <span style={{ marginLeft: 'auto' }}><DealBriefCell deal={d} canEdit={canEdit} v2 /></span>
          </div>
          <div style={{ marginTop: 12, fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{d.advertiser || '—'}{d.brand ? ` · ${d.brand}` : ''}</div>
          <div style={{ marginTop: 3, fontSize: 12.5, color: 'var(--text-muted)' }}>{[d.product, d.period && `период ${d.period}`].filter(Boolean).join(' · ') || '—'}</div>
          <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <LayerStrip layer={d.money_layer} />
            <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-.02em', whiteSpace: 'nowrap' }}>{rub(withVat)} <span style={{ fontSize: 15, color: 'var(--text-faint)' }}>₽</span></span>
          </div>
          {!editing && (
          <div style={{ display: 'flex', gap: 6, marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border-row)', overflowX: 'auto' }}>
            {TABS.map(([id, label]) => (
              <button key={id} onClick={() => setTab(id)} style={{ flexShrink: 0, border: 'none', cursor: 'pointer', borderRadius: 10, padding: '8px 14px', fontSize: 13, fontWeight: tab === id ? 700 : 600, whiteSpace: 'nowrap', background: tab === id ? 'var(--accent-tint)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-secondary)' }}>{label}</button>
            ))}
          </div>
          )}
        </div>

        {/* режим правки */}
        {editing ? (
          <div style={{ ...CARD, padding: '16px', animation: 'sheetFade .2s ease both' }}>
            <div style={{ ...HDR, marginBottom: 14 }}>Редактирование сделки</div>
            <EditField {...ef} label="Название" field="title" type="text" />
            <EditField {...ef} label="Агентство" field="agency_id" clear="— прямой договор —" />
            <EditField {...ef} label="Рекламодатель" field="advertiser_id" clear="— не указан —" />
            <EditField {...ef} label="Плательщик" field="payer_counterparty_id" clear="— по умолчанию —" />
            <EditField {...ef} label="Услуга" field="product" clear="— не указана —" />
            <EditField {...ef} label="Стадия" field="bitrix_stage" clear="— не указана —" />
            <EditField {...ef} label="Продавец" field="sales_rep_id" clear="— не указан —" />
            <EditField {...ef} label="Аккаунт" field="account_manager_id" clear="— не указан —" />
            <EditField {...ef} label="Период (старт РК)" field="period" type="month" />
          </div>
        ) : (<>
        {tab === 'overview' && (
          <div key="ov" style={{ display: 'flex', flexDirection: 'column', gap: 12, animation: 'sheetFade .24s ease both' }}>
            {/* поля */}
            <div style={{ ...CARD, padding: '4px 16px 8px' }}>
              <Row k="Агентство" v={d.agency} />
              <Row k="Аккаунт" v={d.account_manager} />
              <Row k="Продавец" v={d.sales_rep} />
              <Row k="Плательщик" v={d.payer} />
              <Row k="Стадия" v={d.bitrix_stage} />
              <Row k="Название" v={d.title} />
              <Row k="Слой денег" v={layerLabel} strong />
              <Row k="Сумма с НДС" v={`${rub(withVat)} ₽`} strong />
              <Row k="Без НДС" v={`${rub(d.amount)} ₽`} strong />
              <Row k="Наша сумма" v={d.our_sum != null ? `${rub(d.our_sum)} ₽` : '—'} strong last />
            </div>
            {/* бриф */}
            <div style={{ ...CARD, padding: '14px 16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ ...HDR, flex: 1 }}>Бриф</span>
                <DealBriefCell deal={d} canEdit={canEdit} v2 />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--bg-subtle)', borderRadius: 12, padding: '10px 12px' }}>
                <span style={{ width: 34, height: 34, borderRadius: 9, background: 'var(--accent-tint)', color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 16 }}>▤</span>
                <span style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.brief_state === 'filled' ? 'Бриф заполнен' : 'Бриф'}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{d.brief_state === 'none' ? 'не подгружался' : d.brief_state === 'empty' ? 'пусто' : 'есть текст'}</div>
                </span>
              </div>
            </div>
            {/* оплаты */}
            <div style={{ ...CARD, padding: '14px 16px' }}>
              <div style={{ ...HDR, marginBottom: 10 }}>Оплаты</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Подключим из операций (связь сделка ↔ платёж) — следующий шаг.</div>
            </div>
          </div>
        )}
        {tab === 'finance' && (
          <div style={{ ...CARD, padding: '4px 16px 8px', animation: 'sheetFade .24s ease both' }}>
            <Row k="Сумма с НДС" v={`${rub(withVat)} ₽`} strong />
            <Row k="Без НДС" v={`${rub(d.amount)} ₽`} strong />
            <Row k="Услуга" v={d.product} />
            <Row k="Период" v={d.period} last />
          </div>
        )}
        {tab === 'docs' && <div style={{ ...CARD, padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Документы — скоро.</div>}
        {tab === 'history' && <div style={{ ...CARD, padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>История — скоро.</div>}
        </>)}
      </div>

      {/* нижняя панель */}
      <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 14px', background: 'var(--bg-card)', borderTop: '1px solid var(--border-inner)', display: 'flex', gap: 8 }}>
        {editing ? (<>
          <button onClick={() => setEditing(false)} disabled={saving} style={{ flex: '0 0 auto', padding: '14px 20px', borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>Отмена</button>
          <button onClick={save} disabled={saving} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : 'Сохранить'}</button>
        </>) : (<>
          <button onClick={canEdit ? startEdit : undefined} disabled={!canEdit} style={{ flex: 1, background: canEdit ? 'var(--accent)' : 'var(--bg-subtle)', color: canEdit ? '#fff' : 'var(--text-faint)', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: canEdit ? 'pointer' : 'default' }}>Редактировать</button>
          <button aria-label="Скачать" style={{ width: 48, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 18 }}>⭳</button>
        </>)}
      </div>
    </div>
  )
}

// ── Карточка-предпросмотр (макет 390px): свёрнутая → тап разворачивает → «Открыть сделку»/✎ ──
function DealCard({ d, onOpen, canEdit, expanded, onToggle }) {
  const local = String(d.bitrix_id || '').startsWith('local-')
  return (
    <div style={{ ...CARD, padding: '12px 14px', fontFamily: UI }}>
      {/* свёрнутая часть — клик разворачивает (аккордеон: одна карточка за раз) */}
      <div onClick={onToggle} style={{ cursor: 'pointer' }}>
        {/* строка 1: слои + ID · период + бриф */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LayerStrip layer={d.money_layer} />
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: local ? 'var(--text-faint)' : 'var(--accent)' }}>{local ? 'локально' : d.bitrix_id}</span>
          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{d.period || '—'}</span>
          <DealBriefCell deal={d} canEdit={canEdit} v2 />
        </div>
        {/* строка 2: заголовок + сумма */}
        <div style={{ marginTop: 9, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <div style={{ flex: 1, minWidth: 0, fontSize: 14.5, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.advertiser || '—'}{d.brand ? ` · ${d.brand}` : ''}</div>
          <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{money(amountOf(d))} ₽</span>
        </div>
        {/* строка 3: агентство · продукт + статус */}
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{[d.agency, d.product].filter(Boolean).join(' · ') || '—'}</span>
          <StatusChip layer={d.money_layer} stage={d.bitrix_stage} />
        </div>
      </div>
      {/* развёрнутая часть */}
      {expanded && (
        <div style={{ animation: 'sheetFade .2s ease both' }}>
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-row)', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 10px', fontSize: 12.5 }}>
            <span style={{ color: 'var(--text-muted)' }}>Аккаунт</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.account_manager || '—'}</span>
            <span style={{ color: 'var(--text-muted)' }}>Плательщик</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.payer || '—'}</span>
            <span style={{ color: 'var(--text-muted)' }}>Название</span><span style={{ color: 'var(--text-primary)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title || '—'}</span>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={() => onOpen(d)} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Открыть сделку</button>
            <button onClick={() => onOpen(d)} aria-label="Редактировать" style={{ width: 46, height: 44, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Табличный (компактный) вид ──
function DealRow({ d, onOpen }) {
  const local = String(d.bitrix_id || '').startsWith('local-')
  return (
    <div onClick={() => onOpen(d)} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 12, alignItems: 'center', padding: '11px 4px', borderTop: '1px solid var(--border-row)', cursor: 'pointer' }}>
      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: local ? 'var(--text-faint)' : 'var(--accent)' }}>{local ? '—' : d.bitrix_id}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.advertiser || '—'}{d.brand ? ` · ${d.brand}` : ''}</div>
        <div style={{ marginTop: 3, display: 'flex', alignItems: 'center', gap: 7, fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)', overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <LayerStrip layer={d.money_layer} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{[d.period, d.agency].filter(Boolean).join(' · ') || '—'}</span>
        </div>
      </div>
      <span style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{money(amountOf(d))} ₽</span>
    </div>
  )
}

export default function DealCardList({ deals, canEdit, view = 'cards', total, onLoadMore, fopts = {}, onPatch }) {
  const [detail, setDetail] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  useEffect(() => { setExpandedId(null) }, [view])   // сброс аккордеона при смене вида карточки/таблица
  if (!deals || !deals.length) {
    return <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, fontFamily: UI }}>Нет сделок по выбранным фильтрам</div>
  }
  const shownTotal = total != null ? total : deals.length
  const canMore = onLoadMore && deals.length < shownTotal

  return (
    <>
      {view === 'table' ? (
        <div style={{ ...CARD, padding: '12px 14px 8px', fontFamily: UI }}>
          {/* заголовок таблицы */}
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 12, padding: '2px 4px 8px', ...HDR }}>
            <span>ID</span><span>Рекл. / бренд</span><span style={{ textAlign: 'right' }}>Сумма</span>
          </div>
          {deals.map(d => <DealRow key={d.id} d={d} onOpen={setDetail} />)}
          {/* подвал */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, marginTop: 4, borderTop: '1px solid var(--border-row)' }}>
            {canMore
              ? <span onClick={onLoadMore} style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer' }}>Показать ещё</span>
              : <span />}
            <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{deals.length} из {shownTotal}</span>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {deals.map(d => <DealCard key={d.id} d={d} onOpen={setDetail} canEdit={canEdit} expanded={expandedId === d.id} onToggle={() => setExpandedId(id => id === d.id ? null : d.id)} />)}
          {canMore && (
            <button onClick={onLoadMore} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '13px', fontSize: 14, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer', fontFamily: UI }}>Показать ещё · {deals.length} из {shownTotal}</button>
          )}
        </div>
      )}
      {detail && <DealDetail deal={detail} onClose={() => setDetail(null)} canEdit={canEdit} fopts={fopts} onPatch={onPatch} />}
    </>
  )
}
