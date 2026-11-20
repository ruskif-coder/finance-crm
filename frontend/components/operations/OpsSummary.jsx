/**
 * Полоса итогов «Операций» (хендофф design_handoff_operations_navy, 17.11.2026, раздел 2): шесть плиток по ВСЕМ операциям текущего
 * фильтра — считает сервер (`GET /operations/summary`), страница видит только 100–500 строк. Четыре плитки — быстрые фильтры
 * (`quick`: in | out | over | empty | issues — «Проблемные» добавлена 20.11.2026), «Сальдо» — только число. Активна одна плитка; повторный клик снимает фильтр.
 * Стекло (`.navy-glass`), ночью — светлая зона (`data-tone="light"`); в прежних темах атрибуты ничего не меняют.
 */
import { MONO } from '@/components/salesTableKit'
import { grp0 } from '@/lib/salesFormat'

const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }

/** «2,87 млн ₽» от миллиона, меньше — полностью; знак — по просьбе (сальдо). */
function money(v, signed = false) {
  const n = Number(v) || 0
  const sign = signed ? (n > 0 ? '+' : n < 0 ? '−' : '') : (n < 0 ? '−' : '')
  const a = Math.abs(n)
  return a >= 1e6 ? { num: `${sign}${(a / 1e6).toFixed(2).replace('.', ',')}`, unit: 'млн ₽' } : { num: `${sign}${grp0(Math.round(a))}`, unit: '₽' }
}
const short = (v) => { const m = money(v); return `${m.num} ${m.unit}` }
const ops = (n) => { const k = n % 100 >= 11 && n % 100 <= 14 ? 2 : n % 10 === 1 ? 0 : n % 10 >= 2 && n % 10 <= 4 ? 1 : 2; return ['операция', 'операции', 'операций'][k] }

function Tile({ label, big, unit, sub, fg, active, onClick, first }) {
  const click = !!onClick
  return (
    <div role={click ? 'button' : undefined} tabIndex={click ? 0 : undefined} onClick={onClick}
      onKeyDown={click ? (e => e.key === 'Enter' && onClick()) : undefined}
      title={click ? (active ? 'Снять фильтр' : 'Показать только эти операции') : undefined}
      style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, padding: '14px 22px', cursor: click ? 'pointer' : 'default',
        borderLeft: first ? 'none' : '1px solid var(--border-inner)', background: active ? 'var(--signal-tint)' : 'transparent', transition: 'background-color var(--dur-fast) ease' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={CAP}>{label}</span>
        {active && <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 700, color: 'var(--signal-text)' }}>фильтр ✕</span>}
      </span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: fg || 'var(--text-primary)' }}>{big}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{unit}</span>
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</span>
    </div>
  )
}

export default function OpsSummary({ s, quick, onQuick }) {
  if (!s) return null
  const pick = (k) => () => onQuick(quick === k ? null : k)
  const inF = money(s.income_fact), outF = money(s.expense_fact), sal = money(s.saldo_fact, true), over = money(s.overdue_sum)
  return (
    <div className="navy-glass" data-tone="light"
      style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0,1fr))', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
        borderRadius: 20, boxShadow: 'var(--shadow-card)', overflow: 'hidden' }}>
      <Tile first label="Поступления" big={inF.num} unit={`${inF.unit} факт`} fg="var(--money-fg)"
        sub={`ожидаем ещё ${short(s.income_plan)} по плану`} active={quick === 'in'} onClick={pick('in')} />
      <Tile label="Списания" big={outF.num} unit={`${outF.unit} факт`}
        sub={`к оплате ещё ${short(s.expense_plan)} по плану`} active={quick === 'out'} onClick={pick('out')} />
      <Tile label="Сальдо" big={sal.num} unit={`${sal.unit} факт`} fg={s.saldo_fact < 0 ? 'var(--bad-fg)' : undefined}
        sub={`с планом ${money(s.saldo_fact + s.saldo_plan, true).num} ${money(s.saldo_fact + s.saldo_plan).unit}`} />
      <Tile label="Просроченная ДЗ" big={over.num} unit={over.unit} fg={s.overdue_count ? 'var(--signal-num)' : undefined}
        sub={s.overdue_count ? `${s.overdue_count} ${ops(s.overdue_count)} · самая старая ${s.overdue_oldest_days} дн` : 'просрочек нет'}
        active={quick === 'over'} onClick={pick('over')} />
      <Tile label="Незаполненные" big={String(s.empty_count)} unit={ops(s.empty_count)} fg={s.empty_count ? 'var(--attn-fg)' : undefined}
        sub="нет контрагента или статьи" active={quick === 'empty'} onClick={pick('empty')} />
      {/* проблемные (20.11.2026): удалённый пакет у оплаченной, переделка, расхождение с 1С — разбирать руками */}
      <Tile label="Проблемные" big={String(s.issues_count || 0)} unit={ops(s.issues_count || 0)} fg={s.issues_count ? 'var(--attn-fg, var(--warning-fg))' : undefined}
        sub={s.issues_count ? 'разобрать руками' : 'проблем нет'} active={quick === 'issues'} onClick={pick('issues')} />
    </div>
  )
}

export const QUICK_LABEL = { in: 'Поступления', out: 'Списания', over: 'Просроченная ДЗ', empty: 'Незаполненные', issues: 'Проблемные' }
