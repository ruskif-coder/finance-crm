/**
 * Гейт сборки: ввод суммы с копейками разбирается верно.
 *
 * ЗАЧЕМ. До 23.09.2026 мобильная форма операции разбирала сумму своим
 * `replace(/\D/g, '')`: «1500,50» сохранялось как 150 050 ₽, а правка суммы
 * 100 714,71 — как округлённые 100 715. Теперь разбор один (`lib/money.js`), и этот
 * гейт проверяет его ПОВЕДЕНИЕ на тех самых случаях, а не текст исходника.
 */
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const { sanMoney, moneyNum } = await import(pathToFileURL(join(ROOT, 'lib/money.js')).href)

const cases = [
  ['1500,50', 1500.5], ['1500.50', 1500.5], ['100 714,71', 100714.71],
  ['1 000 ₽', 1000], ['', 0], ['1,5', 1.5],
  // Вставка с разрядами (ревью 23.09.2026): до правки первые два давали 1,5005.
  ['1,500.50', 1500.5], ['1.500,50', 1500.5], ['1.000.000', 1000000],
  ['1 500 000,00', 1500000], ['2.500,', 2500],
]
// moneyNum обязан разбирать и НЕочищенную строку так же — её зовут и на вставленном.
const raw = [['1,500.50', 1500.5], ['1.500,50', 1500.5]]
  .filter(([i, w]) => Math.abs(moneyNum(i) - w) > 1e-9)
if (raw.length) {
  console.error('check-money-input: moneyNum без sanMoney разбирает иначе: ' + raw.map(([i]) => i).join(', '))
  process.exit(1)
}
const bad = cases
  .map(([input, want]) => [input, want, moneyNum(sanMoney(input))])
  .filter(([, want, got]) => Math.abs(got - want) > 1e-9)

if (bad.length) {
  console.error('check-money-input: разбор суммы неверен\n  · '
    + bad.map(([i, w, g]) => `«${i}» → ${g}, ждали ${w}`).join('\n  · '))
  process.exit(1)
}
console.log('check-money-input: суммы с копейками разбираются верно — порядок')
