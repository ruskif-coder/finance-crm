/**
 * Приоритезация в расхлопе «Моих сделок» (владелец 16.11.2026): до старта — чек-лист площадок (согласовала · ЕРИД · цель),
 * готовые отмечены, «Запустить (N)»; в размещении — площадка / план / факт / % и незапущенные с «Дозапустить», плюс
 * переключатель «дозапускать сам» (`prio_requests.auto_launch_more`, сервер — `app/prio/autolaunch.py`).
 * Данные и действия — те же ручки, что у секции приоритезации в карточке (`/prio/deal/{id}`).
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'
import { MONO } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'
import BusyAct from '@/components/BusyAct'
import { BOX, CAP, pct } from '@/components/accounts/deals/nowWidgets'

const LIVE = new Set(['идёт', 'остановлено'])
const ready = (x) => x.status === 'согласовано' && x.erid_ready
const TONE = { 'идёт': 'var(--income)', 'остановлено': 'var(--text-faint)', 'согласовано': 'var(--accent)', 'отказ': 'var(--danger)', 'правки': 'var(--warning)' }
const BTN = { height: 30, padding: '0 14px', borderRadius: 9, border: 0, background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 12.5,
  fontWeight: 700, display: 'inline-flex', alignItems: 'center', fontFamily: 'inherit' }
const GRID_PREP = '22px minmax(0,1.6fr) 110px minmax(0,1fr) 90px'
const GRID_LIVE = '22px minmax(0,1.6fr) 110px 90px 90px 64px'
const oneLine = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }
const num = { ...oneLine, fontFamily: MONO, textAlign: 'right' }

function Status({ x }) {
  return (
    <span style={{ ...oneLine, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: 2, background: TONE[x.status] || 'var(--text-disabled)' }} />{x.status}
    </span>
  )
}

function Erid({ x }) {
  if (x.erid_ready) return <span style={{ ...oneLine, fontFamily: MONO, color: 'var(--income)' }} title={x.erid}>✓ {x.erid}</span>
  const why = x.ord_error ? 'ОРД отказал' : (x.erid_blockers?.length ? x.erid_blockers.join(', ') : (x.erid ? 'регистрация' : 'после согласования'))
  return <span style={{ ...oneLine, color: 'var(--text-faint)' }} title={why}>— {why}</span>
}

export default function PrioLaunch({ dealId, live, canEdit, onDone }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [pick, setPick] = useState(null)        // отмеченные к запуску; null — «все готовые» по умолчанию
  const [note, setNote] = useState('')
  const base = `/prio/deal/${dealId}`
  const load = useCallback(() => {
    api.get(base, auth()).then(r => { setS(r.data); setErr('') }).catch(e => setErr(detailText(e, 'Приоритезация не загрузилась')))
  }, [base])
  useEffect(() => { load() }, [load])
  if (!s) return err ? <div style={{ ...BOX, color: 'var(--danger-fg)', fontSize: 12.5 }}>{err}</div> : null

  const rows = s.placements.filter(x => x.status !== 'отказ')
  const readyIds = rows.filter(ready).map(x => x.id)
  const chosen = (pick || readyIds).filter(id => readyIds.includes(id))
  const toggle = (id) => setPick(chosen.includes(id) ? chosen.filter(x => x !== id) : [...chosen, id])
  const launch = async () => {
    setErr(''); setNote('')
    try {
      const r = await api.post(`${base}/bulk/launch`, { ids: chosen }, auth())
      setS(r.data); setPick(null)
      const bad = r.data.failed || []
      setNote(`Запущено: ${r.data.done.length}` + (bad.length ? ` · не прошли: ${bad.map(f => f.error).join('; ')}` : ''))
      onDone && onDone()
    } catch (e) { setErr(detailText(e, 'Запуск не прошёл')) }
  }
  const setAuto = async (on) => {
    setErr('')
    try { const r = await api.put(`${base}/auto-launch`, { on }, auth()); setS(r.data); onDone && onDone() }
    catch (e) { setErr(detailText(e, 'Не сохранилось')) }
  }

  const grid = live ? GRID_LIVE : GRID_PREP
  const waiting = rows.filter(ready).length
  return (
    <div style={{ ...BOX, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={CAP}>Площадки приоритезации</span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>
          {live ? `идут ${rows.filter(x => x.status === 'идёт').length} из ${rows.length}` : `готово ${waiting} из ${rows.length}`}</span>
        {live && !!waiting && <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--warning-fg)' }}>есть незапущенные площадки: {waiting}</span>}
        {s.launched && (
          <label title="РК уже идёт: площадка, согласовавшая и получившая ЕРИД позже, запускается сама — вам придёт уведомление"
            style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', cursor: canEdit ? 'pointer' : 'default' }}>
            <input type="checkbox" checked={!!s.auto_launch_more} disabled={!canEdit} onChange={e => setAuto(e.target.checked)} />дозапускать сам
          </label>)}
      </div>
      {!rows.length ? <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Площадок нет — добавьте их в карточке сделки</span> : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 10, padding: '0 0 6px', borderBottom: '1px solid var(--border-inner)' }}>
            {(live ? ['', 'Площадка', 'Статус', 'План', 'Факт', '%'] : ['', 'Площадка', 'Статус', 'ЕРИД', 'Цель']).map((t, i) => (
              <span key={i} style={{ ...CAP, fontSize: 9, textAlign: i >= 3 && (live || i === 4) ? 'right' : 'left' }}>{t}</span>))}
          </div>
          {rows.map(x => {
            const can = ready(x)
            const done = x.goal_imp ? (x.fact_imp || 0) / x.goal_imp * 100 : null
            return (
              <div key={x.id} style={{ display: 'grid', gridTemplateColumns: grid, gap: 10, alignItems: 'center', minHeight: 30, borderBottom: '1px solid var(--border-row)' }}>
                {can ? <input type="checkbox" checked={chosen.includes(x.id)} disabled={!canEdit} onChange={() => toggle(x.id)} aria-label={`Запустить ${x.name}`} />
                  : <span style={{ textAlign: 'center', color: LIVE.has(x.status) ? 'var(--income)' : 'var(--text-disabled)', fontSize: 12 }}>{LIVE.has(x.status) ? '✓' : '·'}</span>}
                <span style={{ ...oneLine, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 6 }} title={x.landing_foreign || x.name}>{x.name}
                  {!!x.landing_foreign && <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--warning-fg)', background: 'var(--warning-tint)', borderRadius: 6, padding: '0 5px' }}>⚠ чужая посадочная</span>}</span>
                <Status x={x} />
                {live ? <>
                  <span style={num}>{x.goal_imp ? grp(x.goal_imp) : '—'}</span>
                  <span style={num}>{x.fact_imp != null ? grp(x.fact_imp) : '—'}</span>
                  <span style={{ ...num, color: done != null && done >= 100 ? 'var(--income)' : 'var(--text-secondary)' }}>{pct(done)}</span>
                </> : <>
                  <Erid x={x} />
                  <span style={num}>{x.goal_imp ? grp(x.goal_imp) : '—'}</span>
                </>}
              </div>
            )
          })}
        </div>)}
      {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
      {!!note && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{note}</span>}
      {!!readyIds.length && canEdit && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BusyAct as="button" run={launch} label={`${live ? 'Дозапустить' : 'Запустить'} · ${chosen.length}`}
            style={{ ...BTN, opacity: chosen.length ? 1 : 0.5, pointerEvents: chosen.length ? 'auto' : 'none' }} />
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
            {live ? 'площадки согласовали и получили ЕРИД после запуска' : 'запускаются отмеченные: согласовали и получили ЕРИД'}</span>
        </div>)}
    </div>
  )
}
