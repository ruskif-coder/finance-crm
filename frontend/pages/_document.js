import { Html, Head, Main, NextScript } from 'next/document'
import { DEFAULT_THEME, THEME_KEY, THEME_ON } from '../lib/theme'

// Тема ставится ДО первой отрисовки (22.10.2026): из useEffect в _app она приходила после кадра,
// и тёмная тема начиналась с белой вспышки.
const setTheme = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});document.documentElement.setAttribute('data-theme',t||${JSON.stringify(DEFAULT_THEME)})}catch(e){}`

export default function Document() {
  return (
    <Html lang="ru">
      <Head />
      <body>
        {THEME_ON && <script dangerouslySetInnerHTML={{ __html: setTheme }} />}
        <Main />
        <NextScript />
      </body>
    </Html>
  )
}
