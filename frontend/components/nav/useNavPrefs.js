// Закреплённые и недавние экраны — у пользователя на сервере (`/api/nav-prefs`, владелец 17.11.2026), а не в браузере:
// закреп едет за человеком на любой компьютер. Запись — одним PUT обоих списков.
//
// Шапка у каждой страницы своя и монтируется заново на каждом переходе, поэтому:
//  · прочитанное держится в памяти вкладки (`cache`) — запрос на сервер один раз за вкладку, а не на каждый экран;
//  · недавние пишутся НЕ во время работы на экране, а при уходе с него: переход внутри приложения — PUT, закрытие
//    вкладки — `fetch` с `keepalive` (браузер доставит и после закрытия). Запись во время загрузки сдвигала «тишину в
//    сети», и тяжёлые экраны («Операции») открывались на ~0,9 с дольше (обход 17.11.2026);
//  · закреп звездой — действие человека — пишется сразу.
import { useCallback, useEffect, useRef, useState } from 'react'
import api, { auth } from '@/lib/http'
import { pushRecent, togglePin } from '@/lib/navModel.mjs'

let cache = null            // { pinned, recent } — общее для всех шапок этой вкладки
let cacheFor = null         // чей это кэш: токен входа. Выход и вход другим в той же вкладке — кэш не годится
const token = () => (typeof window === 'undefined' ? null : localStorage.getItem('token'))
const cached = () => (cache && cacheFor && cacheFor === token() ? cache : null)

const body = (prefs) => ({ pinned: prefs.pinned, recent: prefs.recent })
const send = (prefs) => api.put('/nav-prefs', body(prefs), auth())
  .catch(() => { /* не сохранилось — в этой вкладке закреп всё равно виден */ })
// Закрытие вкладки: обычный запрос браузер обрывает, `keepalive` — доставляет.
const sendOnClose = (prefs) => {
  try {
    fetch('/api/nav-prefs', { method: 'PUT', keepalive: true, body: JSON.stringify(body(prefs)),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` } })
  } catch { /* вкладка закрывается — сделать больше нечего */ }
}

export default function useNavPrefs(currentHref) {
  const [prefs, setPrefs] = useState(() => (cached() ? { ...cached(), loaded: true } : { pinned: [], recent: [], loaded: false }))
  const latest = useRef(prefs)
  const pending = useRef(null)
  latest.current = prefs

  useEffect(() => {
    if (cached() || !token()) return undefined
    let alive = true
    const who = token()
    api.get('/nav-prefs', auth())
      .then(r => {
        cache = { pinned: r.data.pinned || [], recent: r.data.recent || [] }
        cacheFor = who
        if (alive) setPrefs({ ...cache, loaded: true })
      })
      // Не загрузилось — меню работает без закрепов, но и НЕ пишет: иначе пустые списки этой страницы затёрли бы
      // настоящие закреплённые на сервере (сбой одного запроса стирал закреп «ДДС», обход 17.11.2026).
      .catch(() => {})
    return () => { alive = false }
  }, [])

  // now — сразу (закреп); иначе — запомнить и отправить при уходе с экрана
  const save = useCallback((next, now) => {
    if (!cached()) return            // писать можно только поверх прочитанного с сервера
    cache = { pinned: next.pinned, recent: next.recent }
    cacheFor = token()
    if (now) { pending.current = null; send(cache); return }
    pending.current = cache
  }, [])
  useEffect(() => {
    const onHide = () => { if (pending.current) { sendOnClose(pending.current); pending.current = null } }
    window.addEventListener('pagehide', onHide)
    return () => {
      window.removeEventListener('pagehide', onHide)
      if (pending.current) { send(pending.current); pending.current = null }   // переход внутри приложения
    }
  }, [])

  // Каждый переход кладёт экран в начало недавних — только после загрузки, иначе затёрли бы сохранённый список.
  useEffect(() => {
    if (!prefs.loaded || !currentHref || latest.current.recent[0] === currentHref) return
    const next = { ...latest.current, recent: pushRecent(latest.current.recent, currentHref) }
    setPrefs(next)
    save(next, false)
  }, [currentHref, prefs.loaded, save])

  const pin = useCallback((href) => {
    const next = { ...latest.current, pinned: togglePin(latest.current.pinned, href) }
    if (next.pinned === latest.current.pinned) return false
    setPrefs(next)
    save(next, true)
    return true
  }, [save])

  return { pinned: prefs.pinned, recent: prefs.recent, pin }
}
