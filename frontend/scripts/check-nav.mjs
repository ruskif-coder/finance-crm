// Проверка карты навигации. Запуск: node scripts/check-nav.mjs (из /app в контейнере).
// Ловит ошибки, которые иначе всплывают только у пользователя:
// дублирующийся адрес, адрес без файла страницы, редирект в никуда,
// сломанный разбор правила, цепочку редиректов.
import { readFileSync, existsSync, readdirSync } from 'fs'
import { resolveLegacy } from '../lib/legacy.mjs'

const nav = JSON.parse(readFileSync(new URL('../lib/nav.data.json', import.meta.url)))
const errors = []
const warnings = []

// Ожидания разбора правил. Таблицу пополнять при каждом новом правиле в карте:
// слева — адрес, который может прийти из закладки или из notifications.link,
// справа — куда он обязан приехать (null = адрес не должен меняться).
const RESOLVE_CASES = [
  ['/deals/mp/12',        '/accounts/mp/12'],
  ['/deals/mp',           '/accounts/mp'],
  ['/deals/mp/pdf/7',     '/accounts/mp/pdf/7'],
  ['/operations',         '/finance/operations'],
  ['/dashboard',          '/finance/cashflow'],
  ['/counterparty/5',     '/directory/counterparties/5'],
  ['/counterparty/5?tab=x', '/directory/counterparties/5?tab=x'], // query переносится
  ['/deals/mp/5#anchor',  '/accounts/mp/5#anchor'],               // хеш переносится
  ['/deals/stage-demo',   '/deals/stage-demo'],  // исключён негативным lookahead
  ['/sales/deals/9',      '/sales/deals/9'],     // уже актуальный адрес
]

// Страницы, законно отсутствующие в карте и среди целей редиректов.
const ORPHAN_ALLOWED = new Set([
  '/_app',        // не маршрут, а обёртка приложения
  '/login',       // вход, до прав и до навигации
  '/index',       // корень, сам разводит по контурам
  '/directories', // исторический адрес-заглушка, редиректит на /directory
  '/finance',     // точка входа контура (выбирает первый доступный экран)
  '/sales',
  '/accounts',
  '/directory',
])
// settings и settings/* гейтятся отдельным require_admin, в карту не входят намеренно
const orphanExempt = (route) => ORPHAN_ALLOWED.has(route) || route === '/settings' || route.startsWith('/settings/')

// 1. Адреса экранов уникальны
const seen = new Map()
for (const s of nav.sections)
  for (const it of s.items) {
    if (seen.has(it.href)) errors.push(`Адрес ${it.href} встречается дважды: ${seen.get(it.href)} и ${s.key}.${it.key}`)
    seen.set(it.href, `${s.key}.${it.key}`)
  }

// 2. Под каждый адрес есть файл страницы
const pageExists = (href) => {
  const p = href.replace(/^\//, '')
  return existsSync(`pages/${p}.js`) || existsSync(`pages/${p}/index.js`) || (p === '' && existsSync('pages/index.js'))
}
for (const s of nav.sections)
  for (const it of s.items)
    if (!pageExists(it.href)) errors.push(`Нет файла страницы для ${s.key}.${it.key} → ${it.href}`)

// 3. Редиректы ведут на существующие адреса карты.
// Параметрические (`/deals/:id`) проверяются иначе: конкретной цели у них нет,
// поэтому сверяем, что существует страница-шаблон под их основанием.
for (const r of nav.redirects) {
  if (r.to.includes(':')) {
    const base = r.to.split('/:')[0].replace(/^\//, '')
    if (!existsSync(`pages/${base}`)) errors.push(`Редирект ${r.from} → ${r.to}: нет папки pages/${base}`)
  } else if (!seen.has(r.to) && !nav.sections.some(s => s.href === r.to)) {
    errors.push(`Редирект ${r.from} → ${r.to}: цели нет в карте`)
  }
  if (seen.has(r.from)) errors.push(`Редирект ${r.from} перекрывает действующий экран`)
}

// 4. Разбор правил: тот же код, что работает в браузере (lib/legacy.mjs), на таблице ожиданий
for (const [href, expected] of RESOLVE_CASES) {
  const got = resolveLegacy(href, nav.redirects)
  if (got !== expected) errors.push(`Разбор правил: ${href} → ${got}, ожидалось ${expected}`)
}

// 5. Цепочки редиректов. Next цепочки не разворачивает: если цель одного правила
// сама подпадает под другое, человек упирается в лишний прыжок или в 404.
for (const r of nav.redirects) {
  const probe = r.to.replace(/:([A-Za-z0-9_]+)(\([^]*\))?/g, '1')
  const got = resolveLegacy(probe, nav.redirects)
  if (got !== probe) errors.push(`Цепочка редиректов: ${r.from} → ${r.to}, а ${probe} сам редиректится на ${got}`)
}

// 6. Обратная сверка: страницы, которых нет ни в карте, ни среди целей редиректов.
// Не ошибка (есть законные исключения), а предупреждение — чтобы забытая страница
// не жила незамеченной.
const walk = (dir, acc = []) => {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const full = `${dir}/${e.name}`
    if (e.isDirectory()) walk(full, acc)
    else if (/\.(js|jsx)$/.test(e.name)) acc.push(full)
  }
  return acc
}
const known = new Set([...seen.keys(), ...nav.sections.map(s => s.href)])
for (const r of nav.redirects) known.add(r.to)
if (existsSync('pages')) {
  for (const f of walk('pages')) {
    let route = '/' + f.replace(/^pages\//, '').replace(/\.(js|jsx)$/, '')
    // динамические сегменты приводим к синтаксису карты: [id] → :id
    const asParam = route.replace(/\[([^\]]+)\]/g, ':$1')
    const asIndex = asParam.replace(/\/index$/, '') || '/'
    if (orphanExempt(route) || orphanExempt(asIndex)) continue
    if (known.has(asParam) || known.has(asIndex)) continue
    warnings.push(`Страница ${f} не значится ни в карте, ни среди целей редиректов`)
  }
}

if (errors.length) {
  console.error('Карта навигации: ошибок ' + errors.length)
  for (const e of errors) console.error('  · ' + e)
  process.exit(1)
}
console.log(`Карта навигации в порядке: разделов ${nav.sections.length}, экранов ${seen.size}, редиректов ${nav.redirects.length}, разбор правил ${RESOLVE_CASES.length}/${RESOLVE_CASES.length}`)
if (warnings.length) {
  console.log('Предупреждения (осиротевшие страницы), всего ' + warnings.length + ':')
  for (const w of warnings) console.log('  · ' + w)
}
