// Окно «Перераспределить объём» (хендофф 26.10.2026): фильтры и таблица площадок. Клик по строке выбирает площадку для
// графика; поле «Новый план» и «↺» выбор не переключают.
import { useEffect, useRef, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'
import { FILTERS, needPerDay, nextSort, parsePlan, passes, planOf, sortRows, tempoOf } from '@/lib/reallocView.mjs'

const COLS = 'minmax(170px,1.7fr) minmax(104px,1fr) repeat(6,minmax(70px,0.8fr)) minmax(132px,1.1fr) minmax(84px,0.8fr)'
const nf = (v) => (v < 0 ? '−' : '') + grp(Math.abs(Math.round(v || 0)))
const R = { fontFamily: MONO, fontSize: 12, textAlign: 'right' }
const stop = (e) => e.stopPropagation()
// Колонки шапки: ключ сортировки (`lib/reallocView` → sortRows) и подпись в две строки.
const HEAD = [['name', 'Площадка'], ['pace', 'Темп'], ['shows_day', 'Показано', 'за сутки'], ['offered_day', 'Предложено', 'сетью · сутки'],
  ['capacity', 'Может', 'в сутки ≈'], ['need', 'Нужно в сутки', 'до конца'], ['plan', 'План', 'сейчас'], ['delta', 'Отдаёт / берёт', 'за флайт'],
  ['newplan', 'Новый план'], ['after', 'Нужно в сутки', 'после']]

function HeadCell({ k, top, sub, sort, onSort }) {
  const on = sort?.key === k
  return (
    <span onClick={() => onSort(k)} title="Сортировать" style={{ textAlign: k === 'name' || k === 'pace' ? 'left' : 'right', cursor: 'pointer',
      userSelect: 'none', color: on ? 'var(--accent)' : undefined }}>
      {top}{sub && <><br />{sub}</>}{on && <span> {sort.dir === 'asc' ? '↑' : '↓'}</span>}
    </span>
  )
}

export function ReallocFilters({ rows, edits, filter, setFilter }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {FILTERS.map(([k, label]) => {
        const on = filter === k
        const n = rows.filter(r => passes(r, k, edits)).length
        return (
          <span key={k} onClick={() => setFilter(k)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 11px', borderRadius: 10,
            background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
            color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            {label}<span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span></span>
        )
      })}
      <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>все величины — показы; «нужно в сутки» = остаток плана ÷ дни до конца флайта</span>
    </div>
  )
}

export function ReallocTable({ rows, all, edits, setEdit, days, sel, setSel, canEdit, busy }) {
  // Итого — по всем площадкам РК (баланс плана), а не по отфильтрованным строкам
  const planTotal = all.reduce((a, r) => a + (r.plan || 0), 0)
  const newTotal = all.reduce((a, r) => a + (planOf(r, edits) || 0), 0)
  // Порядок считается по правкам на момент клика: иначе при сортировке по «Новому плану» строка уезжала бы из-под курсора.
  // Правки пришли НЕ из таблицы («Перенести», «Применить», сброс, перезагрузка) — порядок пересчитывается (ревью 26.10.2026).
  const [sort, setSort] = useState(null)
  const own = useRef(false)
  useEffect(() => {
    if (own.current) { own.current = false; return }
    setSort(s => (s ? { key: s.key, dir: s.dir, edits } : s))
  }, [edits, all])
  const typed = (id, v) => { own.current = true; setEdit(id, v) }
  const list = sortRows(rows, sort, sort?.edits || edits, days)
  return (
    // Прокрутку (обе оси) держит контейнер окна: своя горизонтальная прокрутка сломала бы липкую шапку колонок.
    <div>
      <div style={{ minWidth: 1040 }}>
        <div style={{ position: 'sticky', top: 0, zIndex: 1, background: 'var(--bg-card)',
          display: 'grid', gridTemplateColumns: COLS, gap: 12, padding: '8px 8px 8px', borderBottom: '1px solid var(--border-card)', alignItems: 'end',
          fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
          {HEAD.map(([k, top, sub]) => <HeadCell key={k} k={k} top={top} sub={sub} sort={sort} onSort={(key) => { own.current = false; setSort(s => ({ ...nextSort(s, key), edits })) }} />)}
        </div>
        {list.map(r => {
          const np = planOf(r, edits)
          const ch = np !== r.plan
          const T = tempoOf(r.pace)
          const after = Math.round(needPerDay(np, r.fact, days))
          const over = r.capacity != null && after > r.capacity
          const picked = sel === r.id
          const noOffer = r.offered_day == null
          return (
            <div key={r.id} onClick={() => setSel(picked ? null : r.id)} title="Показать площадку на графике"
              style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: 8, borderBottom: '1px solid var(--border-row)', cursor: 'pointer',
                background: picked ? 'var(--accent-tint)' : ch ? 'var(--bg-tint)' : 'transparent', boxShadow: picked ? 'inset 3px 0 0 var(--accent)' : 'none' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                {!!r.note && <span title={r.note} style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.note}</span>}
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, justifySelf: 'start', height: 22, padding: '0 8px', borderRadius: 8,
                background: T[1], color: T[2], fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: T[3] }} />{T[0]}</span>
              <span style={R}>{r.shows_day != null ? nf(r.shows_day) : '—'}</span>
              <span style={{ ...R, color: noOffer ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{noOffer ? '—' : nf(r.offered_day)}</span>
              <span style={{ ...R, color: r.capacity == null ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{r.capacity == null ? '—' : nf(r.capacity)}</span>
              <span style={{ ...R, fontWeight: 700 }}>{nf(r.need)}</span>
              <span style={{ ...R, color: 'var(--text-secondary)' }}>{nf(r.plan)}{r.fixed_plan != null ? ' ✎' : ''}</span>
              <span style={{ ...R, fontWeight: 700, color: !ch ? 'var(--text-disabled)' : np > r.plan ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
                {!ch ? '—' : (np > r.plan ? '+' : '−') + nf(Math.abs(np - r.plan))}</span>
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                {ch && <span onClick={e => { stop(e); typed(r.id, null) }} title="Вернуть план" style={{ fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>↺</span>}
                {canEdit ? (
                  <input value={grp(np)} disabled={busy} onClick={stop} inputMode="numeric"
                    onChange={e => { const v = parsePlan(e.target.value); typed(r.id, v == null || v === r.plan ? null : v) }}
                    style={{ width: 120, boxSizing: 'border-box', height: 32, padding: '0 10px', textAlign: 'right', fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
                      border: `1px solid ${ch ? 'var(--accent)' : 'var(--border-card)'}`, borderRadius: 12, background: ch ? 'var(--bg-tint)' : 'var(--bg-card)',
                      color: 'var(--text-primary)', outline: 'none' }} />
                ) : <span style={R}>{nf(np)}</span>}
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                <span style={{ ...R, fontWeight: 700, color: over ? 'var(--danger-fg)' : after > (r.shows_day ?? Infinity) ? 'var(--warning-fg)' : 'var(--text-primary)' }}>{nf(after)}</span>
                {over && <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--danger-fg)' }}>выше «может»</span>}
              </span>
            </div>
          )
        })}
        <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: '10px 8px 0', fontFamily: MONO, fontWeight: 700 }}>
          <span style={{ fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>Итого · {rows.length} площадок</span>
          <span /><span /><span /><span /><span />
          <span style={{ fontSize: 12, textAlign: 'right' }}>{nf(planTotal)}</span><span />
          <span style={{ fontSize: 12, textAlign: 'right', color: newTotal !== planTotal ? 'var(--danger-fg)' : 'var(--income-fg)' }}>{nf(newTotal)}</span><span />
        </div>
      </div>
    </div>
  )
}
