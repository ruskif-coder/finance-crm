/**
 * Основная колонка карточки договора (хендофф «договорZ»): ДС, закрытие, сделки, агентские условия, площадки. ДС и сделки — с поиском,
 * чипами-фильтрами и итогом по отфильтрованному. Блок приходит, только если есть право его раздела.
 */
import Link from 'next/link'
import { grpDec, fmtDateFull } from '@/lib/salesFormat'
import DataTable from '@/components/contractCard/DataTable'
import { Pill, money, link } from '@/components/contractCard/ui'

const period = (a, b) => (a || b ? `${fmtDateFull(a)} — ${fmtDateFull(b)}` : '—')
const STATE = { 'черновик': 'muted', 'у юриста': 'warning', 'подтверждён': 'income' }
const VIA = { 'ДС': 'accent', 'ОРД': 'violet', 'закрытие': 'income' }
const yearOf = (a) => String(a.date || '').slice(0, 4)

export function Annexes({ data }) {
  const rows = data.items
  const years = [...new Set(rows.map(yearOf).filter(Boolean))].sort().reverse().slice(0, 2)
  const filters = [{ key: 'all', label: 'все', test: () => true }, { key: 'draft', label: 'не подтверждены', test: a => a.state !== 'подтверждён' },
                   ...years.map(y => ({ key: y, label: y, test: a => yearOf(a) === y }))]
  const hint = `следующий № ${data.next_no ?? '—'}${data.start_no != null ? ` · вне системы выдано до № ${data.start_no}` : ''}`
  return (
    <DataTable id="annexes" title="ДС" hint={hint} rows={rows} filters={filters} sum={a => a.total_amount}
               search={a => [a.number, ...(a.deals || []).map(d => d.code)].join(' ')} empty="Приложений по договору нет."
               cols={[
                 { t: 'ДС', w: '130px', bold: true, cell: a => <Link href={`/directory/annexes/${a.id}`} style={link}>{a.number || `черновик #${a.id}`}</Link> },
                 { t: 'статус', w: '120px', cell: a => <Pill tone={STATE[a.state]}>{a.state}</Pill> },
                 { t: 'дата', w: '90px', mono: true, cell: a => fmtDateFull(a.date) },
                 { t: 'период', w: '210px', mono: true, cell: a => period(a.period_from, a.period_to) },
                 { t: 'сумма', w: '130px', right: true, mono: true, bold: true, cell: a => money(a.total_amount) },
                 { t: 'шаблон', cell: a => (a.template ? `${a.template.title} · v${a.template.version}` : a.state === 'черновик' ? 'по умолчанию' : '—') },
                 { t: 'сделки', w: '150px', mono: true, cell: a => (a.deals || []).map(d => d.code).join(', ') || '—' },
               ]} />
  )
}

export function Masters({ rows }) {
  return (
    <DataTable id="masters" title="Закрытие" hint="мастер-сделки по договору" rows={rows.map(m => ({ ...m, id: m.code }))} minW={640} maxH={300}
               empty="Пакетов закрытия по договору нет."
               cols={[
                 { t: 'пакет', w: '120px', mono: true, bold: true, cell: m => <Link href={`/accounts/master/${m.code}`} style={link}>{m.code}</Link> },
                 { t: 'период', w: '90px', mono: true, cell: m => m.period },
                 { t: 'статус', cell: m => m.status_label || m.status },
                 { t: 'ушёл в ДО', w: '110px', mono: true, cell: m => fmtDateFull(m.sent_at) },
                 { t: 'документы закрыты', w: '150px', mono: true, cell: m => fmtDateFull(m.docs_closed_at) },
               ]} />
  )
}

export function Deals({ rows }) {
  const filters = [{ key: 'all', label: 'все', test: () => true }, ...['ДС', 'закрытие', 'ОРД'].map(v => ({ key: v, label: v, test: d => d.via.includes(v) }))]
  return (
    <DataTable id="deals" title="Сделки" hint="закрыты ДС договора, вошли в его пакеты или он итоговый в ОРД" rows={rows} filters={filters} sum={d => d.amount}
               search={d => [d.code, d.title, d.advertiser, String(d.period_from || '').slice(0, 7)].join(' ')} empty="Сделок, связанных с договором, нет."
               cols={[
                 { t: 'код', w: '100px', mono: true, bold: true, cell: d => <Link href={`/sales/deals/${d.code || d.id}`} style={link}>{d.code || d.id}</Link> },
                 { t: 'сделка', cell: d => d.title || '—' },
                 { t: 'рекламодатель', w: '170px', cell: d => d.advertiser || '—' },
                 { t: 'период', w: '210px', mono: true, cell: d => period(d.period_from, d.period_to) },
                 { t: 'сумма', w: '130px', right: true, mono: true, bold: true, cell: d => money(d.amount) },
                 { t: 'связь', w: '190px', cell: d => <span style={{ display: 'inline-flex', gap: 4 }}>{d.via.map(v => <Pill key={v} tone={VIA[v]} small>{v}</Pill>)}</span> },
               ]} />
  )
}

export function Sk({ data }) {
  const rows = [...data.rules.map(r => ({ ...r, id: `r${r.id}`, what: r.kind ? `СК · ${r.kind}` : 'СК' })),
                ...data.work.map(w => ({ ...w, id: `w${w.id}`, what: 'условия работы', mode: (w.body || '').slice(0, 80) }))]
  return (
    <DataTable id="sk" title="Агентские условия" hint="правила, заведённые именно на этот договор" rows={rows} minW={860} maxH={300}
               empty="На договор отдельных правил нет — действуют правила агентства и рекламодателя («Продажи → Агентские условия»)."
               cols={[
                 { t: 'что', w: '150px', cell: r => r.what },
                 // К чему привязано правило на договоре: агентство сделки или рекламодатель напрямую (владелец 28.10.2026).
                 { t: 'агентство / рекламодатель', w: '230px', cell: r => (r.agency ? `агентство «${r.agency}»` : r.advertiser ? `рекламодатель «${r.advertiser}» напрямую` : 'весь договор') },
                 { t: 'способ', cell: r => r.mode || '—' },
                 { t: '%', w: '60px', right: true, mono: true, bold: true, cell: r => (r.percent == null ? '—' : grpDec(r.percent, 1)) },
                 { t: 'бренд / услуга', w: '170px', cell: r => [r.brand, r.service].filter(Boolean).join(' · ') || 'все' },
                 { t: 'действует', w: '210px', mono: true, cell: r => period(r.valid_from, r.valid_to) },
               ]} />
  )
}

export function Publishers({ rows, outer }) {
  return (
    <DataTable id="publishers" title="Площадки" rows={rows.map(p => ({ ...p, pid: p.id, id: `${p.id}-${p.role}` }))} minW={560} maxH={300}
               empty={outer ? 'Площадки к договору не привязаны.' : 'Договор доходный — площадок у него нет.'}
               cols={[
                 { t: 'площадка', bold: true, cell: p => <Link href={`/publishers/${p.pid}`} style={link}>{p.name}</Link> },
                 { t: 'роль', w: '140px', cell: p => p.role || '—' },
                 { t: 'номер в карточке', w: '170px', mono: true, cell: p => p.number_raw || '—' },
                 { t: '', w: '80px', cell: p => (p.is_archived ? 'в архиве' : '') },
               ]} />
  )
}
