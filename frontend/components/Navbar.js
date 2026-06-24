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

  return (
    <div style={{ position: 'sticky', top: 0, zIndex: 100 }}>
      {/* Верхняя строка — логотип и кнопки */}
      <div style={{ background: 'white', borderBottom: '1px solid #e5e7eb', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '48px' }}>
        <div style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }} onClick={() => router.push('/dashboard')}>
          <img src="/logo.png" alt="Логотип" style={{ height: '26px', width: 'auto' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', color: '#6b7280', marginRight: '4px' }}>{name}</span>
          {can(permissions, 'operations') && <button onClick={() => router.push('/operations')} style={{ fontSize: '13px', padding: '5px 12px', borderRadius: '7px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#374151' }}>Операции</button>}
          {can(permissions, 'import') && <button onClick={() => router.push('/import')} style={{ fontSize: '13px', padding: '5px 12px', borderRadius: '7px', border: '1px solid #2563eb', background: 'transparent', cursor: 'pointer', color: '#2563eb' }}>Импорт</button>}
          {can(permissions, 'settings_balances') && <button onClick={() => router.push('/settings')} style={{ fontSize: '13px', padding: '5px 12px', borderRadius: '7px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#374151' }}>⚙️ Настройки</button>}
          <button onClick={logout} style={{ fontSize: '13px', padding: '5px 12px', borderRadius: '7px', border: 'none', background: '#dc2626', color: 'white', cursor: 'pointer' }}>Выйти</button>
        </div>
      </div>

      {/* Нижняя строка — вкладки слева, children справа */}
      <div style={{ background: 'white', borderBottom: '1px solid #e5e7eb', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '44px' }}>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          {navItems.map(item => (
            <button key={item.id} onClick={() => router.push(item.href)}
              style={{
                padding: '6px 18px', borderRadius: '7px', border: 'none', cursor: 'pointer',
                fontWeight: active === item.id ? '600' : '400', fontSize: '14px',
                background: active === item.id ? '#2563eb' : 'transparent',
                color: active === item.id ? 'white' : '#374151',
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
