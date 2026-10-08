// Оценка темпа площадки за последние сутки (владелец 08.10.2026, `app/ad/pace`): плашка со статусом,
// в подсказке — показано / нужно / предложено сетью и возможность площадки в день. «Хронический» —
// недобор в 3 из последних 5 суток.
import { MONO } from '@/components/salesTableKit'

const TONE = {
  'в темпе': ['var(--income-tint)', 'var(--income-fg)'],
  'перебор': ['var(--accent-tint)', 'var(--accent-fg)'],
  'мало трафика': ['var(--warning-tint)', 'var(--warning-text)'],
  'трафик есть, не открутили': ['var(--danger-tint)', 'var(--danger-fg)'],
  'нет трафика': ['var(--danger-tint)', 'var(--danger-fg)'],
  'недобор': ['var(--warning-tint)', 'var(--warning-text)'],
}
const SHORT = { 'трафик есть, не открутили': 'не открутили', 'мало трафика': 'мало трафика' }
const n = (v) => (v == null ? '—' : Math.round(v).toLocaleString('ru-RU'))

export default function PaceCell({ pace }) {
  if (!pace) return <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>—</span>
  const [bg, fg] = TONE[pace.status] || ['var(--bg-subtle)', 'var(--text-secondary)']
  const title = [
    `${pace.status} · сутки ${String(pace.day).slice(8, 10)}.${String(pace.day).slice(5, 7)}`,
    `показано ${n(pace.shows)} · нужно в сутки ${n(pace.need)}`,
    pace.offered == null ? 'предложено сетью: нет данных' : `предложено сетью ${n(pace.offered)}`,
    pace.capacity != null ? `возможность площадки ≈ ${n(pace.capacity)} в сутки` : '',
    pace.chronic ? 'хронический недобор: 3 из последних 5 суток' : '',
  ].filter(Boolean).join('\n')
  return (
    <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
      <span style={{ padding: '2px 7px', borderRadius: 6, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis', background: bg, color: fg }}>
        {SHORT[pace.status] || pace.status}
      </span>
      {pace.chronic && <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--danger-fg)' }}>⚠</span>}
    </span>
  )
}
