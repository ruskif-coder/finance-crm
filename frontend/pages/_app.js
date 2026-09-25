import '../styles/globals.css'
import localFont from 'next/font/local'
import Head from 'next/head'
import { useEffect, useState, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { PageLoader } from '../components/LogoLoader'

// Локальный шрифт вместо next/font/google: раньше каждая сборка (docker compose
// up -d --build) скачивала Onest с fonts.googleapis.com/fonts.gstatic.com, и при
// недоступности этих хостов из контейнера сборка фронтенда падала (ETIMEDOUT).
// Файлы лежат в public/fonts/ — см. CLAUDE.md.
//
// Формат woff2, а не ttf (13.09.2026). Все шесть начертаний ПРЕДЗАГРУЖАЮТСЯ на каждой
// странице — этот класс висит на <main>, — и в ttf они весили 354 КБ. На экране входа
// это было 48 % всей страницы: форма из двух полей тянула шрифта больше, чем React.
// woff2 — тот же шрифт под сжатием brotli: 149 КБ, глифы и таблица символов совпадают
// один в один (509 глифов, 470 символов). Исходные .ttf оставлены в public/fonts/ —
// из них конвертируются новые начертания, если понадобятся.
const onest = localFont({
  src: [
    { path: '../public/fonts/onest-300.woff2', weight: '300', style: 'normal' },
    { path: '../public/fonts/onest-400.woff2', weight: '400', style: 'normal' },
    { path: '../public/fonts/onest-500.woff2', weight: '500', style: 'normal' },
    { path: '../public/fonts/onest-600.woff2', weight: '600', style: 'normal' },
    { path: '../public/fonts/onest-700.woff2', weight: '700', style: 'normal' },
    { path: '../public/fonts/onest-800.woff2', weight: '800', style: 'normal' },
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
        // Согласие не принято (токен выдан, а форму закрыли) — сервер данных не отдаст;
        // ведём на вход, там форма согласия (аудит 23.09.2026, 9.7).
        if (d.consent_required) { localStorage.clear(); router.replace('/login') }
      })
      .catch(e => { if (e.response?.status === 401) { localStorage.clear(); router.replace('/login') } })
      .finally(() => setReady(true))
  }, [])

  // Загрузчик 1a «Волна» на переходах между страницами (с дебаунсом ~180мс, чтобы
  // не мигал на мгновенной клиентской навигации). Начальная загрузка — через `ready`.
  const [nav, setNav] = useState(false)
  const navTimer = useRef(null)
  useEffect(() => {
    const start = () => { navTimer.current = setTimeout(() => setNav(true), 180) }
    const stop = () => { clearTimeout(navTimer.current); setNav(false) }
    router.events.on('routeChangeStart', start)
    router.events.on('routeChangeComplete', stop)
    router.events.on('routeChangeError', stop)
    return () => {
      clearTimeout(navTimer.current)
      router.events.off('routeChangeStart', start)
      router.events.off('routeChangeComplete', stop)
      router.events.off('routeChangeError', stop)
    }
  }, [router])

  return (
    <>
      {/* Next по умолчанию инжектит только width=device-width (без initial-scale) —
          на телефоне это давало зум-аут (мелкий рендер) при малейшем переполнении
          по ширине. Явный initial-scale=1 фиксирует масштаб 1:1. Действует на все страницы. */}
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        {/* Заголовок по умолчанию. Страница со своим <title> его перекрывает: next/head
            из нескольких тегов title оставляет ПОСЛЕДНИЙ, а Head страницы рендерится
            после этого. Нужен точкам входа контуров (/finance, /sales, …) — они живут
            доли секунды и перебрасывают дальше, но без него вкладка показывает голый
            адрес. Заодно страховка: новая страница, где забыли <title>, покажет бренд. */}
        <title>SIMB-AD ERP</title>
      </Head>
      <main className={onest.className}>
        {(!ready || nav) && <PageLoader />}
        {ready ? <Component {...pageProps} /> : null}
      </main>
    </>
  )
}
