/**
 * «События и сроки» «Моих сделок» (экран 14 хендоффа v5). Шапка — окно дат, впереди / просрочено, кнопки-фильтры типов; лента
 * «Просрочено + 11 дней» (клик прокручивает к дню); блок «Просрочено» (6 строк, дальше «показать ещё»), затем события по дням.
 * Строка: тип · код · рекламодатель и бренд · сейлз и трафик · бюджет · что сделать и норма. Расчёт — `lib/dealEvents.mjs`.
 */
import { useMemo, useRef, useState } from 'react'
import { MONO, Z } from '@/components/salesTableKit'
import { overlayClose } from '@/lib/overlay'
import { mln } from '@/components/accounts/dashboard/ladder'
import { TYPES, buildEvents, daysOf } from '@/lib/dealEvents.mjs'

const TYPE_DOT = { start: 'var(--accent)', end: 'var(--warning)', norm: 'var(--violet-fg)' }
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']
const WD_FULL = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']
const dd = (s) => `${s.slice(8, 10)}.${s.slice(5, 7)}`
const wd = (s) => new Date(`${s}T00:00:00Z`).getUTCDay()
const diff = (a, b) => Math.round((new Date(`${a}T00:00:00Z`) - new Date(`${b}T00:00:00Z`)) / 86400000)
const label = (k) => TYPES.find(t => t.key === k)?.label || k

function Block({ children, id }) {
  return <div data-day={id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>
}

function Row({ e, today, onPick }) {
  const r = e.row
  const late = e.overdue ? diff(today, e.date) : 0
  return (
    <div onClick={() => onPick(r)} style={{ display: 'grid', gridTemplateColumns: '150px 84px minmax(0,1.2fr) 44px minmax(0,1fr) 92px minmax(0,1.5fr) 14px', gap: 10,
      alignItems: 'center', padding: '10px 14px', borderTop: '1px solid var(--border-row)', cursor: 'pointer' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12.5, fontWeight: 700 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: TYPE_DOT[e.type] }} />{label(e.type)}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{r.code}</span>
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <b style={{ fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.advertiser || '—'}</b>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{[r.brand, r.product].filter(Boolean).join(' · ')}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', lineHeight: 1.7 }}>
        <span>сейлз</span><span>трафик</span></span>
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, fontSize: 12 }}>
        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.sales_rep || '—'}</span>
        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: r.traffic_manager ? 'var(--text-primary)' : 'var(--warning-text)' }}>{r.traffic_manager || 'не назначен'}</span>
      </span>
      <b style={{ fontFamily: MONO, fontSize: 12.5, textAlign: 'right', whiteSpace: 'nowrap' }}>{mln(r.amount)}</b>
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={{ fontSize: 12.5, fontWeight: e.overdue ? 700 : 600 }}>{e.what}</span>
        <span style={{ fontSize: 11, color: e.overdue ? 'var(--warning-text)' : 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {e.overdue ? `просрочено ${late} дн. · ` : ''}{e.norm}</span>
      </span>
      <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>›</span>
    </div>
  )
}

export default function EventsModal({ rows, today, onClose, onPick }) {
  const all = useMemo(() => buildEvents(rows, today), [rows, today])
  const [types, setTypes] = useState([])
  const [more, setMore] = useState(false)
  const box = useRef(null)
  const ev = types.length ? all.filter(e => types.includes(e.type)) : all
  const late = ev.filter(e => e.overdue)
  const days = daysOf(today)
  const byDay = (d) => ev.filter(e => !e.overdue && e.date === d)
  const go = (id) => { const el = box.current?.querySelector(`[data-day="${id}"]`); if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' }) }
  const toggle = (k) => setTypes(t => (t.includes(k) ? t.filter(x => x !== k) : [...t, k]))
  const sum = (list) => mln(list.reduce((s, e) => s + (e.row.amount || 0), 0))
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '6vh 16px' }}>
      <div style={{ width: 'min(1100px, 100%)', maxHeight: '88vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-modal)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid var(--border-inner)', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ display: 'flex', flexDirection: 'column' }}>
              <b style={{ fontSize: 17 }}>События и сроки</b>
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{dd(days[0])} — {dd(days[days.length - 1])} · впереди {ev.length - late.length} · просрочено {late.length}</span>
            </span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
              {TYPES.map(t => {
                const on = types.includes(t.key)
                return (
                  <button key={t.key} type="button" onClick={() => toggle(t.key)} aria-pressed={on}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 10px', borderRadius: 9, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, fontWeight: 600,
                      border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`, background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: 'var(--text-primary)' }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: TYPE_DOT[t.key] }} />{t.label}
                    <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{all.filter(e => e.type === t.key).length}</span>
                  </button>)
              })}
              <button type="button" onClick={onClose} title="Закрыть" style={{ width: 30, height: 30, borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', color: 'var(--text-secondary)' }}>×</button>
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: `1.3fr repeat(${days.length}, minmax(0,1fr))`, gap: 6 }}>
            <button type="button" onClick={() => go('late')} style={{ textAlign: 'left', padding: '7px 9px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-subtle)', cursor: 'pointer', fontFamily: 'inherit' }}>
              <b style={{ display: 'block', fontSize: 12 }}>Просрочено</b>
              <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700 }}>{late.length} не закрыто</span>
            </button>
            {days.map((d, i) => {
              const list = byDay(d)
              return (
                <button key={d} type="button" onClick={() => go(d)} disabled={!list.length}
                  style={{ textAlign: 'left', padding: '7px 8px', borderRadius: 10, border: '1px solid var(--border-card)', background: i === 0 ? 'var(--bg-subtle)' : 'var(--bg-card)', cursor: list.length ? 'pointer' : 'default', fontFamily: 'inherit', minWidth: 0 }}>
                  <span style={{ display: 'block', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: list.length ? 'var(--text-primary)' : 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                    {dd(d)} <span style={{ fontWeight: 400, fontSize: 9.5, color: 'var(--text-faint)' }}>{i === 0 ? 'сегодня' : WD[wd(d)]}</span></span>
                  <span style={{ display: 'flex', gap: 2, margin: '3px 0 1px', height: 6 }}>
                    {[...new Set(list.map(e => e.type))].map(t => <span key={t} style={{ width: 6, height: 6, borderRadius: 2, background: TYPE_DOT[t] }} />)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{list.length || '—'}</span>
                </button>)
            })}
          </div>
        </div>
        <div ref={box} style={{ overflowY: 'auto', padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!ev.length && <span style={{ fontSize: 13, color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>Событий в окне нет</span>}
          {!!late.length && (
            <Block id="late">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--danger)', alignSelf: 'center' }} />
                <b style={{ fontSize: 14 }}>Просрочено</b><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>срок прошёл, не закрыто</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{late.length} · {sum(late)}</span>
              </div>
              <div style={{ border: '1px solid var(--border-card)', borderRadius: 12, overflow: 'hidden' }}>
                {(more ? late : late.slice(0, 6)).map((e, i) => <Row key={`${e.row.id}-${e.type}-${i}`} e={e} today={today} onPick={onPick} />)}
                {late.length > 6 && !more && <button type="button" onClick={() => setMore(true)}
                  style={{ width: '100%', textAlign: 'left', padding: '10px 14px', border: 0, borderTop: '1px solid var(--border-row)', background: 'var(--bg-card)', color: 'var(--accent-fg)', fontWeight: 700, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
                  показать ещё {late.length - 6}</button>}
              </div>
            </Block>
          )}
          {days.map((d, i) => {
            const list = byDay(d)
            if (!list.length) return null
            const n = diff(d, today)
            return (
              <Block key={d} id={d}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <b style={{ fontFamily: MONO, fontSize: 14 }}>{dd(d)}</b>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{WD_FULL[wd(d)]}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: i <= 1 ? 'var(--warning-text)' : 'var(--text-secondary)' }}>{i === 0 ? 'сегодня' : i === 1 ? 'завтра' : `через ${n} дн.`}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{list.length} · {sum(list)}</span>
                </div>
                <div style={{ border: '1px solid var(--border-card)', borderRadius: 12, overflow: 'hidden' }}>
                  {list.map((e, k) => <Row key={`${e.row.id}-${e.type}-${k}`} e={e} today={today} onPick={onPick} />)}
                </div>
              </Block>
            )
          })}
        </div>
      </div>
    </div>
  )
}
