import axios from 'axios'

// Единый HTTP-слой всего фронтенда (финмодуль + продажи).
//
// Раньше каждая страница создавала свой axios.create({ baseURL:'/api' }) — 16 копий,
// и только раздел продаж (lib/api.js) имел перехватчик 401. Из-за этого на страницах
// финмодуля протухший токен приводил к молчаливым пустым экранам без редиректа.
//
// Относительный baseURL '/api' — запрос идёт через Caddy на тот же origin, что и
// страница (см. Caddyfile), поэтому работает и на localhost, и под реальным доменом
// без CORS и без переключения конфигурации.
//
// paramsSerializer:{indexes:null} обязателен: FastAPI для List[...] ждёт повторяющийся
// ключ без скобок (`?a=1&a=2`); дефолт axios шлёт `a[]=1&a[]=2`, которые бэкенд молча
// игнорирует — фильтры не срабатывают.

// 401 (протухшая/невалидная сессия) → чистим токен и уводим на логин.
// 403 (нет прав) НЕ трогаем — пользователь залогинен, просто нет доступа к ресурсу.
function attach401(instance) {
  instance.interceptors.response.use(
    (r) => r,
    (err) => {
      if (typeof window !== 'undefined' && err.response?.status === 401) {
        const path = window.location.pathname
        if (path !== '/login' && !path.startsWith('/login')) {
          try { localStorage.removeItem('token') } catch (e) {}
          window.location.replace('/login')
        }
      }
      return Promise.reject(err)
    }
  )
  return instance
}

// Фабрика для страниц финмодуля: токен вшивается в инстанс при создании.
// Заменяет локальное `const api = (token) => axios.create({...})`.
export const makeApi = (token) => attach401(axios.create({
  baseURL: '/api',
  headers: token ? { Authorization: `Bearer ${token}` } : {},
  paramsSerializer: { indexes: null },
}))

// Синглтон для раздела продаж: токен читается на каждый запрос через auth().
const api = attach401(axios.create({ baseURL: '/api', paramsSerializer: { indexes: null } }))

export const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

export default api
