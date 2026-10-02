import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions, isAdmin as isAdminNow } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function TrafficEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const isAdmin = isAdminNow()
    router.replace(entryHref('traffic', perms, isAdmin) || firstAllowedHref(perms, isAdmin))
  }, [])
  return null
}
