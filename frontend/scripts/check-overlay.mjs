/**
 * Гейт сборки: подложка модального окна закрывается только через `overlayClose`.
 *
 * ЗАЧЕМ. Событие `click` в DOM рождается на общем предке того, где нажали, и того, где
 * отпустили. Человек выделяет текст внутри окна, ведёт мышь и отпускает на подложке —
 * клик приходит подложке, проверка `e.target === e.currentTarget` его пропускает, и окно
 * закрывается вместе с набранным. Так было во всех 31 подложке проекта до 26.08.2026.
 * Помощник `lib/overlay.js` смотрит ещё и на то, где начался жест.
 *
 * ЧТО ЛОВИМ. Подложку С СОДЕРЖИМЫМ (`<div …>`, не самозакрывающийся), у которой есть
 * `onClick` и нет `overlayClose`. Прозрачные ловушки кликов под поповерами — пустой
 * самозакрывающийся `<div … />` рядом с поповером, а не вокруг него — правила не
 * касаются: выделять в них нечего, и клик из поповера до них не доходит.
 *
 * Гейт, а не заметка в навыке: заметку читают, когда о ней помнят, а этот баг живёт
 * до первой жалобы человека, который потерял набранный текст.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const DIRS = ['components', 'pages']
const OVERLAY = "position: 'fixed', inset: 0"

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.jsx?$/.test(name)) out.push(p)
  }
  return out
}

/** Конец открывающего тега: первый `>` вне фигурных скобок атрибутов.
 *  Наивный `indexOf('>')` спотыкается о стрелку в `onClick={() => …}` — так и вышло
 *  при первом прогоне: шестнадцать прозрачных ловушек кликов попали в нарушители. */
function tagEnd(text, start) {
  let depth = 0
  for (let i = start; i < text.length; i++) {
    const c = text[i]
    if (c === '{') depth++
    else if (c === '}') depth--
    else if (c === '>' && depth === 0) return i
  }
  return -1
}

const bad = []
for (const dir of DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const text = readFileSync(file, 'utf8')
    let at = text.indexOf(OVERLAY)
    while (at !== -1) {
      const open = text.lastIndexOf('<div', at)
      const end = open === -1 ? -1 : tagEnd(text, open)
      if (open !== -1 && end !== -1 && end > at) {
        const tag = text.slice(open, end + 1)
        const selfClosing = text[end - 1] === '/'      // пустая ловушка кликов
        if (!selfClosing && tag.includes('onClick=') && !tag.includes('overlayClose')) {
          const line = (text.slice(0, open).match(/\n/g) || []).length + 1
          bad.push(`${relative(ROOT, file)}:${line}`)
        }
      }
      at = text.indexOf(OVERLAY, at + 1)
    }
  }
}

if (bad.length) {
  console.error('\nПодложка модалки закрывается голым onClick — выделение текста будет')
  console.error('считаться кликом и закрывать окно. Использовать overlayClose из lib/overlay.js:\n')
  bad.forEach(b => console.error('  ' + b))
  console.error('')
  process.exit(1)
}
console.log(`check-overlay: подложек через overlayClose — порядок`)
