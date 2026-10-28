/**
 * Шапка карточки контрагента v2 (хендофф «контрикZ», 28.10.2026): название (длинное — многоточием, полное в `title`), статус, тип,
 * чипы холдингов (вместо блока «Принадлежность»), ИНН/КПП, сайт, «в системе с · N операций · N договоров»; кнопки «Редактировать»
 * и «+ Договор» — справа вверху, рядом с плашкой «Расчёты» (сальдо = нам должны − мы должны; одна плашка вместо четырёх KPI).
 */
import { MONO } from '@/components/salesTableKit'
import safeHref from '@/lib/safeHref'
import { fmtDateFull } from '@/lib/salesFormat'
import { box, cap, btnGhost, btnPrimary, Pill, money, plural, link } from '@/components/contractCard/ui'

const KIND = { income: 'доход', expense: 'расход', mixed: 'смешанный · доход и расход' }
const STATUS_TONE = { 'действующий': 'income', 'виртуальный': 'muted' }

function Settlement({ s, onShow }) {
  const tone = s.saldo < 0 ? ['var(--warning-bg)', 'var(--warning-border)', 'var(--warning-fg)', 'мы должны']
    : s.saldo > 0 ? ['var(--bg-tint)', 'var(--accent-border)', 'var(--accent-fg)', 'нам должны']
      : ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-secondary)', 'расчёты закрыты']
  const sub = (label, v) => (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={cap}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: v ? tone[2] : 'var(--text-disabled)' }}>{money(v)}</span>
    </span>
  )
  return (
    <div style={{ flex: '0 0 420px', display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 18px', background: tone[0], border: `1px solid ${tone[1]}`, borderRadius: 14 }}>
      <span style={cap}>Расчёты · сальдо на сегодня</span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, color: tone[2], whiteSpace: 'nowrap' }}>{s.saldo < 0 ? '−' : ''}{money(Math.abs(s.saldo))}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: tone[2] }}>{tone[3]}</span>
      </span>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, paddingTop: 8, borderTop: `1px solid ${tone[1]}` }}>
        {sub('Дебиторка · нам должны', s.receivable)}{sub('Кредиторка · мы должны', s.payable)}
      </div>
      {s.reason && (
        <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
          {s.reason}. <span onClick={onShow} style={{ ...link, fontWeight: 600, cursor: 'pointer' }}>показать →</span>
        </span>
      )}
    </div>
  )
}

export default function Head({ card, ov, canEdit, canContract, onEdit, onNewContract, onShowPlan }) {
  const site = safeHref(card.website)
  const holdings = card.linked_agencies || []
  return (
    <section style={{ ...box, padding: '20px 22px', display: 'flex', gap: 22, alignItems: 'stretch' }}>
      <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <span title={card.name} style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{card.name}</span>
          {card.status && <Pill tone={STATUS_TONE[card.status] || 'muted'}>{card.status}</Pill>}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, flex: '0 0 auto' }}>
            {canEdit && <button type="button" onClick={onEdit} style={btnPrimary}>Редактировать</button>}
            {canContract && <button type="button" onClick={onNewContract} style={btnGhost}>+ Договор</button>}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {ov && ov.kind && <Pill tone="violet">{KIND[ov.kind]}</Pill>}
          {holdings.map(a => (
            <span key={a.id} title={`${a.name_en || a.name}${a.holding ? ` · холдинг ${a.holding}` : ''} · агентство`}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 22, padding: '0 8px', borderRadius: 6, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', fontSize: 11.5, fontWeight: 600 }}>
              {a.short_name || a.name}{a.holding && <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{a.holding}</span>}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 28, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span style={cap}>ИНН</span><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>{card.inn || '—'}</span></span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span style={cap}>КПП</span><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>{card.kpp || '—'}</span></span>
          {site && <a href={site} target="_blank" rel="noopener noreferrer" style={{ ...link, fontSize: 12.5, fontWeight: 600 }}>{card.website.replace(/^https?:\/\//i, '').replace(/\/$/, '')} ↗</a>}
        </div>
        {ov && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {ov.since ? `в системе с ${fmtDateFull(ov.since)} · ` : ''}{ov.op_count} {plural(ov.op_count, 'операция', 'операции', 'операций')} · {ov.contracts.length} {plural(ov.contracts.length, 'договор', 'договора', 'договоров')}
          </span>
        )}
      </div>
      {ov && <Settlement s={ov.settlement} onShow={onShowPlan} />}
    </section>
  )
}
