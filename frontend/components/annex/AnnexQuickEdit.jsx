/**
 * Быстрая правка текста на экране сборки ДС (14.10.2026): блок зоны аккаунта (до таблицы МП) и «основание для закрывающих документов».
 * Как в конструкторе шаблонов: текст с подстановками в фигурных скобках, кнопки подстановок, предпросмотр на значениях этого документа.
 * Текст хранится С подстановками — значения остаются живыми и пересчитываются при смене сделки, периода, номера.
 */
import { useEffect, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { annexTemplatesApi } from '@/lib/annexTemplatesApi'

const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }

/** Значения подставляются на клиенте только для предпросмотра; настоящий текст собирает сервер. */
function resolveLocal(text, values) {
  return String(text || '').split(/(\{[^{}]+\})/g).filter(Boolean).map(p => {
    const m = /^\{([^{}]+)\}$/.exec(p)
    if (!m) return { t: p }
    const v = values[m[1]]
    return v === undefined ? { t: p, bad: true } : { t: v === '' ? `нет: ${m[1].replace(/_/g, ' ')}` : v, sub: true, empty: v === '' }
  })
}

function Preview({ text, values }) {
  return (
    <div style={{ padding: '10px 12px', background: 'var(--bg-subtle)', borderRadius: 10, fontFamily: "'Times New Roman', Georgia, serif", fontSize: 14, lineHeight: 1.55 }}>
      {resolveLocal(text, values).map((g, i) => (
        g.sub || g.bad
          ? <span key={i} style={{ color: g.bad || g.empty ? 'var(--danger-fg)' : 'var(--income-fg)', background: g.bad || g.empty ? 'var(--danger-tint)' : 'var(--income-tint)', borderRadius: 3, padding: '0 2px' }}>{g.t}</span>
          : <span key={i}>{g.t}</span>
      ))}
    </div>
  )
}

export default function AnnexQuickEdit({ title, hint, source, defaultText, edited, inheritedFrom, values, canEdit, copy, onSave, aside }) {
  const [text, setText] = useState(source || '')
  const [subs, setSubs] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => { setText(source || '') }, [source])
  useEffect(() => {
    let alive = true
    annexTemplatesApi.subs().then(items => { if (alive) setSubs(items) }).catch(() => { if (alive) setSubs([]) })
    return () => { alive = false }
  }, [])

  const keys = (subs && subs.length ? subs.map(s => s.key) : Object.keys(values || {})).filter(k => values && k in values)
  const dirty = text !== (source || '')

  const save = async (value) => {
    setBusy(true); setErr('')
    try { await onSave(value) } catch (e) { setErr((e && e.response && e.response.data && e.response.data.detail) || 'Не удалось сохранить') }
    finally { setBusy(false) }
  }
  const copyText = () => {
    const resolved = resolveLocal(text, values || {}).map(g => g.t).join('')
    try { navigator.clipboard.writeText(resolved); setDone(true); setTimeout(() => setDone(false), 1500) } catch (_) { /* буфер недоступен */ }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={CAP}>{title}</span>
        {edited && <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--accent-fg)', background: 'var(--accent-tint)', borderRadius: 6, padding: '2px 8px' }}>изменено аккаунтом</span>}
        {!edited && !!inheritedFrom && <span title="По умолчанию берётся текст прошлого ДС этого договора" style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--violet-fg)', background: 'var(--violet-tint)', borderRadius: 6, padding: '2px 8px' }}>взято из прошлого ДС · {inheritedFrom}</span>}
        {hint && <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{hint}</span>}
        {aside}
      </div>
      <textarea value={text} rows={3} disabled={!canEdit} onChange={e => setText(e.target.value)}
                style={{ boxSizing: 'border-box', width: '100%', padding: '10px 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, lineHeight: 1.5, resize: 'vertical', outline: 'none', color: 'var(--text-primary)', fontFamily: 'inherit' }} />
      {canEdit && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {keys.map(k => (
            <span key={k} onClick={() => setText(t => `${t.replace(/\s*$/, '')} {${k}}`)} title={`вставить {${k}} · сейчас: ${values[k] || '—'}`}
                  style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 8px', borderRadius: 7, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)', fontFamily: MONO, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
              {`{${k}}`}
            </span>
          ))}
        </div>
      )}
      <Preview text={text} values={values || {}} />
      {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {canEdit && <button type="button" disabled={!dirty || busy} onClick={() => save(text)}
                            style={{ height: 32, padding: '0 14px', borderRadius: 10, border: 'none', background: dirty ? 'var(--accent)' : 'var(--accent-soft)', color: 'var(--on-accent)', fontSize: 12.5, fontWeight: 700, cursor: dirty && !busy ? 'pointer' : 'not-allowed' }}>
          {busy ? 'Сохраняю…' : 'Сохранить'}
        </button>}
        {canEdit && (edited || !!inheritedFrom || dirty) && <button type="button" disabled={busy} onClick={() => { if (defaultText) setText(defaultText); save(null) }}
                                                 style={{ height: 32, padding: '0 12px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>
          Вернуть по шаблону
        </button>}
        {copy && <button type="button" onClick={copyText}
                         style={{ marginLeft: 'auto', height: 32, padding: '0 12px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>
          {done ? 'Скопировано' : 'Копировать текст'}
        </button>}
      </div>
    </div>
  )
}
