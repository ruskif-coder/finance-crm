/**
 * «Кампании» на телефоне — хендофф «моб версия кп», п. 3.
 *
 * Те же строки и то же правило отбора, что у десктопного экрана (`visibleCampaigns`), —
 * иначе на телефоне и на компьютере площадка видела бы разные месяцы. Биллинг — тот же
 * `billing` оттуда же. Меняется только раскладка: заголовков колонок нет, сортировка
 * чипами; повторный тап меняет направление, по умолчанию — период от новых к старым.
 */
import { useMemo, useState } from 'react'
import { T, RK_STATUS, SERVICE_DOT, billing, periodOf, visibleCampaigns } from './CampaignsScreen'
import { periodLabel } from '../lib/ui'

const nf = v => Number(v || 0).toLocaleString('ru-RU')
const pctOf = c => (c.plan ? Math.round((c.fact || 0) / c.plan * 100) : null)
const bill = c => (c.fact ? billing(c.fact, c.cpm) : 0)

/* Ключ сортировки периода — месяц и старт флайта: внутри месяца раньше начавшаяся
   кампания стоит ниже, как в хронологии. */
const flightKey = c => periodOf(c) + (c.flight || '').slice(0, 5).split('.').reverse().join('')

const SORTS = [
  ['period', 'Период', flightKey],
  ['fact', 'Факт', c => c.fact || 0],
  ['pct', '% плана', c => pctOf(c) ?? -1],
  ['bill', 'Биллинг', bill],
]

const cap = { fontFamily: T.mono, fontSize: 9.5, fontWeight: 700, letterSpacing: '.08em',
  textTransform: 'uppercase', color: T.t4 }

export default function CampaignsMobile({ campaigns = [] }) {
  const [sort, setSort] = useState('period')
  const [dir, setDir] = useState(-1)
  const [open, setOpen] = useState(null)

  const all = useMemo(() => visibleCampaigns(campaigns), [campaigns])
  const list = useMemo(() => {
    const key = SORTS.find(s => s[0] === sort)[2]
    return [...all].sort((a, b) => {
      const x = key(a), y = key(b)
      return (x > y ? 1 : x < y ? -1 : 0) * dir
    })
  }, [all, sort, dir])

  const tot = {
    fact: all.reduce((a, c) => a + (c.fact || 0), 0),
    bill: all.reduce((a, c) => a + bill(c), 0),
    erid: all.filter(c => c.erid).length,
  }
  const pick = (k) => {
    if (k === sort) setDir(-dir)
    else { setSort(k); setDir(-1) }
    setOpen(null)
  }

  const box = { background: T.card, border: `1px solid ${T.border}`, borderRadius: 16,
    boxShadow: T.shadow }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontFamily: T.sans }}>
      <div style={{ ...box, padding: '14px 14px 12px' }}>
        <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em' }}>Кампании</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', marginTop: 12 }}>
          {[['показы', nf(tot.fact)], ['биллинг', nf(tot.bill) + ' ₽'],
            ['ЕРИД', `${tot.erid} из ${all.length}`]].map(([l, v], i) => (
            <div key={l} style={{ paddingLeft: i ? 10 : 0, marginLeft: i ? 10 : 0,
              borderLeft: i ? `1px solid ${T.row}` : 'none', minWidth: 0 }}>
              <div style={cap}>{l}</div>
              <div style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, marginTop: 5,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 2 }}>
        {SORTS.map(([k, label]) => {
          const on = k === sort
          return (
            <button key={k} onClick={() => pick(k)}
              style={{ minHeight: 40, padding: '0 14px', borderRadius: 100, cursor: 'pointer',
                flex: '0 0 auto', fontFamily: T.sans, fontSize: 13, fontWeight: 700,
                border: `1px solid ${on ? T.accentBorder : T.border}`,
                background: on ? T.accentTint : T.card, color: on ? T.accent : T.t2 }}>
              {label}{on ? (dir < 0 ? ' ↓' : ' ↑') : ''}
            </button>
          )
        })}
      </div>

      {list.map((c, i) => {
        const [stBg, stFg, stBd] = RK_STATUS[c.status] || [T.subtle, T.t3, T.border]
        const pct = pctOf(c)
        const col = !c.fact ? T.t5 : pct >= 90 ? T.income : T.danger
        const isOpen = open === i
        return (
          <div key={`${c.brand}|${c.flight}|${c.site}|${i}`}
            style={{ ...box, padding: '12px 14px',
              borderColor: isOpen ? T.accentBorder : T.border }}>
            <div onClick={() => setOpen(isOpen ? null : i)} style={{ cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, marginTop: 6,
                  flex: '0 0 7px', background: c.status === 'отказ' ? T.t5
                    : (SERVICE_DOT[c.service] || T.accent) }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{c.brand}</div>
                  <div style={{ fontFamily: T.mono, fontSize: 11, color: T.t3, marginTop: 2 }}>
                    {c.flight} · {periodLabel(periodOf(c))}
                  </div>
                </span>
                <span style={{ background: stBg, color: stFg, border: `1px solid ${stBd}`,
                  borderRadius: 7, padding: '3px 8px', fontSize: 11, fontWeight: 700,
                  whiteSpace: 'nowrap' }}>{c.status}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
                <span style={{ flex: 1, height: 6, borderRadius: 4, background: T.subtle,
                  overflow: 'hidden' }}>
                  {!!c.fact && pct !== null && (
                    <span style={{ display: 'block', height: '100%',
                      width: `${Math.min(100, pct)}%`, background: col }} />
                  )}
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700,
                  color: c.fact ? col : T.t5, minWidth: 36, textAlign: 'right' }}>
                  {c.fact && pct !== null ? `${pct}%` : '—'}
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                  minWidth: 92, textAlign: 'right' }}>
                  {c.fact ? nf(bill(c)) + ' ₽' : '—'}
                </span>
                <span style={{ color: T.t4, fontSize: 11 }}>{isOpen ? '▴' : '▾'}</span>
              </div>
            </div>
            {isOpen && (
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${T.row}`,
                display: 'flex', flexDirection: 'column', gap: 7 }}>
                {[['Площадка', c.site || '—', T.t1, T.sans],
                  ['Услуга', [c.service, c.surface].filter(Boolean).join(' · '), T.t1, T.sans],
                  ['Факт показов', c.fact ? nf(c.fact) : '—', c.fact ? T.t1 : T.t5, T.mono],
                  ['План показов', c.plan ? nf(c.plan) : '—', c.plan ? T.t2 : T.t5, T.mono],
                  ['Расчётный биллинг', c.fact ? nf(bill(c)) + ' ₽' : '—',
                    c.fact ? T.t1 : T.t5, T.mono],
                  ['ЕРИД', c.erid || 'не выпущен', c.erid ? T.accent : T.t5, T.mono],
                  ['Период', periodLabel(periodOf(c)), T.t2, T.mono],
                ].map(([label, value, fg, font]) => (
                  <div key={label} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <span style={{ ...cap, flex: '0 0 118px' }}>{label}</span>
                    <span style={{ fontFamily: font, fontSize: 12.5, color: fg,
                      wordBreak: 'break-word' }}>{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      {!list.length && (
        <div style={{ ...box, padding: 20, textAlign: 'center', fontSize: 13, color: T.t3 }}>
          Кампаний пока нет.
        </div>
      )}

      <div style={{ ...cap, fontSize: 9.5, lineHeight: 1.6, padding: '0 4px' }}>
        {nf(tot.fact)} показов · {nf(tot.bill)} ₽ · ЕРИД {tot.erid} из {all.length} · суммы до НДС
      </div>
    </div>
  )
}
