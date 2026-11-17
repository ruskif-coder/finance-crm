// Общие мелочи панели площадок v2 (хендофф design_handoff_traffic_expand_v2, раздел 8): сетка, подписи столбцов,
// переключатель «один из», точка статуса, CTR. Цвета — только токены `globals.css`, числа — MONO.
import { MONO } from '@/components/salesTableKit'
import { DASH } from '@/components/traffic/dashboardKit'
import { ctrTone } from '@/lib/sitesModel.mjs'

/** Сетка таблицы площадок — дословно из макета (8.2), шаг 8. */
export const SITE_GRID = 'minmax(184px,1.4fr) 44px 50px 44px 96px 60px 42px 50px minmax(70px,1fr) 62px 56px 64px 74px 68px 54px'
/** Сетка креативов в расхлопе площадки (8.6). */
export const CR_GRID_V2 = 'minmax(110px,1.3fr) 92px minmax(96px,0.9fr) minmax(96px,0.9fr) 50px 64px 60px 44px 78px 100px 116px 54px'

export const CAP_V2 = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
export const NUM = { fontFamily: MONO, fontSize: 11.5, textAlign: 'right', whiteSpace: 'nowrap' }

/** Процент с запятой и сотыми — для CTR: «0,71 %». */
export const pct2 = (v) => (v == null ? DASH : `${Number(v).toFixed(2).replace('.', ',')} %`)
/** Процент с запятой и десятыми — «7,6 %». */
export const pct1 = (v) => (v == null ? DASH : `${Number(v).toFixed(1).replace('.', ',')} %`)

/** Цвет и насыщенность CTR против цели РК (8.2): не ниже цели — зелёным жирно, ниже 0,75 цели — жёлтым жирно. */
export const CTR_STYLE = {
  good: { color: 'var(--income-fg)', fontWeight: 700 },
  low: { color: 'var(--warning-fg)', fontWeight: 700 },
  mid: { color: 'var(--text-secondary)', fontWeight: 400 },
  none: { color: 'var(--text-disabled)', fontWeight: 400 },
}
export const CTR_BAR = { good: 'var(--income)', low: 'var(--warning)', mid: 'var(--text-faint)', none: 'transparent' }

export const ctrTitle = (ctr, goal, empty = 'показов нет') => {
  if (ctr == null) return empty
  if (!goal) return 'цели по CTR в медиаплане нет'
  return `${ctrTone(ctr, goal) === 'good' ? 'не ниже' : 'ниже'} цели РК ${pct2(goal)}`
}

/** Переключатель «один из» (вид, порядок): плашки на подложке, активная — белая с тенью. */
export const Seg = ({ items, value, onPick }) => (
  <span style={{ display: 'inline-flex', padding: 2, borderRadius: 10, background: 'var(--bg-subtle)',
    border: '1px solid var(--border-inner)' }}>
    {items.map(([key, label, title]) => {
      const on = key === value
      return (
        <span key={key} onClick={() => onPick(key)} title={title}
          style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', borderRadius: 8,
            background: on ? 'var(--bg-card)' : 'transparent', boxShadow: on ? 'var(--shadow-card)' : 'none',
            color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 11.5, fontWeight: on ? 700 : 600,
            cursor: 'pointer', whiteSpace: 'nowrap' }}>{label}</span>
      )
    })}
  </span>
)

// Точка + слово статуса (8.2). Слова — боевые статусы площадки и креатива, цвета — по смыслу: крутит, мы
// остановили, мяч у площадки, ещё не дошло, отключено.
const DOT = {
  'запущен': ['var(--income)', 'var(--text-secondary)'],
  'согласован': ['var(--income)', 'var(--text-secondary)'],
  'ждёт запуска': ['var(--income)', 'var(--text-secondary)'],
  'пауза': ['var(--accent)', 'var(--accent-fg)'],
  'у трафика': ['var(--accent)', 'var(--accent-fg)'],
  'у площадки': ['var(--warning)', 'var(--warning-fg)'],
  'отклонён': ['var(--danger)', 'var(--danger-fg)'],
  'ждёт сборки': ['var(--text-disabled)', 'var(--text-faint)'],
  'завершена': ['var(--text-disabled)', 'var(--text-faint)'],
}
export const StatusDot = ({ value, title, size = 11.5 }) => {
  const [dot, fg] = DOT[value] || ['var(--text-disabled)', 'var(--text-muted)']
  return (
    <span title={title || value} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0,
      fontSize: size, fontWeight: 600, color: fg, whiteSpace: 'nowrap' }}>
      <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: 2, background: dot }} />
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{value || DASH}</span>
    </span>
  )
}

/** Мини-полоса CTR со шкалой до 1 % (8.6, 8.8). */
export const CtrBar = ({ ctr, tone, width = 18, height = 5, goal }) => (
  <span style={{ flex: `0 0 ${width}px`, width, height, borderRadius: 3, background: 'var(--bg-card)',
    border: '1px solid var(--border-inner)', boxSizing: 'border-box', position: 'relative',
    overflow: goal ? 'visible' : 'hidden' }}>
    <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 3,
      width: `${ctr == null ? 0 : Math.min(100, Math.round(ctr * 100))}%`, background: CTR_BAR[tone] }} />
    {!!goal && (
      <span title={`Цель РК — ${pct2(goal)}`} style={{ position: 'absolute', top: -3, bottom: -3, width: 2,
        left: `${Math.min(100, goal * 100)}%`, background: 'var(--text-secondary)' }} />
    )}
  </span>
)

/* ── системы: полоски и легенда ─────────────────────────────────────────────── */

// Легенда столбца «Системы» (владелец 17.11.2026): полоски площадки и креатива — в этом же порядке. Цвета у полосок: зелёная —
// готово, жёлтая — ждёт или готово частично, красная обводка — ошибка, пустая — ещё не начато.
const SYS_LEGEND = [
  ['Е', 'ЕРИД креативов'], ['W', 'Пиксель Weborama'], ['D', 'Заведено в DSP'], ['С', 'Скрины запуска'],
]
const SYS_COLORS = 'Полоски — в этом порядке: зелёная — готово, жёлтая — ждёт или частично, красная — ошибка, пустая — не начато'

export const SysLegend = () => (
  <span title={SYS_COLORS} style={{ display: 'inline-flex', gap: 3, cursor: 'help' }}>
    {SYS_LEGEND.map(([l, what]) => (
      <span key={l} title={`${l} — ${what}. ${SYS_COLORS}`}
        style={{ fontFamily: MONO, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16,
          boxSizing: 'border-box', borderRadius: 5, border: '1px solid var(--border-hover)', background: 'var(--bg-card)',
          fontSize: 8.5, fontWeight: 700, color: 'var(--text-faint)' }}>{l}</span>
    ))}
  </span>
)


/** Четыре полоски систем (Е · W · D · С) и подпись «ок» / «нет …» — у площадки и у креатива. */
export const SysCell = ({ s }) => (
  <span title={s.title} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <span style={{ display: 'inline-flex', gap: 2 }}>
      {s.marks.map(m => (
        <span key={m.l} style={{ width: 5, height: 12, borderRadius: 1.5, boxSizing: 'border-box',
          background: m.tone === 'ok' ? 'var(--income)' : m.tone === 'wait' ? 'var(--warning-tint)' : 'transparent',
          border: `1px solid ${m.tone === 'ok' ? 'var(--income)' : m.tone === 'bad' ? 'var(--danger)'
            : s.empty ? 'var(--text-disabled)' : 'var(--warning)'}` }} />
      ))}
    </span>
    <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden',
      color: s.empty ? 'var(--text-disabled)' : !s.missing.length ? 'var(--text-faint)' : 'var(--warning-fg)' }}>{s.label}</span>
  </span>
)
