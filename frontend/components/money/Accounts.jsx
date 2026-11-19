/** «Счета» (README хендоффа, п. 8). Выписок в системе ещё нет — свежесть по последней проведённой операции банка. */
import { CARD, MONO, f } from './kit'
import { parseDate, diffDays, ddmm } from './model'

const mlnT = (n) => (n / 1e6).toFixed(1).replace('.', ',') + ' млн'

export default function Accounts({ data }) {
  const today = parseDate(data.today)
  return (
    <div data-motion="rise" style={{ ...CARD, gap: 4, '--i': 2 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingBottom: 8 }}>
        <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>Счета</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{f(data.balance_total)} ₽</span>
      </div>
      {data.accounts.map(a => {
        const last = parseDate(a.last_op)
        const age = last ? diffDays(today, last) : null
        const fresh = age != null && age <= 1
        const cash = a.bank === 'Наличные'
        return (
          <div key={a.bank} style={{ display: 'grid', gridTemplateColumns: '30px minmax(0,1fr) auto', gap: '2px 10px', alignItems: 'center',
            padding: '9px 0', borderTop: '1px solid var(--border-row)' }}>
            <span style={{ gridRow: 'span 2', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30,
              borderRadius: 9, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 11,
              fontWeight: 700, color: 'var(--text-secondary)' }}>{a.abbr}</span>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{a.bank}</span>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap',
              color: a.balance < 0 ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{f(a.balance)}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: fresh ? 'var(--text-muted)' : 'var(--attn-fg)' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: fresh ? 'var(--ok)' : 'var(--attn)' }} />
              {last ? `${cash ? 'внесено' : 'последняя операция'} ${age === 0 ? 'сегодня' : age === 1 ? 'вчера' : ddmm(last)}` : 'операций нет'}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)', textAlign: 'right', whiteSpace: 'nowrap' }}>
              {cash ? 'касса · ввод вручную' : `↑ ${mlnT(a.in12)}  ↓ ${mlnT(a.out12)}`}</span>
          </div>
        )
      })}
      <span style={{ marginTop: 'auto', paddingTop: 10, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45 }}>
        Выписок в системе пока нет: свежесть — по последней проведённой операции, обороты — за 12 месяцев. Синим — старше суток.
      </span>
    </div>
  )
}
