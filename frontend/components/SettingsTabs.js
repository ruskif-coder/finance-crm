import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { can } from './Navbar'

// Брейкпоинт мобильного вида — как в Nav.js.
const BP = 1024

// Под-навигация раздела «Настройки». Доступ — как у справочников: каждый раздел по
// своему праву (settings_*), Пользователи/Роли — только админ. Показываются лишь
// доступные вкладки; админ видит всё (can() байпасит роль admin).
const SECTIONS = [
  // ПЕРВОЙ в разделе (владелец 07.09.2026). Порядок здесь не только про вид: экран
  // отвечает на вопрос «работает ли вообще всё», и его место — до того, как человек
  // пойдёт разбираться с остальным.
  //
  // Следствие, о котором надо помнить: `firstSettingsHref()` берёт ПЕРВУЮ доступную
  // вкладку, поэтому шестерёнка и /settings у админа теперь ведут сюда. У остальных
  // ролей ничего не изменилось — они эту вкладку не видят и попадают на свою первую.
  //
  // adminOnly, а не своё право: экран показывает инфраструктуру, как «Пользователи» и
  // «Роли», и секцию в конструкторе ролей можно выдать по неосторожности.
  { id: 'system', label: 'Статус', href: '/settings/system', adminOnly: true },
  { id: 'balances', label: 'Остатки', href: '/settings/balances', perm: 'settings_balances' },
  { id: 'articles', label: 'Статьи', href: '/settings/articles', perm: 'settings_articles' },
  { id: 'pipelines', label: 'Воронки', href: '/settings/pipelines', perm: 'settings_pipelines' },
  { id: 'stages', label: 'Стадии', href: '/settings/stages', perm: 'settings_pipelines' },
  { id: 'services', label: 'Услуги', href: '/settings/services', perm: 'settings_services' },
  { id: 'field_audit', label: 'Сверка полей', href: '/settings/field-audit', perm: 'settings_field_audit' },
  { id: 'audit', label: 'Журнал', href: '/settings/audit', perm: 'settings_audit' },
  // Рядом с «Журналом» намеренно: журнал — «что сделали», бэклог — «что может выстрелить».
  { id: 'backlog', label: 'Бэклог отладки', href: '/settings/backlog', perm: 'settings_backlog' },
  // Профили уведомлений — политика на всю компанию, поэтому вкладка админская.
  // Личная часть той же страницы открывается всем из меню профиля («Мои уведомления»).
  { id: 'notifications', label: 'Уведомления', href: '/settings/notifications', adminOnly: true },
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
  // Права читаем после монтирования: на сервере localStorage нет, и рендер
  // разошёлся бы с клиентским.
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const { perms, isAdmin } = mounted ? readPerms() : { perms: {}, isAdmin: false }
  const tabs = mounted ? SECTIONS.filter(s => s.adminOnly ? isAdmin : can(perms, s.perm, 'view')) : []

  // isMobile: как в Nav.js — на сервере/первом кадре false, матчится в эффекте,
  // чтобы серверный и первый клиентский рендер совпали (без этого — рассинхрон гидратации).
  const [isMobile, setIsMobile] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(`(max-width:${BP - 1}px)`)
    setIsMobile(mq.matches)
    const on = e => setIsMobile(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      ...(isMobile ? {
        flexWrap: 'nowrap', overflowX: 'auto', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
        maskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
        WebkitMaskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
      } : { flexWrap: 'wrap' }),
      background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '10px 14px', marginBottom: 16,
    }}>
      {tabs.map(t => {
        const isActive = t.id === active
        return (
          <button key={t.id} onClick={() => !isActive && router.push(t.href)}
            style={{
              padding: '8px 14px', borderRadius: 10, border: 'none', cursor: isActive ? 'default' : 'pointer',
              fontWeight: isActive ? 700 : 600, fontSize: 14, whiteSpace: 'nowrap', ...(isMobile ? { flex: '0 0 auto' } : null),
              background: isActive ? 'var(--accent-tint)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
              transition: 'background-color 150ms ease, color 150ms ease',
            }}>
            {t.label}
          </button>
        )
      })}
      {actions && <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, ...(isMobile ? { flex: '0 0 auto' } : null) }}>{actions}</span>}
    </div>
  )
}
