import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { MONO, UI, card, CAP } from '@/components/salesTableKit'
import MonthPicker from '@/components/MonthPicker'
import ApprovalsMatrix, { TONE, short, totalsOf } from '@/components/publishers/ApprovalsMatrix'
import StuckView from '@/components/publishers/StuckView'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { todayMsk } from '@/lib/dates'

// Паблишеры → «Согласования»: матрица площадка × РК месяца (владелец 29.09.2026).
// Две вкладки на одних данных: светофор согласования и план площадок (показы и план
// себестоимости по закупочному CPM из реестра). Третья — «Подвисшие» (03.10.2026): свой
// список без периода, components/publishers/StuckView. Только чтение, право dir_publishers_approvals.
// Мобильной версии нет намеренно (решение владельца): широкая матрица на телефоне не читается.
//
// Раскладка — хендофф docs/матрица сайтов.zip: страница не скроллится, матрица занимает
// всю оставшуюся высоту, скролл только внутри неё. Период — календарик со стрелками
// (просьба владельца 29.09), а не ряд кнопок-месяцев макета.

const thisMonth = () => todayMsk().slice(0, 7)
const PROBLEM = ['late', 'refused', 'rework', 'unsent']

const chipBtn = (on) => ({ height: 30, padding: '0 11px', borderRadius: 9, cursor: 'pointer', whiteSpace: 'nowrap',
  fontFamily: UI, fontSize: 12, fontWeight: on ? 700 : 600, border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent)' : 'var(--text-secondary)' })
const segBtn = (on) => ({ ...chipBtn(on), height: 30, border: 'none', borderRadius: 9, padding: '0 13px', fontSize: 13,
  background: on ? 'var(--accent-tint)' : 'transparent' })
const sep = <span style={{ width: 1, height: 22, background: 'var(--border-inner)' }} />

export default function PublisherApprovals() {
  const router = useRouter()
  const [month, setMonth] = useState(thisMonth())
  const [service, setService] = useState('')
  const [view, setView] = useState('appr')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [onlyProblems, setOnlyProblems] = useState(false)
  const [allPubs, setAllPubs] = useState(false)
  const [pend, setPend] = useState(false)
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    let p = {}
    try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch { p = {} }
    if (!can(p, 'dir_publishers_approvals', 'view')) {
      router.push(firstAllowedHref(p, localStorage.getItem('is_admin') === '1')); return
    }
    setReady(true)
  }, [router])

  const load = useCallback(() => {
    const qs = new URLSearchParams({ month, ...(service ? { service_id: service } : {}) })
    api.get(`/publisher-approvals/matrix?${qs}`, auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить матрицу'))
  }, [month, service])
  useEffect(() => { if (ready && view !== 'stuck') load() }, [ready, load, view])
  useRefreshOnReturn(load)

  const cell = useMemo(() => Object.fromEntries((data?.cells || [])
    .map(c => [`${c.deal_id}:${c.publisher_id}`, c])), [data])

  const onSort = (key) => setSort(s => (s.key === key
    ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' }))

  const { deals, pubs } = useMemo(() => {
    let ds = data?.deals || []
    let ps = data?.publishers || []
    const has = (d, p) => !!cell[`${d.id}:${p.id}`]
    const s = q.trim().toLowerCase()
    if (s) {
      const byDeal = ds.filter(d => `${d.brand} ${d.advertiser || ''} ${d.code}`.toLowerCase().includes(s))
      if (byDeal.length) ds = byDeal
      else ps = ps.filter(p => p.name.toLowerCase().includes(s))
    }
    const bad = (d, p) => { const c = cell[`${d.id}:${p.id}`]; return c && PROBLEM.includes(c.tone) }
    if (onlyProblems) {
      ps = ps.filter(p => ds.some(d => bad(d, p)))
      ds = ds.filter(d => ps.some(p => bad(d, p)))
    }
    // «Все площадки» оставляет и пустые строки; колонка без видимых ячеек не рисуется никогда.
    if (!allPubs || onlyProblems) ps = ps.filter(p => ds.some(d => has(d, p)))
    ds = ds.filter(d => ps.some(p => has(d, p)))
    const k = sort.dir === 'asc' ? 1 : -1
    const total = p => { const t = totalsOf(ds.map(d => cell[`${d.id}:${p.id}`]), pend); return view === 'plan' ? t.s : t.g / (t.n || 1) }
    ps = [...ps].sort((a, b) => (sort.key === 'name' ? a.name.localeCompare(b.name) : total(a) - total(b)) * k)
    return { deals: ds, pubs: ps }
  }, [data, q, onlyProblems, allPubs, cell, sort, view, pend])

  const kpis = useMemo(() => {
    const cells = deals.flatMap(d => pubs.map(p => cell[`${d.id}:${p.id}`])).filter(Boolean)
    const n = Object.fromEntries(Object.keys(TONE).map(k => [k, 0]))
    cells.forEach(c => { n[c.tone]++ })
    const t = totalsOf(cells, pend)
    if (view === 'plan') {
      const waiting = cells.filter(c => c.tone === 'waiting' || c.tone === 'late')
      const ws = waiting.reduce((a, c) => a + (c.plan_show || 0), 0)
      const wm = waiting.reduce((a, c) => a + (c.plan_cost || 0), 0)
      const noCpm = [...new Set(cells.filter(c => c.plan_show && c.plan_cost == null)
        .map(c => (data.publishers.find(p => p.id === c.publisher_id) || {}).name))]
      return [
        ['РК в периоде', deals.length],
        [pend ? 'План показов' : 'План показов, согласовано', short(t.s)],
        [pend ? 'План себестоимости' : 'План себестоимости, согласовано', `${short(t.m)} ₽`],
        ['Ещё ждёт ответа', `${short(ws)} · ${short(wm)} ₽`],
        ...(noCpm.length ? [['Нет CPM в реестре', noCpm.join(', '), 'var(--danger-fg)', true]] : []),
      ]
    }
    return [
      ['РК в периоде', deals.length], ['Пар площадка×РК', t.n],
      ['Согласовано', n.agreed, TONE.agreed.kpi], ['Ждём ответа', n.waiting, TONE.waiting.kpi],
      [`Ждём > ${data?.late_workdays ?? 3} дн.`, n.late, TONE.late.kpi],
      ['На доработке', n.rework, TONE.rework.kpi],
      ['Отказ', n.refused, TONE.refused.kpi], ['Не отправлено', n.unsent, TONE.unsent.kpi],
    ]
  }, [deals, pubs, cell, view, pend, data])

  if (!ready) return null
  return (
    <>
      <Head><title>Согласования · Паблишеры | SIMB-AD ERP</title></Head>
      <Navbar active="publishers" />
      <div style={{ height: 'calc(100vh - var(--navbar-h))', overflow: 'hidden', background: 'var(--bg-canvas)', fontFamily: UI, padding: '22px 28px 18px', boxSizing: 'border-box' }}>
        <div style={{ maxWidth: 1600, height: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', flex: '0 0 auto' }}>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-.025em' }}>Паблишеры</h1>
            <span style={{ ...CAP, marginBottom: 0, paddingTop: 6 }}>{view === 'stuck' ? 'что подвисло на площадках' : 'матрица согласований · площадка × РК'}</span>
            {/* Переключатель вида — справа в шапке, в виде плашки вкладок (владелец 29.09). */}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 12 }}>
              {view === 'plan' && (
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input type="checkbox" checked={pend} onChange={e => setPend(e.target.checked)} /> учитывать ожидающие ответа
                </label>
              )}
              <span style={{ display: 'flex', gap: 4, padding: 6, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, boxShadow: 'var(--shadow-card)' }}>
                <button style={segBtn(view === 'appr')} onClick={() => setView('appr')}>Согласования</button>
                <button style={segBtn(view === 'plan')} onClick={() => setView('plan')}>План площадок</button>
                <button style={segBtn(view === 'stuck')} onClick={() => setView('stuck')}>Подвисшие</button>
              </span>
            </span>
          </div>

          {view === 'stuck' ? <StuckView /> : (<>
          <div style={{ display: 'flex', flex: '0 0 auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)', padding: '4px 8px' }}>
            {kpis.map(([label, value, color, small], i) => (
              <div key={label} style={{ flex: 1, minWidth: 0, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 7, borderRight: i < kpis.length - 1 ? '1px solid var(--border-inner)' : 'none' }}>
                <span style={{ ...CAP, marginBottom: 0 }}>{label}</span>
                <b style={small
                  ? { fontSize: 12.5, fontWeight: 600, color, lineHeight: 1.35 }
                  : { fontFamily: MONO, fontSize: 26, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1, color: color || 'var(--text-primary)' }}>{value}</b>
              </div>
            ))}
          </div>

          <div style={{ ...card, flex: '0 0 auto', padding: '14px 18px', borderRadius: 18 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ ...CAP, marginBottom: 0 }}>Период</span>
              <MonthPicker value={month} onChange={m => { setMonth(m); setService('') }} marked={data?.months || []} />
              {sep}
              <span style={{ ...CAP, marginBottom: 0 }}>Услуга</span>
              <button style={chipBtn(!service)} onClick={() => setService('')}>Все</button>
              {(data?.services || []).map(s => (
                <button key={s.id} style={chipBtn(String(service) === String(s.id))} onClick={() => setService(String(s.id))}>{s.name}</button>
              ))}
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                <input placeholder="Площадка или бренд…" value={q} onChange={e => setQ(e.target.value)}
                  style={{ height: 32, padding: '0 11px', border: '1px solid var(--border-card)', borderRadius: 10, background: 'var(--bg-subtle)', fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)', width: 220, outline: 'none', boxSizing: 'border-box' }} />
                <button style={chipBtn(onlyProblems)} onClick={() => setOnlyProblems(v => !v)} title="Просрочено, отказ или комплект не отправлен">Только проблемные</button>
                <button style={chipBtn(allPubs)} onClick={() => setAllPubs(v => !v)} title="Показать и площадки без РК в этом месяце">Все площадки</button>
              </span>
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', paddingTop: 10, marginTop: 10, borderTop: '1px solid var(--border-row)' }}>
              <span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                показано площадок {pubs.length} · РК {deals.length} из {data?.deals.length ?? 0}</span>
              {view === 'appr' && Object.entries(TONE).map(([k, t]) => (
                <span key={k} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', color: 'var(--text-secondary)', fontSize: 11.5 }}>
                  <i style={{ width: 10, height: 10, borderRadius: 3, background: t.bg, boxShadow: `inset 0 0 0 1px ${t.bd}` }} />
                  {k === 'late' ? `ждём > ${data?.late_workdays ?? 3} раб. дн.` : t.label}
                </span>
              ))}
              {view === 'plan' && !!service && data && !data.plan_by_service && (
                <span style={{ fontSize: 12, color: 'var(--warning-text)' }}>
                  План размещения ведётся на площадку в РК целиком и по услугам не делится — показан план по всей РК.</span>
              )}
            </div>
          </div>

          <div style={{ flex: '1 1 auto', minHeight: 240, overflow: 'auto', border: '1px solid var(--border-card)', borderRadius: 18, background: 'var(--bg-card)', boxShadow: 'var(--shadow-card)' }}>
            {!!err && <div style={{ padding: 20, color: 'var(--danger-fg)' }}>{err}</div>}
            {!data && !err && <div style={{ padding: 30, color: 'var(--text-muted)' }}>Загрузка…</div>}
            {data && !deals.length && (
              <div style={{ padding: 30, color: 'var(--text-muted)', textAlign: 'center' }}>
                {data.deals.length ? 'Под фильтр ничего не попало' : 'В этом месяце нет РК со «Сбором запуска»'}
              </div>
            )}
            {!!deals.length && (
              <ApprovalsMatrix view={view} deals={deals} pubs={pubs} cell={cell} pend={pend}
                sort={sort} onSort={onSort} lateDays={`${data.late_workdays} раб. дн.`} />
            )}
          </div>

          <div style={{ flex: '0 0 auto', color: 'var(--text-muted)', fontSize: 11.5, lineHeight: 1.5, padding: '0 4px' }}>
            Колонка — сделка с финансовым периодом в выбранном месяце; при «Все» услуги у пары площадка×РК сводятся в одну ячейку
            по худшему состоянию; ячейка — состояние получателя «Сбора запуска», цифры — согласовано / отправлено комплектов;
            себестоимость — план показов × закупочный CPM площадки / 1000, до НДС. Клик по ячейке открывает креативы сделки.
          </div>
          </>)}
        </div>
      </div>
    </>
  )
}
