import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { grp0 as fmt, mln, pctDot as fmtPct } from '../../lib/salesFormat'
import { monoLbl, Marker, rise } from './kit'
import ReportShell, { ReportSection } from './ReportShell'

// Мобильный финотчёт (< 1024px). Десктоп показывает широкую таблицу «периоды
// в колонках» — на мобиле это не воспроизводимо без горизонтальной прокрутки,
// поэтому вместо неё список групп с итогом за весь выбранный период и
// раскрытием в подгруппы/статьи (тот же способ показать те же данные).
// Данные и расчёт (periods/groups/summary/control) приходят из pages/finance/report.js —
// компонент только сводит их к сумме за диапазон и рисует.
const mlnK = (n) => mln(n || 0, 2)

const MONTH_SHORT = { '01':'янв','02':'фев','03':'мар','04':'апр','05':'май','06':'июн','07':'июл','08':'авг','09':'сен','10':'окт','11':'ноя','12':'дек' }
const capMonth = (p) => { if (!p) return '—'; const [, m] = String(p).split('-'); const s = MONTH_SHORT[m] || m; return s.charAt(0).toUpperCase() + s.slice(1) }
const rangeShort = (from, to) => { const one = (p) => { if (!p) return ''; const [y] = String(p).split('-'); return `${capMonth(p)} ${y.slice(2)}` }; return `${one(from)} — ${one(to)}` }

// Сумма поля из summary по всем периодам диапазона — то же самое, что колонка
// «ИТОГО» на десктопе, просто без промежуточных периодов.
const sumField = (periods, summary, field) => periods.reduce((s, p) => s + (summary[p]?.[field] || 0), 0)
const sumTotals = (periods, totals) => periods.reduce((s, p) => s + (totals[p] || 0), 0)

const TOTALS_AFTER = {
  cogs:       { label: 'Валовая прибыль',      field: 'gross_profit',     margin: 'gross_margin' },
  marketing:  { label: 'Операционная прибыль', field: 'operating_profit', margin: 'operating_margin' },
}

function Kpi({ label, val, unit, color, sub }) {
  return (
    <div style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={monoLbl}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-.03em', color, whiteSpace: 'nowrap' }}>{val}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
      </div>
      <div style={{ minHeight: 16, fontSize: 11, color: 'var(--text-faint)' }}>{sub}</div>
    </div>
  )
}

// Строка промежуточного/финального итога (валовая/операционная/чистая прибыль).
// showMargin — строка «маржа» присутствует у валовой/операционной/чистой прибыли; сама
// маржа за диапазон здесь не считается (это не среднее помесячных %, а сумма/сумма —
// десктоп в колонке ИТОГО тоже не считает её и рисует «—», см. pages/finance/report.js:212).
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
  const total = sumTotals(periods, g.totals)
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div onClick={onToggle} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 8px', borderRadius: 10, cursor: 'pointer', background: open ? '#F6F8FF' : 'transparent' }}>
        <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{g.label}</span>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(total)} ₽</span>
        <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
      </div>
      {open && (
        <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: '4px 10px', ...rise(0, '.24s') }}>
          {g.subgroups.map((sg, i) => (
            <div key={sg.subgroup || i}>
              {sg.subgroup && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0 4px' }}>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sg.subgroup}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)' }}>{fmt(sumTotals(periods, sg.totals))} ₽</span>
                </div>
              )}
              {sg.articles.map(a => (
                <div key={a.article} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', paddingLeft: sg.subgroup ? 12 : 0, borderTop: '1px solid var(--border-inner)' }}>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.article}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)' }}>{fmt(sumTotals(periods, a.periods))} ₽</span>
                </div>
              ))}
            </div>
          ))}
          {g.subgroups.length === 0 && <div style={{ padding: '8px 0', fontSize: 12, color: 'var(--text-muted)' }}>Нет статей</div>}
        </div>
      )}
    </div>
  )
}

export default function FinReportMobile({
  basis, setBasis, vat, setVat, dateFrom, setDateFrom, dateTo, setDateTo,
  data, exportXlsx,
}) {
  const [expanded, setExpanded] = useState({})
  const [periodOpen, setPeriodOpen] = useState(false)
  const { periods, groups, summary, control } = data

  const seg = (active) => ({ flex: 1, border: 'none', borderRadius: 8, padding: '7px 0', fontFamily: UI, fontSize: 12.5, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })

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
      <button onClick={exportXlsx} aria-label="Выгрузить в Excel" style={{ marginLeft: 'auto', width: 38, height: 38, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
      </button>
    </>
  )

  const basisVat = (
    <div style={{ display: 'flex', gap: 6, width: '100%' }}>
      <div style={{ display: 'inline-flex', flex: 1, border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, background: 'var(--bg-card)' }}>
        <button onClick={() => setBasis('accrual')} style={seg(basis === 'accrual')}>Начисление</button>
        <button onClick={() => setBasis('cash')} style={seg(basis === 'cash')}>Оплата</button>
      </div>
      <div style={{ display: 'inline-flex', flex: 1, border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, background: 'var(--bg-card)' }}>
        <button onClick={() => setVat('net')} style={seg(vat === 'net')}>Без НДС</button>
        <button onClick={() => setVat('gross')} style={seg(vat === 'gross')}>С НДС</button>
      </div>
    </div>
  )

  const grossProfit = sumField(periods, summary, 'gross_profit')
  const operatingProfit = sumField(periods, summary, 'operating_profit')
  const profitBeforeTax = sumField(periods, summary, 'profit_before_tax')
  const netProfit = sumField(periods, summary, 'net_profit')
  // Маржа за диапазон в итоговых строках — см. showMargin/TotalRow ниже: это не среднее
  // арифметическое помесячных %, а сумма прибыли/сумма выручки; десктоп такую сумму не
  // считает и показывает «—» в колонке ИТОГО (pages/finance/report.js:212), здесь так же.

  return (
    <ReportShell title="Финансовый отчёт" meta={basis === 'accrual' ? 'по начислению' : 'по оплате'} filters={filters}>
      {/* переключатели базы/НДС — отдельной секцией, filters оболочки занят периодом+экспортом */}
      <ReportSection padded padding="10px 12px">
        {basisVat}
      </ReportSection>

      {/* KPI 2×2 */}
      <ReportSection padded={false}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Валовая прибыль" val={mlnK(grossProfit)} unit="млн ₽" color={grossProfit >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
          <div style={{ borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Операционная прибыль" val={mlnK(operatingProfit)} unit="млн ₽" color={operatingProfit >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi label="Прибыль до налога" val={mlnK(profitBeforeTax)} unit="млн ₽" color={profitBeforeTax >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
          <div>
            <Kpi label="Чистая прибыль" val={mlnK(netProfit)} unit="млн ₽" color={netProfit >= 0 ? 'var(--income)' : 'var(--expense)'} sub="маржа —" />
          </div>
        </div>
      </ReportSection>

      {/* Группы P&L со сворачиванием в статьи, итог за весь выбранный период */}
      <ReportSection title="Статьи" padding="14px 14px 8px" gap={6} aside={<span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{rangeShort(dateFrom, dateTo)}</span>}>
        <div>
          {groups.map(g => {
            const t = TOTALS_AFTER[g.key]
            return (
              <div key={g.key}>
                <GroupRow g={g} periods={periods} open={!!expanded[g.key]} onToggle={() => setExpanded(prev => ({ ...prev, [g.key]: !prev[g.key] }))} />
                {t && (
                  <div style={{ padding: '6px 0' }}>
                    <TotalRow label={t.label} val={sumField(periods, summary, t.field)} showMargin strong />
                  </div>
                )}
              </div>
            )
          })}
          <div style={{ padding: '6px 0' }}>
            <TotalRow label="Прибыль до налога" val={profitBeforeTax} />
          </div>
          <div style={{ padding: '6px 0 10px' }}>
            <TotalRow label="Чистая прибыль" val={netProfit} showMargin strong />
          </div>
        </div>
      </ReportSection>

      {/* Контроль — что не вошло в отчёт */}
      {(control.excluded?.length > 0 || !!control.unclassified_total || !!control.zero_vat_rows || !!control.no_period_rows) && (
        <ReportSection title="Контроль" gap={4}>
          <div>
            {(control.excluded || []).map(e => (
              <div key={e.reason} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{e.reason}</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmt(e.amount)} ₽</span>
              </div>
            ))}
            {!!control.unclassified_total && (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12, color: 'var(--warning)' }}>Требует разметки — учтено отдельной строкой</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--warning)', whiteSpace: 'nowrap' }}>{fmt(control.unclassified_total)} ₽</span>
              </div>
            )}
            {vat === 'net' && !!control.zero_vat_rows && (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Необлагаемые, ставка 0 ({control.zero_vat_rows} опер.)</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmt(control.zero_vat_amount)} ₽</span>
              </div>
            )}
            {!!control.no_period_rows && (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ fontSize: 12, color: 'var(--expense)' }}>{basis === 'cash' ? 'Без даты платежа' : 'Без периода'} — не вошли</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--expense)' }}>{control.no_period_rows}</span>
              </div>
            )}
          </div>
        </ReportSection>
      )}
    </ReportShell>
  )
}
