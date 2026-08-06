import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { firstSettingsHref } from '../components/SettingsTabs'

// Раздел «Настройки» разнесён на отдельные страницы (/settings/*). Этот роут —
// тонкий редирект на первую ДОСТУПНУЮ секцию (с поддержкой старых ссылок ?tab=<id>).
// Разделы, права и навигация между ними — components/SettingsTabs.js.
const TAB_TO_ROUTE = {
  balances: 'balances', articles: 'articles', pipelines: 'pipelines', services: 'services',
  users: 'users', roles: 'roles', audit: 'audit', field_audit: 'field-audit',
}

export default function SettingsRedirect() {
  const router = useRouter()
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.replace('/login'); return }
    const q = router.query.tab
    if (typeof q === 'string' && TAB_TO_ROUTE[q]) { router.replace('/settings/' + TAB_TO_ROUTE[q]); return }
    const href = firstSettingsHref()
    router.replace(href || '/dashboard')
  }, [router.query.tab])
  return null
}
