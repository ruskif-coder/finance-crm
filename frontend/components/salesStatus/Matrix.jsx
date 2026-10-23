// «Статусы продаж» — таблица: рекламодатель → бренд → сделки, 3 месяца × (факт · средняя · низкая).
// Вёрстка — из хендоффа («Статусы продаж.dc.html»); первая колонка и шапка закреплены, скролл только внутри таблицы.
import { useMemo } from 'react'
import Bell from './Bell'
import Link from 'next/link'
import { grp } from '@/lib/salesFormat'
import { COLS, COL_LABEL, COL_SHORT, GROUP, STAGE_DOT, cellSum, dm, meetLook, MEET_NEXT, monthName } from '@/lib/salesStatus'

const MONO = "'JetBrains Mono', monospace"
const ELL = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const TXT = { padding: '0 8px', fontSize: 11, color: 'var(--text-secondary)', ...ELL }
const uniq = (list, k) => Array.from(new Set(list.map(d => d[k]).filter(Boolean))).join(', ')
const line = (c) => (c === 'low' ? 'var(--border-inner)' : 'transparent')

function Meet({ value, excel, who, onClick }) {
  const l = meetLook(value || '')
  return (
    <span onClick={onClick} title={`Встреча с ${who}: ${l.word}${excel ? ' (из Excel)' : ''}${onClick ? ' · клик — сменить' : ''}`}
      style={{ position: 'relative', width: 12, height: 12, borderRadius: '50%', boxSizing: 'border-box', background: l.bg, border: l.border, cursor: onClick ? 'pointer' : 'default' }}>
      {excel && <span style={{ position: 'absolute', top: -3, right: -3, width: 5, height: 5, borderRadius: '50%', background: 'var(--accent)' }} />}
    </span>
  )
}

// Комментарий: правка в ячейке, сохранение при уходе из поля. Компонент — на уровне модуля (иначе фокус слетает).
function Comment({ value, excel, title, onSave }) {
  return (
    <>
      <textarea key={value || ''} defaultValue={value || ''} placeholder={onSave ? 'добавить…' : ''} readOnly={!onSave} title={title}
        onBlur={e => { const v = e.target.value.trim(); if (onSave && v !== (value || '')) onSave(v) }}
        style={{ flex: '1 1 auto', minWidth: 0, boxSizing: 'border-box', minHeight: 28, padding: '5px 7px', border: '1px solid transparent', borderRadius: 7,
          background: 'transparent', fontFamily: "'Manrope', sans-serif", fontSize: 11, lineHeight: 1.35, color: 'var(--text-secondary)',
          resize: 'none', outline: 'none', cursor: onSave ? 'text' : 'default', fieldSizing: 'content' }} />
      {excel && <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', whiteSpace: 'nowrap' }}>из Excel</span>}
    </>
  )
}

function DateCell({ iso, kind, title, onSet, fg }) {
  if (!onSet) return <span style={{ fontFamily: MONO, fontSize: 10.5, color: fg, whiteSpace: 'nowrap', padding: '0 2px' }}>{dm(iso)}{kind === 'modify' ? ' ~' : ''}</span>
  return (
    <input type="date" defaultValue={iso || ''} key={iso || ''} title={title}
      // Сохранение при уходе из поля: onChange срабатывал на каждую цифру года и писал «0002-10-21» (ревью 22.10.2026)
      onBlur={e => { const v = e.target.value; if (v && v !== iso && v.slice(0, 4) >= '2000' && v.slice(0, 4) <= '2100') onSet(v) }}
      style={{ width: '100%', boxSizing: 'border-box', height: 24, padding: '0 4px', border: '1px solid transparent', borderRadius: 6, background: 'transparent',
        fontFamily: MONO, fontSize: 10.5, color: fg, outline: 'none', cursor: 'pointer' }} />
  )
}

export default function Matrix({ months, deals, notes, leads, directory = [], reminders = [], showDirectory, search, st, set, can, act }) {
  // Будильник строки (владелец 23.10.2026): ставит себе любой, кто видит экран, — это напоминание, а не правка сделок
  const bell = (a, b, c) => (
    <Bell list={reminders.filter(r => (c ? (r.client_name || '').toLowerCase() === c.toLowerCase()
      : r.advertiser_id === a && (r.brand_id ?? null) === (b ?? null)))}
      onSave={v => act.remind({ advertiser_id: c ? null : a, brand_id: c ? null : (b ?? null), client_name: c || null, ...v })}
      onRemove={act.unremind} />
  )
  const live = deals.filter(d => !d.lost)
  const shown = st.showLost ? deals : live
  const drag = st.drag ? deals.find(d => d.id === st.drag) : null
  const cols = 'minmax(260px,1.2fr) 44px 44px 110px 150px 112px 32px ' + 'minmax(104px,.8fr) '.repeat(months.length * 3) +
    'minmax(240px,1.3fr) 120px 110px 110px minmax(220px,1.2fr)'
  const tail = `${8 + months.length * 3} / span 5`
  const totals = {}
  COLS.forEach(c => { totals[c] = months.map(m => cellSum(live, m, c)) })
  // Темп к закрытию по месяцу (владелец 23.10.2026): факт × прогноз открутки РК полного цикла, внешние услуги — 100 %
  const tempo = months.map(m => live.filter(d => d.month === m && d.col === 'fact').reduce((a, d) => a + d.amount * (d.pace ?? 1), 0))

  const empty = (c, click, extra = {}) => ({ kind: 'empty', bg: GROUP[c].cell, line: line(c), cursor: click ? 'pointer' : 'default', click, ...extra })

  const pinCell = (d, c, m) => ({
    kind: 'pin', d, bg: GROUP[c].cell, line: line(c),
    title: (d.lost ? 'Сорвалась — в суммы не идёт' : d.locked ? 'Проект запущен — период и вероятность больше не двигаются'
      : `${d.code || 'новая'} · ${monthName(m)}, ${COL_LABEL[c].toLowerCase()} · тащите в любую из 9 ячеек строки`) + startHint(d),
  })

  const dealCells = (d, adv, brand) => months.flatMap(m => COLS.map(c => {
    if (d.col === c && d.month === m) return pinCell(d, c, m)
    const mine = drag && drag.id === d.id
    return empty(c, mine || d.lost || !can ? null : () => act.newDeal({ adv, brand, month: m, col: c }),
      { dropKey: mine ? c + m : null, onDrop: mine ? () => act.drop(d, m, c) : null })
  }))

  const rows = useMemo(() => {
    const out = []
    // рекламодатель → { adv, brands: Map(бренд → {brand, deals}) }: сначала из сделок, затем весь справочник
    // (владелец 22.10.2026: в таблице все наши рекламодатели и бренды; «скрыть пустое» и фильтры по людям их убирают)
    const advs = new Map()
    const slot = (aid, aname, bid, bname) => {
      const k = aid ?? `?${aname || ''}`
      if (!advs.has(k)) advs.set(k, { adv: { id: aid ?? null, name: aname || '— рекламодатель не указан —' }, brands: new Map(), deals: [] })
      const A = advs.get(k)
      const bk = bid ?? 0
      if (!A.brands.has(bk)) A.brands.set(bk, { brand: { id: bid ?? null, name: bname || (aid ? 'общее по рекламодателю' : '— без бренда —') }, deals: [] })
      return A
    }
    shown.forEach(d => { const A = slot(d.advertiser_id, d.advertiser, d.brand_id, d.brand); A.deals.push(d); A.brands.get(d.brand_id ?? 0).deals.push(d) })
    if (showDirectory) {
      const qx = (search || '').trim().toLowerCase()
      const hit = (...xs) => !qx || xs.some(x => (x || '').toLowerCase().includes(qx))
      directory.forEach(a => {
        const own = notes.get(`a:${a.id}|b:`)
        a.brands.forEach(b => {
          const n = notes.get(`a:${a.id}|b:${b.id}`)
          if (hit(a.name, b.name, n?.comment_sales, n?.comment_head)) slot(a.id, a.name, b.id, b.name)
        })
        if (own && hit(a.name, own.comment_sales, own.comment_head)) slot(a.id, a.name, null, null)
        if (!a.brands.length && hit(a.name)) slot(a.id, a.name, null, null)
      })
    }
    const weight = (ds) => ds.filter(d => !d.lost && d.col !== 'low').reduce((a, d) => a + d.amount, 0)
    Array.from(advs.values()).sort((a, b) => weight(b.deals) - weight(a.deals) || b.deals.length - a.deals.length
      || a.adv.name.localeCompare(b.adv.name, 'ru')).forEach(({ adv, brands, deals: ds }) => {
      const liveDs = ds.filter(d => !d.lost)
      const brandRows = []
      brands.forEach(({ brand, deals: bd }) => {
        const bl = bd.filter(d => !d.lost)
        if (st.hideEmpty && !bl.reduce((a, d) => a + d.amount, 0)) return
        const key = `${adv.id}|${brand.id ?? ''}`
        const open = st.expandAll ? !st.open[key] : !!st.open[key]
        const single = bl.length === 1 ? bl[0] : null
        const cells = single ? dealCells(single, adv, brand) : months.flatMap(m => COLS.map(c => {
          const v = cellSum(bl, m, c)
          return v ? { kind: 'sum', value: v, weight: 600, fg: 'var(--text-primary)', bg: GROUP[c].cell, line: line(c) }
            : empty(c, can ? () => act.newDeal({ adv, brand, month: m, col: c }) : null)
        }))
        const dated = bl.filter(d => d.status_date).sort((a, b) => (a.status_date < b.status_date ? 1 : -1))
        const last = dated[0] || bl[0] || null
        const top = bl.slice().sort((a, b) => b.locked - a.locked)[0]
        const note = notes.get(`a:${adv.id}|b:${brand.id ?? ''}`)
        brandRows.push({ type: 'brand', key, adv, brand, open, cells, note, single, last, top, bl, bd,
          mine: single && drag && drag.id === single.id })
        if (open) bd.forEach(d => brandRows.push({ type: 'deal', key: `d${d.id}`, d, adv, brand, cells: d.lost ? months.flatMap(m => COLS.map(c => empty(c, null))) : dealCells(d, adv, brand),
          mine: drag && drag.id === d.id }))
      })
      if (!brandRows.length) return
      out.push({ type: 'adv', key: `a${adv.id}`, adv, liveDs, brandsN: brands.size,
        cells: months.flatMap(m => COLS.map(c => {
          const v = cellSum(liveDs, m, c)
          return v ? { kind: 'sum', value: v, weight: 700, fg: GROUP[c].fg, bg: GROUP[c].cell, line: line(c) }
            : empty(c, can && adv.id ? () => act.newDeal({ adv, month: m, col: c }) : null)
        })) })
      out.push(...brandRows)
    })
    return out
  }, [shown, notes, st.open, st.expandAll, st.hideEmpty, st.drag, months, can, directory, showDirectory, search]) // eslint-disable-line react-hooks/exhaustive-deps

  const dim = (mine) => (drag && !mine ? 0.15 : 1)
  const head = [['Клиент / бренд', 'left'], ['бренд', 'center'], ['РА', 'center'], ['Продукт', 'left'], ['Стадия', 'left'], ['Дата', 'left'], ['', 'center']]


  return (
    <div style={{ overflow: 'auto', maxHeight: 'calc(100vh - 330px)' }}>
      <div style={{ minWidth: 2430, display: 'flex', flexDirection: 'column' }}>
        <div style={{ position: 'sticky', top: 0, zIndex: 5, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: cols, borderLeft: '3px solid transparent' }}>
            <span style={{ gridColumn: 1, position: 'sticky', left: 0, zIndex: 3, background: 'var(--bg-card)' }} />
            <span style={{ gridColumn: '2 / span 6', borderRight: '1px solid var(--border-inner)' }} />
            {months.map(m => (
              <span key={m} style={{ gridColumn: 'span 3', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '9px 0 5px', background: 'var(--bg-subtle)',
                borderRight: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>
                {monthName(m)} {m.slice(0, 4)}
              </span>
            ))}
            <span style={{ gridColumn: tail }} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: cols, borderLeft: '3px solid transparent', alignItems: 'end', fontFamily: MONO, fontSize: 8.5,
            letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
            {head.map(([l, a], i) => (
              <span key={l + i} style={{ position: i === 0 ? 'sticky' : 'static', left: 0, zIndex: i === 0 ? 3 : 'auto', padding: '5px 8px 7px', textAlign: a,
                background: 'var(--bg-card)', borderRight: `1px solid ${i === 6 ? 'var(--border-inner)' : 'transparent'}`, ...ELL }}>{l}</span>
            ))}
            {months.flatMap(m => COLS.map(c => (
              <span key={m + c} style={{ padding: '5px 8px 7px', textAlign: 'right', background: GROUP[c].bg, borderRight: `1px solid ${line(c)}`, ...ELL }}>{COL_SHORT[c]}</span>
            )))}
            {['Комментарий Sales', 'РА', 'Аккаунт', 'Sales', 'Комментарий руководителя'].map(l => (
              <span key={l} style={{ padding: '5px 8px 7px', background: 'var(--bg-card)', ...ELL }}>{l}</span>
            ))}
          </div>
          <Totals cols={cols} tail={tail} months={months} totals={totals} label="итог по месяцу" top />
          <TempoRow cols={cols} tail={tail} months={months} fact={totals.fact} tempo={tempo} />
        </div>

        {rows.map(r => {
          if (r.type === 'adv') return (
            <div key={r.key} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', minHeight: 34, background: 'var(--bg-subtle)',
              borderBottom: '1px solid var(--border-card)', borderLeft: '3px solid transparent', opacity: dim(false) }}>
              <span style={{ position: 'sticky', left: 0, zIndex: 2, display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px 0 12px', background: 'var(--bg-subtle)', height: '100%', minWidth: 0 }}>
                <span style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: '-.01em', ...ELL }}>{r.adv.name}</span>
                <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{r.brandsN} бр. · {r.liveDs.length} сд.</span>
              </span>
              <span /><span /><span /><span />
              <span />
              <span style={{ borderRight: '1px solid var(--border-inner)', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{!!r.adv.id && bell(r.adv.id, null)}</span>
              <Cells cells={r.cells} st={st} set={set} can={can} />
              <span /><span style={TXT}>{uniq(r.liveDs, 'agency')}</span><span /><span /><span />
            </div>
          )
          if (r.type === 'brand') {
            const n = r.note || {}
            const ex = new Set(n.from_excel || [])
            const tgt = { advertiser_id: r.adv.id, brand_id: r.brand.id }
            const meet = (field, who) => (
              <Meet value={n[field]} excel={ex.has(field)} who={who}
                onClick={can && r.adv.id ? (e => { e.stopPropagation(); act.note(tgt, field, MEET_NEXT[n[field] || '']) }) : null} />
            )
            return (
              <div key={r.key} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', minHeight: 38, background: 'var(--bg-card)',
                borderBottom: '1px solid var(--border-row)', borderLeft: '3px solid transparent', opacity: dim(r.mine), outline: r.mine ? '1px solid var(--accent)' : 'none', outlineOffset: -1 }}>
                <span style={{ position: 'sticky', left: 0, zIndex: 2, display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px 0 14px', background: 'var(--bg-card)', height: '100%', minWidth: 0 }}>
                  <span onClick={() => act.toggle(r.key)} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, borderRadius: 4,
                    color: 'var(--text-faint)', fontSize: 9, cursor: 'pointer', flex: '0 0 16px' }}>{r.open ? '▾' : '▸'}</span>
                  <span title={r.brand.name} style={{ fontSize: 12.5, fontWeight: 600, ...ELL }}>{r.brand.name}</span>
                  {r.bl.length > 1 && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{r.bl.length} сд.</span>}
                </span>
                <span style={{ display: 'flex', justifyContent: 'center' }}>{meet('meet_brand', 'брендом')}</span>
                <span style={{ display: 'flex', justifyContent: 'center' }}>{meet('meet_agency', 'РА')}</span>
                <span style={TXT}>{uniq(r.bl, 'service')}</span>
                <span style={{ padding: '0 8px', display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  {r.top && <><span style={{ width: 6, height: 6, borderRadius: 2, background: STAGE_DOT[r.top.stage_key] || 'var(--text-disabled)', flex: '0 0 6px' }} />
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)', ...ELL }}>{r.top.stage}</span></>}
                </span>
                <span style={{ padding: '0 6px', height: '100%', display: 'flex', alignItems: 'center' }}>
                  {r.last && <DateCell iso={r.last.status_date} kind={r.last.status_date_kind} fg="var(--text-secondary)"
                    title={r.bl.length > 1 ? `Дата последнего статуса · правка уйдёт в сделку ${r.last.code || 'новую'}` : 'Дата статуса · кликните, чтобы изменить'}
                    onSet={can ? (v => act.date(r.last, v)) : null} />}
                </span>
                <span style={{ borderRight: '1px solid var(--border-inner)', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{!!r.adv.id && bell(r.adv.id, r.brand.id)}</span>
                <Cells cells={r.cells} st={st} set={set} can={can} />
                <span style={{ padding: '4px 6px', minWidth: 0, display: 'flex', alignItems: 'center', gap: 6, height: '100%' }}>
                  <Comment value={n.comment_sales} excel={ex.has('comment_sales')} title="Комментарий Sales · сохраняется при уходе из поля"
                    onSave={can && r.adv.id ? (v => act.note(tgt, 'comment_sales', v)) : null} />
                </span>
                <span style={TXT}>{uniq(r.bl, 'agency')}</span>
                <span style={TXT}>{uniq(r.bl, 'account')}</span>
                <span style={TXT}>{uniq(r.bl, 'sales')}</span>
                <span style={{ padding: '4px 6px', minWidth: 0, display: 'flex', alignItems: 'center', height: '100%' }}>
                  <Comment value={n.comment_head} excel={ex.has('comment_head')} title="Комментарий руководителя · сохраняется при уходе из поля"
                    onSave={can && r.adv.id ? (v => act.note(tgt, 'comment_head', v)) : null} />
                </span>
              </div>
            )
          }
          const d = r.d
          const fg = d.status_date_kind === 'manual' ? 'var(--accent-fg)' : d.status_date_kind === 'history' ? 'var(--text-secondary)' : 'var(--text-faint)'
          const strike = d.lost ? 'line-through' : 'none'
          return (
            <div key={r.key} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', minHeight: 34, background: r.mine ? 'var(--bg-tint)' : 'var(--bg-card)',
              borderBottom: '1px solid var(--border-row)', borderLeft: `3px solid ${d.moved && !d.lost ? 'var(--accent)' : 'transparent'}`,
              opacity: dim(r.mine), outline: r.mine ? '1px solid var(--accent)' : 'none', outlineOffset: -1 }}>
              <span style={{ position: 'sticky', left: 0, zIndex: 2, display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px 0 36px', background: 'inherit', height: '100%', minWidth: 0 }}>
                <Link href={`/sales/deals/${d.code || d.id}`} style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)', textDecoration: strike }}>{d.code}</Link>
                <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', textDecoration: strike, ...ELL }}>{d.service} · {d.lost ? 'сорвалась' : d.stage}</span>
              </span>
              <span /><span />
              <span style={TXT}>{d.service}</span>
              <span style={{ padding: '0 8px', display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: d.lost ? 'var(--danger)' : STAGE_DOT[d.stage_key] || 'var(--text-disabled)', flex: '0 0 6px' }} />
                <span style={{ fontSize: 11, color: 'var(--text-secondary)', ...ELL }}>{d.lost ? 'сорвалась' : `${d.locked ? '▶ ' : ''}${d.stage}`}</span>
              </span>
              <span style={{ padding: '0 6px', height: '100%', display: 'flex', alignItems: 'center' }}>
                <DateCell iso={d.status_date} kind={d.status_date_kind} fg={fg}
                  title={d.status_date_kind === 'manual' ? 'Дата статуса поставлена вручную' : d.status_date_kind === 'history' ? 'Дата перехода на стадию · клик — изменить'
                    : 'Переходов в истории нет, взята дата правки (~) · клик — задать точную'}
                  onSet={can && !d.lost ? (v => act.date(d, v)) : null} />
              </span>
              <span style={{ borderRight: '1px solid var(--border-inner)', height: '100%' }} />
              <Cells cells={r.cells} st={st} set={set} can={can} />
              <span /><span style={TXT}>{d.agency}</span><span style={TXT}>{d.account}</span><span style={TXT}>{d.sales}</span><span />
            </div>
          )
        })}

        {!st.hideEmpty && leads.length > 0 && <>
          <div style={{ display: 'grid', gridTemplateColumns: cols, borderLeft: '3px solid transparent', borderBottom: '1px solid var(--border-row)' }}>
            <span style={{ position: 'sticky', left: 0, zIndex: 2, gridColumn: 1, display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px 6px', background: 'var(--bg-card)', whiteSpace: 'nowrap', overflow: 'visible' }}>
              <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>Вне справочника · {leads.length}</span>
              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>клиенты из таблицы продаж, которых нет среди наших рекламодателей — список на привязку</span>
            </span>
          </div>
          {leads.map(l => {
            const ex = new Set(l.from_excel || [])
            const tgt = l.client_name ? { client_name: l.client_name } : { advertiser_id: l.advertiser_id, brand_id: l.brand_id }
            return (
              <div key={l.key} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', minHeight: 36, borderBottom: '1px solid var(--border-row)', borderLeft: '3px solid transparent', opacity: dim(false) }}>
                <span style={{ position: 'sticky', left: 0, zIndex: 2, background: 'var(--bg-card)', display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px 0 24px', minWidth: 0, height: '100%' }}>
                  <span title={l.title} style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', ...ELL }}>{l.title}</span>
                </span>
                {['meet_brand', 'meet_agency'].map((f, i) => (
                  <span key={f} style={{ display: 'flex', justifyContent: 'center' }}>
                    <Meet value={l[f]} excel={ex.has(f)} who={i ? 'РА' : 'брендом'} onClick={can ? (() => act.note(tgt, f, MEET_NEXT[l[f] || ''])) : null} />
                  </span>
                ))}
                <span /><span />
                <span />
                <span style={{ borderRight: '1px solid var(--border-inner)', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{bell(l.advertiser_id, l.brand_id, l.client_name)}</span>
                {months.flatMap(m => COLS.map(c => (
                  <span key={m + c} onClick={can ? (() => act.newDeal({ adv: l.advertiser_id ? { id: l.advertiser_id, name: l.title } : null, client: l.client_name, month: m, col: c })) : undefined}
                    title={can ? `Новая сделка: ${monthName(m)}, ${COL_LABEL[c].toLowerCase()}` : ''}
                    style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '0 8px', background: GROUP[c].cell,
                      borderRight: `1px solid ${line(c)}`, cursor: can ? 'pointer' : 'default', color: 'var(--text-disabled)', fontSize: 11 }}>·</span>
                )))}
                <span style={{ padding: '4px 6px', minWidth: 0, display: 'flex', alignItems: 'center', gap: 6, height: '100%' }}>
                  <Comment value={l.comment_sales} excel={ex.has('comment_sales')} title="Комментарий Sales" onSave={can ? (v => act.note(tgt, 'comment_sales', v)) : null} />
                </span>
                <span /><span /><span />
                <span style={{ padding: '4px 6px', minWidth: 0, display: 'flex', alignItems: 'center', height: '100%' }}>
                  <Comment value={l.comment_head} excel={ex.has('comment_head')} title="Комментарий руководителя" onSave={can ? (v => act.note(tgt, 'comment_head', v)) : null} />
                </span>
              </div>
            )
          })}
        </>}

        <Totals cols={cols} tail={tail} months={months} totals={totals} label="Итого, без НДС" sub={`${live.length} сд.`} />
      </div>
    </div>
  )
}

function Cells({ cells, st, set, can }) {
  return cells.map((c, i) => (
    <span key={i} onClick={c.click || undefined}
      onDragOver={c.onDrop ? (e => { e.preventDefault(); if (st.over !== c.dropKey) set({ over: c.dropKey }) }) : undefined}
      onDrop={c.onDrop ? (e => { e.preventDefault(); c.onDrop() }) : undefined}
      style={{ height: '100%', boxSizing: 'border-box', padding: '4px 6px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
        background: c.bg, borderRight: `1px solid ${c.line}`, cursor: c.cursor || 'default',
        outline: c.dropKey && st.over === c.dropKey ? '2px dashed var(--accent)' : 'none', outlineOffset: -2 }}>
      {c.kind === 'pin' && <Pin d={c.d} title={c.title} drag={st.drag} canMove={can} onStart={() => set({ drag: c.d.id })} onEnd={() => set({ drag: null, over: null })} />}
      {c.kind === 'sum' && <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: c.weight, color: c.fg }}>{grp(c.value)}</span>}
      {c.kind === 'empty' && <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>·</span>}
    </span>
  ))
}

const TEMPO_HINT = 'Темп — прогноз суммы к закрытию: сделки полного цикла — с недокрутом по прогнозу открутки РК (факт ÷ отчитанные дни × флайт); '
  + 'внешние услуги и закрытые сверкой по плану — 100 %.'

// Строка «темп» под итогом месяца — только в колонке «Факт»
function TempoRow({ cols, tail, months, fact, tempo }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', fontFamily: MONO, fontSize: 11, fontWeight: 700,
      borderLeft: '3px solid transparent', background: 'var(--bg-card)' }}>
      <span style={{ gridColumn: 1, position: 'sticky', left: 0, zIndex: 3, background: 'var(--bg-card)', padding: '4px 10px', fontSize: 8.5,
        letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>темп к закрытию</span>
      <span style={{ gridColumn: '2 / span 6' }} />
      {months.flatMap((m, mi) => COLS.map(c => {
        if (c !== 'fact') return <span key={m + c} style={{ background: GROUP[c].bg, borderRight: `1px solid ${line(c)}`, height: '100%' }} />
        const v = tempo[mi], f = fact[mi]
        const pct = f ? Math.round(v / f * 100) : null
        return (
          <span key={m + c} title={f ? `Темп ${pct} % от факта · недокрут ${grp(f - v)} ₽\n${TEMPO_HINT}` : TEMPO_HINT}
            style={{ padding: '4px 8px', textAlign: 'right', background: GROUP[c].bg, borderRight: `1px solid ${line(c)}`, height: '100%', cursor: 'help',
              display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 5, whiteSpace: 'nowrap',
              color: pct != null && pct < 100 ? 'var(--warning-fg)' : GROUP[c].fg }}>
            {f ? grp(v) : '—'}
          </span>
        )
      }))}
      <span style={{ gridColumn: tail }} />
    </div>
  )
}

function Totals({ cols, tail, months, totals, label, sub, top }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', minHeight: top ? 0 : 38, fontFamily: MONO, fontSize: top ? 11 : 11.5, fontWeight: 700,
      borderLeft: '3px solid transparent', background: 'var(--bg-card)',
      ...(top ? { borderTop: '1px solid var(--border-inner)' } : { position: 'sticky', bottom: 0, zIndex: 5, borderTop: '2px solid var(--border-card)' }) }}>
      <span style={{ gridColumn: 1, position: 'sticky', left: 0, zIndex: 3, background: 'var(--bg-card)', padding: top ? '5px 10px' : '0 12px', height: '100%',
        fontSize: top ? 8.5 : 9.5, letterSpacing: '.1em', textTransform: 'uppercase', color: top ? 'var(--text-faint)' : 'var(--text-cap)', display: 'flex', alignItems: 'center', gap: 10, whiteSpace: 'nowrap' }}>
        {label}{sub && <span style={{ fontWeight: 400, color: 'var(--text-faint)', textTransform: 'none', letterSpacing: 0 }}>{sub}</span>}
      </span>
      <span style={{ gridColumn: '2 / span 6' }} />
      {months.flatMap((m, mi) => COLS.map(c => {
        const v = totals[c][mi]
        return <span key={m + c} style={{ padding: top ? '5px 8px' : '0 8px', textAlign: 'right', color: v ? GROUP[c].fg : 'var(--text-disabled)', borderRight: `1px solid ${line(c)}`,
          background: GROUP[c].bg, height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>{v ? grp(v) : '—'}</span>
      }))}
      <span style={{ gridColumn: tail }} />
    </div>
  )
}

// Реальный старт в подсказке пина (владелец 23.10.2026): полный цикл — первый день статистики, внешние — кнопка «Запустить»
function startHint(d) {
  const full = d.full ? 'первая статистика' : 'кнопка «Запустить»'
  if (d.real_start) return `\nРеальный старт: ${dm(d.real_start)}.${d.real_start.slice(0, 4)} (${full})`
  if (!d.plan_start) return ''
  const late = d.late ? ` — опоздание ${d.late_days} дн.` : ''
  return `\nСтарта ещё не было (${full}) · план ${dm(d.plan_start)}${late}`
}

// Старт опаздывает: 7 дней после планового — жёлтый, 14 — красный (владелец 23.10.2026, app/sales/status_launch.py)
const LATE = { warn: { fg: 'var(--warning-fg)', border: 'var(--warning)', bg: 'var(--warning-tint)' },
  bad: { fg: 'var(--danger-fg)', border: 'var(--danger)', bg: 'var(--danger-tint)' } }

// Пин сделки: перетаскивается по своей строке; запущенная — под замком, новая — пунктир.
function Pin({ d, title, drag, canMove, onStart, onEnd }) {
  const movable = canMove && !d.locked && !d.lost
  const mine = drag === d.id
  const lt = !d.lost && LATE[d.late]
  return (
    <span draggable={movable} title={title}
      onDragStart={e => { if (!movable) { e.preventDefault(); return } e.dataTransfer.effectAllowed = 'move'; onStart() }}
      onDragEnd={onEnd}
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 4, height: 24, padding: '0 7px 0 5px', borderRadius: 7, maxWidth: '100%',
        background: lt ? lt.bg : d.locked ? 'var(--income-tint)' : 'var(--bg-card)',
        border: `1px solid ${lt ? lt.border : d.locked ? 'var(--income-border)' : 'var(--border-card)'}`,
        boxShadow: d.locked ? 'none' : 'var(--shadow-card)',
        color: d.lost ? 'var(--text-disabled)' : lt ? lt.fg : d.locked ? 'var(--income-fg)' : 'var(--text-primary)',
        fontFamily: MONO, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', cursor: !movable ? 'not-allowed' : mine ? 'grabbing' : 'grab' }}>
      <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{d.locked ? '🔒' : '⠿'}</span>{grp(d.amount)}
      {/* «!» — значком в углу пина, ширины не добавляет: иначе запертый пин с опозданием вылезал за колонку */}
      {lt && <span aria-label="старт опаздывает" style={{ position: 'absolute', top: -6, right: -6, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 13, height: 13, borderRadius: '50%', background: lt.border, color: 'var(--on-accent)', fontSize: 9, fontWeight: 800,
        boxShadow: '0 0 0 2px var(--bg-card)' }}>!</span>}
    </span>
  )
}
