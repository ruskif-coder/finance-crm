import { useMemo, useRef, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, UI, card, Modal, primaryBtn, btn, PickValue } from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import { DownloadOverlay } from '@/components/LogoLoader'
import { downloadName, fmtDateShort, grpDec } from '@/lib/salesFormat'
import { todayMsk } from '@/lib/dates'

// Вторая вкладка «Аудитория»: сетка заполнения — все поля площадок в одном месте, правка прямо в
// ячейках, «Скачать Excel» и «Загрузить Excel» (владелец 09.10.2026). Две группы колонок:
//   · «Аудитория — замеры»: пишутся в замеры этого экрана с источником и датой, история остаётся;
//   · «Из карточки площадки» — поля, что в системе уже были (трафик, SimilarWeb, запросы кода,
//     покрытие): привязаны к тем же таблицам, что карточка и балансировщик, и ПЕРЕЗАПИСЫВАЮТ замер
//     текущего месяца, как в карточке. Второго склада тех же цифр здесь нет.
// Пустая ячейка — «нет значения»; очистить значение с этой вкладки нельзя (это делается в карточке).

const COL = 112
const mono = (e) => ({ fontFamily: MONO, ...e })
const num = (s) => Number(String(s).replace(/\s/g, '').replace(',', '.'))
const fmt = (v, pct) => grpDec(v, pct ? 2 : 1)

export default function AudienceData({ grid, sources, canEdit, onSaved }) {
  const [edits, setEdits] = useState({})            // { 'pid|key': 'строка' }
  const [q, setQ] = useState('')
  const [source, setSource] = useState('медиакит')
  const [when, setWhen] = useState(todayMsk())
  const [vpop, setVpop] = useState(null)
  const [busy, setBusy] = useState('')              // '' | 'save' | 'export' | 'import'
  const [msg, setMsg] = useState(null)              // { ok, text }
  const [preview, setPreview] = useState(null)
  const fileRef = useRef(null)
  const fileObj = useRef(null)

  const fields = useMemo(() => grid?.fields || [], [grid])
  const groups = useMemo(() => ['audience', 'system'].map(g => ({ g, cols: fields.filter(f => f.group === g) })), [fields])
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (grid?.publishers || []).filter(p => !s || p.name.toLowerCase().includes(s))
  }, [grid, q])

  const changed = useMemo(() => Object.entries(edits).filter(([k, v]) => {
    if (String(v).trim() === '') return false
    const [pid, key] = k.split('|')
    const cur = grid?.publishers.find(p => p.id === Number(pid))?.values?.[key]?.value
    return Number.isFinite(num(v)) && (cur == null || Math.abs(cur - num(v)) > 1e-9)
  }), [edits, grid])
  const bad = Object.entries(edits).filter(([, v]) => String(v).trim() !== '' && !Number.isFinite(num(v))).length

  const setCell = (pid, key, v) => setEdits(e => ({ ...e, [`${pid}|${key}`]: v }))

  const save = async () => {
    if (!source.trim()) { setMsg({ ok: false, text: 'Источник обязателен: без него цифра ничего не стоит' }); return }
    setBusy('save'); setMsg(null)
    try {
      const items = changed.map(([k, v]) => { const [pid, key] = k.split('|'); return { publisher_id: Number(pid), key, value: num(v) } })
      const r = await api.post('/publisher-audience/bulk', { source, measured_at: when, items }, auth())
      setEdits({})
      setMsg({ ok: true, text: `Записано ${r.data.written}, без изменений ${r.data.skipped_same}, площадок ${r.data.publishers}` })
      onSaved?.()
    } catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || 'Не удалось сохранить' }) } finally { setBusy('') }
  }

  const exportXlsx = async () => {
    setBusy('export'); setMsg(null)
    try {
      const r = await api.get('/publisher-audience/export.xlsx', { responseType: 'blob', ...auth() })
      const url = window.URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a'); a.href = url
      a.download = downloadName('аудитория площадок', 'xlsx', 'SIMB-AD')
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url)
    } catch (e) {
      let t = ''
      try { t = JSON.parse(await e.response?.data?.text()).detail } catch { /* не json */ }
      setMsg({ ok: false, text: t || 'Не удалось выгрузить Excel' })
    } finally { setBusy('') }
  }

  const pickFile = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    fileObj.current = f
    setBusy('import'); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await api.post('/publisher-audience/import?apply=false', fd, auth())
      setPreview(r.data)
    } catch (err) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Не удалось прочитать файл' }) } finally { setBusy('') }
  }
  const applyImport = async () => {
    setBusy('import')
    try {
      const fd = new FormData(); fd.append('file', fileObj.current)
      const r = await api.post('/publisher-audience/import?apply=true', fd, auth())
      setPreview(null)
      setMsg({ ok: true, text: `Загружено: записано ${r.data.written}, площадок ${r.data.publishers}, ошибок ${r.data.errors_total}` })
      onSaved?.()
    } catch (err) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Не удалось загрузить' }) } finally { setBusy('') }
  }

  const btnS = (on) => ({ ...btn(false), height: 32, padding: '0 14px', opacity: on ? 1 : 0.5, cursor: on ? 'pointer' : 'default' })
  const head = (extra) => mono({ fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-cap)', ...extra })

  return (
    <div style={{ ...card, padding: '16px 22px 14px', display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
      {busy === 'export' && <DownloadOverlay label="Готовим Excel…" />}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 12px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, minWidth: 200 }}>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Площадка…" style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)' }} />
        </span>
        {canEdit && (
          <>
            <span style={head({ marginLeft: 8 })}>источник</span>
            <span data-pop-root><PickValue value={source} placeholder="выбрать" onOpen={e => setVpop(e.currentTarget.getBoundingClientRect())} /></span>
            <span style={head()}>дата замера</span>
            <input type="date" value={when} max={todayMsk()} onChange={e => setWhen(e.target.value)}
              style={{ height: 32, padding: '0 10px', border: '1px solid var(--border-card)', borderRadius: 10, background: 'var(--bg-card)', fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)' }} />
          </>
        )}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
          <button type="button" style={btnS(true)} onClick={exportXlsx} disabled={!!busy}>↓ Скачать Excel</button>
          {canEdit && <button type="button" style={btnS(true)} onClick={() => fileRef.current?.click()} disabled={!!busy}>↑ Загрузить Excel</button>}
          {canEdit && <button type="button" style={{ ...primaryBtn, height: 32, padding: '0 14px', opacity: changed.length && !bad ? 1 : 0.5 }}
            disabled={!changed.length || !!bad || !!busy} onClick={save}>Сохранить{changed.length ? ` (${changed.length})` : ''}</button>}
          {!!Object.keys(edits).length && <button type="button" style={btnS(true)} onClick={() => setEdits({})}>Сбросить</button>}
        </span>
        <input ref={fileRef} type="file" accept=".xlsx" onChange={pickFile} style={{ display: 'none' }} />
      </div>
      {!!msg && <div role="status" style={{ fontSize: 12.5, fontWeight: 600, color: msg.ok ? 'var(--income-fg)' : 'var(--danger-fg)' }}>{msg.text}</div>}
      {!!bad && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>В {bad} ячейках не число — исправьте, иначе сохранить нельзя.</div>}

      <div style={{ overflow: 'auto', maxHeight: 'calc(100vh - 330px)', border: '1px solid var(--border-inner)', borderRadius: 12 }}>
        <div style={{ minWidth: 230 + fields.length * COL }}>
          <div style={{ display: 'grid', gridTemplateColumns: `230px repeat(${fields.length}, ${COL}px)`, position: 'sticky', top: 0, zIndex: 4, background: 'var(--bg-card)' }}>
            <span style={{ position: 'sticky', left: 0, zIndex: 5, background: 'var(--bg-card)' }} />
            {groups.map(({ g, cols }) => (
              <span key={g} style={{ gridColumn: `span ${cols.length}`, padding: '8px 10px 4px', borderLeft: '1px solid var(--border-inner)', ...head({ fontWeight: 700, color: g === 'audience' ? 'var(--accent-fg)' : 'var(--income-fg)' }) }}>
                {g === 'audience' ? 'Аудитория · замеры с источником и датой' : 'Из карточки площадки · перезаписывает месяц, без истории'}
              </span>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: `230px repeat(${fields.length}, ${COL}px)`, position: 'sticky', top: 27, zIndex: 4, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)' }}>
            <span style={{ position: 'sticky', left: 0, zIndex: 5, background: 'var(--bg-card)', padding: '4px 10px 8px', ...head() }}>Площадка</span>
            {fields.map(f => <span key={f.key} style={{ padding: '4px 8px 8px', textAlign: 'right', lineHeight: 1.25, ...head() }}>{f.label}</span>)}
          </div>
          {rows.map(p => (
            <div key={p.id} className="aud-data-row" style={{ display: 'grid', gridTemplateColumns: `230px repeat(${fields.length}, ${COL}px)`, borderBottom: '1px solid var(--border-row)', alignItems: 'center' }}>
              <span style={{ position: 'sticky', left: 0, zIndex: 3, background: 'var(--bg-card)', padding: '5px 10px', display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                <span style={mono({ fontSize: 9, color: 'var(--text-faint)' })}>{p.kind || '—'}</span>
              </span>
              {fields.map(f => {
                const k = `${p.id}|${f.key}`
                const cur = p.values[f.key]
                const edited = k in edits && String(edits[k]).trim() !== ''
                const isBad = edited && !Number.isFinite(num(edits[k]))
                const isChanged = edited && !isBad && (cur == null || Math.abs(cur.value - num(edits[k])) > 1e-9)
                return (
                  <span key={f.key} style={{ padding: '3px 4px' }} title={cur ? `${cur.source}${cur.measured_at ? ` · ${fmtDateShort(cur.measured_at)}` : ''}` : 'значения нет'}>
                    <input value={k in edits ? edits[k] : fmt(cur?.value, f.pct)} disabled={!canEdit}
                      onChange={e => setCell(p.id, f.key, e.target.value)} inputMode="decimal"
                      style={mono({ width: '100%', boxSizing: 'border-box', height: 28, padding: '0 8px', textAlign: 'right', fontSize: 12, outline: 'none',
                        border: `1px solid ${isBad ? 'var(--danger-border)' : isChanged ? 'var(--accent-border)' : 'transparent'}`,
                        background: isBad ? 'var(--danger-tint)' : isChanged ? 'var(--accent-tint)' : 'transparent', borderRadius: 7,
                        color: cur || edited ? 'var(--text-primary)' : 'var(--text-disabled)' })}
                      placeholder="—" />
                  </span>
                )
              })}
            </div>
          ))}
          {!rows.length && <div style={{ padding: 28, textAlign: 'center', fontSize: 12.5, color: 'var(--text-faint)' }}>Ничего не найдено</div>}
        </div>
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.45 }}>
        Подсказка у ячейки — источник и дата последнего значения. Изменённые ячейки подсвечены; «Сохранить» записывает их одним источником и датой.
        Excel из выгрузки читается обратно по колонке ID: заполните «Источник» (и при желании «Дата замера») в строках, где что-то поменяли, неизменённое пропускается.
        Доли — в процентах. Показано {rows.length} из {grid?.publishers?.length ?? 0} активных площадок.
      </span>
      <style>{'.aud-data-row:hover > span:not(:first-child){background:var(--bg-subtle)}'}</style>

      {vpop && <ValuePopover anchor={vpop} title="Источник" value={source} options={(sources || []).map(s => ({ value: s, label: s }))}
        onPick={v => { if (v) setSource(v); setVpop(null) }} onAddNew={v => { setSource(v); setVpop(null) }} onClose={() => setVpop(null)} />}

      {preview && (
        <Modal title="Загрузка из Excel · предпросмотр" width={560} onClose={() => setPreview(null)}
          footer={<>
            <button type="button" style={btn(false)} onClick={() => setPreview(null)}>Отмена</button>
            <button type="button" style={{ ...primaryBtn, opacity: preview.written ? 1 : 0.5 }} disabled={!preview.written || busy === 'import'} onClick={applyImport}>
              Применить ({preview.written})</button>
          </>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
            <span>Будет записано значений: <b>{preview.written}</b> по <b>{preview.publishers}</b> площадкам. Без изменений: {preview.skipped_same}.</span>
            {!!preview.unknown_columns?.length && <span style={{ color: 'var(--warning-fg)' }}>Неизвестные колонки пропущены: {preview.unknown_columns.join(', ')}</span>}
            {preview.errors_total > 0 && (
              <div>
                <div style={{ color: 'var(--danger-fg)', fontWeight: 600, marginBottom: 4 }}>Отклонено строк с ошибками: {preview.errors_total}</div>
                <pre style={{ margin: 0, padding: '8px 10px', background: 'var(--bg-subtle)', borderRadius: 8, fontSize: 11.5, maxHeight: 180, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{preview.errors.join('\n')}</pre>
              </div>
            )}
            {!preview.written && <span style={{ color: 'var(--text-muted)' }}>Нечего записывать: либо значения совпадают с текущими, либо в строках не указан источник.</span>}
          </div>
        </Modal>
      )}
    </div>
  )
}
