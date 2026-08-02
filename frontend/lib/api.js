import axios from 'axios'

// Единый HTTP-клиент раздела продаж. paramsSerializer:{indexes:null} обязателен:
// FastAPI для List[...] ждёт повторяющийся ключ без скобок (`?a=1&a=2`), а дефолт
// axios шлёт `a[]=1&a[]=2`, которые бэкенд молча игнорирует — фильтры не срабатывают.
const api = axios.create({ baseURL: '/api', paramsSerializer: { indexes: null } })

export const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

// Протухшая/невалидная сессия: любой 401 → чистим токен и уводим на логин.
// 403 (нет прав) НЕ трогаем — пользователь залогинен, просто нет доступа к ресурсу.
// Иначе при простое токен истекает, запросы молча возвращают 401, страница
// остаётся открытой без данных и без редиректа.
api.interceptors.response.use(
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

export default api
