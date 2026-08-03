import { useState } from 'react'
import { useRouter } from 'next/router'
import { MONO, UI } from '../salesTableKit'
import { grp } from '../../lib/salesFormat'
import { T } from '../../lib/tokens'
import { CARD, Marker } from './kit'
import BottomSheet from './BottomSheet'
import DirectoryMobile, { FilterChip } from './DirectoryMobile'

const fmt = (n) => grp(Math.abs(n || 0))
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('ru-RU') : '—'

// тип контрагента (relation) → чип
const REL_META = {
  'заказчик': { label: 'Заказчик', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
  'поставщик': { label: 'Поставщик', bg: T.warningTint, fg: T.warningText },
  'смешенный': { label: 'Смешанный', bg: '#F1EDFC', fg: T.mixed },
}
const relMeta = (r) => REL_META[r] || { label: 'не заполнен', bg: 'var(--bg-subtle)', fg: 'var(--text-faint)' }
// вид (status) → цвет маркера
const vidColor = (s) => s === 'действующий' ? 'var(--income)' : 'var(--text-faint)'

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

function DiffValue({ v }) {
  const col = v > 0 ? 'var(--income)' : v < 0 ? T.danger : 'var(--text-faint)'
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: col, whiteSpace: 'nowrap' }}>{v ? `${sign}${fmt(v)}` : '—'}</span>
}

function CpCard({ c, open, onToggle, onOpen, onEdit, canEdit }) {
  const rel = relMeta(c.relation)
  return (
    <div style={{ ...CARD, padding: '13px 14px', fontFamily: UI }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* верхняя строка: маркер вида · ID · статус-чип */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Marker c={vidColor(c.status)} size={8} />
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>#{c.id}</span>
          {c.is_own_company && <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', background: 'var(--accent-tint)', borderRadius: 6, padding: '2px 6px' }}>НАША</span>}
          <span style={{ marginLeft: 'auto', background: rel.bg, color: rel.fg, borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{rel.label}</span>
        </div>
        {/* название */}
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, wordBreak: 'break-word' }}>{c.name}</div>
        {/* нижняя строка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>{c.inn || '—'}</span>
          {c.group && <span style={{ width: 1, height: 11, background: 'var(--border-card)' }} />}
          {c.group && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.04em', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{c.group}</span>}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <DiffValue v={c.diff} />
            <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{open ? '▴' : '▾'}</span>
          </span>
        </div>
      </div>
      {open && (
        <div style={{ animation: 'riseIn .24s ease both', marginTop: 10 }}>
          <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '2px 12px' }}>
            {[
              ['Поступления', c.income_paid > 0 ? fmt(c.income_paid) : '—', 'var(--income)'],
              ['Выплаты', c.expense_paid > 0 ? fmt(c.expense_paid) : '—', 'var(--text-secondary)'],
              ['Дебиторка', c.receivable > 0 ? fmt(c.receivable) : '—', 'var(--accent)'],
              ['Кредиторка', c.payable > 0 ? fmt(c.payable) : '—', T.warning],
              ['Договоров', c.contracts_count || 0, 'var(--text-primary)'],
              ['Операций', c.op_count || 0, 'var(--text-primary)'],
              ['Отсрочка', `${c.term_days_effective} дн.${c.term_days_is_default ? ' (по умолч.)' : ''}`, 'var(--text-primary)'],
              ['Последняя операция', fmtDate(c.last_op_date), 'var(--text-secondary)'],
            ].map(([k, v, col], i) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{k}</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: col }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={() => onOpen(c)} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Открыть карточку</button>
            {canEdit && (
              <button onClick={() => onEdit(c)} aria-label="Редактировать" style={{ width: 46, height: 44, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Форма создания/редактирования (bottom sheet) ──
function CpForm({ initial, editId, isAdmin, onClose, onSave, saving }) {
  const [f, setF] = useState(initial)
  const set = (p) => setF(s => ({ ...s, ...p }))
  const fieldRow = { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }
  const lbl = { fontSize: 12, color: 'var(--text-muted)' }
  const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }
  return (
    <BottomSheet open onClose={onClose} title={editId ? 'Редактирование' : 'Новый контрагент'}
      footer={<button onClick={() => onSave(f, editId)} disabled={saving} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : editId ? 'Сохранить' : 'Создать'}</button>}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>{editId ? `Контрагент #${editId}` : 'Новый контрагент'}</div>
      <div style={fieldRow}><span style={lbl}>Название *</span><input autoFocus value={f.name} onChange={e => set({ name: e.target.value })} placeholder="ООО Контрагент" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>ИНН</span><input value={f.inn} onChange={e => set({ inn: e.target.value })} placeholder="1234567890" style={{ ...inp, fontFamily: MONO }} /></div>
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ ...fieldRow, flex: 1 }}><span style={lbl}>Вид</span>
          <select value={f.status} onChange={e => set({ status: e.target.value })} style={inp}>
            <option value="действующий">Действующий</option>
            <option value="виртуальный">Виртуальный</option>
          </select>
        </div>
        <div style={{ ...fieldRow, flex: '0 0 120px' }}><span style={lbl}>Отсрочка, дн.</span><input inputMode="numeric" value={f.term_days} onChange={e => set({ term_days: e.target.value.replace(/\D/g, '') })} placeholder="60" style={{ ...inp, fontFamily: MONO }} /></div>
      </div>
      {isAdmin && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-primary)', padding: '4px 0', cursor: 'pointer' }}>
          <input type="checkbox" checked={f.is_own_company} onChange={e => set({ is_own_company: e.target.checked })} /> 🏢 Наша компания
        </label>
      )}
    </BottomSheet>
  )
}

const VID_OPTS = [['', 'Все виды'], ['действующий', 'Действующий'], ['виртуальный', 'Виртуальный']]

export default function CounterpartiesMobile({
  total, rows, loading, canEdit, isAdmin,
  search, setSearch, statusFilter, setStatusFilter,
  onSave, saving, limit, setLimit,
}) {
  const router = useRouter()
  const [form, setForm] = useState(null)          // { initial, editId } | null
  const [vidSheet, setVidSheet] = useState(false)

  const openCreate = () => setForm({ editId: null, initial: { name: '', inn: '', status: 'действующий', term_days: '', is_own_company: false } })
  const openEdit = (c) => setForm({ editId: c.id, initial: { name: c.name, inn: c.inn || '', status: c.status, term_days: c.term_days != null ? String(c.term_days) : '', is_own_company: !!c.is_own_company } })
  const openCard = (c) => router.push(`/counterparty/${c.id}`)

  const save = async (f, editId) => {
    const ok = await onSave(f, editId)
    if (ok !== false) setForm(null)
  }

  const vidLabel = (VID_OPTS.find(([v]) => v === statusFilter) || VID_OPTS[0])[1]
  const shown = limit ? rows.slice(0, limit) : rows

  return (
    <>
      <DirectoryMobile
        title="Контрагенты" total={total} shownCount={shown.length} loading={loading} canEdit={canEdit}
        search={search} setSearch={setSearch} searchPlaceholder="название, ИНН…"
        filterChips={<FilterChip label={vidLabel} active={!!statusFilter} onClick={() => setVidSheet(true)} />}
        onAdd={openCreate}
        rows={shown}
        renderCard={(c, open, toggle) => <CpCard c={c} open={open} onToggle={toggle} onOpen={openCard} onEdit={openEdit} canEdit={canEdit} />}
        hasMore={rows.length > shown.length}
        onMore={() => setLimit(l => (l || 50) + 50)}
        moreLabel={`Показать ещё · ${shown.length} из ${new Intl.NumberFormat('ru-RU').format(rows.length)}`}
      />

      {vidSheet && (
        <BottomSheet open onClose={() => setVidSheet(false)} title="Вид">
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Вид контрагента</div>
          {VID_OPTS.map(([v, label]) => (
            <button key={v} onClick={() => { setStatusFilter(v); setVidSheet(false) }} style={{ width: '100%', textAlign: 'left', border: 'none', background: statusFilter === v ? 'var(--accent-tint)' : 'transparent', color: statusFilter === v ? 'var(--accent)' : 'var(--text-primary)', borderRadius: 10, padding: '13px 12px', fontSize: 14, fontWeight: statusFilter === v ? 700 : 600, cursor: 'pointer', fontFamily: UI }}>{label}</button>
          ))}
        </BottomSheet>
      )}

      {form && <CpForm initial={form.initial} editId={form.editId} isAdmin={isAdmin} saving={saving} onClose={() => setForm(null)} onSave={save} />}
    </>
  )
}
