import { useState } from 'react'
import { MONO } from '../salesTableKit'
import { grp, mln } from '../../lib/salesFormat'
import { monoLbl, rise } from './kit'
import ReportShell, { ReportSection } from './ReportShell'

// Мобильный план-факт (< 1024px). Десктоп — таблица «план / факт / отклонение
// / % выполнения» в колонках; на узком экране колонки не помещаются, поэтому
// пара план/факт ставится строкой: наименование сверху, под ним
// план · факт · отклонение моноширинным (см. бриф задачи 5, шаг 3).
// Данные (groups/summary) приходят из pages/finance/plan-fact.js — компонент
// только сводит их и рисует, арифметика (diff/pct) уже посчитана на сервере.
const fmt = (n) => grp(n || 0)
const mlnK = (n) => mln(n || 0, 2)
const fmtPct = (n) => (n === null || n === undefined) ? '—' : n.toFixed(1) + '%'

const MONTH_SHORT = { '01':'янв','02':'фев','03':'мар','04':'апр','05':'май','06':'июн','07':'июл','08':'авг','09':'сен','10':'окт','11':'ноя','12':'дек' }
const capMonth = (p) => { if (!p) return '—'; const [, m] = String(p).split('-'); const s = MONTH_SHORT[m] || m; return s.charAt(0).toUpperCase() + s.slice(1) }
const rangeShort = (from, to) => { const one = (p) => { if (!p) return ''; const [y] = String(p).split('-'); return `${capMonth(p)} ${y.slice(2)}` }; return `${one(from)} — ${one(to)}` }

// Цвет % выполнения: для доходов хорошо когда факт >= план, для расходов — наоборот.
// Та же логика (и те же пороги), что pctColor в pages/finance/plan-fact.js.
const pctColor = (pct, isIncome) => {
  if (pct === null || pct === undefined) return 'var(--text-faint)'
  if (isIncome) {
    if (pct >= 100) return 'var(--income)'
    if (pct >= 90) return 'var(--dot-current-dz)'
    return 'var(--expense)'
  }
  if (pct <= 100) return 'var(--income)'
  if (pct <= 110) return 'var(--dot-current-dz)'
  return 'var(--expense)'
}

function Kpi({ label, plan, fact, pct, isIncome }) {
  const diff = fact - plan
  return (
    <div style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={monoLbl}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, letterSpacing: '-.03em', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{mlnK(fact)}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>млн ₽</span>
        {pct !== undefined && <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: pctColor(pct, isIncome) }}>{fmtPct(pct)}</span>}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>
        план {mlnK(plan)} млн {pct !== undefined && <>· <span style={{ color: diff >= 0 ? 'var(--income)' : 'var(--expense)' }}>{diff >= 0 ? '+' : ''}{mlnK(diff)}</span></>}
      </div>
    </div>
  )
}

// Строка «план · факт · отклонение» — наименование сверху, значения строкой снизу,
// моноширинным. % выполнения — справа отдельным блоком.
function PfRow({ label, plan, fact, diff, pct, isIncome, weight, size, color, bg, pad }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: pad || '8px 8px', background: bg, borderRadius: bg ? 10 : 0 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: size || 13, fontWeight: weight || 600, color: color || 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
        <div style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', marginTop: 2 }}>
          план {plan > 0 ? fmt(plan) : '—'} · факт {fact > 0 ? fmt(fact) : '—'}
          {!!(plan || fact) && <> · <span style={{ color: diff >= 0 ? 'var(--income)' : 'var(--expense)' }}>{diff >= 0 ? '+' : ''}{fmt(diff)}</span></>}
        </div>
      </div>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: pctColor(pct, isIncome), flexShrink: 0 }}>{fmtPct(pct)}</span>
    </div>
  )
}

function GroupRow({ g, open, onToggle }) {
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', borderRadius: 10, background: open ? '#F6F8FF' : 'transparent' }}>
        <PfRow label={`${open ? '▾' : '▸'} ${g.group}`} plan={g.totals.plan} fact={g.totals.fact} diff={g.totals.diff} pct={g.totals.pct} isIncome={g.is_income} weight={700} size={13.5} />
      </div>
      {open && (
        <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: '4px 10px', ...rise(0, '.24s') }}>
          {(g.subgroups || []).map((sg, i) => (
            <div key={sg.subgroup || i}>
              {sg.subgroup && (
                <PfRow label={sg.subgroup} plan={sg.totals.plan} fact={sg.totals.fact} diff={sg.totals.diff} pct={sg.totals.pct} isIncome={g.is_income} weight={700} size={11.5} color="var(--text-secondary)" pad="8px 0 4px" />
              )}
              {sg.articles.map(a => (
                <div key={a.article} style={{ borderTop: '1px solid var(--border-inner)', paddingLeft: sg.subgroup ? 12 : 0 }}>
                  <PfRow label={a.article} plan={a.plan} fact={a.fact} diff={a.diff} pct={a.pct} isIncome={g.is_income} weight={400} size={12} color="var(--text-muted)" pad="6px 0" />
                </div>
              ))}
            </div>
          ))}
          {(g.subgroups || []).length === 0 && <div style={{ padding: '8px 0', fontSize: 12, color: 'var(--text-muted)' }}>Нет статей</div>}
        </div>
      )}
    </div>
  )
}

export default function PlanFactMobile({
  dateFrom, setDateFrom, dateTo, setDateTo, data,
}) {
  const [expanded, setExpanded] = useState({})
  const [periodOpen, setPeriodOpen] = useState(false)
  const { groups, summary } = data

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

  return (
    <ReportShell title="План / Факт" meta={rangeShort(dateFrom, dateTo)} filters={filters}>
      {/* KPI: выручка / расходы / чистая прибыль — план и факт строкой, как в остальных карточках */}
      <ReportSection padded={false}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Выручка" plan={summary.plan_income} fact={summary.fact_income} pct={summary.pct_income} isIncome />
          </div>
          <div style={{ borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Расходы" plan={summary.plan_expense} fact={summary.fact_expense} pct={summary.pct_expense} isIncome={false} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <Kpi label="Чистая прибыль" plan={summary.plan_net} fact={summary.fact_net} />
          </div>
        </div>
      </ReportSection>

      {/* Группы со сворачиванием в статьи */}
      <ReportSection title="Статьи" padding="14px 14px 8px" gap={6} aside={<span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{rangeShort(dateFrom, dateTo)}</span>}>
        <div>
          {groups.map(g => (
            <GroupRow key={g.group} g={g} open={!!expanded[g.group]} onToggle={() => setExpanded(prev => ({ ...prev, [g.group]: !prev[g.group] }))} />
          ))}
        </div>
      </ReportSection>
    </ReportShell>
  )
}
