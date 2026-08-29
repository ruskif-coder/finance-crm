/**
 * Ступень «Доходный договор»: выбор договора плательщика и заведение нового.
 *
 * Показываются ВСЕ договоры плательщика, не только помеченные ОРД: отметку ставит
 * человек, и у 16 из 40 юрлиц агентств помеченного договора нет, хотя договор есть
 * (мерено 26.08.2026). Список из одних помеченных был бы пустым там, где выбирать
 * есть из чего.
 *
 * Идентификатор ОРД не выдумывается. Он приходит из кабинета, и пока договор туда не
 * заведён — поле пустое, а строка честно говорит, что ЕРИД по нему не выпустить.
 */
import { useEffect, useState } from 'react'
import { Modal, UI, MONO, btnSm } from '../salesTableKit'
import { fmtDateFull } from '../../lib/salesFormat'
import api, { auth } from '../../lib/http'
import { CreatePanel, Field, PickRow, SelectField, Tag, useCreateForm } from './pickers'
import { PAYMENT_TERM_CONDITIONS } from '../../lib/contractTerms'

export default function FinalPicker({ dealId, onDone, onClose }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const form = useCreateForm({ number: '', date: '', payment_term_days: '',
    payment_term_condition: '' })
  // Тот же список, что в карточке договора: значение уезжает в акт ОРД, и две
  // разошедшиеся копии дали бы разное условие на один договор.
  const CONDITIONS = PAYMENT_TERM_CONDITIONS.map(v => ({ code: v, label: v }))

  const load = () => {
    setErr('')
    api.get(`/ord/deal/${dealId}/final-options`, auth())
      .then(r => setData(r.data))
      .catch(e => setErr(e.response?.data?.detail || 'Не удалось загрузить договоры'))
  }
  useEffect(() => { load() }, [dealId])

  const pick = async (id) => {
    setErr('')
    try {
      await api.put(`/ord/deal/${dealId}/final`, { contract_id: id }, auth())
      onDone()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось выбрать договор') }
  }

  const create = (d) => api.post(`/ord/deal/${dealId}/final`, {
    ...d, payment_term_days: parseInt(d.payment_term_days, 10) || 0,
  }, auth()).then(() => onDone())

  const items = (data && data.items) || []

  return (
    <Modal title={`Доходный договор${data && data.payer ? ` — ${data.payer.name}` : ''}`}
      width={760} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: UI }}>
        {!!err && <div style={{ fontSize: 12.5, color: 'var(--danger)' }}>{err}</div>}
        {data === null && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</div>}
        {data && !data.payer && (
          <div style={{ fontSize: 13, color: 'var(--warning-text)' }}>
            Сначала определите плательщика — договор заводится с ним.
          </div>
        )}

        {!!items.length && items.map(c => {
          const [ok, total, missing] = c.fill || [0, 0, '']
          const full = ok === total
          return (
            <PickRow key={c.id} chosen={c.id === (data && data.chosen_id)} onPick={() => pick(c.id)}
              title={c.number || 'без номера'}
              meta={[c.date ? `от ${fmtDateFull(c.date)}` : 'без даты',
                full ? null : `не заполнено: ${missing}`].filter(Boolean).join(' · ')}
              right={c.ord_contract_id
                ? <Tag ok title="Договор связан с ОРД">отметка ОРД</Tag>
                : <Tag title="Договор заведён у нас, но не связан с кабинетом ОРД — ЕРИД по нему не выпустить">
                  не в ОРД
                </Tag>} />
          )
        })}
        {data && data.payer && !items.length && (
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
            У плательщика нет ни одного договора — заведите его здесь.
          </span>
        )}

        {!!(data && data.chosen_id) && (
          <div>
            <button type="button" onClick={() => pick(null)} style={btnSm(false)}>
              снять выбор и вернуть автоподбор
            </button>
          </div>
        )}

        {!!(data && data.payer) && (
          <CreatePanel label="Завести договор" open={form.open} onToggle={form.toggle}
            error={form.err} busy={form.busy} submitLabel="Завести и выбрать"
            note="Срок и условие оплаты обязательны: без них акт в ОРД не сдать."
            onSubmit={() => form.submit(create)}>
            <Field label="Номер договора" value={form.data.number} onChange={form.set('number')}
              placeholder="ПМ-01/2026" />
            <Field label="Дата договора" type="date" value={form.data.date} onChange={form.set('date')} />
            <Field label="Срок оплаты, дней" value={form.data.payment_term_days}
              onChange={form.set('payment_term_days')} placeholder="60" width="0 1 140px" />
            <SelectField label="Условие оплаты" value={form.data.payment_term_condition}
              onChange={form.set('payment_term_condition')} options={CONDITIONS} />
            {/* Идентификатор ОРД руками не вводится: его выдаёт ОРД. Договор заводится
                без него и получает его сам — регистрацией по API (появится с доступом)
                либо следующей загрузкой выгрузки: импортёр ищет наш договор по номеру
                с уточнением по ИНН среди тех, у кого идентификатора ещё нет. */}
            <span style={{ flex: '1 1 100%', fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Идентификатор ОРД проставится сам — регистрацией договора в ОРД по API либо
              при следующей загрузке выгрузки кабинета. Пока его нет, ЕРИД по договору
              не выпустить, и ступень скажет об этом прямо.
            </span>
          </CreatePanel>
        )}

        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
          textTransform: 'uppercase', color: 'var(--text-faint)' }}>
          выбор побеждает автоподбор · снятие возвращает его
        </span>
      </div>
    </Modal>
  )
}
