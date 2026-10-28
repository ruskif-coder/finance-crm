/**
 * Каркас таблиц карточки договора (хендофф «договорZ»): заголовок · счётчик · подпись; поиск и чипы-фильтры со счётчиками; тело в
 * прокрутке с липкой шапкой и общей минимальной шириной (страница по горизонтали не едет); подвал «показано N из M» + итог по
 * отфильтрованному. Колонки: `{ t, w, right, mono, cell(row) }`.
 */
import { useMemo, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { box, cap, h2, count, note, money } from '@/components/contractCard/ui'

const searchBox = { display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 10px', width: 240, boxSizing: 'border-box', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 9 }

function Chip({ on, label, n, onClick }) {
  return (
    <span onClick={onClick} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 8, border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                                      background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
      {label}<span style={{ fontFamily: MONO, fontSize: 10.5, color: on ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{n}</span>
    </span>
  )
}

export default function DataTable({ id, title, hint, rows, cols, minW = 760, maxH = 440, search, filters, sum, empty, aside }) {
  const [q, setQ] = useState('')
  const [f, setF] = useState(filters ? filters[0].key : null)
  const pass = useMemo(() => {
    const flt = filters ? filters.find(x => x.key === f) : null
    const needle = q.trim().toLowerCase()
    return rows.filter(r => (!flt || flt.test(r)) && (!needle || !search || search(r).toLowerCase().includes(needle)))
  }, [rows, q, f, filters, search])
  const tmpl = cols.map(c => c.w || 'minmax(0, 1fr)').join(' ')
  const total = sum ? pass.reduce((s, r) => s + (sum(r) || 0), 0) : null
  return (
    <section id={id} style={{ ...box, padding: '16px 20px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingBottom: 10 }}>
        <span style={h2}>{title}</span><span style={count}>{rows.length}</span>{hint && <span style={note}>{hint}</span>}
        {aside && <span style={{ marginLeft: 'auto' }}>{aside}</span>}
      </div>
      {!rows.length ? <span style={{ padding: '4px 0', fontSize: 12.5, color: 'var(--text-muted)' }}>{empty}</span> : (
        <>
          {(search || filters) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 10 }}>
              {search && (
                <span style={searchBox}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                  <input value={q} onChange={e => setQ(e.target.value)} placeholder="поиск" style={{ flex: 1, minWidth: 0, border: 0, outline: 'none', background: 'transparent', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--text-primary)' }} />
                </span>
              )}
              {filters && filters.map(x => <Chip key={x.key} on={f === x.key} label={x.label} n={rows.filter(x.test).length} onClick={() => setF(x.key)} />)}
            </div>
          )}
          <div style={{ overflow: 'auto', maxHeight: maxH, borderBottom: '1px solid var(--border-inner)' }}>
            <div style={{ minWidth: minW }}>
              <div style={{ ...cap, position: 'sticky', top: 0, zIndex: 1, background: 'var(--bg-card)', display: 'grid', gridTemplateColumns: tmpl, gap: 14, padding: '0 8px 7px', borderBottom: '1px solid var(--border-card)' }}>
                {cols.map(c => <span key={c.t} style={{ textAlign: c.right ? 'right' : 'left' }}>{c.t}</span>)}
              </div>
              {pass.map((r, i) => (
                <div key={r.id ?? i} style={{ display: 'grid', gridTemplateColumns: tmpl, gap: 14, alignItems: 'center', padding: '9px 8px', borderBottom: '1px solid var(--border-row)' }}>
                  {cols.map(c => (
                    <span key={c.t} style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: c.right ? 'right' : 'left', fontFamily: c.mono ? MONO : 'inherit', fontSize: 12.5, fontWeight: c.bold ? 700 : 500 }}>
                      {c.cell(r)}
                    </span>
                  ))}
                </div>
              ))}
              {!pass.length && <span style={{ display: 'block', padding: '16px 8px', fontSize: 12.5, color: 'var(--text-muted)' }}>Под поиск ничего не попало</span>}
            </div>
          </div>
          {(search || filters) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 8px 0', fontSize: 12, color: 'var(--text-muted)' }}>
              <span>показано {pass.length} из {rows.length}</span>
              {sum && <><span style={{ ...cap, marginLeft: 'auto' }}>итого</span><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{money(total)}</span></>}
            </div>
          )}
        </>
      )}
    </section>
  )
}
