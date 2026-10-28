/**
 * Подписанты юрлица (владелец 28.10.2026): их несколько, один — по умолчанию (★); у доверенности — срок. Договор выбирает своего
 * подписанта из этого списка (карточка договора → «Стороны»), без выбора — подписант по умолчанию. Правка — право «Контрагенты → правка».
 */
import { useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, inpSm, btnSm } from '@/components/salesTableKit'
import { fmtDateFull } from '@/lib/salesFormat'
import { daysUntil } from '@/lib/dates'

const EMPTY = { director_name: '', signer_position: '', signer_basis: '', valid_until: '' }
const expired = (s) => !!s.valid_until && daysUntil(String(s.valid_until).slice(0, 10)) < 0

function Form({ init, busy, onSave, onCancel }) {
  const [f, setF] = useState({ ...EMPTY, ...init, valid_until: init && init.valid_until ? String(init.valid_until).slice(0, 10) : '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const ok = !!f.director_name.trim()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 0', borderTop: '1px solid var(--border-row)' }}>
      <input value={f.director_name} onChange={set('director_name')} placeholder="ФИО полностью: Иванов Иван Иванович" style={inpSm('100%')} />
      <input value={f.signer_position} onChange={set('signer_position')} placeholder="Должность: Генеральный директор" style={inpSm('100%')} />
      <input value={f.signer_basis} onChange={set('signer_basis')} placeholder="Основание: Устава / доверенности № 5 от 01.01.2026" style={inpSm('100%')} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
        доверенность до <input type="date" value={f.valid_until} onChange={set('valid_until')} style={inpSm(150)} />
        <span style={{ color: 'var(--text-faint)' }}>пусто — бессрочно</span>
      </label>
      <span style={{ display: 'flex', gap: 8 }}>
        <button type="button" disabled={!ok || busy} onClick={() => onSave({ ...f, valid_until: f.valid_until || null })} style={{ ...btnSm(true), opacity: ok ? 1 : 0.5 }}>
          {busy ? 'Сохраняю…' : 'Сохранить'}
        </button>
        <button type="button" onClick={onCancel} style={btnSm(false)}>Отмена</button>
      </span>
    </div>
  )
}

function Row({ s, canEdit, onEdit, onDefault, onArchive }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '9px 0', borderTop: '1px solid var(--border-row)', opacity: s.is_archived ? 0.55 : 1 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        {s.is_default && <span title="по умолчанию" style={{ color: 'var(--warning)' }}>★</span>}
        <b style={{ fontSize: 13 }}>{s.director_name || '—'}</b>
        {s.is_archived && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>в архиве</span>}
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.signer_position || 'должность не указана'} · на основании {s.signer_basis || '—'}</span>
      {s.valid_until && (
        <span style={{ fontFamily: MONO, fontSize: 11, color: expired(s) ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
          {expired(s) ? 'доверенность истекла ' : 'до '}{fmtDateFull(s.valid_until)}
        </span>
      )}
      {canEdit && (
        <span style={{ display: 'flex', gap: 10, fontSize: 11.5, paddingTop: 2 }}>
          <a onClick={onEdit} style={{ cursor: 'pointer' }}>изменить</a>
          {!s.is_default && !s.is_archived && <a onClick={onDefault} style={{ cursor: 'pointer' }}>★ по умолчанию</a>}
          {!s.is_default && <a onClick={onArchive} style={{ cursor: 'pointer', color: 'var(--text-muted)' }}>{s.is_archived ? 'из архива' : 'в архив'}</a>}
        </span>
      )}
    </div>
  )
}

export default function SignersPanel({ counterpartyId, signers, canEdit, onChange }) {
  const [edit, setEdit] = useState(null)          // null | 'new' | id подписанта
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); setEdit(null); await onChange() }
    catch (e) { setErr((e.response && e.response.data && e.response.data.detail) || 'Не удалось сохранить подписанта') }
    finally { setBusy(false) }
  }
  const list = signers || []
  return (
    <div>
      {err && <div style={{ fontSize: 12, color: 'var(--danger-fg)', paddingBottom: 6 }}>{err}</div>}
      {!list.length && edit !== 'new' && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Подписантов нет — без подписанта ДС не выгрузится.</span>}
      {list.map(s => (edit === s.id
        ? <Form key={s.id} init={s} busy={busy} onCancel={() => setEdit(null)} onSave={f => run(() => api.put(`/signers/${s.id}`, f, auth()))} />
        : <Row key={s.id} s={s} canEdit={canEdit} onEdit={() => setEdit(s.id)}
               onDefault={() => run(() => api.put(`/signers/${s.id}/default`, {}, auth()))}
               onArchive={() => run(() => api.put(`/signers/${s.id}/archive`, { on: !s.is_archived }, auth()))} />))}
      {edit === 'new' && <Form busy={busy} onCancel={() => setEdit(null)} onSave={f => run(() => api.post(`/signers/counterparty/${counterpartyId}`, f, auth()))} />}
      {canEdit && edit !== 'new' && (
        <button type="button" onClick={() => setEdit('new')} style={{ ...btnSm(false), marginTop: 8 }}>+ Подписант</button>
      )}
    </div>
  )
}
