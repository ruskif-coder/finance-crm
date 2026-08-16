import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { firstAllowedHref } from '../lib/nav'

export default function Home() {
  const router = useRouter()
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
      const isAdmin = localStorage.getItem('role') === 'admin'
      router.push(firstAllowedHref(p, isAdmin))
    } else {
      router.push('/login')
    }
  }, [])
  return null
}