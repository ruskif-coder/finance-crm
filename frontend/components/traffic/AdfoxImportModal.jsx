// Окно «Импорт ADFOX» (владелец 02.10.2026): суточный отчёт Adfox → факт РК.
// Шаги со статусами: файл уходит на сервер (полоса загрузки настоящая) → разбор и
// сопоставление → предпросмотр: каждая строка «сопоставлена / неоднозначно / не
// сопоставлена» и что станет с фактом («новые данные / обновление было → станет / без
// изменений»). Неоднозначные — выбор из предложенных вариантов или поиск по коду.
// Запись — пачками, полоса хода по пачкам; итог словами, действие — в журнал.
import { useMemo, useRef, useState } from 'react'
import { Modal, btnSm, primaryBtn, inp, MONO, th, td } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import { grp } from '@/lib/salesFormat'
import api from '@/lib/api'

const BASE = '/traffic-dashboard/adfox-import'
const CHUNK = 60   // строк файла за вызов записи; размещение×день не разрезается

const STATUS = {
  matched: { label: 'сопоставлена', color: 'var(--income-fg)' },
  ambiguous: { label: 'неоднозначно', color: 'var(--warning-text)' },
  unmatched: { label: 'не сопоставлена', color: 'var(--danger-fg)' },
}
const CHANGE = {
  new: { label: 'новые данные', color: 'var(--accent)' },
  update: { label: 'обновление', color: 'var(--warning-text)' },
  same: { label: 'без изменений', color: 'var(--text-faint)' },
}

const errText = (e, dflt) => e?.response?.data?.detail || dflt
const dayRu = (iso) => (iso ? iso.split('-').reverse().join('.') : '')

// Размещение × день записывается СУММОЙ и перезаписывает прежнюю (ревью 03.10.2026):
// если у дня отмечены не все строки с креативом, в факт легла бы половина. Такой день
// не пишется целиком — возвращаем строки, которые реально уйдут, и сколько отложено.
function writable(rows) {
  const groups = {}
  rows.filter(r => r.creative_id && r.placement_id).forEach(r => {
    const k = `${r.placement_id}|${r.day}`; (groups[k] = groups[k] || []).push(r)
  })
  const ok = [], held = []
  Object.values(groups).forEach(g => {
    if (g.every(r => r.take)) ok.push(...g)
    else held.push(...g.filter(r => r.take))
  })
  return { ok, held }
}

// Чанки по размещению×дню: запись перезаписывает сумму дня, разрезанная группа
// оставила бы в факте половину.
function chunked(rows) {
  const groups = {}
  rows.forEach(r => { const k = `${r.placement_id}|${r.day}`; (groups[k] = groups[k] || []).push(r) })
  const out = []; let cur = []
  Object.values(groups).forEach(g => {
    if (cur.length && cur.length + g.length > CHUNK) { out.push(cur); cur = [] }
    cur = cur.concat(g)
  })
  if (cur.length) out.push(cur)
  return out
}

function Pick({ row, onPick, auth }) {
  const [q, setQ] = useState('')
  const [found, setFound] = useState(null)
  const [busy, setBusy] = useState(false)
  const find = async () => {
    if (q.trim().length < 2) return
    setBusy(true)
    try { setFound((await api.get(`${BASE}/search`, { ...auth(), params: { q: q.trim() } })).data.items) }
    catch { setFound([]) }
    setBusy(false)
  }
  const opts = found || row.candidates || []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {!!row.reason && <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{row.reason}</div>}
      {opts.slice(0, 6).map(c => (
        <button key={c.creative_id} type="button" onClick={() => onPick(c)}
          style={{ ...btnSm(row.pick?.creative_id === c.creative_id), textAlign: 'left', display: 'block' }}
          title={c.why}>
          {c.label}<span style={{ color: 'var(--text-faint)', marginLeft: 6, fontSize: 11 }}>{c.why}</span>
        </button>
      ))}
      {found && !found.length && <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>ничего не найдено</div>}
      <div style={{ display: 'flex', gap: 6 }}>
        <input style={{ ...inp, padding: '4px 8px', fontSize: 12, flex: 1 }} value={q}
          placeholder="код сделки или площадки" onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') find() }} />
        <button type="button" style={btnSm(false)} onClick={find} disabled={busy}>
          {busy ? '…' : 'найти'}
        </button>
      </div>
    </div>
  )
}

export default function AdfoxImportModal({ auth, onClose, onDone }) {
  const fileRef = useRef(null)
  const [stage, setStage] = useState(null)   // { text, pct }
  const [err, setErr] = useState('')
  const [file, setFile] = useState(null)
  const [rows, setRows] = useState(null)
  const [res, setRes] = useState(null)

  const busy = !!stage && !res

  const upload = async (f) => {
    if (!f) return
    setErr(''); setRows(null); setRes(null); setFile(f.name)
    const fd = new FormData(); fd.append('file', f)
    setStage({ text: 'загружаю файл', pct: 0 })
    try {
      const r = await api.post(`${BASE}/preview`, fd, {
        ...auth(),
        onUploadProgress: (e) => {
          const p = e.total ? Math.round((e.loaded / e.total) * 100) : 0
          setStage(p >= 100 ? { text: 'сопоставляю строки с РК и сверяю с загруженным', pct: null }
            : { text: 'загружаю файл', pct: p })
        },
      })
      setRows(r.data.rows.map(x => ({ ...x, take: x.status === 'matched' && x.change !== 'same' })))
      setStage(null)
    } catch (e) {
      setStage(null)
      setErr(errText(e, 'Не удалось разобрать файл'))
    }
  }

  const pick = async (row, c) => {
    setErr('')
    try {
      const r = await api.post(`${BASE}/state`, {
        rows: [{ line: row.line, day: row.day, creative_id: c.creative_id, shows: row.shows,
          clicks: row.clicks, uniques: row.uniques }],
      }, auth())
      const st = r.data.rows[0] || {}
      setRows(rs => rs.map(x => x.line !== row.line ? x : {
        ...x, pick: c, label: c.label, creative_id: c.creative_id, placement_id: c.placement_id,
        change: st.change, was: st.was, will: st.will, take: true,
      }))
    } catch (e) { setErr(errText(e, 'Не удалось проверить выбранный креатив')) }
  }

  const sum = useMemo(() => {
    if (!rows) return null
    const s = { matched: 0, ambiguous: 0, unmatched: 0, new: 0, update: 0, same: 0, picked: 0 }
    rows.forEach(r => {
      s[r.status] += 1
      if (r.pick) s.picked += 1
      if (r.change && (r.status === 'matched' || r.pick)) s[r.change] += 1
    })
    const w = writable(rows)
    s.take = w.ok.length
    s.held = w.held.length
    s.skip = rows.length - s.take
    return s
  }, [rows])

  const go = async () => {
    const take = writable(rows).ok
    const chunks = chunked(take)
    let written = 0
    let failure = null
    setErr('')
    try {
      for (let i = 0; i < chunks.length; i += 1) {
        setStage({ text: `записываю ${i + 1} из ${chunks.length}`, pct: Math.round((i / chunks.length) * 100) })
        const r = await api.post(`${BASE}/apply`, {
          rows: chunks[i].map(x => ({ line: x.line, day: x.day, creative_id: x.creative_id,
            shows: x.shows, clicks: x.clicks, uniques: x.uniques })),
        }, auth())
        written += r.data.written
      }
      setStage({ text: 'готово', pct: 100 })
      setRes({ written, skipped: rows.length - take.length })
      onDone && onDone()
    } catch (e) {
      failure = errText(e, 'Запись прервалась')
      setStage(null)
      setErr(`${failure} — записано строк факта: ${written}. Повторная загрузка того же файла безопасна: дни перезаписываются.`)
    } finally {
      // Журнал — и при сбое на середине: частичная запись не должна остаться без следа.
      try {
        await api.post(`${BASE}/done`, { file, written, skipped: rows.length - take.length,
          days: [...new Set(take.map(x => x.day))], error: failure }, auth())
      } catch { /* журнал — не повод прятать итог */ }
    }
  }

  const unresolved = rows ? rows.filter(r => r.status !== 'matched' && !r.pick).length : 0

  const footer = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
      {!!err && <span style={{ fontSize: 12.5, color: 'var(--danger-fg)', marginRight: 'auto' }}>⚠ {err}</span>}
      {!err && !!rows && !res && (unresolved > 0 || sum.held > 0) && (
        <span style={{ fontSize: 12.5, color: 'var(--warning-text)', marginRight: 'auto' }}>
          {unresolved > 0 && `не разобрано строк: ${unresolved} — они не запишутся`}
          {unresolved > 0 && sum.held > 0 && ' · '}
          {sum.held > 0 && `${sum.held} строк отложено: у площадки за день отмечены не все креативы`}
        </span>
      )}
      <button style={btnSm(false)} onClick={onClose} disabled={busy}>{res ? 'Закрыть' : 'Отмена'}</button>
      {!!rows && !res && (
        <button style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 8,
          opacity: sum.take ? 1 : 0.6, cursor: busy ? 'progress' : 'pointer' }}
          disabled={busy || !sum.take} onClick={go}>
          {busy && <Cube variant="spinner" size={14} />}
          {sum.take ? `Загрузить (${sum.take})` : 'Загружать нечего'}
        </button>
      )}
    </div>
  )

  const summary = sum
    ? `строк ${rows.length} · сопоставлено ${sum.matched + sum.picked} · неоднозначно ${sum.ambiguous - sum.picked > 0 ? sum.ambiguous - sum.picked : 0}`
      + ` · не сопоставлено ${sum.unmatched} · новых ${sum.new} · обновлений ${sum.update} · без изменений ${sum.same}`
    : 'Суточный отчёт Adfox: День · Название кампании · Показы · Переходы · Уникальные показы'

  return (
    <Modal title="Импорт ADFOX" summary={summary} footer={footer} width={1040}
      onClose={() => { if (!busy) onClose() }}>
      <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
        onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />

      {!rows && !stage && (
        <div style={{ padding: '18px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button style={primaryBtn} onClick={() => fileRef.current?.click()}>Выбрать файл .xlsx</button>
          <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
            Ничего не записывается, пока вы не проверите строки и не нажмёте «Загрузить».
            Строки, которых нет в отчёте, — «нет данных», а не ноль.
          </span>
        </div>
      )}

      {!!stage && (
        <div style={{ margin: '6px 0 12px' }}>
          <div style={{ height: 8, borderRadius: 6, background: 'var(--bg-subtle)', overflow: 'hidden' }}>
            <div style={{ width: `${stage.pct == null ? 100 : stage.pct}%`, height: '100%',
              background: 'var(--accent)', opacity: stage.pct == null ? 0.45 : 1, transition: 'width .35s ease' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontSize: 12.5, color: 'var(--text-muted)' }}>
            {busy && <Cube variant="spinner" size={12} />}{stage.text}{stage.pct != null && stage.pct < 100 ? ` · ${stage.pct} %` : ''}
          </div>
        </div>
      )}

      {!!res && (
        <div style={{ padding: '10px 12px', margin: '0 0 10px', borderRadius: 10, fontSize: 13,
          background: 'var(--income-tint)', color: 'var(--income-fg)' }}>
          Записано строк факта (размещение × день): {res.written}
          {res.skipped ? ` · строк файла не загружено: ${res.skipped}` : ''}
        </div>
      )}

      {!!rows && (
        <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={th}></th><th style={th}>День</th><th style={th}>Кампания Adfox</th>
                <th style={{ ...th, textAlign: 'right' }}>Показы</th><th style={{ ...th, textAlign: 'right' }}>Перех.</th>
                <th style={{ ...th, textAlign: 'right' }}>Уник.</th><th style={th}>Сопоставление</th><th style={th}>Факт</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const st = STATUS[r.status]
                const ch = r.change && CHANGE[r.change]
                const canTake = !!r.creative_id && (r.status === 'matched' || !!r.pick)
                return (
                  <tr key={r.line}>
                    <td style={{ ...td, padding: '6px 8px', width: 24 }}>
                      <input type="checkbox" checked={!!r.take} disabled={!canTake || busy || !!res}
                        onChange={e => setRows(rs => rs.map(x => x.line === r.line ? { ...x, take: e.target.checked } : x))} />
                    </td>
                    <td style={{ ...td, padding: '6px 8px', fontFamily: MONO, fontSize: 11.5, whiteSpace: 'nowrap' }}>{dayRu(r.day)}</td>
                    <td style={{ ...td, padding: '6px 8px', fontFamily: MONO, fontSize: 11.5 }}>{r.name}</td>
                    <td style={{ ...td, padding: '6px 8px', textAlign: 'right', fontFamily: MONO }}>{grp(r.shows)}</td>
                    <td style={{ ...td, padding: '6px 8px', textAlign: 'right', fontFamily: MONO }}>{grp(r.clicks)}</td>
                    <td style={{ ...td, padding: '6px 8px', textAlign: 'right', fontFamily: MONO }}>{r.uniques == null ? '—' : grp(r.uniques)}</td>
                    <td style={{ ...td, padding: '6px 8px', minWidth: 260 }}>
                      <div style={{ fontWeight: 600, color: r.pick ? 'var(--income-fg)' : st.color }}>
                        {r.pick ? 'выбрано вручную' : st.label}
                      </div>
                      {(r.status === 'matched' || r.pick) && <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{r.label}</div>}
                      {r.status !== 'matched' && !res && <Pick row={r} auth={auth} onPick={c => pick(r, c)} />}
                    </td>
                    <td style={{ ...td, padding: '6px 8px', whiteSpace: 'nowrap' }}>
                      {ch ? (
                        <>
                          <div style={{ fontWeight: 600, color: ch.color }}>{ch.label}</div>
                          {r.change === 'update' && r.was && r.will && (
                            <div style={{ fontFamily: MONO, fontSize: 11 }}>
                              {grp(r.was.shows)} → {grp(r.will.shows)}
                            </div>
                          )}
                          {r.change === 'new' && r.will && r.will.shows !== r.shows && (
                            <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>за день по площадке {grp(r.will.shows)}</div>
                          )}
                        </>
                      ) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}
