/**
 * Список «Моих сделок» по группам «чей ход» (v5, README §«Список»): «Ваш ход» раскрыта, «Ждём: …» и «Всё хорошо: …» свёрнуты;
 * при выбранной стадии раскрыты все. Строка — та же, что в «Дашборде» (`QueueRow`: колонки как на проде), клик — расхлоп.
 * Сортировка по заголовкам действует внутри каждой группы.
 */
import { Collapse } from '@/lib/motion'
import { Fragment, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import QueueRow, { QueueHead } from '@/components/accounts/dashboard/QueueRow'
import { compareRows, mln } from '@/components/accounts/dashboard/ladder'
import { groups, hot } from './contours'

// «Ваш ход» в NAVY — оранжевый --signal (README §4 хендоффа design_handoff_account_navy); в прежних темах переменная не задана
const DOT = { mine: 'var(--acc-turn, var(--danger))', wait: 'var(--text-faint)', good: 'var(--income)' }
const NOTE = { mine: null, wait: 'от вас ничего не нужно', good: 'идёт по плану' }

// Шапка колонок прилипает под меню и закреплённой панелью фильтров (владелец 18.11.2026: закрепляться должна и панель):
// высота меню — `--nav-h` (NavBar), высота панели — `--acc-bar-h` (страница меряет её сама). Шапки доски — на том же уровне.
export const STICKY_TOP = 'calc(var(--nav-h, 58px) + var(--acc-bar-h, 0px) + 6px)'
// Панель фильтров — сразу под меню
export const BAR_TOP = 'var(--nav-h, 58px)'

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
                // раскрытая группа: заголовок отделён от шапки колонок чертой и зазором (владелец 16.11.2026: «плохо разведены»)
                borderBottom: isOpen ? '1px solid var(--border-card)' : 'none',
                background: g.tone === 'mine' ? 'var(--bg-card)' : 'var(--bg-subtle)' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: DOT[g.tone] }} />
              <span style={{ fontSize: 14, fontWeight: 800 }}>{g.title}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: g.tone === 'mine' ? 'var(--acc-turn-num, var(--text-secondary))' : 'var(--text-secondary)' }}>{g.rows.length}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{mln(g.rows.reduce((s, r) => s + (r.amount || 0), 0))}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {g.tone === 'mine' ? `по срочности${hotN ? `: ${hotN} горит` : ''}` : NOTE[g.tone]}</span>
              <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{isOpen ? 'свернуть ▴' : 'развернуть ▾'}</span>
            </div>
            {isOpen && (
              <div style={{ padding: '0 8px 6px' }}>
                {/* сверху 12 px — по замеру равно нижнему отступу подписей (SortHead: 0 8px 10px + межстрочное), чтобы шапка стояла посередине (16.11.2026) */}
                <div data-col-head style={{ position: 'sticky', top: STICKY_TOP, zIndex: 4, background: 'var(--bg-card)', paddingTop: 12 }}>
                  <QueueHead sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                </div>
                {sorted.map(r => (
                  <Fragment key={r.id}>
                    <QueueRow row={r} open={expandedId === r.id} {...rowProps} />
                    {expandedId === r.id && <Collapse>{renderDetail(r)}</Collapse>}
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
