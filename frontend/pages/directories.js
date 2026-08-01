import { useEffect } from 'react'
import { useRouter } from 'next/router'

export default function Directories() {
  const router = useRouter()
  useEffect(() => { router.replace('/counterparties') }, [])
  return null
}
