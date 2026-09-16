/**
 * Личные каналы получателя: привязка Telegram, тихие часы, час дайджеста.
 *
 * Часть модуля «Уведомления и письма». Здесь человек отвечает за СЕБЯ — чем и когда его
 * можно трогать, — в отличие от вкладки «Правила», где админ задаёт политику компании.
 */
import { useState } from 'react'
import { UI, MONO, inp, btnSm } from '../salesTableKit'
import api, { auth } from '../../lib/http'
import { msg, badge, linkBtn } from './kit'

export default function MyChannels({ me, tgCode, setTgCode, reload, onErr }) {
  const c = me.channels || {}
  const [quiet, setQuiet] = useState({ from: c.quiet_from ?? '', to: c.quiet_to ?? '' })
  const [dig, setDig] = useState({ hour: c.digest_hour ?? 9, minute: c.digest_minute ?? 30 })
  const [busy, setBusy] = useState(false)

  const link = async () => {
    setBusy(true)
    try {
      const r = await api.post('/notifications/settings/me/telegram/link', {}, auth())
      setTgCode(r.data)
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }
  const unlink = async () => {
    try { await api.delete('/notifications/settings/me/telegram', auth()); setTgCode(null); reload() }
    catch (e) { onErr(msg(e)) }
  }
  const test = async () => {
    try { await api.post('/notifications/settings/me/telegram/test', {}, auth()); onErr('') }
    catch (e) { onErr(msg(e)) }
  }
  const saveQuiet = async () => {
    try {
      await api.put('/notifications/settings/me/channels', {
        quiet_from: quiet.from === '' ? null : Number(quiet.from),
        quiet_to: quiet.to === '' ? null : Number(quiet.to),
      }, auth())
      reload()
    } catch (e) { onErr(msg(e)) }
  }
  const saveDigest = async () => {
    try {
      await api.put('/notifications/settings/me/channels', {
        digest_hour: Number(dig.hour), digest_minute: Number(dig.minute),
      }, auth())
      reload()
    } catch (e) { onErr(msg(e)) }
  }

  return (
    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
      display: 'flex', gap: 22, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <b>Telegram</b>
        {c.tg_linked
          ? <>
              <span style={badge('#E8F6F0', '#CBE9DE', '#1E7A5C')}>привязан</span>
              <button onClick={test} style={linkBtn}>Отправить тест</button>
              <button onClick={unlink} style={linkBtn}>Отвязать</button>
            </>
          : <>
              <span style={{ color: 'var(--text-muted)' }}>не привязан</span>
              <button onClick={link} disabled={busy} style={linkBtn}>Привязать</button>
            </>}
      </span>
      {tgCode && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          color: 'var(--text-secondary)' }}>
          {/* Кнопка ведёт в чат с ботом и несёт код в себе: Telegram подставит его в
              «Начать», вводить руками не нужно. Код рядом оставлен намеренно — если
              чат с ботом уже открывали, кнопки «Начать» в нём нет. */}
          {tgCode.link
            ? <a href={tgCode.link} target="_blank" rel="noopener noreferrer"
                 style={{ ...btnSm(true), textDecoration: 'none', display: 'inline-flex',
                   alignItems: 'center', gap: 6 }}>
                Перейти в бота{tgCode.bot ? ` @${tgCode.bot}` : ''} →
              </a>
            : <span>Откройте бота{tgCode.bot ? ` @${tgCode.bot}` : ' в Telegram'} и отправьте:</span>}
          <span>
            код{' '}
            <code style={{ fontFamily: MONO, background: 'var(--bg-subtle)', padding: '2px 6px', borderRadius: 6 }}>
              /start {tgCode.code}
            </code>
          </span>
        </span>
      )}
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <b>Тихие часы</b>
        <input type="number" min={0} max={23} value={quiet.from} placeholder="с"
          onChange={e => setQuiet(q => ({ ...q, from: e.target.value }))}
          style={{ ...inp, width: 58, padding: '5px 7px', textAlign: 'center' }} />
        <input type="number" min={0} max={23} value={quiet.to} placeholder="по"
          onChange={e => setQuiet(q => ({ ...q, to: e.target.value }))}
          style={{ ...inp, width: 58, padding: '5px 7px', textAlign: 'center' }} />
        <button onClick={saveQuiet} style={linkBtn}>Сохранить</button>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          в это время ничего не приходит, кроме событий «нельзя отключить»
        </span>
      </span>
      {/* Час пачки — рядом с тихими часами, потому что вопрос у них общий: «когда меня
          трогать». Показан ВСЕГДА, а не только при включённом дайджесте: иначе человек,
          поставивший галочку в таблице ниже, получал бы письмо в час, которого нигде не
          видел. */}
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <b>Дайджест в</b>
        <input type="number" min={0} max={23} value={dig.hour}
          onChange={e => setDig(d => ({ ...d, hour: e.target.value }))}
          style={{ ...inp, width: 58, padding: '5px 7px', textAlign: 'center' }} />
        <span style={{ color: 'var(--text-muted)' }}>:</span>
        <input type="number" min={0} max={59} step={5} value={dig.minute}
          onChange={e => setDig(d => ({ ...d, minute: e.target.value }))}
          style={{ ...inp, width: 58, padding: '5px 7px', textAlign: 'center' }} />
        <button onClick={saveDigest} style={linkBtn}>Сохранить</button>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          события, переведённые в дайджест, придут одним письмом в этот час
        </span>
      </span>
    </div>
  )
}

/** Журнал отправок: что реально ушло, кому и чем это кончилось. */
