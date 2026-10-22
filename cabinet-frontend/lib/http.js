/**
 * Ось связи с бэкендом кабинета. Относительный `/api` — как в финмодуле: абсолютный
 * адрес ломает приложение в тот день, когда оно переезжает с localhost на домен.
 *
 * Токен живёт в localStorage под СВОИМ ключом. Совпадение с ключом финмодуля было бы
 * не экономией, а способом однажды подставить один токен вместо другого: контуры
 * разные, ключи подписи разные, хранилища тоже разные.
 */
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const TOKEN_KEY = 'cabinet_token'

export function auth() {
  const t = typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY)
  return { headers: t ? { Authorization: `Bearer ${t}` } : {} }
}

export function signOut() {
  // Сначала отзываем входы на сервере (аудит 2.6.76, п. 1.6), потом стираем токен здесь. Не дожидаемся ответа: выход
  // не должен зависеть от сети, а сервер без ответа отзовёт входы при следующем «Выйти» или отключении учётки.
  try { api.post('/logout', {}, auth()).catch(() => {}) } catch { /* без сети — только локальный выход */ }
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem('cabinet_name')
  } catch { /* приватный режим — просто нечего чистить */ }
}

export default api
