// Строка меню v3 · микс (хендофф design_handoff_nav_mix, 17.11.2026), десктоп. Слева направо: логотип · контуры · поиск ·
// «Справочники» · закреплённые · ₽ · сбой · колокольчик · шестерёнка · профиль. Названия контуров уходят: развёрнут
// активный и тот, на который навели, остальные — пиктограмма. Подсветка активного и наведения — два слоя, которые
// переезжают, а не гаснут и зажигаются. Меню ничего не правит в данных — только переходы.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { layoutOf, objectOf, pinsShown, sumBadge } from '@/lib/navModel.mjs'
import { useDeclaredObject } from '@/lib/navObject'
import SearchBar from '@/components/search/SearchBar'
import ScreenPanel from './ScreenPanel'
import useNavPrefs from './useNavPrefs'
import useNavKeys from './useNavKeys'
import { Badge, EASE, Ico, NAV3_CSS, UI_ICON, iconBtn } from './navBits'

const OPEN_DELAY = 90
const CLOSE_DELAY = 140
const OPERATIONS = '/finance/operations'

/** Положение пунктов в строке — для переезжающих слоёв; пересчёт на каждое изменение размера (и во время анимации). */
function useRects(box, count) {
  const [rects, setRects] = useState([])
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return undefined
    const measure = () => setRects([...el.querySelectorAll('[data-top]')].map(n => ({ x: n.offsetLeft, w: n.offsetWidth })))
    measure()
    const ro = new ResizeObserver(measure)
    el.querySelectorAll('[data-top]').forEach(n => ro.observe(n))
    return () => ro.disconnect()
  }, [box, count])
  return rects
}

// Сжатие строки при прокрутке — с ДВУМЯ порогами (владелец 17.11.2026: «шапка дрожит между двумя размерами»). С одним
// порогом строка, сжавшись на 12 px, поднимала страницу, прокрутка падала обратно под порог — и строка разжималась,
// и так по кругу. Зазор между порогами больше разницы высот (58 − 46), поэтому собственное сжатие её не перебрасывает.
const COMPACT_AT = 40
const EXPAND_AT = 8

function useCompact() {
  const [c, setC] = useState(false)
  useEffect(() => {
    const on = () => setC(prev => (prev ? window.scrollY >= EXPAND_AT : window.scrollY > COMPACT_AT))
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  return c
}

function TopItem({ s, idx, expanded, active, hovered, sub, obj, onEnter, onClick, onBack }) {
  const badge = sumBadge(s)
  const tip = badge ? s.items.filter(i => i.badge).map(i => `${i.label}: ${i.badge}`).join(' · ') : ''
  return (
    <button type="button" data-top={idx} className="nav3-top" onMouseEnter={onEnter} onClick={onClick} title={expanded ? undefined : s.title}
      style={{ position: 'relative', zIndex: 1, border: 'none', background: 'transparent', font: 'inherit', cursor: 'pointer',
        display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 12px', whiteSpace: 'nowrap',
        color: active ? 'var(--accent-fg)' : hovered ? 'var(--text-primary)' : 'var(--text-muted)', transition: `color var(--dur-base) ease, transform var(--dur-fast) ease` }}>
      <Ico d={s.icon} />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, overflow: 'hidden', maxWidth: expanded ? 560 : 0,
        opacity: expanded ? 1 : 0, marginLeft: expanded ? 8 : 0, fontSize: 13.5, fontWeight: active ? 700 : 600,
        transition: `max-width var(--dur-slow) ${EASE}, opacity var(--dur-base) ease, margin-left var(--dur-slow) ${EASE}` }}>
        {s.title}
        {!!sub && (
          <span style={{ fontWeight: 500, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            <span style={{ opacity: 0.8 }}>·&nbsp;</span>
            {obj
              ? <span role="link" tabIndex={-1} className="nav3-back" title="Вернуться к списку" onClick={onBack}
                  style={{ opacity: 0.85, padding: '2px 4px', margin: '0 -4px', borderRadius: 6 }}>{sub}</span>
              : <span style={{ opacity: 0.8 }}>{sub}</span>}
          </span>
        )}
        {!!obj && (
          <span style={{ whiteSpace: 'nowrap', animation: `m-bounce var(--dur-slow) ${EASE} both` }}>
            <span style={{ fontWeight: 500, color: 'var(--accent)', opacity: 0.8 }}>·&nbsp;</span>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{obj}</span>
          </span>
        )}
        {!!badge && <Badge title={tip}>{badge}</Badge>}
        <span style={{ fontSize: 8, color: 'var(--text-faint)', transition: `transform var(--dur-base) ${EASE}`, transform: hovered ? 'rotate(180deg)' : 'none' }}>▾</span>
      </span>
      {!expanded && !!badge && <Badge corner title={tip}>{badge}</Badge>}
    </button>
  )
}

function SearchField({ open, onOpen, onClose, onNavigate }) {
  return (
    <span style={{ flex: open ? '1 1 auto' : '0 0 150px', maxWidth: open ? 900 : 150, minWidth: 0, display: 'flex', margin: '0 12px 0 10px',
      transition: `max-width var(--dur-slow) ${EASE}` }}>
      {open ? <SearchBar height={34} onClose={onClose} onNavigate={onNavigate} /> : (
        <button type="button" onClick={onOpen} title="Поиск (Ctrl K)" aria-label="Поиск"
          style={{ flex: '1 1 auto', display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, boxSizing: 'border-box',
            padding: '0 10px 0 12px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
            color: 'var(--text-faint)', font: 'inherit', fontSize: 13, cursor: 'text' }}>
          <Ico d={UI_ICON.search} /><span style={{ flex: '1 1 auto', textAlign: 'left' }}>Поиск</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, padding: '1px 5px', borderRadius: 5, background: 'var(--bg-card)',
            border: '1px solid var(--border-inner)' }}>Ctrl K</span>
        </button>
      )}
    </span>
  )
}

/**
 * props: sections — разделы, доступные роли (с `badge` на экранах); active — {section, item} или null; path — текущий
 * адрес с хвостом; isAdmin, canSettings; onNavigate(href); onLogo(); bug, bell, profile — готовые элементы; children —
 * строка фильтров страницы под меню.
 */
export default function NavBar({ sections, active, path, isAdmin, canSettings, onNavigate, onLogo, bug, bell, profile, children }) {
  const { mains, directory } = layoutOf(sections)
  // Разделы с панелью: контуры и «Справочники» (← → ходят по ним по кругу).
  const panelSecs = directory ? [...mains, directory] : mains
  const currentHref = active?.item?.href || null
  const { pinned, recent, pin } = useNavPrefs(currentHref)
  const compact = useCompact()
  // Высота строки меню — переменной `--nav-h` на <html>: закреплённые строки экранов встают под меню, а не уходят под него
  // («Мои сделки»: панель фильтров и шапка колонок, 18.11.2026). 58 px, сжатая при прокрутке — 46 px.
  useEffect(() => { document.documentElement.style.setProperty('--nav-h', compact ? '46px' : '58px') }, [compact])
  const declared = useDeclaredObject(path)
  const [searchOpen, setSearchOpen] = useState(false)
  const [hov, setHov] = useState(-1)            // индекс раздела в panelSecs, чья панель открыта
  const [focused, setFocused] = useState(-1)    // строка панели, выбранная с клавиатуры
  const [kb, setKb] = useState(false)
  const [moving, setMoving] = useState(false)
  const timer = useRef(null)
  const topsBox = useRef(null)
  const bar = useRef(null)
  const dirRef = useRef(null)

  const tops = mains
  const rects = useRects(topsBox, `${tops.length}|${searchOpen}|${currentHref}|${hov}`)
  const actI = tops.findIndex(s => s.key === active?.section?.key)

  const closeNow = useCallback(() => { clearTimeout(timer.current); setHov(-1); setFocused(-1); setKb(false); setMoving(false) }, [])
  const enter = (i) => {
    clearTimeout(timer.current)
    if (hov === i) return
    if (hov >= 0) { setMoving(true); setHov(i); setKb(false); setFocused(-1); return }
    timer.current = setTimeout(() => { setMoving(false); setHov(i) }, OPEN_DELAY)
  }
  const leave = () => { clearTimeout(timer.current); timer.current = setTimeout(closeNow, CLOSE_DELAY) }
  const keep = () => clearTimeout(timer.current)
  useEffect(() => () => clearTimeout(timer.current), [])

  const go = useCallback((href) => { closeNow(); setSearchOpen(false); onNavigate(href) }, [closeNow, onNavigate])
  const entry = (s) => s.items[0]?.href

  useNavKeys({ tops, panelSecs, hov, focused, currentHref, setHov, setFocused, setKb, setMoving, closeNow, go,
    openSearch: () => { closeNow(); setSearchOpen(true) } })

  // Под чьим пунктом стоит панель: у контура — его левый край, у «Справочников» — правый край кнопки.
  const [anchor, setAnchor] = useState(null)
  useLayoutEffect(() => {
    if (hov < 0 || !bar.current) return
    const top = bar.current.getBoundingClientRect().bottom
    const isDir = directory && panelSecs[hov] === directory
    const el = isDir ? dirRef.current : topsBox.current?.querySelector(`[data-top="${hov}"]`)
    if (!el) return
    const r = el.getBoundingClientRect()
    setAnchor({ left: r.left, right: r.right, top })
  }, [hov, rects, compact]) // eslint-disable-line react-hooks/exhaustive-deps

  const pins = pinsShown(pinned, mains)
  const opsItem = operationsItem(mains)
  const showRuble = isAdmin && !!opsItem && !pins.some(p => p.href === OPERATIONS)
  const a = rects[actI]
  const hI = hov >= 0 && hov < tops.length ? hov : -1
  const h = rects[hI]
  const panelSection = hov >= 0 ? panelSecs[hov] || null : null

  return (
    <div data-navbar onMouseLeave={leave} onMouseEnter={keep}
      style={{ position: 'sticky', top: 0, zIndex: 40, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-inner)',
        boxShadow: compact ? 'var(--shadow-card)' : 'none', transition: 'box-shadow var(--dur-slow) ease' }}>
      <style>{NAV3_CSS}</style>
      <div ref={bar} style={{ display: 'flex', alignItems: 'center', height: compact ? 46 : 58, padding: '0 20px',
        transition: `height var(--dur-slow) ${EASE}`, color: 'var(--text-primary)' }}>
        <button type="button" onClick={onLogo} aria-label="На главную" title="SIMB-AD"
          style={{ flex: '0 0 150px', display: 'flex', alignItems: 'center', border: 'none', background: 'transparent', padding: 0, cursor: 'pointer' }}>
          <span style={{ width: 133, height: 16, background: 'var(--logo) left center / contain no-repeat' }} />
        </button>

        <div ref={topsBox} style={{ position: 'relative', display: 'flex', gap: 2, height: 34, flex: '0 1 auto', minWidth: 0 }}>
          {a && <span style={{ position: 'absolute', top: 0, left: a.x, width: a.w, height: 34, borderRadius: 10, background: 'var(--accent-tint)',
            transition: `left var(--dur-slow) ${EASE}, width var(--dur-slow) ${EASE}` }} />}
          <span style={{ position: 'absolute', top: 0, left: (h || a || { x: 0 }).x, width: (h || a || { w: 0 }).w, height: 34, borderRadius: 10,
            background: 'var(--bg-subtle)', opacity: h && hI !== actI ? 1 : 0,
            transition: `left var(--dur-slow) ${EASE}, width var(--dur-slow) ${EASE}, opacity var(--dur-base) ease` }} />
          {tops.map((s, i) => {
            const on = i === actI
            const obj = on && !searchOpen ? (declared?.code || objectOf(path, active.item)) : ''
            return (
              <TopItem key={s.key} s={s} idx={i} active={on} hovered={hov === i}
                expanded={!searchOpen && (on || hov === i)} sub={on && !searchOpen ? active.item.label : ''} obj={obj}
                onEnter={() => enter(i)} onClick={() => go(entry(s))}
                onBack={e => { e.stopPropagation(); if (declared?.onBack) { closeNow(); declared.onBack() } else go(active.item.href) }} />
            )
          })}
        </div>

        <SearchField open={searchOpen} onOpen={() => { closeNow(); setSearchOpen(true) }} onClose={() => setSearchOpen(false)}
          onNavigate={href => go(href)} />

        <span onMouseEnter={() => { if (hov >= 0 && !(directory && panelSecs[hov] === directory)) leave() }}
          style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
          {directory && (
            <button ref={dirRef} type="button" className="nav3-dir" onMouseEnter={() => enter(panelSecs.indexOf(directory))}
              onClick={() => go(entry(directory))}
              style={{ font: 'inherit', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, width: 128, height: 32,
                boxSizing: 'border-box', borderRadius: 10, cursor: 'pointer', fontSize: 13,
                border: `1px solid ${active?.section?.key === 'directory' ? 'var(--accent-border)' : 'var(--border-card)'}`,
                background: active?.section?.key === 'directory' ? 'var(--accent-tint)' : 'var(--bg-card)',
                fontWeight: active?.section?.key === 'directory' ? 700 : 600,
                color: active?.section?.key === 'directory' ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
              Справочники<span style={{ fontSize: 8, color: 'var(--text-faint)' }}>▾</span>
            </button>
          )}
          {pins.map(p => {
            const on = p.href === currentHref
            return (
              <button key={p.href} type="button" className="nav3-btn" onClick={() => go(p.href)}
                title={`${p.section.title} · ${p.item.label}${p.item.badge ? `: ${p.item.badge}` : ''}`} aria-label={`${p.section.title} · ${p.item.label}`}
                style={{ ...iconBtn, position: 'relative', background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)' }}>
                <Ico d={p.item.icon || p.section.icon} />
                {/* счётчик пункта и на закреплённой иконке (владелец 19.11.2026) — тот же, что в меню раздела */}
                {!!p.item.badge && <Badge corner>{p.item.badge}</Badge>}
              </button>
            )
          })}
          {isAdmin && (
            <button type="button" className="nav3-btn" onClick={() => go('/exec')} title="Деньги" aria-label="Деньги" style={iconBtn}>
              <Ico d={UI_ICON.exec} />
            </button>
          )}
          {showRuble && (
            <button type="button" className="nav3-btn" onClick={() => go(OPERATIONS)} title="Операции" aria-label="Операции" style={iconBtn}>
              <Ico d={opsItem.icon} />
            </button>
          )}
          {bug}
          {bell}
          {canSettings && (
            <button type="button" className="nav3-btn" onClick={() => go('/settings')} title="Настройки" aria-label="Настройки" style={iconBtn}>
              <Ico d={UI_ICON.gear} />
            </button>
          )}
          {profile}
        </span>
      </div>
      {children && (
        <div style={{ padding: '10px 24px', borderTop: '1px solid var(--border-inner)', display: 'flex', alignItems: 'center',
          justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>{children}</div>
      )}
      <ScreenPanel section={panelSection} anchor={anchor} alignRight={panelSection === directory} moving={moving}
        currentHref={currentHref} focused={focused} kb={kb} pinned={pinned} recent={recent}
        onGo={go} onPin={pin} onEnter={keep} onLeave={leave} />
    </div>
  )
}

/** Пиктограмма «Операций» (₽) одна на панель, закреплённые и кнопку справа (README §6) — из карты, своей копии нет. */
const operationsItem = (mains) => mains.flatMap(s => s.items).find(i => i.href === OPERATIONS)
