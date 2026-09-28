// Верхний ряд дашборда аккаунта: «В работе» + «Уведомления» (макет «акки 3», README §1–2, §7).
//
// Два вида: развёрнутый (две карточки рядом) и компактный — одна строка. Переключает
// иконка в шапке страницы — та же, что у дашборда трафика (`WidgetsToggle`); выбор
// помнится для каждого пользователя. В компактном виде список
// уведомлений открывается модалкой — она рисуется страницей первым ребёнком корня
// (`NotifyModal`), вне анимированных контейнеров: `transform` предка ломает `fixed`.
import { useState } from 'react'
import { MONO, PIP, Z, card, DealCodeLink } from '@/components/salesTableKit'
import NotificationsWidget from '@/components/dashboard/NotificationsWidget'
import { overlayClose } from '@/lib/overlay'
import { LADDER } from './ladder'

const CAP9 = { fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const mix = (fill) => (fill <= 2 ? PIP[0] : fill <= 4 ? PIP[2] : PIP[4])
const mlnShort = (n) => (n ? `${(n / 1e6).toFixed(1).replace('.', ',')} млн ₽` : '—')

const Badge = ({ n, size = 18 }) => (
  <span title="Горящих сделок на стадии" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    minWidth: size, height: size, padding: '0 5px', boxSizing: 'border-box', borderRadius: 6, flex: '0 0 auto',
    background: 'var(--danger-tint)', color: 'var(--danger-fg)', fontFamily: MONO, fontSize: size > 16 ? 10.5 : 9.5, fontWeight: 700 }}>{n}</span>
)

const Cells = ({ fill, size = 8 }) => (
  <span style={{ display: 'inline-flex', gap: 1, flex: '0 0 auto' }}>
    {PIP.map((c, i) => <span key={i} style={{ width: size, height: size, borderRadius: 2, background: i < fill ? c : 'var(--border-inner)' }} />)}
  </span>
)

/** Счётчики лестницы: {ключ: {n, hot}} — по строкам, которые видит человек. */
export function ladderCounts(rows) {
  const out = Object.fromEntries(LADDER.map(s => [s.key, { n: 0, hot: 0 }]))
  rows.forEach(r => {
    const st = LADDER.find(s => s.slots.includes(r.slot))
    if (!st) return
    out[st.key].n += 1
    if (r.urgency === 'overdue') out[st.key].hot += 1
  })
  return out
}

function Forward({ months }) {
  const LR = 10
  const max = Math.max(1, ...months.map(m => m.total))
  return (
    <div style={{ flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={CAP9}>Загрузка вперёд</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 10, fontSize: 10, color: 'var(--text-faint)' }}>
          {[['подтв.', 'var(--income)'], ['в проработке', 'var(--text-faint)']].map(([l, c]) => (
            <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: c }} />{l}</span>
          ))}
        </span>
      </div>
      <div style={{ flex: '1 1 auto', minHeight: 120, display: 'flex', alignItems: 'stretch', gap: 6 }}>
        {months.map(m => {
          const ok = Math.round(m.ok / max * LR)
          const all = Math.round(m.total / max * LR)
          return (
            <span key={m.ym} title={`${m.label}: ${m.ok} подтверждено, ${m.plan} в проработке`}
              style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
              <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700,
                color: m.hot ? 'var(--warning-fg)' : (m.total ? 'var(--text-primary)' : 'var(--text-faint)') }}>{m.total || '—'}</span>
              <span style={{ width: '100%', flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
                {Array.from({ length: LR }, (_, i) => {
                  const rank = LR - i
                  return <span key={i} style={{ flex: '1 1 0', minHeight: 5, borderRadius: 2,
                    background: rank <= ok ? 'var(--income)' : rank <= all ? 'var(--text-faint)' : 'var(--border-inner)' }} />
                })}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: m.hot ? 'var(--warning-fg)' : 'var(--text-faint)' }}>{m.label}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}

// «Весь список» — все сделки в работе одной лентой; номер открывает карточку в новой вкладке.
function FullList({ rows }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 10, marginTop: 4, borderTop: '1px solid var(--border-card)' }}>
      <span style={CAP9}>Полный список</span>
      <div style={{ maxHeight: 260, overflowX: 'hidden', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2, margin: '0 -8px', padding: '0 8px' }}>
        {rows.map(r => {
          const st = LADDER.find(s => s.slots.includes(r.slot))
          return (
            <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 9, border: '1px solid var(--border-card)' }}>
              <DealCodeLink deal={r} size={10.5} />
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: '1 1 auto' }}>
                <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {[r.advertiser || r.title, r.brand].filter(Boolean).join(' · ')}</span>
                <span style={{ fontSize: 9.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.our_stage?.name || 'Без стадии'}</span>
              </span>
              <Cells fill={st ? st.fill : 0} size={7} />
              <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, flex: '0 0 auto' }}>
                {r.period_from ? `${r.period_from.slice(8, 10)}.${r.period_from.slice(5, 7)}` : '—'}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function WideRow({ rows, counts, stage, onStage, months, budgets, notifs, onOpenNotif, onReadAll, onShowAll }) {
  const total = rows.length
  const [listOpen, setListOpen] = useState(false)
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'stretch' }}>
      <div style={{ ...card, flex: '1.35 1 0', minWidth: 0, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em' }}>В работе</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{total} сделок</span>
          <span onClick={() => setListOpen(o => !o)}
            style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
            {listOpen ? 'Свернуть' : 'Весь список'}</span>
        </div>
        <div style={{ flex: 1, display: 'flex', gap: 18, alignItems: 'stretch', minWidth: 0 }}>
          <div style={{ flex: '1.35 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ display: 'flex', gap: 2, height: 9 }}>
              {LADDER.map(s => !!counts[s.key].n && (
                // Доли — от сделок НА ЛЕСТНИЦЕ, а не от всех: «Без стадии» в лестнице нет,
                // и его доля оставляла полосу недорисованной справа (владелец 28.09.2026).
                <span key={s.key} title={`${s.label} · ${counts[s.key].n}`}
                  style={{ flex: `${counts[s.key].n} 1 0`, minWidth: 4, borderRadius: 3, background: mix(s.fill) }} />
              ))}
              {!LADDER.some(s => counts[s.key].n) && <span style={{ flex: 1, borderRadius: 3, background: 'var(--border-inner)' }} />}
            </span>
            {LADDER.map(s => {
              const on = stage === s.key
              const c = counts[s.key]
              return (
                <div key={s.key} onClick={() => onStage(on ? null : s.key)} title={on ? 'Снять фильтр' : 'Показать в таблице'}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '3px 8px', margin: '0 -8px', borderTop: '1px solid var(--border-row)',
                    borderRadius: 8, cursor: 'pointer', background: on ? 'var(--accent-tint)' : 'transparent', transition: 'background-color 150ms ease' }}>
                  <Cells fill={s.fill} />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: on ? 'var(--accent)' : 'var(--text-primary)', flex: '1 1 auto', minWidth: 0,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.label}</span>
                  {!!c.hot && <Badge n={c.hot} />}
                  <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, minWidth: 20, textAlign: 'right',
                    color: on ? 'var(--accent)' : (c.n ? 'var(--text-primary)' : 'var(--text-faint)') }}>{c.n}</span>
                </div>
              )
            })}
            {listOpen && <FullList rows={rows} />}
          </div>
          <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12, paddingLeft: 18, borderLeft: '1px solid var(--border-inner)' }}>
            <Forward months={months} />
            <div style={{ flex: '0 0 auto', marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 10, borderTop: '1px solid var(--border-row)' }}>
              <span style={CAP9}>Бюджеты под управлением</span>
              <span style={{ fontSize: 10, color: 'var(--text-faint)', lineHeight: 1.35 }}>справочно, суммы до НДС — не показатель работы аккаунта</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '8px 16px', paddingTop: 6 }}>
                {budgets.map(([label, sum], i) => (
                  <span key={label} style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: '0 0 auto' }}>
                    <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{label}</span>
                    <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.1, whiteSpace: 'nowrap',
                      color: i ? 'var(--text-secondary)' : 'var(--text-primary)' }}>{mlnShort(sum)}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div style={{ flex: '1 1 0', minWidth: 0, minHeight: 260, position: 'relative' }}>
        <NotificationsWidget dense items={notifs} onOpen={onOpenNotif} onAction={onOpenNotif} onReadAll={onReadAll}
          onShowAll={onShowAll} />
      </div>
    </div>
  )
}

export function CompactRow({ rows, counts, stage, onStage, notifs, onOpenModal }) {
  const unread = notifs.filter(n => n.unread).length
  return (
    <div style={{ ...card, padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 18, minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8, flex: '0 0 auto' }}>
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em' }}>В работе</span>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{rows.length} сделок</span>
      </span>
      <span style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', gap: 4, overflowX: 'auto', scrollbarWidth: 'none' }}>
        {LADDER.map(s => {
          const on = stage === s.key
          const c = counts[s.key]
          return (
            <span key={s.key} onClick={() => onStage(on ? null : s.key)} title={on ? 'Снять фильтр' : 'Показать в таблице'}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 9px', borderRadius: 8, flex: '0 0 auto',
                background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                whiteSpace: 'nowrap', cursor: 'pointer' }}>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: on ? 'var(--accent)' : 'var(--text-primary)' }}>{s.label}</span>
              {!!c.hot && <Badge n={c.hot} size={16} />}
              <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: on ? 'var(--accent)' : 'var(--text-primary)' }}>{c.n}</span>
            </span>
          )
        })}
      </span>
      <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-inner)', flex: '0 0 1px' }} />
      <span onClick={onOpenModal} title="Открыть все уведомления"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 1 420px', minWidth: 0, padding: '4px 8px', margin: '-4px -8px',
          borderRadius: 10, cursor: 'pointer' }}>
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em', flex: '0 0 auto' }}>Уведомления</span>
        {!!unread && <Badge n={unread} size={20} />}
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          {notifs.slice(0, 2).map(n => (
            <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, flex: '0 0 6px', background: n.unread ? 'var(--accent)' : 'var(--border-hover)' }} />
              <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.text}</span>
            </span>
          ))}
          {!notifs.length && <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>нет уведомлений</span>}
        </span>
      </span>
    </div>
  )
}

export function NotifyModal({ notifs, onClose, onOpenNotif, onReadAll }) {
  return (
    <div {...overlayClose(onClose)}
      style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'rgba(28,36,51,.32)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, boxSizing: 'border-box' }}>
      <div style={{ position: 'relative', width: 560, maxWidth: '100%', height: 'min(82vh, 720px)' }}>
        <NotificationsWidget dense items={notifs} onOpen={onOpenNotif} onAction={onOpenNotif}
          onReadAll={onReadAll} onClose={onClose} />
      </div>
    </div>
  )
}
