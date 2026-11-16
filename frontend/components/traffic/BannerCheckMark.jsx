// Значок проверки баннера в браузере (владелец 15–16.11.2026): ✓ прошёл, ✗ — что не так в подсказке, … — в очереди.
// Один на два этапа: пара на отправке («Креативы на проверку», разметка как у DSP) и креатив после заливки (дашборд
// трафика, настоящая разметка DSP). Нет строки проверки — значка нет: залит до появления проверки или проверять нечем
// (Adfox, «вне контура», тизер).
import { fmtDateTime } from '@/lib/dates'

const LOOK = {
  ok: { mark: '✓', color: 'var(--success)' },
  bad: { mark: '✗', color: 'var(--danger)' },
  queued: { mark: '…', color: 'var(--text-faint)' },
}

function titleOf(check, stage) {
  const what = stage === 'pair' ? 'Проверка показа (разметка как у DSP)' : 'Проверка показа'
  if (check.state === 'queued') return `${what} — в очереди`
  const when = check.checked_at ? ` · ${fmtDateTime(check.checked_at)}` : ''
  if (check.state === 'ok') return `${what} пройдена: плашка «Реклама» видна и раскрывает ЕРИД, клик ведёт на ссылку${when}`
  const lines = Object.entries(check.problems || {}).map(([k, v]) => `${k}: ${(v || []).join('; ')}`)
  return `${what} не пройдена${when}\n${lines.join('\n')}`
}

export default function BannerCheckMark({ check, stage = 'creative', withLabel = false }) {
  if (!check) return null
  const s = LOOK[check.state]
  if (!s) return null
  return (
    <span title={titleOf(check, stage)}
      style={{ marginLeft: withLabel ? 0 : 5, fontWeight: 700, color: s.color, cursor: 'help', whiteSpace: 'nowrap' }}>
      {s.mark}
      {withLabel && <span style={{ fontWeight: 500, fontSize: 10.5, marginLeft: 3 }}>баннер</span>}
    </span>
  )
}
