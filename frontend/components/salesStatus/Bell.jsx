// «Статусы продаж» — будильник на строку рекламодателя или бренда (владелец 23.10.2026): ставишь себе дату — в 09:00 МСК
// этого дня напоминание приходит в Telegram и на почту. Свой — залитый значок с датой; чужие видны в подсказке.
import { useEffect, useState } from 'react'
import { PortalPopover, MONO, inp, primaryBtn } from '@/components/salesTableKit'
import { todayMsk } from '@/lib/dates'
import { dm } from '@/lib/salesStatus'

function BellIcon({ on }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden style={{ flex: '0 0 13px' }}>
      <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" fill={on ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M10 20a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

/** list — будильники этой строки (свой и чужие); onSave({remind_on, note}) / onRemove(id) — ручки страницы. */
export default function Bell({ list, onSave, onRemove }) {
  const mine = list.find(r => r.mine)
  const others = list.filter(r => !r.mine)
  const [open, setOpen] = useState(false)
  const [day, setDay] = useState('')
  const [note, setNote] = useState('')
  useEffect(() => {
    if (!open) return
    setDay(mine?.remind_on || '')
    setNote(mine?.note || '')
    const close = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const othersText = others.map(r => `${r.user}: ${dm(r.remind_on)}${r.note ? ` — ${r.note}` : ''}`).join('\n')
  const hint = [mine && `Ваш: ${dm(mine.remind_on)}${mine.sent ? ' (отправлен)' : ''}${mine.note ? ` — ${mine.note}` : ''}`, othersText]
    .filter(Boolean).join('\n') || 'Поставить себе будильник'
  const live = mine && !mine.sent
  return (
    <span data-pop-root style={{ position: 'relative', display: 'inline-flex', flex: '0 0 auto' }}>
      <span onClick={e => { e.stopPropagation(); setOpen(o => !o) }} title={hint}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 4px', borderRadius: 6, cursor: 'pointer',
          color: live ? 'var(--accent)' : others.length ? 'var(--text-secondary)' : 'var(--text-disabled)',
          background: live ? 'var(--accent-tint)' : 'transparent', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>
        <BellIcon on={live} />{live && dm(mine.remind_on)}{!live && others.length > 0 && others.length}
      </span>
      <PortalPopover open={open} minWidth={260} align="right" flip>
        <div onClick={e => e.stopPropagation()} style={{ padding: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 12.5, fontWeight: 700 }}>Будильник себе</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>В 09:00 МСК выбранного дня — в Telegram и на почту</span>
          <input type="date" value={day} min={todayMsk()} onChange={e => setDay(e.target.value)} style={{ ...inp, fontFamily: MONO }} />
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="о чём напомнить" maxLength={500} style={inp} />
          {others.length > 0 && (
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}>
              {othersText}
            </span>
          )}
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button disabled={!day} onClick={() => { onSave({ remind_on: day, note }); setOpen(false) }}
              style={{ ...primaryBtn, opacity: day ? 1 : 0.5, cursor: day ? 'pointer' : 'default' }}>Поставить</button>
            {mine && <span onClick={() => { onRemove(mine.id); setOpen(false) }}
              style={{ fontSize: 12, color: 'var(--danger-fg)', cursor: 'pointer' }}>Снять</span>}
          </span>
        </div>
      </PortalPopover>
    </span>
  )
}
