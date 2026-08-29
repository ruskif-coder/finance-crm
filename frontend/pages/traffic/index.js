import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function TrafficEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const isAdmin = localStorage.getItem('role') === 'admin'
    router.replace(entryHref('traffic', perms, isAdmin) || firstAllowedHref(perms, isAdmin))
  }, [])
  return null
}
