// Тёмная тема (владелец 22.10.2026: «дай кнопку переключения, пройдусь глазами»). Тема — атрибут
// data-theme на <html>; цвета переопределяет блок [data-theme="dark"] в styles/globals.css. Выбор
// хранится у пользователя (users.theme, PUT /api/auth/me/theme), в браузере — копия для первого кадра;
// по умолчанию — светлая (системную настройку не подхватываем).
// Приём тот же, что в кабинете паблишера (cabinet-frontend/pages/_app.js).
import { useEffect, useState } from 'react'

export const THEME_KEY = 'theme'
// Пять тем хендоффа docs/темки.zip (tokens-5themes.css); образец — цвет фона темы.
export const THEMES = [
  { key: 'light', label: 'День', swatch: '#EBEEF6' },
  { key: 'dark', label: 'Ночь', swatch: '#10141C' },
  { key: 'graphite', label: 'Графит', swatch: '#121314' },
  { key: 'pink', label: 'Розовая', swatch: '#F7ECF1' },
  { key: 'japandi', label: 'Джапанди', swatch: '#EEE7DA' },
  // NAVY (хендофф docs/navy_theme.zip, 17.11.2026) — рядом с прежними, токены в styles/navy.css
  { key: 'navy', label: 'Navy день', swatch: '#D8E1EA' },
  { key: 'navy-dark', label: 'Navy ночь', swatch: '#2D3E50' },
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

/** Выбрать тему: сразу на странице и у пользователя на сервере (users.theme) — одна функция для меню профиля и переключателя
 *  «День / Ночь» дашборда трафика (NAVY, 17.11.2026). Не сохранилось на сервере — в этом браузере тема всё равно останется. */
/** Текущая тема страницы (атрибут data-theme на <html>) — состоянием React, с подпиской на смену из меню профиля. Для экранов,
 *  где тема меняет РАЗМЕТКУ, а не только цвета: «Мои сделки» в NAVY — блок «Сейчас» днём тёмный, ночью светлый (18.11.2026). */
export function useThemeKey() {
  const [theme, setTheme] = useState(null)
  useEffect(() => {
    const el = document.documentElement
    const read = () => setTheme(el.getAttribute('data-theme') || 'light')
    read()
    const mo = new MutationObserver(read)
    mo.observe(el, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return theme
}

/** Тон контрастного блока NAVY (главное на экране: «Сейчас», полоса стадий пакета, «Получится», нижняя строка действия):
 *  днём тёмный, ночью светлый; в прежних темах — без тона (вид прежний). Одно правило для всех экранов (18.11.2026). */
export const contrastTone = (theme) => (theme === 'navy' ? 'dark' : theme === 'navy-dark' ? 'light' : undefined)

export function saveTheme(theme) {
  applyTheme(theme)
  import('@/lib/http').then(({ default: api, auth }) => api.put('/auth/me/theme', { theme }, auth())).catch(() => {})
}
