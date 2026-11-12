// Первые три этапа пакета — итоговая сверка, сборка ДС, согласование ДС (владелец 12.11.2026: «корректно и внятно, с описанием,
// что надо сделать, чтобы пойти дальше»). Поломки, которые ловит набор: этап назван внутренним статусом («черновик», «ждём
// закрытия»); строка «сейчас» не говорит, ГДЕ сделать шаг; у сверки нет ссылки на сделку; у согласования не видно, кто держит ДС.
import test from 'node:test'
import assert from 'node:assert/strict'
import { nextAction, stagesOf } from './masterNext.js'

const SEQ = ['черновик', 'согласование', 'ждём 1С', 'выставление', 'ждём оплату', 'архив']
const pack = (status, extra = {}) => ({ code: 'M-0031', status, sequence: SEQ, deals: [], annexes: [], todo: null, ...extra })

test('этапы пакета называются словами процесса, сверка — первым шагом', () => {
  const s = stagesOf(pack('черновик', { todo: { text: 'задать стартовый № ДС', who: 'аккаунт' } }))
  assert.deepEqual(s.items.map(x => x.label).slice(0, 3), ['итоговая сверка', 'сборка ДС', 'согласование ДС'])
  assert.equal(s.current, 1)
})

test('сделка не сведена — текущий этап «итоговая сверка», ссылка на сделку и что в ней сделать', () => {
  const m = pack('черновик', { todo: { text: 'дождаться сверки сделок', who: 'аккаунт' },
    deals: [{ code: 'ZQ7QS7', state: 'rk' }, { code: 'AB12CD', state: 'done' }] })
  assert.equal(stagesOf(m).current, 0)
  const a = nextAction(m)
  assert.equal(a.text, 'Завершите итоговую сверку сделки ZQ7QS7')
  assert.match(a.hint, /РК не завершена/)
  assert.deepEqual(a.link, { label: 'Открыть сделку ZQ7QS7 →', href: '/sales/deals/ZQ7QS7' })
})

test('стартовый пакет ждёт закрытия — тот же этап сверки, подсказка про «Отправить в ДО»', () => {
  const m = pack('ждём закрытия', { sequence: ['черновик', 'согласование', 'ждём закрытия', 'ждём 1С'], deals: [{ code: 'ZQ7QS7', state: 'ready' }] })
  const s = stagesOf(m)
  assert.equal(s.items[s.current].label, 'итоговая сверка')
  assert.match(nextAction(m).hint, /«Отправить в ДО»/)
})

test('сборка ДС: номер не задан — говорит, где поле', () => {
  const a = nextAction(pack('черновик', { todo: { text: 'задать стартовый № ДС', who: 'аккаунт' } }))
  assert.equal(a.text, 'Задайте стартовый № ДС')
  assert.match(a.hint, /«Раскладке» слева/)
  assert.equal(a.scroll, 'layout')
})

test('сборка ДС: всё готово — кнопка «В конструктор ДС» внизу', () => {
  const a = nextAction(pack('черновик', { todo: { text: 'создать ДС', who: 'аккаунт' } }))
  assert.equal(a.text, 'Раскладка готова — создайте ДС пакета')
  assert.match(a.hint, /«В конструктор ДС →»/)
})

test('согласование ДС: у аккаунта — какие ДС подтвердить и чем; у юриста — ждать', () => {
  const annexes = [{ number: 'ДС № 6', confirmed: false }, { number: 'ДС № 6-01', confirmed: false }, { number: 'ДС № 5', confirmed: true }]
  const acc = nextAction(pack('согласование', { annexes, todo: { text: 'подтвердить ДС (2)', who: 'аккаунт' } }))
  assert.equal(acc.text, 'Подтвердите ДС: ДС № 6, ДС № 6-01')
  assert.match(acc.hint, /«Подтвердить ДС пакета»/)
  const law = nextAction(pack('согласование', { annexes, todo: { text: 'заявка юристу по ДС (1)', who: 'юрист' } }))
  assert.equal(law.who, 'юрист')
  assert.match(law.hint, /от вас ничего не нужно/)
})

test('сборка ДС: неизвестная причина раскладки не выдаётся за «готово»', () => {
  const a = nextAction(pack('черновик', { todo: { text: 'у договора не определён шаблон ДС', who: 'аккаунт' } }))
  assert.equal(a.text, 'У договора не определён шаблон ДС')
})

test('согласование после возврата: ДС с номерами — «Обновить из сделки» и «ДС проверены → в 1С»', () => {
  const a = nextAction(pack('согласование', { unconfirmed: 0, annexes: [{ number: 'ДС № 6', confirmed: true }], todo: { text: 'подтвердить ДС (0)', who: 'аккаунт' } }))
  assert.equal(a.text, 'Пересоберите ДС по текущим данным и отправьте в 1С')
  assert.match(a.hint, /«ДС проверены → в 1С»/)
})
