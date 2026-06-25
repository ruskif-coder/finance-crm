import '../styles/globals.css'
import { Onest } from 'next/font/google'

const onest = Onest({
  subsets: ['latin', 'cyrillic'],
  weight: ['300', '400', '500', '600', '700', '800'],
  display: 'swap',
})

export default function App({ Component, pageProps }) {
  return (
    <main className={onest.className}>
      <Component {...pageProps} />
    </main>
  )
}
