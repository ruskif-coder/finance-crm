// «Трафики → Статистика» (владелец 03.10.2026): по текущим РК накопительно — общая стата,
// «Block SIMB» (блок по умолчанию площадки в нашей DSP) и база = общая − «Block SIMB».
// «Block SIMB» по кампаниям в DSP не делится: суточные показы блока площадки раскладываются
// на РК по их суточным показам на площадке (расчёт — backend app/traffic/stats.py).
// Adfox «Block SIMB» не содержит: у его показов база = общая.
// Три вида: по РК, по площадкам (с раскрытием) и матрица РК × площадка.
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import { MONO, UI, card, btnSm, inp, cell, SortHead } from '@/components/salesTableKit'
import { KpiRow } from '@/components/traffic/dashboardKit'
import { grp } from '@/lib/salesFormat'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const VIEWS = [['rk', 'По РК'], ['pub', 'По площадкам'], ['matrix', 'Матрица']]
const COLS = [
  { key: 'name', label: '', right: false },
  { key: 'total', label: 'Общая', right: true },
  { key: 'adfox', label: 'в т.ч. Adfox', right: true },
  { key: 'block_simb', label: 'Block SIMB', right: true },
  { key: 'share', label: 'Доля Block SIMB', right: true },
  { key: 'base', label: 'База', right: true },
  { key: 'money', label: '₽ общая', right: true },
  { key: 'moneyK', label: '₽ Block SIMB', right: true },
]
const GRID = 'minmax(220px,2fr) repeat(7, minmax(90px,1fr))'
// Деньги — показы × CPM площадки по договору (закупочный, до НДС) / 1000; «Block SIMB» в
// деньгах — её показы по тому же CPM, то есть в той же пропорции, что и в показах.
const rub = (v) => (v ? `${grp(v)} ₽` : '—')

const pct = (k, t) => (t ? (100 * k) / t : 0)
const pctTxt = (k, t) => (t ? `${pct(k, t).toFixed(1).replace('.', ',')} %` : '—')

function sum(rows) {
  return rows.reduce((a, r) => ({ total: a.total + r.total, adfox: a.adfox + r.adfox,
    block_simb: a.block_simb + r.block_simb, base: a.base + r.base,
    money: a.money + (r.money || 0), moneyK: a.moneyK + (r.moneyK || 0),
    noCpm: a.noCpm + (r.cpm ? 0 : r.total) }),
  { total: 0, adfox: 0, block_simb: 0, base: 0, money: 0, moneyK: 0, noCpm: 0 })
}

function group(rows, key, label) {
  const m = {}
  rows.forEach(r => {
    const k = r[key]
    if (!m[k]) m[k] = { id: k, name: r[label], rows: [] }
    m[k].rows.push(r)
  })
  return Object.values(m).map(g => ({ ...g, ...sum(g.rows) }))
}

function Row({ name, v, bold, sub, onClick, open }) {
  return (
    <div onClick={onClick} style={{ display: 'grid', gridTemplateColumns: GRID, alignItems: 'center',
      minHeight: 38, borderBottom: '1px solid var(--border-row)', cursor: onClick ? 'pointer' : 'default',
      background: sub ? 'var(--bg-subtle)' : 'transparent' }}>
      <div style={{ ...cell, paddingLeft: sub ? 28 : 8, fontWeight: bold ? 700 : 500,
        fontFamily: sub ? UI : MONO, fontSize: sub ? 12.5 : 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {onClick && <span style={{ color: 'var(--text-faint)', marginRight: 6 }}>{open ? '▾' : '▸'}</span>}
        {name}
      </div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO }}>{grp(v.total)}</div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, color: v.adfox ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
        {v.adfox ? grp(v.adfox) : '—'}
      </div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, color: 'var(--warning-text)' }}>{v.block_simb ? grp(v.block_simb) : '—'}</div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, color: 'var(--text-secondary)' }}>{pctTxt(v.block_simb, v.total)}</div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, fontWeight: 700 }}>{grp(v.base)}</div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO }}
        title={v.noCpm ? `без CPM площадки: ${grp(v.noCpm)} показов — в деньги не вошли` : (v.cpm ? `CPM ${grp(v.cpm)} ₽` : '')}>
        {rub(v.money)}{!!v.noCpm && <span style={{ color: 'var(--warning-text)' }}> *</span>}
      </div>
      <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, color: 'var(--warning-text)' }}>{rub(v.moneyK)}</div>
    </div>
  )
}

export default function TrafficStats() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [view, setView] = useState('rk')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState({ key: 'total', dir: 'desc' })
  const [open, setOpen] = useState(null)
  // Период: '' — текущие РК (накопительно), 'ГГГГ-ММ' — РК сделок этого месяца.
  const [period, setPeriod] = useState('')
  // Учитывать ли Adfox в общей, базе и доле «Block SIMB» (владелец 03.10.2026). Сам «Block SIMB»
  // Adfox не касается ни в каком режиме — меняется только то, с чем её сравнивают.
  const [withAdfox, setWithAdfox] = useState(true)
  useEffect(() => {
    try { const v = localStorage.getItem('traffic_stats_adfox'); if (v !== null) setWithAdfox(v === '1') } catch { /* нет хранилища */ }
  }, [])
  const toggleAdfox = (v) => {
    setWithAdfox(v)
    try { localStorage.setItem('traffic_stats_adfox', v ? '1' : '0') } catch { /* нет хранилища */ }
  }

  const load = useCallback(async () => {
    try {
      setData((await api.get('/traffic-stats', { ...auth(), params: period ? { period } : {} })).data)
      setErr('')
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить статистику') }
  }, [period])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const rows = useMemo(() => {
    const all = (data?.rows || []).map(r => {
      const adfox = withAdfox ? r.adfox : 0
      const total = r.dsp + adfox
      const k = (r.cpm || 0) / 1000
      return { ...r, adfox, total, base: total - r.block_simb, money: total * k, moneyK: r.block_simb * k,
        noCpm: r.cpm ? 0 : total }
    })
    const s = q.trim().toLowerCase()
    return s ? all.filter(r => r.deal.toLowerCase().includes(s) || (r.publisher || '').toLowerCase().includes(s)) : all
  }, [data, q, withAdfox])

  const sorter = (a, b) => {
    const d = sort.dir === 'asc' ? 1 : -1
    if (sort.key === 'name') return d * String(a.name).localeCompare(String(b.name), 'ru')
    if (sort.key === 'share') return d * (pct(a.block_simb, a.total) - pct(b.block_simb, b.total))
    return d * ((a[sort.key] || 0) - (b[sort.key] || 0))
  }
  const byRk = useMemo(() => group(rows, 'campaign_id', 'deal').sort(sorter), [rows, sort]) // eslint-disable-line react-hooks/exhaustive-deps
  const byPub = useMemo(() => group(rows, 'publisher_id', 'publisher').sort(sorter), [rows, sort]) // eslint-disable-line react-hooks/exhaustive-deps
  const tot = useMemo(() => sum(rows), [rows])
  const clickSort = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))

  const KPI = [
    { label: period ? `РК ${period.split('-').reverse().join('.')}` : 'Текущих РК', value: grp(new Set(rows.map(r => r.campaign_id)).size) },
    { label: 'Общая', value: grp(tot.total), hint: tot.adfox ? `в т.ч. Adfox ${grp(tot.adfox)}` : '' },
    { label: 'Block SIMB', value: grp(tot.block_simb), color: 'var(--warning-text)' },
    { label: 'Доля Block SIMB', value: pctTxt(tot.block_simb, tot.total) },
    { label: 'База', value: grp(tot.base) },
    { label: '₽ общая', value: rub(tot.money), hint: 'показы × CPM площадки по договору, до НДС' },
    { label: '₽ Block SIMB', value: rub(tot.moneyK), color: 'var(--warning-text)' },
  ]

  const list = view === 'rk' ? byRk : byPub
  const childName = view === 'rk' ? (r) => r.publisher : (r) => r.deal

  // Матрица: строки — РК, столбцы — площадки; в клетке база, общая и Block SIMB — в подсказке.
  const pubCols = byPub
  const cellOf = useMemo(() => {
    const m = {}
    rows.forEach(r => { m[`${r.campaign_id}|${r.publisher_id}`] = r })
    return m
  }, [rows])

  return (
    <>
      <Head><title>Статистика · Трафики | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '18px 24px 60px', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>Статистика</h1>
          <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
            {period ? 'РК сделок месяца' : 'текущие РК'}, накопительно · база = общая − Block SIMB
            {data?.block_simb_day ? ` · Block SIMB снят по ${String(data.block_simb_day).split('-').reverse().join('.')}` : ' · Block SIMB ещё не снимался'}
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <select style={{ ...inp, cursor: 'pointer' }} value={period} onChange={e => { setPeriod(e.target.value); setOpen(null) }}>
              <option value="">Текущие РК</option>
              {(data?.months || []).map(m => (
                <option key={m} value={m}>{m.split('-').reverse().join('.')}</option>
              ))}
            </select>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text-secondary)', cursor: 'pointer' }}
              title="Включено — показы Adfox входят в общую, базу и в долю Block SIMB. Сам Block SIMB Adfox не касается.">
              <input type="checkbox" checked={withAdfox} onChange={e => toggleAdfox(e.target.checked)} />
              учитывать Adfox
            </label>
            <input style={{ ...inp, minWidth: 220 }} placeholder="код РК или площадка" value={q}
              onChange={e => setQ(e.target.value)} />
            {VIEWS.map(([k, l]) => (
              <button key={k} style={btnSm(view === k)} onClick={() => { setView(k); setOpen(null) }}>{l}</button>
            ))}
          </span>
        </div>

        {!!err && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--danger)' }}>{err}</div>}
        <div style={{ marginBottom: 14 }}><KpiRow items={KPI} /></div>

        {!data && !err && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>загрузка…</div>}

        {!!data && view !== 'matrix' && (
          <div style={{ ...card, padding: '14px 10px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID }}>
              {COLS.map(c => (
                <SortHead key={c.key} label={c.key === 'name' ? (view === 'rk' ? 'РК' : 'Площадка') : c.label}
                  right={c.right} active={sort.key === c.key} dir={sort.dir} onClick={() => clickSort(c.key)} />
              ))}
            </div>
            {!list.length && <div style={{ padding: 16, color: 'var(--text-faint)', fontSize: 13 }}>Нет данных по текущим РК</div>}
            {list.map(g => (
              <Fragment key={g.id ?? 'none'}>
                <Row name={g.name} v={g} open={open === g.id} onClick={() => setOpen(o => (o === g.id ? null : g.id))} />
                {open === g.id && [...g.rows].sort((a, b) => b.total - a.total).map(r => (
                  <Row key={`${r.campaign_id}-${r.publisher_id}`} name={childName(r)} v={r} sub />
                ))}
              </Fragment>
            ))}
            {!!list.length && <Row name="Итого" v={tot} bold />}
          </div>
        )}

        {!!data && view === 'matrix' && (
          <div style={{ ...card, padding: 10, overflow: 'auto', maxHeight: '75vh' }}>
            <table style={{ borderCollapse: 'separate', borderSpacing: 0, fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ position: 'sticky', left: 0, top: 0, zIndex: 2, background: 'var(--bg-card)', padding: '6px 10px', textAlign: 'left', fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>РК \ площадка</th>
                  {pubCols.map(p => (
                    <th key={p.id ?? 'none'} title={`общая ${grp(p.total)} · Block SIMB ${grp(p.block_simb)} (${pctTxt(p.block_simb, p.total)})`}
                      style={{ position: 'sticky', top: 0, zIndex: 1, background: 'var(--bg-card)', padding: '6px 8px', fontWeight: 600, whiteSpace: 'nowrap', textAlign: 'right' }}>
                      {p.name}
                    </th>
                  ))}
                  <th style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', padding: '6px 8px', textAlign: 'right' }}>Итого база</th>
                  <th style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', padding: '6px 8px', textAlign: 'right' }}>Доля Block SIMB</th>
                </tr>
              </thead>
              <tbody>
                {byRk.map(rk => (
                  <tr key={rk.id}>
                    <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', padding: '5px 10px', fontFamily: MONO, fontWeight: 600, borderTop: '1px solid var(--border-row)' }}>{rk.name}</td>
                    {pubCols.map(p => {
                      const c = cellOf[`${rk.id}|${p.id}`]
                      return (
                        <td key={p.id ?? 'none'} title={c ? `общая ${grp(c.total)} · Block SIMB ${grp(c.block_simb)} (${pctTxt(c.block_simb, c.total)})${c.adfox ? ` · Adfox ${grp(c.adfox)}` : ''}` : ''}
                          style={{ padding: '5px 8px', textAlign: 'right', fontFamily: MONO, borderTop: '1px solid var(--border-row)', color: c ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                          {c ? grp(c.base) : '·'}
                        </td>
                      )
                    })}
                    <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: MONO, fontWeight: 700, borderTop: '1px solid var(--border-row)' }}>{grp(rk.base)}</td>
                    <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: MONO, borderTop: '1px solid var(--border-row)' }}>{pctTxt(rk.block_simb, rk.total)}</td>
                  </tr>
                ))}
                <tr>
                  <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', padding: '6px 10px', fontWeight: 700, borderTop: '2px solid var(--border-card)' }}>Итого база</td>
                  {pubCols.map(p => (
                    <td key={p.id ?? 'none'} style={{ padding: '6px 8px', textAlign: 'right', fontFamily: MONO, fontWeight: 700, borderTop: '2px solid var(--border-card)' }}>{grp(p.base)}</td>
                  ))}
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: MONO, fontWeight: 800, borderTop: '2px solid var(--border-card)' }}>{grp(tot.base)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: MONO, borderTop: '2px solid var(--border-card)' }}>{pctTxt(tot.block_simb, tot.total)}</td>
                </tr>
                <tr>
                  <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', padding: '4px 10px', color: 'var(--text-muted)' }}>Доля Block SIMB</td>
                  {pubCols.map(p => (
                    <td key={p.id ?? 'none'} style={{ padding: '4px 8px', textAlign: 'right', fontFamily: MONO, color: 'var(--text-muted)' }}>{pctTxt(p.block_simb, p.total)}</td>
                  ))}
                  <td /><td />
                </tr>
                {[['₽ общая', 'money', 'var(--text-primary)'], ['₽ Block SIMB', 'moneyK', 'var(--warning-text)']].map(([l, k, c]) => (
                  <tr key={k}>
                    <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', padding: '4px 10px', fontWeight: 600, color: c }}>{l}</td>
                    {pubCols.map(p => (
                      <td key={p.id ?? 'none'} style={{ padding: '4px 8px', textAlign: 'right', fontFamily: MONO, color: c }}>{rub(p[k])}</td>
                    ))}
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: MONO, fontWeight: 700, color: c }}>{rub(tot[k])}</td>
                    <td />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
