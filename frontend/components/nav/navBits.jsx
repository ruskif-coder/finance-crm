// Мелочи строки меню v3: пиктограмма 16×16 с обводкой 1.5 (README §6), счётчик, кривая анимаций (README §8).
import { MONO } from '@/components/salesTableKit'

export const EASE = 'var(--ease-out)'   // = токен --ease-out (styles/globals.css, «Стандарт движения»); имя — для файлов меню

/** Пути пиктограмм кнопок справа — из `icons/ui` хендоффа; сводка руководителя — своя (в макете её нет). */
export const UI_ICON = {
  search: 'M7 2.8a4.2 4.2 0 1 0 0 8.4 4.2 4.2 0 0 0 0-8.4zM10.2 10.2l3 3',
  gear: 'M8 5.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4zM8 1.8v1.7M8 12.5v1.7M1.8 8h1.7M12.5 8h1.7M3.6 3.6l1.2 1.2M11.2 11.2l1.2 1.2M12.4 3.6l-1.2 1.2M4.8 11.2l-1.2 1.2',
  exec: 'M2.5 13.5h11M4.5 13.5v-4M8 13.5V5M11.5 13.5V8',
}

export const Ico = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
)

const badgeBase = { fontFamily: MONO, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 17, height: 16,
  padding: '0 4px', boxSizing: 'border-box', borderRadius: 8, fontSize: 9.5, fontWeight: 700 }

/** Счётчик в строке — после названия; `corner` — в правом верхнем углу свёрнутого пункта. */
export const Badge = ({ children, corner, title }) => (
  <span title={title} style={corner
    ? { ...badgeBase, position: 'absolute', top: -4, right: -2, background: 'var(--accent)', color: 'var(--bg-card)',
        border: '2px solid var(--bg-card)', height: 18, animation: `m-bounce var(--dur-slow) ${EASE} both` }
    : { ...badgeBase, background: 'var(--accent-tint)', color: 'var(--accent-fg)' }}>{children}</span>
)

/** Кнопка 32×32 справа (README §1: «Кнопки справа — 32×32, радиус 10»). */
export const iconBtn = {
  border: 'none', font: 'inherit', position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 32, height: 32, padding: 0, borderRadius: 10, background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer',
}

export const NAV3_CSS = `
  
  
  .nav3-row:not([data-on]):hover { background: var(--bg-subtle) !important }
  .nav3-star:hover { color: var(--warning) !important; transform: scale(1.2) }
  .nav3-chip:hover { border-color: var(--border-hover) !important; color: var(--text-primary) !important }
  .nav3-btn { transition: background var(--dur-fast) ease, color var(--dur-fast) ease, transform var(--dur-fast) ease }
  .nav3-btn:hover { background: var(--bg-subtle) !important; color: var(--accent) !important }
  .nav3-btn:active, .nav3-top:active { transform: scale(0.96) }
  .nav3-dir:hover { border-color: var(--border-hover) !important }
  .nav3-back:hover { opacity: 1 !important; background: var(--bg-card) }
`
