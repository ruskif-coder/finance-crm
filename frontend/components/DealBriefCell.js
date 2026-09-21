import { useState, useEffect, useRef } from 'react'
import api, { auth } from '../lib/api'
import { overlayClose } from '@/lib/overlay'
import { fmtDateTime } from '@/lib/dates'
import BriefFiles from '@/components/deal/BriefFiles'

// Иконка «бриф» в строке сделки + всплывающее окно с текстом и инлайн-правкой.
// Ленивая загрузка: текст тянется только при первом открытии (GET), дальше — из кэша БД.
// Сохранение двустороннее: наша БД + поле ufCrm_1761318500 в Битриксе (на бэке).
// controlledOpen/onClose — управление снаружи (кнопка «Бриф» на канбан-доске):
// иконку-триггер в этом режиме не рисуем, показываем только сам попап.
export default function DealBriefCell({ deal, canEdit, v2, controlledOpen, onClose }) {
  const controlled = controlledOpen !== undefined
  const [openState, setOpenState] = useState(false)
  const open = controlled ? controlledOpen : openState
  const setOpen = (v) => { if (controlled) { if (!v && onClose) onClose() } else setOpenState(v) }
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [text, setText] = useState('')
  const [orig, setOrig] = useState('')
  const [meta, setMeta] = useState({ loaded: false, is_local: false, synced_at: null })
  const loadedOnce = useRef(false)

  const load = async (refresh = false) => {
    setLoading(true); setErr(''); setOk('')
    try {
      const r = await api.get(`/sales/deals/${deal.id}/brief${refresh ? '?refresh=1' : ''}`, auth())
      setText(r.data.brief || ''); setOrig(r.data.brief || '')
      setMeta({ loaded: r.data.loaded, is_local: r.data.is_local, synced_at: r.data.synced_at })
      loadedOnce.current = true
      if (refresh) setOk('Обновлено из Битрикса')
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось загрузить бриф')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (open && !loadedOnce.current) load(false)
    // при закрытии сбрасываем сообщения, но кэш текста держим
    if (!open) { setErr(''); setOk('') }
  }, [open])

  const save = async () => {
    setSaving(true); setErr(''); setOk('')
    try {
      const r = await api.put(`/sales/deals/${deal.id}/brief`, { brief: text }, auth())
      setOrig(text)
      setMeta(m => ({ ...m, loaded: true, synced_at: r.data.synced_at }))
      setOk(r.data.pushed_to_bitrix ? 'Сохранено и отправлено в Битрикс' : 'Сохранено')
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось сохранить')
    } finally { setSaving(false) }
  }

  const state = deal.brief_state || 'none'
  const hasBrief = state === 'filled'
  const iconColor = hasBrief ? 'var(--accent, #2563eb)' : 'var(--muted, #94a3b8)'
  const dirty = text !== orig

  return (
    <>
      {controlled ? null : v2 ? (
        <span title={hasBrief ? 'Бриф подгружен' : 'Базовый бриф'}
          onClick={(e) => { e.stopPropagation(); setOpen(true) }}
          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, cursor: 'pointer',
            background: hasBrief ? 'var(--accent-tint)' : 'transparent', color: hasBrief ? 'var(--accent)' : 'var(--text-faint)' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M9.5 2.5h5v3h-5z" /><path d="M9 12h6" /><path d="M9 16h4" />
          </svg>
        </span>
      ) : (
      <button
        title={hasBrief ? 'Бриф (заполнен)' : 'Бриф'}
        onClick={(e) => { e.stopPropagation(); setOpen(true) }}
        style={{
          border: 'none', background: 'none', cursor: 'pointer', padding: 0,
          fontSize: 15, lineHeight: 1, color: iconColor, opacity: hasBrief ? 1 : 0.6,
        }}>📋</button>
      )}

      {open && (
        <div {...overlayClose(() => setOpen(false))}
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(15,23,42,0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              borderRadius: 12, width: 'min(680px, 96vw)', maxHeight: '88vh', display: 'flex',
              flexDirection: 'column', boxShadow: 'var(--shadow-card, 0 10px 40px rgba(0,0,0,0.25))' }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px',
              borderBottom: '1px solid var(--border-card)' }}>
              <span style={{ fontSize: 15 }}>📋</span>
              <div style={{ fontWeight: 600, fontSize: 15, flex: 1, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Бриф · {deal.title || `сделка ${deal.code || deal.id}`}
              </div>
              <button onClick={() => setOpen(false)} title="Закрыть"
                style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 18,
                  color: 'var(--muted)', lineHeight: 1 }}>✕</button>
            </div>

            <div style={{ padding: 18, overflowY: 'auto' }}>
              {loading ? (
                <div style={{ color: 'var(--muted)', fontSize: 13, padding: '20px 0' }}>Загрузка…</div>
              ) : (
                <>
                  {meta.is_local && (
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                      Локальная сделка — бриф хранится только у нас, в Битрикс не отправляется.
                    </div>
                  )}
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    readOnly={!canEdit}
                    placeholder={canEdit ? 'Бриф пустой — можно заполнить…' : 'Бриф пустой'}
                    style={{ width: '100%', minHeight: 260, resize: 'vertical', boxSizing: 'border-box',
                      padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-card)',
                      background: canEdit ? 'var(--bg-card)' : 'var(--bg-subtle)', color: 'inherit',
                      fontSize: 13.5, lineHeight: 1.5, fontFamily: 'inherit', whiteSpace: 'pre-wrap' }} />
                  {/* Файлы брифа. Тот же компонент, что в конструкторе МП, только
                      другая дверь: здесь право продаж, там — медиапланов. */}
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase',
                      color: 'var(--text-faint)', marginBottom: 6 }}>Файлы брифа</div>
                    <BriefFiles base={`/sales/deals/${deal.id}/brief/files`} readOnly={!canEdit} />
                  </div>
                </>
              )}
              {err && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 10 }}>{err}</div>}
              {ok && <div style={{ color: 'var(--accent)', fontSize: 13, marginTop: 10 }}>{ok}</div>}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 18px',
              borderTop: '1px solid var(--border-card)' }}>
              <button onClick={() => load(true)} disabled={loading || saving}
                title="Перечитать бриф из Битрикса"
                style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border-card)',
                  background: 'var(--bg-subtle)', cursor: 'pointer', fontSize: 12.5 }}>
                ⟳ Обновить из Битрикса
              </button>
              <span style={{ flex: 1, fontSize: 11.5, color: 'var(--muted)' }}>
                {meta.synced_at ? `синхронизировано: ${fmtDateTime(meta.synced_at)}` : ''}
              </span>
              {canEdit && (
                <button onClick={save} disabled={saving || loading || !dirty}
                  style={{ padding: '7px 16px', borderRadius: 8, border: 'none', cursor: dirty ? 'pointer' : 'default',
                    background: dirty ? 'var(--accent)' : 'var(--bg-subtle)',
                    color: dirty ? '#fff' : 'var(--muted)', fontSize: 13, fontWeight: 600 }}>
                  {saving ? 'Сохранение…' : 'Сохранить'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
