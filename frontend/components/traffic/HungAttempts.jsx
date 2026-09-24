/* Сверка «исход неизвестен» — в окне кнопок «DSP» и «ПИКСЕЛЬ WR» (владелец 23.09.2026).

   Вызов, ушедший без ответа, запирает повтор: объект в чужом кабинете мог создаться, а
   второй там не удалить. Этот блок — выход из запертого: человек смотрит в кабинет и
   отмечает «нашёл» (с id) или «в кабинете нет». Проверку найденного делает сервер —
   экран ничего не решает сам.

   Компонент на уровне модуля, а не внутри окна: поле ввода в компоненте, объявленном в
   теле другого, теряет фокус после каждого символа. */
import { useState } from 'react'
import { CAP, btnSm, inp } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { fmtDateTime } from '@/lib/dates'

const HINT = {
  dsp: 'Хеш — 16 знаков из кабинета DSP',
  weborama: 'id объекта из кабинета Weborama — цифрами',
}

function Attempt({ campaignId, a, onDone }) {
  const [id, setId] = useState('')
  const [busy, setBusy] = useState(false)
  // Отказ — здесь же, в блоке: сообщение страницы лежит под окном, и его не видно.
  const [err, setErr] = useState('')
  const send = async (found) => {
    setBusy(true)
    setErr('')
    try {
      const r = await api.post(`/traffic-dashboard/campaign/${campaignId}/external/resolve`,
        { system: a.system, ref: a.ref, found, external_id: found ? id.trim() : null }, auth())
      // id — как его записал сервер (хеш DSP заглавными, у Weborama только цифры).
      onDone(found ? `Записан как наш: ${r.data.id}. Следующее нажатие продолжит с него`
        : 'Отмечено «в кабинете нет» — повтор разрешён')
    } catch (e) { setErr(e?.response?.data?.detail || 'Отметка не принята') }
    finally { setBusy(false) }
  }
  return (
    <div style={{ padding: '9px 12px', borderRadius: 9, background: 'var(--warning-tint)',
      display: 'grid', gap: 7 }}>
      <div style={{ fontSize: 12.5, color: 'var(--warning-text)' }}>
        {a.what}{a.label ? <> «<b>{a.label}</b>»</> : null} — вызов ушёл, ответа нет
        {a.since ? ` (${fmtDateTime(a.since)})` : ''}.
        Найдите его в кабинете {a.system === 'dsp' ? 'DSP' : 'Weborama'} по имени.
        {!a.checked && ' Этот id система проверить не может — впишите внимательно.'}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <input style={{ ...inp, flex: '1 1 180px', minWidth: 0 }} value={id}
          placeholder={HINT[a.system]} onChange={e => setId(e.target.value)} />
        <button style={btnSm(true)} disabled={busy || !id.trim()} onClick={() => send(true)}>
          Нашёл в кабинете</button>
        <button style={btnSm(false)} disabled={busy} onClick={() => send(false)}>
          В кабинете нет</button>
      </div>
      {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
    </div>
  )
}

export default function HungAttempts({ campaignId, items, onDone }) {
  if (!items?.length) return null
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div style={{ ...CAP, marginBottom: 0 }}>исход неизвестен — повтор заперт до сверки</div>
      {items.map(a => (
        <Attempt key={`${a.system}:${a.ref}`} campaignId={campaignId} a={a}
          onDone={onDone} />
      ))}
    </div>
  )
}
