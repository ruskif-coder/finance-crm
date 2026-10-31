/**
 * Правая колонка карточки договора (440px, хендофф «договорZ»): шаблоны ДС договора, деньги контрагента с его договорами, ОРД,
 * юр запросы, журнал. Только показ; действия — колбэками страницы.
 */
import Link from 'next/link'
import { MONO, Segmented } from '@/components/salesTableKit'
import { isAdmin } from '@/lib/auth'
import { fmtDateFull } from '@/lib/salesFormat'
import { fmtDateTime } from '@/lib/dates'
import { cap, h2, count, note, btnPrimary, Pill, Notice, money, plural, link, panel } from '@/components/contractCard/ui'

// Тумблер «как называется ДС» (владелец 31.10.2026). Подписи — как у нас на экранах («ДС»);
// в самом документе слово печатается полностью — «Доп. соглашение» (`annex_tpl/doc_kind.py`).
// Пусто в базе = «приложение»: так договоры печатаются по умолчанию.
const WORDS = [{ value: 'приложение', label: 'Приложение' }, { value: 'дс', label: 'ДС' }]

const PEN = 'M4 20h4l10-10-4-4L4 16v4z'
const COPY = 'M9 9h11v11H9zM5 15V4h11'

function TplRow({ t, onOpen, onCopy }) {
  const base = t.scope === 'base'
  const kind = base ? ['базовый формата', 'muted'] : t.is_main ? ['основной', 'accent'] : ['именованный', 'violet']
  return (
    <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto 30px', gap: '4px 10px', alignItems: 'center', padding: '9px 10px',
                   background: t.is_main ? 'var(--bg-tint)' : 'var(--bg-subtle)', border: `1px solid ${t.is_main ? 'var(--accent-border)' : 'var(--border-inner)'}`, borderRadius: 11 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
        <Pill tone={kind[1]} small>{kind[0]}</Pill>
      </span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 4, justifySelf: 'end', whiteSpace: 'nowrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: t.annexes ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{t.annexes}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{plural(t.annexes, 'документ', 'документа', 'документов')}</span>
      </span>
      <span onClick={base ? onCopy : onOpen} title={base ? 'Базовый общий для формата — создать свой шаблон на его основе' : 'Открыть шаблон в конструкторе'}
            style={{ gridRow: 'span 2', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, boxSizing: 'border-box', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 8, color: 'var(--text-secondary)', cursor: 'pointer' }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={base ? COPY : PEN} /></svg>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        v{t.version ?? '—'} · правка {fmtDateFull(t.updated_at)}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', justifySelf: 'end', whiteSpace: 'nowrap' }}>
        {t.last_date ? `последний ${fmtDateFull(t.last_date)}` : 'не применялся'}
      </span>
    </span>
  )
}

export function Templates({ rows, total, canCreate, onNew, onOpen, onCopy, onAll, word, canEditWord, onWord }) {
  return (
    <section id="templates" style={{ ...panel, gap: 8 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={h2}>Шаблоны ДС договора</span><span style={count}>{rows.length}</span>
        {canCreate && <button type="button" onClick={onNew} style={{ ...btnPrimary, marginLeft: 'auto', height: 28, padding: '0 11px', fontSize: 12 }}>+ Новый шаблон</button>}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Документ называется</span>
        {/* Выбирается один раз (обычно при первой сборке ДС), дальше — только администратор (владелец 31.10.2026);
            сервер держит то же правило. Не выбран — ничего не подсвечено: показать «Приложение» значило бы выдать
            умолчание за сделанный выбор. */}
        <Segmented value={word || null} options={WORDS} onChange={onWord}
                   disabled={!(isAdmin() || (!word && canEditWord))}
                   title={word ? (isAdmin() ? 'Меняет слово в номере и тексте ДС по этому договору'
                                            : 'Вид уже выбран — изменить может только администратор')
                               : 'Вид ещё не выбран — обычно выбирается при первой сборке ДС'} />
        {!word && <span style={{ fontSize: 11, color: 'var(--warning-fg)' }}>не выбран</span>}
      </span>
      {rows.map(t => <TplRow key={t.id} t={t} onOpen={() => onOpen(t.id)} onCopy={() => onCopy(t.id)} />)}
      {!rows.length && <span style={note}>Шаблонов нет: у договора не указан формат или формату не назначен базовый шаблон.</span>}
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 6, borderTop: '1px solid var(--border-inner)', fontSize: 11.5, color: 'var(--text-muted)' }}>
        все ДС договора — {total}
        <span onClick={onAll} style={{ marginLeft: 'auto', fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>открыть шаблоны →</span>
      </span>
    </section>
  )
}

function Num({ label, v }) {
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={cap}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, whiteSpace: 'nowrap', color: v ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{money(v || 0)}</span>
    </span>
  )
}

export function Money({ data, counterpartyId }) {
  if (!data.counterparty) return <section style={{ ...panel, gap: 8 }}><span style={h2}>Деньги</span><span style={note}>Договор не связан с контрагентом из реестра.</span></section>
  return (
    <section style={{ ...panel, gap: 10 }}>
      <span style={h2}>Деньги</span>
      <Notice>Считается по контрагенту, не по договору: операции к договору не привязаны, номер ДС в них — только текстом</Notice>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 14px' }}>
        <Num label="Поступило" v={data.income_paid} /><Num label="Ждём" v={data.receivable} />
        <Num label="Оплачено" v={data.expense_paid} /><Num label="К оплате" v={data.payable} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 8, borderTop: '1px solid var(--border-inner)' }}>
        <span style={cap}>Договоры контрагента · {(data.contracts || []).length}</span>
        {(data.contracts || []).map(k => {
          const row = (
            <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '2px 10px', alignItems: 'center', padding: '7px 9px', borderRadius: 9,
                           background: k.current ? 'var(--bg-tint)' : 'transparent', border: `1px solid ${k.current ? 'var(--accent-border)' : 'transparent'}` }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: k.current ? 'var(--text-primary)' : 'var(--accent)', whiteSpace: 'nowrap' }}>{k.contract_number || '—'}</span>
                {k.ord_kind && <Pill tone={k.ord_kind === 'outer' ? 'warning' : 'income'} small>{k.ord_kind === 'outer' ? 'расходный' : 'доходный'}</Pill>}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, justifySelf: 'end', whiteSpace: 'nowrap' }}>{money(k.ds_year)}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {[k.cooperation_format, k.end_date_text ? `до ${k.end_date_text}` : null].filter(Boolean).join(' · ') || '—'}
              </span>
              <span style={{ fontSize: 10.5, color: 'var(--text-faint)', justifySelf: 'end', whiteSpace: 'nowrap' }}>{k.current ? 'этот договор' : `ДС за ${data.year}`}</span>
            </span>
          )
          return k.current ? <span key={k.id}>{row}</span> : <Link key={k.id} href={`/directory/contracts/${k.id}`} style={{ color: 'inherit', textDecoration: 'none' }}>{row}</Link>
        })}
      </div>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 8, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-secondary)' }}>
        операций <b style={{ fontFamily: MONO }}>{data.op_count}</b> · последняя <span style={{ fontFamily: MONO }}>{fmtDateFull(data.last_op_date)}</span>
        {counterpartyId && <Link href={`/directory/counterparties/${counterpartyId}`} style={{ ...link, marginLeft: 'auto', fontWeight: 600 }}>карточка контрагента →</Link>}
      </span>
    </section>
  )
}

export function Ord({ data }) {
  const rows = [['номер в ОРД', data.contract_id || '—'], ['контур', data.env === 'demo' ? 'демо' : data.contract_id ? 'боевой' : '—'],
                ['сделок как итоговым', data.final_deals], ...data.initial.map(i => [`изначальный · ${i.contractor_name || '—'}`, `${i.number || '—'} от ${fmtDateFull(i.date)}`])]
  return (
    <section style={{ ...panel, gap: 8 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={h2}>ОРД</span>
        <Pill tone={data.contract_id ? 'income' : 'muted'}>{data.contract_id ? (data.status || 'статус не получен') : 'не зарегистрирован'}</Pill>
      </span>
      {rows.map(([l, v], i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '5px 0', borderTop: '1px solid var(--border-row)' }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', flex: '0 0 150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l}</span>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, minWidth: 0, overflowWrap: 'anywhere' }}>{v}</span>
        </span>
      ))}
    </section>
  )
}

const LEGAL_TONE = { 'открыта': 'warning', 'в работе': 'accent', 'сделана': 'income', 'отклонена': 'danger' }

export function Legal({ rows }) {
  return (
    <section style={{ ...panel, gap: 8 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={h2}>Юр запросы</span><span style={count}>{rows.length}</span></span>
      {!rows.length && <span style={note}>Заявок юристу по договору не было.</span>}
      {rows.map(r => (
        <span key={r.id} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '9px 10px', background: 'var(--bg-subtle)', borderRadius: 10 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>№ {r.id}</span>
            {r.annex_id && <Link href={`/directory/annexes/${r.annex_id}`} style={{ ...link, fontFamily: MONO, fontSize: 11 }}>{r.annex_number || `черновик #${r.annex_id}`}</Link>}
            <span style={{ marginLeft: 'auto' }}><Pill tone={LEGAL_TONE[r.status] || 'muted'} small>{r.status}</Pill></span>
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4, overflowWrap: 'anywhere' }}>{r.text}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>подана {fmtDateFull(r.created_at)}</span>
        </span>
      ))}
    </section>
  )
}

export function Audit({ rows }) {
  return (
    <section style={{ ...panel, gap: 6 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={h2}>Журнал действий</span><span style={note}>последние 50</span></span>
      {!rows.length && <span style={note}>Записей нет.</span>}
      <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {rows.map(l => (
          <span key={l.id} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
            <span style={{ display: 'flex', gap: 8, fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}><span>{fmtDateTime(l.created_at)}</span><span>· {l.user_name || '—'}</span></span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4, overflowWrap: 'anywhere' }}>{l.details || l.action}</span>
          </span>
        ))}
      </div>
    </section>
  )
}
