/**
 * Гейт сборки: возврат на вкладку не стирает несохранённый ввод.
 *
 * ЗАЧЕМ. 23.09.2026 аккаунты пожаловались: заполняешь годовой план, уходишь в соседнюю
 * вкладку за материалом, возвращаешься — заполненного нет. Перечитка при возврате
 * (`lib/useRefreshOnReturn`) писала данные сервера поверх экрана. Защита теперь стоит в
 * `lib/unsaved`, и сломать её можно тихо: перечитка продолжит работать, просто снова
 * будет стирать. Со стороны это неотличимо от «данные не сохранились».
 *
 * Проверяется ПОВЕДЕНИЕ, а не текст: модуль грузится на подставном DOM и проходит
 * сценарии. Сверка строк исходника пропустила бы перевёрнутое условие.
 *
 * Ещё проверяется, что хук действительно спрашивает учёт, а годовой план — сообщает в
 * него свой признак: без этих двух связей модуль работал бы сам по себе, никого не
 * защищая.
 */
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { pathToFileURL } from 'node:url'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const bad = []

// ── Подставной DOM: ровно то, чем пользуется модуль ─────────────────────────────
const listeners = {}
globalThis.window = {}
globalThis.document = {
  addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn) },
}
const routeHandlers = []

class El {
  constructor(tag, attrs = {}, parentAttrs = null) {
    this.tagName = tag; this.type = attrs.type || ''; this.attrs = attrs
    this.isConnected = true; this.isContentEditable = false; this.parentAttrs = parentAttrs
  }
  getAttribute(k) { return this.attrs[k] ?? null }
  // Метка проверяется НАЛИЧИЕМ, как в браузере: у `data-no-unsaved` значение пустое,
  // и проверка по значению (первая редакция прибора) принимала её за отсутствие.
  closest(sel) { return sel === '[data-no-unsaved]' && this.parentAttrs && 'data-no-unsaved' in this.parentAttrs ? {} : null }
}
const type = (el, trusted = true) =>
  (listeners.input || []).forEach((fn) => fn({ target: el, isTrusted: trusted }))

// Модуль написан с `import`, а пакет не объявлен как ES-модуль: копия во временный .mjs,
// маршрутизатор Next подменён — проверяется учёт, а не Next.
const src = readFileSync(join(ROOT, 'lib/unsaved.js'), 'utf8').replace(
  "import Router from 'next/router'",
  'const Router = { events: { on: (e, fn) => globalThis.__route.push([e, fn]) } }')
globalThis.__route = routeHandlers
const dir = mkdtempSync(join(tmpdir(), 'unsaved-'))
const file = join(dir, 'unsaved.mjs')
writeFileSync(file, src)
const u = await import(pathToFileURL(file).href)
rmSync(dir, { recursive: true, force: true })

const expect = (cond, msg) => { if (!cond) bad.push(msg) }

// 1. Чистый экран перечитывается.
expect(!u.hasUnsaved(), 'пустой экран считается несохранённым — перечитка не пойдёт никогда')

// 2. Человек ввёл в поле — перечитка ждёт.
const field = new El('INPUT')
type(field)
expect(u.hasUnsaved(), 'ввод в поле не засчитан — возврат на вкладку сотрёт его')

// 3. Окно закрыли / поле ушло с экрана — учёт снялся сам.
field.isConnected = false
expect(!u.hasUnsaved(), 'поле ушло с экрана, а перечитка всё ещё заблокирована')

// 4. Программная подстановка значения — не правка.
type(new El('INPUT'), false)
expect(!u.hasUnsaved(), 'подстановка кодом засчитана как ввод человека')

// 5. Поиск и фильтры не блокируют обновление реестра.
type(new El('INPUT', { type: 'search' }))
type(new El('INPUT', { placeholder: 'Поиск по сделкам' }))
type(new El('INPUT', {}, { 'data-no-unsaved': '' }))
expect(!u.hasUnsaved(), 'набранный поиск блокирует обновление — реестр перестал бы освежаться')

// 6. Правка щелчками: явная отметка держит, сохранение снимает.
u.markDirty()
expect(u.hasUnsaved(), 'markDirty не блокирует перечитку — годовой план снова будет стираться')
u.markClean()
expect(!u.hasUnsaved(), 'после сохранения перечитка так и осталась заблокированной')

// 7. Смена страницы снимает всё.
u.markDirty(); type(new El('TEXTAREA'))
const onRoute = routeHandlers.find(([e]) => e === 'routeChangeComplete')
expect(!!onRoute, 'смена страницы не снимает учёт — новая страница не обновится никогда')
if (onRoute) { onRoute[1](); expect(!u.hasUnsaved(), 'после смены страницы учёт не снят') }

// ── Связи: без них модуль никого не защищает ────────────────────────────────────
const hook = readFileSync(join(ROOT, 'lib/useRefreshOnReturn.js'), 'utf8')
expect((hook.match(/!hasUnsaved\(\)/g) || []).length >= 2,
  'useRefreshOnReturn не спрашивает учёт в обоих событиях (возврат и bfcache)')
const plan = readFileSync(join(ROOT, 'components/plan/YearPlan.jsx'), 'utf8')
expect(/if \(dirty\) markDirty\(\)/.test(plan),
  'годовой план не сообщает свой признак несохранённых правок')

if (bad.length) {
  console.error('\ncheck-unsaved: возврат на вкладку может стереть несохранённый ввод\n  · '
    + bad.join('\n  · ') + '\n')
  process.exit(1)
}
console.log('check-unsaved: несохранённый ввод переживает возврат на вкладку — порядок')
