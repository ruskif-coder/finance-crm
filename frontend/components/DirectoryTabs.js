import { useRouter } from 'next/router'
import { can } from './Navbar'

// Единая строка вкладок каталога справочников. Показывается и на directories.js,
// и на отдельных страницах (advertisers/agencies/pipelines), чтобы между разделами
// можно было переключаться откуда угодно.
//
// Вкладки Контрагенты/Статьи/Договоры живут внутри directories.js как внутренние
// табы — ведём на /directories?tab=<id>. Остальные — отдельные страницы.
export default function DirectoryTabs({ active, actions }) {
  const router = useRouter()
  let perms = {}
  let role = ''
  if (typeof window !== 'undefined') {
    try { perms = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
    role = localStorage.getItem('role') || ''
  }
  const isAdmin = role === 'admin'

  // Статьи и Воронки переехали в раздел «Настройки» (вкладки /settings).
  const tabs = []
  if (isAdmin || can(perms, 'counterparties', 'view')) tabs.push({ id: 'counterparties', label: 'Контрагенты', href: '/counterparties' })
  if (isAdmin || can(perms, 'contracts', 'view')) tabs.push({ id: 'contracts', label: 'Договора', href: '/contracts' })
  if (isAdmin || can(perms, 'dir_advertisers', 'view')) tabs.push({ id: 'advertisers', label: 'Рекламодатели', href: '/advertisers' })
  if (isAdmin || can(perms, 'dir_agencies', 'view')) tabs.push({ id: 'agencies', label: 'Агентства', href: '/agencies' })
  if (isAdmin || can(perms, 'bx_reconcile', 'view')) tabs.push({ id: 'reconcile', label: 'Сверка с Битриксом', href: '/reconcile' })

  return (
    <div className="desktop-only" style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '10px 14px', marginBottom: 16 }}>
      {tabs.map(t => {
        const isActive = t.id === active
        return (
          <button key={t.id} onClick={() => !isActive && router.push(t.href)}
            style={{
              padding: '8px 14px', borderRadius: 10, border: 'none', cursor: isActive ? 'default' : 'pointer',
              fontWeight: isActive ? 700 : 600, fontSize: 14, whiteSpace: 'nowrap',
              background: isActive ? 'var(--accent-tint)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
              transition: 'background-color 150ms ease, color 150ms ease',
            }}>
            {t.label}
          </button>
        )
      })}
      {actions && <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>{actions}</span>}
    </div>
  )
}
