import React, { useEffect, useMemo, useRef, useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { resolveLegacy } from '@/lib/nav'

/**
 * Виджет «Уведомления» — правая колонка дашборда (25 % ширины ряда).
 * Дизайн — хендофф docs/уведомления.zip (design_handoff_notifications).
 *
 * ГЛАВНОЕ ПРАВИЛО ВЫСОТЫ: виджет ровно такой же высоты, как соседний слева, и НЕ растёт
 * от числа уведомлений. Ряд — align-items:stretch, слот — position:relative,
 * карточка — position:absolute; inset:0. Всё лишнее уходит во внутренний скролл списка.
 *
 * Данные — реальные из /api/notifications: тон, группа и подпись кнопки бэкенд отдаёт
 * по виду события (KIND_META), «где» собирает из объекта события. Здесь ничего не
 * выдумываем: пришло пусто — строка просто без этого куска.
 */

const T = {
  card: '#FFFFFF', unreadBg: '#F6F8FF', hoverBg: '#F6F7FB', tabBg: '#F6F7FB',
  border: '#E3E7F1', row: '#F2F4FA', dotSep: '#C7D0E8',
  t1: '#1C2433', t2: '#525C70', t4: '#A3ABBD',
  accent: '#4F6CE6', accentTint: '#ECEFFD', accentBorder: '#D7DEFA', accentSoft: '#8F9BE8',
  income: '#2FA37C', warning: '#E89020',
  danger: '#C93A3E', dangerTint: '#FBEAEA', dangerBorder: '#F0C9CA',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  mono: MONO, sans: UI, ease: 'cubic-bezier(0.22,1,0.36,1)',
}

export const TONE = { danger: T.danger, warning: T.warning, success: T.income, info: T.accent }
export const TABS = ['Все', 'Сделки', 'Документы', 'Оплаты', 'Брифы']

/** Относительное время: «20 мин» / «1 ч» / «вчера» / «2 дня». */
export function whenText(iso) {
  if (!iso) return ''
  const t = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + 'Z').getTime()
  if (!Number.isFinite(t)) return ''
  const min = Math.max(0, Math.floor((Date.now() - t) / 60000))
  if (min < 1) return 'только что'
  if (min < 60) return `${min} мин`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} ч`
  const d = Math.floor(h / 24)
  if (d === 1) return 'вчера'
  if (d < 5) return `${d} дня`
  return `${d} дней`
}

/** Уведомление из API → строка виджета. */
export function toItem(n) {
  return {
    id: n.id,
    text: n.title || '',
    where: n.where || '',
    when: whenText(n.created_at),
    tone: n.tone || 'info',
    action: n.action || '',
    unread: !n.is_read,
    group: n.group || 'Сделки',
    // Адрес лежит в БД строкой и мог быть записан до переезда разделов —
    // прогоняем через те же правила, что и серверные редиректы.
    href: n.link ? resolveLegacy(n.link) : null,
  }
}

export const NotificationsSlot = ({ children }) => (
  <div style={{ flex: '0 0 25%', minWidth: 280, position: 'relative' }}>{children}</div>
)

function Row({ n, onOpen, onAction }) {
  const [hover, setHover] = useState(false)
  return (
    <div onClick={() => onOpen && onOpen(n)}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', gap: 10, padding: 10, borderRadius: 12, cursor: 'pointer',
        borderBottom: `1px solid ${T.row}`,
        background: hover ? T.hoverBg : (n.unread ? T.unreadBg : T.card),
        transition: 'background-color 150ms ease', animation: `riseIn .24s ${T.ease} both`,
      }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, marginTop: 5, flex: '0 0 8px', background: TONE[n.tone] || T.accent }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600, lineHeight: 1.35, color: T.t1 }}>{n.text}</span>
        {(n.where || n.when) && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            {n.where && (
              <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.where}</span>
            )}
            {n.where && n.when && <span style={{ width: 3, height: 3, borderRadius: 2, background: T.dotSep, flex: '0 0 3px' }} />}
            {n.when && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.t4, whiteSpace: 'nowrap' }}>{n.when}</span>}
          </span>
        )}
        {n.action && (
          <span onClick={e => { e.stopPropagation(); onAction && onAction(n) }}
            style={{
              alignSelf: 'flex-start', height: 26, marginTop: 3, padding: '0 11px', borderRadius: 8,
              display: 'inline-flex', alignItems: 'center', fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
              background: n.tone === 'danger' ? T.dangerTint : T.card,
              border: `1px solid ${n.tone === 'danger' ? T.dangerBorder : T.accentBorder}`,
              color: n.tone === 'danger' ? T.danger : T.accent,
              transition: 'background-color 150ms ease, color 150ms ease',
            }}>{n.action}</span>
        )}
      </div>
      {n.unread && <span style={{ width: 7, height: 7, borderRadius: 2, marginTop: 5, flex: '0 0 7px', background: T.accent }} />}
    </div>
  )
}

export default function NotificationsWidget({ items = [], onOpen, onAction, onReadAll }) {
  const [tab, setTab] = useState('Все')
  const listRef = useRef(null)

  const counts = useMemo(() => {
    const map = { 'Все': items.length }
    TABS.slice(1).forEach(t => { map[t] = items.filter(i => i.group === t).length })
    return map
  }, [items])

  const unread = items.filter(i => i.unread).length
  const list = tab === 'Все' ? items : items.filter(i => i.group === tab)
  // при смене вкладки список — в начало (по ТЗ)
  useEffect(() => { if (listRef.current) listRef.current.scrollTop = 0 }, [tab])

  return (
    <div style={{
      position: 'absolute', inset: 0, boxSizing: 'border-box',
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 28, boxShadow: T.shadow,
      padding: '24px 22px 18px', display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden',
      fontFamily: T.sans, color: T.t1, animation: `riseIn .4s ${T.ease} both`,
    }}>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
      `}</style>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em' }}>Уведомления</span>
        {unread > 0 && (
          <span style={{ minWidth: 20, height: 20, padding: '0 6px', borderRadius: 7, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: T.dangerTint, color: T.danger, fontFamily: T.mono, fontSize: 11, fontWeight: 700 }}>{unread}</span>
        )}
        {unread > 0 && onReadAll && (
          <span onClick={onReadAll} style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: T.accent, cursor: 'pointer', whiteSpace: 'nowrap' }}>Прочитать все</span>
        )}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {TABS.map(t => {
          const on = t === tab
          return (
            <span key={t} onClick={() => setTab(t)} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 9,
              background: on ? T.accentTint : T.tabBg, color: on ? T.accent : T.t2,
              fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer',
              transition: 'background-color 150ms ease, color 150ms ease',
            }}>
              {t}
              <span style={{ fontFamily: T.mono, fontSize: 9.5, color: on ? T.accentSoft : T.t4 }}>{counts[t] || 0}</span>
            </span>
          )
        })}
      </div>

      <div ref={listRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', margin: '0 -10px', padding: '0 10px' }}>
        {list.length === 0
          ? <div style={{ padding: '18px 0', textAlign: 'center', fontSize: 12, color: T.t4 }}>Нет уведомлений</div>
          : list.map(n => <Row key={n.id} n={n} onOpen={onOpen} onAction={onAction} />)}
      </div>
    </div>
  )
}
