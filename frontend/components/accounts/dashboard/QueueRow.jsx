// Строка таблицы «Требует действия» (макет «акки 3», README §3).
//
// Ширины — макета, с одной поправкой: у текстовых колонок диапазон вместо точного числа.
// В макете таблица шире 1366 (1448 px) и прокручивалась бы вбок уже на ноутбуке; с
// диапазоном она сжимается до 1366 без прокрутки, а на широком экране колонки встают
// ровно в ширины макета. Тянется одна «Что сделать».
import { MONO, DealCodeLink, SortHead, ROW_TONE } from '@/components/salesTableKit'
import { surfaceTag } from '@/lib/dealTitle'
import { LAYER_DOT, mln } from './ladder'
import StateChips from './StateChips'

export const COLS = [
  { key: 'code', label: 'Код', w: '62px' },
  { key: 'advertiser', label: 'Рекламодатель / бренд', w: 'minmax(130px,180px)' },
  { key: 'agency', label: 'Агентство', w: 'minmax(80px,118px)' },
  { key: 'product', label: 'Услуга', w: 'minmax(96px,124px)' },
  // 128 — чтобы подпись «Бюджет до НДС» стояла в одну строку (владелец 28.09.2026).
  { key: 'amount', label: 'Бюджет до НДС', w: '128px', right: true, nowrap: true },
  { key: 'stage', label: 'Стадия', w: 'minmax(120px,150px)' },
  { key: 'period', label: 'Период', w: '118px' },
  { key: 'todo', label: 'Что сделать', w: 'minmax(196px,1fr)' },
  { key: 'cta', label: '', w: '150px' },
  { key: 'snooze', label: '', w: '28px' },
  { key: 'caret', label: '', w: '20px' },
]
export const GRID = COLS.map(c => c.w).join(' ')

const dm = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : '')
const daysBetween = (a, b) => Math.round((new Date(a) - new Date(b)) / 864e5)

const ClockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
    <circle cx="12" cy="13" r="7" /><path d="M12 10v3.5l2 1.5" /><path d="M9 3h6" />
  </svg>
)

export function QueueHead({ sortKey, sortDir, onSort }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '0 10px',
      borderBottom: '1px solid var(--border-card)' }}>
      {COLS.map(c => (
        <SortHead key={c.key} label={c.label} right={c.right} wrap={!c.nowrap}
          active={sortKey === c.key} dir={sortDir}
          onClick={c.label ? () => onSort(c.key) : undefined} />
      ))}
    </div>
  )
}

// Кнопка строки: залита, когда сделка горит или подходит срок; спокойная — белая с
// синим текстом; кнопки нет — серая подпись, чей это участок («ведёт трафик»).
function Cta({ row, canEdit, onAction }) {
  const a = row.action
  if (!a) {
    return <span style={{ fontSize: 11.5, color: 'var(--text-faint)', textAlign: 'center', whiteSpace: 'nowrap',
      overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.action_note || '—'}</span>
  }
  const calm = row.urgency === 'normal'
  return (
    <button disabled={!canEdit && a.do !== 'link' && a.do !== 'expand'}
      onClick={(e) => { e.stopPropagation(); onAction(row, a) }} title={a.hint || ''}
      style={{ height: 28, padding: '0 11px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'inherit',
        border: calm ? '1px solid var(--accent-border)' : '1px solid transparent',
        background: calm ? 'var(--bg-card)' : 'var(--accent)', color: calm ? 'var(--accent)' : 'var(--on-accent)' }}>
      {a.label}
    </button>
  )
}

export default function QueueRow({ row: r, today, open, canEdit, onToggle, onAction, onSnooze, onUnsnooze }) {
  const tone = ROW_TONE[r.urgency] || ROW_TONE.normal
  const startIn = r.period_from && today ? daysBetween(r.period_from, today) : null
  const endIn = r.period_to && today ? daysBetween(r.period_to, today) : null
  const near = startIn != null && startIn >= 0 && startIn <= 5
  const startSub = startIn == null ? 'даты не заданы'
    : startIn > 0 ? `старт через ${startIn} дн.` : startIn === 0 ? 'старт сегодня'
      : endIn == null ? 'конец периода не задан'
        : endIn >= 0 ? `до конца ${endIn} дн.` : `закончился ${-endIn} дн. назад`
  const surface = surfaceTag(r.inventory)
  const layer = r.our_stage?.money_layer
  return (
    <div onClick={() => onToggle(r)}
      style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', boxSizing: 'border-box',
        padding: '7px 10px', borderBottom: '1px solid var(--border-row)', borderRadius: 9, cursor: 'pointer',
        background: open ? 'var(--bg-tint)' : (r.urgency === 'overdue' || r.urgency === 'today' ? tone.bg : 'transparent'),
        transition: 'background-color 150ms ease' }}>
      <DealCodeLink deal={r} size={11.5} />

      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }} title={r.title || ''}>
        <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {r.advertiser || r.title || '—'}</span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {r.brand || '—'}</span>
      </span>

      <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
        title={r.agency || ''}>{r.agency || '—'}</span>

      <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 7, minWidth: 0 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, flex: '0 0 7px', marginTop: 4,
          background: r.product_color || 'var(--border-hover)' }} />
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={r.product || ''}>{r.product || '—'}</span>
          {!!surface && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', color: 'var(--text-faint)' }}>{surface}</span>}
        </span>
      </span>

      {/* Отступ справа — как у заголовка: сумма не липнет к «Стадии». */}
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap', paddingRight: 8 }}>{mln(r.amount)}</span>

      <span title={r.reason || r.our_stage?.name || ''} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, flex: '0 0 7px',
          background: layer ? (LAYER_DOT[layer] || 'var(--text-faint)') : 'var(--danger)' }} />
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {r.our_stage?.name || 'Без стадии'}</span>
          <span style={{ fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
            {r.stage_days != null ? `на стадии ${r.stage_days} дн.` : '—'}</span>
        </span>
      </span>

      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: near ? 700 : 600, whiteSpace: 'nowrap',
          color: r.period_from ? 'var(--text-primary)' : 'var(--text-faint)' }}>
          {r.period_from ? r.period_from.slice(0, 7) : '—'}</span>
        <span title={startSub} style={{ fontFamily: MONO, fontSize: 9.5, whiteSpace: 'nowrap',
          color: near ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
          {r.period_from ? `${dm(r.period_from)}–${dm(r.period_to)}` : 'даты не заданы'}</span>
      </span>

      <StateChips row={r} />

      <Cta row={r} canEdit={canEdit} onAction={onAction} />

      <span style={{ display: 'flex', justifyContent: 'center' }}>
        {canEdit && (r.snoozed ? (
          <button onClick={(e) => { e.stopPropagation(); onUnsnooze(r) }} title="Вернуть в очередь"
            style={{ width: 28, height: 28, borderRadius: 8, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
              color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>↩</button>
        ) : (
          <button onClick={(e) => { e.stopPropagation(); onSnooze(r) }} title={r.note || 'Отложить и вернуть к дате'}
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 8,
              border: `1px solid ${r.note ? 'var(--warning-border)' : 'var(--border-card)'}`, background: 'var(--bg-card)',
              color: r.note ? 'var(--warning-fg)' : 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
            <ClockIcon /></button>
        ))}
      </span>

      <span style={{ fontSize: 10, color: 'var(--text-faint)', textAlign: 'right' }}>{open ? '▴' : '▾'}</span>
    </div>
  )
}
