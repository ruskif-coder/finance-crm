// Тесты логики экрана шаблонов ДС. Запуск: node --test lib/annexTemplate.test.mjs
// Правило проверки шаблона одно на проект: сервер — `backend/app/annex_tpl/check.py`, здесь его зеркало для живой подсветки в редакторе.
import test from 'node:test'
import assert from 'node:assert/strict'
import { numbering, zoneAt, canMove, moved, check, segs, plural, emptyFields } from './annexTemplate.mjs'

// Образец блоков в форме реального шаблона владельца (пункты 1, 1.1, 1.2, 2–5).
const SAMPLE = [
  { id: 'head', sys: 'head', title: 'Заголовок' },
  { id: 'place', sys: 'place', title: 'Место и дата' },
  { id: 'pre', sys: 'pre', title: 'Преамбула со сторонами' },
  { id: 'p1', title: 'Предмет', req: 1, pin: 1, text: 'На условиях настоящего Приложения № {номер_дс} Исполнитель оказывает услуги в период с {период_с} по {период_по}:' },
  { id: 'mp', sys: 'table', title: 'Таблица медиаплана' },
  { id: 'p11', title: 'Стоимость', req: 1, pin: 1, sub: 1, money: 1, text: 'Стоимость {сумма_прописью}, включая НДС ({ндс_ставка}%) {ндс_сумма_прописью}.' },
  { id: 'p12', title: 'Требования к услугам', sub: 1, text: 'Услуги оказываются в соответствии с требованиями Заказчика.' },
  { id: 'p2', title: 'Претензии по качеству', text: 'Заказчик мотивированно сообщает Исполнителю, что его не устраивает.' },
  { id: 'p3', title: 'Остальное — по Договору', text: 'Во всем остальном стороны руководствуются Договором.' },
  { id: 'sign', sys: 'sign', title: 'Реквизиты и подписи сторон' },
]
const copy = () => SAMPLE.map(x => ({ ...x }))

test('нумерация считается из порядка, подпункты цепляются к основному', () => {
  const n = numbering(copy())
  assert.deepEqual([n.p1, n.p11, n.p12, n.p2, n.p3], ['1.', '1.1.', '1.2.', '2.', '3.'])
})

test('зона выводится из положения относительно таблицы МП', () => {
  const b = copy()
  assert.equal(zoneAt(b, b.findIndex(x => x.id === 'p1')), 'acc')
  assert.equal(zoneAt(b, b.findIndex(x => x.id === 'p11')), 'law')
})

test('пункт не перескакивает через таблицу МП и системные блоки', () => {
  const b = copy()
  assert.equal(canMove(b, b.findIndex(x => x.id === 'p1'), 1), false)
  assert.equal(moved(b, 'p1', 1), b)
  const j = b.findIndex(x => x.id === 'p12')
  assert.equal(moved(b, 'p12', 1)[j + 1].id, 'p12')
})

test('образец шаблона владельца проходит проверку; деньги — фразой с прописью', () => {
  assert.deepEqual(check(copy()), [])
})

test('проверка ловит пустой пункт, неизвестную подстановку, убранную сумму, безымянный пункт', () => {
  const b = copy()
  b.find(x => x.id === 'p11').text = 'Стоимость услуг {сумма} рублей {что_это}'
  b.find(x => x.id === 'p12').text = 'Текст пункта.'
  b.find(x => x.id === 'p2').title = 'Новый пункт'
  const texts = check(b).map(i => i.text).join(' | ')
  assert.match(texts, /неизвестная подстановка \{что_это\}/)
  assert.match(texts, /убрана защищённая подстановка \{ндс_сумма\} или \{ндс_сумма_прописью\}/)
  assert.doesNotMatch(texts, /подстановка \{сумма\} или/)
  assert.match(texts, /пункт не заполнен/)
  assert.match(texts, /у пункта нет названия/)
})

test('образец с пустыми полями: подстановка превращается в «нет: …», остальные остаются', () => {
  const s = segs('Дата {договор_дата}, бренд {бренд}', true)
  assert.equal(s.find(x => x.empty).t, 'нет: дата договора')
  assert.equal(s.find(x => x.sub === 'бренд').t, 'Мезим')
  const withBoth = copy().map(x => (x.id === 'p3' ? { ...x, text: 'Договор {договор_дата}, рекламодатель {рекламодатель}.' } : x))
  assert.deepEqual(emptyFields(withBoth).map(e => e.label).sort(), ['дата договора', 'рекламодатель'])
  assert.deepEqual(emptyFields(copy()), [])   // реальный шаблон этих подстановок не использует
})

test('склонение «ошибка»', () => {
  assert.deepEqual([1, 2, 5, 11, 12, 21, 24, 25].map(plural), ['ошибка', 'ошибки', 'ошибок', 'ошибок', 'ошибок', 'ошибка', 'ошибки', 'ошибок'])
})
