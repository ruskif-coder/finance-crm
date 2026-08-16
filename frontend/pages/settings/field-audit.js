import { useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { UI } from '../../components/salesTableKit'
import FieldAuditPanel from '../../components/FieldAuditPanel'

export default function SettingsFieldAudit() {
  const router = useRouter()
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('field_audit')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
  }, [])
  return (
    <>
      <Head><title>Сверка полей | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="field_audit" />
        <FieldAuditPanel />
      </div>
    </>
  )
}
