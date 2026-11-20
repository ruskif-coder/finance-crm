// Проблемные операции (владелец 20.11.2026): значок ⚠ в строке реестра и блок над боковой панелью операции — что не так и
// «Закрыть» с комментарием. Проблемы открывает сервер (`app/operation_issues`): комплект удалён при оплаченной операции,
// документы на переделке, новые цифры 1С у оплаченной. «На переделке» закрывается сама повторным внесением.
import { useState } from 'react'
import { MONO, btn, inp } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'
import { fmtDateTime } from '@/lib/dates'

const msk = (iso) => fmtDateTime(iso, '')        // общий формат «дд.мм.гггг чч:мм» по Москве — lib/dates

/** Значок в строке реестра: число открытых проблем, тексты — подсказкой. */
export function IssueMark({ issues }) {
  if (!issues?.length) return null
  const tip = issues.map(i => `${i.kind}: ${i.text || ''}`).join('\n\n')
  return (
    <span title={tip} aria-label={`Проблемы операции: ${issues.length}`}
      style={{ marginLeft: 6, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 3, padding: '1px 6px', borderRadius: 6, cursor: 'help',
        background: 'var(--attn-tint, var(--warning-tint))', color: 'var(--attn-fg, var(--warning-fg))', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>
      ⚠{issues.length > 1 ? ` ${issues.length}` : ''}
    </span>
  )
}

function OpenIssue({ issue, canEdit, onResolved }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const save = () => {
    if (!note.trim()) { setErr('Напишите, что сделали'); return }
    setBusy(true); setErr('')
    api.post(`/operations/issues/${issue.id}/resolve`, { resolution: note.trim() }, auth())
      .then(() => { setOpen(false); setNote(''); onResolved() })
      .catch(e => setErr(detailText(e, 'Не удалось закрыть')))
      .finally(() => setBusy(false))
  }
  return (
    <div style={{ padding: '10px 0', borderTop: '1px solid var(--border-inner)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontWeight: 700, color: 'var(--attn-fg, var(--warning-fg))' }}>⚠ {issue.kind}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{msk(issue.at)}</span>
        {canEdit && !open && issue.kind !== 'на переделке' && (
          <button type="button" onClick={() => setOpen(true)} style={{ ...btn(false), marginLeft: 'auto', padding: '4px 12px', fontSize: 12 }}>
            Закрыть
          </button>
        )}
      </div>
      <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{issue.text}</div>
      {issue.kind === 'на переделке' && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>Закроется сама, когда бухгалтер внесёт документы заново.</div>}
      {open && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} autoFocus placeholder="Что сделали: поправил сумму, связал с новым пакетом…"
            style={{ ...inp, width: '100%', resize: 'vertical' }} />
          {!!err && <span style={{ color: 'var(--danger-fg)', fontSize: 12 }}>{err}</span>}
          <span style={{ display: 'flex', gap: 8 }}>
            <button type="button" disabled={busy} onClick={save} style={{ ...btn(true), padding: '5px 12px', fontSize: 12, cursor: busy ? 'wait' : 'pointer' }}>
              {busy ? 'Закрываю…' : 'Закрыть проблему'}
            </button>
            <button type="button" onClick={() => { setOpen(false); setErr('') }} style={{ ...btn(false), padding: '5px 12px', fontSize: 12 }}>Отмена</button>
          </span>
        </div>
      )}
    </div>
  )
}

/** Блок над панелью операции: открытые проблемы с «Закрыть», закрытые — одной строкой «кто и как». */
export default function OperationIssues({ issues, canEdit, onResolved }) {
  if (!issues?.length) return null
  const open = issues.filter(i => i.open), done = issues.filter(i => !i.open)
  return (
    <div style={{ width: 560, boxSizing: 'border-box', padding: '12px 26px', background: open.length ? 'var(--attn-tint, var(--warning-tint))' : 'var(--bg-card)',
      borderBottom: '1px solid var(--border-card)' }}>
      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
        {open.length ? `Проблемы операции · ${open.length}` : 'Проблемы операции · все закрыты'}
      </div>
      {open.map(i => <OpenIssue key={i.id} issue={i} canEdit={canEdit} onResolved={onResolved} />)}
      {done.map(i => (
        <div key={i.id} style={{ padding: '6px 0', borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
          ✓ {i.kind} — {i.resolution}{i.resolved_by ? ` · ${i.resolved_by}` : ''}{i.resolved_at ? `, ${msk(i.resolved_at)}` : ''}
        </div>
      ))}
    </div>
  )
}
