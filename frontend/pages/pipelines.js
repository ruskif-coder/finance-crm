import { useState, useEffect, Fragment } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'

const api = axios.create({ baseURL: '/api' })
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

export default function Pipelines() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [expanded, setExpanded] = useState(null)
  const [stages, setStages] = useState({})   // { pipelineId: {items, bitrix_category_id} }

  const mayEdit = can(perms, 'sales_directories', 'edit')
  const mayDelete = can(perms, 'sales_directories', 'delete')

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

  const toggle = async (p) => {
    setError('')
    try {
      await api.put(`/sales/directories/pipelines/${p.id}/tracked`,
        { is_tracked: !p.is_tracked }, auth())
      flash(`«${p.name}»: ${!p.is_tracked ? 'парсится' : 'не парсится'}`)
      load()
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось изменить') }
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
      <Head><title>Воронки</title></Head>
      <Navbar active="directories" />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '20px 24px 50px' }}>

        <DirectoryTabs active="pipelines" />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 6 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Воронки</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{items.length}</span>
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
            borderRadius: 'var(--radius-card)', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
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
                      <td style={{ ...td, fontWeight: 500, cursor: 'pointer' }} onClick={() => toggleExpand(p)}>
                        <span style={{ color: 'var(--muted)', marginRight: 6, fontSize: 11 }}>
                          {expanded === p.id ? '▼' : '▶'}
                        </span>
                        {p.name}
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
                    {expanded === p.id && (
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
                              <div style={{ fontSize: 11, color: 'var(--muted)', margin: '6px 0' }}>
                                Воронка в Битриксе: id={stages[p.id].bitrix_category_id ?? '—'}
                              </div>
                              <table style={{ borderCollapse: 'collapse' }}>
                                <tbody>
                                  {stages[p.id].items.map((s, i) => (
                                    <tr key={s.id}>
                                      <td style={{ padding: '3px 10px', fontSize: 12.5, color: 'var(--muted)', width: 26 }}>{i + 1}</td>
                                      <td style={{ padding: '3px 10px', fontSize: 13 }}>{s.name}</td>
                                      <td style={{ padding: '3px 10px', fontSize: 11.5, color: 'var(--muted)', fontFamily: 'monospace' }}>{s.status_id}</td>
                                      <td style={{ padding: '3px 10px', fontSize: 12.5, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                                        {s.deals ? `${s.deals} сд.` : ''}
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
