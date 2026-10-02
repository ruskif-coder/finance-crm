import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { getPermissions, isAdmin } from '@/lib/auth'
import { entryHref, firstAllowedHref } from '@/lib/nav'

export default function DirectoryEntry() {
  const router = useRouter()
  useEffect(() => {
    const perms = getPermissions()
    const admin = isAdmin()
    router.replace(entryHref('directory', perms, admin) || firstAllowedHref(perms, admin))
  }, [])
  return null
}
