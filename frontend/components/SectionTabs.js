import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { getPermissions } from '@/lib/auth'
import { NAV, allowedItems } from '@/lib/nav'

/**
 * Ряд вкладок внутри контура — тот же вид, что у SettingsTabs в «Настройках».
 *
 * Нужен там, где экранов в контуре много и переключаться между ними надо часто:
 * панель в шапке для этого требует навести курсор и попасть в неё, а на самой
 * странице вкладки видны сразу. Раньше эту роль исполняли DirectoryTabs со своим
 * списком экранов — здесь список берётся из карты приложения, чтобы не заводить
 * восьмой источник правды.
 *
 * actions — правая группа кнопок страницы (сброс фильтров, экспорт, импорт).
 * Живут в той же полосе, как и в настройках.
 */
// Брейкпоинт мобильного вида — как в Nav.js.
const BP = 1024

export default function SectionTabs({ section, actions }) {
  const router = useRouter()
  // Права читаем после монтирования: на сервере localStorage нет, и рендер
  // разошёлся бы с клиентским.
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

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

  const s = NAV.find(x => x.key === section)
  if (!s) return null

  const perms = mounted ? getPermissions() : {}
  const isAdmin = mounted && localStorage.getItem('role') === 'admin'
  const items = mounted ? allowedItems(s, perms, isAdmin) : []
  const path = router.asPath.split('?')[0]

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      ...(isMobile ? {
        flexWrap: 'nowrap', overflowX: 'auto', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
        maskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
        WebkitMaskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
      } : { flexWrap: 'wrap' }),
      background: 'var(--bg-card)', border: '1px solid var(--border-card)',
      boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '10px 14px', marginBottom: 16,
    }}>
      {items.map(it => {
        const isActive = path === it.href || path.startsWith(it.href + '/')
        return (
          <button key={it.key} onClick={() => !isActive && router.push(it.href)}
            style={{
              padding: '8px 14px', borderRadius: 10, border: 'none', cursor: isActive ? 'default' : 'pointer',
              fontWeight: isActive ? 700 : 600, fontSize: 14, whiteSpace: 'nowrap', ...(isMobile ? { flex: '0 0 auto' } : null),
              background: isActive ? 'var(--accent-tint)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
              transition: 'background-color 150ms ease, color 150ms ease',
            }}>
            {it.label}
          </button>
        )
      })}
      {actions && <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, ...(isMobile ? { flex: '0 0 auto' } : null) }}>{actions}</span>}
    </div>
  )
}
