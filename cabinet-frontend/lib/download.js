/**
 * Скачать файл кабинета. Вход кабинета — заголовок Authorization, а не cookie, поэтому
 * голая ссылка `<a href download>` уходит БЕЗ токена: сервер отвечает 401, а браузер
 * молча сохраняет этот ответ как файл — площадка получала JSON вместо баннера (прод
 * 25.09.2026). Отсюда запрос с токеном и сохранение полученного.
 *
 * Имя — из Content-Disposition (сначала `filename*` с кириллицей), иначе запасное.
 * Отказ сервера показывается текстом, а не сохраняется файлом.
 */
import api, { auth } from './http'

function nameOf(r, fallback) {
  const cd = r?.headers?.['content-disposition'] || ''
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (star) { try { return decodeURIComponent(star[1]) } catch { /* битая кодировка */ } }
  const plain = /filename="?([^";]+)"?/i.exec(cd)
  return plain ? plain[1] : fallback
}

/** Отдать браузеру готовый файл — общий шаг для скачанного с сервера и собранного на месте (выгрузка «Кампаний»). */
export function saveBlob(blob, name) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(href)
}

export async function downloadFile(url, fallback, onError) {
  try {
    const r = await api.get(url, { ...auth(), responseType: 'blob' })
    saveBlob(r.data, nameOf(r, fallback) || 'file')
    return true
  } catch (e) {
    let msg = 'Не удалось скачать файл'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* не JSON */ }
    if (onError) onError(msg); else alert(msg)
    return false
  }
}

/* Разаллокация согласованных сверок — один файл, площадка на своей вкладке (владелец 29.10.2026).
   Зовут кнопка месяца в «Кампаниях» и окно после согласия со сверкой. */
export const downloadRazaloc = (list, onError) =>
  downloadFile('/recons/razaloc?' + list.map(x => 'ids=' + encodeURIComponent(x.request_id)).join('&'), 'Разаллокация.xlsx', onError)
