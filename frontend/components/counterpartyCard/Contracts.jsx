/**
 * «Договоры» карточки контрагента v2 (хендофф «контрикZ»): № и дата · формат + тип · срок + состояние · ДС · сумма ДС за 12 мес · СК · →;
 * строка — ссылка в карточку договора. Если операции идут после окончания всех договоров — жёлтая плашка.
 */
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { fmtDateFull } from '@/lib/salesFormat'
import { box, cap, h2, count, Pill, Notice, money, link } from '@/components/contractCard/ui'

const COLS = 'minmax(170px, 1.2fr) minmax(190px, 1fr) minmax(170px, 1fr) 70px 150px 120px 24px'

export default function Contracts({ rows, warning, canSk }) {
  const cols = canSk ? COLS : COLS.replace(' 120px', '')
  return (
    <section style={{ ...box, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={h2}>Договоры</span><span style={count}>{rows.length}</span>
        <Link href="/directory/contracts" style={{ ...link, marginLeft: 'auto', fontSize: 12.5, fontWeight: 600 }}>в реестр договоров →</Link>
      </div>
      {!rows.length ? <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Договоров с контрагентом нет.</span> : (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 980 }}>
            <div style={{ ...cap, display: 'grid', gridTemplateColumns: cols, gap: 14, padding: '0 8px 7px', borderBottom: '1px solid var(--border-card)' }}>
              <span>№ договора</span><span>формат</span><span>срок</span><span style={{ textAlign: 'right' }}>ДС</span>
              <span style={{ textAlign: 'right' }}>ДС за 12 мес</span>{canSk && <span>СК</span>}<span />
            </div>
            {rows.map(k => (
              <Link key={k.id} href={`/directory/contracts/${k.id}`} style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, alignItems: 'center', padding: '9px 8px',
                                                                           borderBottom: '1px solid var(--border-row)', color: 'inherit', textDecoration: 'none' }}>
                <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{k.contract_number || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>от {fmtDateFull(k.contract_date)}</span>
                </span>
                <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                  {k.cooperation_format && <Pill tone="accent" small>{k.cooperation_format}</Pill>}
                  {k.ord_kind && <Pill tone={k.ord_kind === 'outer' ? 'warning' : 'income'} small>{k.ord_kind === 'outer' ? 'расходный' : 'доходный'}</Pill>}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, whiteSpace: 'nowrap' }}>{k.end_date_text ? `до ${k.end_date_text}` : '—'}</span>
                  <Pill tone={k.in_force ? 'income' : 'danger'} small>{k.in_force ? 'действует' : 'истёк'}</Pill>
                </span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{k.ds_count}</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', color: k.ds_12m ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{money(k.ds_12m)}</span>
                {canSk && <span style={{ fontSize: 12, color: 'var(--violet-fg)', whiteSpace: 'nowrap' }}>{k.sk || '—'}</span>}
                <span style={{ color: 'var(--text-faint)' }}>→</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {warning && <Notice>{warning}</Notice>}
    </section>
  )
}
