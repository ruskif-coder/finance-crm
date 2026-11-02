/**
 * Кредитные линии на экране «Настройки → Остатки» (02.11.2026). Источник «Кредита» в «Деньгах на сегодня» над планом
 * оплат: свободно = лимит − выбрано. «Выбрано» вводится руками — тело кредита в статьях не выделено, — поэтому рядом
 * дата, на которую цифра верна. Удаления нет: закрытую линию выключают галочкой «действует», история остаётся.
 * Право — то же, что у стартовых остатков (`settings_balances`). Список банков — от сервера (`banks`: тот же ответ, что
 * у стартовых остатков, без наличных), а не своей копией.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '../../lib/http'
import { getPermissions } from '../../lib/auth'
import { can } from '../Navbar'
import { MONO, card, inp, sel, primaryBtn, btn } from '../salesTableKit'
import { grp0 } from '../../lib/salesFormat'

const EMPTY = { bank: '', limit_amount: '', used_amount: '0', as_of: '', note: '', is_active: true }
const LABEL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-muted)' }
const GRID = '150px 150px 150px 150px minmax(160px,1fr) 90px 110px'

const toForm = (c) => ({ bank: c.bank, limit_amount: String(c.limit_amount ?? ''), used_amount: String(c.used_amount ?? 0),
  as_of: c.as_of || '', note: c.note || '', is_active: c.is_active })
const toBody = (f) => ({ ...f, limit_amount: parseFloat(f.limit_amount) || 0, used_amount: parseFloat(f.used_amount) || 0,
  as_of: f.as_of || null, note: f.note || null })

function Row({ banks, form, setForm, onSave, busy, canEdit, isNew }) {
  const set = (k) => (e) => setForm({ ...form, [k]: k === 'is_active' ? e.target.checked : e.target.value })
  const free = (parseFloat(form.limit_amount) || 0) - (parseFloat(form.used_amount) || 0)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', opacity: form.is_active ? 1 : 0.55 }}>
      <select value={form.bank} onChange={set('bank')} disabled={!canEdit} style={{ ...sel, fontSize: 13 }}>
        {banks.map(b => <option key={b} value={b}>{b}</option>)}
      </select>
      <input type="number" value={form.limit_amount} onChange={set('limit_amount')} disabled={!canEdit} placeholder="лимит" style={{ ...inp, textAlign: 'right' }} />
      <input type="number" value={form.used_amount} onChange={set('used_amount')} disabled={!canEdit} style={{ ...inp, textAlign: 'right' }} />
      <input type="date" value={form.as_of} onChange={set('as_of')} disabled={!canEdit} style={inp} />
      <input value={form.note} onChange={set('note')} disabled={!canEdit} placeholder="договор, ставка, срок" style={inp} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={form.is_active} onChange={set('is_active')} disabled={!canEdit} /> действует
      </label>
      {canEdit
        ? <button onClick={onSave} disabled={busy} style={{ ...(isNew ? primaryBtn : btn(false)), opacity: busy ? 0.6 : 1 }}>{busy ? '…' : isNew ? 'Добавить' : 'Сохранить'}</button>
        : <span />}
      <span style={{ gridColumn: '1 / -1', marginTop: -4, fontSize: 11.5, color: 'var(--text-muted)' }}>
        свободно <b style={{ fontFamily: MONO, color: free < 0 ? 'var(--danger-fg)' : 'var(--accent-fg)' }}>{grp0(free)} ₽</b>
      </span>
    </div>
  )
}

export default function CreditLines({ banks }) {
  const [lines, setLines] = useState([])
  const [forms, setForms] = useState({})
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState('')
  const [canEdit, setCanEdit] = useState(false)

  const load = async () => {
    try {
      const r = await api.get('/settings/credit-lines', auth())
      setLines(r.data)
      setForms(Object.fromEntries(r.data.map(c => [c.id, toForm(c)])))
      setErr('')
    } catch (e) { setErr(e.response?.data?.detail || 'Кредитные линии не загрузились') }
  }
  useEffect(() => { setCanEdit(can(getPermissions(), 'settings_balances', 'edit')); load() }, [])

  const save = async (id) => {
    setBusy(id ?? 'new')
    try {
      if (id) await api.put(`/settings/credit-lines/${id}`, toBody(forms[id]), auth())
      else { await api.post('/settings/credit-lines', toBody(draft), auth()); setDraft(null) }
      await load()
    } catch (e) {
      const d = e.response?.data?.detail
      alert(typeof d === 'string' ? d : 'Не сохранилось')
    } finally { setBusy(null) }
  }

  return (
    <div style={{ ...card, padding: '20px 22px', marginTop: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 16, fontWeight: 700 }}>Кредитные линии</span>
        <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>свободный остаток лимита показывается в «Деньгах на сегодня» над планом оплат</span>
        {canEdit && !draft && !!banks.length && <button onClick={() => setDraft({ ...EMPTY, bank: banks[0] })} style={{ ...btn(false), marginLeft: 'auto' }}>+ Добавить линию</button>}
      </div>
      {err && <span style={{ color: 'var(--danger-fg)', fontSize: 13 }}>{err}</span>}
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10 }}>
        {['Банк', 'Лимит', 'Выбрано', 'На дату', 'Примечание', '', ''].map((h, i) => <span key={i} style={LABEL}>{h}</span>)}
      </div>
      {lines.map(c => forms[c.id] && (
        <Row key={c.id} form={forms[c.id]} setForm={f => setForms(p => ({ ...p, [c.id]: f }))}
          banks={banks} onSave={() => save(c.id)} busy={busy === c.id} canEdit={canEdit} />
      ))}
      {draft && <Row isNew banks={banks} form={draft} setForm={setDraft} onSave={() => save(null)} busy={busy === 'new'} canEdit={canEdit} />}
      {!lines.length && !draft && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Линий нет — в «Деньгах на сегодня» кредит не учитывается.</span>}
    </div>
  )
}
