/**
 * Настройки → Уведомления и письма. ОДИН модуль, четыре вкладки:
 *
 *   Правила          что кому приходит: политика профиля и личные переопределения
 *   Журнал отправок  общая лента обоих контуров с указанием канала
 *   Шаблоны писем    оболочка письма и тексты карточек, с предпросмотром
 *   Каналы           общие настройки, почта и два телеграм-бота
 *
 * Почта жила отдельным пунктом меню до 16.09.2026, и это было ошибкой раскладки:
 * рассылка — одно целое, а человек должен был помнить, что правила тут, а текст письма
 * через два клика. Части модуля лежат в `components/notify/`, общий набор стилей и слов
 * там же в `kit.js`.
 *
 * Эта страница — ОБОЛОЧКА: вкладки, загрузка данных правил и раскладка. Ни одной плашки
 * и ни одного словаря состояний здесь нет — иначе они разойдутся с частями модуля.
 */
import { useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { UI, MONO, CAP, card, inp, sel, primaryBtn, btnSm, th } from '../../components/salesTableKit'
import Channels from '../../components/notify/Channels'
import DeliveryLog from '../../components/notify/DeliveryLog'
import MyChannels from '../../components/notify/MyChannels'
import TemplateEditor from '../../components/notify/TemplateEditor'
import { CH_LABELS, badge, checkbox, hint, linkBtn, msg, segBtn, td, topTab }
  from '../../components/notify/kit'
import api, { auth } from '../../lib/http'
import { fmtDateTime } from '@/lib/dates'
import { TONE, toneOf } from '@/lib/tone'


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
  /* Вкладки МОДУЛЯ, а не экрана: почта переехала сюда (владелец 16.09.2026) — рассылка
     это один модуль, и держать правила в одном пункте меню, а текст письма в другом
     значило заставлять человека помнить, где что лежит. */
  const [tab, setTab] = useState('rules')   // rules | log | templates | sender
  const [logFilter, setLogFilter] = useState({ channel: '', contour: '', status: '', q: '' })
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
    if (tab !== 'log' || !isAdmin) return undefined
    const p = new URLSearchParams({ limit: '100' })
    Object.entries(logFilter).forEach(([k, v]) => { if (v) p.set(k, v) })
    // Пауза перед запросом: иначе поле поиска шлёт его на каждый символ.
    const t = setTimeout(() => {
      api.get(`/notifications/settings/deliveries?${p}`, auth())
        .then(r => setLog(r.data)).catch(e => setErr(msg(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [tab, isAdmin, logFilter])


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
      {/* Ширина модуля — 2500 (владелец 16.09.2026). Здесь она нужна не «на всякий
          случай»: у правил четыре канала плюс пороги, у журнала шесть колонок, у
          шаблонов три полосы сразу — список карточек, редактор и письмо. На 1320 всё
          это жило в горизонтальной прокрутке, то есть половина экрана была не видна. */}
      <div style={{ maxWidth: 2500, padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="notifications" />

        {isAdmin && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
            {[['rules', 'Правила'], ['log', 'Журнал отправок'],
              ['templates', 'Шаблоны писем'], ['channels', 'Каналы']].map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)} style={topTab(tab === k)}>{label}</button>
            ))}
          </div>
        )}

        {tab === 'templates' ? <TemplateEditor mayEdit={isAdmin} onErr={setErr} />
        : tab === 'channels' ? <Channels mayEdit={isAdmin} onErr={setErr} />
        : tab === 'log' ? (
          <DeliveryLog data={log} filter={logFilter} setFilter={setLogFilter}
            onErr={setErr} />
        ) : (
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

          {/* Текст письма — соседняя вкладка «Шаблоны писем» этого же экрана: модуль
              один, и ходить за ним в другой пункт меню больше не надо. */}

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
              Telegram доставляется после привязки чата. Дайджест уходит одним письмом в свой час; событие после этого часа ждёт следующего дня.
            </span>
          </div>
        </div>
        )}

      </div>
    </div>
  )
}

