import '../styles/globals.css'
import localFont from 'next/font/local'
import Head from 'next/head'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

// Локальный шрифт вместо next/font/google: раньше каждая сборка (docker compose
// up -d --build) скачивала Onest с fonts.googleapis.com/fonts.gstatic.com, и при
// недоступности этих хостов из контейнера сборка фронтенда падала (ETIMEDOUT).
// Файлы лежат в public/fonts/ — см. CLAUDE.md.
const onest = localFont({
  src: [
    { path: '../public/fonts/onest-300.ttf', weight: '300', style: 'normal' },
    { path: '../public/fonts/onest-400.ttf', weight: '400', style: 'normal' },
    { path: '../public/fonts/onest-500.ttf', weight: '500', style: 'normal' },
    { path: '../public/fonts/onest-600.ttf', weight: '600', style: 'normal' },
    { path: '../public/fonts/onest-700.ttf', weight: '700', style: 'normal' },
    { path: '../public/fonts/onest-800.ttf', weight: '800', style: 'normal' },
  ],
  display: 'swap',
})

export default function App({ Component, pageProps }) {
  const router = useRouter()
  // Освежаем права/роль из /auth/me при загрузке приложения: снимок в localStorage
  // делается при логине, и без этого изменения роли в настройках не подхватывались
  // до повторного входа (кнопки/инлайн-редактирование оставались по старым правам).
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
    if (!token) { setReady(true); return }
    axios.get('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => {
        const d = r.data || {}
        localStorage.setItem('role', d.role || '')
        localStorage.setItem('role_label', d.role_label || '')
        localStorage.setItem('is_admin', d.is_admin ? '1' : '0')
        localStorage.setItem('permissions', JSON.stringify(d.permissions || {}))
        if (d.name) localStorage.setItem('name', d.name)
      })
      .catch(e => { if (e.response?.status === 401) { localStorage.clear(); router.replace('/login') } })
      .finally(() => setReady(true))
  }, [])

  return (
    <>
      {/* Next по умолчанию инжектит только width=device-width (без initial-scale) —
          на телефоне это давало зум-аут (мелкий рендер) при малейшем переполнении
          по ширине. Явный initial-scale=1 фиксирует масштаб 1:1. Действует на все страницы. */}
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <main className={onest.className}>
        {ready ? <Component {...pageProps} /> : null}
      </main>
    </>
  )
}
