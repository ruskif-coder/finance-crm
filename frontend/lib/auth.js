// Единый источник проверки прав на фронтенде.
//
// Раньше getPermissions + can дублировались в 5-6 файлах, причём локальные копии
// can (в balance/import/settings) НЕ имели admin-bypass — админ на этих страницах
// зависел от устаревшего снимка permissions в localStorage и мог не увидеть новую
// секцию. Здесь единая версия с bypass, как на бэкенде.
//
// permissions — снимок с момента логина (localStorage). Меняется только при
// перелогине: если админ изменил роль/права, пользователь увидит это после logout.

export function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

// Админ имеет полный доступ (как на бэкенде). Роль берём из localStorage, чтобы
// не зависеть от устаревшего снимка permissions после добавления секций.
export const can = (perms, section, action = 'view') => {
  if (typeof window !== 'undefined' && localStorage.getItem('role') === 'admin') return true
  return !!(perms && perms[section] && perms[section][action])
}
