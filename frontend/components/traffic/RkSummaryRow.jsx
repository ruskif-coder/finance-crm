// Строка «Сводка» в раскрытой РК дашборда трафика (макет «Дашборд трафика · сводка», 11.10.2026).
// Отвечает на «всё ли в порядке с этой кампанией» без перехода на экран проверок. Данные — ночной
// прогон `app/ad/rk_check.py`, ручка `/api/rk-check/summary`. Цвет и текст считает сервер, экран
// красит и ведёт по ссылке-действию в существующий блок расхлопа (`onAction`).
import { MONO, UI } from '@/components/salesTableKit'

// Уровни сервера → оформление. skip у РК целиком — «проверять нечем», нейтрально.
const LEVEL = {
  red: { label: 'нужно действие', dot: 'var(--danger)', fg: 'var(--danger-fg)', bg: 'var(--danger-tint)', border: 'var(--danger-border)' },
  yellow: { label: 'есть вопросы', dot: 'var(--warning)', fg: 'var(--warning-fg)', bg: 'var(--warning-tint)', border: 'var(--warning-border)' },
  green: { label: 'в порядке', dot: 'var(--income)', fg: 'var(--income-fg)', bg: 'var(--income-tint)', border: 'var(--border-inner)' },
  skip: { label: 'нет данных', dot: 'var(--text-faint)', fg: 'var(--text-muted)', bg: 'var(--bg-subtle)', border: 'var(--border-inner)' },
}
const PIP = { red: 'var(--danger)', yellow: 'var(--warning)', green: 'var(--income)', skip: 'var(--border-inner)' }
const TEXT_FG = { red: 'var(--text-primary)', yellow: 'var(--text-primary)', green: 'var(--text-secondary)', skip: 'var(--text-muted)' }

const ellipsis = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

// «2026-10-11T03:12» → «11.10 03:12»
const stamp = (v) => {
  const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(v || '')
  return m ? `${m[2]}.${m[1]} ${m[3]}` : ''
}

// Квадрат 7×7 перед кодом РК в списке — цвет худшего уровня сводки.
export function SummaryDot({ sum }) {
  if (!sum) return <span style={{ width: 7, height: 7, flex: '0 0 7px' }} />
  const lv = LEVEL[sum.worst] || LEVEL.skip
  return <span title={`Сводка: ${lv.label}`} style={{ width: 7, height: 7, borderRadius: 2, background: lv.dot, flex: '0 0 7px' }} />
}

function Pips({ pips }) {
  return (
    <span style={{ display: 'inline-flex', gap: 2, flex: '0 0 auto' }}>
      {pips.map(p => (
        <span key={p.key} title={`${p.title}: ${p.message}${p.common ? ' (общая причина — на уровень не влияет)' : ''}`}
          style={{ width: 5, height: 10, borderRadius: 1, background: p.common ? 'var(--border-inner)' : PIP[p.level], opacity: p.common ? 0.7 : 1 }} />
      ))}
    </span>
  )
}

function Column({ g, onAction }) {
  const lv = LEVEL[g.level] || LEVEL.skip
  const act = g.action
  return (
    <span title={g.text} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
      gap: 1, padding: '4px 14px', borderLeft: '1px solid var(--border-inner)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: lv.dot, flex: '0 0 7px' }} />
        <span style={{ ...ellipsis, flex: '0 1 auto', fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: '.08em',
          textTransform: 'uppercase', color: 'var(--text-muted)' }}>{g.title}</span>
        <Pips pips={g.pips} />
        {g.total > 0 && (
          <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{g.ok} из {g.total}</span>
        )}
        {!!act && (
          <a href="#" onClick={e => { e.preventDefault(); e.stopPropagation(); onAction(act.target, act) }}
            style={{ ...ellipsis, flex: '0 1 auto', minWidth: 0, marginLeft: 'auto', fontSize: 11, fontWeight: 600,
              color: 'var(--accent)', textDecoration: 'none' }}>{act.label} →</a>
        )}
      </span>
      <span style={{ ...ellipsis, fontSize: 11.5, lineHeight: 1.35, color: TEXT_FG[g.level] }}>{g.text}</span>
    </span>
  )
}

export default function RkSummaryRow({ sum, checkedAt, onAction }) {
  if (!sum) return null
  const lv = LEVEL[sum.worst] || LEVEL.skip
  const calm = sum.all_ok
  const note = stamp(checkedAt)
  return (
    <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'stretch', height: 44, boxSizing: 'border-box',
      background: 'var(--bg-card)', border: `1px solid ${lv.border}`, borderRadius: 12, overflow: 'hidden', fontFamily: UI }}>
      <span style={{ flex: '0 0 140px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'center',
        gap: 1, padding: '4px 14px', background: lv.bg }}>
        <span style={{ fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase',
          color: 'var(--text-muted)' }}>Сводка</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 9.5, fontWeight: 700,
          letterSpacing: '.04em', textTransform: 'uppercase', color: lv.fg, whiteSpace: 'nowrap' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: lv.dot }} />{lv.label}
        </span>
      </span>
      {calm ? (
        <span style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '4px 14px',
          fontSize: 12, color: 'var(--text-secondary)' }}>
          <span style={ellipsis} title={sum.groups.map(g => g.text).join(' · ')}>
            Заведение, сбор и раскладка в норме · {sum.groups.map(g => g.text).filter(Boolean).join(' · ')}</span>
          {!!note && (
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase',
              color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>проверка {note}</span>
          )}
        </span>
      ) : sum.groups.map(g => <Column key={g.key} g={g} onAction={onAction} />)}
    </div>
  )
}
