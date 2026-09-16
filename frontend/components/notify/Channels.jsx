/**
 * Каналы модуля «Уведомления и письма»: общие настройки и подсистема на каждый способ
 * доставки.
 *
 * Собрано в одном месте (владелец 16.09.2026), потому что вопрос к каналам один —
 * «настроен ли и чем проверить», — а мест для ответа было три: почта на своём экране,
 * боты нигде. Ненастроенный канал так находился последним, уже при разборе «почему не
 * пришло».
 *
 * СЕКРЕТОВ ЗДЕСЬ НЕТ и не будет: токены ботов и пароль ящика живут в `.env`, как токены
 * ОРД и DSP. На экран уходит только факт настроенности и то, что и так видит получатель —
 * адрес отправителя и имя бота. Показывать пароль «только админу» значит завести ещё
 * одно место, откуда он утечёт.
 *
 * Ботов ДВА, и это не дублирование: наш рабочий пишет сотрудникам, бот площадок — наружу.
 * Один на оба контура означал бы, что паблишер видит внутренний алёрт-бот подрядчика.
 */
import { useCallback, useEffect, useState } from 'react'
import { UI, CAP, card, inp, btn, primaryBtn } from '../salesTableKit'
import api, { auth } from '../../lib/http'
import { msg, Chip, STATUS } from './kit'

export default function Channels({ mayEdit, onErr }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  const load = useCallback(async () => {
    try { setState((await api.get('/mail/channels', auth())).data) }
    catch (e) { onErr(msg(e)) }
  }, [onErr])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setBusy(true)
    try {
      await api.put('/mail/settings', {
        from_name: state.mail.from_name, subject_prefix: state.mail.subject_prefix,
        signature: state.mail.signature,
      }, auth())
      setNote('Сохранено'); load()
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }

  const test = async () => {
    setBusy(true)
    try {
      const r = await api.post('/mail/test', {}, auth())
      setNote(`Проверочное письмо ушло на ${r.data.to}`)
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }

  useEffect(() => { if (!note) return undefined
    const t = setTimeout(() => setNote(''), 2500); return () => clearTimeout(t) }, [note])

  if (!state) return <div style={{ ...card, padding: 20, color: 'var(--text-muted)' }}>Загрузка…</div>
  const m = state.mail
  const setMail = patch => setState(s => ({ ...s, mail: { ...s.mail, ...patch } }))

  // Полосу формы НЕ растягиваем на весь модуль, хотя место есть: поле ввода в два
  // экрана шириной не становится удобнее, а глаз теряет начало строки. Ширина экрана
  // тратится там, где есть что показать — в правилах, журнале и шаблонах.
  return (
    <div style={{ display: 'grid', gap: 12, maxWidth: 760, fontFamily: UI }}>
      {note && <div style={{ ...card, padding: 10, color: 'var(--income-fg)', fontSize: 12.5 }}>{note}</div>}

      {/* ── общее для всех каналов ─────────────────────────────────────────── */}
      <div style={{ ...card, padding: 16 }}>
        <div style={{ ...CAP }}>общее для всех писем</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
          Имя отправителя стоит и в письме сотруднику, и в письме площадке: компания для
          получателя одна, и два разных имени читались бы как две разные конторы.
        </div>

        <div style={{ ...CAP }}>имя отправителя</div>
        <input value={m.from_name || ''} readOnly={!mayEdit}
          onChange={e => setMail({ from_name: e.target.value })}
          style={{ ...inp, width: '100%', marginBottom: 12 }} />

        <div style={{ ...CAP }}>приставка к теме</div>
        <input value={m.subject_prefix || ''} readOnly={!mayEdit}
          placeholder="например: [Симб-ЭД]"
          onChange={e => setMail({ subject_prefix: e.target.value })}
          style={{ ...inp, width: '100%', marginBottom: 12 }} />

        <div style={{ ...CAP }}>подпись</div>
        <textarea value={m.signature || ''} readOnly={!mayEdit} rows={3}
          onChange={e => setMail({ signature: e.target.value })}
          style={{ ...inp, width: '100%', marginBottom: 14, fontFamily: UI }} />

        {mayEdit && (
          <button onClick={save} disabled={busy} style={primaryBtn}>
            {busy ? 'Сохраняю…' : 'Сохранить'}
          </button>
        )}
      </div>

      {/* ── почта ──────────────────────────────────────────────────────────── */}
      <div style={{ ...card, padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <b style={{ fontSize: 14 }}>Почта</b>
          <Chip pair={STATUS[m.configured ? 'sent' : 'queued']}
            text={m.configured ? 'настроена' : 'не настроена'} />
          {!!m.queued && (
            <span style={{ ...CAP, marginBottom: 0 }}>в очереди {m.queued}</span>
          )}
          {mayEdit && m.configured && (
            <button onClick={test} disabled={busy}
              style={{ ...btn(false), marginLeft: 'auto', fontSize: 12 }}>
              Проверочное письмо себе
            </button>
          )}
        </div>
        <div style={{ fontSize: 13 }}>
          {m.configured
            ? <>Письма уходят с <b>{m.sender}</b>{m.host ? <>, сервер {m.host}, режим {m.mode}</> : null}.</>
            : <>Письма копятся в очереди. {m.problem ? <b>{m.problem}</b> : null}</>}
        </div>
        <div style={{ ...CAP, marginTop: 8, marginBottom: 0 }}>{m.env_hint}</div>
      </div>

      {/* ── телеграм: два бота ─────────────────────────────────────────────── */}
      {state.bots.map(b => (
        <div key={b.contour} style={{ ...card, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
            flexWrap: 'wrap' }}>
            <b style={{ fontSize: 14 }}>{b.label}</b>
            <Chip pair={STATUS[b.configured ? 'sent' : 'queued']}
              text={b.configured ? 'настроен' : 'не настроен'} />
            {b.username && (
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>@{b.username}</span>
            )}
            <span style={{ marginLeft: 'auto', ...CAP, marginBottom: 0 }}>
              {b.linked} {b.linked_hint}
            </span>
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{b.hint}</div>
          {!b.configured && (
            <div style={{ ...CAP, marginTop: 8, marginBottom: 0 }}>
              токен кладётся в .env переменной {b.env}; до этого сообщения копятся в журнале
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
