import { useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import { isAdmin } from '../../lib/auth'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { UI, PAGE_W } from '../../components/salesTableKit'
import Articles from '../articles'

export default function SettingsArticles() {
  const router = useRouter()
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('articles')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, isAdmin())); return }
  }, [])
  return (
    <>
      <Head><title>Статьи · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="articles" />
        {/* Ряд вкладок — на всю ширину, содержимое — под 1600 по левому краю (владелец 16.11.2026). */}
        <div style={{ maxWidth: PAGE_W.base }}>
          <Articles embedded />
        </div>
      </div>
    </>
  )
}
