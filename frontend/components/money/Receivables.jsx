/** «Нам должны» и «Качество данных» (README хендоффа, п. 8) — по живым данным. */
import Link from 'next/link'
import { BTN, CARD, CAPS, H, MONO, NUM, Bar, Dot, f } from './kit'
import { bucketOf } from './model'

const BK = { ok: ['в срок', 'var(--ok)', 'var(--text-primary)'], soon: ['до 7 дней', 'var(--attn)', 'var(--attn-fg)'], over: ['просрочено', 'var(--bad)', 'var(--bad-fg)'] }

export function Receivables({ inv, dz, setDz }) {
  const bs = { ok: 0, soon: 0, over: 0 }
  inv.forEach(x => { bs[bucketOf(x)] += x.amount })
  const total = inv.reduce((a, x) => a + x.amount, 0)
  const byC = {}
  inv.filter(x => !dz || bucketOf(x) === dz).forEach(x => {
    const c = byC[x.cp_id ?? x.who] || (byC[x.cp_id ?? x.who] = { who: x.who, v: 0, worst: 9999, delay: x.delay })
    c.v += x.amount; c.worst = Math.min(c.worst, x.d)
  })
  const rows = Object.values(byC).sort((a, b) => ((a.worst < 0) !== (b.worst < 0) ? (a.worst < 0 ? -1 : 1) : b.v - a.v)).slice(0, 5)
  const cols = 'minmax(0,1fr) 120px 130px'
  return (
    <div data-motion="rise" style={{ ...CARD, gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}><span style={H}>Нам должны</span>
        <span style={{ ...NUM, fontSize: 15 }}>{f(total)} ₽</span>
        <span style={{ marginLeft: 'auto', ...CAPS }}>{inv.length} счетов</span></div>
      <Bar parts={['ok', 'soon', 'over'].map(k => ({ w: bs[k], c: BK[k][1] }))} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
        {['ok', 'soon', 'over'].map(k => {
          const on = dz === k
          return (
            <button type="button" key={k} onClick={() => setDz(on ? '' : k)} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 11px',
              borderRadius: 12, border: `1px solid ${on ? 'var(--hot)' : 'var(--border-card)'}`, background: on ? 'var(--bg-subtle)' : 'transparent',
              cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', color: 'inherit' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Dot c={BK[k][1]} /><span style={CAPS}>{BK[k][0]}</span></span>
              <span style={{ ...NUM, fontSize: 16, color: BK[k][2] }}>{f(bs[k])}</span>
            </button>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, padding: '0 0 6px', borderBottom: '1px solid var(--border-inner)' }}>
          <span style={CAPS}>клиент</span><span style={{ ...CAPS, textAlign: 'right' }}>сумма</span><span style={{ ...CAPS, textAlign: 'right' }}>срок</span></div>
        {rows.map(c => {
          const b = c.worst < 0 ? 'over' : c.worst <= 7 ? 'soon' : 'ok'
          return (
            <div key={c.who} style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, alignItems: 'center', height: 44, borderBottom: '1px solid var(--border-row)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}><Dot c={BK[b][1]} r="50%" />
                <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.who}</span></span>
              <span style={{ ...NUM, fontSize: 13, textAlign: 'right' }}>{f(c.v)}</span>
              <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: BK[b][2], whiteSpace: 'nowrap' }}>
                  {c.worst < 0 ? `просрочка ${-c.worst} дн` : c.worst === 0 ? 'сегодня' : `через ${c.worst} дн`}</span>
                <span style={{ fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{!c.delay ? 'платит в срок' : c.delay > 0 ? `обычно позже на ${c.delay} дн` : `обычно раньше на ${-c.delay} дн`}</span>
              </span>
            </div>
          )
        })}
      </div>
      <span style={{ marginTop: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
        {dz ? `Фильтр: ${BK[dz][0]} · нажмите ещё раз, чтобы снять` : 'Сначала просроченные, затем по сумме. Срок — как в «Операциях».'}</span>
    </div>
  )
}

const QC = { no_article: 'var(--attn)', no_counterparty: 'var(--attn)', no_document: 'var(--ok)', duplicates: 'var(--bad)' }

export function Quality({ rows }) {
  return (
    <div data-motion="rise" style={{ ...CARD, gap: 4 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingBottom: 8 }}><span style={H}>Качество данных</span>
        <span style={CAPS}>операции за 90 дней · цифры точны, если здесь ноль</span></div>
      {rows.map(q => (
        <div key={q.key} style={{ display: 'grid', gridTemplateColumns: '10px minmax(0,1fr) auto', gap: '2px 10px', alignItems: 'center', padding: '10px 0',
          borderTop: '1px solid var(--border-row)' }}>
          <span style={{ width: 7, height: 7, borderRadius: 2, background: q.count ? QC[q.key] : 'var(--border-hover)' }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>{q.title}</span>
          <span style={{ ...NUM, fontSize: 14, textAlign: 'right' }}>{q.count}</span>
          <span /><span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{f(q.sum)} ₽</span><span />
        </div>
      ))}
      <Link href="/finance/operations" style={{ ...BTN, alignSelf: 'flex-start', marginTop: 'auto', textDecoration: 'none' }}>Разобрать в «Операциях» →</Link>
    </div>
  )
}
