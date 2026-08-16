import { useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { UI } from '../../components/salesTableKit'
import Articles from '../articles'

export default function SettingsArticles() {
  const router = useRouter()
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('articles')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
  }, [])
  return (
    <>
      <Head><title>Статьи | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="articles" />
        <Articles embedded />
      </div>
    </>
  )
}
