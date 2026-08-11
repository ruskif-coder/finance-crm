import { useRouter } from 'next/router'
import { can } from './Navbar'

// Под-навигация раздела «Продажи»: три экрана на одних данных
// (дашборд сотрудника, реестр сделок, аналитика). Показывается на всех трёх
// страницах, чтобы переключаться между ними откуда угодно. Тот же приём, что
// DirectoryTabs у справочников.
export default function SalesTabs({ active }) {
  const router = useRouter()
  let perms = {}
  let role = ''
  if (typeof window !== 'undefined') {
    try { perms = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
    role = localStorage.getItem('role') || ''
  }
  const isAdmin = role === 'admin'
  const tabs = [
    { id: 'dashboard', label: 'Дашборд', href: '/sales-dashboard', section: 'sales_dashboard' },
    { id: 'registry', label: 'Реестр сделок', href: '/sales', section: 'sales_registry' },
    { id: 'analytics', label: 'Аналитика', href: '/analytics', section: 'sales_analytics' },
    { id: 'year_plan', label: 'Годовой план', href: '/deals/year-plan', section: 'year_plan' },
  ].filter(t => isAdmin || can(perms, t.section, 'view'))
  if (!tabs.length) return null

  return (
    <div className="desktop-only" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
      {tabs.map(t => {
        const isActive = t.id === active
        return (
          <button key={t.id} onClick={() => router.push(t.href)}
            style={{
              padding: '6px 16px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontWeight: 500, fontSize: 14, whiteSpace: 'nowrap',
              background: isActive ? 'var(--accent, #2563eb)' : 'var(--bg-subtle, #eef1f7)',
              color: isActive ? '#fff' : 'var(--text-secondary, #374151)',
            }}>
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
