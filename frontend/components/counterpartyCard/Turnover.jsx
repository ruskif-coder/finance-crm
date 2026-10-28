/**
 * «Оборот по месяцам» (хендофф «контрикZ»): пиксельные бары — 18 ячеек на месяц, снизу вверх приход (`--income`), расход
 * (`--bank-sovkom`), пусто (`--border-inner`). Подписи — начала кварталов (с годом у января и у первого месяца), выбранный — синим.
 * Клик по месяцу фильтрует операции, повторный — снимает. Под графиком — итоги за 12 месяцев и доли.
 */
import { MONO } from '@/components/salesTableKit'
import { grpDec } from '@/lib/salesFormat'
import { box, cap, h2, note, money } from '@/components/contractCard/ui'

const CELLS = 18
const MON = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

function label(p, i) {
  const m = Number(p.slice(5, 7))
  if (i !== 0 && (m - 1) % 3 !== 0) return null
  return m === 1 || i === 0 ? `${MON[m - 1]} ${p.slice(2, 4)}` : MON[m - 1]
}

function Bar({ m, max, on, i, onPick }) {
  const inc = Math.round((m.income / max) * CELLS)
  const exp = Math.min(CELLS - inc, Math.round((m.expense / max) * CELLS))
  const cells = Array.from({ length: CELLS }, (_, k) => (k < inc ? 'var(--income)' : k < inc + exp ? 'var(--bank-sovkom)' : 'var(--border-inner)'))
  const lb = label(m.period, i)
  return (
    <span onClick={() => onPick(m.period)} title={`${m.period} · приход ${money(m.income)} · расход ${money(m.expense)}`}
          style={{ position: 'relative', flex: '1 1 0', minWidth: 6, display: 'flex', flexDirection: 'column-reverse', gap: 2, cursor: 'pointer', paddingBottom: 18 }}>
      {cells.map((c, k) => <span key={k} style={{ height: 6, borderRadius: 1.5, background: c, opacity: on === null || on ? 1 : 0.35 }} />)}
      {lb && <span style={{ position: 'absolute', left: 0, bottom: 0, fontFamily: MONO, fontSize: 10, whiteSpace: 'nowrap', color: on ? 'var(--accent)' : 'var(--text-faint)', fontWeight: on ? 700 : 400 }}>{lb}</span>}
    </span>
  )
}

export default function Turnover({ monthly, analytics, month, onMonth }) {
  const max = Math.max(1, ...monthly.map(m => (m.income || 0) + (m.expense || 0)))
  const last12 = monthly.slice(-12)
  const inc12 = last12.reduce((s, m) => s + (m.income || 0), 0)
  const exp12 = last12.reduce((s, m) => s + (m.expense || 0), 0)
  const pct = (v) => (v || v === 0 ? `${grpDec(v, 1)} %` : '—')
  const total = (l, v, sub) => (
    <span style={{ flex: '1 1 0', minWidth: 140, display: 'flex', flexDirection: 'column', gap: 3, padding: '0 14px', borderLeft: '1px solid var(--border-inner)' }}>
      <span style={{ ...cap, whiteSpace: 'normal' }}>{l}</span>
      <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{v}</span>
      {sub && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</span>}
    </span>
  )
  return (
    <section style={{ ...box, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={h2}>Оборот по месяцам</span>
        <span style={note}>{month ? `выбран ${month} — операции ниже отфильтрованы` : 'нажмите на месяц, чтобы отфильтровать операции'}</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12, fontSize: 11.5, color: 'var(--text-secondary)' }}>
          <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: 'var(--income)', marginRight: 5 }} />приход</span>
          <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: 'var(--bank-sovkom)', marginRight: 5 }} />расход</span>
        </span>
      </div>
      {!monthly.length ? <span style={note}>Операций с периодом по месяцам нет.</span> : (
        <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end' }}>
          {monthly.map((m, i) => <Bar key={m.period} m={m} max={max} i={i} on={month ? m.period === month : null} onPick={p => onMonth(p === month ? null : p)} />)}
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', rowGap: 10, marginLeft: -14 }}>
        {total('Приход за 12 мес', money(inc12), `в среднем ${money(inc12 / 12)} в месяц`)}
        {total('Расход за 12 мес', money(exp12))}
        {total('Доля в выручке за 12 мес', pct(analytics && analytics.share_income_12m))}
        {total('Доля в закупках за 12 мес', pct(analytics && analytics.share_expense_12m))}
      </div>
    </section>
  )
}
