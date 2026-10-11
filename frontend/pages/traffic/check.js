// «Трафики → Проверка РК» (владелец 11.10.2026): светофоры заведения, сбора и раскладки по каждой
// идущей РК. Строки считает ночной прогон backend app/ad/rk_check.py; экран читает записанное.
// Право — traffic_check (view — экран, edit — «перепроверить сейчас»). Только десктоп.
// Это же скелет будущих алертов: «с какого дня» держится красное — уже в ответе.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import { MONO, UI, card, inp, th, td, btn, primaryBtn } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { getPermissions, can } from '@/lib/auth'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const ru = (d) => (d ? String(d).split('-').reverse().join('.') : '—')

// Цвет светофора — переменные темы, не хексы. skip — серый: «проверить нечем», а не «в порядке».
const TONE = {
  red: { dot: 'var(--expense)', bg: 'var(--danger-tint)', fg: 'var(--danger-fg)', label: 'красный' },
  yellow: { dot: 'var(--warning-text)', bg: 'var(--warning-tint)', fg: 'var(--warning-text)', label: 'жёлтый' },
  green: { dot: 'var(--income)', bg: 'var(--income-tint)', fg: 'var(--income-fg)', label: 'в порядке' },
  skip: { dot: 'var(--text-faint)', bg: 'var(--bg-subtle)', fg: 'var(--text-muted)', label: 'нечем проверить' },
}
const FILTERS = [['red', 'Красные'], ['yellow', 'Жёлтые'], ['all', 'Все']]

const Dot = ({ level, size = 12 }) => (
  <span title={TONE[level]?.label} style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%',
    background: TONE[level]?.dot, flexShrink: 0 }} />
)

function Kpi({ label, value, tone, active, onClick }) {
  return (
    <button type="button" onClick={onClick} style={{ ...card, padding: '12px 18px', minWidth: 130, textAlign: 'left', cursor: 'pointer',
      outline: active ? '2px solid var(--accent)' : 'none', fontFamily: UI }}>
      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{label}</div>
      <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, color: tone || 'var(--text-primary)' }}>{value}</div>
    </button>
  )
}

function CheckLine({ c }) {
  const t = TONE[c.level]
  return (
    <div style={{ padding: '7px 0', borderBottom: '1px solid var(--border-row)', opacity: c.common ? 0.6 : 1 }}
      title={c.common ? 'Общая причина у нескольких РК сразу — на уровень РК не влияет' : undefined}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <Dot level={c.level} />
        <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', minWidth: 230 }}>{c.title}</span>
        <span style={{ fontSize: 12.5, color: t.fg, flex: 1 }}>{c.message}</span>
        {!!c.common && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>общая причина</span>}
        {!!c.since && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>с {ru(c.since)}</span>}
      </div>
      {c.placements.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, paddingLeft: 20, marginTop: 3, fontSize: 12, color: 'var(--text-secondary)' }}>
          <Dot level={p.level} size={8} />
          <span style={{ fontFamily: MONO, minWidth: 190 }}>{p.name || `площадка ${p.placement_id}`}</span>
          <span>{p.message}</span>
        </div>
      ))}
    </div>
  )
}

function CampRow({ c, groups, open, onToggle }) {
  const pace = c.checks.find(x => x.key === 'pace')
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer' }}>
        <td style={{ ...td, fontFamily: MONO, fontWeight: 700 }}>{open ? '▾ ' : '▸ '}{c.code}</td>
        <td style={{ ...td, maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.title}>{c.title}</td>
        <td style={{ ...td, color: 'var(--text-secondary)' }}>{c.status}</td>
        <td style={{ ...td, fontFamily: MONO, whiteSpace: 'nowrap' }}>{ru(c.date_start)}–{ru(c.date_end)}</td>
        {groups.map(g => (
          <td key={g.key} style={{ ...td, textAlign: 'center' }}><Dot level={c.groups[g.key]} size={14} /></td>
        ))}
        <td style={{ ...td, color: 'var(--text-muted)', fontSize: 12 }}>
          {c.checks.filter(x => x.level === 'red').length || '—'} / {c.checks.filter(x => x.level === 'yellow').length || '—'}
          {!!pace?.value?.ratio && ` · темп ${Math.round(pace.value.ratio * 100)} %`}
        </td>
      </tr>
      {open && (
        <tr style={{ background: 'var(--bg-subtle)' }}>
          <td style={{ ...td, paddingLeft: 28 }} colSpan={5 + groups.length}>
            {c.checks.map(x => <CheckLine key={x.key} c={x} />)}
          </td>
        </tr>
      )}
    </>
  )
}

export default function RkCheckPage() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('red')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [canEdit, setCanEdit] = useState(false)

  useEffect(() => { setCanEdit(can(getPermissions(), 'traffic_check', 'edit')) }, [])

  const load = useCallback(async () => {
    try {
      const r = await api.get('/rk-check', auth())
      setData(r.data)
      setErr('')
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить проверки РК') }
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const rerun = async () => {
    setBusy(true)
    try {
      await api.post('/rk-check/run', {}, auth())
      await load()
    } catch (e) { setErr(e?.response?.data?.detail || 'Перепроверка не удалась') }
    setBusy(false)
  }

  const rows = useMemo(() => {
    const list = data?.campaigns || []
    const s = q.trim().toLowerCase()
    return list.filter(c => {
      if (filter === 'red' && c.worst !== 'red') return false
      if (filter === 'yellow' && c.worst !== 'yellow') return false
      return !s || `${c.code} ${c.title}`.toLowerCase().includes(s)
    })
  }, [data, filter, q])

  const sum = data?.summary || {}
  const groups = data?.groups || []
  return (
    <>
      <Head><title>Проверка РК · Трафики | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '18px 24px 60px', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>Проверка РК</h1>
          <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
            {data?.run_date ? `прогон за ${ru(data.run_date)} · история ${data.keep_months} мес.` : 'прогонов ещё не было'}
          </span>
          {canEdit && (
            <button type="button" disabled={busy} onClick={rerun} style={{ ...primaryBtn, marginLeft: 'auto', opacity: busy ? 0.6 : 1 }}>
              {busy ? 'Проверяю…' : 'Перепроверить сейчас'}
            </button>
          )}
        </div>
        {!!err && <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--expense)' }}>{err}</div>}

        {!!data?.common?.length && (
          <div style={{ ...card, padding: '10px 14px', marginBottom: 12, fontSize: 12.5, color: 'var(--text-secondary)' }}>
            Общие причины (одна поломка у многих РК, уровень РК не поднимают):{' '}
            {data.common.map(x => `${x.title} — ${x.campaigns} РК`).join(' · ')}
          </div>
        )}
        <div style={{ display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <Kpi label="С красным" value={sum.red ?? '—'} tone="var(--expense)" active={filter === 'red'} onClick={() => setFilter('red')} />
          <Kpi label="С жёлтым" value={sum.yellow ?? '—'} tone="var(--warning-text)" active={filter === 'yellow'} onClick={() => setFilter('yellow')} />
          <Kpi label="В порядке" value={sum.green ?? '—'} tone="var(--income)" active={filter === 'all'} onClick={() => setFilter('all')} />
        </div>

        <div style={{ ...card, padding: 16 }}>
          <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            {FILTERS.map(([k, label]) => (
              <button key={k} type="button" onClick={() => setFilter(k)}
                style={{ ...btn(filter === k), padding: '6px 13px' }}>{label}</button>
            ))}
            <input style={{ ...inp, minWidth: 260 }} placeholder="Код сделки или название" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={th}>Сделка</th>
                <th style={th}>Название</th>
                <th style={th}>Статус РК</th>
                <th style={th}>Период</th>
                {groups.map(g => <th key={g.key} style={{ ...th, textAlign: 'center' }}>{g.title}</th>)}
                <th style={th} title="красных / жёлтых проверок">Красных / жёлтых</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <CampRow key={c.id} c={c} groups={groups} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} />
              ))}
              {!rows.length && (
                <tr><td style={{ ...td, color: 'var(--text-muted)' }} colSpan={5 + groups.length}>
                  {data?.run_date ? 'Нет РК под этот фильтр' : 'Нажмите «Перепроверить сейчас» или дождитесь ночного прогона'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
