import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { grp, mln, signRub, bankColor } from '../../lib/salesFormat'
import { CARD, monoLbl, Marker } from './kit'

// Мобильный ДДС (< 1024px) по хендоффу design_handoff_cashflow_mobile.
// Данные считаются в pages/dashboard.js — компонент только рисует.
const RUB = (n) => grp(n || 0)
const mln2 = (n) => mln(n || 0, 2)
// mln1 — «max 1 знак, без обязательного дробного» (для осей/подписей ДДС); отличается от общего mln(,1).
const mln1 = (n) => ((n || 0) / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 })
const signMln = (n) => `${n >= 0 ? '+' : '−'}${mln1(Math.abs(n))} млн`

const MONTH_SHORT = { '01': 'янв', '02': 'фев', '03': 'мар', '04': 'апр', '05': 'май', '06': 'июн', '07': 'июл', '08': 'авг', '09': 'сен', '10': 'окт', '11': 'ноя', '12': 'дек' }
const shortMonth = (p) => { if (!p) return '—'; const [, m] = String(p).split('-'); return MONTH_SHORT[m] || m }
const capMonth = (p) => { const s = shortMonth(p); return s.charAt(0).toUpperCase() + s.slice(1) }
const formatPeriod = (p) => { if (!p) return '—'; const [y, m] = String(p).split('-'); return `${MONTH_SHORT[m] || m} ${y}` }
const rangeShort = (from, to) => { const one = (p) => { if (!p) return ''; const [y] = String(p).split('-'); return `${capMonth(p)} ${y.slice(2)}` }; return `${one(from)} — ${one(to)}` }

const INCOME = '#2FA37C', OUTFLOW = '#8B93A6', EMPTY = 'var(--border-inner)', FACT = '#4F6CE6', FORECAST = '#A9B6F2'
const WARN_TXT = '#B26A0C', DANGER_TXT = '#C93A3E'

function Kpi({ label, val, unit, color, badge, sub }) {
  return (
    <div style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={monoLbl}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, letterSpacing: '-.03em', color, whiteSpace: 'nowrap' }}>{val}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
      </div>
      <div style={{ minHeight: 18 }}>
        {badge ? <span style={{ display: 'inline-block', background: 'var(--warning-tint)', color: WARN_TXT, borderRadius: 6, padding: '2px 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>{badge}</span>
          : <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{sub}</span>}
      </div>
    </div>
  )
}

// Столбец недели: приход вверх / расход вниз (по 10 ячеек)
function CashBar({ income, expense, scale, selected, onClick }) {
  const inc = income > 0 ? Math.max(1, Math.round(income / scale * 10)) : 0
  const exp = expense > 0 ? Math.max(1, Math.round(expense / scale * 10)) : 0
  return (
    <div onClick={onClick} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2, cursor: 'pointer', background: selected ? '#F0F3FF' : 'transparent', borderRadius: 4, padding: '2px 0', transition: 'background .15s' }}>
      <div style={{ display: 'flex', flexDirection: 'column-reverse', gap: 1, height: 56 }}>
        {Array.from({ length: 10 }, (_, i) => <div key={i} style={{ flex: 1, borderRadius: 2, background: i < inc ? INCOME : EMPTY }} />)}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, height: 56 }}>
        {Array.from({ length: 10 }, (_, i) => <div key={i} style={{ flex: 1, borderRadius: 2, background: i < exp ? OUTFLOW : EMPTY }} />)}
      </div>
    </div>
  )
}

// Ось X: подписи месяцев, каждая вторая
function MonthAxis({ months }) {
  return (
    <div style={{ display: 'flex' }}>
      {months.map((m, i) => <span key={i} style={{ flex: 1, textAlign: 'center', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{i % 2 === 0 ? capMonth(m.period) : ''}</span>)}
    </div>
  )
}

export default function CashflowMobile({
  dateFrom, dateTo, setDateFrom, setDateTo, groupBy, setGroupBy,
  kpi, cashWeeks, cashScale, cumWeeks, cumScale, accounts, months, totals,
  expanded, setExpanded, exportCsv,
}) {
  const [updated] = useState(() => { try { return new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) } catch (e) { return '' } })
  const [selWeek, setSelWeek] = useState(null)
  const [periodOpen, setPeriodOpen] = useState(false)
  const sel = selWeek != null ? cashWeeks[selWeek] : null

  const seg = (active) => ({ border: 'none', borderRadius: 8, padding: '6px 14px', whiteSpace: 'nowrap', fontFamily: UI, fontSize: 13, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
      <style>{`@keyframes ddsRise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@media (prefers-reduced-motion:reduce){[style*="animation"]{animation:none!important}}`}</style>

      {/* заголовок + обновлено */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
        <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--text-primary)' }}>Движение денег</span>
        <span style={monoLbl}>обновлено {updated}</span>
      </div>

      {/* фильтры: период + сегмент */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, position: 'relative' }}>
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
        <div style={{ marginLeft: 'auto', display: 'inline-flex', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, background: 'var(--bg-card)' }}>
          <button onClick={() => setGroupBy('period')} style={seg(groupBy === 'period')}>Период</button>
          <button onClick={() => setGroupBy('date')} style={seg(groupBy === 'date')}>Дата</button>
        </div>
      </div>

      {/* KPI 2×2 */}
      <div style={{ ...CARD, animation: 'ddsRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: '.07s' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Актуальный баланс" val={mln2(kpi.actualBalance)} unit="млн ₽" color={kpi.actualBalance >= 0 ? INCOME : DANGER_TXT} sub={`${kpi.accountsCount} источника`} />
          </div>
          <div style={{ borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Прогнозный баланс" val={mln2(kpi.forecastBalance)} unit="млн ₽" color={FACT} badge={`${signMln(kpi.forecastDelta)} к тек.`} />
          </div>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi label="План поступлений" val={mln2(kpi.planIncome)} unit="млн ₽" color="var(--text-primary)" sub={`${kpi.incomeCount} операций`} />
          </div>
          <div>
            <Kpi label="План расходов" val={mln2(kpi.planExpense)} unit="млн ₽" color="var(--text-primary)" sub={`${kpi.expenseCount} операций`} />
          </div>
        </div>
      </div>

      {/* По неделям */}
      <div style={{ ...CARD, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, animation: 'ddsRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: '.14s' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>По неделям</span>
          <span style={{ display: 'flex', gap: 12, fontSize: 10, color: 'var(--text-muted)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Marker c={INCOME} />приход</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Marker c={OUTFLOW} />расход</span>
          </span>
        </div>
        <div style={{ background: '#F6F8FF', borderRadius: 12, padding: '10px 12px', minHeight: 44, display: 'flex', alignItems: 'center', gap: 10 }}>
          {sel ? (<>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>{sel.monthLabel} · неделя {sel.week}</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>
              <span style={{ color: INCOME }}>+{RUB(sel.income)} ₽</span>
              <span style={{ color: 'var(--text-secondary)' }}>−{RUB(sel.expense)} ₽</span>
            </span>
          </>) : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>нажмите на столбец</span>}
        </div>
        <div style={{ display: 'flex', gap: 2, alignItems: 'stretch' }}>
          {cashWeeks.map((w, i) => <CashBar key={i} income={w.income} expense={w.expense} scale={cashScale} selected={selWeek === i} onClick={() => setSelWeek(selWeek === i ? null : i)} />)}
        </div>
        <MonthAxis months={months} />
      </div>

      {/* Счета */}
      <div style={{ ...CARD, padding: '14px 14px 10px', animation: 'ddsRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: '.21s' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Счета</span>
          <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>остаток</span>
        </div>
        {accounts.map(b => (
          <div key={b.bank} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
            <Marker c={bankColor(b.bank)} size={8} />
            <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.bank}</span>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{RUB(b.balance)} ₽</span>
          </div>
        ))}
        {accounts.length === 0 && <div style={{ padding: 16, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет счетов</div>}
      </div>

      {/* Накопительный остаток */}
      <div style={{ ...CARD, padding: 16, display: 'flex', flexDirection: 'column', gap: 10, animation: 'ddsRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: '.28s' }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Накопительный остаток</span>
        <div style={{ display: 'flex', gap: 1, height: 96, alignItems: 'stretch' }}>
          {cumWeeks.map((w, i) => {
            const n = w.value > 0 ? Math.max(1, Math.round(w.value / cumScale * 12)) : 0
            const color = w.isForecast ? FORECAST : FACT
            return (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column-reverse', gap: 1 }}>
                {Array.from({ length: 12 }, (_, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: j < n ? color : EMPTY }} />)}
              </div>
            )
          })}
        </div>
        <MonthAxis months={months} />
      </div>

      {/* Детализация по месяцам */}
      <div style={{ ...CARD, padding: '14px 14px 8px', display: 'flex', flexDirection: 'column', animation: 'ddsRise .4s cubic-bezier(0.22,1,0.36,1) both', animationDelay: '.35s' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Детализация по месяцам</span>
          <button onClick={exportCsv} aria-label="Выгрузить в Excel" style={{ width: 32, height: 32, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
          </button>
        </div>
        {months.map(m => {
          const open = expanded === m.period
          return (
            <div key={m.period} style={{ borderBottom: '1px solid var(--border-row)' }}>
              <div onClick={() => setExpanded(open ? null : m.period)} style={{ display: 'grid', gridTemplateColumns: '1fr auto 14px', gap: 10, alignItems: 'center', padding: '10px 8px', borderRadius: 10, cursor: 'pointer', background: open ? '#F6F8FF' : 'transparent' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{formatPeriod(m.period)}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, marginTop: 2 }}>
                    <span style={{ color: INCOME }}>+{mln1(m.income)} млн</span>
                    <span style={{ color: 'var(--text-muted)' }}> · −{mln1(m.expense)} млн</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: m.net >= 0 ? INCOME : DANGER_TXT }}>{signMln(m.net)}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--accent)', marginTop: 2 }}>ост. {mln1(m.cumulative)} млн</div>
                </div>
                <span style={{ color: 'var(--text-faint)', fontSize: 10, textAlign: 'center' }}>{open ? '▴' : '▾'}</span>
              </div>
              {open && (
                <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: '4px 10px', animation: 'ddsRise .24s cubic-bezier(0.22,1,0.36,1) both' }}>
                  {Object.entries(m.by_bank || {}).map(([bank, d]) => {
                    const net = d.net ?? (d.income - d.expense)
                    return (
                      <div key={bank} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
                        <Marker c={bankColor(bank)} />
                        <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bank}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>+{RUB(d.income)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: net >= 0 ? INCOME : DANGER_TXT, minWidth: 74, textAlign: 'right' }}>{signRub(net)}</span>
                      </div>
                    )
                  })}
                  {Object.keys(m.by_bank || {}).length === 0 && <div style={{ padding: 10, fontSize: 12, color: 'var(--text-muted)' }}>Нет разбивки по банкам</div>}
                </div>
              )}
            </div>
          )
        })}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, marginTop: 4, borderTop: '1px solid var(--border-inner)' }}>
          <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого</span>
          <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent)' }}>{RUB(totals.lastCum)} ₽</span>
        </div>
      </div>
    </div>
  )
}
