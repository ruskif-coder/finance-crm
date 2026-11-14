/**
 * Список «Моих сделок» по группам «чей ход» (v5, README §«Список»): «Ваш ход» раскрыта, «Ждём: …» и «Всё хорошо: …» свёрнуты;
 * при выбранной стадии раскрыты все. Строка — та же, что в «Дашборде» (`QueueRow`: колонки как на проде), клик — расхлоп.
 * Сортировка по заголовкам действует внутри каждой группы.
 */
import { Fragment, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import QueueRow, { QueueHead } from '@/components/accounts/dashboard/QueueRow'
import { compareRows, mln } from '@/components/accounts/dashboard/ladder'
import { groups, hot } from './contours'

const DOT = { mine: 'var(--danger)', wait: 'var(--text-faint)', good: 'var(--income)' }
const NOTE = { mine: null, wait: 'от вас ничего не нужно', good: 'идёт по плану' }

// Шапка колонок прилипает под верхним меню (его высота — 58 px; шапки колонок доски — на том же уровне).
export const STICKY_TOP = 64

export default function TurnGroups({ rows, allOpen, sortKey, sortDir, onSort, renderDetail, expandedId, rowProps }) {
  const [open, setOpen] = useState({ mine: true })
  const list = groups(rows)
  if (!list.length) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Сделок нет — под выбранные условия ничего не попало</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {list.map(g => {
        const isOpen = allOpen || (open[g.key] ?? g.tone === 'mine')
        const sorted = sortKey ? [...g.rows].sort(compareRows(sortKey, sortDir)) : g.rows
        const hotN = g.rows.filter(hot).length
        return (
          // Без overflow: hidden — иначе шапка колонок внутри не прилипает при прокрутке (владелец 14.11.2026).
          <div key={g.key} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }}>
            <div onClick={() => setOpen(o => ({ ...o, [g.key]: !isOpen }))}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 18px', cursor: 'pointer', borderRadius: isOpen ? '16px 16px 0 0' : 16,
                background: g.tone === 'mine' ? 'var(--bg-card)' : 'var(--bg-subtle)' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: DOT[g.tone] }} />
              <span style={{ fontSize: 14, fontWeight: 800 }}>{g.title}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>{g.rows.length}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{mln(g.rows.reduce((s, r) => s + (r.amount || 0), 0))}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {g.tone === 'mine' ? `по срочности${hotN ? `: ${hotN} горит` : ''}` : NOTE[g.tone]}</span>
              <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{isOpen ? 'свернуть ▴' : 'развернуть ▾'}</span>
            </div>
            {isOpen && (
              <div style={{ padding: '0 8px 6px' }}>
                <div style={{ position: 'sticky', top: STICKY_TOP, zIndex: 4, background: 'var(--bg-card)' }}>
                  <QueueHead sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                </div>
                {sorted.map(r => (
                  <Fragment key={r.id}>
                    <QueueRow row={r} open={expandedId === r.id} {...rowProps} />
                    {expandedId === r.id && renderDetail(r)}
                  </Fragment>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
