import { useState, useEffect, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'
import api, { auth } from '../lib/api'

export default function Pipelines({ embedded = false } = {}) {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [expanded, setExpanded] = useState(null)
  const [stages, setStages] = useState({})   // { pipelineId: {items, bitrix_category_id} }
  const [expandAll, setExpandAll] = useState(false)
  const [busy, setBusy] = useState(false)

  const mayEdit = can(perms, 'settings', 'edit')
  const mayDelete = can(perms, 'settings', 'edit')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const r = await api.get('/sales/directories/pipelines', auth())
      setItems(r.data.items)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить воронки') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }

  const refresh = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.post('/sales/directories/pipelines/refresh', {}, auth())
      flash(`Обновлено из Битрикса: воронок +${r.data.pipelines_added} (переим. ${r.data.pipelines_renamed || 0}), стадий +${r.data.stages_added}, переименовано стадий ${r.data.stages_renamed}`)
      await load()
    } catch (e) { setError(e.response?.data?.detail || 'Обновление недоступно') }
    finally { setBusy(false) }
  }

  const loadStagesFor = async (p) => {
    if (stages[p.id]) return
    try {
      const r = await api.get(`/sales/directories/pipelines/${p.id}/stages`, auth())
      setStages(s => ({ ...s, [p.id]: r.data }))
    } catch (e) { /* тихо */ }
  }

  const toggleAll = async () => {
    const next = !expandAll
    setExpandAll(next)
    if (next) { for (const p of items) { await loadStagesFor(p) } }
  }

  const isOpen = (p) => expandAll || expanded === p.id

  const toggleExpand = async (p) => {
    if (expanded === p.id) { setExpanded(null); return }
    setExpanded(p.id)
    if (!stages[p.id]) {
      try {
        const r = await api.get(`/sales/directories/pipelines/${p.id}/stages`, auth())
        setStages(s => ({ ...s, [p.id]: r.data }))
      } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить стадии') }
    }
  }

  // Привязка стадии к светофору 2/2/2. Пустое значение снимает привязку.
  // Обновляем локально, чтобы селектор сразу показал новый слой.
  const mapStage = async (p, stage, stageKey) => {
    setError('')
    try {
      const r = await api.put(
        `/sales/directories/pipelines/${p.id}/stages/${stage.id}/mapping`,
        { stage_key: stageKey || null }, auth())
      setStages(s => ({
        ...s,
        [p.id]: {
          ...s[p.id],
          items: s[p.id].items.map(it => it.id === stage.id
            ? { ...it, stage_key: r.data.stage_key, money_layer: r.data.money_layer } : it),
        },
      }))
      flash(r.data.message)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось привязать стадию') }
  }

  // Цвет слоя денег — тот же язык, что в реестре сделок.
  const layerColor = (l) => l === 'фактические' ? 'var(--success)'
    : l === 'реализуемые' ? 'var(--warning, #d97706)'
    : l === 'планируемые' ? 'var(--muted)' : 'var(--danger)'

  const toggle = async (p) => {
    setError('')
    try {
      await api.put(`/sales/directories/pipelines/${p.id}/tracked`,
        { is_tracked: !p.is_tracked }, auth())
      flash(`«${p.name}»: ${!p.is_tracked ? 'парсится' : 'не парсится'}`)
      load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось изменить') }
  }

  const rename = async (p) => {
    setError('')
    const next = window.prompt(`Новое название воронки «${p.name}»:`, p.name)
    if (next === null) return
    const name = next.trim()
    if (!name || name === p.name) return
    try {
      const r = await api.put(`/sales/directories/pipelines/${p.id}/name`, { name }, auth())
      flash(`Переименовано: «${p.name}» → «${r.data.name}»`)
      load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось переименовать') }
  }

  const remove = async (p) => {
    setError('')
    // Удаление воронки уносит все её сделки. Подтверждение обязательно
    // и показывает число сделок, чтобы удаление не было случайным.
    if (!window.confirm(
      `Удалить воронку «${p.name}» и все её сделки (${p.deals} шт.)?\n\n` +
      `Это необратимо. Данные и их сырьё будут удалены физически.`)) return
    try {
      const r = await api.delete(`/sales/directories/pipelines/${p.id}`, auth())
      flash(r.data.message)
      load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось удалить') }
  }

  const btn = (variant) => ({
    padding: '5px 12px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 12.5, fontWeight: 500,
    background: variant === 'danger' ? 'var(--danger-tint)' : 'var(--bg-subtle)',
    color: variant === 'danger' ? 'var(--danger)' : 'inherit',
  })
  const th = { padding: '9px 12px', textAlign: 'left', fontSize: 11.5, fontWeight: 600,
    color: 'var(--muted)', borderBottom: '1px solid var(--border-card)' }
  const td = { padding: '10px 12px', fontSize: 13.5, borderBottom: '1px solid var(--border-row)' }

  return (
    <>
      {!embedded && <Head><title>Воронки</title></Head>}
      {!embedded && <Navbar active="directories" />}
      <div style={{ padding: embedded ? 0 : '20px 24px 50px' }}>

        {!embedded && <DirectoryTabs active="pipelines" />}

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 6 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Воронки</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length}</span>
          <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
            {!!items.length && (
              <button style={btn()} onClick={toggleAll}>{expandAll ? 'Свернуть все' : 'Развернуть все'}</button>
            )}
            {mayEdit && (
              <button style={btn()} disabled={busy} onClick={refresh}>{busy ? 'Обновление…' : 'Обновить из Битрикса'}</button>
            )}
          </div>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 0, marginBottom: 16 }}>
          «Парсить» — учитывать ли воронку при синхронизации с Битрикс24. Снятый флаг
          не трогает существующие данные. Удаление воронки уносит все её сделки безвозвратно.
        </p>

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)',
          marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading && <div style={{ color: 'var(--muted)' }}>Загрузка…</div>}

        {!loading && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card)', overflow: 'hidden', width: 'max-content' }}>
            <table style={{ borderCollapse: 'collapse' }}>
              <thead><tr>
                <th style={th}>Воронка</th>
                <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                <th style={{ ...th, textAlign: 'center' }}>Парсить</th>
                <th style={th}></th>
              </tr></thead>
              <tbody>
                {items.map(p => (
                  <Fragment key={p.id}>
                    <tr style={{ opacity: p.is_tracked ? 1 : 0.55 }}>
                      <td style={{ ...td, fontWeight: 500 }}>
                        <span onClick={() => toggleExpand(p)} style={{ cursor: 'pointer' }}>
                          <span style={{ color: 'var(--muted)', marginRight: 6, fontSize: 11 }}>
                            {isOpen(p) ? '▼' : '▶'}
                          </span>
                          {p.name}
                        </span>
                        {mayEdit && (
                          <button title="Переименовать" onClick={() => rename(p)}
                            style={{ marginLeft: 8, border: 'none', background: 'none', cursor: 'pointer',
                              color: 'var(--muted)', fontSize: 12.5, padding: 0 }}>✎</button>
                        )}
                      </td>
                      <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{p.deals}</td>
                      <td style={{ ...td, textAlign: 'center' }}>
                        <input type="checkbox" checked={p.is_tracked} disabled={!mayEdit}
                          onChange={() => toggle(p)} style={{ cursor: mayEdit ? 'pointer' : 'default' }} />
                      </td>
                      <td style={{ ...td, textAlign: 'right' }}>
                        {mayDelete && (
                          <button style={btn('danger')} onClick={() => remove(p)}>Удалить с данными</button>
                        )}
                      </td>
                    </tr>
                    {isOpen(p) && (
                      <tr>
                        <td colSpan={4} style={{ padding: '4px 12px 14px 32px', background: 'var(--bg-subtle)' }}>
                          {!stages[p.id] ? (
                            <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Загрузка стадий…</span>
                          ) : !stages[p.id].items.length ? (
                            <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                              Стадии не загружены. Запустите синхронизацию с Битрикс24.
                            </span>
                          ) : (
                            <>
                              <div style={{ fontSize: 11, color: 'var(--muted)', margin: '6px 0 10px' }}>
                                Воронка в Битриксе: id={stages[p.id].bitrix_category_id ?? '—'}
                                {' · '}«Светофор 2/2/2» задаёт слой денег для отчётов и реестра.
                                {stages[p.id].items.some(s => s.deals && !s.stage_key) && (
                                  <span style={{ color: 'var(--danger)', marginLeft: 6 }}>
                                    ⚠ есть стадии со сделками без привязки
                                  </span>
                                )}
                              </div>
                              <table style={{ borderCollapse: 'collapse' }}>
                                <tbody>
                                  {stages[p.id].items.map((s, i) => (
                                    <tr key={s.id}>
                                      <td style={{ padding: '4px 10px', fontSize: 12.5, color: 'var(--muted)', width: 26 }}>{i + 1}</td>
                                      <td style={{ padding: '4px 10px', fontSize: 13 }}>{s.name}</td>
                                      <td style={{ padding: '4px 10px', fontSize: 11.5, color: 'var(--muted)', fontFamily: 'monospace' }}>{s.status_id}</td>
                                      <td style={{ padding: '4px 10px', fontSize: 12.5, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: s.deals && !s.stage_key ? 'var(--danger)' : undefined }}>
                                        {s.deals ? `${s.deals} сд.` : ''}
                                      </td>
                                      <td style={{ padding: '4px 10px', textAlign: 'center' }}>
                                        {/* Точка-индикатор слоя денег текущей привязки */}
                                        <span title={s.money_layer || 'не привязана'} style={{
                                          display: 'inline-block', width: 9, height: 9, borderRadius: '50%',
                                          background: s.stage_key ? layerColor(s.money_layer) : 'var(--border-card)',
                                        }} />
                                      </td>
                                      <td style={{ padding: '4px 10px' }}>
                                        <select value={s.stage_key || ''} disabled={!mayEdit}
                                          onChange={e => mapStage(p, s, e.target.value)}
                                          style={{ padding: '3px 6px', fontSize: 12.5, borderRadius: 'var(--radius-input)',
                                            border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                                            color: 'inherit', cursor: mayEdit ? 'pointer' : 'default' }}>
                                          <option value="">— не учитывать —</option>
                                          {(stages[p.id].catalog || []).map(c => (
                                            <option key={c.key} value={c.key}>{c.label} · {c.money_layer}</option>
                                          ))}
                                        </select>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!items.length && (
                  <tr><td colSpan={4} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
                    Воронок нет
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
