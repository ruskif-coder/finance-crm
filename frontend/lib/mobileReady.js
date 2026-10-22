// Экраны, у которых есть адаптация под телефон (владелец 16.10.2026). На остальных на узком экране
// поверх страницы встаёт заглушка «этот экран для устройств побольше» (`components/mobile/MobileStub`).
// Адрес — как `router.pathname` (с [id]), не фактический путь. Добавил мобильную вёрстку экрану —
// добавь его сюда.
export const MOBILE_READY = [
  '/',            // вход: сам перебрасывает на первый доступный экран
  '/login',
  '/accounts/mp/[id]',
  '/directory/advertisers',
  '/directory/agencies',
  '/directory/contracts',
  '/directory/counterparties',
  '/directory/counterparties/[id]',
  '/finance/balance',
  '/finance/cashflow',
  '/finance/operations',
  '/finance/plan-fact',
  '/finance/pnl',
  '/finance/receivables',
  '/finance/report',
  '/sales/dashboard',
  '/sales/deals',
  '/sales/deals/[id]',
  '/sales/year-plan',
]

// Печатные страницы (`…/pdf/[id]`) открывает сервис PDF узким окном — заглушка легла бы поверх документа и ушла в файл
// (найдено 21.10.2026 на ДС мастер-сделки). На них её не бывает никогда.
export const isPrintPage = (pathname) => /\/pdf\/\[id\]$/.test(pathname || '')

export const isMobileReady = (pathname) => MOBILE_READY.includes(pathname) || isPrintPage(pathname)
