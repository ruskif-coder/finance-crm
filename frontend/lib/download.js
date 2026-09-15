import api, { auth } from './http'

// ── Скачивание файла: ОДНА точка на все экраны ───────────────────────────────
//
// Раньше каждый экран сам создавал <a download>, сам разбирал Content-Disposition и
// сам придумывал запасное имя. Копий набралось семь, и половина подставляла заглушку
// ПОВЕРХ правильного имени, которое прислал сервер: документ договора площадки уезжал
// на диск как «contract» — без расширения, то есть файл, который не открыть двойным
// щелчком.
//
// Правило имени одно и живёт здесь: явно переданное → имя от сервера → 'file'.

// Имя файла из Content-Disposition. Сначала `filename*` (UTF-8, кириллица), потом
// обычный `filename` — так его и отдаёт бэкенд (см. annexes.py, publishers.py).
export function filenameFromResponse(r) {
  const cd = r?.headers?.['content-disposition'] || ''
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (star) { try { return decodeURIComponent(star[1]) } catch (e) { /* битая кодировка */ } }
  const plain = /filename="?([^";]+)"?/i.exec(cd)
  return plain ? plain[1] : ''
}

// Сохранить уже полученный blob под именем. Ссылку на объект обязательно освобождаем:
// без revokeObjectURL blob висит в памяти вкладки до перезагрузки страницы.
export function saveBlob(blob, name) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name || 'file'
  document.body.appendChild(a)     // часть браузеров не кликает по элементу вне дерева
  a.click()
  a.remove()
  URL.revokeObjectURL(href)
}

// Сохранить ответ axios (responseType:'blob'): имя берём у сервера, если своего нет.
export function saveResponse(r, name) {
  saveBlob(r.data, name || filenameFromResponse(r))
}

// Скачать по адресу. Возвращает true/false — вызывающий снимает свой индикатор.
// onError позволяет экрану показать отказ по-своему (плашка вместо alert).
export async function downloadFile(url, name, onError) {
  try {
    const r = await api.get(url, { ...auth(), responseType: 'blob' })
    saveResponse(r, name)
    return true
  } catch (e) {
    // Отказ приходит блобом, а не JSON, потому что запрос просил blob. Без чтения тела
    // на экране оказывается общее «не удалось», хотя сервер прислал, ЧЕГО не хватает —
    // так выгрузка ДС молчала бы о незаполненных реквизитах подписанта.
    let msg = 'Не удалось скачать файл'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch (_) { /* тело не JSON */ }
    if (onError) onError(msg); else alert(msg)
    return false
  }
}
