// Отчёт клиенту по РК за выбранные дни (владелец 17.11.2026): «XLS» рядом скачивает отчёт целиком, а эта кнопка-календарик
// открывает окно «с … по …» и скачивает только эти дни. Сервер (`/client-report/deal/{id}.xlsx`) сам клипует период к
// флайту и не отдаёт пустой отчёт — его отказ («за выбранный период данных нет») показывается здесь же, а не алертом.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover, UI, Z } from '@/components/salesTableKit'
import { downloadBlob } from '@/lib/dealDocs'
import { todayMsk } from '@/lib/dates'

const CalendarIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true"><path d="M2.5 4h11v9.5h-11zM2.5 7h11M5.5 2.5v3M10.5 2.5v3" /></svg>
)
const field = { height: 32, boxSizing: 'border-box', padding: '0 8px', border: '1px solid var(--border-card)', borderRadius: 8,
  background: 'var(--bg-card)', color: 'var(--text-primary)', fontFamily: MONO, fontSize: 12, outline: 'none', width: '100%' }
const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }

/** Адрес выгрузки: пустые даты и «вся РК» в запрос не идут — сервер тогда берёт весь флайт. */
export const reportUrl = (dealId, { from, to, group } = {}) => {
  const q = new URLSearchParams()
  if (from) q.set('date_from', from)
  if (to) q.set('date_to', to)
  if (group) q.set('group', group)
  const s = q.toString()
  return `/client-report/deal/${dealId}.xlsx${s ? `?${s}` : ''}`
}

/**
 * props: dealId; startDate — начало РК по медиаплану (`report_from` сделки): им окно открывается в «с», «по» — сегодня
 * (владелец 17.11.2026); groups — группы креативов сделки (тогда в окне выбор «вся РК / группа»); disabled; style — вид
 * кнопки под соседнюю «XLS»; title.
 */
export default function ReportDates({ dealId, startDate, groups = [], disabled, style, title = 'Отчёт за выбранные дни' }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [group, setGroup] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [open])

  const bad = !!from && !!to && from > to
  const download = async () => {
    if (bad || (!from && !to)) return
    setBusy(true); setErr('')
    const ok = await downloadBlob(reportUrl(dealId, { from, to, group }), '', (m) => setErr(m || 'Не удалось собрать отчёт'))
    setBusy(false)
    if (ok) setOpen(false)
  }

  return (
    <span data-pop-root style={{ position: 'relative', display: 'inline-flex' }}>
      <button type="button" disabled={disabled} title={title} aria-label={title} onClick={() => {
          setErr('')
          if (!open && !from && !to) { setFrom(startDate ? String(startDate).slice(0, 10) : ''); setTo(todayMsk()) }
          setOpen(o => !o)
        }}
        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1, fontFamily: UI, ...style,
          ...(open ? { borderColor: 'var(--accent-border)', color: 'var(--accent-fg)', background: 'var(--accent-tint)' } : {}) }}>
        <CalendarIcon />
      </button>
      <PortalPopover open={open} minWidth={268} align="right" style={{ padding: 12, zIndex: Z.dropdown, fontFamily: UI }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>Отчёт по РК за дни</span>
          <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={cap}>с</span>
              <input type="date" value={from} max={to || undefined} onChange={e => setFrom(e.target.value)} style={field} /></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={cap}>по</span>
              <input type="date" value={to} min={from || undefined} onChange={e => setTo(e.target.value)} style={field} /></label>
          </span>
          {!!groups.length && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={cap}>креативы</span>
              <select value={group} onChange={e => setGroup(e.target.value)} style={{ ...field, fontFamily: UI }}>
                <option value="">Вся РК</option>
                {groups.map(g => <option key={g} value={g}>Группа «{g}»</option>)}
              </select></label>
          )}
          <span style={{ fontSize: 11, lineHeight: 1.4, color: bad || err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
            {bad ? 'Начало позже конца' : err || 'Одна дата — от неё до конца или от начала до неё. Дни вне флайта отрежутся.'}
          </span>
          <button type="button" onClick={download} disabled={busy || bad || (!from && !to)}
            style={{ height: 32, border: 'none', borderRadius: 9, fontFamily: UI, fontSize: 12.5, fontWeight: 700,
              cursor: busy || bad || (!from && !to) ? 'not-allowed' : 'pointer',
              background: busy || bad || (!from && !to) ? 'var(--bg-subtle)' : 'var(--accent)',
              color: busy || bad || (!from && !to) ? 'var(--text-faint)' : 'var(--on-accent)' }}>
            {busy ? 'Собираю…' : 'Скачать XLS'}
          </button>
        </span>
      </PortalPopover>
    </span>
  )
}
