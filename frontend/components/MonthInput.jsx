// Поле месяца — замена `<input type="month">` (владелец 03.11.2026: в Safari «ломается календарь выбора периода»).
// Десктопный Safari такого поля не знает и рисует обычное текстовое: месяц надо вписывать руками как «2025-12», а
// onChange срабатывает на каждой букве недописанного значения. Здесь — кнопка со значением и сетка месяцев года,
// одинаковые во всех браузерах.
//
// Подменяет поле без правки вызова: value / defaultValue — 'YYYY-MM' или '', onChange получает `{ target: { value } }`,
// как от настоящего поля; style — стиль бывшего поля; autoFocus открывает сетку сразу; onBlur — сетка закрылась.
// `clearable` — строка «Очистить» (для фильтров, где пустой период — «за всё время»).
// Мобильные экраны остаются на родном поле: в iOS у него есть свой выбор месяца.
import { useEffect, useRef, useState } from 'react'
import { MONO, PortalPopover, Z } from '@/components/salesTableKit'

export const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август',
  'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const isYm = (v) => /^\d{4}-\d{2}$/.test(v || '')

export const navBtn = { width: 28, height: 28, borderRadius: 9, border: '1px solid var(--border-card)',
  background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 15,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 }

// Сетка месяцев одного года со стрелками по годам — общая для MonthInput и MonthPicker.
// marked — месяцы, помеченные точкой; markTitle(ym, isMarked) — подсказка у кнопки месяца.
export function MonthGrid({ value, onPick, marked, markTitle }) {
  const [year, setYear] = useState(() => (isYm(value) ? Number(value.slice(0, 4)) : new Date().getFullYear()))
  const has = new Set(marked || [])
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 2px 8px' }}>
        <button type="button" style={navBtn} title="Предыдущий год" onClick={() => setYear(v => v - 1)}>‹</button>
        <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>{year}</span>
        <button type="button" style={navBtn} title="Следующий год" onClick={() => setYear(v => v + 1)}>›</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 72px)', gap: 4 }}>
        {SHORT.map((label, i) => {
          const ym = `${year}-${String(i + 1).padStart(2, '0')}`
          const on = ym === value
          const dim = marked && !has.has(ym)
          return (
            <button type="button" key={ym} onClick={() => onPick(ym)} title={markTitle ? markTitle(ym, has.has(ym)) : undefined}
              style={{ position: 'relative', height: 34, borderRadius: 8, cursor: 'pointer',
                fontFamily: MONO, fontSize: 12, fontWeight: 700,
                border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
                background: on ? 'var(--accent)' : 'var(--bg-card)',
                color: on ? 'var(--on-accent)' : dim ? 'var(--text-faint)' : 'var(--text-primary)' }}>
              {label}
              {has.has(ym) && !on && <span style={{ position: 'absolute', top: 4, right: 5, width: 5, height: 5,
                borderRadius: 3, background: 'var(--accent)' }} />}
            </button>
          )
        })}
      </div>
    </>
  )
}

export default function MonthInput({ value, defaultValue, onChange, onBlur, style, autoFocus = false, clearable = false,
  placeholder = 'выбрать месяц', title }) {
  const [own, setOwn] = useState(defaultValue || '')
  const cur = value !== undefined ? (value || '') : own
  const [open, setOpen] = useState(autoFocus)
  const wasOpen = useRef(autoFocus)
  const root = useRef(null)    // само поле
  const grid = useRef(null)    // сетка в портале

  useEffect(() => {
    if (!open) return undefined
    // По своим узлам, а не по `[data-pop-root]`: поле стоит и внутри чужих панелей (фильтр периода сделок), и клик
    // в соседнее место такой панели — тоже «мимо», сетка должна закрыться.
    const close = (e) => { if (!root.current?.contains(e.target) && !grid.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  useEffect(() => {                       // onBlur — когда сетка закрылась, как уход фокуса с поля
    if (wasOpen.current && !open) onBlur?.()
    wasOpen.current = open
  }, [open, onBlur])

  const emit = (v) => {
    if (value === undefined) setOwn(v)
    onChange?.({ target: { value: v } })
    setOpen(false)
  }
  const label = isYm(cur) ? `${MONTHS[Number(cur.slice(5, 7)) - 1]} ${cur.slice(0, 4)}` : ''

  return (
    <span ref={root} data-pop-root style={{ display: 'inline-flex', minWidth: 0, flex: style?.flex, width: style?.width }}>
      <button type="button" title={title} onClick={() => setOpen(o => !o)}
        style={{ ...style, width: '100%', flex: undefined, display: 'inline-flex', alignItems: 'center', gap: 7,
          justifyContent: 'space-between', cursor: 'pointer', textAlign: 'left', whiteSpace: 'nowrap',
          background: style?.background ?? 'var(--bg-card)', color: label ? (style?.color ?? 'var(--text-primary)') : 'var(--text-faint)',
          ...(open ? { borderColor: 'var(--accent)' } : null) }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label || placeholder}</span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
          strokeLinecap="round" style={{ flexShrink: 0, opacity: 0.6 }}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
      </button>
      {/* Поле стоит и в окнах, и в плавающих панелях выше Z.dropdown — сетка обязана открываться поверх них */}
      <PortalPopover open={open} minWidth={236} style={{ zIndex: Z.overlay + 1 }}>
        <div ref={grid} style={{ display: 'flex', flexDirection: 'column' }}>
          <MonthGrid value={cur} onPick={emit} />
          {clearable && cur && (
            <button type="button" onClick={() => emit('')}
              style={{ marginTop: 6, height: 30, borderRadius: 8, border: 'none', background: 'transparent', cursor: 'pointer',
                fontSize: 12, color: 'var(--text-secondary)' }}>Очистить</button>
          )}
        </div>
      </PortalPopover>
    </span>
  )
}
