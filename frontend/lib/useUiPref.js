// Личная настройка вида — у пользователя на сервере (`/api/ui-prefs/<ключ>`, 19.11.2026), а не в браузере: едет за
// человеком на любой компьютер. Прочитанное держится в памяти вкладки — запрос один раз на ключ, а не на каждый расхлоп.
// Запись — сразу при изменении; не сохранилось — в этой вкладке настройка всё равно действует.
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'

const cache = {}       // ключ → значение (null — не настраивал)
const waiting = {}     // ключ → общий запрос, пока он в пути

export default function useUiPref(key) {
  const [value, setValue] = useState(() => (key in cache ? cache[key] : null))
  useEffect(() => {
    if (key in cache) return undefined
    let alive = true
    waiting[key] = waiting[key] || api.get(`/ui-prefs/${key}`, auth())
      .then(r => { cache[key] = r.data.value ?? null; return cache[key] })
      .catch(() => null)
      .finally(() => { delete waiting[key] })
    waiting[key].then(v => { if (alive) setValue(v) })
    return () => { alive = false }
  }, [key])
  const save = useCallback((v) => {
    cache[key] = v
    setValue(v)
    api.put(`/ui-prefs/${key}`, { value: v }, auth()).catch(() => { /* не сохранилось — действует в этой вкладке */ })
  }, [key])
  return [value, save]
}
