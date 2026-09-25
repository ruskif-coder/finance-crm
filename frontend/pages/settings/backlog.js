/**
 * Бэклог отладки — что держим под наблюдением после больших изменений.
 *
 * Журнал действий отвечает «что было сделано», этот список — «что может выстрелить
 * и по какому признаку это опознать». Отсюда две вещи в интерфейсе:
 *   • подвкладка «Просрочено» со счётчиком — ради неё список и существует;
 *   • закрытие запрещено без «Чем кончилось» (то же правило на бэкенде, 400).
 *
 * Бэкенд: backend/app/routers/backlog.py, право settings_backlog (view/create/edit).
 * Стили — только общий набор из components/salesTableKit.js.
 */
import { useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { UI, MONO, card, inp, sel, primaryBtn, th, td } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import { getPermissions, can } from '../../lib/auth'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import safeHref from '@/lib/safeHref'
import { fmtDateTime, fmtDate as fmtDateOnly } from '@/lib/dates'

const SEVERITIES = ['низкая', 'средняя', 'высокая']
const STATUSES = ['наблюдаем', 'подтвердилось', 'закрыто', 'не воспроизвелось']
const CLOSED = ['закрыто', 'не воспроизвелось']

const SEV_TONE = { 'высокая': 'var(--dot-overdue)', 'средняя': 'var(--dot-current-dz)', 'низкая': 'var(--text-muted)' }
const ST_TONE = { 'наблюдаем': 'var(--accent)', 'подтвердилось': 'var(--dot-overdue)',
                  'закрыто': 'var(--text-muted)', 'не воспроизвелось': 'var(--text-muted)' }

const msg = e => e?.response?.data?.detail || e?.message || 'Ошибка'
const fmtDate = v => fmtDateOnly(v)
const fmtDT = v => fmtDateTime(v, '')

export default function DebugBacklog() {
  const [perms, setPerms] = useState({})
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState('watch')          // 'watch' | 'overdue' | 'closed'
  const [rows, setRows] = useState([])
  const [areas, setAreas] = useState([])
  const [area, setArea] = useState('')
  const [severity, setSeverity] = useState('')
  const [q, setQ] = useState('')
  const [openId, setOpenId] = useState(null)
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState('')

  useRefreshOnReturn(() => reload())
  useEffect(() => { setPerms(getPermissions()); setReady(true) }, [])

  const mayView = ready && can(perms, 'settings_backlog', 'view')
  const mayCreate = ready && can(perms, 'settings_backlog', 'create')
  const mayEdit = ready && can(perms, 'settings_backlog', 'edit')

  const reload = () => {
    const params = {}
    if (area) params.area = area
    if (severity) params.severity = severity
    if (q.trim()) params.q = q.trim()
    api.get('/backlog/', { ...auth(), params })
      .then(r => setRows(r.data)).catch(e => setErr(msg(e)))
  }

  useEffect(() => {
    if (!mayView) return
    reload()
    api.get('/backlog/areas', auth()).then(r => setAreas(r.data)).catch(() => {})
  }, [mayView, area, severity])

  // Разбивка по подвкладкам — на клиенте: «Просрочено» должно иметь счётчик,
  // даже когда открыта другая вкладка, иначе смысл списка теряется.
  const groups = useMemo(() => ({
    watch: rows.filter(r => !CLOSED.includes(r.status)),
    overdue: rows.filter(r => r.overdue),
    closed: rows.filter(r => CLOSED.includes(r.status)),
  }), [rows])
  const shown = groups[tab] || []

  if (ready && !mayView) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Бэклог отладки · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ maxWidth: 1320, padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <div style={{ ...card, padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>
          Нет доступа к разделу «Бэклог отладки».
        </div>
      </div>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Бэклог отладки · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ maxWidth: 1320, padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="backlog" />

        <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button onClick={() => setTab('watch')} style={topTab(tab === 'watch')}>Наблюдаем</button>
          <button onClick={() => setTab('overdue')} style={topTab(tab === 'overdue')}>
            Просрочено
            {groups.overdue.length > 0 && (
              <span style={{ marginLeft: 7, fontFamily: MONO, fontSize: 11,
                background: 'var(--dot-overdue)', color: 'var(--bg-card)',
                borderRadius: 7, padding: '1px 6px' }}>{groups.overdue.length}</span>
            )}
          </button>
          <button onClick={() => setTab('closed')} style={topTab(tab === 'closed')}>Закрытые</button>
          {mayCreate && (
            <button onClick={() => { setCreating(v => !v); setErr('') }}
              style={{ ...primaryBtn, marginLeft: 'auto' }}>
              {creating ? 'Отмена' : '+ Запись'}
            </button>
          )}
        </div>

        {creating && mayCreate && (
          <CreateForm areas={areas} onErr={setErr}
            onDone={() => { setCreating(false); reload(); api.get('/backlog/areas', auth()).then(r => setAreas(r.data)).catch(() => {}) }} />
        )}

        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
            display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && reload()} onBlur={reload}
              placeholder="Поиск по заголовку и контексту" style={{ ...inp, minWidth: 240 }} />
            <select value={area} onChange={e => setArea(e.target.value)} style={sel}>
              <option value="">Все разделы</option>
              {areas.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={severity} onChange={e => setSeverity(e.target.value)} style={sel}>
              <option value="">Любая важность</option>
              {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>записей: {shown.length}</span>
            {err && <span style={{ color: 'var(--dot-overdue)', fontSize: 12 }}>{err}</span>}
          </div>

          <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr>
                <th style={{ ...th, width: 96 }}>Важность</th>
                <th style={{ ...th, width: 150 }}>Раздел</th>
                <th style={{ ...th, minWidth: 300 }}>Заголовок</th>
                <th style={{ ...th, width: 140 }}>Статус</th>
                <th style={{ ...th, width: 120 }}>Срок</th>
                <th style={{ ...th, width: 90 }}>Наблюдений</th>
                <th style={{ ...th, width: 160 }}>Автор</th>
              </tr></thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={7} style={{ ...td, color: 'var(--text-muted)', fontSize: 13 }}>
                    Пусто. {tab === 'overdue'
                      ? 'Ни одна запись не просрочена — сроки наблюдения в норме.'
                      : 'Заведите запись, когда после крупного изменения остаётся что-то, за чем стоит последить.'}
                  </td></tr>
                )}
                {shown.map(r => (
                  <RowGroup key={r.id} row={r} open={openId === r.id} mayEdit={mayEdit}
                    onToggle={() => setOpenId(openId === r.id ? null : r.id)}
                    onChanged={reload} onErr={setErr} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Строка реестра + раскрывающаяся карточка записи. */
function RowGroup({ row, open, mayEdit, onToggle, onChanged, onErr }) {
  const [full, setFull] = useState(null)

  useEffect(() => {
    if (!open) return
    api.get(`/backlog/${row.id}`, auth()).then(r => setFull(r.data)).catch(e => onErr(msg(e)))
  }, [open, row.id])

  const reloadFull = () => api.get(`/backlog/${row.id}`, auth())
    .then(r => setFull(r.data)).catch(e => onErr(msg(e)))

  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer',
        background: open ? 'var(--bg-subtle)' : 'transparent' }}>
        <td style={td}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <i style={{ width: 7, height: 7, borderRadius: '50%', background: SEV_TONE[row.severity] || 'var(--text-muted)' }} />
            {row.severity}
          </span>
        </td>
        <td style={{ ...td, color: 'var(--text-secondary)' }}>{row.area || '—'}</td>
        <td style={{ ...td, fontWeight: 600 }}>{row.title}</td>
        <td style={{ ...td, color: ST_TONE[row.status] || 'var(--text-primary)' }}>{row.status}</td>
        <td style={{ ...td, fontFamily: MONO, fontSize: 12,
          color: row.overdue ? 'var(--dot-overdue)' : 'var(--text-muted)',
          fontWeight: row.overdue ? 700 : 400 }}>
          {fmtDate(row.watch_until)}{row.overdue ? ' · просрочено' : ''}
        </td>
        <td style={{ ...td, fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{row.notes_count}</td>
        <td style={{ ...td, color: 'var(--text-secondary)', fontSize: 12 }}>{row.created_by_name || '—'}</td>
      </tr>
      {open && (
        <tr><td colSpan={7} style={{ ...td, background: 'var(--bg-subtle)', padding: '14px 12px' }}>
          {!full ? <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</span>
            : <Detail item={full} mayEdit={mayEdit} onErr={onErr}
                onChanged={() => { reloadFull(); onChanged() }} />}
        </td></tr>
      )}
    </>
  )
}

/** Карточка записи: признаки, лента наблюдений, смена статуса и закрытие. */
function Detail({ item, mayEdit, onChanged, onErr }) {
  const [status, setStatus] = useState(item.status)
  const [resolution, setResolution] = useState(item.resolution || '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [warn, setWarn] = useState('')

  useEffect(() => { setStatus(item.status); setResolution(item.resolution || '') }, [item.id])

  const needsResolution = CLOSED.includes(status) && !resolution.trim()

  const save = async () => {
    if (needsResolution) {
      setWarn('Чтобы закрыть запись, опишите, чем всё кончилось — иначе через месяц её нельзя будет отличить от забытой.')
      return
    }
    setWarn(''); setBusy(true)
    try {
      await api.put(`/backlog/${item.id}`, { status, resolution: resolution || null }, auth())
      onChanged()
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }

  const addNote = async () => {
    if (!note.trim()) return
    setBusy(true)
    try {
      await api.post(`/backlog/${item.id}/notes`, { text: note.trim() }, auth())
      setNote(''); onChanged()
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
        <Field label="Контекст" hint="что именно меняли и почему за этим следим">{item.context}</Field>
        <Field label="Признак нормы" hint="как выглядит, когда всё в порядке">{item.signal_ok}</Field>
      </div>

      {/* Главное поле записи: по нему через две недели опознают, что сломалось. */}
      <div style={{ ...card, padding: '12px 14px', borderColor: 'var(--dot-overdue)' }}>
        <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase',
          color: 'var(--dot-overdue)', fontWeight: 700, marginBottom: 5 }}>
          Признак поломки — как выглядит проблема, если она проявится
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
          {item.signal_bad || <span style={{ color: 'var(--text-muted)' }}>не заполнено — по такой записи опознать поломку не выйдет</span>}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>Заведено: {fmtDT(item.created_at)} · {item.created_by_name || '—'}</span>
        {item.resolved_at && <span>Исход: {fmtDT(item.resolved_at)} · {item.resolved_by_name || '—'}</span>}
        {item.source_link && (
          <a href={safeHref(item.source_link)} target="_blank" rel="noreferrer"
            style={{ color: 'var(--accent)' }}>Источник</a>
        )}
      </div>

      <div>
        <div style={{ ...th, borderBottom: 'none', padding: '0 0 6px' }}>Наблюдения</div>
        {(item.notes || []).length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Пока никто ничего не заметил.</div>
        )}
        <div style={{ display: 'grid', gap: 8 }}>
          {(item.notes || []).map(n => (
            <div key={n.id} style={{ ...card, padding: '9px 12px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: MONO, marginBottom: 3 }}>
                {fmtDT(n.created_at)} · {n.author_name || '—'}
              </div>
              <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{n.text}</div>
            </div>
          ))}
        </div>
        {mayEdit && (
          <div style={{ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }}>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={2}
              placeholder="Что заметили — с датой и обстоятельствами"
              style={{ ...inp, flex: '1 1 320px', resize: 'vertical', fontFamily: UI }} />
            <button onClick={addNote} disabled={busy || !note.trim()}
              style={{ ...primaryBtn, opacity: note.trim() ? 1 : .45 }}>Добавить</button>
          </div>
        )}
      </div>

      {mayEdit && (
        <div style={{ display: 'grid', gap: 8, borderTop: '1px solid var(--border-inner)', paddingTop: 12 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Статус</span>
            <select value={status} onChange={e => { setStatus(e.target.value); setWarn('') }} style={sel}>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={save} disabled={busy}
              style={{ ...primaryBtn, opacity: needsResolution ? .55 : 1 }}>Сохранить</button>
          </div>
          <textarea value={resolution} onChange={e => { setResolution(e.target.value); setWarn('') }} rows={2}
            placeholder="Чем кончилось — обязательно для «закрыто» и «не воспроизвелось»"
            style={{ ...inp, resize: 'vertical', fontFamily: UI,
              borderColor: needsResolution ? 'var(--dot-overdue)' : 'var(--border-card)' }} />
          {warn && <span style={{ color: 'var(--dot-overdue)', fontSize: 12 }}>{warn}</span>}
        </div>
      )}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <div style={{ ...th, borderBottom: 'none', padding: '0 0 4px' }}>{label}</div>
      <div style={{ fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
        color: children ? 'var(--text-primary)' : 'var(--text-muted)' }}>
        {children || `не заполнено (${hint})`}
      </div>
    </div>
  )
}

/** Форма заведения записи. Раздел — выпадашка из /areas с возможностью ввести новый. */
function CreateForm({ areas, onDone, onErr }) {
  const [f, setF] = useState({ title: '', area: '', severity: 'средняя', watch_until: '',
    context: '', signal_ok: '', signal_bad: '', source_link: '' })
  const [newArea, setNewArea] = useState(false)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF(p => ({ ...p, [k]: v }))

  const submit = async () => {
    if (!f.title.trim()) { onErr('Название записи обязательно'); return }
    setBusy(true)
    try {
      await api.post('/backlog/', {
        title: f.title.trim(),
        area: f.area.trim() || null,
        severity: f.severity,
        watch_until: f.watch_until || null,
        context: f.context || null,
        signal_ok: f.signal_ok || null,
        signal_bad: f.signal_bad || null,
        source_link: f.source_link || null,
      }, auth())
      onErr('')
      onDone()
    } catch (e) { onErr(msg(e)) } finally { setBusy(false) }
  }

  return (
    <div style={{ ...card, padding: 16, marginBottom: 12, display: 'grid', gap: 10 }}>
      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        <input value={f.title} onChange={e => set('title', e.target.value)}
          placeholder="Заголовок — что держим под наблюдением" style={inp} />
        {newArea
          ? <input value={f.area} onChange={e => set('area', e.target.value)}
              placeholder="Новый раздел" style={inp} onBlur={() => !f.area && setNewArea(false)} />
          : <select value={f.area} onChange={e => {
              if (e.target.value === '__new') { setNewArea(true); set('area', '') }
              else set('area', e.target.value)
            }} style={sel}>
              <option value="">Раздел не указан</option>
              {areas.map(a => <option key={a} value={a}>{a}</option>)}
              <option value="__new">+ новый раздел…</option>
            </select>}
        <select value={f.severity} onChange={e => set('severity', e.target.value)} style={sel}>
          {SEVERITIES.map(s => <option key={s} value={s}>Важность: {s}</option>)}
        </select>
        <input type="date" value={f.watch_until} onChange={e => set('watch_until', e.target.value)}
          style={inp} title="Срок наблюдения" />
      </div>
      <textarea value={f.context} onChange={e => set('context', e.target.value)} rows={2}
        placeholder="Контекст: что меняли и почему за этим следим" style={{ ...inp, resize: 'vertical', fontFamily: UI }} />
      <textarea value={f.signal_ok} onChange={e => set('signal_ok', e.target.value)} rows={2}
        placeholder="Признак нормы: как выглядит, когда всё в порядке" style={{ ...inp, resize: 'vertical', fontFamily: UI }} />
      <div>
        <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase',
          color: 'var(--dot-overdue)', fontWeight: 700, marginBottom: 5 }}>
          Признак поломки — как выглядит проблема, если она проявится
        </div>
        <textarea value={f.signal_bad} onChange={e => set('signal_bad', e.target.value)} rows={3}
          placeholder="Например: в реестре операций у части строк пропадает № ДС, суммы за период не сходятся с выгрузкой"
          style={{ ...inp, resize: 'vertical', fontFamily: UI, width: '100%',
            borderColor: 'var(--dot-overdue)', fontSize: 14 }} />
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <input value={f.source_link} onChange={e => set('source_link', e.target.value)}
          placeholder="Ссылка на источник (задача, коммит, экран)" style={{ ...inp, flex: '1 1 260px' }} />
        <button onClick={submit} disabled={busy} style={primaryBtn}>
          {busy ? 'Сохраняю…' : 'Завести запись'}
        </button>
      </div>
    </div>
  )
}

const topTab = on => ({ padding: '8px 14px', borderRadius: 10, border: 'none', fontFamily: UI,
  cursor: on ? 'default' : 'pointer', fontWeight: on ? 700 : 600, fontSize: 13,
  display: 'inline-flex', alignItems: 'center',
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
  color: on ? 'var(--accent)' : 'var(--text-secondary)' })
