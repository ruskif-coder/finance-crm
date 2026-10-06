/* Посадочная app-площадки бывает диплинком SDK (владелец 02.10.2026):
   `deeplink+://navigate?primaryUrl=<ссылка https в base64>&primaryTrackingUrl={LINK_ESC}`.
   Открыть его в браузере нельзя, поэтому кнопка «посадочная» ведёт на веб-адрес из
   primaryUrl. Ссылкой его делает всё равно safeHref — только http(s). */
export function landingWeb(u) {
  const m = /^deeplink\+:\/\/[^?]*\?(?:.*&)?primaryUrl=([^&]+)/i.exec(String(u || ''))
  if (!m) return u
  try {
    const b = decodeURIComponent(m[1]).replace(/-/g, '+').replace(/_/g, '/')
    return new TextDecoder().decode(Uint8Array.from(atob(b), (c) => c.charCodeAt(0)))
  } catch {
    return null
  }
}

export const isAppLink = (u) => /^deeplink\+:\/\//i.test(String(u || ''))

// Форматы ссылки в приложении — одним списком для подсказки (владелец 06.10.2026).
export const APP_LINK_FORMATS = [
  ['своя схема приложения', 'storefront://product_selection/4846, ozerki://catalog/1'],
  ['диплинк SDK', 'deeplink+://navigate?primaryUrl=<веб-ссылка в base64>&primaryTrackingUrl={LINK_ESC}'],
  ['веб-ссылка', 'https://… — та же, что в первом поле, если отдельной ссылки в приложении нет'],
]
