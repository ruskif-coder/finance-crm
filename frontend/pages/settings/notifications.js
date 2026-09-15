/**
 * Настройки уведомлений — страница раздела «Настройки». Два режима:
 *   • «Профили» — админ задаёт, что получают сотрудники профиля (политика компании);
 *   • «Мои»     — каждый правит только свои, видит унаследованное от профиля пунктиром.
 *
 * Матрица строится ИЗ реестра на бэкенде (/api/notifications/settings/catalog):
 * новое событие появляется здесь само, без правки этого файла.
 * Макет: docs/mockup_notifications.html
 */
import { useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { UI, MONO, card, inp, sel, primaryBtn, btnSm, th } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import { fmtDateTime } from '@/lib/dates'
import { TONE, toneOf } from '@/lib/tone'

const CH_LABELS = { app: 'В приложении', tg: 'Telegram', mail: 'Почта', digest: 'Дайджест' }
// Цвет точки берётся из общего словаря: своя карта здесь стояла на старых словах,
// и после перехода реестра на канон все точки, кроме «к сведению», стали синими.

export default function NotificationSettings() {
  const [isAdmin, setIsAdmin] = useState(false)
  const [mode, setMode] = useState('me')            // 'profiles' | 'me'
  const [catalog, setCatalog] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [profileId, setProfileId] = useState(null)
  const [items, setItems] = useState([])
  const [dir, setDir] = useState('account')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState('rules')        // 'rules' | 'log'
  const [log, setLog] = useState(null)
  const [me, setMe] = useState(null)             // личные каналы: Telegram, тихие часы
  const [tgCode, setTgCode] = useState(null)
  const [testing, setTesting] = useState(null)   // ключ события, которое сейчас шлём себе
  const [testMsg, setTestMsg] = useState({})     // ключ → {ok, text}: ответ под строкой

  // Проверка одного вида уведомления: приходит ТОЛЬКО себе и только админу. Ответ
  // показываем прямо под строкой — «отправлено» без подтверждения ничего не значит,
  // а причина отказа («бот не настроен», «чат не привязан») сама говорит, что чинить.
  const testEvent = async (key) => {
    setTesting(key); setTestMsg(m => ({ ...m, [key]: null }))
    try {
      await api.post(`/notifications/settings/events/${key}/test`, {}, auth())
      setTestMsg(m => ({ ...m, [key]: { ok: true, text: 'Отправлено вам в Telegram' } }))
    } catch (e) {
      setTestMsg(m => ({ ...m, [key]: { ok: false, text: msg(e) } }))
    } finally { setTesting(null) }
  }

  useEffect(() => {
    const admin = localStorage.getItem('role') === 'admin'
    setIsAdmin(admin)
    setMode(admin ? 'profiles' : 'me')
    api.get('/notifications/settings/catalog', auth())
      .then(r => setCatalog(r.data)).catch(e => setErr(msg(e)))
    if (admin) api.get('/notifications/settings/profiles', auth())
      .then(r => { setProfiles(r.data); if (r.data.length) setProfileId(r.data[0].id) })
      .catch(e => setErr(msg(e)))
  }, [])

  useEffect(() => {
    if (!catalog) return
    const url = mode === 'profiles'
      ? (profileId ? `/notifications/settings/profiles/${profileId}/subscriptions` : null)
      : '/notifications/settings/me'
    if (!url) return
    api.get(url, auth())
      .then(r => {
        setItems(mode === 'me' ? r.data.items : r.data)
        if (mode === 'me') setMe(r.data)
        setDirty(false)
      })
      .catch(e => setErr(msg(e)))
  }, [catalog, mode, profileId])

  useEffect(() => {
    if (tab !== 'log' || !isAdmin) return
    api.get('/notifications/settings/deliveries?limit=100', auth())
      .then(r => setLog(r.data)).catch(e => setErr(msg(e)))
  }, [tab, isAdmin])

  const dirs = catalog?.directions || []
  const channels = catalog?.channels || []
  const shown = useMemo(() => items.filter(i => i.direction === dir), [items, dir])
  const countIn = k => items.filter(i => i.direction === k).length

  const patch = (eventKey, fn) => {
    setItems(prev => prev.map(i => i.event_key !== eventKey ? i
      : { ...fn(i), source: mode === 'me' ? 'personal' : i.source }))
    setDirty(true)
  }

  const toggle = (k, ch) => patch(k, i => ({ ...i, channels: { ...i.channels, [ch]: !i.channels[ch] } }))
  const setParam = (k, key, v) => patch(k, i => ({ ...i, params: { ...i.params, [key]: v === '' ? '' : Number(v) } }))

  async function resetOne(eventKey) {
    try {
      await api.delete(`/notifications/settings/me/subscriptions/${eventKey}`, auth())
      const r = await api.get('/notifications/settings/me', auth())
      setItems(r.data.items)
    } catch (e) { setErr(msg(e)) }
  }

  async function save() {
    setSaving(true); setErr('')
    const payload = { items: items.map(i => ({
      event_key: i.event_key, is_enabled: i.is_enabled, channels: i.channels,
      params: i.params, recipients: i.recipients })) }
    try {
      if (mode === 'profiles') await api.put(`/notifications/settings/profiles/${profileId}/subscriptions`, payload, auth())
      else await api.put('/notifications/settings/me/subscriptions', payload, auth())
      setDirty(false)
    } catch (e) { setErr(msg(e)) } finally { setSaving(false) }
  }

  async function createProfile() {
    const label = window.prompt('Название нового профиля')
    if (!label) return
    try {
      // Копия текущего профиля — самый частый способ завести новый.
      const r = await api.post('/notifications/settings/profiles', { label, copy_from: profileId }, auth())
      const list = await api.get('/notifications/settings/profiles', auth())
      setProfiles(list.data); setProfileId(r.data.id)
    } catch (e) { setErr(msg(e)) }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Уведомления · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '18px 20px 40px' }}>
        <SettingsTabs active="notifications" />

        {isAdmin && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
            <button onClick={() => setTab('rules')} style={topTab(tab === 'rules')}>Правила</button>
            <button onClick={() => setTab('log')} style={topTab(tab === 'log')}>Журнал отправок</button>
          </div>
        )}

        {tab === 'log' ? <DeliveryLog data={log} /> : (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {isAdmin && (
              <div style={{ display: 'flex', background: 'var(--bg-subtle)', borderRadius: 10, padding: 3 }}>
                <button onClick={() => setMode('profiles')} style={segBtn(mode === 'profiles')}>Профили</button>
                <button onClick={() => setMode('me')} style={segBtn(mode === 'me')}>Мои настройки</button>
              </div>
            )}
            {mode === 'profiles' ? (
              <>
                {/* Подпись обязательна: рядом стоят ДВА независимых выбора — слева
                    направления (какие события показать), здесь профиль (для кого правим
                    политику). Без неё выпадашка читается как фильтр списка слева
                    (вопрос владельца 08.09.2026). */}
                <span style={{ ...hint, whiteSpace: 'nowrap' }}>Настраиваю для профиля:</span>
                <select value={profileId || ''} onChange={e => setProfileId(Number(e.target.value))} style={sel}>
                  {profiles.map(p => <option key={p.id} value={p.id}>{p.label} · {p.users} чел.</option>)}
                </select>
                <button onClick={createProfile} style={{ ...inp, cursor: 'pointer' }}>+ Профиль</button>
                <span style={hint}>Что получают сотрудники профиля по умолчанию. Личные настройки перекрывают это.</span>
              </>
            ) : (
              <span style={hint}>Пунктир — унаследовано от профиля, сплошная галочка — вы переопределили.</span>
            )}
          </div>

          {mode === 'me' && me && (
            <MyChannels me={me} tgCode={tgCode} setTgCode={setTgCode}
              reload={() => api.get('/notifications/settings/me', auth()).then(r => setMe(r.data))}
              onErr={setErr} />
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '210px 1fr', minHeight: 440 }}>
            <div style={{ borderRight: '1px solid var(--border-inner)', padding: 10, background: 'var(--bg-subtle)' }}>
              {dirs.map(d => {
                const n = countIn(d.key), on = dir === d.key
                return (
                  <div key={d.key} onClick={() => setDir(d.key)}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 10px', borderRadius: 10,
                      cursor: 'pointer', opacity: n ? 1 : .5, fontSize: 14,
                      background: on ? 'var(--bg-card)' : 'transparent',
                      fontWeight: on ? 700 : 500,
                      color: on ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {d.label}
                    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>
                  </div>
                )
              })}
            </div>

            <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ ...th, minWidth: 360 }}>Событие</th>
                    {channels.map(c => <th key={c} style={{ ...th, textAlign: 'center', width: 92 }}>{CH_LABELS[c] || c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {shown.length === 0 && (
                    <tr><td colSpan={channels.length + 1} style={{ padding: 24, color: 'var(--text-muted)', fontSize: 13 }}>
                      В этом направлении пока нет реализованных событий — реестр не показывает то,
                      чего ещё нет в коде. Они появятся здесь по мере реализации.
                    </td></tr>
                  )}
                  {shown.map(i => (
                    <tr key={i.event_key}>
                      <td style={td}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                          <i style={{ width: 7, height: 7, borderRadius: '50%', background: TONE[toneOf(i.tone)].dot }} />
                          <span style={{ fontWeight: 600, fontSize: 14 }}>{i.title}</span>
                          {i.scan && <span style={badge('#FFF6E9', '#F5E0BE', '#9A6512')}>сканер</span>}
                          {i.locked && <span style={badge('#FDECEE', '#F6CDD2', '#B23540')}>нельзя отключить</span>}
                          {mode === 'me' && i.source === 'personal' &&
                            <span style={badge('var(--accent-tint)', '#D9E0FB', 'var(--accent)')}>переопределено</span>}
                          {/* Проверка ОДНОГО вида уведомления себе в бот (владелец
                              08.09.2026). Половина событий состояниевые: дождаться
                              настоящего — значит ждать сутки и чужую просрочку. */}
                          {isAdmin && (
                            <button onClick={() => testEvent(i.event_key)} disabled={testing === i.event_key}
                              title="Прислать этот вид уведомления мне в Telegram"
                              style={{ ...btnSm(false), marginLeft: 'auto', cursor: 'pointer', opacity: testing === i.event_key ? .5 : 1 }}>
                              {testing === i.event_key ? '…' : 'тест в бот'}
                            </button>
                          )}
                        </div>
                        {testMsg[i.event_key] && (
                          <div style={{ marginTop: 4, fontSize: 12,
                            color: testMsg[i.event_key].ok ? 'var(--income)' : 'var(--danger)' }}>
                            {testMsg[i.event_key].text}
                          </div>
                        )}
                        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 3, lineHeight: 1.45 }}>{i.description}</div>
                        {Object.keys(i.params || {}).length > 0 && (
                          <div style={{ marginTop: 7, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 12 }}>
                            {Object.entries(i.params).map(([k, v]) => (
                              <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                                <input type="number" value={v} onChange={e => setParam(i.event_key, k, e.target.value)}
                                  style={{ ...inp, width: 62, padding: '5px 7px', textAlign: 'center' }} />
                              </span>
                            ))}
                          </div>
                        )}
                        {mode === 'me' && i.source === 'personal' && (
                          <button onClick={() => resetOne(i.event_key)}
                            style={{ marginTop: 7, background: 'none', border: 0, padding: 0,
                              fontSize: 11, color: 'var(--accent)', cursor: 'pointer', fontFamily: UI }}>
                            Вернуть как в профиле
                          </button>
                        )}
                      </td>
                      {channels.map(c => (
                        <td key={c} style={{ ...td, textAlign: 'center' }}>
                          <span onClick={() => toggle(i.event_key, c)}
                            style={checkbox(i.channels[c], mode === 'me' && i.source !== 'personal')} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-inner)',
            display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <button onClick={save} disabled={!dirty || saving}
              style={{ ...primaryBtn, opacity: dirty ? 1 : .45, cursor: dirty ? 'pointer' : 'default' }}>
              {saving ? 'Сохраняю…' : 'Сохранить'}
            </button>
            {err && <span style={{ color: 'var(--dot-overdue)', fontSize: 12 }}>{err}</span>}
            <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
              Telegram доставляется после привязки чата. Почта и дайджест настраиваются, но пока не доставляются — их отправки копятся в журнале.
            </span>
          </div>
        </div>
        )}
      </div>
    </div>
  )
}

/** Личные каналы: привязка Telegram, тихие часы, «не беспокоить». */
function MyChannels({ me, tgCode, setTgCode, reload, onErr }) {
  const c = me.channels || {}
  const [quiet, setQuiet] = useState({ from: c.quiet_from ?? '', to: c.quiet_to ?? '' })
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
    </div>
  )
}

/** Журнал отправок: что реально ушло, кому и чем это кончилось. */
function DeliveryLog({ data }) {
  if (!data) return <div style={{ ...card, padding: 20, color: 'var(--text-muted)' }}>Загрузка…</div>
  const scan = data.last_scan
  const ST = { sent: ['#E8F6F0', '#1E7A5C', 'доставлено'],
               queued: ['#F4F5F9', 'var(--text-muted)', 'ждёт канала'],
               suppressed: ['#F4F5F9', 'var(--text-muted)', 'подавлено'],
               failed: ['#FDECEE', '#B23540', 'ошибка'] }
  return (
    <div style={{ ...card, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
        display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', fontSize: 12 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Журнал отправок</span>
        <span style={{ color: 'var(--text-muted)' }}>всего записей: {data.total}</span>
        {/* Прогон сканера показываем здесь же: «алерты не приходят» надо уметь
            отличить от «сканер вообще не запускался». */}
        {scan && (
          <span style={{ color: 'var(--text-muted)' }}>
            последний прогон: {fmtDateTime(scan.started_at)} ·
            сработок {scan.matches} · отправок {scan.sent} · пропущено {scan.suppressed}
            {scan.dry_run ? ' · сухой прогон' : ''}
            {scan.error ? ` · ошибка: ${scan.error}` : ''}
          </span>
        )}
      </div>
      <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            <th style={th}>Когда</th><th style={th}>Событие</th><th style={th}>Что ушло</th>
            <th style={th}>Кому</th><th style={th}>Канал</th><th style={th}>Статус</th>
          </tr></thead>
          <tbody>
            {data.items.length === 0 && (
              <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>Пока пусто.</td></tr>
            )}
            {data.items.map(r => {
              const [bg, fg, label] = ST[r.status] || ['#F4F5F9', 'var(--text-muted)', r.status]
              return (
                <tr key={r.id}>
                  <td style={{ ...td, whiteSpace: 'nowrap', color: 'var(--text-muted)', fontFamily: MONO, fontSize: 11 }}>
                    {fmtDateTime(r.created_at)}
                  </td>
                  <td style={{ ...td, fontSize: 13 }}>{r.event_title}</td>
                  <td style={{ ...td, fontSize: 13 }}>{r.title}</td>
                  <td style={{ ...td, fontSize: 13 }}>{r.user}</td>
                  <td style={{ ...td, fontSize: 13 }}>{CH_LABELS[r.channel] || r.channel}</td>
                  <td style={td}>
                    <span style={{ ...badge(bg, bg, fg) }}>
                      {label}{r.suppress_reason ? ` · ${r.suppress_reason}` : ''}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const msg = e => e?.response?.data?.detail || e?.message || 'Ошибка'
const topTab = on => ({ padding: '8px 14px', borderRadius: 10, border: 'none', fontFamily: UI,
  cursor: on ? 'default' : 'pointer', fontWeight: on ? 700 : 600, fontSize: 13,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
  color: on ? 'var(--accent)' : 'var(--text-secondary)' })
const linkBtn = { background: 'none', border: 0, padding: 0, fontSize: 12, color: 'var(--accent)', cursor: 'pointer', fontFamily: UI }
const hint = { fontSize: 12, color: 'var(--text-muted)' }
const td = { padding: '11px 10px', borderBottom: '1px solid var(--border-row)', verticalAlign: 'top' }
const segBtn = on => ({ border: 0, background: on ? 'var(--bg-card)' : 'transparent', padding: '7px 14px',
  borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: on ? 700 : 600, fontFamily: UI,
  color: on ? 'var(--text-primary)' : 'var(--text-secondary)' })
const badge = (bg, bd, fg) => ({ fontSize: 10, borderRadius: 5, padding: '2px 6px', background: bg,
  border: `1px solid ${bd}`, color: fg, whiteSpace: 'nowrap' })
const checkbox = (on, inherited) => ({
  display: 'inline-block', width: 18, height: 18, borderRadius: 6, cursor: 'pointer', verticalAlign: 'middle',
  border: `1.5px ${inherited ? 'dashed' : 'solid'} ${on ? (inherited ? '#B9C5F2' : 'var(--accent)') : '#C9D1E4'}`,
  background: on ? (inherited ? '#DDE3FA' : 'var(--accent)') : 'var(--bg-card)',
  backgroundImage: on ? `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M2 6.5l2.5 2.5L10 3.5' fill='none' stroke='${inherited ? '%237E90DF' : 'white'}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>")` : 'none',
  backgroundSize: '13px 13px', backgroundPosition: 'center', backgroundRepeat: 'no-repeat',
})
