// Корень контура — не страница, а переброс на первый доступный экран по правам.
// Человек, которому закрыт ДДС, попадает в P&L, а не в отказ.
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function FinanceEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const isAdmin = localStorage.getItem('role') === 'admin'
    router.replace(entryHref('finance', perms, isAdmin) || firstAllowedHref(perms, isAdmin))
  }, [])
  return null
}
