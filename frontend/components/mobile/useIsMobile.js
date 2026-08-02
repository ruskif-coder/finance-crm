import { useState, useEffect } from 'react'

// Единый брейкпоинт мобильного слоя (совпадает с .desktop-only/.mobile-only и
// мобильным Navbar). SSR-безопасно: на сервере и до монтирования — false,
// затем синхронизируется с matchMedia и реагирует на ресайз/поворот.
export default function useIsMobile(query = '(max-width: 1023px)') {
  const [isMobile, setIsMobile] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mql = window.matchMedia(query)
    const apply = () => setIsMobile(mql.matches)
    apply()
    if (mql.addEventListener) mql.addEventListener('change', apply)
    else mql.addListener(apply)
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', apply)
      else mql.removeListener(apply)
    }
  }, [query])
  return isMobile
}
