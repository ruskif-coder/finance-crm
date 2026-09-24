// Гейт: ссылка из ДАННЫХ в href — только через safeHref (аудит 23.09.2026, 7.M1).
//
// Ловит `href={…}`, в котором выражение читает поле-ссылку из данных (chat_url,
// figma_url, max_url, advertiser_url, document_url, …url) и не обёрнуто в safeHref.
// Внутренние адреса (`/deals/…`, шаблонные строки с путём) гейт не трогает — они не
// приходят от людей.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const ROOTS = process.argv.slice(2).length ? process.argv.slice(2) : ['components', 'pages']
const DATA_URL = /\b(chat_url(_max)?|figma_url|max_url|advertiser_url|document_url|\w+\.url)\b/
const HREF = /href=\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(jsx?|mjs)$/.test(name)) yield p
  }
}

const bad = []
for (const root of ROOTS) {
  for (const file of walk(root)) {
    const src = readFileSync(file, 'utf8')
    for (const m of src.matchAll(HREF)) {
      const expr = m[1]
      if (DATA_URL.test(expr) && !/safeHref\(/.test(expr)) {
        const line = src.slice(0, m.index).split('\n').length
        bad.push(`${file}:${line}  href={${expr.trim()}}`)
      }
    }
  }
}
if (bad.length) {
  console.error('check-hrefs: ссылка из данных без safeHref — схема javascript: исполнит код:')
  bad.forEach(b => console.error('  ' + b))
  process.exit(1)
}
console.log('check-hrefs: ссылки из данных идут через safeHref — порядок')
