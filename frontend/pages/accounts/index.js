import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function AccountsEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const isAdmin = localStorage.getItem('role') === 'admin'
    router.replace(entryHref('accounts', perms, isAdmin) || firstAllowedHref(perms, isAdmin))
  }, [])
  return null
}
