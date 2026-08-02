import { useRouter } from 'next/router'
import { can } from './Navbar'

// Единая строка вкладок каталога справочников. Показывается и на directories.js,
// и на отдельных страницах (advertisers/agencies/pipelines), чтобы между разделами
// можно было переключаться откуда угодно.
//
// Вкладки Контрагенты/Статьи/Договоры живут внутри directories.js как внутренние
// табы — ведём на /directories?tab=<id>. Остальные — отдельные страницы.
export default function DirectoryTabs({ active }) {
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
  // Временный инструмент сверки справочников с Битриксом — только админ.
  if (isAdmin) tabs.push({ id: 'reconcile', label: 'Сверка с Битриксом', href: '/reconcile' })

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
