// Единственный источник правды по структуре приложения. До этого карта была размазана
// по семи спискам (NAV_ITEMS, SECTION_TITLE, SECTION_SUBNAV, LANDING_ORDER,
// DIRECTORY_ORDER, SALES, SECTIONS) — их приходилось править синхронно, и рассинхрон
// не проявлялся до момента, когда пользователь упирался в пустоту.
import data from './nav.data.json'
import { can } from './auth'
import { resolveLegacy as _resolve, compileRules } from './legacy.mjs'

export const NAV = data.sections

// can() из lib/auth.js сам пропускает админа (читает роль из localStorage), поэтому
// admin-bypass здесь НЕ повторяется: второй источник признака админа рано или поздно
// разошёлся бы с первым. Параметр isAdmin нужен только пунктам adminOnly — у них нет
// ключа права, и решать может только роль.
const itemAllowed = (it, perms, isAdmin) =>
  it.adminOnly ? !!isAdmin : can(perms, it.perm, 'view')

export const allowedItems = (section, perms, isAdmin) =>
  section.items.filter(it => itemAllowed(it, perms, isAdmin))

// Раздел без единого доступного экрана не показывается вовсе.
export const allowedSections = (perms, isAdmin) =>
  NAV.filter(s => allowedItems(s, perms, isAdmin).length > 0)

// Точка входа в контур: первый доступный экран. Человек, которому закрыт дашборд
// продаж, попадает в реестр, а не в отказ.
export const entryHref = (sectionKey, perms, isAdmin) => {
  const s = NAV.find(x => x.key === sectionKey)
  if (!s) return null
  const items = allowedItems(s, perms, isAdmin)
  return items.length ? items[0].href : null
}

// ОСТОРОЖНО: одноимённая функция есть в components/Navbar.js, и второй аргумент у неё
// другой — строка роли, а не булево. Обёртка существует ради страниц, написанных до
// появления этого модуля. Копируя вызов из соседнего файла, смотри, откуда импорт.
//
// Фолбэк — /login, а не /dashboard, как было раньше. Пользователь без единого права
// на дашборде видел отказ, а редирект внутри самой страницы мог зациклиться на неё же.
// Отправлять его на вход честнее: значит, роль настроена не до конца.
export const firstAllowedHref = (perms, isAdmin) => {
  for (const s of NAV) {
    const items = allowedItems(s, perms, isAdmin)
    if (items.length) return items[0].href
  }
  return '/login'
}

export const firstDirectoryHref = (perms, isAdmin) =>
  entryHref('directory', perms, isAdmin) || '/login'

// Активный экран по текущему маршруту. Совпадение по префиксу, чтобы вложенные
// страницы (карточка сделки, конструктор МП) подсвечивали свой раздел.
export const findByPath = (pathname) => {
  let best = null
  for (const s of NAV)
    for (const it of s.items)
      if (pathname === it.href || pathname.startsWith(it.href + '/'))
        if (!best || it.href.length > best.item.href.length) best = { section: s, item: it }
  return best
}

// ВНИМАНИЕ: next.config.js читает nav.data.json напрямую и повторяет это преобразование
// у себя. Иначе никак: конфиг — CommonJS, а этот модуль ESM и тянет ./auth. Функция
// оставлена для кода приложения; правя формат редиректов, правь оба места.
export const legacyRedirects = () =>
  data.redirects.map(r => ({ source: r.from, destination: r.to, permanent: false }))

// Клиентский двойник серверных редиректов. Нужен там, где адрес приходит из базы
// (notifications.link): колокольчик делает router.push(), а на клиентский переход
// redirects из next.config.js не распространяются — они работают только на запрос
// к серверу. Правила берутся из того же nav.data.json, так что расхождения быть не может.
//
// Разбор правил вынесен в lib/legacy.mjs — модуль без зависимостей, который импортирует
// и этот файл, и scripts/check-nav.mjs. Здесь остаётся только подстановка data.redirects,
// чтобы наружу сигнатура resolveLegacy(href) не менялась.
const RULES = compileRules(data.redirects)

export const resolveLegacy = (href) => _resolve(href, RULES)
