/**
 * Гейт сборки: экран, который читает данные, перечитывает их при возврате.
 *
 * ЗАЧЕМ. Механизма актуальности в приложении не было вовсе: каждый экран грузил данные
 * один раз при монтировании и больше не перепроверял (замер 13.09.2026 — перечитывающих
 * при возврате было 0 из 40). Со стороны это выглядит как «кеш»: правку, сделанную на
 * соседнем экране или другим человеком, не видно никогда, и человек правит второй раз,
 * решив, что не сохранилось.
 *
 * 13.09 хук `useRefreshOnReturn` завели на 34 экрана — и ПРОПУСТИЛИ ВЕСЬ ФИНМОДУЛЬ:
 * ДДС, баланс, операции, P&L, план-факт, дебиторку и фин. отчёт. Замечено только
 * 16.09.2026, и не человеком, а обходом графа кодовой базы. Ровно поэтому здесь прибор,
 * а не запись в заметках: список экранов растёт, и следующий пропуск будет таким же
 * тихим — число на экране просто окажется вчерашним.
 *
 * ЧТО ЛОВИМ. Страница, в которой есть запрос за данными, но нет `useRefreshOnReturn`.
 *
 * ЧЕГО НЕ ЛОВИМ (и почему — список ведётся осознанно, а не «чтобы стало зелёно»):
 *   · редиректы контуров и `_app` — своих данных не показывают;
 *   · `login` — открывается до авторизации, ему нечего перечитывать;
 *   · PDF-сайдкары (`**\/pdf/[id].js`) — печатная копия снимка, она обязана не меняться
 *     под рукой у того, кто её печатает;
 *   · РЕДАКТОРЫ с несохранёнными правками (конструктор МП, карточка приложения). Здесь
 *     перечитывание не «освежает», а МОЛЧА ВЫБРАСЫВАЕТ набранное. Несвежесть дешевле
 *     потери работы; там, где нужно и то и другое, хук ставится с `{ enabled: !dirty }`
 *     — так сделано на экране уведомлений.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const PAGES = ROOT + 'pages'

// Экраны, которым хук не нужен. Каждая строка — решение, а не умолчание.
const EXEMPT = [
  /^_app\.js$/, /^_document\.js$/, /^login\.js$/,
  /^index\.js$/, /^(accounts|finance|sales|traffic|directory|publishers)\/index\.js$/,
  /^directories\.js$/, /^settings\.js$/,
  /\/pdf\/\[id\]\.js$/,
  // редакторы: перечитывание затрёт несохранённое
  /^accounts\/mp\/\[id\]\.js$/, /^directory\/annexes\/\[id\]\.js$/, /^directory\/add\.js$/,
  // тела, импортируемые в другие экраны, а не маршруты (см. CLAUDE.md)
  /^settings\/articles\.js$/, /^settings\/pipelines\.js$/,
  // редирект на /settings/notifications
  /^settings\/mail\.js$/,
]

// Признак «экран читает данные»: любой из наших способов сходить на бэкенд.
const FETCHES = /\b(api|http|a|ax)\s*(\([^)]*\))?\.(get|post)\s*\(|useSWR\(|fetch\(['"`]\/api/

const walk = (dir, base = '') => readdirSync(dir).flatMap((name) => {
  const full = dir + '/' + name
  const rel = base ? base + '/' + name : name
  if (statSync(full).isDirectory()) return name === 'api' ? [] : walk(full, rel)
  return name.endsWith('.js') ? [rel] : []
})

const bad = []
for (const rel of walk(PAGES)) {
  if (EXEMPT.some((rx) => rx.test(rel))) continue
  const text = readFileSync(PAGES + '/' + rel, 'utf8')
  if (!FETCHES.test(text)) continue
  if (!text.includes('useRefreshOnReturn')) bad.push(rel)
}

if (bad.length) {
  console.error('\nЭкран читает данные, но не перечитывает их при возврате:\n')
  for (const f of bad) console.error('  pages/' + f)
  console.error('\nПоставьте `useRefreshOnReturn(load)` рядом с загрузкой (см. lib/useRefreshOnReturn),')
  console.error('а если экран держит несохранённые правки — `{ enabled: !dirty }` или запись в EXEMPT')
  console.error('этого файла с объяснением, почему перечитывать нельзя.\n')
  process.exit(1)
}
console.log('check-freshness: все экраны с данными перечитывают их при возврате')
