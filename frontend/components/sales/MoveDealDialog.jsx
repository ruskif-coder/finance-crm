import { useState, useEffect } from 'react'
import api, { auth } from '../../lib/http'

// Диалог движения сделки по нашему каталогу (E2). Одна кнопка → адаптивный диалог:
// дефолт «следующая стадия», доп-выбор всплывает по необходимости (перепрыгнуть /
// воронка реализации / терминал). Комментарий обязателен. Толкание в Битрикс — на бэке.
const layerColor = (l) => l === 'фактические' ? 'var(--success)'
  : l === 'реализуемые' ? 'var(--warning, #d97706)'
  : l === 'планируемые' ? 'var(--muted)' : 'var(--border-card)'

export default function MoveDealDialog({ deal, onClose, onMoved }) {
  const [phases, setPhases] = useState([])
  const [funnels, setFunnels] = useState([])
  const [target, setTarget] = useState(deal.our_next_stage?.id || '')
  const [comment, setComment] = useState('')
  const [funnel, setFunnel] = useState(deal.realization_pipeline_id || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    (async () => {
      try {
        const [c, p] = await Promise.all([
          api.get('/sales/directories/stage-catalog', auth()),
          api.get('/sales/directories/pipelines', auth()),
        ])
        setPhases(c.data.phases || [])
        setFunnels((p.data.items || []).filter(x => x.is_tracked))
      } catch (e) { setErr('Не удалось загрузить каталог стадий') }
    })()
  }, [])

  const flat = phases.flatMap(ph => ph.stages.map(s => ({ ...s, phaseName: ph.name, is_realization: ph.is_realization })))
  const targetStage = flat.find(s => s.id === Number(target))
  const showFunnel = !!targetStage?.is_realization
  const needFunnel = showFunnel && !deal.realization_pipeline_id && !funnel
  const hasMp = (deal.our_mps || []).length > 0
  const needMp = !!targetStage?.requires_media_plan && !targetStage?.is_terminal && !hasMp
  const cur = deal.our_stage

  const move = async () => {
    if (!comment.trim()) { setErr('Введите комментарий'); return }
    if (needMp) { setErr('Нужен привязанный медиаплан — привяжите МП к сделке в конструкторе'); return }
    if (needFunnel) { setErr('Выберите воронку реализации'); return }
    setBusy(true); setErr('')
    try {
      const body = { to_stage_id: target ? Number(target) : null, comment: comment.trim() }
      if (showFunnel && funnel) body.realization_pipeline_id = Number(funnel)
      const r = await api.post(`/sales/deals/${deal.id}/move`, body, auth())
      onMoved({ our_stage: r.data.our_stage, our_next_stage: r.data.our_next_stage, realization_pipeline_id: r.data.realization_pipeline_id })
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось двинуть сделку'); setBusy(false) }
  }

  const chip = (st) => st ? (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: layerColor(st.money_layer) }} />
      {st.name}<span style={{ color: 'var(--text-faint)', fontWeight: 500 }}>· {st.phase || st.phaseName}</span>
    </span>
  ) : <span style={{ color: 'var(--text-faint)', fontSize: 13 }}>стадия не задана</span>

  const lbl = { fontSize: 12, color: 'var(--text-muted)', marginBottom: 5 }
  const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 11px', fontSize: 14, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(15,23,42,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, width: 'min(460px, 96vw)', padding: '22px 24px', boxShadow: '0 24px 64px rgba(28,36,51,.22)' }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Двинуть сделку</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 16 }}>Сейчас: {chip(cur)}</div>

        <div style={{ marginBottom: 14 }}>
          <div style={lbl}>Куда</div>
          <select value={target} onChange={e => setTarget(e.target.value)} style={inp}>
            <option value="">— выберите стадию —</option>
            {phases.map(ph => (
              <optgroup key={ph.id} label={ph.name}>
                {ph.stages.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name}{cur && s.id === cur.id ? ' (текущая)' : ''}{s.is_terminal ? ' ⛔' : ''}
                    {deal.our_next_stage && s.id === deal.our_next_stage.id ? ' → следующая' : ''}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        {showFunnel && (
          <div style={{ marginBottom: 14 }}>
            <div style={lbl}>Воронка реализации (под продукт){deal.realization_pipeline_id ? ' — можно сменить' : ''}</div>
            <select value={funnel} onChange={e => setFunnel(e.target.value)} style={{ ...inp, borderColor: needFunnel ? 'var(--danger)' : 'var(--border-card)' }}>
              <option value="">— выберите воронку —</option>
              {funnels.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
        )}

        {/* Чек-лист полноты данных — v1: проверка привязки МП + простое подтверждение */}
        <div style={{ marginBottom: 14, background: needMp ? 'var(--danger-tint)' : 'var(--bg-subtle)', borderRadius: 10, padding: '10px 12px', fontSize: 13, color: needMp ? 'var(--danger)' : 'var(--text-secondary)' }}>
          {needMp
            ? <>☐ Медиаплан не привязан — привяжите МП к сделке в конструкторе (обязательно с этой стадии)</>
            : <>✓ Все данные внесены{targetStage?.requires_media_plan ? ' · медиаплан привязан' : ''} — поехали дальше</>}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={lbl}>Комментарий*</div>
          <textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} placeholder="что сделано / почему двигаем" style={{ ...inp, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>

        {err && <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>{err}</div>}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '9px 18px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Отмена</button>
          <button onClick={move} disabled={busy || !target || needMp} style={{ padding: '9px 20px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', cursor: (busy || !target || needMp) ? 'default' : 'pointer', fontSize: 14, fontWeight: 700, opacity: (busy || !target || needMp) ? 0.5 : 1 }}>{busy ? 'Двигаю…' : 'Двинуть'}</button>
        </div>
      </div>
    </div>
  )
}
