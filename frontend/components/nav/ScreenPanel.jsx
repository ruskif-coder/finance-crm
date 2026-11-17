// Панель экранов меню v3 (хендофф design_handoff_nav_mix, README §2): ОДНА на все контуры. При переходе на соседний
// контур не закрывается, а перетекает — положение, ширина и высота за 340 мс. Живёт в портале у body, как и прежняя:
// внутри шапки она попадала в её стопку и уходила под окна карточки сделки.
import { createPortal } from 'react-dom'
import { MONO, Z } from '@/components/salesTableKit'
import { MAX_PINS, panelCols, recentFor } from '@/lib/navModel.mjs'
import { Ico, EASE, Badge } from './navBits'

const COL = 232
const ROW = 34
const HEAD = 28
const FOOT = 41

export const panelSize = (section, recentCount) => {
  const cols = panelCols(section.items.length)
  const rows = Math.ceil(section.items.length / cols)
  return { cols, rows, width: cols * COL + 16, height: HEAD + rows * ROW + 14 + (recentCount ? FOOT : 0) }
}

const kbd = { fontFamily: MONO, fontSize: 9.5, padding: '1px 5px', borderRadius: 5, background: 'var(--bg-card)',
  border: '1px solid var(--border-inner)', color: 'var(--text-faint)' }

function starTitle(pinned, full) {
  if (pinned) return 'Открепить из шапки'
  if (full) return `В шапке уже ${MAX_PINS} экрана — открепите один, чтобы закрепить этот`
  return 'Закрепить в шапке'
}

function Row({ it, i, n, isDir, current, focused, pinned, full, onGo, onPin }) {
  return (
    <button type="button" className="nav3-row" data-on={current || undefined} onClick={() => onGo(it.href)}
      style={{ border: 'none', font: 'inherit', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 9,
        height: ROW, boxSizing: 'border-box', padding: '0 11px', borderRadius: 10, whiteSpace: 'nowrap', fontSize: 13,
        background: current ? 'var(--accent-tint)' : focused ? 'var(--bg-subtle)' : 'transparent',
        fontWeight: current ? 700 : 600, color: current ? 'var(--accent-fg)' : 'var(--text-primary)',
        animation: `nav3Rise 300ms ${EASE} ${(n - 1 - i) * 26}ms both` }}>
      {isDir || !it.icon
        ? <span style={{ flex: '0 0 7px', width: 7, height: 7, margin: '0 4px', borderRadius: 2, background: current ? 'var(--accent)' : 'var(--border-hover)' }} />
        : <span style={{ flex: '0 0 16px', display: 'inline-flex', color: current ? 'var(--accent)' : 'var(--text-muted)' }}><Ico d={it.icon} /></span>}
      <span style={{ flex: '1 1 auto' }}>{it.label}</span>
      {!!it.badge && <Badge>{it.badge}</Badge>}
      {focused && <span style={kbd}>Enter</span>}
      {!isDir && (
        <span role="button" tabIndex={-1} className={pinned ? 'nav3-star on' : 'nav3-star'} title={starTitle(pinned, full)}
          onClick={e => { e.stopPropagation(); onPin(it.href) }}
          style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22,
            borderRadius: 7, fontSize: 12, lineHeight: 1, cursor: full && !pinned ? 'not-allowed' : 'pointer',
            color: pinned ? 'var(--warning)' : 'var(--text-faint)' }}>{pinned ? '★' : '☆'}</span>
      )}
    </button>
  )
}

/**
 * props: section — раздел или null (закрыта); anchor — {left, right, top} под чьим пунктом; alignRight — у «Справочников»;
 * moving — уже была открыта (тогда перетекает, иначе появляется на месте); currentHref; focused — строка с клавиатуры;
 * kb — открыта с клавиатуры (подсказка в шапке); pinned, recent; onGo(href), onPin(href); onEnter/onLeave — наведение.
 */
export default function ScreenPanel({ section, anchor, alignRight, moving, currentHref, focused, kb, pinned, recent,
  onGo, onPin, onEnter, onLeave }) {
  if (typeof document === 'undefined' || !anchor) return null
  const open = !!section
  const isDir = section?.key === 'directory'
  const rec = section ? recentFor(recent, section, currentHref) : []
  const size = section ? panelSize(section, rec.length) : { cols: 1, rows: 1, width: 248, height: 80 }
  const full = pinned.length >= MAX_PINS
  const left = alignRight ? Math.max(8, anchor.right - size.width) : anchor.left
  const flow = `left 340ms ${EASE}, width 340ms ${EASE}, height 340ms ${EASE}, top 320ms ${EASE}`
  return createPortal(
    /* Внешний слой — прозрачный мост высотой в зазор: мышь, идущая со строки вниз, не «уходит» с меню. */
    <div onMouseEnter={onEnter} onMouseLeave={onLeave}
      style={{ position: 'fixed', zIndex: Z.dropdown, top: anchor.top, left, width: size.width, paddingTop: 6,
        pointerEvents: open ? 'auto' : 'none', transition: moving ? flow : 'none' }}>
      <div style={{ height: size.height, boxSizing: 'border-box', overflow: 'hidden', background: 'var(--bg-card)',
        border: '1px solid var(--border-card)', borderRadius: 14, boxShadow: 'var(--shadow-float)',
        opacity: open ? 1 : 0, transform: open ? 'none' : 'translateY(6px)',
        transition: `${moving ? `height 340ms ${EASE}, ` : ''}opacity 170ms ease, transform 220ms ${EASE}` }}>
        {section && (
          <div key={section.key}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, height: HEAD, boxSizing: 'border-box', padding: '10px 18px 0' }}>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-primary)' }}>{section.title}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{section.items.length} {screensWord(section.items.length)}</span>
              {kb && <span style={{ fontFamily: MONO, marginLeft: 'auto', fontSize: 9.5, whiteSpace: 'nowrap', color: 'var(--text-faint)' }}>↑↓ ←→ Esc</span>}
            </div>
            <div style={{ display: 'grid', gridAutoFlow: 'column', gridTemplateRows: `repeat(${size.rows}, ${ROW}px)`, gridAutoColumns: COL, padding: '5px 7px 7px' }}>
              {section.items.map((it, i) => (
                <Row key={it.href} it={it} i={i} n={section.items.length} isDir={isDir} current={it.href === currentHref}
                  focused={i === focused} pinned={pinned.includes(it.href)} full={full} onGo={onGo} onPin={onPin} />
              ))}
            </div>
            {!!rec.length && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 40, boxSizing: 'border-box', margin: '0 7px', padding: '0 11px',
                borderTop: '1px solid var(--border-inner)' }}>
                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)', paddingRight: 4 }}>недавно</span>
                {rec.map(it => (
                  <button key={it.href} type="button" className="nav3-chip" onClick={() => onGo(it.href)}
                    style={{ font: 'inherit', display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 9px', borderRadius: 8,
                      background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', fontSize: 11.5, fontWeight: 600,
                      color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' }}>{it.label}</button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body)
}

function screensWord(n) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return 'экран'
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'экрана'
  return 'экранов'
}
