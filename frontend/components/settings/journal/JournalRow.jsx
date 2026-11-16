// Строка ленты журнала по макету design_handoff_journal (16.11.2026): обычная запись, строка группы «× N» и её записи.
import Link from 'next/link'
import { MONO } from '../../salesTableKit'
import { fmtTime } from '@/lib/dates'
import { groupSummary, whoOf } from './journalModel'

export const COLS = '92px 230px 264px minmax(200px,1fr) minmax(300px,1.7fr)'
const grid = { display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', minHeight: 40,
  borderBottom: '1px solid var(--border-row)' }
const cell = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

function Action({ label, section, mult, open }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <span title={section ? `Раздел: ${section.title}` : ''}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 24, boxSizing: 'border-box', padding: '3px 9px',
          borderRadius: 7, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', fontSize: 11.5, fontWeight: 600,
          color: 'var(--text-secondary)', lineHeight: 1.25, minWidth: 0 }}>
        <span style={{ flex: '0 0 7px', width: 7, height: 7, borderRadius: 2, background: section?.color || 'var(--text-cap)' }} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      </span>
      {mult > 0 && (
        <span title={open ? 'Свернуть' : `Показать все ${mult}`}
          style={{ fontFamily: MONO, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 4, height: 22, padding: '0 7px',
            borderRadius: 6, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', fontSize: 11, fontWeight: 700,
            color: 'var(--accent-fg)', whiteSpace: 'nowrap' }}>× {mult} <span style={{ fontSize: 8 }}>{open ? '▴' : '▾'}</span></span>
      )}
    </span>
  )
}

function Who({ item, showCab, hide }) {
  if (hide) return <span />
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
      <span style={{ ...cell, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' }}>{whoOf(item)}</span>
      {showCab && item.actor.kind === 'cabinet' && (
        <span title="Пользователь кабинета паблишера"
          style={{ fontFamily: MONO, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5,
            background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', fontSize: 9, fontWeight: 700, letterSpacing: '.05em',
            textTransform: 'uppercase', color: 'var(--warning-fg)' }}>кабинет</span>
      )}
    </span>
  )
}

function ObjectCell({ object }) {
  if (!object) return <span style={{ ...cell, fontSize: 12.5, color: 'var(--text-disabled)' }}>—</span>
  return (
    <span style={{ ...cell, fontSize: 12.5, color: 'var(--text-primary)' }} title={[object.code, object.label].filter(Boolean).join(' · ')}>
      {!!object.code && (
        <Link href={`/sales/deals/${object.code}`} onClick={e => e.stopPropagation()}
          style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, marginRight: 6, color: 'var(--accent)' }}>{object.code}</Link>
      )}
      {object.label || ''}
    </span>
  )
}

export function OneRow({ item, sections, showCab, child }) {
  return (
    <div className="j-row" style={{ ...grid, padding: `5px 20px 5px ${child ? 34 : 20}px`, background: child ? 'var(--bg-subtle)' : 'transparent' }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, color: child ? 'var(--text-faint)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtTime(item.at)}</span>
      <Who item={item} showCab={showCab} hide={child} />
      <Action label={item.action_label} section={sections[item.section]} />
      <ObjectCell object={item.object} />
      <span style={{ minWidth: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.35 }} title={item.details}>{item.details}</span>
    </div>
  )
}

export function GroupRow({ items, open, onToggle, sections, showCab }) {
  const s = groupSummary(items)
  const first = items[0]
  return (
    <>
      <div className="j-row" onClick={onToggle} role="button" aria-expanded={open}
        style={{ ...grid, padding: '5px 20px', cursor: 'pointer', background: open ? 'var(--bg-tint)' : 'transparent' }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{s.time}</span>
        <Who item={first} showCab={showCab} />
        <Action label={first.action_label} section={sections[first.section]} mult={items.length} open={open} />
        <span style={{ ...cell, fontSize: 12.5, color: s.object === '—' ? 'var(--text-disabled)' : 'var(--text-secondary)' }}>{s.object}</span>
        <span style={{ minWidth: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.35 }}>{open ? '' : s.details}</span>
      </div>
      {open && items.map(it => <OneRow key={it.id} item={it} sections={sections} showCab={showCab} child />)}
    </>
  )
}
