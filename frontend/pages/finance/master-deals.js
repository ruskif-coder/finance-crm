/**
 * Реестр мастер-сделок (Финансы, 19.10.2026) — по хендоффу «мастер и шапка» (docs/мастер и шапка.zip, макет «реестр»).
 * Пакеты закрытия месяца: статус, что нужно сейчас, действие прямо из строки (шаги-отметки), договор, ДС, суммы, прибыль.
 * Право `master_deals` (нет / просмотр / редактирование); прибыль — только с `master_deals_finance` (сервер без него не отдаёт).
 * Правила шагов — на сервере (`master_deal/status.py`, `issue.py`); строка лишь зовёт ту же ручку, что кнопка в карточке.
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { pageAccess } from '@/lib/pageGuard'
import { can, getPermissions } from '@/lib/auth'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fmtDate, fmtDateTimeShort } from '@/lib/dates'
import { monthLabel, pctComma, rub0 } from '@/lib/salesFormat'
import { plural } from '@/components/master/kit'
import { MasterStatusPill, TODO_DOT } from '@/lib/masterStatus'
import { NoAccessScreen, PortalPopover, MONO, UI } from '@/components/salesTableKit'
import ActionCell from '@/components/master/registry/ActionCell'
import Chips from '@/components/master/registry/Chips'
import ChannelChip from '@/components/master/registry/ChannelChip'
import ExpandedRow from '@/components/master/registry/ExpandedRow'
import StatusBar from '@/components/master/registry/StatusBar'
import { CAPS, KEEP } from '@/components/master/registry/kit'

// 15 колонок хендоффа v2 (21.10.2026): ширины фиксированных — как в макете; текстовые — без жёсткого минимума (`minmax(0,…)`, доли — из
// макета): делят свободное место и обрезаются многоточием, полный текст в title. Окно владельца ≈ 2000 px — минимумы макета (200 px)
// туда не влезали (урок 19.10); прокрутка — лишь на окне уже 1800 px.
const COLS = '84px 80px 150px minmax(0,1.5fr) 164px 110px minmax(0,1.3fr) minmax(0,0.7fr) minmax(0,1fr) minmax(0,1.15fr) 140px 56px 120px 120px 142px'
export default function MasterDealsRegistry() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [month, setMonth] = useState('')
  const [monthOpen, setMonthOpen] = useState(false)
  const [tab, setTab] = useState(KEEP)
  const [asking, setAsking] = useState(null)
  const [expanded, setExpanded] = useState(null)       // один расхлоп одновременно
  const [moved, setMoved] = useState({})            // код → статус, в который строка только что ушла (держим 3 с)
  const [rights, setRights] = useState({ edit: false, fin: false })
  useEffect(() => {
    setMounted(true)
    const p = getPermissions()
    setRights({ edit: can(p, 'master_deals', 'edit'), fin: can(p, 'master_deals_finance', 'view') })
  }, [])
  const access = pageAccess(router.pathname, mounted)

  const load = useCallback(async () => {
    setErr('')
    try { setData((await api.get('/master-deals/registry/list', auth())).data) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить мастер-сделки'); setData({ rows: [], statuses: [], hidden: [] }) }
  }, [])
  useEffect(() => { if (access === 'ok') load() }, [access, load])
  useRefreshOnReturn(load, { enabled: access === 'ok' && !asking })
  useEffect(() => {
    if (!monthOpen) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setMonthOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [monthOpen])
  useEffect(() => {
    if (!asking) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setAsking(null) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [asking])

  const rows = useMemo(() => data?.rows || [], [data])
  const hidden = useMemo(() => new Set(data?.hidden || []), [data])
  const byMonth = useMemo(() => rows.filter(r => !month || r.period === month), [rows, month])
  const bySearch = useMemo(() => {
    const s = q.trim().toLowerCase()
    return byMonth.filter(r => !s || [r.code, r.contract?.number, r.counterparty, r.payer, ...r.advertisers, ...r.brands].join(' ').toLowerCase().includes(s))
  }, [byMonth, q])
  const inTab = useCallback((r) => (tab === KEEP ? !hidden.has(r.status) : r.status === tab), [tab, hidden])
  const shown = useMemo(() => bySearch.filter(r => inTab(r) || moved[r.code]), [bySearch, inTab, moved])
  const tabs = useMemo(() => [KEEP, ...(data?.statuses || [])].map(key => ({
    key, count: bySearch.filter(r => (key === KEEP ? !hidden.has(r.status) : r.status === key)).length })), [data, bySearch, hidden])
  const months = useMemo(() => [...new Set(rows.map(r => r.period))].sort().reverse(), [rows])

  const done = useCallback(async (r) => {
    setAsking(null)
    const before = r.status
    const fresh = (await api.get('/master-deals/registry/list', auth())).data
    setData(fresh)
    const now = fresh.rows.find(x => x.code === r.code)
    if (now && now.status !== before) {
      setMoved(m => ({ ...m, [r.code]: now.status_label || now.status }))
      setTimeout(() => setMoved(m => { const n = { ...m }; delete n[r.code]; return n }), 3000)
    }
  }, [])

  const withSum = shown.filter(r => r.net != null)
  const tNet = withSum.reduce((a, r) => a + r.net, 0)
  const tGross = withSum.reduce((a, r) => a + (r.gross || 0), 0)
  const withProfit = withSum.filter(r => r.efficiency && r.efficiency.profit != null)
  const tProfit = withProfit.reduce((a, r) => a + r.efficiency.profit, 0)
  const tRev = withProfit.reduce((a, r) => a + r.efficiency.revenue, 0)
  const noSum = shown.length - withSum.length
  const filtered = !!q || !!month || tab !== KEEP
  const cols = rights.fin ? COLS : COLS.replace(/ 142px$/, '')

  const head = <><Head><title>Мастер-сделки · Финансы | SIMB-AD ERP</title></Head><Navbar active="master_deals" /></>
  if (access === 'denied') return <NoAccessScreen title="Мастер-сделки: нет доступа" what="Мастер-сделки" nav={head} />

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI, color: 'var(--text-primary)' }}>
      {head}
      <div style={{ maxWidth: 2500, margin: '0 auto', padding: '22px 28px 40px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ position: 'relative', zIndex: 20, display: 'flex', alignItems: 'center', gap: '12px 16px', flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 4, marginRight: 8 }}>
            <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em' }}>Мастер-сделки</span>
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>пакеты закрытия месяца: договор, сделки, ДС и УПД</span>
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, flex: '0 1 320px', minWidth: 220 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="1.9" strokeLinecap="round" aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" /></svg>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="код, договор, контрагент, бренд…"
              style={{ flex: '1 1 auto', minWidth: 0, border: 0, outline: 'none', background: 'transparent', fontSize: 13, fontFamily: UI, color: 'var(--text-primary)' }} />
          </span>
          <span data-pop-root style={{ position: 'relative', display: 'inline-flex' }}>
            <span onClick={() => setMonthOpen(o => !o)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 10, height: 36, padding: '0 12px', background: 'var(--bg-card)', border: `1px solid ${monthOpen ? 'var(--accent)' : 'var(--border-card)'}`, borderRadius: 10, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
              {month ? monthLabel(month) : 'все месяцы'}<span style={{ color: 'var(--text-faint)', fontSize: 10 }}>{monthOpen ? '▴' : '▾'}</span>
            </span>
            <PortalPopover open={monthOpen} minWidth={200} offset={6} style={{ boxShadow: 'var(--shadow-float)' }}>
              {[['', 'все месяцы', rows.length], ...months.map(k => [k, monthLabel(k), rows.filter(r => r.period === k).length])].map(([k, label, n]) => {
                const on = month === k
                return (
                  <span key={k || 'all'} onClick={() => { setMonth(k); setMonthOpen(false) }}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, height: 32, padding: '0 10px', borderRadius: 8, background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-primary)', fontSize: 12.5, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                    {label}<span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{n}</span>
                  </span>
                )
              })}
            </PortalPopover>
          </span>
          <StatusBar tabs={tabs} value={tab} onPick={setTab} />
        </div>
        {!!err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}

        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '6px 0 0' }}>
          <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 1800, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, alignItems: 'end', padding: '10px 20px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
                <span>Код</span><span>Канал</span><span>Статус</span><span>Что нужно сейчас</span><span>Действие</span><span>Месяц</span><span>Договор · контрагент</span><span>ДС</span>
                <span>Рекламодатели</span><span>Бренды</span><span>Кто собирает</span><span style={{ textAlign: 'right' }}>Сделок</span>
                <span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
                {rights.fin && <span title="Право «Эффективность мастер-сделок»" style={{ textAlign: 'right', color: 'var(--accent-fg)' }}>Прибыль · маржа</span>}
              </div>

              {data === null && <div style={{ padding: '40px 20px', textAlign: 'center', fontSize: 13, color: 'var(--text-faint)' }}>Загрузка…</div>}
              {data && !shown.length && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '56px 20px' }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-secondary)' }}>{rows.length ? 'Под фильтр ничего не попало' : 'Мастер-сделок пока нет'}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{filtered ? 'сбросьте поиск, месяц или статус' : 'пакет создаётся из карточки сделки — «В мастер-сделку»'}</span>
                </div>
              )}

              {shown.map(r => {
                const t = r.todo
                const arch = r.status === 'архив'
                const e = r.efficiency
                const leaving = !!moved[r.code] && !inTab(r)
                const party = r.payer && r.payer !== r.counterparty ? `${r.counterparty || '—'} · плательщик ${r.payer}` : (r.counterparty || '—')
                const isOpen = expanded === r.code
                const toggle = (ev) => { if (ev.target.closest('a,button,input,label,[data-noexp],[data-pop-root]')) return; setExpanded(isOpen ? null : r.code) }
                return (
                  <Fragment key={r.code}>
                  <div onClick={toggle} style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, alignItems: 'center', padding: '12px 20px', borderBottom: '1px solid var(--border-row)', minWidth: 0, cursor: 'pointer',
                    background: moved[r.code] ? 'var(--income-tint)' : isOpen ? 'var(--bg-subtle)' : 'transparent', opacity: leaving ? 0.7 : 1, transition: 'background-color 300ms ease, opacity 300ms ease' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <span aria-hidden style={{ fontSize: 9, color: 'var(--text-faint)', transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 160ms ease' }}>▸</span>
                      <Link href={`/accounts/master/${r.code}`} style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', color: 'var(--accent)' }}>{r.code}</Link>
                    </span>
                    <span style={{ display: 'inline-flex', minWidth: 0 }}><ChannelChip way={r.channel} /></span>
                    <span style={{ display: 'inline-flex', minWidth: 0 }}><MasterStatusPill status={r.status} label={r.status} /></span>
                    <span title={t ? `${t.text} — очередь: ${t.who}` : 'пакет закрыт'} style={{ display: 'flex', alignItems: 'flex-start', gap: 9, minWidth: 0 }}>
                      <span aria-hidden style={{ width: 8, height: 8, borderRadius: 2, background: t && !arch ? TODO_DOT[t.tone] : 'transparent', flex: '0 0 8px', marginTop: 5 }} />
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                        <span style={{ fontSize: 12.5, fontWeight: 600, lineHeight: 1.35, color: !t || arch ? 'var(--text-faint)' : t.tone === 'bad' ? 'var(--danger-fg)' : 'var(--text-primary)' }}>{t ? t.text : '—'}</span>
                        {!!t && <span style={{ ...CAPS, letterSpacing: '.06em', color: 'var(--text-faint)' }}>очередь: {t.who}</span>}
                      </span>
                    </span>
                    <ActionCell r={{ ...r, moved: moved[r.code] }} canEdit={rights.edit} open={asking === r.code}
                      onAsk={() => setAsking(a => (a === r.code ? null : r.code))} onClose={() => setAsking(null)} onDone={() => done(r)}
                      onExpand={() => setExpanded(r.code)} />
                    <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{monthLabel(r.period)}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        № {r.contract?.number || '—'}{r.contract?.date ? ` от ${fmtDate(r.contract.date)}` : ''}</span>
                      <span title={r.payer ? `Контрагент: ${r.counterparty || '—'}\nПлательщик: ${r.payer}` : (r.counterparty || '')}
                        style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{party}</span>
                    </span>
                    <span title={r.ds.join(', ')} style={{ fontFamily: MONO, fontSize: 11.5, color: r.ds.length ? 'var(--text-primary)' : 'var(--text-disabled)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.ds.length ? r.ds.join(', ') : '—'}</span>
                    <Chips list={r.advertisers} keep={2} max={120} />
                    <Chips list={r.brands} keep={3} max={96} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.built_by || '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{r.created_at ? fmtDateTimeShort(r.created_at) : ''}</span>
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{r.deals}</span>
                    <span title={r.net == null ? 'суммы появятся после раскладки на УПД' : 'сумма по комплектам УПД'}
                      style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap', color: r.net == null ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{r.net == null ? '—' : rub0(r.net)}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12.5, textAlign: 'right', whiteSpace: 'nowrap', color: r.gross == null ? 'var(--text-disabled)' : 'var(--text-secondary)' }}>{r.gross == null ? '—' : rub0(r.gross)}</span>
                    {rights.fin && (e && e.profit != null ? (
                      <span title={`Выручка ${rub0(e.revenue)} − СК ${rub0(e.sk_cost)} − себестоимость ${rub0(e.cost)}${e.estimated.length ? ' (оценка по CPM площадок)' : ''} · до НДС`}
                        style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, whiteSpace: 'nowrap' }}>
                        <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: e.margin_pct >= 60 ? 'var(--income-fg)' : e.margin_pct >= 45 ? 'var(--text-primary)' : 'var(--warning-fg)' }}>{rub0(e.profit)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-muted)' }}>маржа {e.margin_pct == null ? '—' : pctComma(e.margin_pct)}</span>
                      </span>
                    ) : (
                      <span title={r.net == null ? 'рентабельность появится после раскладки на УПД' : `нет себестоимости: ${(e?.missing_cost || []).join(', ')}`}
                        style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, whiteSpace: 'nowrap' }}>
                        <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--text-disabled)' }}>—</span>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-disabled)' }}>{r.net == null ? 'после раскладки' : 'нет себестоимости'}</span>
                      </span>
                    ))}
                  </div>
                  {isOpen && <ExpandedRow code={r.code} channel={r.channel} canEdit={rights.edit} onChanged={load} />}
                  </Fragment>
                )
              })}

              {shown.length > 1 && (
                <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, alignItems: 'center', padding: '13px 20px', background: 'var(--bg-subtle)', borderRadius: '0 0 18px 18px' }}>
                  <span style={{ gridColumn: 'span 11', fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                    Итого · {shown.length} {plural(shown.length, ['пакет', 'пакета', 'пакетов'])}
                    {!!noSum && <span style={{ marginLeft: 12, fontWeight: 400, textTransform: 'none', letterSpacing: 0, color: 'var(--text-faint)' }}>без {noSum} {plural(noSum, ['пакета', 'пакетов', 'пакетов'])} до раскладки</span>}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{shown.reduce((a, r) => a + r.deals, 0)}</span>
                  <span title="по пакетам с раскладкой на УПД" style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{rub0(tNet)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, color: 'var(--text-secondary)', textAlign: 'right', whiteSpace: 'nowrap' }}>{rub0(tGross)}</span>
                  {rights.fin && (
                    <span title="Итоговая рентабельность по пакетам с раскладкой и себестоимостью" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, whiteSpace: 'nowrap' }}>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--income-fg)' }}>{withProfit.length ? rub0(tProfit) : '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-muted)' }}>{tRev ? `маржа ${pctComma(tProfit / tRev * 100)}` : ''}</span>
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        <span style={{ display: 'flex', gap: 18, flexWrap: 'wrap', padding: '0 4px', fontSize: 11, color: 'var(--text-muted)' }}>
          {[['info', 'обычный шаг'], ['warn', 'что-то держит пакет'], ['bad', 'без правки данных дальше не пройдёт']].map(([k, l]) => (
            <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span aria-hidden style={{ width: 8, height: 8, borderRadius: 2, background: TODO_DOT[k] }} />{l}</span>
          ))}
        </span>
      </div>
    </div>
  )
}
