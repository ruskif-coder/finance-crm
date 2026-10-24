// Панель ячейки «Плана продаж» (владелец 24.10.2026): как складывается прогноз, динамика за 7 дней, что может закрыть
// разрыв (планируемые сделки ячейки по сумме — без «перекрасить светофор»: перекраска двигает прогноз, а не деньги), сделки
// за этим числом и в конце — кто и когда правил цель (журнал «было → стало»).
import { useEffect, useState } from 'react'
import { MONO, UI, Z } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { overlayClose } from '@/lib/overlay'
import { fmtDateTimeShort } from '@/lib/dates'
import { fmtK, fmtSigned, pct } from '@/lib/salesPlan.mjs'

const cap = { fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const BUCKET = { fact: ['факт', 'var(--income-tint)', 'var(--income-fg)'], work: ['в работе', 'var(--accent-tint)', 'var(--accent-fg)'],
  green: ['зелёный', 'var(--income-tint)', 'var(--income-fg)'], orange: ['оранжевый', 'var(--warning-tint)', 'var(--warning-fg)'],
  grey: ['серый', 'var(--bg-subtle)', 'var(--text-muted)'] }
const WEIGHT = { green: 1, orange: 0.5, grey: 0 }

function Waterfall({ c }) {
  const scale = Math.max(c.goal || 0, c.forecast || 0) || 1
  const w = (v) => `${Math.max(0, v) / scale * 100}%`
  const rows = [['Цель', c.goal, 0, 'var(--border-card)'], ['Факт', c.fact, 0, 'var(--income)'], ['В работе — со «Сборки»', c.work, c.fact, 'var(--accent)'],
    ['Планируемые · зелёные · 100 %', c.green, c.done, 'var(--income-border)'], ['Планируемые · оранжевые · 50 %', c.orange * 0.5, c.done + c.green, 'var(--warning)']]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map(([l, v, off, col]) => (
        <div key={l} style={{ display: 'grid', gridTemplateColumns: '1fr 96px 1fr', alignItems: 'center', gap: 10, fontSize: 12.5 }}>
          <span>{l}</span><b style={{ fontFamily: MONO, textAlign: 'right' }}>{v == null ? '—' : fmtK(v)}</b>
          <span style={{ position: 'relative', height: 12, borderRadius: 4, background: 'var(--bg-subtle)' }}>
            {v != null && <i style={{ position: 'absolute', top: 0, bottom: 0, left: w(off), width: w(v), borderRadius: 4, background: col }} />}
          </span>
        </div>
      ))}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 96px 1fr', gap: 10, fontSize: 12.5, borderTop: '1px solid var(--border-card)', paddingTop: 6 }}>
        <b>Прогноз</b><b style={{ fontFamily: MONO, textAlign: 'right', color: 'var(--accent-fg)' }}>{fmtK(c.forecast)}</b>
        <span style={{ color: c.goal == null ? 'var(--text-muted)' : c.forecast >= c.goal ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
          {c.goal == null ? 'цель не задана' : `${fmtSigned(c.forecast - c.goal)} к цели · ${pct(c.forecast, c.goal)} %`}</span>
      </div>
      {c.forecast_week_ago != null && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Прогноз за 7 дней:{' '}
          <b style={{ fontFamily: MONO, color: c.forecast >= c.forecast_week_ago ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
            {c.forecast >= c.forecast_week_ago ? '▲ ' : '▼ '}{fmtSigned(c.forecast - c.forecast_week_ago)}</b></div>
      )}
    </div>
  )
}

export default function CellPanel({ year, row, b, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    api.get('/sales-plan/cell', { ...auth(), params: { year, m_from: b.m0 + 1, m_to: b.m1 + 1, scope: row.scope, key_id: row.key_id || 0 } })
      .then(r => { if (alive) setD(r.data) }).catch(e => { if (alive) setErr(e.response?.data?.detail || 'Не удалось загрузить ячейку') })
    return () => { alive = false }
  }, [year, row.scope, row.key_id, b.m0, b.m1])
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  const c = b.c
  const gap = c.goal != null ? c.goal - c.forecast : 0
  let acc = 0
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)', fontFamily: UI }}>
      <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 560, maxWidth: '100%', background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-modal)', padding: '20px 22px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
            <span style={cap}>{b.label} {year}</span>
            <span style={{ fontSize: 18, fontWeight: 800 }}>{row.name}</span>
          </span>
          <button type="button" onClick={onClose} aria-label="Закрыть" style={{ marginLeft: 'auto', width: 32, height: 32, borderRadius: 9,
            border: '1px solid var(--border-card)', background: 'var(--bg-card)', cursor: 'pointer', color: 'var(--text-muted)' }}>✕</button>
        </div>
        <div><div style={{ ...cap, marginBottom: 8 }}>как складывается прогноз · тыс. ₽ без НДС</div><Waterfall c={c} /></div>
        {!!err && <div style={{ color: 'var(--danger-fg)', fontSize: 12.5 }}>{err}</div>}
        {!d && !err && <div style={{ color: 'var(--text-muted)', fontSize: 12.5 }}>загружаю сделки…</div>}
        {!!d && gap > 0 && (
          <div style={{ background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ ...cap, marginBottom: 8 }}>что может закрыть разрыв {fmtK(gap)}</div>
            {!d.candidates.length && <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Планируемых сделок нет — разрыв закрывать нечем, нужны новые.</div>}
            {d.candidates.map(x => {
              const adds = x.amount * (1 - WEIGHT[x.bucket])
              acc += adds
              return (
                <div key={x.id} style={{ display: 'grid', gridTemplateColumns: '80px 1fr 90px 110px', gap: 8, alignItems: 'center', fontSize: 12, padding: '5px 0',
                  borderTop: '1px solid var(--accent-border)' }}>
                  <a href={`/sales/deals/${x.code || x.id}`} target="_blank" rel="noopener noreferrer" style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--accent-fg)' }}>{x.code || x.id}</a>
                  <span style={{ minWidth: 0 }}><span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.client || x.title}</span>
                    <small style={{ color: 'var(--text-muted)' }}>{BUCKET[x.bucket][0]} · {x.rep || 'без продажника'}</small></span>
                  <span style={{ fontFamily: MONO, textAlign: 'right' }}>{adds ? `+${fmtK(adds)}` : 'в прогнозе'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right', color: acc >= gap ? 'var(--income-fg)' : 'var(--text-muted)' }}>
                    {fmtK(Math.min(acc, gap))} из {fmtK(gap)}</span>
                </div>
              )
            })}
            {!!d.candidates.length && <div style={{ fontSize: 11.5, marginTop: 6, color: acc >= gap ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
              {acc >= gap ? 'Если эти сделки состоятся, разрыв закроется.' : `Даже если все состоятся, не хватит ${fmtK(gap - acc)}.`}</div>}
          </div>
        )}
        {!!d && (
          <div>
            <div style={{ ...cap, marginBottom: 6 }}>сделки за этим числом · {d.deals.length}</div>
            {d.deals.map(x => (
              <div key={x.id} style={{ display: 'grid', gridTemplateColumns: '80px 1fr 84px 90px', gap: 8, alignItems: 'center', fontSize: 12, padding: '6px 0',
                borderTop: '1px solid var(--border-inner)' }}>
                <a href={`/sales/deals/${x.code || x.id}`} target="_blank" rel="noopener noreferrer" style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--accent-fg)' }}>{x.code || x.id}</a>
                <span style={{ minWidth: 0 }}><span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.client || x.title}</span>
                  <small style={{ color: 'var(--text-muted)' }}>{x.stage} · {x.rep || 'без продажника'}</small></span>
                <span style={{ justifySelf: 'end', padding: '2px 6px', borderRadius: 5, fontFamily: MONO, fontSize: 10, fontWeight: 700,
                  background: BUCKET[x.bucket][1], color: BUCKET[x.bucket][2] }}>{BUCKET[x.bucket][0]}</span>
                <span style={{ fontFamily: MONO, textAlign: 'right' }}>{fmtK(x.amount)}</span>
              </div>
            ))}
          </div>
        )}
        {!!d && (
          <div>
            <div style={{ ...cap, marginBottom: 6 }}>кто и когда правил цель</div>
            {!d.history.length && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{row.scope.startsWith('без') || row.scope === 'группа' ? 'у строки нет своей цели' : 'цель не правилась'}</div>}
            {d.history.map((h, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12, padding: '4px 0', borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ color: 'var(--text-muted)', minWidth: 104 }}>{fmtDateTimeShort(h.at)}</span>
                <span style={{ flex: 1 }}>{h.by || '—'}{b.m0 !== b.m1 ? ` · ${h.month} мес.` : ''}</span>
                <span style={{ fontFamily: MONO }}>{fmtK(h.was)} → {fmtK(h.now)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
