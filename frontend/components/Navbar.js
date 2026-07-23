import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'

const NAV_ITEMS = [
  { id: 'dds',      label: 'ДДС',         href: '/dashboard', section: 'dashboard' },
  { id: 'pl',       label: 'P&L',         href: '/pl', section: 'pl' },
  { id: 'balance',  label: 'Баланс',      href: '/balance', section: 'balance' },
  { id: 'receivables', label: 'Дебиторка', href: '/receivables', section: 'receivables' },
  { id: 'planfact', label: 'План / Факт', href: '/planfact', section: 'planfact' },
  { id: 'sales',    label: 'Продажи',     href: '/sales', section: 'sales_dashboard' },
]

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

export const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

export default function Navbar({ active, children }) {
  const router = useRouter()
  const name = typeof window !== 'undefined' ? localStorage.getItem('name') || '' : ''
  const role = typeof window !== 'undefined' ? localStorage.getItem('role') || '' : ''
  const permissions = getPermissions()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    const h = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const logout = () => { localStorage.clear(); router.push('/login') }

  const navItems = NAV_ITEMS.filter(item => can(permissions, item.section))
  const initial = (name || '?').trim().charAt(0).toUpperCase() || '?'

  const utilBtn = {
    fontSize: '13.5px', padding: '8px 16px', borderRadius: 'var(--radius-btn)',
    border: 'none', background: 'var(--bg-subtle)',
    cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 500, whiteSpace: 'nowrap',
  }

  return (
    <div style={{ position: 'sticky', top: 0, zIndex: 100 }}>
      {/* Единая строка — логотип, вкладки, утилиты, аватар */}
      <header style={{
        background: 'var(--bg-header)', borderBottom: '1px solid var(--border-card)',
        height: '66px',
      }}>
        <div style={{
          maxWidth: 1920, margin: '0 auto', padding: '0 30px', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '36px', minWidth: 0 }}>
            <img src="/logo.png" alt="Логотип" style={{ height: '24px', width: 'auto', display: 'block', cursor: 'pointer', flexShrink: 0 }}
              onClick={() => router.push('/dashboard')}
              onError={(e) => { e.target.style.display = 'none' }} />
            <nav style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
              {navItems.map(item => (
                <button key={item.id} onClick={() => router.push(item.href)}
                  style={{
                    padding: '8px 16px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                    fontWeight: active === item.id ? 600 : 500, fontSize: '14px',
                    background: active === item.id ? 'var(--accent-tint)' : 'transparent',
                    color: active === item.id ? 'var(--accent)' : 'var(--text-secondary)',
                    transition: 'background .15s, color .15s', whiteSpace: 'nowrap',
                  }}>
                  {item.label}
                </button>
              ))}
            </nav>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            {can(permissions, 'operations') && <button onClick={() => router.push('/operations')} style={utilBtn}>Операции</button>}
            {(role === 'admin' || can(permissions, 'counterparties') || can(permissions, 'articles') || can(permissions, 'contracts')) &&
              <button onClick={() => router.push('/directories')} style={utilBtn}>Справочники</button>}
            {role === 'admin' && <button onClick={() => router.push('/settings')} title="Настройки" style={{ ...utilBtn, padding: '8px 12px', fontSize: '16px', lineHeight: 1 }}>⚙️</button>}

            <div ref={menuRef} style={{ position: 'relative', marginLeft: '6px' }}>
              <div onClick={() => setMenuOpen(o => !o)} title={name || ''} style={{
                width: '34px', height: '34px', borderRadius: '50%', background: 'var(--text-primary)',
                color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '14px', fontWeight: 600, cursor: 'pointer', userSelect: 'none',
              }}>
                {initial}
              </div>
              {menuOpen && (
                <div style={{
                  position: 'absolute', top: '42px', right: 0, background: 'var(--bg-card)',
                  border: '1px solid var(--border-card)', borderRadius: 'var(--radius-card-sm)',
                  boxShadow: 'var(--shadow-card)', minWidth: '160px', zIndex: 200, overflow: 'hidden',
                }}>
                  <div style={{ padding: '10px 14px', fontSize: '13.5px', color: 'var(--text-secondary)', fontWeight: 500, borderBottom: '1px solid var(--border-row)' }}>
                    {name || '—'}
                  </div>
                  <button onClick={logout} style={{
                    display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px',
                    fontSize: '13.5px', color: 'var(--dot-overdue)', background: 'transparent',
                    border: 'none', cursor: 'pointer', fontWeight: 500,
                  }}>
                    Выйти
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Вторая строка — опциональные элементы конкретной страницы (фильтры, кнопки) */}
      {children && (
        <div style={{ background: 'var(--bg-header)', borderBottom: '1px solid var(--border-card)', height: '46px' }}>
          <div style={{ maxWidth: 1920, margin: '0 auto', padding: '0 30px', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {children}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
