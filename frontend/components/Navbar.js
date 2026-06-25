import { useRouter } from 'next/router'

const NAV_ITEMS = [
  { id: 'dds',      label: 'ДДС',         href: '/dashboard', section: 'dashboard' },
  { id: 'pl',       label: 'P&L',         href: '/pl', section: 'pl' },
  { id: 'balance',  label: 'Баланс',      href: '/balance', section: 'balance' },
  { id: 'receivables', label: 'Дебиторка', href: '/receivables', section: 'receivables' },
  { id: 'planfact', label: 'План / Факт', href: '/planfact', section: 'planfact' },
]

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

export const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

export default function Navbar({ active, children }) {
  const router = useRouter()
  const name = typeof window !== 'undefined' ? localStorage.getItem('name') || '' : ''
  const permissions = getPermissions()

  const logout = () => { localStorage.clear(); router.push('/login') }

  const navItems = NAV_ITEMS.filter(item => can(permissions, item.section))

  const utilBtn = {
    fontSize: '13.5px', padding: '8px 16px', borderRadius: 'var(--radius-btn)',
    border: '1px solid var(--border-card)', background: 'var(--bg-card)',
    cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 500,
  }

  return (
    <div style={{ position: 'sticky', top: 0, zIndex: 100 }}>
      {/* Верхняя строка — логотип и кнопки */}
      <div style={{ background: 'var(--bg-header)', borderBottom: '1px solid var(--border-card)', padding: '0 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '52px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }} onClick={() => router.push('/dashboard')}>
          <img src="/logo.png" alt="Логотип" style={{ height: '26px', width: 'auto', display: 'block' }}
            onError={(e) => { e.target.style.display = 'none' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13.5px', color: 'var(--text-muted)', marginRight: '6px', fontWeight: 500 }}>{name}</span>
          {can(permissions, 'operations') && <button onClick={() => router.push('/operations')} style={utilBtn}>Операции</button>}
          {can(permissions, 'import') && <button onClick={() => router.push('/import')} style={{ ...utilBtn, border: '1px solid var(--accent)', color: 'var(--accent)' }}>Импорт</button>}
          {can(permissions, 'settings_balances') && <button onClick={() => router.push('/settings')} style={utilBtn}>⚙️ Настройки</button>}
          <button onClick={logout} style={{ fontSize: '13.5px', padding: '8px 16px', borderRadius: 'var(--radius-btn)', border: 'none', background: 'var(--dot-overdue)', color: '#fff', cursor: 'pointer', fontWeight: 500 }}>Выйти</button>
        </div>
      </div>

      {/* Нижняя строка — вкладки слева, children справа */}
      <div style={{ background: 'var(--bg-header)', borderBottom: '1px solid var(--border-card)', padding: '0 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '46px' }}>
        <div style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
          {navItems.map(item => (
            <button key={item.id} onClick={() => router.push(item.href)}
              style={{
                padding: '7px 16px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                fontWeight: active === item.id ? 600 : 500, fontSize: '14px',
                background: active === item.id ? 'var(--accent-tint)' : 'transparent',
                color: active === item.id ? 'var(--accent)' : 'var(--text-secondary)',
                transition: 'background .15s, color .15s',
              }}>
              {item.label}
            </button>
          ))}
        </div>
        {children && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {children}
          </div>
        )}
      </div>
    </div>
  )
}
