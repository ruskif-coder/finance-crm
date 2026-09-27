// Глобальный поиск — клиентский слой. Спецификация: docs/SPEC_глобальный_поиск.md.
//
// Нагрузка приходит из клавиатуры, а не из базы, поэтому здесь три заслона:
// задержка после последней клавиши, отмена незавершённого запроса и кеш ответов
// на время жизни вкладки.
//
// Запрос в адрес НЕ кладём (ИНН и названия юрлиц осели бы в журналах Caddy): строка
// уходит в теле POST, а на страницу результатов переезжает через sessionStorage.
import api, { auth } from './http'

export const SEARCH_DELAY_MS = 300
export const SEARCH_MIN = 2
export const SEARCH_MAX = 100
export const SEARCH_HINT = 'Сделка, контрагент, ИНН, договор, площадка…'
// Та же подсказка внутри фразы «Ищется: …» — строчная только первая буква: ИНН остаётся ИНН.
export const SEARCH_HINT_TEXT = `Ищется: ${SEARCH_HINT[0].toLowerCase()}${SEARCH_HINT.slice(1)}`

export const TYPE_LABELS = {
  deal: 'Сделки',
  counterparty: 'Контрагенты',
  contract: 'Договоры',
  publisher: 'Площадки',
  advertiser: 'Рекламодатели',
  agency: 'Агентства',
  brand: 'Бренды',
  media_plan: 'Медиапланы',
  ord_contract: 'ОРД: изначальные договоры',
  erid: 'ОРД: ЕРИД',
}

const KEY = 'search_q'
const cache = new Map()
const CACHE_MAX = 100

/** Строка годится для запроса: обрезана и не короче минимума. */
export const searchable = (q) => {
  const s = (q || '').trim()
  return s.length >= SEARCH_MIN && s.length <= SEARCH_MAX ? s : ''
}

// Кеш и перенесённый запрос привязаны к СЕССИИ. Выход и вход — клиентские переходы, модуль
// не перезагружается: без привязки следующий человек на той же вкладке получил бы из кеша
// выдачу предыдущего — чужие сделки и ИНН (ревью 27.09.2026). Метка — хвост токена: новый
// вход даёт новый токен, а сам токен ни в ключ, ни в sessionStorage целиком не кладём.
function sessionTag() {
  try { return (localStorage.getItem('token') || '').slice(-16) } catch { return '' }
}

/** POST /api/search с кешем. `signal` — от AbortController вызывающего. */
export async function searchApi(q, { types, perType = 5, offset = 0, signal } = {}) {
  const body = { q, per_type: perType, offset, ...(types ? { types } : {}) }
  const key = sessionTag() + JSON.stringify(body)
  if (cache.has(key)) return cache.get(key)
  const r = await api.post('/search', body, { ...auth(), signal })
  if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value)
  cache.set(key, r.data)
  return r.data
}

/** Текст ошибки для человека: 429 и 400 приходят с объяснением от сервера. */
export const searchError = (e) => e?.response?.data?.detail || 'Поиск не ответил — попробуйте ещё раз'

export const isAbort = (e) => e?.name === 'CanceledError' || e?.name === 'AbortError'

// sessionStorage может бросить (приватный режим, запрет хранилища) — поиск от этого
// не должен падать, теряется только перенос запроса на страницу результатов.
export function saveQuery(q) {
  try { sessionStorage.setItem(KEY, JSON.stringify({ q, s: sessionTag() })) } catch { /* без переноса запроса */ }
}

/** Запрос, оставленный ЭТОЙ сессией; чужой (после смены пользователя) — пустая строка. */
export function readQuery() {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    return v && v.s === sessionTag() && typeof v.q === 'string' ? v.q : ''
  } catch { return '' }
}

/** Ссылка строки выдачи — только внутренний путь приложения. Сервер строит их сам,
 *  но `<a href>` из данных держим на том же правиле, что и safeHref: чужая схема
 *  (`javascript:`, `//хост`) ссылкой не становится. Управляющие символы и обратная косая
 *  тоже: браузер вырезает табуляцию, и «/\t/хост» превратился бы в «//хост». */
export const internalHref = (h) => (typeof h === 'string' && /^\/(?!\/)/.test(h)
  && !/[\u0000-\u001f\u007f\\]/.test(h) ? h : '/search')
