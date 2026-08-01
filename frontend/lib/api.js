import axios from 'axios'

// Единый HTTP-клиент раздела продаж. paramsSerializer:{indexes:null} обязателен:
// FastAPI для List[...] ждёт повторяющийся ключ без скобок (`?a=1&a=2`), а дефолт
// axios шлёт `a[]=1&a[]=2`, которые бэкенд молча игнорирует — фильтры не срабатывают.
const api = axios.create({ baseURL: '/api', paramsSerializer: { indexes: null } })

export const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })

export default api
