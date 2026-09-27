// Поиск с задержкой и отменой: пока человек печатает, запросы не уходят; новая буква
// отменяет незавершённый запрос. Ответ помечен строкой, для которой он пришёл, — чтобы
// Enter не открыл результат ПРЕДЫДУЩЕЙ строки, пока новая ещё в пути.
import { useEffect, useState } from 'react'
import { SEARCH_DELAY_MS, isAbort, searchApi, searchError, searchable } from '@/lib/search'

export default function useSearch(query, { perType = 5, enabled = true } = {}) {
  const [state, setState] = useState({ q: '', groups: [], loading: false, error: '' })
  const [attempt, setAttempt] = useState(0)   // «Повторить» после ошибки — тот же запрос заново

  useEffect(() => {
    const q = searchable(query)
    if (!enabled || !q) {
      setState({ q: '', groups: [], loading: false, error: '' })
      return undefined
    }
    const ctl = new AbortController()
    // Прежняя выдача на время запроса не текущая (q пустой): хендофф — «старая выдача во
    // время поиска не показывается», и повтор после ошибки не мигнёт «ничего не найдено».
    setState(s => ({ ...s, q: '', loading: true, error: '' }))
    const t = setTimeout(() => {
      searchApi(q, { perType, signal: ctl.signal })
        .then(d => setState({ q, groups: d.groups || [], loading: false, error: '' }))
        .catch(e => { if (!isAbort(e)) setState({ q, groups: [], loading: false, error: searchError(e) }) })
    }, SEARCH_DELAY_MS)
    return () => { clearTimeout(t); ctl.abort() }
  }, [query, perType, enabled, attempt])

  return { ...state, retry: () => setAttempt(n => n + 1) }
}
