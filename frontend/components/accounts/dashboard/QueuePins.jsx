// Пины очереди (макет «акки 3», README §3).
//
// QuickPins — справа в шапке «Требует действия»: пять участков работы, «Без срочности»
// и «⏱ Отложено». Стадийные пины и лестница «В работе» — один и тот же фильтр.
// ActionPins — под тулбаром: какие кнопки у строк выбранной стадии и сколько их.
// Появляются только после выбора стадии: без неё список действий был бы всем подряд.
import { MONO } from '@/components/salesTableKit'
import { QUICK } from './ladder'

const pin = (on, hot) => ({
  display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 8,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
  border: `1px solid ${on ? 'var(--accent-border)' : hot ? 'var(--danger-border)' : 'var(--border-card)'}`,
  color: on ? 'var(--accent)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600,
  whiteSpace: 'nowrap', cursor: 'pointer', transition: 'background-color 150ms ease, color 150ms ease',
})
const num = (on, hot) => ({ fontFamily: MONO, fontSize: 10, fontWeight: 700,
  color: hot ? 'var(--danger-fg)' : on ? 'var(--accent)' : 'var(--text-faint)' })

export function QuickPins({ counts, stage, onStage, calmN, calmOnly, onCalm, snoozedN, snoozeOpen, onSnooze }) {
  return (
    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4, flexWrap: 'wrap' }}>
      {QUICK.map(([label, key]) => {
        const on = stage === key
        const c = counts[key] || { n: 0, hot: 0 }
        return (
          <span key={key} onClick={() => onStage(on ? null : key)} title={`Показать: ${label}`} style={pin(on, !!c.hot)}>
            {label}<span style={num(on, !!c.hot)}>{c.n}</span>
          </span>
        )
      })}
      <span onClick={onCalm} title="Сделки, по которым сейчас ничего не горит — по умолчанию в конце списка"
        style={pin(calmOnly, false)}>
        Без срочности<span style={num(calmOnly, false)}>{calmN}</span>
      </span>
      <span onClick={onSnooze} title="Отложенные сделки — вернутся в очередь сами"
        style={{ ...pin(false, false), background: snoozeOpen ? 'var(--bg-subtle)' : 'var(--bg-card)',
          borderColor: snoozeOpen ? 'var(--border-hover)' : 'var(--border-card)',
          color: snoozeOpen ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: snoozeOpen ? 700 : 600 }}>
        ⏱ Отложено<span style={num(false, false)}>{snoozedN}</span>
      </span>
    </span>
  )
}

export function ActionPins({ rows, stageOn, act, onAct }) {
  const counts = new Map()
  const hot = new Set()
  rows.forEach(r => {
    const a = r.action?.label
    if (!a) return
    counts.set(a, (counts.get(a) || 0) + 1)
    if (r.urgency === 'overdue') hot.add(a)
  })
  const list = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const total = list.reduce((s, [, n]) => s + n, 0)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', padding: '10px 2px 2px', borderTop: '1px solid var(--border-row)' }}>
      <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', paddingRight: 4 }}>
        Вид работы</span>
      {!stageOn ? (
        <span style={{ ...pin(false, false), background: 'var(--bg-subtle)', borderColor: 'var(--border-inner)', color: 'var(--text-faint)', cursor: 'default' }}>
          Выберите стадию справа — здесь появятся её действия</span>
      ) : (
        <>
          <span onClick={() => onAct(null)} style={pin(!act, false)}>Все<span style={num(!act, false)}>{total}</span></span>
          {list.map(([label, n]) => {
            const on = act === label
            const h = hot.has(label)
            return (
              <span key={label} onClick={() => onAct(on ? null : label)} style={pin(on, h)}>
                <span style={{ width: 6, height: 6, borderRadius: 2, flex: '0 0 6px', background: h ? 'var(--danger)' : 'var(--accent)' }} />
                {label}<span style={num(on, h)}>{n}</span>
              </span>
            )
          })}
        </>
      )}
      <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--border-hover)' }}>
        цвет — критичность</span>
    </div>
  )
}
