/**
 * Сводка над вкладкой «План оплат» (хендофф «План оплат · виджеты сводки», 02.11.2026) — вёрстка макета буквально.
 *
 * Считает сервер (`/operations/pay-plan/summary`, `app/pay_plan_summary.py`): сводка — по всему плану, а таблица
 * листается страницами. Каждый блок несёт `ids` своих строк; клик отдаёт их наверх, и таблица показывает ровно эти
 * операции. Второго расчёта условий здесь нет. Повторный клик по тому же блоку снимает фильтр.
 *
 * «Деньги на сегодня» и плашки «не хватает / остаётся» приходят только тому, у кого есть «Баланс: просмотр»
 * (владелец 02.11.2026): без права `money` пустой — карточки нет вовсе.
 */
import { MONO, UI, card as CARD } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'
import { plural } from '@/lib/publisherRecon.mjs'

const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const COL = { display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }
const RISE = 'opRise .4s cubic-bezier(0.22,1,0.36,1) both'
const GROW = { transformOrigin: 'left', animation: 'ppGrow .55s cubic-bezier(0.22,1,0.36,1) both' }

// Цвет статьи — по месту в списке (самая крупная первая): так статьи макета получают свои цвета, а новая статья — свой.
const ART_DOT = ['var(--accent)', 'var(--income)', 'var(--violet-fg)', 'var(--bank-sovkom)', 'var(--warning)', 'var(--bank-opt)', 'var(--danger)']
const AGE = { cur: ['var(--accent)', 'var(--text-primary)'], old: ['var(--warning)', 'var(--warning-fg)'] }
const TONE = {
  bad: { tint: 'var(--danger-tint)', border: 'var(--danger-border)', fg: 'var(--danger-fg)', dot: 'var(--danger)' },
  warn: { tint: 'var(--warning-bg)', border: 'var(--warning-border)', fg: 'var(--warning-fg)', dot: 'var(--warning)' },
  ok: { tint: 'var(--income-tint)', border: 'var(--income-border)', fg: 'var(--income-fg)' },
}
const pct = (v, all) => (all ? (v / all * 100).toFixed(1) : 0) + '%'

/** Тег дубля рядом с контрагентом в таблице: «уже списано?» (danger) или «проверить» (warning). */
export function DupTag({ tag }) {
  if (!tag) return null
  const t = tag.kind === 'done' ? TONE.bad : TONE.warn
  return (
    <span title={tag.text} style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 7px', background: t.tint, borderRadius: 6, color: t.fg, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
      <span style={{ width: 5, height: 5, borderRadius: 1, background: t.dot }} />{tag.kind === 'done' ? 'уже списано?' : 'проверить'}
    </span>
  )
}

/** Чип активного фильтра над таблицей. */
export function FilterChip({ filter, onClear }) {
  if (!filter) return null
  return (
    <span onClick={onClear} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 10px', background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', borderRadius: 8, color: 'var(--accent-fg)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
      {filter.label} ✕
    </span>
  )
}

function Gap({ label, gap }) {
  const t = gap.short ? TONE.bad : TONE.ok
  const text = `${label} — ${gap.short ? 'не хватает' : 'остаётся'}`
  return (
    <span title={`${text}: ${grp(gap.value)} ₽`} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1, padding: '5px 9px', background: t.tint, border: `1px solid ${t.border}`, borderRadius: 8 }}>
      <span style={{ fontSize: 10.5, fontWeight: 600, color: t.fg, lineHeight: 1.3 }}>{text}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: t.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{grp(gap.value)}</span>
    </span>
  )
}

function Total({ d, pick, on }) {
  return (
    <div style={COL}>
      <span style={CAP}>К оплате · по плану</span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 32, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1 }}>{grp(d.total)}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)' }}>₽</span>
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {d.count} {plural(d.count, 'платёж', 'платежа', 'платежей')} · {d.counterparties} {plural(d.counterparties, 'контрагент', 'контрагента', 'контрагентов')}
      </span>
      {d.money && (
        <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Gap label="Своих" gap={d.money.own} />
          {d.money.with_credit && <Gap label="С кредитом" gap={d.money.with_credit} />}
        </span>
      )}
      <span style={{ display: 'flex', height: 8, gap: 2, marginTop: 4 }}>
        {d.ages.map(a => <span key={a.key} title={`${a.label} · ${grp(a.sum)} ₽`} style={{ width: pct(a.sum, d.total), height: 8, borderRadius: 2, background: AGE[a.key][0], ...GROW }} />)}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {d.ages.map(a => (
          <span key={a.key} className="pp-pick" onClick={() => pick('age', a.key, a.label, a.ids)}
            style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: on('age', a.key) ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer' }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: AGE[a.key][0], flex: '0 0 7px' }} />{a.label}
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontWeight: 700, color: AGE[a.key][1] }}>{grp(a.sum)}</span>
          </span>
        ))}
      </span>
    </div>
  )
}

function Articles({ d, pick, on }) {
  return (
    <div style={{ ...COL, overflow: 'hidden' }}>
      <span style={CAP}>По статьям</span>
      <span style={{ display: 'flex', height: 8, gap: 2 }}>
        {d.articles.map((s, i) => <span key={s.name} title={`${s.name} · ${grp(s.sum)} ₽`} style={{ width: pct(s.sum, d.total), height: 8, borderRadius: 2, background: ART_DOT[i % ART_DOT.length], ...GROW }} />)}
      </span>
      {d.articles.map((s, i) => (
        <span key={s.name} className="pp-row" onClick={() => pick('item', s.name, `статья: ${s.name.toLowerCase()}`, s.ids)} title={`${s.count} шт`}
          style={{ display: 'grid', gridTemplateColumns: '10px minmax(0,1fr) auto', gap: 8, alignItems: 'center', padding: '3px 6px', margin: '0 -6px', borderRadius: 7, background: on('item', s.name) ? 'var(--accent-tint)' : 'transparent', cursor: 'pointer' }}>
          <span style={{ width: 7, height: 7, borderRadius: 2, background: ART_DOT[i % ART_DOT.length] }} />
          <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
          <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{grp(s.sum)}</span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{s.pct} % · {s.count} шт</span>
          </span>
        </span>
      ))}
    </div>
  )
}

function Top({ d, pick, on }) {
  const lead = d.top[0]?.sum || 0
  return (
    <div style={{ ...COL, overflow: 'hidden' }}>
      <span style={CAP}>Крупнейшие получатели</span>
      {d.top.map(t => {
        const meta = `${t.count} ${plural(t.count, 'платёж', 'платежа', 'платежей')} · ${t.periods.join(', ')}`
        return (
          <span key={t.counterparty_id} className="pp-row" onClick={() => pick('cp', t.counterparty_id, t.name, t.ids)} title={meta}
            style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '3px 6px', margin: '0 -6px', borderRadius: 7, background: on('cp', t.counterparty_id) ? 'var(--accent-tint)' : 'transparent', cursor: 'pointer', minWidth: 0 }}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
              <span style={{ flex: '1 1 auto', minWidth: 0, fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
              <span style={{ flex: '0 0 auto', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{grp(t.sum)}</span>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span style={{ flex: '0 0 64px', display: 'block', height: 5, borderRadius: 2, background: 'var(--border-inner)', overflow: 'hidden' }}>
                <span style={{ display: 'block', height: 5, width: pct(t.sum, lead), background: 'var(--bank-sovkom)', borderRadius: 2 }} />
              </span>
              <span style={{ flex: '1 1 auto', minWidth: 0, fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta}</span>
            </span>
          </span>
        )
      })}
    </div>
  )
}

function Pins({ d, pick, on }) {
  if (!d.pins.length) return null
  return (
    <div style={COL}>
      <span style={CAP}>Дозаполнить, чтобы не пропустить</span>
      {d.pins.map(g => {
        const t = TONE[g.tone], a = on('gap', g.key)
        return (
          <span key={g.key} className="pp-pin" onClick={() => pick('gap', g.key, g.label.toLowerCase(), g.ids)} title={g.title}
            style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 9px', background: a ? t.tint : 'var(--bg-card)', border: `1px solid ${a ? t.border : 'var(--border-card)'}`, borderRadius: 9, cursor: 'pointer' }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: t.dot, flex: '0 0 7px' }} />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: t.fg, whiteSpace: 'nowrap' }}>{g.label}</span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, fontWeight: 700, color: t.fg }}>{g.count} из {d.count}</span>
          </span>
        )
      })}
    </div>
  )
}

function Money({ m }) {
  const accounts = `${m.bank_count} ${plural(m.bank_count, 'счёт', 'счёта', 'счетов')}`
  const rows = [
    { label: 'Банки', value: m.banks, note: accounts },
    { label: 'Наличные', value: m.cash, note: 'касса' },
    m.credit
      ? { label: 'Кредит', value: m.credit.free, fg: 'var(--accent-fg)', note: `доступно из ${grp(m.credit.limit)} · ${m.credit.banks.join(', ')}` }
      : { label: 'Кредит', value: null, note: 'линии не заведены — Настройки → Остатки' },
  ]
  return (
    <div style={{ ...CARD, flex: '0 0 300px', minWidth: 0, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12, animation: RISE, animationDelay: '.04s' }}>
      <span style={{ ...CAP, fontWeight: 700, letterSpacing: '0.1em' }}>Деньги на сегодня</span>
      {rows.map(r => (
        <span key={r.label} style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingBottom: 10, borderBottom: '1px solid var(--border-inner)', minWidth: 0 }}>
          <span style={CAP}>{r.label}</span>
          {r.value !== null && (
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: r.fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{grp(r.value)}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>₽</span>
            </span>
          )}
          <span title={r.note} style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.note}</span>
        </span>
      ))}
    </div>
  )
}

/** `data` — ответ сводки; `filter` — { kind, value, label, ids } | null; `onFilter(next | null)`. */
export default function PayPlanSummary({ data, filter, onFilter }) {
  if (!data || !data.count) return null
  const on = (kind, value) => !!filter && filter.kind === kind && filter.value === value
  const pick = (kind, value, label, ids) => onFilter(on(kind, value) ? null : { kind, value, label, ids })
  const p = { d: data, pick, on }
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', fontFamily: UI }}>
      <style>{`
        @keyframes ppGrow { from { transform:scaleX(0) } to { transform:scaleX(1) } }
        .pp-pick:hover { color: var(--accent) !important; }
        .pp-row:hover { background: var(--bg-subtle) !important; }
        .pp-pin:hover { border-color: var(--border-hover) !important; }
      `}</style>
      <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex' }}>
        <div style={{ ...CARD, padding: '16px 22px', flex: '1 1 auto', minWidth: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px 28px', color: 'var(--text-primary)', animation: RISE }}>
          <Total {...p} />
          <Articles {...p} />
          <Top {...p} />
          <Pins {...p} />
        </div>
      </div>
      {data.money && <Money m={data.money} />}
    </div>
  )
}
