import { useRouter } from 'next/router'
import { can } from './Navbar'

// Под-навигация раздела «Настройки». Доступ — как у справочников: каждый раздел по
// своему праву (settings_*), Пользователи/Роли — только админ. Показываются лишь
// доступные вкладки; админ видит всё (can() байпасит роль admin).
const SECTIONS = [
  { id: 'balances', label: 'Остатки', href: '/settings/balances', perm: 'settings_balances' },
  { id: 'articles', label: 'Статьи', href: '/settings/articles', perm: 'settings_articles' },
  { id: 'pipelines', label: 'Воронки', href: '/settings/pipelines', perm: 'settings_pipelines' },
  { id: 'services', label: 'Услуги', href: '/settings/services', perm: 'settings_services' },
  { id: 'field_audit', label: 'Сверка полей', href: '/settings/field-audit', perm: 'settings_field_audit' },
  { id: 'audit', label: 'Журнал', href: '/settings/audit', perm: 'settings_audit' },
  { id: 'users', label: 'Пользователи', href: '/settings/users', adminOnly: true },
  { id: 'roles', label: 'Роли', href: '/settings/roles', adminOnly: true },
]

function readPerms() {
  if (typeof window === 'undefined') return { perms: {}, isAdmin: false }
  let perms = {}
  try { perms = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
  return { perms, isAdmin: localStorage.getItem('role') === 'admin' }
}

// Видимость раздела: adminOnly → только админ; иначе по праву settings_* (can байпасит admin).
export function settingsSectionAllowed(id) {
  const { perms, isAdmin } = readPerms()
  const s = SECTIONS.find(x => x.id === id)
  if (!s) return false
  return s.adminOnly ? isAdmin : can(perms, s.perm, 'view')
}

// Первая доступная страница настроек (для редиректа /settings и ссылки в Navbar).
export function firstSettingsHref() {
  const { perms, isAdmin } = readPerms()
  const t = SECTIONS.find(s => s.adminOnly ? isAdmin : can(perms, s.perm, 'view'))
  return t ? t.href : null
}

export default function SettingsTabs({ active, actions }) {
  const router = useRouter()
  const { perms, isAdmin } = readPerms()
  const tabs = SECTIONS.filter(s => s.adminOnly ? isAdmin : can(perms, s.perm, 'view'))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '10px 14px', marginBottom: 16 }}>
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
