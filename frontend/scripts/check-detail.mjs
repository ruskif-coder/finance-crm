/**
 * Гейт сборки: причину отказа сервера показываем только через `detailText` (`lib/loadError.js`).
 *
 * ЗАЧЕМ. FastAPI кладёт причину отказа в `detail`: обычно строкой, а на ошибке проверки (422) — СПИСКОМ объектов
 * `{type, loc, msg, input}`. Код вида `setErr(e.response?.data?.detail || 'Не удалось')` кладёт этот список в JSX,
 * и React роняет страницу целиком («Application error», React #31). Так упала карточка сделки при назначении трафика
 * 13.11.2026; таких мест было 380 в 128 файлах.
 *
 * ЧТО ЛОВИМ. Любое чтение `response.data.detail` (с `?.` или без) вне `lib/loadError.js`. Если место действительно
 * разбирает структуру `detail` само (не показывает её как текст) — пометить строку комментарием `detail-ok: <почему>`.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['components', 'pages', 'lib']
const SKIP = new Set([join('lib', 'loadError.js')])
const RX = /response\??\.data\??\.detail/

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(jsx?|mjs)$/.test(name) && !/\.test\.mjs$/.test(name)) out.push(p)
  }
  return out
}

const bad = []
for (const d of DIRS) {
  for (const f of walk(join(ROOT, d))) {
    const rel = relative(ROOT, f)
    if (SKIP.has(rel)) continue
    readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
      if (RX.test(line) && !line.includes('detail-ok:')) bad.push(`${rel}:${i + 1}: ${line.trim().slice(0, 120)}`)
    })
  }
}

if (bad.length) {
  console.error(`check-detail: ${bad.length} мест показывают detail сервера мимо detailText (lib/loadError.js) — `
    + 'на 422 это уронит страницу:\n' + bad.slice(0, 40).join('\n') + (bad.length > 40 ? `\n… и ещё ${bad.length - 40}` : ''))
  process.exit(1)
}
console.log('check-detail: ok — причина отказа сервера везде через detailText')
