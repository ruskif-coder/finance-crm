/** Детализация по месяцам — свёрнута по умолчанию (README хендоффа, каркас). Факт по оплаченным операциям, остаток на конец месяца. */
import { useState } from 'react'
import { Collapse } from '@/lib/motion'
import { CAPS, H, MONO, f, fs, sg } from './kit'
import { MON } from './model'

const label = (m) => `${MON[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`

export default function MonthTable({ months }) {
  const [open, setOpen] = useState(false)
  const rows = months.slice(1)
  const cols = 'minmax(0,1fr) 180px 180px 180px 180px'
  return (
    <div data-motion="rise" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, overflow: 'hidden' }}>
      <button type="button" onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 22px', cursor: 'pointer', width: '100%',
        border: 0, background: 'transparent', fontFamily: 'inherit', color: 'inherit', textAlign: 'left' }}>
        <span style={{ display: 'inline-flex', width: 14, color: 'var(--text-muted)', fontSize: 12 }}>{open ? '▾' : '▸'}</span>
        <span style={H}>Детализация по месяцам</span>
        <span style={CAPS}>{label(rows[0].month)} — {label(rows[rows.length - 1].month)} · по оплаченным операциям</span>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>{open ? 'свернуть' : `${rows.length} месяцев · развернуть`}</span>
      </button>
      {open && <Collapse><div style={{ padding: '0 22px 14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border-inner)' }}>
          <span style={CAPS}>период</span>
          {['поступления', 'списания', 'чистый поток', 'остаток на конец'].map(t => <span key={t} style={{ ...CAPS, textAlign: 'right' }}>{t}</span>)}
        </div>
        {rows.map((m, k) => {
          const n = m.income - m.expense
          return (
            <div key={m.month} style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', height: 36, borderBottom: '1px solid var(--border-row)', fontSize: 13 }}>
              <span style={{ fontWeight: k === rows.length - 1 ? 800 : 500 }}>{label(m.month)}{k === rows.length - 1 ? ' · по сегодня' : ''}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right', color: 'var(--money-fg)' }}>{f(m.income)}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right' }}>{f(m.expense)}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right', color: n < 0 ? 'var(--bad-fg)' : 'var(--money-fg)' }}>{sg(n)}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right', fontWeight: 700, color: m.balance_end < 0 ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{fs(m.balance_end)}</span>
            </div>
          )
        })}
        <div style={{ paddingTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>Остаток — от стартовых сумм счетов плюс оплаченные операции; выписками не сверен. Когда появятся выписки, прошлые месяцы встанут по ним.</div>
      </div></Collapse>}
    </div>
  )
}
