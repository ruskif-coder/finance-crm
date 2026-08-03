import { useState } from 'react'
import { useRouter } from 'next/router'
import { MONO, UI } from '../salesTableKit'
import { grp } from '../../lib/salesFormat'
import { CARD, Marker } from './kit'
import BottomSheet from './BottomSheet'
import DirectoryMobile, { FilterChip } from './DirectoryMobile'

// Мобильный справочник «Рекламодатели» (sales-домен). По аналогии с
// CounterpartiesMobile: карточка с одиночным раскрытием + форма в BottomSheet.
// Управление брендами / привязка юрлиц / слияние дублей — только на десктопе;
// на мобиле бренды и юрлица показываются в раскрытии, редактируются основные поля.

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

// имя рекламодателя: русское → англ → короткое → служебное name
const advName = (a) => a.name_ru || a.name_en || a.short_name || a.name || '—'
// вторичное (моно) имя для нижней строки: короткое / англ, отличное от заголовка
const advSub = (a) => {
  const title = advName(a)
  const cands = [a.short_name, a.name_en, a.name_ru].filter(Boolean).filter(v => v !== title)
  return cands[0] || null
}
const vidColor = (a) => (a.is_active ? 'var(--income)' : 'var(--text-faint)')
const cleanUrl = (u) => (u ? (u.startsWith('http') ? u : `https://${u}`) : '')

function AdvCard({ a, open, onToggle, onEdit, onDeals, canEdit }) {
  const brands = a.brands || []
  const cps = a.counterparties || []
  const sub = advSub(a)
  const site = a.website
  return (
    <div style={{ ...CARD, padding: '13px 14px', fontFamily: UI }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* верхняя строка: маркер · #bx_id · чип «сделок» / «брендов» */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Marker c={vidColor(a)} size={8} />
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>#{a.bx_id || a.id}</span>
          {a.deals > 0
            ? <span style={{ marginLeft: 'auto', background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>сделок: {grp(a.deals)}</span>
            : brands.length > 0
              ? <span style={{ marginLeft: 'auto', background: 'var(--bg-subtle)', color: 'var(--text-muted)', borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>брендов: {brands.length}</span>
              : <span style={{ marginLeft: 'auto', color: 'var(--text-faint)', fontFamily: MONO, fontSize: 10.5 }}>без сделок</span>}
        </div>
        {/* название */}
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, wordBreak: 'break-word' }}>{advName(a)}</div>
        {/* нижняя строка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {sub && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{sub}</span>}
          {sub && site && <span style={{ width: 1, height: 11, background: 'var(--border-card)' }} />}
          {site && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.02em', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{site.replace(/^https?:\/\//, '')}</span>}
          <span style={{ marginLeft: 'auto', color: 'var(--text-faint)', fontSize: 11 }}>{open ? '▴' : '▾'}</span>
        </div>
      </div>
      {open && (
        <div style={{ animation: 'riseIn .24s ease both', marginTop: 10 }}>
          <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '2px 12px' }}>
            {[
              ['Английское', a.name_en || '—'],
              ['Короткое', a.short_name || a.name || '—'],
              ['Сделок', a.deals > 0 ? grp(a.deals) : '—'],
            ].map(([k, v], i) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '8px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{k}</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
              </div>
            ))}
            {/* Сайт (ссылка) */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
              <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Сайт</span>
              {site
                ? <a href={cleanUrl(site)} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: 'var(--accent)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>{site.replace(/^https?:\/\//, '')}</a>
                : <span style={{ fontFamily: MONO, fontSize: 12.5, color: 'var(--text-faint)' }}>—</span>}
            </div>
            {/* Бренды */}
            <div style={{ padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: brands.length ? 7 : 0 }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Бренды</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: brands.length ? 'var(--text-primary)' : 'var(--text-faint)' }}>{brands.length || '—'}</span>
              </div>
              {brands.length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {brands.map(b => (
                    <span key={b.id} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 8, padding: '3px 8px', fontSize: 12, color: 'var(--text-secondary)' }}>{b.name}</span>
                  ))}
                </div>
              )}
            </div>
            {/* Юрлица */}
            <div style={{ padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: cps.length ? 7 : 0 }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Юрлица</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: cps.length ? 'var(--text-primary)' : 'var(--text-faint)' }}>{cps.length || '—'}</span>
              </div>
              {cps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {cps.map(c => (
                    <span key={c.counterparty_id} style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{c.name}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            {a.deals > 0 && (
              <button onClick={() => onDeals(a)} style={{ flex: 1, background: 'var(--bg-card)', color: 'var(--accent)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Сделки · {grp(a.deals)}</button>
            )}
            {canEdit && (
              <button onClick={() => onEdit(a)} style={{ flex: a.deals > 0 ? '0 0 auto' : 1, minWidth: 46, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px 16px', fontSize: 14, fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                {a.deals > 0 ? '' : 'Редактировать'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Форма создания/редактирования (bottom sheet) ──
function AdvForm({ initial, editId, onClose, onSave, saving }) {
  const [f, setF] = useState(initial)
  const set = (p) => setF(s => ({ ...s, ...p }))
  const fieldRow = { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }
  const lbl = { fontSize: 12, color: 'var(--text-muted)' }
  const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }
  return (
    <BottomSheet open onClose={onClose} title={editId ? 'Редактирование' : 'Новый рекламодатель'}
      footer={<button onClick={() => onSave(f, editId)} disabled={saving} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : editId ? 'Сохранить' : 'Создать'}</button>}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>{editId ? `Рекламодатель #${editId}` : 'Новый рекламодатель'}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>Достаточно любого из названий</div>
      <div style={fieldRow}><span style={lbl}>Короткое</span><input autoFocus value={f.short_name} onChange={e => set({ short_name: e.target.value })} placeholder="напр. Coca-Cola" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Английское</span><input value={f.name_en} onChange={e => set({ name_en: e.target.value })} placeholder="The Coca-Cola Company" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Русское</span><input value={f.name_ru} onChange={e => set({ name_ru: e.target.value })} placeholder="Кока-Кола" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Сайт</span><input value={f.website} onChange={e => set({ website: e.target.value })} placeholder="example.com" style={{ ...inp, fontFamily: MONO }} /></div>
      <div style={fieldRow}><span style={lbl}>ИНН</span><input value={f.inn} onChange={e => set({ inn: e.target.value })} placeholder="1234567890" style={{ ...inp, fontFamily: MONO }} /></div>
    </BottomSheet>
  )
}

export default function AdvertisersMobile({
  total, rows, loading, canEdit,
  search, setSearch,
  onSave, saving, limit, setLimit,
}) {
  const router = useRouter()
  const [form, setForm] = useState(null)   // { initial, editId } | null

  const openCreate = () => setForm({ editId: null, initial: { short_name: '', name_en: '', name_ru: '', website: '', inn: '' } })
  const openEdit = (a) => setForm({ editId: a.id, initial: { short_name: a.short_name || a.name || '', name_en: a.name_en || '', name_ru: a.name_ru || '', website: a.website || '', inn: a.inn || '' } })
  const openDeals = (a) => router.push(`/sales?advertiser_id=${a.id}`)

  const save = async (f, editId) => {
    const ok = await onSave(f, editId)
    if (ok !== false) setForm(null)
  }

  const shown = limit ? rows.slice(0, limit) : rows

  return (
    <>
      <DirectoryMobile
        title="Рекламодатели" total={total} shownCount={shown.length} loading={loading} canEdit={canEdit}
        search={search} setSearch={setSearch} searchPlaceholder="название, бренд…"
        onAdd={openCreate}
        rows={shown}
        renderCard={(a, open, toggle) => <AdvCard a={a} open={open} onToggle={toggle} onEdit={openEdit} onDeals={openDeals} canEdit={canEdit} />}
        hasMore={rows.length > shown.length}
        onMore={() => setLimit(l => (l || 50) + 50)}
        moreLabel={`Показать ещё · ${shown.length} из ${new Intl.NumberFormat('ru-RU').format(rows.length)}`}
      />

      {form && <AdvForm initial={form.initial} editId={form.editId} saving={saving} onClose={() => setForm(null)} onSave={save} />}
    </>
  )
}
