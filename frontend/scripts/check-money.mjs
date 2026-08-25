/**
 * Гейт сборки: разбор денежной строки не должен терять запятую.
 *
 * В интерфейсе десятичный разделитель — запятая: поля сумм принимают «100714,71»
 * (см. sanMoney в pages/finance/operations.js, оно намеренно пропускает и точку,
 * и запятую). Разбор такой строки обязан приводить запятую к точке.
 *
 * Ошибка, ради которой заведён гейт: в форме операции стоял свой разбор
 *
 *     const toNum = (v) => Number(String(v).replace(/[^0-9.]/g, '')) || 0
 *
 * Он вырезал запятую вместе с остальными «лишними» символами, и «100714,71»
 * превращалось в 10071471. На сервер при этом уходило правильное значение —
 * расходились два разбора одной строки в одном файле. Наружу это вышло как
 * «НДС в превью 1 816 167 ₽ вместо 18 161,67 ₽»: число правдоподобное, ошибка
 * ровно в 100 раз, и заметить её можно только сложив в уме.
 *
 * Что ищем: класс символов с отрицанием, в котором точка есть, а запятой нет.
 * Именно эта форма и означает «точка — разделитель, запятая — мусор».
 * Проверка текстовая и намеренно узкая: она ловит форму ошибки, а не все
 * возможные способы неправильно разобрать число.
 */
import { readdirSync, readFileSync, statSync } from 'fs'
import { dirname, join, relative } from 'path'
import { fileURLToPath } from 'url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIRS = ['pages', 'components', 'lib']

/** Класс вида [^...] , внутри которого есть точка и нет запятой. */
const NEGATED_CLASS = /\[\^([^\]]*)\]/g

const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p)
    else if (name.endsWith('.js') || name.endsWith('.mjs')) files.push(p)
  }
}
DIRS.forEach(d => walk(join(ROOT, d)))

const bad = []
for (const file of files) {
  const src = readFileSync(file, 'utf8')
  const lines = src.split('\n')
  lines.forEach((line, i) => {
    if (!line.includes('replace')) return
    for (const m of line.matchAll(NEGATED_CLASS)) {
      const body = m[1]
      if (body.includes('.') && !body.includes(',')) {
        bad.push(`${relative(ROOT, file)}:${i + 1}  ${line.trim()}`)
      }
    }
  })
}

if (bad.length) {
  console.error('\nРазбор суммы теряет запятую — копейки пропадут, число вырастет в 100 раз:\n')
  bad.forEach(b => console.error('  ' + b))
  console.error('\nЗапятая — десятичный разделитель, а не мусор. Приводите её к точке:')
  console.error("  parseFloat(String(v ?? '').replace(',', '.'))\n")
  process.exit(1)
}

console.log(`check-money: ok (${files.length} файлов)`)
