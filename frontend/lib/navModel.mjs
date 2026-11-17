// Правила строки меню v3 (хендофф design_handoff_nav_mix, 17.11.2026) — без React, чтобы проверялись `node --test`.
// Закреплённые и недавние — АДРЕСА экранов: так их хранит сервер (`user_nav_prefs`), а экран по адресу находит карта.
export const MAX_PINS = 3
export const RECENT_LIMIT = 12

/** Контуры строки и «Справочники» отдельно. Плоского меню для роли с одним контуром нет (владелец 17.11.2026):
 *  строка у всех одинаковая — контур пиктограммой и названием, экраны в панели. */
export const layoutOf = (sections) => ({
  mains: sections.filter(s => s.key !== 'directory'),
  directory: sections.find(s => s.key === 'directory') || null,
})

/** Третий уровень пилюли — код открытого объекта: первый сегмент адреса сразу за адресом экрана. */
export const objectOf = (path, item) => {
  if (!item) return ''
  const clean = String(path || '').split(/[?#]/)[0]
  if (!clean.startsWith(item.href + '/')) return ''
  const seg = clean.slice(item.href.length + 1).split('/')[0]
  try { return decodeURIComponent(seg) } catch { return seg }
}

/** README §2: до семи экранов — одна колонка, больше — две. */
export const panelCols = (n) => (n > 7 ? 2 : 1)

/** Звезда: повторный клик снимает; четвёртая не встаёт (README §3) — чужой закреп не вытесняется. */
export const togglePin = (pins, href) => {
  if (pins.includes(href)) return pins.filter(p => p !== href)
  return pins.length >= MAX_PINS ? pins : [...pins, href]
}

export const pushRecent = (recent, href) => [href, ...recent.filter(r => r !== href)].slice(0, RECENT_LIMIT)

/** Подвал панели: два последних экрана ЭТОГО раздела, кроме текущего. */
export const recentFor = (recent, section, currentHref) => recent
  .filter(h => h !== currentHref)
  .map(h => section.items.find(i => i.href === h))
  .filter(Boolean)
  .slice(0, 2)

/** Закреплённые справа: только то, что роли доступно сейчас — закреп экрана, право на который сняли, не ведёт в отказ. */
export const pinsShown = (pins, mains) => pins.flatMap(href => {
  const section = mains.find(s => s.items.some(i => i.href === href))
  if (!section) return []
  return [{ href, section, item: section.items.find(i => i.href === href) }]
})

export const sumBadge = (section) => section.items.reduce((a, i) => a + (parseInt(i.badge, 10) || 0), 0)
