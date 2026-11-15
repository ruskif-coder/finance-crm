/**
 * «Мои сделки» — дашборд аккаунта v5, три контура (хендофф design_handoff_account_dashboard_v5, 13.11.2026). С 14.11.2026 — пункт
 * «Дашборд» меню «Аккаунты» для всех с правом `accounts_dashboard`; старый дашборд (`/accounts/dashboard`) — ссылкой из шапки.
 *
 * Часть 1: шапка, три контура, панель фильтров, список по группам «чей ход». Данные — та же очередь, что у «Дашборда»
 * (`/sales/account-queue`, «чей ход» считает сервер — `app/sales/account_turn.py`), пакеты — реестр мастер-сделок.
 * Часть 2: расхлоп с виджетами стадий (`DealNow`). Часть 4: режим «Карточки» (`Board`, `DealCard`) и модалка сделки (`DealModal`).
 * Контур «Документы» — пакеты мастер-сделок списком (`PackList`) и карточками (`PackBoard`). «События и сроки» — `EventsModal`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Link from 'next/link'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, sel } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { dm } from '@/lib/salesFormat'
import { detailText } from '@/lib/loadError'
import useLatest from '@/lib/useLatest'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import DealNow from '@/components/accounts/deals/DealNow'
import QueueToolbar, { applyToolbar, pinOptions, emptyFilters } from '@/components/accounts/dashboard/QueueToolbar'
import useQueueActions from '@/components/accounts/useQueueActions'
import ContourCards from '@/components/accounts/deals/ContourCards'
import TurnGroups from '@/components/accounts/deals/TurnGroups'
import Board from '@/components/accounts/deals/Board'
import DealModal from '@/components/accounts/deals/DealModal'
import PackList from '@/components/accounts/deals/PackList'
import PackBoard from '@/components/accounts/deals/PackBoard'
import EventsModal from '@/components/accounts/deals/EventsModal'
import { buildEvents } from '@/lib/dealEvents.mjs'
import { DOC_STAGES, contourOf, inStages, mine, packMine } from '@/components/accounts/deals/contours'

// Сборка — сложный процесс, её ведут в карточке (владелец 13.11.2026): кнопка стадии в строке заменена переходом.
const GO_ON = (r) => (r.external_launch      // правило — сервер (`account_turn.external_launch`), по матрице учёта
  // Контур аккаунта: запуск во внешней системе — «Подтвердить запуск» в расхлопе (владелец 14.11.2026)
  ? { do: 'expand', label: 'Подтвердить запуск' }
  : { do: 'link', label: 'Продолжить сборку', url: `/sales/deals/${r.code || r.id}` })
const VIEW_KEY = 'my_deals_view'

export default function MyDeals() {
  const router = useRouter()
  const [ready, setReady] = useState(false)          // права из localStorage — только после монтирования
  const [data, setData] = useState(null)
  const [packs, setPacks] = useState(null)
  const [packsErr, setPacksErr] = useState('')
  const [reps, setReps] = useState([])
  const [repId, setRepId] = useState('')
  const [myRepId, setMyRepId] = useState(null)
  const [err, setErr] = useState('')
  const [contour, setContour] = useState('work')
  const [picked, setPicked] = useState([])
  const [f, setF] = useState(emptyFilters)
  const [whose, setWhose] = useState('all')
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [expandedId, setExpandedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [canEdit, setCanEdit] = useState(false)
  const [canMaster, setCanMaster] = useState(false)
  const [view, setView] = useState('list')
  const [openRow, setOpenRow] = useState(null)
  const [eventsOpen, setEventsOpen] = useState(false)

  useEffect(() => {
    setReady(true)
    setCanEdit(can(getPermissions(), 'accounts_dashboard', 'edit'))
    setCanMaster(can(getPermissions(), 'master_deals', 'edit'))   // шаги пакета — право реестра мастер-сделок
  }, [])
  // Вид «Список / Карточки» — удобство одного человека: localStorage, без него всё работает (список по умолчанию).
  useEffect(() => { try { const v = localStorage.getItem(VIEW_KEY); if (v === 'cards' || v === 'list') setView(v) } catch { /* нет хранилища */ } }, [])
  const pickView = (v) => { setView(v); setExpandedId(null); try { localStorage.setItem(VIEW_KEY, v) } catch { /* нет хранилища */ } }

  // Отсечка устаревшего ответа (аудит 13.11.2026): быстрое переключение аккаунта показывало строки прошлого выбора под новым
  const latest = useLatest()
  const load = useCallback(() => {
    const fresh = latest()
    const who = repId === 'all' ? 'all_reps=true' : (repId ? `rep_id=${repId}` : '')
    api.get(`/sales/account-queue${who ? `?${who}` : ''}`, auth())
      .then(r => { if (!fresh()) return; setData(r.data); setMyRepId(r.data.my_rep_id ?? null); setErr('') })
      .catch(e => { if (fresh()) setErr(detailText(e, 'Не удалось загрузить сделки')) })
    // Пакеты — реестр мастер-сделок, своё право: без него контур «Документы» говорит причину, а не ошибку запроса (14.11.2026)
    if (!can(getPermissions(), 'master_deals', 'view')) { setPacks(null); setPacksErr('Пакеты мастер-сделок недоступны: нет права «Мастер-сделки»'); return }
    // Сбой реестра — причиной на экране, а не «пакетов нет» (гейт check-screens)
    api.get('/master-deals/registry/list', auth()).then(r => { if (!fresh()) return; setPacks(r.data.rows || []); setPacksErr('') })
      .catch(e => { if (fresh()) setPacksErr(detailText(e, 'Не удалось загрузить мастер-сделки')) })
  }, [repId, latest])
  useEffect(() => { if (ready) load() }, [ready, load])
  useRefreshOnReturn(load)
  useEffect(() => {
    if (!ready) return
    api.get('/sales/reps?role=account', auth()).then(r => { setReps(r.data.items || []); setMyRepId(x => x ?? r.data.mine ?? null) }).catch(() => {})
  }, [ready])

  const openRef = useRef(null)
  const loadDetail = (r) => api.get(`/sales/deals/${r.code || r.id}`, auth())
    .then(res => { if (openRef.current === r.id) setDetail({ id: r.id, deal: res.data }) })
    .catch(() => { if (openRef.current === r.id) setDetail({ id: r.id, deal: null }) })
  const toggleRow = (r) => {
    if (expandedId === r.id) { openRef.current = null; setExpandedId(null); setDetail(null); return }
    openRef.current = r.id
    setExpandedId(r.id); setDetail(null); loadDetail(r)
  }
  const { runAction, setSnoozeFor, unsnooze, dialogs } = useQueueActions({
    router, load, onExpand: (row) => (view === 'cards' ? setOpenRow(row) : expandedId === row.id ? null : toggleRow(row)) })

  // Все строки очереди, кроме отложенных, с контуром. Отложенные — у «Дашборда» (здесь будильник — фильтр следующих частей).
  const allRows = useMemo(() => (data?.groups || []).filter(g => g.key !== 'snoozed')
    .flatMap(g => g.rows).map(r => ({ ...r, __contour: contourOf(r), ...(r.slot === 'prep' ? { action: GO_ON(r) } : {}) })).filter(r => r.__contour), [data])
  const options = useMemo(() => pinOptions(allRows), [allRows])
  const filtered = useMemo(() => applyToolbar(allRows, f), [allRows, f])
  // Пакеты — тех сделок, что видит аккаунт: реестр отдаёт по своему охвату, а «мои» — пакеты с моими сделками. Коды — по ВСЕЙ
  // очереди, включая сделки, уже ушедшие в ДО (в контуры 1–2 они не входят). «Ждём закрытия» (ДС на старте, РК идёт) и архив —
  // вне контура «Документы»: хода у аккаунта там нет.
  const myCodes = useMemo(() => new Set((data?.groups || []).flatMap(g => g.rows).map(r => r.code)), [data])
  const myPacks = useMemo(() => (packs || []).filter(p => DOC_STAGES.some(st => st.key === p.status)
    && (repId === 'all' || (p.deal_codes || []).some(c => myCodes.has(c)))), [packs, myCodes, repId])

  const inContour = useMemo(() => filtered.filter(r => r.__contour === contour), [filtered, contour])
  // События и сроки — по всем сделкам аккаунта (оба контура), без фильтров панели: модалка — свой обзор.
  const events = useMemo(() => (data?.today ? buildEvents(allRows, data.today) : []), [allRows, data])
  const lateN = events.filter(e => e.overdue).length
  const nextDay = events.find(e => !e.overdue)
  const nextN = nextDay ? events.filter(e => !e.overdue && e.date === nextDay.date).length : 0
  // Клик по событию: в карточках — модалка сделки; в списке — найти сделку кодом и раскрыть её строку.
  const pickEvent = (r) => {
    setEventsOpen(false)
    if (view === 'cards') { setOpenRow(r); return }
    setContour(r.__contour); setPicked([]); setF({ ...emptyFilters(), qtext: r.code }); setWhose('all')
    openRef.current = r.id; setExpandedId(r.id); setDetail(null); loadDetail(r)
  }
  // Пакеты на экране: поиск (код пакета или сделки, договор, контрагент, рекламодатель, бренд), стадии, «только мой ход».
  const shownPacks = useMemo(() => {
    const q = (f.qtext || '').trim().toLowerCase()
    return myPacks.filter(p => (!picked.length || picked.includes(p.status))
      && (!q || [p.code, p.contract?.number, p.counterparty, p.payer, ...(p.advertisers || []), ...(p.brands || []), ...(p.deal_codes || [])].join(' ').toLowerCase().includes(q))
      && (whose !== 'mine' || packMine(p)))
  }, [myPacks, picked, f.qtext, whose])
  const shown = useMemo(() => {
    const st = inStages(inContour, contour, picked)
    return whose === 'mine' ? st.filter(mine) : st
  }, [inContour, contour, picked, whose])

  const filtersOn = !!(f.qtext || f.range.from || f.range.to || f.gaps.length || Object.values(f.pins).some(v => v.length) || picked.length)
  const resetAll = () => { setF(emptyFilters()); setPicked([]) }
  const pickContour = (key) => { setContour(key); setPicked([]); setF(emptyFilters()); setExpandedId(null) }
  const pickStage = (key, st, multi) => {
    if (key !== contour) { setContour(key); setPicked([st]); setExpandedId(null); return }
    setPicked(a => (a.includes(st) ? (multi ? a.filter(x => x !== st) : (a.length > 1 ? [st] : [])) : (multi ? [...a, st] : [st])))
  }
  const onSort = (key) => {
    if (sortKey !== key) { setSortKey(key); setSortDir(key === 'amount' ? 'desc' : 'asc'); return }
    if ((key === 'amount' ? 'desc' : 'asc') === sortDir) { setSortDir(sortDir === 'asc' ? 'desc' : 'asc'); return }
    setSortKey(null); setSortDir('asc')
  }

  const rowProps = { today: data?.today, canEdit, onToggle: toggleRow, onAction: runAction, onSnooze: setSnoozeFor, onUnsnooze: unsnooze, copyCode: true }
  // Расхлоп — по экранам 03–05 хендоффа v5: «Сейчас» с виджетом стадии, «История», «Медиаплан и документы» + «Деньги».
  const renderDetail = (r) => (
    <DealNow row={r} deal={detail?.id === r.id ? detail.deal : null} canEdit={canEdit} onAction={runAction} onSnooze={setSnoozeFor} onReload={load} />)
  const myName = (reps.find(r => r.id === myRepId) || {}).name
  const who = repId === 'all' ? 'все аккаунты' : (repId ? (reps.find(r => String(r.id) === String(repId)) || {}).name : myName)
  const total = contour === 'docs' ? myPacks.length : inContour.length

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Мои сделки · Аккаунты | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ boxSizing: 'border-box', padding: '22px clamp(28px, 1.9vw, 48px) 40px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em' }}>Мои сделки</div>
            <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginTop: 4 }}>
              {[who || 'мои сделки', data?.today && dm(data.today), 'три контура: до брони → работа → документы'].filter(Boolean).join(' · ')}</div>
          </div>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Link href="/accounts/dashboard" style={{ fontSize: 12, color: 'var(--text-muted)', textDecoration: 'underline dotted', whiteSpace: 'nowrap' }}>Старый дашборд</Link>
            <button type="button" onClick={() => setEventsOpen(true)} disabled={!data}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 12px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                cursor: 'pointer', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
              события · просрочено <b style={{ color: lateN ? 'var(--danger-fg)' : 'var(--text-secondary)' }}>{lateN}</b>
              {!!nextDay && <> · {nextDay.date.slice(8, 10)}.{nextDay.date.slice(5, 7)} — {nextN}</>}
            </button>
            <span style={{ display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: 2 }}>
              {[['list', 'Список'], ['cards', 'Карточки']].map(([k, l]) => (
                <button key={k} type="button" onClick={() => pickView(k)} aria-pressed={view === k}
                  style={{ height: 30, padding: '0 14px', border: 0, borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                    background: view === k ? 'var(--bg-card)' : 'transparent', color: view === k ? 'var(--accent-fg)' : 'var(--text-secondary)',
                    boxShadow: view === k ? 'var(--shadow-card)' : 'none' }}>{l}</button>
              ))}
            </span>
            {(data?.can_view_others ?? true) && (
              <select value={repId} onChange={e => setRepId(e.target.value)} style={{ ...sel, minWidth: 210, padding: '8px 11px' }}>
                {!!myRepId && <option value="">★ {myName || 'Мои сделки'}</option>}
                <option value="all">Все аккаунты</option>
                {reps.filter(r => r.id !== myRepId).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            )}
          </span>
        </div>

        {err && <div style={{ color: 'var(--danger-fg)' }}>{err}</div>}

        <ContourCards rows={filtered} packs={myPacks} contour={contour} picked={picked} onContour={pickContour}
          onStage={pickStage} />

        {/* Панель фильтров — одна строка, липкая (README §3). */}
        <div style={{ position: 'sticky', top: 0, zIndex: 20, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
          borderRadius: 16, boxShadow: 'var(--shadow-card)', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 600px', minWidth: 0 }}>
            <QueueToolbar f={f} setF={setF} options={options} filtersOn={filtersOn} onReset={resetAll} />
          </div>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            показано {contour === 'docs' ? shownPacks.length : shown.length} из {total}</span>
          <span style={{ display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: 2 }}>
            {[['all', 'Все'], ['mine', 'Только мой ход']].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setWhose(k)} aria-pressed={whose === k}
                style={{ height: 28, padding: '0 12px', border: 0, borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                  background: whose === k ? 'var(--bg-card)' : 'transparent', color: whose === k ? 'var(--accent-fg)' : 'var(--text-secondary)',
                  boxShadow: whose === k ? 'var(--shadow-card)' : 'none' }}>{l}</button>
            ))}
          </span>
        </div>

        {!data && !err && <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>}
        {!!data && contour !== 'docs' && view === 'cards' && (
          <Board rows={shown} contour={contour} picked={picked} canEdit={canEdit} onOpen={setOpenRow} onAction={runAction} onSnooze={setSnoozeFor} />
        )}
        {!!data && contour !== 'docs' && view === 'list' && (
          <TurnGroups rows={shown} allOpen={picked.length > 0} sortKey={sortKey} sortDir={sortDir} onSort={onSort}
            renderDetail={renderDetail} expandedId={expandedId} rowProps={rowProps} />
        )}
        {!!data && contour === 'docs' && !!packsErr && <div style={{ padding: 40, color: 'var(--danger-fg)' }}>{packsErr}</div>}
        {!!data && contour === 'docs' && packs === null && !packsErr && <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>}
        {!!data && contour === 'docs' && packs !== null && view === 'list' && <PackList packs={shownPacks} canEdit={canMaster} onReload={load} />}
        {!!data && contour === 'docs' && packs !== null && view === 'cards' && <PackBoard packs={shownPacks} picked={picked} canEdit={canMaster} onReload={load} />}
      </div>
      {eventsOpen && <EventsModal rows={allRows} today={data?.today} onClose={() => setEventsOpen(false)} onPick={pickEvent} />}
      {!!openRow && <DealModal rows={shown} row={openRow} canEdit={canEdit} onClose={() => setOpenRow(null)} onMove={setOpenRow}
        onAction={runAction} onSnooze={setSnoozeFor} onReload={() => { setOpenRow(null); load() }} />}
      {dialogs}
    </div>
  )
}
