// Корень контура — не страница, а переброс на первый доступный экран по правам.
// Человек, которому закрыт дашборд продаж, попадает в реестр, а не в отказ.
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function SalesEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const isAdmin = localStorage.getItem('role') === 'admin'
    router.replace(entryHref('sales', perms, isAdmin) || firstAllowedHref(perms, isAdmin))
  }, [])
  return null
}
