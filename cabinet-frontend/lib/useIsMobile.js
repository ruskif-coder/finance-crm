/**
 * Узкий экран — мобильная раскладка кабинета (хендофф «моб версия кп», брейкпоинт < 1024).
 *
 * Первый кадр — всегда десктоп: на сервере ширины нет, и угадывать её значит получить
 * расхождение с клиентом и ошибку гидрации. Кабинет до входа всё равно ничего не рисует,
 * так что подмена раскладки после монтирования не мигает.
 */
import { useEffect, useState } from 'react'

export const MOBILE_QUERY = '(max-width: 1023px)'

export default function useIsMobile() {
  const [mobile, setMobile] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const on = () => setMobile(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return mobile
}
