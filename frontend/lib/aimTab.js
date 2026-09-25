/* Вкладка нацеливания — одна на две кнопки «нацелить на себя»: конвейер трафиков и блок
   креатива в карточке сделки. До 25.09.2026 у каждой была своя копия, и разошлись они
   ровно так, как расходятся копии: одна писала в вкладку «готовим…», другая оставляла её
   пустой; обе при отказе вкладку ЗАКРЫВАЛИ — человек видел «открылась и сразу пропала»,
   а причина лежала полосой на странице, куда он уже не смотрит.

   Открывается СИНХРОННО по клику, адрес подставляется после ответа: окно из `await`
   блокировщик всплывающих окон считает непрошеным и режет. */

const WAIT = 'Готовим нацеливание: копируем баннер в DSP и выпускаем ссылку…'

export function openAimTab() {
  // Вкладка не держит ссылку на нашу (аудит 23.09.2026, 7.L1): туда уходит страница DSP,
  // и через `opener` она могла бы увести наш экран на подделку.
  const tab = window.open('', '_blank')
  if (tab) tab.opener = null
  if (!tab) return null
  try {
    tab.document.write('<title>Нацеливание…</title>'
      + '<body style="margin:0;display:flex;align-items:center;justify-content:center;'
      + 'height:100vh;font:15px/1.5 system-ui,sans-serif;color:#5b6474"></body>')
    tab.document.close()
    tab.document.body.textContent = WAIT
  } catch (e) { /* другое происхождение — останется пустой, это не страшно */ }
  return tab
}

/** Ссылка выпущена — ведём вкладку туда (или текущую, если вкладку не дали открыть). */
export function aimTabGo(tab, url) {
  if (tab) tab.location = url
  else window.location.href = url
}

/** Отказ — причина В ТОЙ ЖЕ вкладке. Текст пришёл с сервера, поэтому textContent. */
export function aimTabFail(tab, why) {
  if (!tab) return
  try {
    tab.document.title = 'Нацеливание не выпущено'
    const box = tab.document.body
    box.style.color = '#9A1C1C'
    box.style.padding = '0 24px'
    box.style.textAlign = 'center'
    box.textContent = 'Нацеливание не выпущено: ' + why
  } catch (e) { tab.close() }
}

/* Цвет кнопки по ответу сервера (владелец 25.09.2026): зелёная — креатив и кампания
   ПЕРЕЧИТАНЫ запущенными, то есть кука покажет баннер; жёлтая — ссылка выпущена, но
   крутиться нечему. До нажатия — обычная: состояние не хранится, его знает только DSP. */
export function aimTone(active) {
  if (active === true) {
    return { color: 'var(--income-fg)', borderColor: 'var(--income-border)',
             background: 'var(--income-tint)' }
  }
  if (active === false) {
    return { color: 'var(--warning-fg)', borderColor: 'var(--warning-border)',
             background: 'var(--warning-tint)' }
  }
  return {}
}

/** Что сказать, если ссылка выпущена, а баннер крутиться не будет. Пусто — всё в порядке. */
export function aimNotLive(data) {
  return data && data.active === false
    ? `Ссылка выпущена, но баннер на сайте не появится: ${data.reason || 'креатив в DSP не запущен'}`
    : ''
}
