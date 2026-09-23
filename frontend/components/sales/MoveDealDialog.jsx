import { useState, useEffect } from 'react'
import api, { auth } from '../../lib/http'
import { overlayClose } from '@/lib/overlay'
import StageRequirements from './StageRequirements'

// Диалог движения сделки по нашему каталогу (E2). Одна кнопка → адаптивный диалог:
// дефолт «следующая стадия», перепрыгнуть или уйти в терминал — из того же списка.
// Комментарий обязателен. Толкание в Битрикс — на бэке.
//
// Воронка отдельной строкой НЕ выбирается: стадии реализационного этапа разворачиваются
// в списке по воронкам («В размещении · Pharm»), то есть выбор один и он же несёт
// привязку. Ещё один шаг от битриксовой модели, где воронка была отдельной сущностью.
//
// Составное значение опции («стадия:воронка») живёт только внутри <select> и сразу
// разбирается на два числа. Наружу уходят строго id — прошлый баг с утечкой составного
// value фильтра в bitrix_stage повторять незачем.
const layerColor = (l) => l === 'фактические' ? 'var(--success)'
  : l === 'реализуемые' ? 'var(--warning)'
  : l === 'планируемые' ? 'var(--muted)' : 'var(--border-card)'

// toStageKey — предвыбрать конкретную позицию 2/2/2 (кнопки дашборда «Подтвердить бронь»
// и «В размещение» ведут в известную стадию). Комментарий всё равно спрашивается: одно
// нажатие не должно превращать движение сделки в запись без причины.
// onCard — диалог открыт С КАРТОЧКИ сделки: только там работают ссылки на её блоки.
export default function MoveDealDialog({ deal, onClose, onMoved, toStageKey, toLost, onCard = false }) {
  const [phases, setPhases] = useState([])
  const [funnels, setFunnels] = useState([])
  const [sel, setSel] = useState('')          // «id» либо «id:воронка» — только для <select>
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Требования ЦЕЛИ. Спрашиваем заранее и показываем списком: отказ, прилетающий после
  // нажатия кнопки, заставляет угадывать, чего не хватило.
  const [req, setReq] = useState(null)
  const [reqBusy, setReqBusy] = useState(false)
  const [override, setOverride] = useState('')

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

  // Разбор составного значения: наружу отдаём только числа.
  const [selStageId, selFunnelId] = (() => {
    const [a, b] = String(sel).split(':')
    return [Number(a) || null, b ? Number(b) || null : null]
  })()
  const targetStage = flat.find(s => s.id === selStageId)

  // Продуктовые воронки — те, что не закреплены за стадиями нереализационных этапов
  // («Песочница», «ДО» закреплены жёстко и продуктом не являются). Правило выводится из
  // каталога, а не из списка имён: переименуют или добавят воронку — ничего не сломается.
  const boundIds = new Set(flat.filter(s => !s.is_realization && s.bitrix_pipeline_id)
    .map(s => s.bitrix_pipeline_id))
  const productFunnels = funnels.filter(f => !boundIds.has(f.id))
  const noFunnels = flat.some(s => s.is_realization) && productFunnels.length === 0
  // Своей проверки МП здесь БОЛЬШЕ НЕТ (13.09.2026). Она собирала признак из четырёх
  // разных полей, потому что диалог открывают из двух мест с разной формой строки, —
  // и всё равно повторяла бэкенд своими словами. Теперь требования приходят готовым
  // списком из `move-preview`: один источник и одна формулировка на экране и в отказе.
  const cur = deal.our_stage

  // Предвыбор «следующей стадии» — после загрузки каталога и воронок. Для реализационной
  // стадии подставляем воронку сделки, если она уже выбрана; иначе выбор остаётся за
  // пользователем (молча угадывать воронку нельзя).
  useEffect(() => {
    if (sel || !phases.length) return
    const nx = deal.our_next_stage
    // toLost — предвыбрать срыв. Именно по признаку is_lost, а не по имени стадии:
    // «Сделка сорвалась» переименуют, а признак останется.
    const st = toLost
      ? flat.find(s => s.is_lost)
      : (toStageKey ? flat.find(s => s.stage_key === toStageKey)
                    : (nx && flat.find(s => s.id === nx.id)))
    if (!st) return
    if (!st.is_realization) setSel(String(st.id))
    else if (deal.realization_pipeline_id && productFunnels.some(f => f.id === deal.realization_pipeline_id))
      setSel(`${st.id}:${deal.realization_pipeline_id}`)
  }, [phases, funnels, toStageKey, toLost])

  useEffect(() => {
    if (!selStageId) { setReq(null); return }
    let dead = false
    setReqBusy(true)
    ;(async () => {
      try {
        // Воронку шлём ТУ, ЧТО ВЫБРАНА СЕЙЧАС: стадия и воронка выбираются одним
        // списком, и до отправки формы у сделки её ещё нет. Без этого требование
        // «воронка выбрана» всегда отвечало бы «не выбрана» и гасило кнопку.
        const params = { to_stage_id: selStageId }
        if (selFunnelId) params.realization_pipeline_id = selFunnelId
        const r = await api.get(`/sales/deals/${deal.id}/move-preview`, { ...auth(), params })
        if (!dead) setReq(r.data)
      } catch (_) {
        // Требования не загрузились — НЕ выдаём это за «требований нет»: пустой список
        // выглядел бы как разрешение. Кнопка остаётся живой, решение примет бэкенд.
        if (!dead) setReq(null)
      } finally { if (!dead) setReqBusy(false) }
    })()
    return () => { dead = true }
  }, [selStageId, selFunnelId, deal.id])

  const blocking = (req?.blocking || [])
  const locked = blocking.length > 0
  const canPass = !locked || (req?.can_override && override.trim())

  const move = async () => {
    if (!comment.trim()) { setErr('Введите комментарий'); return }
    if (locked && !canPass) { setErr('Не выполнены требования перехода — список выше'); return }
    setBusy(true); setErr('')
    try {
      const body = { to_stage_id: selStageId, comment: comment.trim() }
      if (selFunnelId) body.realization_pipeline_id = selFunnelId
      if (locked && override.trim()) body.override_reason = override.trim()
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
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(15,23,42,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, width: 'min(460px, 96vw)', padding: '22px 24px', boxShadow: '0 24px 64px rgba(28,36,51,.22)' }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Двинуть сделку</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 16 }}>Сейчас: {chip(cur)}</div>

        <div style={{ marginBottom: 14 }}>
          <div style={lbl}>Куда</div>
          <select value={sel} onChange={e => setSel(e.target.value)} style={inp}>
            <option value="">— выберите стадию —</option>
            {phases.map(ph => (
              <optgroup key={ph.id} label={ph.name}>
                {ph.stages.flatMap(s => {
                  const mark = `${cur && s.id === cur.id ? ' (текущая)' : ''}${s.is_terminal ? ' ⛔' : ''}`
                    + `${deal.our_next_stage && s.id === deal.our_next_stage.id ? ' → следующая' : ''}`
                  // Реализационная стадия существует в каждой продуктовой воронке —
                  // разворачиваем её по воронкам, чтобы выбор остался одним действием.
                  if (!ph.is_realization || s.is_terminal) {
                    return [<option key={s.id} value={s.id}>{s.name}{mark}</option>]
                  }
                  return productFunnels.map(f => (
                    <option key={`${s.id}:${f.id}`} value={`${s.id}:${f.id}`}>
                      {s.name} · {f.name}
                      {deal.realization_pipeline_id === f.id ? ' (воронка сделки)' : ''}{mark}
                    </option>
                  ))
                })}
              </optgroup>
            ))}
          </select>
          {noFunnels && (
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>
              Нет отслеживаемых воронок — стадии реализации выбрать не из чего.
              Отметьте воронки в справочнике.
            </div>
          )}
        </div>

        {/* Требования ЦЕЛИ, списком и заранее. Плашка «✓ все данные внесены» здесь
            стояла до 13.09.2026 и проверяла ровно одно — привязку МП; теперь список
            приходит с бэкенда, тот же, что применится при попытке. */}
        {!!selStageId && (
          <div style={{
            marginBottom: 14, borderRadius: 10, padding: '11px 12px',
            background: locked ? 'var(--danger-tint)' : 'var(--bg-subtle)',
            border: `1px solid ${locked ? 'var(--danger-border)' : 'var(--border-card)'}`,
          }}>
            {reqBusy && <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Проверяю требования…</div>}
            {!reqBusy && req && (
              <StageRequirements
                onCard={onCard}
                lines={req.lines}
                title={locked ? `Не выполнено для перехода в «${targetStage?.name || '—'}»`
                              : `Требования перехода в «${targetStage?.name || '—'}»`}
                empty="Для этого перехода требований нет" />
            )}
            {!reqBusy && !req && (
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                Требования не загрузились — проверит бэкенд при попытке
              </div>
            )}
          </div>
        )}

        {/* Переход ФИКСИРУЕТ медиаплан (Бронь → Сборка) — говорим до нажатия, а не после:
            узнать об этом на отказе при сохранении плана значит потерять правку. Текст и
            условие приходят с сервера (`plan_lock_notice`), своей проверки стадий здесь
            нет — решение владельца 23.09.2026, backend/app/sales/plan_lock.py. */}
        {!reqBusy && req?.plan_lock_notice && (
          <div role="note" style={{
            marginBottom: 14, borderRadius: 10, padding: '11px 12px', display: 'flex', gap: 10,
            background: 'var(--warning-tint)', border: '1px solid var(--warning-border)',
            color: 'var(--text-primary)', fontSize: 13, lineHeight: 1.45,
          }}>
            <span aria-hidden style={{ color: 'var(--warning-fg)', fontWeight: 700 }}>!</span>
            <span>{req.plan_lock_notice}</span>
          </div>
        )}

        {/* Обход — только мастеру и только с причиной. Она уйдёт в историю движения
            отдельной пометкой: «в обход требований» должно быть видно потом. */}
        {locked && req?.can_override && (
          <div style={{ marginBottom: 14 }}>
            <div style={lbl}>Причина обхода требований*</div>
            <input value={override} onChange={e => setOverride(e.target.value)}
              placeholder="почему двигаем, не выполнив" style={inp} />
          </div>
        )}
        {locked && !req?.can_override && (
          <div style={{ marginBottom: 14, fontSize: 12.5, color: 'var(--text-muted)' }}>
            Провести сделку мимо требований может только мастер.
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <div style={lbl}>Комментарий*</div>
          <textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} placeholder="что сделано / почему двигаем" style={{ ...inp, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>

        {err && <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>{err}</div>}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '9px 18px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Отмена</button>
          {(() => {
            const off = busy || !selStageId || !canPass
            return (
              <button onClick={move} disabled={off} style={{ padding: '9px 20px', borderRadius: 10, border: 'none', background: locked ? 'var(--danger)' : 'var(--accent)', color: 'var(--on-accent)', cursor: off ? 'default' : 'pointer', fontSize: 14, fontWeight: 700, opacity: off ? 0.5 : 1 }}>
                {busy ? 'Двигаю…' : (locked ? 'Двинуть в обход' : 'Двинуть')}
              </button>
            )
          })()}
        </div>
      </div>
    </div>
  )
}
