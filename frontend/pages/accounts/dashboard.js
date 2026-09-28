import { useState, useEffect, useMemo, Fragment, useCallback, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, card, sel, Pager } from '@/components/salesTableKit'
import { toItem } from '@/components/dashboard/NotificationsWidget'
import DealDetail from '@/components/sales/DealDetail'
import MoveDealDialog from '@/components/sales/MoveDealDialog'
import { SnoozeDialog, BookingConfirm, LaunchPrepDialog } from '@/components/accounts/QueueDialogs'
import { WideRow, CompactRow, NotifyModal, ladderCounts } from '@/components/accounts/dashboard/TopRow'
import EventsStrip from '@/components/accounts/dashboard/EventsStrip'
import QueueToolbar, { applyToolbar, pinOptions, emptyPins } from '@/components/accounts/dashboard/QueueToolbar'
import { QuickPins, ActionPins } from '@/components/accounts/dashboard/QueuePins'
import QueueRow, { QueueHead } from '@/components/accounts/dashboard/QueueRow'
import { inStage, defaultRank, compareRows } from '@/components/accounts/dashboard/ladder'
import api, { auth } from '@/lib/api'
import { dm } from '@/lib/salesFormat'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { calendarDate } from '@/lib/dates'
import { WidgetsToggle } from '@/components/traffic/dashboardKit'

// Дашборд аккаунта «Мои сделки» — макет «акки 3» (docs/акки 3.zip, план
// docs/ПЛАН_дашборд_аккаунта_v3.md, решения владельца 27–28.09.2026).
//
// Один список вместо групп по стадиям. Что показать в строке и какая у неё кнопка —
// считает сервер (app/sales/queue_state.py) теми же проверками, что карточка и диалог
// движения; срочность — той же функцией, что лента уведомлений (app/sales/urgency.py).
// Здесь только раскладка, фильтры и порядок строк — они не меняют смысл строки.

// Вид верхнего ряда помнится для КАЖДОГО пользователя (владелец 28.09.2026): ключ несёт
// логин из токена, иначе на общем компьютере второй человек получал бы чужой выбор.
const compactKey = () => {
  try {
    const t = localStorage.getItem('token') || ''
    const sub = JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub
    return `accDash.compact:${sub || 'anon'}`
  } catch { return 'accDash.compact:anon' }
}
const EMPTY_FILTERS = () => ({ qtext: '', range: { from: '', to: '' }, pins: emptyPins(), gaps: [] })

export default function AccountDashboard() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [cal, setCal] = useState([])
  const [notifs, setNotifs] = useState([])
  // Селектор сотрудника: '' — я, 'all' — раздел целиком, число — конкретный аккаунт.
  const [repId, setRepId] = useState('')
  const [reps, setReps] = useState([])
  const [myRepId, setMyRepId] = useState(null)
  const [day, setDay] = useState(null)
  const [f, setF] = useState(EMPTY_FILTERS)
  const [stage, setStage] = useState(null)       // ключ лестницы — общий для «В работе» и пинов
  const [calmOnly, setCalmOnly] = useState(false)
  const [act, setAct] = useState(null)           // пин «вид работы» (подпись кнопки)
  const [snoozeOpen, setSnoozeOpen] = useState(false)
  const [compact, setCompact] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [pageSize, setPageSize] = useState(100)
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [expandedId, setExpandedId] = useState(null)
  // Строка очереди короткая, поэтому при раскрытии сделка догружается целиком: иначе
  // раскрывашка сказала бы «документов нет» там, где они есть.
  const [detail, setDetail] = useState(null)
  const [moveDeal, setMoveDeal] = useState(null)
  const [snoozeFor, setSnoozeFor] = useState(null)
  const [prepFor, setPrepFor] = useState(null)
  const [confirmFor, setConfirmFor] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  /* Права — из снимка в localStorage, поэтому после монтирования. Аргументов у `can`
     ТРИ — `(perms, section, action)`; с двумя он молча отвечал false всем, кроме админа. */
  const [canEdit, setCanEdit] = useState(false)
  useEffect(() => { setCanEdit(can(getPermissions(), 'accounts_dashboard', 'edit')) }, [])

  // Вид верхнего ряда помнит браузер. Хранилище бывает недоступно — тогда развёрнутый.
  useEffect(() => { try { setCompact(localStorage.getItem(compactKey()) === '1') } catch { /* нет хранилища */ } }, [])
  const toggleCompact = () => setCompact(v => {
    try { localStorage.setItem(compactKey(), v ? '0' : '1') } catch { /* нет хранилища */ }
    return !v
  })

  const load = useCallback(() => {
    setLoading(true)
    const who = repId === 'all' ? 'all_reps=true' : (repId ? `rep_id=${repId}` : '')
    const q = [who, day ? `day=${day}` : ''].filter(Boolean).join('&')
    Promise.all([
      api.get(`/sales/account-queue${q ? `?${q}` : ''}`, auth()),
      api.get(`/sales/account-calendar${who ? `?${who}` : ''}`, auth()),
      api.get('/notifications?limit=50', auth()).catch(() => ({ data: { items: [] } })),
    ]).then(([q1, q2, q3]) => {
      setData(q1.data)
      setCal(q2.data.days || [])
      setNotifs((q3.data.items || []).map(toItem))
      setMyRepId(q1.data.my_rep_id ?? null)
      setErr('')
    }).catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить очередь'))
      .finally(() => setLoading(false))
  }, [repId, day])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  useEffect(() => {
    api.get('/sales/reps?role=account', auth())
      .then(r => { setReps(r.data.items || []); setMyRepId(x => x ?? r.data.mine ?? null) })
      .catch(() => {})
  }, [])
  const myName = useMemo(() => (reps.find(r => r.id === myRepId) || {}).name, [reps, myRepId])

  // Любая смена выборки — на первую страницу.
  useEffect(() => { setPage(0) }, [pageSize, f, stage, calmOnly, act, sortKey, sortDir, day])

  const markRead = (ids) => {
    setNotifs(list => list.map(n => (!ids || ids.includes(n.id)) ? { ...n, unread: false } : n))
    api.post('/notifications/read', { ids: ids || null }, auth()).catch(() => {})
  }
  const openNotif = (n) => { markRead([n.id]); setNotifOpen(false); if (n.href) router.push(n.href) }

  // Все строки в порядке сервера (срочность → срок). «Отложено» приходит своей группой.
  const allRows = useMemo(() => (data?.groups || [])
    .flatMap(g => g.rows.map(r => ({ ...r, snoozed: g.key === 'snoozed' }))), [data])
  const options = useMemo(() => pinOptions(allRows), [allRows])
  const filtered = useMemo(() => applyToolbar(allRows, f), [allRows, f])
  const filtersOn = !!(f.qtext || f.range.from || f.range.to || f.gaps.length
    || Object.values(f.pins).some(v => v.length))
  const resetFilters = () => { setF(EMPTY_FILTERS()); setDay(null) }

  // Лестница и пины считаются по тем строкам, что видит человек: выбрав рекламодателя,
  // он не должен видеть в «В работе» счёт по всем сделкам.
  const live = useMemo(() => filtered.filter(r => !r.snoozed), [filtered])
  const snoozed = useMemo(() => filtered.filter(r => r.snoozed), [filtered])
  const counts = useMemo(() => ladderCounts(live), [live])
  const calmN = useMemo(() => live.filter(r => r.calm).length, [live])
  const stageRows = useMemo(() => (calmOnly ? live.filter(r => r.calm) : live.filter(r => inStage(r, stage))),
    [live, stage, calmOnly])
  const tableRows = useMemo(() => {
    const list = act ? stageRows.filter(r => r.action?.label === act) : stageRows
    if (sortKey) return [...list].sort(compareRows(sortKey, sortDir))
    // Порядок по умолчанию: рабочие → ЭДО и Оплата → «Без срочности». Сортировка
    // стабильная, внутри групп остаётся порядок сервера.
    return [...list].sort((a, b) => defaultRank(a) - defaultRank(b))
  }, [stageRows, act, sortKey, sortDir])
  const pages = Math.max(1, Math.ceil(tableRows.length / pageSize))
  const shownRows = tableRows.slice(page * pageSize, (page + 1) * pageSize)
  const needAction = live.filter(r => !r.calm).length

  const pickStage = (key) => { setStage(key); setCalmOnly(false); setAct(null); setExpandedId(null) }
  const pickCalm = () => { setCalmOnly(v => !v); setStage(null); setAct(null); setExpandedId(null) }
  const onSort = (key) => {
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    if (sortDir === 'asc') { setSortDir('desc'); return }
    setSortKey(null); setSortDir('asc')    // третий клик — назад к порядку очереди
  }

  // Ответ по строке, которую уже свернули или сменили, отбрасываем: раскрыли A, потом B,
  // а ответ по A пришёл позже — иначе B висела бы на «Загрузка сделки…» (ревью 28.09.2026).
  const openRef = useRef(null)
  const loadDetail = (r) => api.get(`/sales/deals/${r.code || r.id}`, auth())
    .then(res => { if (openRef.current === r.id) setDetail({ id: r.id, deal: res.data }) })
    .catch(() => { if (openRef.current === r.id) setDetail({ id: r.id, deal: null }) })
  const toggleRow = (r) => {
    if (expandedId === r.id) { openRef.current = null; setExpandedId(null); setDetail(null); return }
    openRef.current = r.id
    setExpandedId(r.id); setDetail(null); loadDetail(r)
  }

  // «Бюджеты под управлением» — три показателя макета. «Не оплачено» не выводится: это
  // дебиторка, и связи сделки с оплатой в системе пока нет.
  const budgets = useMemo(() => {
    const of = (keys) => live.filter(r => keys.includes(r.our_stage?.stage_key)).reduce((s, r) => s + (r.amount || 0), 0)
    return [['Под управлением', of(['booking', 'launch_prep', 'launch', 'closing', 'closing_fact'])],
            ['В эфире', live.filter(r => r.slot === 'live').reduce((s, r) => s + (r.amount || 0), 0)],
            ['Ждут закрывающих', of(['closing'])]]
  }, [live])

  // «Загрузка вперёд» — шесть месяцев. Сделка попадает в КАЖДЫЙ месяц своего периода;
  // подтверждённые — слои «реализуемые» и «фактические», в проработке — «планируемые».
  const months = useMemo(() => {
    const now = data?.today ? calendarDate(data.today) : new Date()
    const out = []
    for (let i = 0; i < 6; i++) {
      const d0 = new Date(now.getFullYear(), now.getMonth() + i, 1)
      out.push({ ym: `${d0.getFullYear()}-${String(d0.getMonth() + 1).padStart(2, '0')}`,
                 label: ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'][d0.getMonth()], ok: 0, plan: 0 })
    }
    live.forEach(r => {
      const from = r.period_from || r.period_to
      const to = r.period_to || r.period_from
      if (!from) return
      const layer = r.our_stage?.money_layer
      const confirmed = layer === 'реализуемые' || layer === 'фактические'
      out.forEach(m => { if (m.ym >= from.slice(0, 7) && m.ym <= to.slice(0, 7)) m[confirmed ? 'ok' : 'plan'] += 1 })
    })
    const avg = out.reduce((s, m) => s + m.ok + m.plan, 0) / out.length
    // Перегруз — больше 1,5 среднего: месяц, набранный заметно выше обычного.
    return out.map(m => ({ ...m, total: m.ok + m.plan, hot: avg > 0 && (m.ok + m.plan) > avg * 1.5 }))
  }, [live, data])

  const doSnooze = async (row, note, return_at) => {
    try {
      await api.post(`/sales/deals/${row.code || row.id}/snooze`, { note, return_at }, auth())
      setSnoozeFor(null); load()
    } catch (e) { alert(e?.response?.data?.detail || 'Не удалось отложить') }
  }
  const unsnooze = async (row) => {
    try { await api.delete(`/sales/deals/${row.code || row.id}/snooze`, auth()); load() }
    catch { alert('Не удалось вернуть в очередь') }
  }

  // Кнопка строки. Куда она ведёт, решил сервер (`action.do`); здесь — как это сделать.
  // Карточку сделки открываем в новой вкладке: очередь с фильтрами остаётся на месте.
  const runAction = (row, a) => {
    if (a.do === 'mp') return router.push(`/accounts/mp/new?deal=${row.id}`)
    if (a.do === 'move') return setMoveDeal(row)
    if (a.do === 'confirm') return setConfirmFor(row)
    if (a.do === 'prep') return setPrepFor(row)
    if (a.do === 'expand') return expandedId === row.id ? null : toggleRow(row)
    if (a.do === 'link' && a.url) {
      if (a.url.startsWith('/sales/deals/')) return window.open(a.url, '_blank', 'noopener')
      return router.push(a.url)
    }
    return null
  }

  const rowProps = { today: data?.today, canEdit, onToggle: toggleRow, onAction: runAction,
                     onSnooze: setSnoozeFor, onUnsnooze: unsnooze }
  const renderRow = (r) => (
    <Fragment key={r.id}>
      <QueueRow row={r} open={expandedId === r.id} {...rowProps} />
      {expandedId === r.id && (
        detail?.id === r.id
          ? <DealDetail layout="queue" deal={detail.deal || r} canEdit={canEdit}
              onOpen={() => window.open(`/sales/deals/${r.code || r.id}`, '_blank', 'noopener')}
              onEdit={() => router.push(`/sales/deals/${r.code || r.id}`)}
              onChanged={() => { load(); loadDetail(r) }} />
          : <div style={{ padding: '14px 12px', fontSize: 12, color: 'var(--text-muted)' }}>Загрузка сделки…</div>
      )}
    </Fragment>
  )

  const snoozeHint = (data?.groups || []).find(g => g.key === 'snoozed')?.hint
  const who = repId === 'all' ? 'Все аккаунты' : (repId ? (reps.find(r => String(r.id) === String(repId)) || {}).name : myName)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Дашборд · Аккаунты | SIMB-AD ERP</title></Head>
      {/* Модалка уведомлений — первым ребёнком корня, вне анимированных контейнеров:
          `transform` предка ломает `position: fixed`. */}
      {notifOpen && <NotifyModal notifs={notifs} onClose={() => setNotifOpen(false)} onOpenNotif={openNotif} onReadAll={() => markRead(null)} />}
      <Navbar />
      <div style={{ margin: '0 auto', padding: '26px 24px 40px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-primary)' }}>Мои сделки</span>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            {[who || 'Все аккаунты', data?.today && dm(data.today)].filter(Boolean).join(' · ')}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {/* Список сотрудников, как в дашборде сейлза. Своя строка помечена ★. */}
            {(data?.can_view_others ?? true) ? (
              <select value={repId} onChange={e => setRepId(e.target.value)} style={{ ...sel, minWidth: 210, padding: '8px 11px' }}>
                {!!myRepId && <option value="">★ {myName || 'Мои сделки'}</option>}
                <option value="all">Все аккаунты</option>
                {reps.filter(r => r.id !== myRepId).map(r => (
                  <option key={r.id} value={r.id}>{r.name}{r.linked ? '' : ' (без юзера)'}</option>
                ))}
              </select>
            ) : (
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{myName || 'Мои сделки'}</span>
            )}
            <WidgetsToggle open={!compact} onToggle={toggleCompact} tone="accent"
              titles={['Компактно: «В работе» и уведомления в одну строку', 'Развернуть «В работе» и уведомления']} />
          </span>
        </div>

        {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}

        {compact
          ? <CompactRow rows={live} counts={counts} stage={stage} onStage={pickStage}
              notifs={notifs} onOpenModal={() => setNotifOpen(true)} />
          : <WideRow rows={live} counts={counts} stage={stage} onStage={pickStage}
              months={months} budgets={budgets} notifs={notifs} onOpenNotif={openNotif} onReadAll={() => markRead(null)}
              onShowAll={() => setNotifOpen(true)} />}

        <EventsStrip days={cal} day={day} onDay={setDay} />

        {/* Требует действия — одна таблица на всю ширину, фильтры внутри карточки. */}
        <div style={{ ...card, padding: '18px 22px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em' }}>Требует действия</span>
            <span title={`всего в очереди ${live.length}`}
              style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: needAction ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
              {needAction} сделок</span>
            {!!day && (
              <span onClick={() => setDay(null)} title="Сбросить фильтр по дате"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 10px', borderRadius: 9, cursor: 'pointer',
                  background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', color: 'var(--accent)',
                  fontFamily: MONO, fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap' }}>
                {dm(day)} ✕</span>
            )}
            {filtersOn && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>отфильтровано из {allRows.length}</span>}
            <QuickPins counts={counts} stage={stage} onStage={pickStage} calmN={calmN} calmOnly={calmOnly} onCalm={pickCalm}
              snoozedN={snoozed.length} snoozeOpen={snoozeOpen} onSnooze={() => setSnoozeOpen(v => !v)} />
          </div>

          <QueueToolbar f={f} setF={setF} options={options} filtersOn={filtersOn} onReset={resetFilters} />
          <ActionPins rows={stageRows} stageOn={!!stage || calmOnly} act={act} onAct={(a) => { setAct(a); setExpandedId(null) }} />

          <div>
            <QueueHead sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            {loading && !data && <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>}
            {shownRows.map(renderRow)}
            {!!data && !tableRows.length && (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                {live.length ? 'На выбранных стадиях сделок нет' : 'Очередь пуста — всё под контролем'}</div>
            )}
            <Pager page={page} pages={pages} total={tableRows.length} shown={shownRows.length} pageSize={pageSize}
              sizes={[100, 300, 500]} onPage={setPage} onSize={setPageSize} />
          </div>

          {/* Отложено — свёрнутая группа под таблицей; раскрывается и пином «⏱ Отложено». */}
          {!!snoozed.length && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div onClick={() => setSnoozeOpen(v => !v)}
                style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 10px', borderRadius: 10, cursor: 'pointer',
                  background: 'var(--bg-subtle)', border: '1px solid var(--border-card)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: 6,
                  background: 'var(--warning-tint)', color: 'var(--warning-fg)', flex: '0 0 18px' }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></svg>
                </span>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)' }}>Отложено</span>
                <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-muted)' }}>{snoozed.length}</span>
                {!!snoozeHint && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{snoozeHint}</span>}
                <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-faint)' }}>{snoozeOpen ? '▴' : '▾'}</span>
              </div>
              {snoozeOpen && (
                <div>
                  {snoozed.map(r => (
                    <Fragment key={r.id}>
                      {renderRow(r)}
                      {(r.note || r.return_at) && expandedId !== r.id && (
                        <div style={{ margin: '-2px 0 4px 82px', fontSize: 11, color: 'var(--text-muted)' }}>
                          {r.note || 'без комментария'}
                          {r.return_at && <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--warning-fg)' }}> · вернётся {dm(r.return_at)}</span>}
                        </div>
                      )}
                    </Fragment>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {moveDeal && <MoveDealDialog deal={moveDeal} toStageKey={moveDeal.__to} toLost={moveDeal.__lost}
        onClose={() => setMoveDeal(null)} onMoved={() => { setMoveDeal(null); load() }} />}
      {confirmFor && (
        <BookingConfirm row={confirmFor} onClose={() => setConfirmFor(null)}
          onPick={(target) => { setMoveDeal({ ...confirmFor, ...target }); setConfirmFor(null) }} />
      )}
      {prepFor && (
        <LaunchPrepDialog row={prepFor} onClose={() => setPrepFor(null)}
          onToLaunch={() => { setMoveDeal({ ...prepFor, __to: 'launch' }); setPrepFor(null) }} />
      )}
      {snoozeFor && <SnoozeDialog row={snoozeFor} onClose={() => setSnoozeFor(null)} onSave={doSnooze} />}
    </div>
  )
}
