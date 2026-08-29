import Head from 'next/head'
import { useEffect } from 'react'
import '../styles/globals.css'

/**
 * Тема выбирается один раз при монтировании и живёт в `localStorage`.
 *
 * Читается ТОЛЬКО после монтирования: на сервере `localStorage` не существует, а
 * `prefers-color-scheme` там неизвестен — попытка угадать тему при рендере даёт
 * расхождение с клиентом и ошибку гидрации. Ценой этого экран на первый кадр светлый;
 * это лучше, чем мигание всей страницы после гидрации.
 */
export default function App({ Component, pageProps }) {
  useEffect(() => {
    try {
      const saved = localStorage.getItem('cabinet_theme')
      const dark = saved ? saved === 'dark'
        : window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    } catch { /* приватный режим — остаёмся на светлой */ }
  }, [])

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <Component {...pageProps} />
    </>
  )
}
