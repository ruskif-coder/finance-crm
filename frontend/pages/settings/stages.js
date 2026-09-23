import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { MONO, UI, card, inp, sel, ci, cs, th, td, primaryBtn } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { markDirty, markClean } from '@/lib/unsaved'

// ── Наш каталог стадий (E1: движение сделки) ──
// Этапы (орг-группировка) → стадии. У стадии: разметка 2/2/2 (для ДДС), флаг терминала,
// и ОДНА привязка к битрикс воронка+стадия (два выпадающих). Правки копятся локально,
// коммит одним запросом «Сохранить все». Воронки в Битриксе НЕ трогаем (см. вкладку «Воронки»).
const layerColor = (l) => l === 'фактические' ? 'var(--success)'
  : l === 'реализуемые' ? 'var(--warning, #d97706)'
  : l === 'планируемые' ? 'var(--muted)' : 'var(--border-card)'

export default function SettingsStages() {
  const router = useRouter()
  const [phases, setPhases] = useState([])      // [{_k, id, name, stages:[{_k, id, name, stage_key, is_terminal, bitrix_pipeline_id, bitrix_status_id}]}]
  const [bxPipes, setBxPipes] = useState([])    // [{id, name, stages:[{status_id, name}]}]
  const [catalog, setCatalog] = useState([])    // под-этапы 2/2/2: [{key, label, money_layer}]
  const [blocks, setBlocks] = useState([])      // блоки карточки: [{key, label, stage_id|null}]
  const [loading, setLoading] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [ok, setOk] = useState('')
  const [err, setErr] = useState('')
  const kRef = useRef(1)
  const nextK = () => `k${kRef.current++}`

  // Правка каталога идёт ЩЕЛЧКАМИ (стрелки, переключатели), а не вводом — общий учёт
  // несохранённого её не видит. Поэтому экран отмечает правку сам (`markDirty`), и возврат
  // на вкладку не перечитывает каталог поверх неё (аудит 23.09.2026, 6.H3).
  useRefreshOnReturn(() => { if (!dirty) load() })
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('pipelines')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
    load()
  }, [])

  const load = async () => {
    setLoading(true); setErr('')
    try {
      const [c, b] = await Promise.all([
        api.get('/sales/directories/stage-catalog', auth()),
        api.get('/sales/directories/stage-catalog/bitrix-options', auth()),
      ])
      setPhases((c.data.phases || []).map(p => ({
        _k: nextK(), id: p.id, name: p.name,
        stages: (p.stages || []).map(s => ({ _k: nextK(), id: s.id, name: s.name,
          stage_key: s.stage_key || '', is_terminal: !!s.is_terminal,
          bitrix_pipeline_id: s.bitrix_pipeline_id || '', bitrix_status_id: s.bitrix_status_id || '' })),
      })))
      setCatalog(c.data.catalog || [])
      setBlocks(c.data.card_blocks || [])
      setBxPipes(b.data.pipelines || [])
      setDirty(false)
      markClean()
    } catch (e) { if (e.response?.status === 401) router.push('/login'); else setErr('Ошибка загрузки') }
    finally { setLoading(false) }
  }

  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }
  const touch = () => { setDirty(true); markDirty() }

  // ── мутаторы каталога (все помечают dirty) ──
  const setPhase = (pk, patch) => { setPhases(ps => ps.map(p => p._k === pk ? { ...p, ...patch } : p)); touch() }
  const setStage = (pk, sk, patch) => { setPhases(ps => ps.map(p => p._k !== pk ? p : { ...p, stages: p.stages.map(s => s._k === sk ? { ...s, ...patch } : s) })); touch() }
  const addPhase = () => { setPhases(ps => [...ps, { _k: nextK(), id: null, name: '', stages: [] }]); touch() }
  const delPhase = (pk) => { setPhases(ps => ps.filter(p => p._k !== pk)); touch() }
  const addStage = (pk) => { setPhases(ps => ps.map(p => p._k !== pk ? p : { ...p, stages: [...p.stages, { _k: nextK(), id: null, name: '', money_layer: '', is_terminal: false, bitrix_pipeline_id: '', bitrix_status_id: '' }] })); touch() }
  const setBlock = (key, stageId) => { setBlocks(bs => bs.map(b => b.key === key ? { ...b, stage_id: stageId } : b)); touch() }
  const delStage = (pk, sk) => { setPhases(ps => ps.map(p => p._k !== pk ? p : { ...p, stages: p.stages.filter(s => s._k !== sk) })); touch() }
  const movePhase = (pk, dir) => { setPhases(ps => { const i = ps.findIndex(p => p._k === pk); const j = i + dir; if (i < 0 || j < 0 || j >= ps.length) return ps; const n = [...ps];[n[i], n[j]] = [n[j], n[i]]; return n }); touch() }
  const moveStage = (pk, sk, dir) => { setPhases(ps => ps.map(p => { if (p._k !== pk) return p; const i = p.stages.findIndex(s => s._k === sk); const j = i + dir; if (i < 0 || j < 0 || j >= p.stages.length) return p; const n = [...p.stages];[n[i], n[j]] = [n[j], n[i]]; return { ...p, stages: n } })); touch() }

  const pipeStages = (pid) => (bxPipes.find(p => p.id === Number(pid))?.stages) || []
  const layerOfKey = (key) => catalog.find(c => c.key === key)?.money_layer || ''

  const saveAll = async () => {
    setSaving(true); setErr('')
    try {
      const payload = { phases: phases.map(p => ({ id: p.id || null, name: p.name,
        stages: p.stages.map(s => ({ id: s.id || null, name: s.name,
          stage_key: s.stage_key || null, is_terminal: !!s.is_terminal,
          bitrix_pipeline_id: s.bitrix_pipeline_id ? Number(s.bitrix_pipeline_id) : null,
          bitrix_status_id: s.bitrix_status_id || null })) })),
        card_blocks: blocks.map(b => ({ key: b.key, stage_id: b.stage_id || null })) }
      await api.put('/sales/directories/stage-catalog', payload, auth())
      flash('Каталог сохранён')
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Ошибка сохранения') }
    finally { setSaving(false) }
  }

  const iconBtn = { border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', borderRadius: 6, fontSize: 12, color: 'var(--text-secondary)', padding: '2px 7px', lineHeight: 1.4 }

  return (
    <>
      <Head><title>Стадии · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 60px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="stages" actions={
          <button onClick={saveAll} disabled={!dirty || saving} style={{ ...primaryBtn, opacity: (!dirty || saving) ? 0.5 : 1 }}>
            {saving ? 'Сохранение…' : 'Сохранить все'}
          </button>
        } />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 8 }}>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Каталог стадий</h1>
          {dirty && <span style={{ fontSize: 12, color: 'var(--warning, #d97706)' }}>есть несохранённые изменения</span>}
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 0, marginBottom: 16, maxWidth: 900 }}>
          Наш список стадий по этапам. «2/2/2» — разметка слоя для ДДС (с какой вероятностью учитывать деньги стадии).
          Привязка «воронка → стадия» связывает нашу стадию с Битриксом (одна на стадию — чтобы движение однозначно
          толкалось и в Битрикс). Правки копятся — жмите «Сохранить все».
        </p>

        {err && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)', color: 'var(--danger)', padding: '10px 14px', borderRadius: 10, marginBottom: 12, fontSize: 13 }}>{err}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)', padding: '10px 14px', borderRadius: 10, marginBottom: 12, fontSize: 13 }}>{ok}</div>}
        {loading ? <div style={{ color: 'var(--muted)', padding: 20 }}>Загрузка…</div> : (
          <>
            {phases.map((p, pi) => (
              <div key={p._k} style={{ ...card, padding: '12px 16px', marginBottom: 14 }}>
                {/* Заголовок этапа */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Этап</span>
                  <input value={p.name} onChange={e => setPhase(p._k, { name: e.target.value })} placeholder="название этапа" style={{ ...inp, width: 280, fontWeight: 600 }} />
                  <button onClick={() => movePhase(p._k, -1)} disabled={pi === 0} style={{ ...iconBtn, opacity: pi === 0 ? 0.4 : 1 }} title="Выше">↑</button>
                  <button onClick={() => movePhase(p._k, 1)} disabled={pi === phases.length - 1} style={{ ...iconBtn, opacity: pi === phases.length - 1 ? 0.4 : 1 }} title="Ниже">↓</button>
                  <button onClick={() => addStage(p._k)} style={{ ...iconBtn, color: 'var(--accent)', borderColor: 'var(--accent-tint)' }}>+ стадия</button>
                  <button onClick={() => delPhase(p._k)} title="Удалить этап" style={{ ...iconBtn, marginLeft: 'auto', color: 'var(--danger)', borderColor: 'var(--danger-tint)' }}>✕ этап</button>
                </div>
                {/* Стадии этапа */}
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                    <thead><tr>
                      <th style={{ ...th, width: 54 }}></th>
                      <th style={th}>Стадия</th>
                      <th style={{ ...th, width: 230 }}>Под-этап 2/2/2 (ДДС)</th>
                      <th style={{ ...th, width: 60, textAlign: 'center' }}>Терм.</th>
                      <th style={{ ...th, width: 200 }}>Воронка Битрикса</th>
                      <th style={{ ...th, width: 220 }}>Стадия Битрикса</th>
                      <th style={{ ...th, width: 44 }}></th>
                    </tr></thead>
                    <tbody>
                      {p.stages.map((s, si) => (
                        <tr key={s._k}>
                          <td style={{ ...td, whiteSpace: 'nowrap' }}>
                            <button onClick={() => moveStage(p._k, s._k, -1)} disabled={si === 0} style={{ ...iconBtn, opacity: si === 0 ? 0.4 : 1 }} title="Выше">↑</button>{' '}
                            <button onClick={() => moveStage(p._k, s._k, 1)} disabled={si === p.stages.length - 1} style={{ ...iconBtn, opacity: si === p.stages.length - 1 ? 0.4 : 1 }} title="Ниже">↓</button>
                          </td>
                          <td style={td}><input value={s.name} onChange={e => setStage(p._k, s._k, { name: e.target.value })} placeholder="название стадии" style={{ ...ci, fontWeight: 600 }} /></td>
                          <td style={td}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                              <span title={layerOfKey(s.stage_key) || 'не размечено'} style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: layerColor(layerOfKey(s.stage_key)), flex: '0 0 auto' }} />
                              <select value={s.stage_key} onChange={e => setStage(p._k, s._k, { stage_key: e.target.value })} style={cs} title="Под-этап 2/2/2 — слой ДДС выводится из него">
                                <option value="">— под-этап —</option>
                                {catalog.map(c => <option key={c.key} value={c.key}>{c.label} · {c.money_layer}</option>)}
                                {s.stage_key && !catalog.some(c => c.key === s.stage_key) && <option value={s.stage_key}>{s.stage_key}</option>}
                              </select>
                            </span>
                          </td>
                          <td style={{ ...td, textAlign: 'center' }}><input type="checkbox" checked={s.is_terminal} onChange={e => setStage(p._k, s._k, { is_terminal: e.target.checked })} title="Терминальная (не случилась / сорвалась)" style={{ cursor: 'pointer' }} /></td>
                          <td style={td}>
                            <select value={s.bitrix_pipeline_id} onChange={e => setStage(p._k, s._k, { bitrix_pipeline_id: e.target.value, bitrix_status_id: '' })} style={cs}>
                              <option value="">— воронка —</option>
                              {bxPipes.map(bp => <option key={bp.id} value={bp.id}>{bp.name}</option>)}
                            </select>
                          </td>
                          <td style={td}>
                            <select value={s.bitrix_status_id} onChange={e => setStage(p._k, s._k, { bitrix_status_id: e.target.value })} disabled={!s.bitrix_pipeline_id} style={{ ...cs, opacity: s.bitrix_pipeline_id ? 1 : 0.5 }}>
                              <option value="">{s.bitrix_pipeline_id ? '— стадия —' : 'сначала воронка'}</option>
                              {pipeStages(s.bitrix_pipeline_id).map(bs => <option key={bs.status_id} value={bs.status_id}>{bs.name}</option>)}
                              {s.bitrix_status_id && !pipeStages(s.bitrix_pipeline_id).some(bs => bs.status_id === s.bitrix_status_id) && <option value={s.bitrix_status_id}>{s.bitrix_status_id} (тек.)</option>}
                            </select>
                          </td>
                          <td style={{ ...td, textAlign: 'center' }}><button onClick={() => delStage(p._k, s._k)} title="Удалить стадию" style={{ ...iconBtn, color: 'var(--danger)', borderColor: 'var(--danger-tint)' }}>✕</button></td>
                        </tr>
                      ))}
                      {!p.stages.length && <tr><td colSpan={7} style={{ ...td, textAlign: 'center', color: 'var(--text-faint)' }}>Стадий нет — «+ стадия»</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
            <button onClick={addPhase} style={{ ...primaryBtn, background: 'var(--bg-card)', color: 'var(--accent)', border: '1px solid var(--border-card)', fontWeight: 600 }}>+ этап</button>

            {/* ── Видимость блоков карточки сделки ──
                По СТРОКЕ НА БЛОК, а не сеткой галочек: правило читается как «виден
                начиная с этой стадии», и дальше блок не исчезает. Сетка позволила бы
                наставить галочек, которые ничего не меняют. */}
            <div style={{ ...card, padding: '14px 18px', marginTop: 22, maxWidth: 720 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 4px', color: 'var(--text-primary)' }}>Блоки карточки сделки</h2>
              <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 12px' }}>
                С какой стадии блок появляется в карточке. Появился — дальше не исчезает.
                Блок, внутри которого уже что-то есть, виден всегда, даже раньше своей стадии.
              </p>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  {blocks.map(b => (
                    <tr key={b.key}>
                      <td style={{ ...td, width: 210, fontWeight: 600 }}>{b.label}</td>
                      <td style={td}>
                        <select value={b.stage_id || ''} onChange={e => setBlock(b.key, e.target.value ? Number(e.target.value) : null)} style={cs}>
                          <option value="">виден всегда</option>
                          {phases.flatMap(p => p.stages.filter(s => s.id)
                            .map(s => <option key={s.id} value={s.id}>{p.name} · {s.name}</option>))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  )
}
