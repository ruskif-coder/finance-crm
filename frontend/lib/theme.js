// Тёмная тема (владелец 22.10.2026: «дай кнопку переключения, пройдусь глазами»). Тема — атрибут
// data-theme на <html>; цвета переопределяет блок [data-theme="dark"] в styles/globals.css. Выбор
// хранится у пользователя (users.theme, PUT /api/auth/me/theme), в браузере — копия для первого кадра;
// по умолчанию — светлая (системную настройку не подхватываем).
// Приём тот же, что в кабинете паблишера (cabinet-frontend/pages/_app.js).
export const THEME_KEY = 'theme'
// Пять тем хендоффа docs/темки.zip (tokens-5themes.css); образец — цвет фона темы.
export const THEMES = [
  { key: 'light', label: 'День', swatch: '#EBEEF6' },
  { key: 'dark', label: 'Ночь', swatch: '#10141C' },
  { key: 'graphite', label: 'Графит', swatch: '#121314' },
  { key: 'pink', label: 'Розовая', swatch: '#F7ECF1' },
  { key: 'japandi', label: 'Джапанди', swatch: '#EEE7DA' },
]
// Переключатель для всех (владелец 22.10.2026: «выложи переключатель тем»); до того был только в next dev.
// Флаг оставлен, чтобы тему можно было снова спрятать одной строкой.
export const THEME_ON = true

export function readTheme() {
  if (!THEME_ON) return 'light'
  try { const t = localStorage.getItem(THEME_KEY); return THEMES.some(x => x.key === t) ? t : 'light' } catch { return 'light' }
}

export function applyTheme(theme) {
  if (!THEME_ON) return
  document.documentElement.setAttribute('data-theme', theme)
  try { localStorage.setItem(THEME_KEY, theme) } catch { /* приватный режим — тема до перезагрузки */ }
}
