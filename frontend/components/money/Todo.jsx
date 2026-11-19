/** «Решить сегодня» (README хендоффа, п. 3–4). Пункты выводятся из тех же данных: оплата со сроком сегодня, провал остатка,
 *  самая тяжёлая просрочка клиента. Кнопки «Что если …» включают сценарий, повторное нажатие выключает. */
import { GLASS, MONO, f, fs, tys } from './kit'
import { ddmm } from './model'

const actBtn = { display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 8, background: 'var(--signal-tint)',
  border: '1px solid var(--signal-border)', color: 'var(--signal-text)', fontSize: 12, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
  fontFamily: 'inherit' }
const wiBtn = (on) => ({ display: 'inline-flex', alignItems: 'center', gap: 5, height: 24, padding: '0 9px', borderRadius: 8,
  background: on ? 'var(--hot)' : 'transparent', border: `1px solid ${on ? 'var(--hot)' : 'var(--border-hover)'}`,
  color: on ? 'var(--hot-fg)' : 'var(--text-secondary)', fontSize: 11.5, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit' })

/** Список пунктов: { key, t, s, v, fg, b, go, wi?: { on, label, toggle } } */
export function todoItems({ R0, thr, data, overdue, move, scen, setScen, pickDay, pickBucket }) {
  const items = []
  const due = R0.days[0].ops.filter(o => o.v < 0 && (o.flag === 'today' || o.flag === 'late')).sort((a, b) => a.v - b.v)[0]
  if (due) {
    items.push({ key: 'due', t: `Оплата ${due.who} — ${due.flag === 'late' ? due.note : 'срок сегодня'}`,
      s: `${due.article || due.cat}${due.invoice ? `, счёт ${due.invoice}` : ''}. После оплаты на счетах останется ${f(data.balance_total + due.v)} ₽.`,
      v: fs(due.v), fg: 'var(--text-primary)', b: 'Открыть', go: () => pickDay(0) })
  }
  if (R0.minB < thr) {
    const day = R0.days[R0.mi]
    items.push({ key: 'dip', t: `${R0.minB < 0 ? `Не хватит ${tys(-R0.minB)}` : `Остаток упадёт до ${tys(R0.minB)}`} · ${ddmm(day.d)}`,
      s: `Ниже неснижаемого ${tys(thr)}.${move ? ` Можно перенести ${move.who} ${tys(move.amount)} на после ${ddmm(R0.days[R0.days.length - 1].d)}.` : ''}`,
      v: fs(R0.minB), fg: 'var(--bad-fg)', b: 'Смотреть день', go: () => pickDay(R0.mi),
      wi: move && { on: scen.moveOut === move.id, label: 'Что если перенести',
        toggle: () => { setScen(s => ({ ...s, moveOut: s.moveOut === move.id ? null : move.id })); pickDay(R0.mi) } } })
  }
  if (overdue) {
    items.push({ key: 'ar', t: `${overdue.who} не платит ${overdue.days} дн`,
      s: `Просрочено ${f(overdue.amount)} ₽ по ${overdue.n} счет${overdue.n === 1 ? 'у' : 'ам'}. Журнала напоминаний в системе пока нет.`,
      v: f(overdue.amount), fg: 'var(--bad-fg)', b: 'К долгам', go: () => pickBucket('over'),
      wi: { on: !!scen.payIn, label: 'Что если заплатит',
        toggle: () => setScen(s => ({ ...s, payIn: s.payIn ? null : { who: overdue.who, amount: overdue.amount } })) } })
  }
  return items
}

export default function Todo({ items }) {
  return (
    <div data-motion="rise" style={{ ...GLASS, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0, '--i': 1 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>Решить сегодня</span>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--signal-num)' }}>{items.length}</span>
      </div>
      {!items.length && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Сегодня решать нечего: сроков нет, остаток выше неснижаемого.</span>}
      {items.map(d => (
        <div key={d.key} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '12px 14px', borderRadius: 14,
          background: 'var(--bg-card)', border: '1px solid var(--border-card)' }}>
          <span style={{ flex: '0 0 8px', width: 8, height: 8, marginTop: 6, borderRadius: '50%', background: 'var(--signal)' }} />
          <div style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700 }}>{d.t}</span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{d.s}</span>
          </div>
          <span style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: d.fg, whiteSpace: 'nowrap' }}>{d.v}</span>
            <button type="button" onClick={d.go} style={actBtn}>{d.b}</button>
            {d.wi && <button type="button" onClick={d.wi.toggle} style={wiBtn(d.wi.on)}>
              {d.wi.on ? `✓ ${d.wi.label.replace('Что если ', '')}` : d.wi.label}</button>}
          </span>
        </div>
      ))}
    </div>
  )
}
