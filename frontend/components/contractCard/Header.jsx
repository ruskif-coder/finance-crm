/**
 * Шапка карточки договора (хендофф «договорZ»): номер, дата, плашки, кнопки; сетка полей в 6 колонок; плашка «СК по договору».
 * Режим правки (право «Договоры → правка»): поля договора — инпуты; контрагент и наше юрлицо не правятся (меняются в их карточках),
 * вид документа — тоже (у поля нет писателя); подписанты — только в «Сторонах». Сохраняет только изменённое (`PUT /contracts/{id}`).
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/http'
import { errText } from '@/lib/loadError'
import safeHref from '@/lib/safeHref'
import { MONO } from '@/components/salesTableKit'
import { fmtDateFull } from '@/lib/salesFormat'
import { ISSUE_CHANNELS, PAYMENT_TERM_CONDITIONS, PROLONGATION_OPTIONS } from '@/lib/contractTerms'
import { box, cap, btnGhost, btnPrimary, Pill, Notice, link, fieldInp } from '@/components/contractCard/ui'

const EDITABLE = ['services', 'payment_term_days', 'payment_term_condition', 'end_date_text', 'prolongation', 'issue_channel', 'marketing_name', 'note']
const locked = { display: 'flex', alignItems: 'center', height: 32, padding: '0 9px', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 8, fontSize: 12.5, fontWeight: 600, color: 'var(--text-muted)', overflow: 'hidden', whiteSpace: 'nowrap' }
const valueStyle = { fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const pencil = 'M4 20h4l10-10-4-4L4 16v4z'
const down = 'M12 4v12M7 11l5 5 5-5M5 20h14'

const Icon = ({ d }) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>

function Cell({ label, children }) {
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span style={cap}>{label}</span>{children}
    </span>
  )
}

function Select({ value, options, onChange }) {
  const list = options.includes(value) || !value ? options : [value, ...options]
  return (
    <select value={value || ''} onChange={e => onChange(e.target.value)} style={fieldInp}>
      <option value="">—</option>
      {list.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

// Услуги договора — из каталога услуг продаж (владелец 28.10.2026: «просто прикреплять из списка»): хранятся названиями через запятую
// в `contracts.services`. Значение не из каталога (переименовали или убрали) остаётся фишкой и снимается кликом.
const SEP = ', '
const splitServices = (v) => (v || '').split(',').map(x => x.trim()).filter(Boolean)

function ServicesPicker({ value, catalog, onChange }) {
  const on = splitServices(value)
  const list = [...catalog, ...on.filter(x => !catalog.includes(x))]
  const toggle = (n) => onChange((on.includes(n) ? on.filter(x => x !== n) : list.filter(x => x === n || on.includes(x))).join(SEP))
  return (
    <span style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {list.map(n => {
        const sel = on.includes(n)
        return (
          <button key={n} type="button" onClick={() => toggle(n)}
                  style={{ height: 24, padding: '0 8px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11.5, fontWeight: sel ? 700 : 500,
                           border: `1px solid ${sel ? 'var(--accent-border)' : 'var(--border-card)'}`, background: sel ? 'var(--accent-tint)' : 'var(--bg-card)',
                           color: sel ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>{n}</button>
        )
      })}
    </span>
  )
}

function SkPlaque({ sk, onClick }) {
  return (
    <span onClick={onClick} title="Правила СК договора — блок «Агентские условия»"
          style={{ flex: '0 0 200px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6, padding: '10px 14px', background: 'var(--violet-tint)', border: '1px solid var(--violet-border)', borderRadius: 12, cursor: 'pointer' }}>
      <span style={{ ...cap, display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, color: 'var(--violet-fg)' }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--violet-fg)' }} />СК по договору
      </span>
      {sk ? (
        <>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, lineHeight: 1, color: 'var(--violet-fg)' }}>{sk.percent} %</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--violet-fg)' }}>{sk.mode}</span>
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.35 }}>
            {sk.scope === 'договор' ? 'на договор' : `по ${sk.scope === 'агентство' ? 'агентству' : 'рекламодателю'}`}
            {sk.agency ? ` · агентство «${sk.agency}»` : sk.advertiser ? ` · рекламодатель «${sk.advertiser}» напрямую` : ''}
            {sk.brand_rules ? ` · +${sk.brand_rules} по бренду` : ''}
          </span>
        </>
      ) : <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>условие СК не задано</span>}
    </span>
  )
}

// editRequest — счётчик: проверка готовности просит открыть режим правки (канал выдачи, срок договора).
// onEditChange — режим правки включён/выключен (в нём же правятся должность и основание подписантов в «Сторонах», владелец 28.10.2026);
// extraSave — сохранить их вместе с полями договора одной кнопкой.
export default function Header({ c, sk, showSk, canEdit, onSaved, onSk, onFile, editRequest = 0, onEditChange, extraSave }) {
  const [edit, setEdit] = useState(null)          // null — просмотр; объект — правка
  const [catalog, setCatalog] = useState([])      // названия услуг каталога — грузятся при входе в правку
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const open = (v) => { setEdit(v); if (onEditChange) onEditChange(!!v) }
  const start = () => {
    setErr(''); open(Object.fromEntries(EDITABLE.map(k => [k, c[k] ?? ''])))
    if (!catalog.length) api.get('/sales/directories/services?only_active=true', auth())
      .then(r => setCatalog((r.data.items || []).map(x => x.name))).catch(e => setErr(errText(e)))
  }
  useEffect(() => { if (editRequest && canEdit) start() }, [editRequest])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (v) => setEdit({ ...edit, [k]: v })
  const save = async () => {
    const sent = {}
    for (const k of EDITABLE) {
      const was = c[k] ?? '', now = edit[k]
      if (String(was) !== String(now)) sent[k] = k === 'payment_term_days' ? (now === '' ? null : Number(now)) : (now === '' ? null : now)
    }
    setBusy(true); setErr('')
    try {
      if (Object.keys(sent).length) await api.put(`/contracts/${c.id}`, sent, auth())
      if (extraSave) await extraSave()
      open(null); await onSaved()
    }
    catch (e) { setErr(errText(e)) }
    finally { setBusy(false) }
  }
  const docHref = safeHref(c.document_link)
  const text = (k) => edit ? <input value={edit[k] ?? ''} onChange={e => set(k)(e.target.value)} style={fieldInp} /> : <span title={c[k] || ''} style={valueStyle}>{c[k] || '—'}</span>
  const pay = [c.payment_term_days != null ? `${c.payment_term_days} дн.` : null, c.payment_term_condition].filter(Boolean).join(' · ')
  return (
    <section style={{ ...box, border: `1px solid ${edit ? 'var(--accent-border)' : 'var(--border-card)'}`, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>Договор № <span style={{ fontFamily: MONO }}>{c.contract_number || '—'}</span></span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>от {fmtDateFull(c.contract_date)}</span>
        {c.cooperation_format && <Pill tone="accent">{c.cooperation_format}</Pill>}
        {c.ord_kind && <Pill tone="income">{c.ord_kind === 'outer' ? 'расходный' : 'доходный'}</Pill>}
        {(c.issue_channel || c.edo_status) && <Pill tone="violet">{[c.issue_channel, c.edo_status].filter(Boolean).join(' · ')}</Pill>}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, flex: '0 0 auto' }}>
          {canEdit && !edit && <button type="button" onClick={start} style={btnPrimary}><Icon d={pencil} />Редактировать</button>}
          {edit && <button type="button" onClick={() => open(null)} style={btnGhost}>Отмена</button>}
          {edit && <button type="button" onClick={save} disabled={busy} style={btnPrimary}>{busy ? 'Сохраняю…' : 'Сохранить'}</button>}
          {docHref && <a href={docHref} target="_blank" rel="noopener noreferrer" style={btnGhost}>Документ ↗</a>}
          {c.attached_filename && <button type="button" onClick={onFile} style={btnGhost}><Icon d={down} />Скачать файл</button>}
        </span>
      </div>
      {edit && <Notice tone="accent">Режим правки · контрагент и наше юрлицо меняются в их карточках; должность и основание подписантов — в блоке «Стороны»</Notice>}
      {err && <Notice tone="danger">{err}</Notice>}
      <div style={{ display: 'flex', gap: 20, alignItems: 'stretch', paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
        <div style={{ flex: '1 1 0', minWidth: 0, display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: '12px 20px' }}>
          <Cell label="Контрагент">
            {edit ? <span title="Меняется в карточке контрагента" style={locked}>{c.counterparty ? c.counterparty.name : c.counterparty_name}</span>
              : c.counterparty ? <Link href={`/directory/counterparties/${c.counterparty.id}`} style={{ ...valueStyle, ...link }}>{c.counterparty.name}</Link>
                : <span style={valueStyle}>{c.counterparty_name || '—'}</span>}
            {!edit && c.inn && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>ИНН {c.inn}</span>}
          </Cell>
          <Cell label="Наше юрлицо">{edit ? <span title="Меняется в карточке юрлица" style={locked}>{c.own_company_name || '—'}</span> : <span style={valueStyle}>{c.own_company_name || '—'}</span>}</Cell>
          <Cell label="Услуги">{edit ? <ServicesPicker value={edit.services} catalog={catalog} onChange={set('services')} />
            : <span title={c.services || ''} style={valueStyle}>{c.services || '—'}</span>}</Cell>
          <Cell label="Оплата · отсрочка">
            {edit ? (
              <span style={{ display: 'flex', gap: 6 }}>
                <input value={edit.payment_term_days ?? ''} onChange={e => set('payment_term_days')(e.target.value.replace(/\D/g, ''))} placeholder="дн." style={{ ...fieldInp, width: 56, flex: '0 0 56px', textAlign: 'right' }} />
                <Select value={edit.payment_term_condition} options={PAYMENT_TERM_CONDITIONS} onChange={set('payment_term_condition')} />
              </span>
            ) : <span title={pay} style={valueStyle}>{pay || '—'}</span>}
          </Cell>
          <Cell label="Срок">{text('end_date_text')}</Cell>
          <Cell label="Пролонгация">{edit ? <Select value={edit.prolongation} options={PROLONGATION_OPTIONS} onChange={set('prolongation')} /> : <span style={valueStyle}>{c.prolongation || '—'}</span>}</Cell>
          <Cell label="Выдача ДС">{edit ? <Select value={edit.issue_channel} options={ISSUE_CHANNELS} onChange={set('issue_channel')} /> : <span style={valueStyle}>{c.issue_channel || '—'}</span>}</Cell>
          <Cell label="Маркетинговое название">{text('marketing_name')}</Cell>
          <Cell label="Примечание">{text('note')}</Cell>
        </div>
        {showSk && <SkPlaque sk={sk} onClick={onSk} />}
      </div>
    </section>
  )
}
