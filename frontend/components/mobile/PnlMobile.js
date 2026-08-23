import { useState } from 'react'
import { MONO } from '../salesTableKit'
import { grp0 as fmt, mln } from '../../lib/salesFormat'
import { monoLbl, rise } from './kit'
import ReportShell, { ReportSection } from './ReportShell'

// Мобильный P&L (< 1024px). Десктоп — широкая таблица «периоды в колонках»;
// на мобиле список групп с итогом за весь выбранный диапазон и раскрытием
// в подгруппы/статьи — тот же приём, что в FinReportMobile (тот же класс
// данных: группа → подгруппа → статья, но эндпоинт /reports/pl отдельный,
// поле группы — g.group, а не g.key, и суммы лежат в totals[p].income/expense).
// Данные и расчёт (periods/groups/summary) приходят из pages/finance/pnl.js —
// компонент только сводит их к сумме за диапазон и рисует.
const mlnK = (n) => mln(n || 0, 2)

const MONTH_SHORT = { '01':'янв','02':'фев','03':'мар','04':'апр','05':'май','06':'июн','07':'июл','08':'авг','09':'сен','10':'окт','11':'ноя','12':'дек' }
const capMonth = (p) => { if (!p) return '—'; const [, m] = String(p).split('-'); const s = MONTH_SHORT[m] || m; return s.charAt(0).toUpperCase() + s.slice(1) }
const rangeShort = (from, to) => { const one = (p) => { if (!p) return ''; const [y] = String(p).split('-'); return `${capMonth(p)} ${y.slice(2)}` }; return `${one(from)} — ${one(to)}` }

// Итоговые строки вставляются сразу после соответствующей группы — тот же
// порядок, что в pages/finance/pnl.js (СЕБЕСТОИМОСТЬ → валовая, МАРКЕТИНГ → EBITDA, НАЛОГИ → чистая).
const TOTALS_AFTER = {
  'СЕБЕСТОИМОСТЬ': { label: 'Валовая прибыль', field: 'gross_profit', margin: 'gross_margin' },
  'МАРКЕТИНГ':     { label: 'EBITDA',           field: 'ebitda',       margin: 'ebitda_margin' },
  'НАЛОГИ':        { label: 'Чистая прибыль',   field: 'net_profit',   margin: 'net_margin' },
}

const sumSummary = (periods, summary, field) => periods.reduce((s, p) => s + (summary[p]?.[field] || 0), 0)
// Сумма группы за диапазон: ВЫРУЧКА складывается по income, остальные группы — по expense
// (то же правило, что isIncome в pages/finance/pnl.js).
const sumGroup = (periods, totals, isIncome) => periods.reduce((s, p) => s + (isIncome ? (totals[p]?.income || 0) : (totals[p]?.expense || 0)), 0)

function Kpi({ label, val, unit, color }) {
  return (
    <div style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={monoLbl}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-.03em', color, whiteSpace: 'nowrap' }}>{val}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
      </div>
    </div>
  )
}

// Строка промежуточного/финального итога (валовая/EBITDA/чистая прибыль).
// Маржа за диапазон не считается — это не среднее помесячных %, а сумма/сумма;
// десктоп в колонке ИТОГО тоже пишет «—» (pages/finance/pnl.js:111), здесь так же.
function TotalRow({ label, val, showMargin, strong }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                  padding: '10px 8px', background: strong ? 'var(--accent-tint)' : 'var(--bg-subtle)', borderRadius: 10 }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{label}</span>
      <span style={{ textAlign: 'right' }}>
        <div style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: val >= 0 ? 'var(--income)' : 'var(--expense)' }}>{fmt(val)} ₽</div>
        {showMargin && <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>маржа —</div>}
      </span>
    </div>
  )
}

function GroupRow({ g, periods, open, onToggle }) {
  const isIncome = g.group === 'ВЫРУЧКА'
  const total = sumGroup(periods, g.totals, isIncome)
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div onClick={onToggle} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 8px', borderRadius: 10, cursor: 'pointer', background: open ? '#F6F8FF' : 'transparent' }}>
        <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{g.group}</span>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(total)} ₽</span>
        <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
      </div>
      {open && (
        <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: '4px 10px', ...rise(0, '.24s') }}>
          {(g.subgroups || []).map((sg, i) => (
            <div key={sg.subgroup || i}>
              {sg.subgroup && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0 4px' }}>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sg.subgroup}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)' }}>{fmt(sumGroup(periods, sg.totals, isIncome))} ₽</span>
                </div>
              )}
              {sg.articles.map(a => {
                const artTotal = periods.reduce((s, p) => s + (isIncome ? (a.periods[p]?.income || 0) : (a.periods[p]?.expense || 0)), 0)
                return (
                  <div key={a.article} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', paddingLeft: sg.subgroup ? 12 : 0, borderTop: '1px solid var(--border-inner)' }}>
                    <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.article}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)' }}>{artTotal > 0 ? fmt(artTotal) + ' ₽' : '—'}</span>
                  </div>
                )
              })}
            </div>
          ))}
          {(g.subgroups || []).length === 0 && <div style={{ padding: '8px 0', fontSize: 12, color: 'var(--text-muted)' }}>Нет статей</div>}
        </div>
      )}
    </div>
  )
}

export default function PnlMobile({
  dateFrom, setDateFrom, dateTo, setDateTo, data,
}) {
  const [expanded, setExpanded] = useState({})
  const [periodOpen, setPeriodOpen] = useState(false)
  const { periods, groups, summary } = data

  const filters = (
    <>
      <button onClick={() => setPeriodOpen(o => !o)} style={{ flex: '0 0 auto', height: 38, border: `1px solid ${periodOpen ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '0 12px', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>
        {rangeShort(dateFrom, dateTo)} ▾
      </button>
      {periodOpen && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setPeriodOpen(false)} />
        <div style={{ position: 'absolute', top: 44, left: 0, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ border: '1px solid var(--border-card)', borderRadius: 8, padding: '7px 8px', fontSize: 12, fontFamily: MONO, outline: 'none' }} />
          <span style={{ color: 'var(--text-faint)' }}>—</span>
          <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ border: '1px solid var(--border-card)', borderRadius: 8, padding: '7px 8px', fontSize: 12, fontFamily: MONO, outline: 'none' }} />
        </div>
      </>)}
    </>
  )

  const revenueGroup = groups.find(g => g.group === 'ВЫРУЧКА')
  const revenue = revenueGroup ? sumGroup(periods, revenueGroup.totals, true) : 0
  const grossProfit = sumSummary(periods, summary, 'gross_profit')
  const ebitda = sumSummary(periods, summary, 'ebitda')
  const netProfit = sumSummary(periods, summary, 'net_profit')

  return (
    <ReportShell title="P&L" meta={rangeShort(dateFrom, dateTo)} filters={filters}>
      {/* KPI 2×2 */}
      <ReportSection padded={false}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Выручка" val={mlnK(revenue)} unit="млн ₽" color="var(--text-primary)" />
          </div>
          <div style={{ borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Валовая прибыль" val={mlnK(grossProfit)} unit="млн ₽" color={grossProfit >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi label="EBITDA" val={mlnK(ebitda)} unit="млн ₽" color={ebitda >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
          <div>
            <Kpi label="Чистая прибыль" val={mlnK(netProfit)} unit="млн ₽" color={netProfit >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
        </div>
      </ReportSection>

      {/* Группы P&L со сворачиванием в статьи, итог за весь выбранный период.
          Группа «НЕ В P&L» на мобиле не появляется по той же причине, что и на
          десктопе: /reports/pl её не отдаёт (см. reports.py). */}
      <ReportSection title="Статьи" padding="14px 14px 8px" gap={6} aside={<span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{rangeShort(dateFrom, dateTo)}</span>}>
        <div>
          {groups.map(g => {
            const t = TOTALS_AFTER[g.group]
            return (
              <div key={g.group}>
                <GroupRow g={g} periods={periods} open={!!expanded[g.group]} onToggle={() => setExpanded(prev => ({ ...prev, [g.group]: !prev[g.group] }))} />
                {t && (
                  <div style={{ padding: '6px 0' }}>
                    <TotalRow label={t.label} val={sumSummary(periods, summary, t.field)} showMargin strong />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </ReportSection>
    </ReportShell>
  )
}
