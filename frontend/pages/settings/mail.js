/**
 * Настройки → Почта: журнал писем НАРУЖУ, шаблоны и состояние канала.
 *
 * Почему отдельная вкладка, а не часть «Уведомлений»: там журнал доставок ВНУТРЕННИХ
 * сообщений сотрудникам, получатель всегда наш пользователь. Здесь адресат вне системы —
 * площадка, паблишер, контрагент, — и читают этот журнал другие люди: трафик и аккаунт,
 * которым надо знать, дошло ли письмо, а не спрашивать админа.
 *
 * Граница прав видна прямо на экране: журнал открыт всем, у кого есть view; шаблоны и
 * настройки отправителя правит только тот, у кого есть edit (по умолчанию — админ).
 *
 * Учётных данных ящика здесь НЕТ и не будет: хост, логин и пароль живут в .env, как
 * токены ОРД, DSP и бота. Показывать пароль «только админу» значит завести ещё одно
 * место, откуда он утечёт.
 *
 * Бэкенд: backend/app/routers/mail_admin.py, право settings_mail (view/edit).
 * Стили — только общий набор из components/salesTableKit.js.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { UI, MONO, CAP, card, inp, btn, primaryBtn, th, td, sel, Modal }
  from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import { getPermissions, can } from '../../lib/auth'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const msg = e => e?.response?.data?.detail || e?.message || 'Ошибка'
const fmtDT = v => v ? new Date(v).toLocaleString('ru-RU') : '—'

// Тон статуса письма. «В очереди» — не ошибка: канал не настроен или письмо ждёт
// досылки, и красным оно быть не должно.
const ST = {
  sent: ['var(--income-tint)', 'var(--income)', 'отправлено'],
  failed: ['var(--danger-tint)', 'var(--danger)', 'не ушло'],
  queued: ['var(--warning-tint)', 'var(--warning-text)', 'в очереди'],
}

const Pill = ({ status }) => {
  const [bg, fg, label] = ST[status] || ['var(--bg-subtle)', 'var(--text-muted)', status]
  return (
    <span style={{ padding: '3px 9px', borderRadius: 8, background: bg, color: fg,
      fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{label}</span>
  )
}

export default function SettingsMail() {
  const [perms, setPerms] = useState({})
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState('log')          // 'log' | 'templates' | 'setup'
  const [state, setState] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [tpls, setTpls] = useState([])
  const [filter, setFilter] = useState({ kind: '', status: '', q: '' })
  const [open, setOpen] = useState(null)          // письмо в разворот
  const [edit, setEdit] = useState(null)          // шаблон в правку
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => { setPerms(getPermissions()); setReady(true) }, [])
  const mayView = ready && can(perms, 'settings_mail', 'view')
  const mayEdit = ready && can(perms, 'settings_mail', 'edit')

  const load = useCallback(async () => {
    if (!ready) return
    try {
      const p = new URLSearchParams()
      if (filter.kind) p.set('kind', filter.kind)
      if (filter.status) p.set('status', filter.status)
      if (filter.q.trim()) p.set('q', filter.q.trim())
      const [s, l] = await Promise.all([
        api.get('/mail/state', auth()),
        api.get(`/mail/log?limit=100&${p}`, auth()),
      ])
      setState(s.data); setRows(l.data.items || []); setTotal(l.data.total || 0)
      setErr('')
    } catch (e) { setErr(msg(e)) }
  }, [ready, filter])

  useEffect(() => { load() }, [load])
  useRefreshOnReturn(() => load())

  const loadTpls = useCallback(async () => {
    try { setTpls((await api.get('/mail/templates', auth())).data.items || []) }
    catch (e) { setErr(msg(e)) }
  }, [])
  useEffect(() => { if (tab === 'templates') loadTpls() }, [tab, loadTpls])

  const saveTpl = async () => {
    setBusy(true); setErr('')
    try {
      await api.put(`/mail/templates/${edit.key}`,
        { subject: edit.subject, body: edit.body }, auth())
      setEdit(null); await loadTpls(); setNote('Шаблон сохранён')
    } catch (e) { setErr(msg(e)) } finally { setBusy(false) }
  }

  const saveSetup = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.put('/mail/settings', {
        from_name: state.from_name, subject_prefix: state.subject_prefix,
        signature: state.signature,
      }, auth())
      setState(r.data); setNote('Настройки сохранены')
    } catch (e) { setErr(msg(e)) } finally { setBusy(false) }
  }

  const sendTest = async () => {
    setBusy(true); setErr(''); setNote('')
    try {
      const r = await api.post('/mail/test', {}, auth())
      setNote(`Проверочное письмо отправлено на ${r.data.to}`)
      await load()
    } catch (e) { setErr(msg(e)) } finally { setBusy(false) }
  }

  if (!ready) return null
  if (!mayView) {
    return (
      <>
        <Navbar />
        <div style={{ ...card, margin: 24, padding: 24, fontFamily: UI }}>
          Раздел «Почта» вам не открыт.
        </div>
      </>
    )
  }

  return (
    <>
      <Head><title>Почта · Настройки</title></Head>
      <Navbar />
      <SettingsTabs active="mail" />
      <div style={{ padding: '0 24px 32px', fontFamily: UI }}>

        {/* Состояние канала — первым и всегда. «Не настроено» это не ошибка экрана, а
            факт, который человек должен увидеть раньше, чем удивится пустому журналу. */}
        <div style={{ ...card, padding: 14, marginBottom: 14, display: 'flex',
          alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <Pill status={state?.configured ? 'sent' : 'queued'} />
          <span style={{ fontSize: 13 }}>
            {state?.configured
              ? <>Отправка настроена, письма уходят с <b>{state.sender}</b></>
              : <>Почта не настроена — письма копятся в очереди. {state?.env_hint}</>}
          </span>
          {!!state?.queued && (
            <span style={{ ...CAP, marginBottom: 0 }}>в очереди {state.queued}</span>
          )}
          {mayEdit && state?.configured && (
            <button onClick={sendTest} disabled={busy}
              style={{ ...btn(false), marginLeft: 'auto' }}>
              {busy ? 'Отправляю…' : 'Проверочное письмо себе'}
            </button>
          )}
        </div>

        {!!err && (
          <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--danger)' }}>{err}</div>
        )}
        {!!note && (
          <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--income)' }}>{note}</div>
        )}

        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          {[['log', `Журнал${total ? ' · ' + total : ''}`], ['templates', 'Шаблоны'],
            ['setup', 'Отправитель']].map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              style={{ ...btn(tab === k), fontSize: 13 }}>{label}</button>
          ))}
        </div>

        {tab === 'log' && (
          <div style={{ ...card, padding: 16 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
              <input value={filter.q} placeholder="адрес или тема"
                onChange={e => setFilter(f => ({ ...f, q: e.target.value }))}
                style={{ ...inp, width: 260 }} />
              <select value={filter.kind} style={{ ...sel, width: 200 }}
                onChange={e => setFilter(f => ({ ...f, kind: e.target.value }))}>
                <option value="">все виды</option>
                {Object.entries(state?.kinds || {}).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <select value={filter.status} style={{ ...sel, width: 170 }}
                onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}>
                <option value="">любой статус</option>
                <option value="sent">отправлено</option>
                <option value="failed">не ушло</option>
                <option value="queued">в очереди</option>
              </select>
            </div>

            {!rows.length && (
              <div style={{ padding: '28px 0', textAlign: 'center', color: 'var(--text-muted)',
                fontSize: 13 }}>
                {state?.configured
                  ? 'Писем пока не было.'
                  : 'Писем нет: почта ещё не настроена.'}
              </div>
            )}

            {!!rows.length && (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  <th style={th}>Когда</th><th style={th}>Кому</th><th style={th}>Тема</th>
                  <th style={th}>Вид</th><th style={th}>Кто</th><th style={th}>Статус</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.id} onClick={() => setOpen(r)} style={{ cursor: 'pointer' }}>
                      <td style={{ ...td, fontFamily: MONO, fontSize: 11.5, whiteSpace: 'nowrap' }}>
                        {fmtDT(r.sent_at || r.created_at)}
                      </td>
                      <td style={td}>
                        {r.to_name ? <>{r.to_name}<br /></> : null}
                        <span style={{ fontFamily: MONO, fontSize: 11.5,
                          color: 'var(--text-muted)' }}>{r.to_email}</span>
                      </td>
                      <td style={td}>{r.subject}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>{r.kind_label}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>{r.user || '—'}</td>
                      <td style={td}>
                        <Pill status={r.status} />
                        {!!r.error && (
                          <div style={{ fontSize: 10.5, color: 'var(--danger)', marginTop: 3 }}>
                            {r.error.slice(0, 60)}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === 'templates' && (
          <div style={{ ...card, padding: 16 }}>
            {!mayEdit && (
              <div style={{ ...CAP, marginBottom: 10 }}>
                только просмотр — правка шаблонов у администратора
              </div>
            )}
            {tpls.map(t => (
              <div key={t.key} style={{ padding: '12px 0',
                borderBottom: '1px solid var(--border-row)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <b style={{ fontSize: 14 }}>{t.title}</b>
                  <span style={{ ...CAP, marginBottom: 0 }}>{t.key}</span>
                  {mayEdit && (
                    <button onClick={() => setEdit({ ...t })}
                      style={{ ...btn(false), marginLeft: 'auto', fontSize: 12,
                        padding: '4px 10px' }}>Изменить</button>
                  )}
                </div>
                <div style={{ fontSize: 12.5, marginTop: 6, color: 'var(--text-secondary)' }}>
                  {t.subject}
                </div>
                <div style={{ fontSize: 12, marginTop: 4, color: 'var(--text-muted)',
                  whiteSpace: 'pre-wrap' }}>{t.body}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'setup' && (
          <div style={{ ...card, padding: 16, maxWidth: 720 }}>
            {/* Учётных данных здесь нет намеренно — см. шапку файла. */}
            <div style={{ ...CAP }}>доступ к ящику</div>
            <div style={{ fontSize: 13, marginBottom: 16 }}>
              {state?.host
                ? <>Сервер <b>{state.host}</b>, режим {state.mode}. </>
                : 'Сервер не задан. '}
              {state?.env_hint}
            </div>

            <div style={{ ...CAP }}>имя отправителя</div>
            <input value={state?.from_name || ''} readOnly={!mayEdit}
              onChange={e => setState(s => ({ ...s, from_name: e.target.value }))}
              style={{ ...inp, width: '100%', marginBottom: 12 }} />

            <div style={{ ...CAP }}>приставка к теме</div>
            <input value={state?.subject_prefix || ''} readOnly={!mayEdit}
              placeholder="например: [Симб-ЭД]"
              onChange={e => setState(s => ({ ...s, subject_prefix: e.target.value }))}
              style={{ ...inp, width: '100%', marginBottom: 12 }} />

            <div style={{ ...CAP }}>подпись</div>
            <textarea value={state?.signature || ''} readOnly={!mayEdit} rows={3}
              onChange={e => setState(s => ({ ...s, signature: e.target.value }))}
              style={{ ...inp, width: '100%', marginBottom: 14, fontFamily: UI }} />

            {mayEdit && (
              <button onClick={saveSetup} disabled={busy} style={primaryBtn}>
                {busy ? 'Сохраняю…' : 'Сохранить'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Письмо целиком: в журнале лежит ИТОГОВЫЙ текст, а не ссылка на шаблон, поэтому
          видно ровно то, что получила площадка. */}
      {open && (
        <Modal title={open.subject} width={720} onClose={() => setOpen(null)}
               summary={`${open.kind_label} · ${open.to_email} · ${fmtDT(open.sent_at || open.created_at)}`}
               footer={<button style={btn(false)} onClick={() => setOpen(null)}>Закрыть</button>}>
          {!!open.reply_to && (
            <div style={{ ...CAP, marginBottom: 8 }}>ответ придёт на {open.reply_to}</div>
          )}
          {!!open.error && (
            <div style={{ color: 'var(--danger)', fontSize: 12.5, marginBottom: 10 }}>
              {open.error}
            </div>
          )}
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.55 }}>
            {open.body}
          </div>
        </Modal>
      )}

      {edit && (
        <Modal title={`Шаблон · ${edit.title}`} width={760} onClose={() => setEdit(null)}
               summary="Поля в фигурных скобках подставляются при отправке. Неизвестное поле сохранить не даст — опечатка уехала бы площадке как есть."
               footer={<>
                 <button style={btn(false)} onClick={() => setEdit(null)}>Отмена</button>
                 <button style={btn(true)} disabled={busy} onClick={saveTpl}>
                   {busy ? 'Сохраняю…' : 'Сохранить'}
                 </button>
               </>}>
          <div style={{ ...CAP }}>доступные поля</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
            {Object.entries(edit.fields || {}).map(([k, hint]) => (
              <span key={k} title={hint}
                style={{ fontFamily: MONO, fontSize: 11, padding: '3px 8px', borderRadius: 7,
                  background: 'var(--bg-subtle)', border: '1px solid var(--border-card)' }}>
                {'{' + k + '}'}
              </span>
            ))}
          </div>
          <div style={{ ...CAP }}>тема</div>
          <input value={edit.subject} onChange={e => setEdit(s => ({ ...s, subject: e.target.value }))}
            style={{ ...inp, width: '100%', marginBottom: 12 }} />
          <div style={{ ...CAP }}>текст</div>
          <textarea value={edit.body} rows={12}
            onChange={e => setEdit(s => ({ ...s, body: e.target.value }))}
            style={{ ...inp, width: '100%', fontFamily: UI }} />
        </Modal>
      )}
    </>
  )
}
