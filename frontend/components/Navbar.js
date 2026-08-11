import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import { motion } from 'framer-motion'
import axios from 'axios'
import { getPermissions, can } from '../lib/auth'

// Ре-экспорт: многие страницы делают `import Navbar, { can } from '../components/Navbar'`.
export { can }

const MONO = "'JetBrains Mono', ui-monospace, monospace"
const SPRING = { type: 'spring', stiffness: 420, damping: 36 }

const NAV_ITEMS = [
  { id: 'dds', label: 'ДДС', href: '/dashboard', section: 'dashboard' },
  // «Продажи» — раздел с тремя вложенными экранами (дашборд, реестр сделок,
  // аналитика), под-навигация — SalesTabs. Вход ведёт на дашборд (первый экран).
  { id: 'sales', label: 'Сделки', href: '/sales-dashboard', section: 'sales_dashboard' },
  { id: 'pl', label: 'P&L', href: '/pl', section: 'pl' },
  { id: 'balance', label: 'Баланс', href: '/balance', section: 'balance' },
  { id: 'receivables', label: 'Дебиторка', href: '/receivables', section: 'receivables' },
  { id: 'planfact', label: 'План / Факт', href: '/planfact', section: 'planfact' },
]

// Название текущего раздела и его под-навигация — для мобильной «строки 2»
// (§2 хендоффа) и десктопных SalesTabs/DirectoryTabs (единый источник).
const SECTION_TITLE = {
  dds: 'ДДС', sales: 'Сделки', pl: 'P&L', balance: 'Баланс',
  receivables: 'Дебиторка', planfact: 'План / Факт',
  operations: 'Операции', directories: 'Справочники', settings: 'Настройки',
}
const SECTION_SUBNAV = {
  sales: [
    { label: 'Дашборд', href: '/sales-dashboard', section: 'sales_dashboard' },
    { label: 'Реестр', href: '/sales', section: 'sales_registry' },
    { label: 'Аналитика', href: '/analytics', section: 'sales_analytics' },
    { label: 'Годовой план', href: '/deals/year-plan', section: 'year_plan' },
  ],
  directories: [
    { label: 'Контрагенты', href: '/counterparties', section: 'counterparties' },
    { label: 'Договора', href: '/contracts', section: 'contracts' },
    { label: 'Рекламодатели', href: '/advertisers', section: 'dir_advertisers' },
    { label: 'Агентства', href: '/agencies', section: 'dir_agencies' },
    { label: 'Сверка', href: '/reconcile', adminOnly: true },
  ],
}

// Приоритет разделов для «первого доступного экрана» — единый источник правды
// для редиректа после логина, клика по логотипу и входа в справочники.
const LANDING_ORDER = [
  ['dashboard', '/dashboard'],
  ['sales_dashboard', '/sales-dashboard'],
  ['sales_registry', '/sales'],
  ['sales_analytics', '/analytics'],
  ['year_plan', '/deals/year-plan'],
  ['media_plans', '/deals/mp'],
  ['pl', '/pl'],
  ['balance', '/balance'],
  ['receivables', '/receivables'],
  ['planfact', '/planfact'],
  ['operations', '/operations'],
  ['counterparties', '/counterparties'],
  ['contracts', '/contracts'],
  ['dir_advertisers', '/advertisers'],
  ['dir_agencies', '/agencies'],
  ['settings_balances', '/settings'],
  ['settings_articles', '/settings'],
  ['settings_pipelines', '/settings'],
  ['settings_services', '/settings'],
  ['settings_field_audit', '/settings'],
  ['settings_audit', '/settings'],
]
const DIRECTORY_ORDER = [
  ['counterparties', '/counterparties'],
  ['contracts', '/contracts'],
  ['dir_advertisers', '/advertisers'],
  ['dir_agencies', '/agencies'],
]

// Первый доступный пользователю экран согласно его правам (админ → ДДС).
export const firstAllowedHref = (perms, role) => {
  if (role === 'admin') return '/dashboard'
  for (const [sec, href] of LANDING_ORDER) if (can(perms, sec)) return href
  return '/dashboard'
}
// Первый доступный справочник (для кнопки «Справочники»).
export const firstDirectoryHref = (perms, role) => {
  if (role === 'admin') return '/counterparties'
  for (const [sec, href] of DIRECTORY_ORDER) if (can(perms, sec)) return href
  return '/counterparties'
}

// ── SVG-иконки ───────────────────────────────────────────────────
const Ico = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
)
const IcoBurger = <Ico size={18} d={<><path d="M3 6h18" /><path d="M3 12h18" /><path d="M3 18h18" /></>} />
const IcoClose = <Ico size={18} d={<><path d="M6 6l12 12" /><path d="M18 6L6 18" /></>} />
const IcoGear = <Ico d={<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></>} />
const IcoCaret = <Ico size={10} d={<path d="M6 9l6 6 6-6" />} />
const IcoSearch = <Ico size={17} d={<><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></>} />

export default function Navbar({ active, children, onSearch }) {
  const router = useRouter()
  const name = typeof window !== 'undefined' ? localStorage.getItem('name') || '' : ''
  const role = typeof window !== 'undefined' ? localStorage.getItem('role') || '' : ''
  const permissions = getPermissions()
  const [menuOpen, setMenuOpen] = useState(false)   // профиль-меню (десктоп)
  const [drawer, setDrawer] = useState(false)        // мобильный оверлей
  const menuRef = useRef(null)

  useEffect(() => {
    const h = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  // Уведомления (колокольчик): загрузка + опрос раз в минуту + закрытие по клику вне.
  const notifRef = useRef(null)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifs, setNotifs] = useState([])
  const [unread, setUnread] = useState(0)
  const _authHdr = () => ({ headers: { Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('token') : ''}` } })
  const loadNotifs = () => {
    if (typeof window === 'undefined' || !localStorage.getItem('token')) return
    axios.get('/api/notifications?limit=20', _authHdr()).then(r => { setNotifs(r.data.items || []); setUnread(r.data.unread || 0) }).catch(() => {})
  }
  useEffect(() => {
    loadNotifs()
    const t = setInterval(loadNotifs, 60000)
    const h = (e) => { if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false) }
    document.addEventListener('mousedown', h)
    return () => { clearInterval(t); document.removeEventListener('mousedown', h) }
  }, [])
  const openNotifs = () => {
    const willOpen = !notifOpen
    setNotifOpen(willOpen)
    if (willOpen && unread > 0) axios.post('/api/notifications/read', {}, _authHdr()).then(() => { setUnread(0); setNotifs(ns => ns.map(n => ({ ...n, is_read: true }))) }).catch(() => {})
  }

  // блок скролла body + Esc при открытом мобильном меню
  useEffect(() => {
    if (!drawer) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e) => { if (e.key === 'Escape') setDrawer(false) }
    document.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', onKey) }
  }, [drawer])

  const logout = () => { localStorage.clear(); router.push('/login') }

  // «Продажи» видны, если есть право хотя бы на одну из трёх страниц раздела;
  // вход ведёт на первую доступную (дашборд → реестр → аналитика).
  const SALES = [
    { key: 'sales_dashboard', href: '/sales-dashboard' },
    { key: 'sales_registry', href: '/sales' },
    { key: 'sales_analytics', href: '/analytics' },
    { key: 'year_plan', href: '/deals/year-plan' },
  ]
  const isAdmin = role === 'admin'
  const firstSales = SALES.find(x => isAdmin || can(permissions, x.key))
  const navItems = NAV_ITEMS
    .map(item => item.id === 'sales' && firstSales ? { ...item, href: firstSales.href } : item)
    .filter(item => item.id === 'sales' ? !!firstSales : (isAdmin || can(permissions, item.section)))
  const initial = (name || '?').trim().charAt(0).toUpperCase() || '?'

  const canOperations = can(permissions, 'operations')
  const canMp = isAdmin || can(permissions, 'media_plans', 'view')   // быстрый вход в реестр МП
  const canDirectories = isAdmin || can(permissions, 'counterparties') || can(permissions, 'contracts') || can(permissions, 'dir_advertisers') || can(permissions, 'dir_agencies')
  const canSettings = isAdmin || ['settings_balances', 'settings_articles', 'settings_pipelines', 'settings_services', 'settings_field_audit', 'settings_audit'].some(k => can(permissions, k))
  // Человеческое название роли (role.label с бэкенда); фолбэк — ключ роли.
  const roleLabelRaw = typeof window !== 'undefined' ? localStorage.getItem('role_label') || '' : ''
  const roleLabel = roleLabelRaw || role
  const homeHref = firstAllowedHref(permissions, role)
  const dirHref = firstDirectoryHref(permissions, role)

  const go = (href) => { setDrawer(false); router.push(href) }

  return (
    <>
      <style>{`
        @keyframes navRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes navFade { from { opacity:0 } to { opacity:1 } }
        @keyframes navSheet { from { opacity:0; transform:translateY(-8px) } to { opacity:1; transform:none } }
        .nav-desktop { display:flex }
        .nav-mobile { display:none }
        @media (max-width:1023px){ .nav-desktop{ display:none } .nav-mobile{ display:block } }
        .nav-link:hover { background:var(--bg-subtle); color:var(--text-primary) !important; }
        .nav-out:hover { border-color:#C7D0E8 !important; color:var(--accent) !important; }
        .nav-ico:hover { background:var(--bg-subtle); color:var(--accent) !important; }
        .nav-strip::-webkit-scrollbar { height:0 }
        .nav-strip { scrollbar-width:none }
        .nav-mrow:active { background:var(--bg-subtle) }
        @media (prefers-reduced-motion:reduce){ [style*="animation"]{ animation:none !important } }
      `}</style>

      <div style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)' }}>

        {/* ═══ ДЕСКТОП ═══ */}
        <header className="nav-desktop" style={{
          boxSizing: 'border-box', width: '100%',
          background: 'var(--bg-card)', padding: '12px 24px', alignItems: 'center', gap: 22,
          animation: 'navRise .4s cubic-bezier(0.22,1,0.36,1) both',
        }}>
          <div style={{ paddingRight: 20, borderRight: '1px solid var(--border-inner)', display: 'flex', alignItems: 'center' }}>
            <img src="/logo.png" alt="Логотип" onClick={() => router.push(homeHref)}
              onError={(e) => { e.target.style.display = 'none' }}
              style={{ height: 22, width: 'auto', display: 'block', cursor: 'pointer' }} />
          </div>

          <nav style={{ flex: 1, display: 'flex', gap: 4, alignItems: 'center', minWidth: 0 }}>
            {navItems.map(item => {
              const on = active === item.id
              return (
                <button key={item.id} className={on ? '' : 'nav-link'} onClick={() => router.push(item.href)}
                  style={{ position: 'relative', border: 'none', cursor: 'pointer', background: 'transparent',
                    borderRadius: 10, padding: '8px 14px', fontSize: 14, fontWeight: on ? 700 : 600,
                    color: on ? 'var(--accent)' : 'var(--text-secondary)', whiteSpace: 'nowrap',
                    transition: 'background .15s, color .15s' }}>
                  {on && <motion.span layoutId="navPillDesktop" transition={SPRING}
                    style={{ position: 'absolute', inset: 0, background: 'var(--accent-tint)', borderRadius: 10, zIndex: 0 }} />}
                  <span style={{ position: 'relative', zIndex: 1 }}>{item.label}</span>
                </button>
              )
            })}
          </nav>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {canMp && <button className="nav-out" onClick={() => router.push('/deals/mp')} style={outBtn}>МП</button>}
            {canOperations && <button className="nav-out" onClick={() => router.push('/operations')} style={outBtn}>Операции</button>}
            {canDirectories && <button className="nav-out" onClick={() => router.push(dirHref)} style={outBtn}>Справочники</button>}

            <div ref={notifRef} style={{ position: 'relative' }}>
              <button className="nav-ico" onClick={openNotifs} title="Уведомления" aria-label="Уведомления"
                style={{ width: 32, height: 32, borderRadius: 10, border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', position: 'relative', fontSize: 16 }}>
                🔔
                {unread > 0 && <span style={{ position: 'absolute', top: 1, right: 0, minWidth: 15, height: 15, padding: '0 3px', borderRadius: 8, background: 'var(--danger)', color: '#fff', fontSize: 9, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO }}>{unread > 9 ? '9+' : unread}</span>}
              </button>
              {notifOpen && (
                <div style={{ position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 3000, width: 340, maxHeight: 420, overflowY: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, boxShadow: '0 12px 40px rgba(20,22,28,.18)', padding: 6 }}>
                  <div style={{ padding: '8px 10px', fontSize: 11, fontFamily: MONO, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Уведомления</div>
                  {!notifs.length && <div style={{ padding: '14px 10px', fontSize: 13, color: 'var(--text-muted)' }}>Пока пусто</div>}
                  {notifs.map(n => (
                    <div key={n.id} onClick={() => { setNotifOpen(false); if (n.link) router.push(n.link) }}
                      style={{ padding: '9px 10px', borderRadius: 9, cursor: n.link ? 'pointer' : 'default', background: n.is_read ? 'transparent' : 'var(--accent-tint)', display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 2 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' }}>{n.title}</span>
                      {n.body && <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{n.body}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {canSettings && <button className="nav-ico" onClick={() => router.push('/settings')} title="Настройки" aria-label="Настройки"
              style={{ width: 32, height: 32, borderRadius: 10, border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{IcoGear}</button>}

            <div ref={menuRef} style={{ position: 'relative', paddingLeft: 12, borderLeft: '1px solid var(--border-inner)' }}>
              <div onClick={() => setMenuOpen(o => !o)} title={name || ''}
                style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', userSelect: 'none' }}>
                <span style={avatar(32)}>{initial}</span>
                <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.25, maxWidth: 140 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name || '—'}</span>
                  {roleLabel && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{roleLabel}</span>}
                </span>
                <span style={{ color: 'var(--text-faint)' }}>{IcoCaret}</span>
              </div>
              {menuOpen && (
                <div style={{ position: 'absolute', top: 'calc(100% + 10px)', right: 0, background: 'var(--bg-card)',
                  border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)',
                  minWidth: 180, zIndex: 200, overflow: 'hidden', animation: 'navFade .15s ease both' }}>
                  <div style={{ padding: '11px 14px', borderBottom: '1px solid var(--border-row)' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{name || '—'}</div>
                    {roleLabel && <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', marginTop: 2 }}>{roleLabel}</div>}
                  </div>
                  {canSettings && <button onClick={() => { setMenuOpen(false); router.push('/settings') }} style={menuItem('var(--text-secondary)')}>Настройки</button>}
                  <button onClick={logout} style={menuItem('var(--dot-overdue)')}>Выйти</button>
                  {isAdmin && <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border-row)', fontFamily: MONO, fontSize: 10, letterSpacing: '.04em', color: 'var(--text-faint)' }}>версия v{process.env.NEXT_PUBLIC_APP_VERSION}</div>}
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ═══ МОБИЛЬНЫЙ ═══ */}
        <div className="nav-mobile">
          {/* строка 1 — бургер · логотип · (поиск) · аватар */}
          <header style={{ background: 'var(--bg-card)', borderBottom: '1px solid var(--border-inner)',
            padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setDrawer(true)} aria-label="Открыть меню"
              style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{IcoBurger}</button>
            <img src="/logo.png" alt="Логотип" onClick={() => router.push(homeHref)} onError={(e) => { e.target.style.display = 'none' }}
              style={{ height: 18, width: 'auto', display: 'block', cursor: 'pointer' }} />
            {onSearch && <button onClick={onSearch} aria-label="Поиск"
              style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginLeft: 'auto' }}>{IcoSearch}</button>}
            <button onClick={() => setDrawer(true)} title={name || ''} aria-label="Профиль"
              style={{ ...avatar(36), marginLeft: onSearch ? 0 : 'auto', flexShrink: 0, cursor: 'pointer', border: 'none' }}>{initial}</button>
          </header>

        </div>

        {/* Вторая строка — опциональные элементы страницы (фильтры, кнопки) */}
        {children && (
          <div style={{ padding: '10px 24px', borderTop: '1px solid var(--border-inner)', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
            {children}
          </div>
        )}
      </div>

      {/* ═══ Мобильный оверлей-меню ═══ */}
      {drawer && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 300 }}>
          <div onClick={() => setDrawer(false)} style={{ position: 'absolute', inset: 0, background: 'rgba(28,36,51,.32)', animation: 'navFade .18s ease both' }} />
          <div role="dialog" aria-modal="true" style={{ position: 'absolute', top: 0, left: 0, right: 0, background: 'var(--bg-card)',
            borderRadius: '0 0 18px 18px', boxShadow: 'var(--shadow-card)', padding: 14, maxHeight: '100vh', overflowY: 'auto',
            animation: 'navSheet .24s cubic-bezier(0.22,1,0.36,1) both' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <button onClick={() => setDrawer(false)} aria-label="Закрыть меню"
                style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid #D7DEFA', background: 'var(--accent-tint)', color: 'var(--accent)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{IcoClose}</button>
              <img src="/logo.png" alt="Логотип" onError={(e) => { e.target.style.display = 'none' }} style={{ height: 18, width: 'auto' }} />
            </div>

            {/* разделы + их подразделы */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {navItems.map(item => {
                const on = active === item.id
                const subs = (SECTION_SUBNAV[item.id] || []).filter(s => isAdmin || (s.adminOnly ? isAdmin : can(permissions, s.section)))
                return (
                  <div key={item.id}>
                    <button className="nav-mrow" onClick={() => go(item.href)} style={mRow(on)}>
                      <span style={{ flex: 1 }}>{item.label}</span>
                      {on && <span style={{ fontFamily: MONO, fontSize: 11, color: '#8F9BE8' }}>текущий</span>}
                    </button>
                    {subs.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginLeft: 12, marginTop: 2 }}>
                        {subs.map(s => {
                          const son = router.pathname === s.href || router.asPath.split('?')[0] === s.href
                          return <button key={s.href} className="nav-mrow" onClick={() => go(s.href)} style={mSubRow(son)}><span style={{ flex: 1 }}>{s.label}</span></button>
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* группа «Данные» */}
            {(canOperations || canDirectories) && (
              <>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-faint)', padding: '14px 14px 6px' }}>Данные</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {canMp && <button className="nav-mrow" onClick={() => go('/deals/mp')} style={mRow(false)}><span style={{ flex: 1 }}>Конструктор МП</span></button>}
                  {canOperations && <button className="nav-mrow" onClick={() => go('/operations')} style={mRow(active === 'operations')}><span style={{ flex: 1 }}>Операции</span>{active === 'operations' && <span style={{ fontFamily: MONO, fontSize: 11, color: '#8F9BE8' }}>текущий</span>}</button>}
                  {canDirectories && (
                    <div>
                      <button className="nav-mrow" onClick={() => go(dirHref)} style={mRow(active === 'directories')}><span style={{ flex: 1 }}>Справочники</span>{active === 'directories' && <span style={{ fontFamily: MONO, fontSize: 11, color: '#8F9BE8' }}>текущий</span>}</button>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginLeft: 12, marginTop: 2 }}>
                        {(SECTION_SUBNAV.directories || []).filter(s => isAdmin || (s.adminOnly ? isAdmin : can(permissions, s.section))).map(s => {
                          const son = router.pathname === s.href || router.asPath.split('?')[0] === s.href
                          return <button key={s.href} className="nav-mrow" onClick={() => go(s.href)} style={mSubRow(son)}><span style={{ flex: 1 }}>{s.label}</span></button>
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* профиль */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border-inner)' }}>
              <span style={avatar(38, 12)}>{initial}</span>
              <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.3, flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name || '—'}</span>
                {roleLabel && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{roleLabel}</span>}
                {isAdmin && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)', marginTop: 2 }}>версия v{process.env.NEXT_PUBLIC_APP_VERSION}</span>}
              </span>
              {canSettings && <button onClick={() => go('/settings')} aria-label="Настройки"
                style={{ width: 38, height: 38, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{IcoGear}</button>}
              <button onClick={logout} aria-label="Выйти"
                style={{ width: 38, height: 38, borderRadius: 12, border: '1px solid #F3C9CC', background: 'var(--bg-card)', color: 'var(--dot-overdue)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Ico d={<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></>} /></button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── переиспользуемые стили ───────────────────────────────────────
const outBtn = {
  border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10,
  padding: '7px 13px', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)',
  cursor: 'pointer', whiteSpace: 'nowrap', transition: 'border-color .15s, color .15s',
}
const avatar = (size, radius) => ({
  width: size, height: size, borderRadius: radius || 10, background: 'var(--text-primary)', color: '#fff',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0,
})
const menuItem = (color) => ({
  display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', fontSize: 13,
  color, background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500,
})
const mRow = (on) => ({
  display: 'flex', alignItems: 'center', width: '100%', boxSizing: 'border-box', border: 'none', cursor: 'pointer', textAlign: 'left',
  borderRadius: 12, padding: '13px 14px', fontSize: 15, fontWeight: on ? 700 : 600,
  background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-primary)',
})
const mSubRow = (on) => ({
  display: 'flex', alignItems: 'center', width: '100%', border: 'none', cursor: 'pointer', textAlign: 'left',
  borderRadius: 10, padding: '10px 14px', fontSize: 14, fontWeight: on ? 700 : 500,
  background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-secondary)',
})
