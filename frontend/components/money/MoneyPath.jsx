/**
 * «Путь денег» экрана «Деньги» (хендофф design_handoff_money_navy, 20.11.2026, README п. 3а): одна полоса — где сейчас деньги,
 * от размещения до банка. Первые два шага — из вкладки «Бизнес» (`/money/business`, цифры совпадают), «Нам должны» и «На счетах» —
 * из того же расчёта, что карточки «Нам должны» и «Счета» ниже. Дни между шагами — средние за 90 дней (`business.speed`).
 */
import Link from 'next/link'
import { CARD, CAPS, H, MONO } from './kit'

const GEN = { январь: 'января', февраль: 'февраля', март: 'марта', апрель: 'апреля', май: 'мая', июнь: 'июня', июль: 'июля', август: 'августа', сентябрь: 'сентября', октябрь: 'октября', ноябрь: 'ноября', декабрь: 'декабря' }
const mln = (v, d = 1) => ((v || 0) / 1e6).toFixed(d).replace('.', ',')

function Card({ cap, v, s, warn, tone, link, href, money }) {
  const w = { attn: ['var(--attn-tint)', 'var(--attn-border)', 'var(--attn-fg)'], bad: ['var(--bad-tint)', 'var(--bad-border)', 'var(--bad-fg)'] }[tone] || []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '14px 16px', borderRadius: 16, minWidth: 0,
      background: money ? 'var(--money-tint)' : 'var(--bg-subtle)', border: `1px solid ${money ? 'var(--money-border)' : 'var(--border-inner)'}` }}>
      <span style={CAPS}>{cap}</span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', color: money ? 'var(--money-fg)' : 'var(--text-primary)' }}>{v}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>млн</span></span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{s}</span>
      {!!warn && <span style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', borderRadius: 6, background: w[0],
        border: `1px solid ${w[1]}`, fontSize: 11, fontWeight: 600, color: w[2], whiteSpace: 'nowrap' }}>{warn}</span>}
      <Link href={href} style={{ marginTop: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{link}</Link>
    </div>
  )
}

function Arrow({ days, label, late }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '0 6px' }}>
      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: late ? 'var(--attn-fg)' : 'var(--text-primary)' }}>{days}</span>
      <span style={{ width: '100%', height: 2, background: 'var(--border-hover)', position: 'relative' }}>
        <span style={{ position: 'absolute', right: -2, top: -4, width: 0, height: 0, borderLeft: '7px solid var(--border-hover)', borderTop: '5px solid transparent', borderBottom: '5px solid transparent' }} /></span>
      <span style={{ fontSize: 10.5, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.3 }}>{label}</span>
    </div>
  )
}

export default function MoneyPath({ biz, inv, data }) {
  const p = biz.placement, u = biz.unbilled, sp = biz.speed || {}
  const month = biz.months.find(m => m.role === 'now')?.name.toLowerCase()
  const owed = inv.reduce((a, x) => a + x.amount, 0)
  const over = inv.filter(x => x.d < 0).reduce((a, x) => a + x.amount, 0)
  const late = sp.to_pay_days != null && sp.term_days != null ? sp.to_pay_days - sp.term_days : null
  const worst = u.rows.filter(r => r.days != null).sort((a, b) => b.days - a.days)[0]
  const months = [...new Set(u.rows.map(r => r.month))]
  return (
    <div style={{ ...CARD, padding: '16px 20px', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}><span style={H}>Путь денег</span><span style={CAPS}>где сейчас наши деньги · без НДС</span>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>светофор продаж, сверка с учётом и маржа — <Link href="/exec?tab=business" style={{ color: 'var(--text-primary)', fontWeight: 700 }}>Бизнес →</Link></span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.25fr) 96px minmax(0,1fr) 96px minmax(0,1fr) 96px minmax(0,0.85fr)', alignItems: 'stretch' }}>
        <Card cap={`В размещении · ${month}`} v={mln(p.total)} s={`${p.deals} сделок${p.delivered_pct != null ? ` · открутилось ${p.delivered_pct} %` : ''}`}
          warn={p.at_risk > 0 ? `под риском ${mln(p.at_risk)} млн · ${p.at_risk_deals} сделок` : ''} tone="attn" link="Дашборд трафика →" href="/traffic/dashboard" />
        <Arrow days={sp.to_invoice_days != null ? `${sp.to_invoice_days} дн` : '—'} label="конец флайта → счёт" />
        <Card cap="Сделано, а счёта нет" v={mln(u.total)}
          s={`${u.rows.length} сделок ${months.length === 1 ? GEN[months[0]] || months[0] : 'закрытых месяцев'}${u.outside.deals ? ` · ещё ${mln(u.outside.total)} млн (${u.outside.deals} сделок) вне пакетов, про счёт система не знает` : ''}`}
          warn={worst ? `до ${worst.days} дн · ${worst.code}` : ''} tone="bad" link="Пакеты закрытия →" href="/finance/master-deals" />
        <Arrow days={sp.to_pay_days != null ? `${sp.to_pay_days} дн` : '—'} label={`счёт → оплата${sp.term_days != null ? ` · отсрочка ${sp.term_days}` : ''}`} late={late > 0} />
        <Card cap="Нам должны" v={mln(owed, 2)} s={over ? `из них просрочено ${mln(over, 2)} млн` : 'просрочки нет'}
          warn={late > 0 ? `+${late} дн к отсрочке` : ''} tone="attn" link="Дебиторка →" href="/finance/receivables" />
        <Arrow days="" label="поступление" />
        <Card cap="На счетах" v={mln(data.balance_total, 2)} s={`${data.accounts.length} счетов · по проведённым операциям`} money link="Операции →" href="/finance/operations" />
      </div>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Дни между шагами — скорость денег: от конца флайта до счёта и от счёта до оплаты, в среднем за 3 месяца.{p.as_of ? ` В размещении и «под риском» — по статистике дашборда трафика за ${p.as_of.slice(8, 10)}.${p.as_of.slice(5, 7)}.` : ''}</span>
    </div>
  )
}
