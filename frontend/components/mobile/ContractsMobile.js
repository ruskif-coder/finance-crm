import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { CARD, Marker, rise } from './kit'
import { T } from '../../lib/tokens'
import BottomSheet from './BottomSheet'
import DirectoryMobile, { FilterChip } from './DirectoryMobile'
import { PAYMENT_TERM_CONDITIONS } from '@/lib/contractTerms'
import { fmtDate as fmtCalendarDate } from '@/lib/dates'

const fmtDate = (s) => fmtCalendarDate(s)
const fmtEndDate = (s) => {
  if (!s) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return fmtCalendarDate(s)
  return s
}

const COOPERATION_FORMATS = ['Агентство КЛ', 'Агентство ПД', 'Клиент', 'Подрядчик', 'Аптека', 'Паблишер', 'Рекламная система']
const PROLONGATION_OPTIONS = ['АВТО на год', 'По соглашению', 'Нет']

// формат сотрудничества → цвет чипа
const FMT_META = {
  'Клиент': { bg: 'var(--accent-tint)', fg: 'var(--accent)' },
  'Подрядчик': { bg: T.warningTint, fg: T.warningText },
  'Агентство КЛ': { bg: '#F1EDFC', fg: T.mixed },
  'Агентство ПД': { bg: '#F1EDFC', fg: T.mixed },
  'Аптека': { bg: '#E6F5EF', fg: 'var(--income)' },
  'Паблишер': { bg: '#E9F0FB', fg: '#3B6FD4' },
  'Рекламная система': { bg: '#FDEBF0', fg: '#C43C6B' },
}
const fmtMeta = (f) => FMT_META[f] || { bg: 'var(--bg-subtle)', fg: 'var(--text-muted)' }
// маркер: есть документ (файл/ссылка) → зелёный, иначе серый
const docColor = (c) => (c.attached_filename || c.document_link) ? 'var(--income)' : 'var(--text-faint)'

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

function CtCard({ c, open, onToggle, onEdit, onDownload, canEdit }) {
  const meta = fmtMeta(c.cooperation_format)
  const docName = c.attached_filename ? c.attached_filename.replace(new RegExp(`^${c.id}_`), '') : null
  return (
    <div style={{ ...CARD, padding: '13px 14px', fontFamily: UI }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* верхняя строка: маркер документа · ID · чип формата */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Marker c={docColor(c)} size={8} />
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>#{c.id}</span>
          {!c.linked && <span title="Не привязан к реестру" style={{ fontSize: 11, color: 'var(--warning, #E89020)' }}>⚠</span>}
          {c.cooperation_format && <span style={{ marginLeft: 'auto', background: meta.bg, color: meta.fg, borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 150 }}>{c.cooperation_format}</span>}
        </div>
        {/* название = контрагент */}
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, wordBreak: 'break-word' }}>{c.counterparty_name || '— без контрагента —'}</div>
        {/* нижняя строка: № договора · ИНН · дата */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }}>№ {c.contract_number || '—'}</span>
          <span style={{ width: 1, height: 11, background: 'var(--border-card)' }} />
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{c.inn || '—'}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(c.contract_date)}</span>
            <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{open ? '▴' : '▾'}</span>
          </span>
        </div>
      </div>
      {open && (
        <div style={{ ...rise(0, '.24s'), marginTop: 10 }}>
          <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '2px 12px' }}>
            {[
              ['Дата договора', fmtDate(c.contract_date)],
              ['Окончание', fmtEndDate(c.end_date_text)],
              ['Пролонгация', c.prolongation || '—'],
              ['Отсрочка', c.payment_term_days != null ? `${c.payment_term_days} дн.` : '—'],
              ['Условие', c.payment_term_condition || '—'],
              ['Назв. маркет.', c.marketing_name || '—'],
              ['Документ', docName || (c.document_link ? 'ссылка' : '—')],
            ].map(([k, v], i) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '8px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)', flexShrink: 0 }}>{k}</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            {c.attached_filename && (
              <button onClick={() => onDownload(c.id, c.attached_filename)} style={{ flex: 1, background: 'var(--accent-tint)', color: 'var(--accent)', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>📥 Документ</button>
            )}
            {!c.attached_filename && c.document_link && (
              <a href={/^https?:\/\//i.test(c.document_link) ? c.document_link : undefined} target="_blank" rel="noopener noreferrer" style={{ flex: 1, background: 'var(--accent-tint)', color: 'var(--accent)', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer', textAlign: 'center', textDecoration: 'none' }}>🔗 Документ</a>
            )}
            {canEdit && (
              <button onClick={() => onEdit(c)} style={{ flex: c.attached_filename || c.document_link ? '0 0 auto' : 1, minWidth: 46, background: c.attached_filename || c.document_link ? 'var(--bg-card)' : 'var(--accent)', color: c.attached_filename || c.document_link ? 'var(--text-secondary)' : '#fff', border: c.attached_filename || c.document_link ? '1px solid var(--border-card)' : 'none', borderRadius: 12, padding: '12px', height: 44, fontSize: 14, fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                {!(c.attached_filename || c.document_link) && 'Редактировать'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Форма создания/редактирования (bottom sheet) ──
function CtForm({ initial, editId, counterparties, onClose, onSave, saving }) {
  const [f, setF] = useState(initial)
  const set = (p) => setF(s => ({ ...s, ...p }))
  const fieldRow = { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }
  const lbl = { fontSize: 12, color: 'var(--text-muted)' }
  const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }
  const cpInn = (counterparties.find(cp => cp.id === f.counterparty_id) || {}).inn || ''
  const sortedCp = [...counterparties].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  return (
    <BottomSheet open onClose={onClose} title={editId ? 'Редактирование' : 'Новый договор'}
      footer={<button onClick={() => onSave(f, editId)} disabled={saving} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : editId ? 'Сохранить' : 'Создать'}</button>}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>{editId ? `Договор #${editId}` : 'Новый договор'}</div>

      <div style={fieldRow}><span style={lbl}>Контрагент *</span>
        <select value={f.counterparty_id || ''} onChange={e => set({ counterparty_id: e.target.value ? parseInt(e.target.value, 10) : null })} style={inp}>
          <option value="">— выберите контрагента —</option>
          {sortedCp.map(cp => <option key={cp.id} value={cp.id}>{cp.name}</option>)}
        </select>
      </div>
      {cpInn && <div style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', margin: '-6px 0 12px 2px' }}>ИНН: {cpInn}</div>}

      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ ...fieldRow, flex: 1 }}><span style={lbl}>№ договора</span><input value={f.contract_number} onChange={e => set({ contract_number: e.target.value })} placeholder="№…" style={inp} /></div>
        <div style={{ ...fieldRow, flex: 1 }}><span style={lbl}>Дата договора</span><input type="date" value={f.contract_date || ''} onChange={e => set({ contract_date: e.target.value })} style={{ ...inp, fontFamily: MONO }} /></div>
      </div>

      <div style={fieldRow}><span style={lbl}>Название маркетинговое</span><input value={f.marketing_name} onChange={e => set({ marketing_name: e.target.value })} placeholder="Название" style={inp} /></div>

      <div style={fieldRow}><span style={lbl}>Формат сотрудничества</span>
        <select value={COOPERATION_FORMATS.includes(f.cooperation_format) ? f.cooperation_format : (f.cooperation_format ? '__other__' : '')} onChange={e => { if (e.target.value !== '__other__') set({ cooperation_format: e.target.value }) }} style={inp}>
          <option value="">—</option>
          {COOPERATION_FORMATS.map(o => <option key={o} value={o}>{o}</option>)}
          {f.cooperation_format && !COOPERATION_FORMATS.includes(f.cooperation_format) && <option value="__other__">{f.cooperation_format} (старое)</option>}
        </select>
      </div>

      <div style={fieldRow}><span style={lbl}>Окончание (дата или текст)</span><input value={f.end_date_text} onChange={e => set({ end_date_text: e.target.value })} placeholder="напр. Бессрочно / 2026-12-31" style={inp} /></div>

      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ ...fieldRow, flex: 1 }}><span style={lbl}>Пролонгация</span>
          <select value={PROLONGATION_OPTIONS.includes(f.prolongation) ? f.prolongation : (f.prolongation ? '__other__' : '')} onChange={e => { if (e.target.value !== '__other__') set({ prolongation: e.target.value }) }} style={inp}>
            <option value="">—</option>
            {PROLONGATION_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
            {f.prolongation && !PROLONGATION_OPTIONS.includes(f.prolongation) && <option value="__other__">{f.prolongation} (старое)</option>}
          </select>
        </div>
        <div style={{ ...fieldRow, flex: '0 0 120px' }}><span style={lbl}>Срок, дн.</span><input inputMode="numeric" value={f.payment_term_days} onChange={e => set({ payment_term_days: e.target.value.replace(/\D/g, '') })} placeholder="60" style={{ ...inp, fontFamily: MONO }} /></div>
      </div>

      <div style={fieldRow}><span style={lbl}>Условие оплаты</span>
        <select value={f.payment_term_condition || ''} onChange={e => set({ payment_term_condition: e.target.value })} style={inp}>
          <option value="">—</option>
          {PAYMENT_TERM_CONDITIONS.map(o => <option key={o} value={o}>{o}</option>)}
          {f.payment_term_condition && !PAYMENT_TERM_CONDITIONS.includes(f.payment_term_condition) && <option value={f.payment_term_condition}>{f.payment_term_condition} (старое)</option>}
        </select>
      </div>

      <div style={fieldRow}><span style={lbl}>🔗 Ссылка на документ</span><input value={f.document_link} onChange={e => set({ document_link: e.target.value })} placeholder="ЭДО, облако…" style={inp} /></div>
    </BottomSheet>
  )
}

export default function ContractsMobile({
  total, rows, loading, canEdit, counterparties = [],
  search, setSearch, formatFilter, setFormatFilter, formatOptions = [],
  onSave, saving, onDownload, limit, setLimit,
}) {
  const [form, setForm] = useState(null)          // { initial, editId } | null
  const [fmtSheet, setFmtSheet] = useState(false)

  const emptyForm = () => ({
    counterparty_id: null, contract_number: '', contract_date: '', marketing_name: '',
    cooperation_format: '', end_date_text: '', prolongation: '', payment_term_days: '',
    payment_term_condition: '', document_link: '',
  })
  const openCreate = () => setForm({ editId: null, initial: emptyForm() })
  const openEdit = (c) => setForm({
    editId: c.id, initial: {
      counterparty_id: c.counterparty_id ?? null,
      contract_number: c.contract_number || '', contract_date: c.contract_date || '',
      marketing_name: c.marketing_name || '', cooperation_format: c.cooperation_format || '',
      end_date_text: c.end_date_text || '', prolongation: c.prolongation || '',
      payment_term_days: c.payment_term_days != null ? String(c.payment_term_days) : '',
      payment_term_condition: c.payment_term_condition || '', document_link: c.document_link || '',
    },
  })

  const save = async (f, editId) => {
    const ok = await onSave(f, editId)
    if (ok !== false) setForm(null)
  }

  const fmtLabel = formatFilter || 'Все форматы'
  const shown = limit ? rows.slice(0, limit) : rows

  return (
    <>
      <DirectoryMobile
        title="Договора" total={total} shownCount={shown.length} loading={loading} canEdit={canEdit}
        search={search} setSearch={setSearch} searchPlaceholder="№, контрагент, ИНН…"
        filterChips={<FilterChip label={fmtLabel} active={!!formatFilter} onClick={() => setFmtSheet(true)} />}
        onAdd={openCreate}
        rows={shown}
        renderCard={(c, open, toggle) => <CtCard c={c} open={open} onToggle={toggle} onEdit={openEdit} onDownload={onDownload} canEdit={canEdit} />}
        hasMore={rows.length > shown.length}
        onMore={() => setLimit(l => (l || 50) + 50)}
        moreLabel={`Показать ещё · ${shown.length} из ${new Intl.NumberFormat('ru-RU').format(rows.length)}`}
      />

      {fmtSheet && (
        <BottomSheet open onClose={() => setFmtSheet(false)} title="Формат">
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Формат сотрудничества</div>
          {[['', 'Все форматы'], ...formatOptions.map(o => [o, o])].map(([v, label]) => (
            <button key={v || '_all'} onClick={() => { setFormatFilter(v); setFmtSheet(false) }} style={{ width: '100%', textAlign: 'left', border: 'none', background: formatFilter === v ? 'var(--accent-tint)' : 'transparent', color: formatFilter === v ? 'var(--accent)' : 'var(--text-primary)', borderRadius: 10, padding: '13px 12px', fontSize: 14, fontWeight: formatFilter === v ? 700 : 600, cursor: 'pointer', fontFamily: UI }}>{label}</button>
          ))}
        </BottomSheet>
      )}

      {form && <CtForm initial={form.initial} editId={form.editId} counterparties={counterparties} saving={saving} onClose={() => setForm(null)} onSave={save} />}
    </>
  )
}
