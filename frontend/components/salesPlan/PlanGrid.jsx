// Сетка «Плана продаж» (владелец 24.10.2026, docs/ПЛАН_план_продаж.md): общая цель → продажники (+ «без продажника») →
// услуги по группам (+ «без услуги»). Режим «Выполнение» — одно число в ячейке, плашка % к цели и подсветка; режим «Цели» —
// поля ввода по месяцам и строки сверки с общей целью. Расчёты — lib/salesPlan.mjs.
import { Fragment } from 'react'
import { MONO, UI } from '@/components/salesTableKit'
import { buckets, cellValue, fmtK, fmtRub, fmtSigned, groupServices, heat, phase, sumCells } from '@/lib/salesPlan.mjs'

const HEAT_BG = { bad: 'var(--danger-tint)', mid: 'var(--warning-tint)', ok: 'var(--income-tint)', over: 'var(--income-border)' }
const HEAT_FG = { bad: 'var(--danger-fg)', mid: 'var(--warning-fg)', ok: 'var(--income-fg)', over: 'var(--income-fg)' }
const NAME_W = 240
const cap = { fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const stickyName = (bg) => ({ position: 'sticky', left: 0, zIndex: 1, background: bg, minWidth: NAME_W, maxWidth: NAME_W, padding: '6px 12px',
  textAlign: 'left', borderBottom: '1px solid var(--border-inner)', borderRight: '1px solid var(--border-inner)' })
const cellBase = { padding: '0 10px', height: 40, textAlign: 'right', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 12.5,
  borderBottom: '1px solid var(--border-inner)', minWidth: 118 }

export const editKey = (row, m) => `${row.scope}|${row.key_id}|${m}`
export const editable = (row) => ['общий', 'услуга', 'продажник'].includes(row.scope)

/** Строки экрана в порядке разделов. `sections` — {reps:[], services:[{group, rows, sub}]}. */
export function layout(rows) {
  const total = rows.find(r => r.scope === 'общий')
  const reps = rows.filter(r => r.scope === 'продажник' || r.scope === 'без продажника')
  const svc = rows.filter(r => r.scope === 'услуга')
  const noSvc = rows.filter(r => r.scope === 'без услуги')
  const groups = groupServices(svc).map(g => ({ ...g, sub: { scope: 'группа', key_id: g.group, name: g.group,
    months: g.rows[0].months.map((_, m) => sumCells(g.rows.map(r => r.months[m]))) } }))
  return { total, reps, groups, noSvc }
}

function NameCell({ row, sub, muted, bg, extra }) {
  return (
    <td title={row.name} style={{ ...stickyName(bg || 'var(--bg-card)'), paddingLeft: sub ? 28 : 12 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
          <span style={{ fontFamily: UI, fontSize: 13, fontWeight: row.scope === 'общий' || row.scope === 'группа' ? 700 : 500,
            color: muted || row.inactive ? 'var(--text-secondary)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.name}</span>
          {row.scope === 'группа' && <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>группа услуг · итог</span>}
          {(row.scope === 'без продажника' || row.scope === 'без услуги') && <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>вне разреза · только в общей цели</span>}
          {!!row.inactive && <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>неактивен · показан за выполненное в году</span>}
        </span>
        {extra}
      </span>
    </td>
  )
}

function RunCell({ row, b, cur, metric, onCell, outside }) {
  const ph = phase(b, cur)
  const { v, p, base, future } = cellValue(b.c, metric, ph)
  const h = outside || metric === 'goal' ? null : heat(p)
  const noGoal = b.c.goal == null
  const text = metric === 'pct' ? (v == null ? '—' : `${v} %`) : metric === 'gap' ? fmtSigned(v) : fmtK(v)
  const title = noGoal ? `цель не задана · ${ph === 'future' ? 'прогноз' : 'выполнено'} ${fmtK(base)}`
    : `цель ${fmtK(b.c.goal)} · выполнено ${fmtK(b.c.done)} · прогноз ${fmtK(b.c.forecast)}`
  return (
    <td onClick={() => onCell(row, b)} title={title}
      style={{ ...cellBase, cursor: 'pointer', background: h ? HEAT_BG[h] : 'transparent',
        color: noGoal && metric !== 'goal' ? 'var(--text-muted)' : future ? 'var(--accent-fg)' : 'var(--text-primary)',
        fontStyle: future ? 'italic' : 'normal', fontWeight: row.scope === 'общий' || row.scope === 'группа' ? 700 : 500,
        boxShadow: ph === 'now' ? 'inset 2px 0 0 var(--accent-border), inset -2px 0 0 var(--accent-border)' : 'none' }}>
      {text}
      {(metric === 'done' || metric === 'forecast') && p != null && !outside && (
        <span style={{ marginLeft: 6, padding: '1px 5px', borderRadius: 5, fontSize: 10, fontWeight: 700, fontStyle: 'normal',
          background: 'var(--bg-card)', color: HEAT_FG[h] || 'var(--text-muted)' }}>{p}%</span>
      )}
    </td>
  )
}

function GoalCell({ row, m, edits, onEdit, b, readOnly }) {
  if (readOnly || b.m0 !== b.m1) {
    return <td style={{ ...cellBase, color: 'var(--text-muted)' }}>{b.c.goal == null ? '—' : fmtK(b.c.goal)}</td>
  }
  const k = editKey(row, m)
  const changed = k in edits
  const val = changed ? edits[k] : fmtRub(row.months[m].goal)       // правки — полные рубли, показ сетки — тыс. ₽
  return (
    <td style={{ ...cellBase, padding: '0 6px', minWidth: 142 }}>
      <input value={val} inputMode="decimal" placeholder="—" onChange={e => onEdit(k, e.target.value)}
        title="полные рубли без НДС, например 10 000 000; пусто — цель не задана"
        style={{ width: 128, height: 28, boxSizing: 'border-box', textAlign: 'right', fontFamily: MONO, fontSize: 12.5, borderRadius: 7,
          padding: '0 7px', outline: 'none', color: 'var(--text-primary)',
          border: `1px solid ${changed ? 'var(--warning-border)' : 'var(--border-card)'}`,
          background: changed ? 'var(--warning-tint)' : 'var(--bg-card)' }} />
    </td>
  )
}

export default function PlanGrid({ rows, mode, grain, metric, cur, scope, collapsed, onToggle, onCell, edits, onEdit, canEdit,
  onSpread, checkRows, year }) {
  const { total, reps, groups, noSvc } = layout(rows)
  if (!total) return null
  const cols = buckets(total.months, grain)
  const run = mode === 'run'
  const line = (row, opts = {}) => {
    const bs = buckets(row.months, grain)
    const outside = row.scope === 'без продажника' || row.scope === 'без услуги'
    const year_ = sumCells(row.months)
    const ro = !canEdit || !editable(row) || opts.readOnly
    return (
      <tr key={`${row.scope}|${row.key_id}`} style={{ background: outside ? 'var(--bg-subtle)' : undefined }}>
        <NameCell row={row} sub={opts.sub} muted={outside} bg={outside ? 'var(--bg-subtle)' : undefined}
          extra={!run && canEdit && editable(row) && grain === 'm' ? (
            <button type="button" data-pop-root title="Разложить год по месяцам" onClick={e => onSpread(row, e.currentTarget.getBoundingClientRect())}
              style={{ width: 22, height: 22, flex: '0 0 22px', borderRadius: 6, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: 0 }}>⇶</button>) : null} />
        {bs.map(b => (run
          ? <RunCell key={b.key} row={row} b={b} cur={cur} metric={metric} onCell={onCell} outside={outside} />
          : <GoalCell key={b.key} row={row} m={b.m0} b={b} edits={edits} onEdit={onEdit} readOnly={ro} />))}
        {run
          ? <RunCell row={row} b={{ key: 'y', label: String(year), m0: 0, m1: 11, c: year_ }} cur={cur >= 12 ? 12 : -1} metric={metric}
              onCell={onCell} outside={outside} />
          : <td style={{ ...cellBase, fontWeight: 700, borderLeft: '2px solid var(--border-card)' }}>{fmtK(year_.goal)}</td>}
      </tr>
    )
  }
  const section = (id, title, right, body) => (
    <Fragment key={`sec-${id}`}>
      <tr key={`sec-${id}`} onClick={() => onToggle(id)} style={{ cursor: 'pointer' }}>
        <td style={{ ...stickyName('var(--bg-subtle)'), ...cap }}>{collapsed[id] ? '▸' : '▾'}&nbsp; {title}</td>
        <td colSpan={cols.length + 1} style={{ background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)', textAlign: 'right',
          padding: '0 12px', fontSize: 11.5, fontFamily: UI }}>{right}</td>
      </tr>
      {!collapsed[id] && body}
    </Fragment>
  )
  return (
    <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%', fontFamily: UI }}>
      <thead>
        <tr>
          <th style={{ ...stickyName('var(--bg-card)'), ...cap, position: 'sticky', top: 0, zIndex: 3 }}>Разрез</th>
          {cols.map(b => {
            const now = phase(b, cur) === 'now'
            return <th key={b.key} style={{ ...cap, position: 'sticky', top: 0, zIndex: 2, padding: '10px', textAlign: 'right',
              background: now ? 'var(--accent-tint)' : 'var(--bg-card)', color: now ? 'var(--accent-fg)' : 'var(--text-cap)',
              borderBottom: '1px solid var(--border-card)' }}>{b.label}</th>
          })}
          <th style={{ ...cap, position: 'sticky', top: 0, zIndex: 2, padding: '10px', textAlign: 'right', background: 'var(--bg-card)',
            borderBottom: '1px solid var(--border-card)', borderLeft: '2px solid var(--border-card)' }}>{year}</th>
        </tr>
      </thead>
      <tbody>
        {line(total)}
        {scope !== 'svc' && section('reps', 'Продажники', checkRows.repsNote, <>
          {reps.map(r => line(r))}
          {!run && checkRows.reps}
        </>)}
        {scope !== 'rep' && groups.length > 0 && section('svc', 'Услуги', checkRows.svcNote, <>
          {groups.map(g => <Fragment key={`g-${g.group}`}>{line(g.sub, { readOnly: true })}{g.rows.map(r => line(r, { sub: true }))}</Fragment>)}
          {noSvc.map(r => line(r))}
          {!run && checkRows.svc}
        </>)}
      </tbody>
    </table>
  )
}
