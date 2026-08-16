import { useEffect } from 'react'
import { useRouter } from 'next/router'

export default function Directories() {
  const router = useRouter()
  // Точка входа контура справочников сама выберет первый ДОСТУПНЫЙ экран по правам.
  useEffect(() => { router.replace('/directory') }, [])
  return null
}
