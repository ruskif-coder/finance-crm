/**
 * Выбор изначального договора: под доходным сделки, поиском по всему зеркалу ОРД,
 * или заведением того, которого в кабинете ещё нет.
 *
 * Почему одного списка «под доходным» мало. Связи приходят из выгрузки и описывают
 * ЧУЖИЕ цепочки, висящие на том же нашем договоре: у сделки HCLA6E под её доходным
 * лежат семь договоров, и ни один не относится к рекламодателю сделки. Список при этом
 * полный и бесполезный одновременно. Плюс в зеркале встречаются двойники — у одного
 * рекламодателя два договора, один связан с нашим доходным, другой нет.
 *
 * Строки вне связей выгрузки помечены и привязываются только осознанно: отсутствие
 * связи означает, что в кабинете такой цепочки нет, и молча собранная она уехала бы
 * в ЕРИР. Запрет снимается подтверждением, а не исчезает.
 *
 * Заведённый здесь договор — НЕ зеркало кабинета: `origin='manual'` и местный
 * идентификатор вместо ордшного. Смешивать его со 126 зеркальными нельзя — иначе
 * следующая загрузка выгрузки сочтёт его пришедшим оттуда и не подменит идентификатор.
 */
import { useEffect, useState } from 'react'
import { Modal, UI, MONO } from '../salesTableKit'
import { fmtDateFull } from '../../lib/salesFormat'
import api, { auth } from '../../lib/http'
import { CreatePanel, Field, FieldRow, PickRow, SelectField, Tag, useCreateForm, INPUT } from './pickers'

export default function InitialPicker({ dealId, onPick, onDone, onClose }) {
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [confirm, setConfirm] = useState(null)   // строка вне связей, ждущая подтверждения
  const [enums, setEnums] = useState({})
  const form = useCreateForm({ number: '', date: '', advertiser_inn: '', advertiser_name: '',
    contractor_inn: '', contractor_name: '', type: '', subject_type: '', action_type: '' })

  const load = (text) => {
    setErr('')
    api.get(`/ord/deal/${dealId}/initial-options${text ? `?q=${encodeURIComponent(text)}` : ''}`, auth())
      .then(r => setData(r.data))
      .catch(e => setErr(e.response?.data?.detail || 'Не удалось загрузить список'))
  }
  useEffect(() => { load('') }, [dealId])
  // Поиск с задержкой: в зеркале 126 договоров, запрос на каждую букву мигает списком.
  useEffect(() => {
    const t = setTimeout(() => load(q.trim()), q.trim() ? 300 : 0)
    return () => clearTimeout(t)
  }, [q])
  useEffect(() => {
    api.get('/ord/enums', auth()).then(r => setEnums(r.data || {})).catch(() => {})
  }, [])

  const create = (d) => api.post(`/ord/deal/${dealId}/initial`, d, auth()).then(() => onDone())

  const items = (data && data.items) || []
  const linked = items.filter(i => i.linked)
  const others = items.filter(i => !i.linked)

  return (
    <Modal title="Изначальный договор" width={880} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: UI }}>
        <input value={q} onChange={e => setQ(e.target.value)} style={INPUT}
          placeholder="Поиск по всему зеркалу ОРД — рекламодатель, исполнитель, номер или ИНН" />

        {!!err && <div style={{ fontSize: 12.5, color: 'var(--danger)' }}>{err}</div>}
        {data === null && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</div>}

        <Group title={`Под доходным договором${data && data.final && data.final.number ? ` ${data.final.number}` : ''}`}
          note="связи из выгрузки ОРД"
          empty="Под доходным договором сделки нет ни одной связи из выгрузки."
          rows={linked} chosenId={data && data.chosen_id} onPick={c => onPick(c.id, false)} />

        {!!others.length && (
          <Group title="Найдено в зеркале ОРД" note="вне связей выгрузки — нужно подтверждение"
            rows={others} chosenId={data && data.chosen_id} onPick={c => setConfirm(c)} />
        )}

        {!!confirm && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9, padding: '13px 15px',
            border: '1px solid var(--warning-border)', background: 'var(--warning-tint)', borderRadius: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning-text)' }}>
              Привязать вне связей выгрузки?
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              В выгрузке ОРД договор «{confirm.number || 'б/н'}»
              ({confirm.advertiser?.name || 'рекламодатель не указан'}) не привязан к доходному
              договору сделки. Значит в кабинете такой цепочки нет — либо выгрузка неполная,
              либо цепочка другая. В журнал запишется отдельной строкой.
            </span>
            <span style={{ display: 'flex', gap: 10 }}>
              <button type="button" onClick={() => setConfirm(null)}
                style={{ height: 32, padding: '0 14px', borderRadius: 9, border: '1px solid var(--border-card)',
                  background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 12.5,
                  cursor: 'pointer', fontFamily: UI }}>Отмена</button>
              <button type="button" onClick={() => { const c = confirm; setConfirm(null); onPick(c.id, true) }}
                style={{ height: 32, padding: '0 16px', borderRadius: 9, border: 'none',
                  background: 'var(--warning)', color: 'var(--bg-card)', fontSize: 12.5,
                  fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>Привязать</button>
            </span>
          </div>
        )}

        <CreatePanel label="Завести изначальный договор" open={form.open} onToggle={form.toggle}
          error={form.err} busy={form.busy} submitLabel="Завести и привязать к сделке"
          note="Для договора, которого нет в выгрузке ОРД. Он пометится как заведённый у нас: настоящий идентификатор подставится, когда договор появится в кабинете."
          onSubmit={() => form.submit(create)}>
          <Field label="Номер договора" value={form.data.number} onChange={form.set('number')} />
          <Field label="Дата договора" type="date" value={form.data.date} onChange={form.set('date')} />
          {/* Тип обязателен: в выгрузке он заполнен у всех 126 договоров. «Вид» — то,
              что реестр показывает колонкой «Вид»; вид деятельности пуст у 64 из 126. */}
          {/* Только услуговый и посреднический — правило владельца: ДС мы не ведём,
              саморекламный договор у нас с площадкой, а не с рекламодателем. В зеркале
              это подтверждено: из 126 изначальных 65 посреднических, 61 услуговый. */}
          <FieldRow>
            <SelectField label="Тип договора" value={form.data.type} onChange={form.set('type')}
              options={enums.initial_contract_types} width="1 1 200px" />
            <SelectField label="Вид договора" value={form.data.subject_type}
              onChange={form.set('subject_type')} options={enums.subject_types} width="1 1 200px" />
            <SelectField label="Вид деятельности" value={form.data.action_type}
              onChange={form.set('action_type')} options={enums.action_types}
              hint="Необязательно — пуст у половины" width="1 1 200px" />
          </FieldRow>
          {/* Стороны договора — по строке на каждую: ИНН и название читаются парой,
              и разорванная по ширине пара заставляет собирать сторону глазами. */}
          <FieldRow label="Рекламодатель">
            <Field label="ИНН" value={form.data.advertiser_inn}
              onChange={form.set('advertiser_inn')} placeholder="7700000000" width="0 1 180px" />
            <Field label="Название юрлица" value={form.data.advertiser_name}
              onChange={form.set('advertiser_name')} placeholder="ООО «Ромашка»" width="3 1 300px" />
          </FieldRow>
          <FieldRow label="Исполнитель">
            <Field label="ИНН" value={form.data.contractor_inn}
              onChange={form.set('contractor_inn')} placeholder="7700000000" width="0 1 180px" />
            <Field label="Название юрлица" value={form.data.contractor_name}
              onChange={form.set('contractor_name')} placeholder="ООО «Ромашка»" width="3 1 300px" />
          </FieldRow>
        </CreatePanel>
      </div>
    </Modal>
  )
}

function Group({ title, note, empty, rows, chosenId, onPick }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em',
          textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-muted)' }}>{title}</span>
        {!!note && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{note}</span>}
      </span>
      {!rows.length
        ? <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{empty || '—'}</span>
        : rows.map(c => (
          <PickRow key={c.id} chosen={c.id === chosenId} onPick={() => onPick(c)}
            title={c.advertiser?.name || 'рекламодатель не указан'}
            meta={[`${c.number || 'б/н'} от ${c.date ? fmtDateFull(c.date) : 'без даты'}`,
              `через ${c.contractor?.name || '—'}`,
              c.subject_type || null].filter(Boolean).join(' · ')}
            right={c.linked
              ? <Tag ok title="Связь есть в выгрузке ОРД">под доходным</Tag>
              : <Tag title="В выгрузке ОРД этот договор не привязан к доходному договору сделки">
                не под этим доходным
              </Tag>} />
        ))}
    </div>
  )
}
