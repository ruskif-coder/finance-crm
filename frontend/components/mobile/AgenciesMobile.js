import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { CARD, Marker } from './kit'
import BottomSheet from './BottomSheet'
import DirectoryMobile from './DirectoryMobile'

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
const nm = (a) => a.name_ru || a.name_en || a.short_name || `#${a.bx_id || a.id}`
const sub = (a) => a.name_en || a.short_name || ''

function AgCard({ a, open, onToggle, onEdit, canEdit }) {
  const cps = a.counterparties || []
  return (
    <div style={{ ...CARD, padding: '13px 14px', fontFamily: UI }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Marker c={a.sk_percent > 0 ? 'var(--accent)' : 'var(--text-faint)'} size={8} />
          {a.bx_id && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>#{a.bx_id}</span>}
          <span style={{ marginLeft: 'auto', background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 8, padding: '4px 9px', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>СК {Math.round(a.sk_percent || 0)}%</span>
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, wordBreak: 'break-word' }}>{nm(a)}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {sub(a) && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{sub(a)}</span>}
          {a.holding && <span style={{ width: 1, height: 11, background: 'var(--border-card)' }} />}
          {a.holding && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.04em', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{a.holding}</span>}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: a.deals > 0 ? 'var(--text-primary)' : 'var(--text-faint)' }}>{a.deals || 0} сд.</span>
            <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{open ? '▴' : '▾'}</span>
          </span>
        </div>
      </div>
      {open && (
        <div style={{ animation: 'riseIn .24s ease both', marginTop: 10 }}>
          <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '2px 12px' }}>
            {[
              ['Английское', a.name_en || '—'],
              ['Краткое', a.short_name || '—'],
              ['Холдинг', a.holding || '—'],
              ['Сделок', a.deals || 0],
              ['СК', `${Math.round(a.sk_percent || 0)}%`],
            ].map(([k, v], i) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{k}</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', textAlign: 'right', maxWidth: '62%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
              </div>
            ))}
            <div style={{ padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 6 }}>Юрлица ({cps.length})</div>
              {cps.length ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{cps.map((c, i) => <span key={i} style={{ fontSize: 11.5, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 8, padding: '3px 8px', color: 'var(--text-secondary)' }}>{c.name}</span>)}</div> : <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>—</span>}
            </div>
          </div>
          {canEdit && (
            <div style={{ marginTop: 12 }}>
              <button onClick={() => onEdit(a)} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Редактировать</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AgForm({ initial, editId, onClose, onSave, saving }) {
  const [f, setF] = useState(initial)
  const set = (p) => setF(s => ({ ...s, ...p }))
  const fieldRow = { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }
  const lbl = { fontSize: 12, color: 'var(--text-muted)' }
  const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px', fontSize: 14, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }
  return (
    <BottomSheet open onClose={onClose} title={editId ? 'Редактирование' : 'Новое агентство'}
      footer={<button onClick={() => onSave(f, editId)} disabled={saving} style={{ width: '100%', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : editId ? 'Сохранить' : 'Создать'}</button>}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>{editId ? `Агентство #${editId}` : 'Новое агентство'}</div>
      <div style={fieldRow}><span style={lbl}>Русское название</span><input autoFocus value={f.name_ru} onChange={e => set({ name_ru: e.target.value })} placeholder="Агентство" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Английское</span><input value={f.name_en} onChange={e => set({ name_en: e.target.value })} placeholder="Agency" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Краткое</span><input value={f.short_name} onChange={e => set({ short_name: e.target.value })} placeholder="кратко" style={inp} /></div>
      <div style={fieldRow}><span style={lbl}>Холдинг</span><input value={f.holding} onChange={e => set({ holding: e.target.value })} placeholder="—" style={inp} /></div>
      {editId != null && <div style={fieldRow}><span style={lbl}>СК, %</span><input inputMode="decimal" value={f.sk_percent} onChange={e => set({ sk_percent: e.target.value.replace(/[^\d.,]/g, '') })} placeholder="0" style={{ ...inp, fontFamily: MONO }} /></div>}
    </BottomSheet>
  )
}

export default function AgenciesMobile({
  total, rows, loading, canEdit,
  search, setSearch, onSave, saving, limit, setLimit,
}) {
  const [form, setForm] = useState(null)

  const openCreate = () => setForm({ editId: null, initial: { short_name: '', name_en: '', name_ru: '', holding: '' } })
  const openEdit = (a) => setForm({ editId: a.id, initial: { short_name: a.short_name || '', name_en: a.name_en || '', name_ru: a.name_ru || '', holding: a.holding || '', sk_percent: a.sk_percent != null ? String(Math.round(a.sk_percent)) : '' } })

  const save = async (f, editId) => {
    const ok = await onSave(f, editId)
    if (ok !== false) setForm(null)
  }

  const shown = limit ? rows.slice(0, limit) : rows

  return (
    <>
      <DirectoryMobile
        title="Агентства" total={total} shownCount={shown.length} loading={loading} canEdit={canEdit}
        search={search} setSearch={setSearch} searchPlaceholder="название, холдинг, юрлицо…"
        onAdd={openCreate}
        rows={shown}
        renderCard={(a, open, toggle) => <AgCard a={a} open={open} onToggle={toggle} onEdit={openEdit} canEdit={canEdit} />}
        hasMore={rows.length > shown.length}
        onMore={() => setLimit(l => (l || 50) + 50)}
        moreLabel={`Показать ещё · ${shown.length} из ${new Intl.NumberFormat('ru-RU').format(rows.length)}`}
      />
      {form && <AgForm initial={form.initial} editId={form.editId} saving={saving} onClose={() => setForm(null)} onSave={save} />}
    </>
  )
}
