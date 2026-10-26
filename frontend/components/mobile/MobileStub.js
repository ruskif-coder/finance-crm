import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import useIsMobile from './useIsMobile'
import { isMobileReady } from '@/lib/mobileReady'
import { Z, btn } from '@/components/salesTableKit'

// Заглушка на телефоне для экранов без мобильной вёрстки (владелец 16.10.2026: «этот экран для девайсов
// побольше»). Встаёт ПОВЕРХ страницы, а не вместо неё: входы контуров перебрасывают дальше из кода
// страницы, и её надо смонтировать. «Открыть всё равно» запоминается на вкладку браузера для этого адреса.
const KEY = 'mobile_stub_skip'

const readSkip = () => {
  try { return JSON.parse(sessionStorage.getItem(KEY) || '[]') } catch { return [] }
}

export default function MobileStub() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [skip, setSkip] = useState([])
  useEffect(() => { setSkip(readSkip()) }, [])
  const path = router.pathname
  if (!isMobile || isMobileReady(path) || skip.includes(path)) return null
  const open = () => {
    const next = [...skip, path]
    try { sessionStorage.setItem(KEY, JSON.stringify(next)) } catch { /* приватный режим — просто на этот раз */ }
    setSkip(next)
  }
  return (
    <div data-overlay="" style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--bg-canvas)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 360, textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <b style={{ fontSize: 18, color: 'var(--text-primary)' }}>Этот экран — для устройств побольше</b>
        <span style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          Он пока не адаптирован под телефон. Откройте его на компьютере или планшете в горизонтальном положении.</span>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button type="button" style={btn(false)} onClick={() => router.push('/')}>На главную</button>
          <button type="button" style={btn(true)} onClick={open}>Открыть всё равно</button>
        </div>
      </div>
    </div>
  )
}
