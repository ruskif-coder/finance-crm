// Форматы ссылки в приложении — одним списком для подсказки (владелец 06.10.2026).
export const APP_LINK_FORMATS = [
  ['своя схема приложения', 'storefront://product_selection/4846, ozerki://catalog/1'],
  ['диплинк SDK', 'deeplink+://navigate?primaryUrl=<веб-ссылка в base64>&primaryTrackingUrl={LINK_ESC}'],
  ['веб-ссылка', 'https://… — та же, что в первом поле, если отдельной ссылки в приложении нет'],
]
