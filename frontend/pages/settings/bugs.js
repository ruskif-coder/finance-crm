/**
 * Журнал заявок о сбоях.
 *
 * ОДИН СПИСОК НА ОБА КОНТУРА с колонкой «кто пишет» (решение владельца 17.09.2026):
 * отдельный список для площадок означал бы, что половина заявок теряется из виду просто
 * потому, что лежит в другом месте.
 *
 * Разбор — это не «прочитать», а закрыть с причиной. Поэтому статус «исправлено» и
 * соседние исходы не принимаются без строки о том, чем закончилось: то же правило, что
 * в бэклоге отладки, и по той же причине — через месяц «закрыто» без объяснения
 * неотличимо от «забыли».
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { overlayClose } from '@/lib/overlay'
import Navbar from '../../components/Navbar'
import SettingsTabs from '../../components/SettingsTabs'
import { UI, MONO, card, inp, btn, btnSm, primaryBtn, th, td } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import { can, getPermissions } from '../../lib/auth'
import { fmtDateTime } from '../../lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const TONE = {
  'новая': ['var(--warning-tint)', 'var(--warning-text)'],
  'в работе': ['var(--accent-tint)', 'var(--accent)'],
  'исправлено': ['var(--income-tint)', 'var(--income)'],
  'не воспроизводится': ['var(--bg-subtle)', 'var(--text-muted)'],
  'не баг': ['var(--bg-subtle)', 'var(--text-muted)'],
}

export default function BugsPage() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('')
  const [contour, setContour] = useState('')
  const [open, setOpen] = useState(null)      // раскрытая заявка целиком
  const [resolution, setResolution] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [mayEdit, setMayEdit] = useState(false)

  useEffect(() => { setMayEdit(can(getPermissions(), 'settings_bugs', 'edit')) }, [])

  const load = useCallback(async () => {
    setErr('')
    try {
      const params = {}
      if (status) params.status = status
      if (contour) params.contour = contour
      const r = await api.get('/bugs', { ...auth(), params })
      setData(r.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить заявки') }
  }, [status, contour])

  useEffect(() => { load() }, [load])
  useRefreshOnReturn(() => load())

  const show = async (id) => {
    try {
      const r = await api.get(`/bugs/${id}`, auth())
      setOpen(r.data); setResolution(r.data.resolution || '')
      // Открытие ставит отметку «прочитано» на сервере — список после этого устарел.
      load()
    } catch (e) { setErr(e.response?.data?.detail || 'Заявка не открылась') }
  }

  const patch = async (payload) => {
    setBusy(true); setErr('')
    try {
      const r = await api.patch(`/bugs/${open.id}`, payload, auth())
      setOpen(r.data); await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить') }
    finally { setBusy(false) }
  }

  const toBacklog = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/bugs/${open.id}/backlog`, {}, auth())
      setOpen(r.data); await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось завести наблюдение') }
    finally { setBusy(false) }
  }

  const chip = (s) => {
    const [bg, fg] = TONE[s] || TONE['не баг']
    return { padding: '2px 9px', borderRadius: 8, background: bg, color: fg,
      fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Заявки о сбоях · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ maxWidth: 1320, padding: '20px 26px 50px', background: 'var(--bg-canvas)',
        minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="bugs" />

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '14px 0',
          flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>Заявки о сбоях</h1>
          <select value={status} onChange={e => setStatus(e.target.value)} style={{ ...inp, width: 190 }}>
            <option value="">статус: любой</option>
            {(data?.statuses || []).map(s => (
              <option key={s} value={s}>{s}{data?.counts?.[s] ? ` (${data.counts[s]})` : ''}</option>
            ))}
          </select>
          <select value={contour} onChange={e => setContour(e.target.value)} style={{ ...inp, width: 190 }}>
            <option value="">кто пишет: любой</option>
            {Object.entries(data?.contours || {}).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
            строк: {data?.items?.length ?? 0}
          </span>
        </div>

        {!!err && (
          <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--dot-overdue)' }}>{err}</div>
        )}

        <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ ...th, width: 56 }}>№</th>
                <th style={th}>Что случилось</th>
                <th style={{ ...th, width: 210 }}>Где</th>
                <th style={{ ...th, width: 170 }}>Кто</th>
                <th style={{ ...th, width: 150 }}>Когда</th>
                <th style={{ ...th, width: 150 }}>Статус</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).length === 0 && (
                <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>
                  Заявок нет. Это хорошая новость ровно до тех пор, пока кнопку видят —
                  она рядом с колокольчиком и в кабинете площадки.
                </td></tr>
              )}
              {(data?.items || []).map(r => (
                <tr key={r.id} onClick={() => show(r.id)} style={{ cursor: 'pointer' }}>
                  <td style={{ ...td, fontFamily: MONO }}>{r.id}</td>
                  <td style={{ ...td, fontWeight: r.seen_at ? 400 : 700 }}>
                    {(r.comment || '').slice(0, 120)}{(r.comment || '').length > 120 ? '…' : ''}
                    {r.files > 0 && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-faint)' }}>
                        📎 {r.files}
                      </span>
                    )}
                  </td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 11.5 }}>
                    {r.page_title || r.page_url || '—'}
                  </td>
                  <td style={td}>
                    <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{r.contour_label}</span>
                    <div>{r.author}</div>
                  </td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 11.5 }}>{fmtDateTime(r.created_at)}</td>
                  <td style={td}><span style={chip(r.status)}>{r.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {open && (
          <div {...overlayClose(() => setOpen(null))}
            style={{ position: 'fixed', inset: 0, background: 'rgba(20,26,38,.45)', zIndex: 200,
              display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
              padding: '40px 16px', overflowY: 'auto' }}>
            <div style={{ ...card, width: 760, maxWidth: '100%', padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{ fontSize: 17, fontWeight: 700 }}>Заявка №{open.id}</span>
                <span style={chip(open.status)}>{open.status}</span>
                <span onClick={() => setOpen(null)} style={{ marginLeft: 'auto', cursor: 'pointer',
                  fontSize: 22, lineHeight: 1, color: 'var(--text-muted)' }}>×</span>
              </div>

              <div style={{ marginTop: 10, fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                {open.comment}
              </div>

              {/* Обстановка — то, ради чего заявка вообще имеет смысл. */}
              <div style={{ marginTop: 12, fontFamily: MONO, fontSize: 11, lineHeight: 1.7,
                color: 'var(--text-faint)' }}>
                <div>{open.contour_label} · {open.author}</div>
                <div>{open.page_title || '—'} · {open.page_url || '—'}</div>
                <div>
                  версия {open.app_version || '—'} · окно {open.viewport || '—'}
                  {open.seen_at ? ` · прочитал ${open.seen_by || '—'} ${fmtDateTime(open.seen_at)}` : ''}
                </div>
                {!!open.resolved_at && (
                  <div>закрыл {open.resolved_by || '—'} · {fmtDateTime(open.resolved_at)}</div>
                )}
                {!!open.user_agent && <div>{open.user_agent}</div>}
              </div>

              {(open.file_list || []).length > 0 && (
                <div style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {open.file_list.map(f => (
                    <a key={f.id} href={`/api/bugs/${open.id}/file/${f.id}`} target="_blank"
                      rel="noreferrer" style={{ display: 'block' }}>
                      {/* Снимок показываем, а не даём ссылкой: разбор начинается с того,
                          что человек смотрит на картинку, а не скачивает её. */}
                      <img src={`/api/bugs/${open.id}/file/${f.id}`} alt={f.name || 'снимок'}
                        style={{ height: 120, borderRadius: 8, border: '1px solid var(--border-card)' }} />
                    </a>
                  ))}
                </div>
              )}

              {mayEdit && (
                <>
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 4 }}>
                      Чем закончилось — без этого закрыть нельзя
                    </div>
                    <textarea value={resolution} onChange={e => setResolution(e.target.value)}
                      rows={2} placeholder="что оказалось и что сделали"
                      style={{ ...inp, width: '100%', boxSizing: 'border-box', height: 'auto',
                        padding: 9, fontFamily: UI, fontSize: 13 }} />
                  </div>

                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    {(data?.statuses || []).map(s => (
                      <button key={s} style={btnSm(open.status === s)} disabled={busy}
                        onClick={() => patch({ status: s, resolution })}>{s}</button>
                    ))}
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
                      {open.backlog_item_id ? (
                        <Link href="/settings/backlog" style={{ ...btn, textDecoration: 'none' }}>
                          наблюдение №{open.backlog_item_id}
                        </Link>
                      ) : (
                        <button style={btn} disabled={busy} onClick={toBacklog}>
                          Завести наблюдение
                        </button>
                      )}
                      <button style={primaryBtn} disabled={busy}
                        onClick={() => patch({ resolution })}>Сохранить</button>
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
