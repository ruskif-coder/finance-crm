/**
 * Ступень «Плательщик»: выбор юрлица агентства, привязка чужого, заведение нового.
 *
 * Список начинается с юрлиц, уже привязанных к агентству сделки, а поиск идёт по всему
 * справочнику: 57 из 92 агентств не имеют ни одного привязанного (мерено 26.08.2026),
 * и без поиска ступень у них была бы пустой формой без вариантов.
 *
 * У каждой строки видно, есть ли договор и помечен ли он ОРД. Без этого выбор делается
 * вслепую и упирается в следующую ступень — человек узнаёт о тупике уже после решения.
 */
import { useEffect, useState } from 'react'
import { Modal, UI, MONO } from '../salesTableKit'
import api, { auth } from '../../lib/http'
import { CreatePanel, Field, PickRow, Tag, useCreateForm, INPUT } from './pickers'

export default function PayerPicker({ dealId, chosenId, onDone, onClose }) {
  const [items, setItems] = useState(null)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const form = useCreateForm({ name: '', inn: '', address: '' })

  const load = (text) => {
    setErr('')
    api.get(`/ord/deal/${dealId}/payer-options${text ? `?q=${encodeURIComponent(text)}` : ''}`, auth())
      .then(r => setItems(r.data.items || []))
      .catch(e => setErr(e.response?.data?.detail || 'Не удалось загрузить список'))
  }
  useEffect(() => { load('') }, [dealId])
  // Поиск с задержкой: справочник контрагентов большой, запрос на каждую букву
  // и лишний, и мигает списком.
  useEffect(() => {
    const t = setTimeout(() => load(q.trim()), q.trim() ? 300 : 0)
    return () => clearTimeout(t)
  }, [q])

  const pick = async (cp) => {
    setErr('')
    try {
      await api.put(`/ord/deal/${dealId}/payer`, { counterparty_id: cp.id }, auth())
      onDone()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось назначить плательщика') }
  }

  const create = (data) =>
    api.post(`/ord/deal/${dealId}/payer`, data, auth()).then(() => onDone())

  const linked = (items || []).filter(i => i.agency_linked)
  const others = (items || []).filter(i => !i.agency_linked)

  return (
    <Modal title="Плательщик" width={720} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: UI }}>
        <input value={q} onChange={e => setQ(e.target.value)} style={INPUT}
          placeholder="Поиск по всему справочнику — название или начало ИНН" />

        {!!err && <div style={{ fontSize: 12.5, color: 'var(--danger)' }}>{err}</div>}
        {items === null && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</div>}

        <Group title="Юрлица агентства" empty="У агентства не привязано ни одного юрлица — найдите поиском или заведите новое."
          rows={linked} chosenId={chosenId} onPick={pick} />
        {!!others.length && (
          <Group title="Найдено в справочнике" note="выбор привяжет юрлицо к агентству"
            rows={others} chosenId={chosenId} onPick={pick} />
        )}

        <CreatePanel label="Завести юрлицо" open={form.open} onToggle={form.toggle}
          error={form.err} busy={form.busy} submitLabel="Завести и назначить плательщиком"
          note="Все три поля обязательны: без ИНН и адреса ЕРИД не выпустить, а выясняется это на сдаче отчётности. Юрлицо сразу привяжется к агентству сделки."
          onSubmit={() => form.submit(create)}>
          <Field label="Название" value={form.data.name} onChange={form.set('name')}
            placeholder="ООО «Ромашка»" width="1 1 100%" />
          <Field label="ИНН" value={form.data.inn} onChange={form.set('inn')} placeholder="7700000000" />
          <Field label="Юридический адрес" value={form.data.address} onChange={form.set('address')}
            placeholder="г. Москва, ул. …" width="2 1 260px" />
        </CreatePanel>
      </div>
    </Modal>
  )
}

function Group({ title, note, empty, rows, chosenId, onPick }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9 }}>
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em',
          textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-muted)' }}>{title}</span>
        {!!note && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{note}</span>}
      </span>
      {!rows.length
        ? <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{empty || '—'}</span>
        : rows.map(cp => (
          <PickRow key={cp.id} chosen={cp.id === chosenId} onPick={() => onPick(cp)}
            title={cp.name}
            meta={[cp.inn ? `ИНН ${cp.inn}` : 'ИНН не указан',
              cp.address ? null : 'адреса нет'].filter(Boolean).join(' · ')}
            right={cp.ord_contracts
              ? <Tag ok title="У юрлица есть договор с отметкой ОРД">договор ОРД есть</Tag>
              : <Tag title={cp.contracts
                ? 'Договор есть, но без отметки ОРД — ЕРИД по нему не выпустить'
                : 'У юрлица нет ни одного договора'}>
                {cp.contracts ? 'без отметки ОРД' : 'нет договора'}
              </Tag>} />
        ))}
    </div>
  )
}
