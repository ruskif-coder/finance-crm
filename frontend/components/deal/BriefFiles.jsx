import { useState, useEffect, useRef, useCallback } from 'react'
import api, { auth } from '@/lib/http'
import { downloadFile } from '@/lib/download'

/* Файлы брифа сделки: один компонент на все экраны, где бриф виден.
 *
 * Бриф приходит от клиента не только текстом — презентацией, тз, чужим медиапланом, — и
 * до сих пор исходник оставался в почте у того, кто его получил.
 *
 * `base` — адрес ручки файлов, и он РАЗНЫЙ у разных экранов: реестр сделок работает
 * правом продаж (`/sales/deals/<id>/brief/files`), конструктор МП — правом медиапланов
 * (`/sales/media-plans/<id>/deal-brief/files`). Хранение при этом общее, разные только
 * двери. Поэтому компонент принимает адрес, а не собирает его сам: собирал бы — знал бы
 * про оба экрана и ломался бы на третьем.
 *
 * `readOnly` — нет права правки: файлы видно и скачать можно, прикрепить нельзя.
 * `disabled` — прикреплять некуда (МП ещё не привязан к сделке); тогда вместо списка
 * стоит объяснение, а не молчащая кнопка.
 */
export default function BriefFiles({ base, readOnly = false, disabled = false,
                                     disabledHint = 'Файл прикрепится после привязки сделки',
                                     compact = false }) {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const inputRef = useRef(null)

  const load = useCallback(async () => {
    if (!base || disabled) { setItems([]); return }
    try {
      const r = await api.get(base, auth())
      setItems(r.data.items || [])
    } catch (e) { /* список не критичен: панель брифа обязана открыться и без него */ }
  }, [base, disabled])

  useEffect(() => { load() }, [load])

  const pick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''            // тот же файл повторно иначе не выбрать
    if (!file) return
    setBusy(true); setErr('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      await api.post(base, fd, auth())
      await load()
    } catch (e2) {
      setErr(e2.response?.data?.detail || 'Не удалось прикрепить файл')
    } finally { setBusy(false) }
  }

  const remove = async (f) => {
    if (!window.confirm(`Снять файл «${f.name}»?`)) return
    setErr('')
    try { await api.delete(`${base}/${f.id}`, auth()); await load() }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось снять файл') }
  }

  // Имя задаёт сервер (Content-Disposition), своё не подставляем — общее правило
  // lib/download: подстановка заглушки поверх правильного имени уже уносила документ
  // на диск без расширения.
  const get = (f) => downloadFile(`${base}/${f.id}`, f.name, setErr)

  const kb = (n) => (n == null ? '' : n < 1024 * 1024
    ? `${Math.max(1, Math.round(n / 1024))} КБ`
    : `${(n / 1024 / 1024).toFixed(1)} МБ`)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {items.map(f => (
          <span key={f.id} title={`${f.name}${f.uploaded_by ? ` · ${f.uploaded_by}` : ''}`}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, maxWidth: 260,
              padding: '4px 9px', borderRadius: 9, fontSize: 12,
              background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
            }}>
            <span onClick={() => get(f)}
              style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              ⤓ {f.name}
            </span>
            <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{kb(f.size)}</span>
            {!readOnly && !disabled && (
              <span onClick={() => remove(f)} title="Снять файл"
                style={{ cursor: 'pointer', color: 'var(--danger)', fontWeight: 700 }}>×</span>
            )}
          </span>
        ))}

        {!readOnly && (
          <>
            <input ref={inputRef} type="file" onChange={pick} style={{ display: 'none' }} />
            <button type="button" disabled={disabled || busy}
              onClick={() => inputRef.current?.click()}
              title={disabled ? disabledHint : 'Презентация, тз, чужой медиаплан — до 20 МБ'}
              style={{
                padding: compact ? '3px 9px' : '6px 11px', borderRadius: 9,
                border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                color: disabled ? 'var(--text-faint)' : 'var(--accent)',
                fontSize: 12, fontWeight: 700,
                cursor: (disabled || busy) ? 'default' : 'pointer',
                opacity: (disabled || busy) ? 0.5 : 1, whiteSpace: 'nowrap',
              }}>
              {busy ? 'Загрузка…' : '📎 Прикрепить файл'}
            </button>
          </>
        )}

        {!items.length && readOnly && (
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>файлов нет</span>
        )}
      </div>

      {disabled && !readOnly && (
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{disabledHint}</span>
      )}
      {!!err && <span style={{ fontSize: 11.5, color: 'var(--danger)' }}>{err}</span>}
    </div>
  )
}
