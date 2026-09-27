// Строка глобального поиска в шапке (десктоп). Спецификация: docs/SPEC_глобальный_поиск.md,
// дизайн — хендофф docs/поиск.zip (README §3).
//
// Свёрнута — элемент размером с вкладку контура в конце ряда вкладок. Развёрнута — поле
// на всю ширину от логотипа до правой группы: ряд вкладок на это время скрывает NavDesktop.
// Выпадашка — ровно по ширине поля. Клавиатура: ↑ ↓ по строкам сквозь группы (наведение
// ставит тот же индекс), Enter — подсвеченная строка (без подсветки — единственное
// попадание или страница результатов), Esc — свернуть. Клик мимо сворачивает пустое поле;
// непустое остаётся до Esc, прячется только выпадашка.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { MONO, PortalPopover, UI } from '@/components/salesTableKit'
import { SEARCH_HINT, SEARCH_HINT_TEXT, TYPE_LABELS, internalHref, saveQuery, searchable } from '@/lib/search'
import { DropRow } from './ResultRow'
import useSearch from './useSearch'

const PILL = {
  display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 12px',
  border: '1px solid var(--border-card)', borderRadius: 10, background: 'transparent',
  color: 'var(--text-secondary)', fontFamily: UI, fontSize: 13, cursor: 'pointer',
}
const GROUP_CAP = {
  padding: '8px 10px 4px', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em',
  textTransform: 'uppercase', color: 'var(--text-faint)',
}
const NOTE = { padding: '10px', fontFamily: UI, fontSize: 13, color: 'var(--text-muted)' }

const SearchIcon = ({ size = 15, color = 'currentColor', width = 1.9 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" />
  </svg>
)

export function SearchPill({ onOpen }) {
  return (
    <button type="button" className="nav-item" onClick={onOpen} title="Поиск (Ctrl+K)" style={PILL}>
      <SearchIcon /> Поиск
    </button>
  )
}

/** Ширина поля — выпадашка ровно по ней (хендофф: «ровно по ширине поля»). */
function useWidth(ref) {
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const set = () => setW(el.getBoundingClientRect().width)
    set()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(set) : null
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [ref])
  return w
}

export default function SearchBar({ onClose, onNavigate }) {
  const [q, setQ] = useState('')
  const [drop, setDrop] = useState(true)
  const [hi, setHi] = useState(-1)
  const input = useRef(null)
  const field = useRef(null)
  const width = useWidth(field)
  const { q: forQ, groups, loading, error } = useSearch(q)
  const ready = !!searchable(q) && forQ === searchable(q)
  const flat = useMemo(() => groups.flatMap(g => g.items), [groups])
  // Сквозной индекс строки по всем группам: начало каждой группы в плоском списке.
  const starts = useMemo(() => groups.reduce(
    (acc, g, i) => [...acc, i ? acc[i - 1] + groups[i - 1].items.length : 0], []), [groups])

  useEffect(() => { input.current?.focus() }, [])
  useEffect(() => { setHi(-1) }, [forQ])

  // Клик мимо: пустое поле сворачивается, непустое прячет только выпадашку.
  useEffect(() => {
    const onDown = (e) => {
      if (e.target.closest('[data-search-root]') || e.target.closest('[data-pop-root]')) return
      if (!q.trim()) onClose()
      else setDrop(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [q, onClose])

  const open = (item) => { onClose(); onNavigate(internalHref(item.href)) }
  const openAll = () => {
    const s = searchable(q)
    if (!s) return
    saveQuery(s)
    onClose()
    onNavigate('/search')
  }

  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
    if (e.key === 'ArrowDown' && flat.length) {
      e.preventDefault(); setDrop(true); setHi(i => Math.min(i + 1, flat.length - 1))
    } else if (e.key === 'ArrowUp' && flat.length) {
      e.preventDefault(); setDrop(true); setHi(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (ready && hi >= 0 && flat[hi]) open(flat[hi])
      else if (ready && flat.length === 1) open(flat[0])
      else openAll()
    }
  }

  const s = searchable(q)
  return (
    <div data-search-root style={{ flex: '1 1 auto', minWidth: 0, display: 'flex' }}>
      <style>{`
        @keyframes srchPop { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @keyframes srchPulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
        .srch-input::placeholder { color: var(--text-disabled) }
        .srch-all:hover { color: var(--accent-hover) !important; text-decoration: underline !important }
      `}</style>
      <label ref={field} style={{
        flex: '1 1 auto', minWidth: 0, display: 'flex', alignItems: 'center', gap: 9, height: 38,
        boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-subtle)',
        border: '1px solid var(--accent)', borderRadius: 10,
      }}>
        <SearchIcon color="var(--accent)" width={2} />
        <input ref={input} className="srch-input" value={q} maxLength={100} placeholder={SEARCH_HINT}
          aria-label="Поиск" onChange={e => { setQ(e.target.value); setDrop(true) }}
          onFocus={() => setDrop(true)} onKeyDown={onKey}
          style={{ flex: '1 1 auto', minWidth: 0, height: '100%', border: 'none', outline: 'none',
                   background: 'transparent', fontFamily: UI, fontSize: 13.5, fontWeight: 600,
                   color: 'var(--text-primary)' }} />
        {loading && (
          <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)',
                         animation: 'srchPulse 1.2s ease-in-out infinite' }}>…</span>
        )}
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 7px',
                       border: '1px solid var(--border-card)', borderRadius: 6, fontFamily: MONO,
                       fontSize: 9.5, color: 'var(--text-faint)' }}>Esc</span>
        {/* Выпадашка выносится в body и шрифт шапки не наследует — задаём явно. */}
        <PortalPopover open={drop && !!s && (ready || !!error)} minWidth={width || 420} maxHeight={470} offset={6}
          style={{ width: width || undefined, borderRadius: 14, padding: 8, fontFamily: UI,
                   boxShadow: '0 12px 36px rgba(28,36,51,.16)',
                   animation: 'srchPop .18s cubic-bezier(0.22,1,0.36,1) both' }}>
          {error && <div style={{ ...NOTE, color: 'var(--danger-fg)' }}>{error}</div>}
          {!error && ready && !flat.length && (
            <div style={NOTE}>Ничего не найдено. {SEARCH_HINT_TEXT}</div>
          )}
          {!error && groups.map((g, gi) => (
              <div key={g.type} style={{ display: 'flex', flexDirection: 'column', paddingBottom: 4 }}>
                <span style={GROUP_CAP}>{TYPE_LABELS[g.type] || g.type}</span>
                {g.items.map((it, ii) => {
                  const my = starts[gi] + ii
                  return <DropRow key={`${g.type}-${it.id}`} item={it} q={s} active={my === hi}
                    onOpen={open} onHover={() => setHi(my)} />
                })}
              </div>
          ))}
          {!error && ready && !!flat.length && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px 4px',
                          borderTop: '1px solid var(--border-row)', marginTop: 2 }}>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)' }}>
                ↑ ↓ выбор · Enter открыть · Esc закрыть
              </span>
              <button type="button" className="srch-all" onClick={openAll}
                style={{ marginLeft: 'auto', padding: 0, border: 'none', background: 'transparent',
                         cursor: 'pointer', fontFamily: UI, fontSize: 12, fontWeight: 700,
                         color: 'var(--accent)' }}>
                Все результаты →
              </button>
            </div>
          )}
        </PortalPopover>
      </label>
    </div>
  )
}
