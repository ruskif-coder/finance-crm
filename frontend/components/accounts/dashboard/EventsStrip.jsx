// Полоса «События» — дни вперёд, клик по дню фильтрует очередь (макет «акки 3»).
// Данные — /sales/account-calendar: три типа, которые система действительно знает
// (старт РК, закрытие периода, дедлайн документов). Дедлайна креативов и «ответа клиента»
// из макета нет намеренно — см. docstring account_calendar.
import { MONO, card } from '@/components/salesTableKit'
import { calendarDate } from '@/lib/dates'
import { dm } from '@/lib/salesFormat'

export const EVENT_KIND = {
  start: ['Старт РК', 'var(--income)'],
  closing: ['Закрытие периода', 'var(--violet-fg)'],
  docs: ['Дедлайн документов', 'var(--dot-current-dz)'],
}
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']
const plural = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a
  : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c)

export default function EventsStrip({ days, day, onDay }) {
  const total = days.reduce((s, d) => s + (d.total || 0), 0)
  return (
    <div style={{ ...card, padding: '16px 22px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>События</span>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
          {days.length} дн. вперёд · клик фильтрует очередь</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {Object.entries(EVENT_KIND).map(([k, [label, c]]) => (
            <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: c }} />{label}</span>
          ))}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
          {total} {plural(total, 'событие', 'события', 'событий')}</span>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
        {days.map((d, i) => {
          const on = day === d.date
          const empty = !d.total
          return (
            <span key={d.date} onClick={() => !empty && onDay(on ? null : d.date)}
              title={`${dm(d.date)} · ${empty ? 'событий нет' : Object.entries(d.kinds || {}).map(([k, n]) => `${(EVENT_KIND[k] || [k])[0]}: ${n}`).join(' · ')}`}
              style={{ flex: '1 1 0', minWidth: 0, boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 5, padding: '9px 10px',
                borderRadius: 11, cursor: empty ? 'default' : 'pointer', transition: 'background-color 150ms ease, border-color 150ms ease',
                background: on ? 'var(--accent-tint)' : i === 0 ? 'var(--bg-tint)' : (empty ? 'var(--bg-subtle)' : 'var(--bg-card)'),
                border: `1px solid ${on ? 'var(--accent)' : i === 0 ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: on || i === 0 ? 'var(--accent)' : 'var(--text-primary)' }}>{dm(d.date)}</span>
                <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                  {WD[calendarDate(d.date).getDay()]}</span>
              </span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
                <span style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1,
                  color: empty ? 'var(--border-hover)' : (i <= 1 ? 'var(--danger-fg)' : 'var(--text-primary)') }}>{d.total}</span>
                <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>соб.</span>
              </span>
              <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap', minHeight: 14 }}>
                {Object.entries(d.kinds || {}).map(([k, n]) => (
                  <span key={k} title={(EVENT_KIND[k] || [k])[0]} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '1px 4px', borderRadius: 5, background: 'var(--bg-subtle)' }}>
                    <span style={{ width: 5, height: 5, borderRadius: 1, background: (EVENT_KIND[k] || [])[1] || 'var(--text-faint)' }} />
                    <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, color: 'var(--text-secondary)' }}>{n}</span>
                  </span>
                ))}
              </span>
              <span style={{ fontSize: 9.5, color: 'var(--text-faint)', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {empty ? 'событий нет' : (d.brands || []).join(', ')}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
