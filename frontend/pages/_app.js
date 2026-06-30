import '../styles/globals.css'
import localFont from 'next/font/local'

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
  return (
    <main className={onest.className}>
      <Component {...pageProps} />
    </main>
  )
}
