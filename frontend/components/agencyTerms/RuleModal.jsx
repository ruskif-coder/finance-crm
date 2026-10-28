// Конструктор правила СК (владелец 27.10.2026: «чем больше условий задано — тем точнее расчёт»). Признаки необязательны;
// сделке подходит правило, чьи заданные признаки с ней совпадают, побеждает самое точное. Проверки ввода и спор правил
// одинаковой точности — на сервере (`app/agency_terms/rules.py`), окно показывает его ответ как есть.
import { useState } from 'react'
import api, { auth } from '@/lib/http'
import { Modal, MONO, Seg, btn, inp } from '@/components/salesTableKit'
import { defaultValidFrom, MODES, parsePct, specificity } from '@/lib/agencyTerms.mjs'
import { plural } from '@/lib/publisherRecon.mjs'
import { todayMsk } from '@/lib/dates'
import { Field, Pick } from './kit'

export default function RuleModal({ rule, opts, canEdit, onClose, onSaved }) {
  const [r, setR] = useState({ valid_from: defaultValidFrom(todayMsk()), valid_to: null, note: '', ...rule,
    percent: rule.percent != null ? String(rule.percent).replace('.', ',') : '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (v) => setR((x) => ({ ...x, [k]: v }))
  const main = r.kind === 'основная'
  const contracts = (opts.contracts || []).map((c) => ({ id: c.id, name: `${c.counterparty} · ${c.number || 'без номера'}` }))
  const brands = (opts.brands || []).filter((b) => !r.advertiser_id || b.advertiser_id === r.advertiser_id)
  const pct = parsePct(r.percent)
  // Партнёрская — своими ручками и по праву «спец. условия» (хендофф 27.10.2026)
  const base = main ? '/agency-terms/rules' : '/agency-terms/special/partner'
  const ready = pct != null && !!r.valid_from && (main ? r.contract_id != null && (r.agency_id != null || r.advertiser_id != null)
    : r.recipient_id != null && specificity(r) > 0)

  const save = async () => {
    setBusy(true); setErr('')
    const body = { ...r, percent: pct, valid_to: r.valid_to || null }
    try {
      const res = r.id ? await api.put(`${base}/${r.id}`, body, auth()) : await api.post(base, body, auth())
      onSaved(res.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm('Удалить правило? Если оно уже в закрытом месяце, сервер откажет — тогда закройте его датой «по».')) return
    setBusy(true); setErr('')
    try { await api.delete(`${base}/${r.id}`, auth()); onSaved(null) } catch (e) { setErr(e.response?.data?.detail || 'Не удалось удалить') } finally { setBusy(false) }
  }

  const title = `${r.id ? 'Правило' : 'Новое правило'} · ${main ? 'основная СК' : 'партнёрская СК'}`
  const footer = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
      <span style={{ fontSize: 12, color: err ? 'var(--danger-fg)' : 'var(--text-muted)', flex: 1 }}>
        {err || `точность: ${specificity(r)} ${plural(specificity(r), 'признак', 'признака', 'признаков')} — чем больше, тем правило главнее`}</span>
      {!!r.id && canEdit && <button type="button" disabled={busy} onClick={remove} style={{ ...btn(false), color: 'var(--danger-fg)' }}>Удалить</button>}
      <button type="button" onClick={onClose} disabled={busy} style={btn(false)}>{canEdit ? 'Отмена' : 'Закрыть'}</button>
      {canEdit && <button type="button" onClick={save} disabled={busy || !ready} style={{ ...btn(true), opacity: busy || !ready ? 0.5 : 1 }}>Сохранить</button>}
    </div>
  )
  return (
    <Modal title={title} width={720} footer={footer} onClose={() => { if (!busy) onClose() }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, padding: '6px 0 10px' }}>
        <Field label={main ? 'Договор закрытия *' : 'Договор'} hint={main ? 'юрлицо — контрагент договора' : null}>
          <Pick value={r.contract_id} onChange={set('contract_id')} list={contracts} empty={main ? '— выберите —' : '— любой —'} disabled={!canEdit} />
        </Field>
        {main
          ? <div style={{ alignSelf: 'end', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45 }}>
            Основная СК — в связке с договором: нужно агентство, а при прямом договоре — рекламодатель. Бренд и услуга
            уточняют условие для части сделок.</div>
          : <Field label="Получатель выплаты *" hint="партнёрская — отдельная выплата">
            <Pick value={r.recipient_id} onChange={set('recipient_id')} list={opts.counterparties || []} empty="— выберите —" disabled={!canEdit} />
          </Field>}
        <Field label="Агентство">
          <Pick value={r.agency_id} onChange={set('agency_id')} list={opts.agencies || []} empty="— любое —" disabled={!canEdit} />
        </Field>
        <Field label="Рекламодатель (производитель)">
          <Pick value={r.advertiser_id} onChange={(v) => setR((x) => ({ ...x, advertiser_id: v, brand_id: null }))} list={opts.advertisers || []} empty="— любой —" disabled={!canEdit} />
        </Field>
        <Field label="Бренд" hint={r.advertiser_id ? null : 'выберите рекламодателя, чтобы сузить список'}>
          <Pick value={r.brand_id} onChange={set('brand_id')} list={brands} empty="— любой —" disabled={!canEdit} />
        </Field>
        <Field label="Услуга">
          <Pick value={r.service_id} onChange={set('service_id')} list={opts.services || []} empty="— любая —" disabled={!canEdit} />
        </Field>
        <Field label="Способ *">
          <Seg value={r.mode} opts={MODES.map((m) => [m, m])} onPick={set('mode')} disabled={() => !canEdit} />
        </Field>
        <Field label="СК, % *" hint={r.percent !== '' && pct == null ? 'число от 0 до 100' : null}>
          <input value={r.percent} onChange={(e) => set('percent')(e.target.value)} disabled={!canEdit} inputMode="decimal"
            style={{ ...inp, width: 120, fontFamily: MONO, textAlign: 'right' }} />
        </Field>
        <Field label="Действует с *">
          <input type="date" value={r.valid_from || ''} onChange={(e) => set('valid_from')(e.target.value)} disabled={!canEdit} style={inp} />
        </Field>
        <Field label="Действует по" hint="пусто — бессрочно; смена условий — закройте старое правило датой «по»">
          <input type="date" value={r.valid_to || ''} onChange={(e) => set('valid_to')(e.target.value || null)} disabled={!canEdit} style={inp} />
        </Field>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="Примечание">
            <input value={r.note || ''} onChange={(e) => set('note')(e.target.value)} disabled={!canEdit} style={{ ...inp, width: '100%' }} />
          </Field>
        </div>
      </div>
    </Modal>
  )
}
