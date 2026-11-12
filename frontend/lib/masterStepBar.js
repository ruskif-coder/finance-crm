/**
 * Полоса «что сделать сейчас» — первая в блоке «ДС · комплекты · документы» расхлопа реестра (хендофф реестра v3, 12.11.2026).
 * Слева шаг «N из 6», фраза-действие и пояснение, справа одна главная кнопка на весь пакет. Нет действия — нет кнопки, только
 * объяснение. Данные — карточка пакета (`GET /master-deals/{код}`); правила и запреты отметок — на сервере (`issue.send_docs`).
 *
 * Отличие от макета (`detail()` → `step*`): у бумаги «ждём оплату» и «ждём сканы» — две стадии, как на сервере: сначала
 * «Оплачено», потом сканы и «В архив». У ЭДО подпись клиента до подключения Диадока отмечают руками у документов ниже.
 */
import { nextAction } from './masterNext.js'
import { plural } from './publisherRecon.mjs'

const SENT = 'выставлен'
const OURS = 'подписан у нас'
const OUT = new Set([SENT, 'подписан'])
const NO = { 'черновик': 1, 'согласование': 2, 'ждём закрытия': 2, 'ждём 1С': 3, 'выставление': 4, 'ждём оплату': 5, 'ждём сканы': 5, 'архив': 6 }

export const docsWord = (n) => plural(n, 'документ', 'документа', 'документов')

/** Документы пакета, уходящие клиенту, по порядку экрана: ДС и его комплекты; комплекты — сквозной номер, как в расхлопе. */
export function packDocs(m) {
  const out = []
  let n = 0
  for (const d of m?.docs?.ds || []) {
    out.push({ ref: { annex_id: d.annex_id }, label: d.number, sign: d.sign, scan: d.scan, kind: 'ds' })
    for (const k of d.kits || []) {
      n += 1
      out.push({ ref: { upd_no: k.upd_no }, label: `комплект ${n}`, sign: k.sign, scan: k.scan, kind: 'kit' })
    }
  }
  return out
}

const bar = (tone, title, sub, extra = {}) => ({ tone, title, sub, zip: false, btn: null, link: null, ...extra })

function issueEdo(docs, canEdit) {
  // отклонённый клиентом в «отправил все» не входит: его сначала переделывают и отмечают у документа (ревью 12.11.2026)
  const left = docs.filter(d => !OUT.has(d.sign?.state) && d.sign?.state !== 'отклонён')
  if (!left.length && docs.some(d => d.sign?.state === 'отклонён')) {
    return bar('bad', 'Клиент отклонил документ — переделайте и отправьте снова', 'Отметка «отметить отправку» — у отклонённого документа ниже, после переделки.')
  }
  if (!left.length) return bar('ok', 'Всё отправлено клиенту в Диадок', 'Пакет переходит в «ждём оплату».')
  const sent = docs.length - left.length
  const all = left.length === docs.length
  return bar('act', `${sent ? 'Осталось отправить' : 'Отправьте'} клиенту через Диадок: ${left.length} ${docsWord(left.length)} — ${left.map(d => d.label).join(', ')}`,
    `Скачайте файлы, загрузите в Диадок, отправьте клиенту — и отметьте здесь. Отправлено ${sent} из ${docs.length}; после последней отметки пакет перейдёт в «ждём оплату».`,
    { zip: true, btn: canEdit ? { label: all ? `Отметить: отправил все ${docs.length}` : left.length === 1 ? `Отметить: отправил ${left[0].label}` : `Отметить: отправил остальные ${left.length}`,
      title: 'Отметить отправку всех оставшихся документов разом', body: { items: left.map(d => d.ref), on: true, state: SENT } } : null })
}

function issuePaper(docs, canEdit) {
  if (docs.some(d => d.sign?.state !== OURS && d.sign?.state !== 'отклонён' && !OUT.has(d.sign?.state))) {
    return bar('act', 'Распечатайте и подпишите документы у нас',
      'ДС и комплекты (счёт и УПД) — кнопки «ДС pdf», «Счёт», «УПД» ниже. Следующий шаг — отправить клиенту почтой или курьером.',
      { btn: canEdit ? { label: 'Отметить: подписано у нас', title: 'Документы подписаны с нашей стороны', body: { items: [], on: true, state: OURS } } : null })
  }
  return bar('act', 'Отправьте подписанные документы клиенту',
    'Почтой или курьером. Трек-номер можно указать при отметке. Дальше — ждём оплату и сканы подписанных клиентом документов.',
    { btn: canEdit ? { label: 'Отметить: отправлено клиенту', title: 'Отметить отправку клиенту', track: true, body: { items: [], on: true, state: SENT } } : null })
}

function scans(docs, canEdit) {
  const ds = docs.filter(d => d.kind === 'ds'), kits = docs.filter(d => d.kind === 'kit')
  const dsHave = ds.filter(d => d.scan).length, kitHave = kits.filter(d => d.scan).length
  if (dsHave < ds.length || kitHave < kits.length) {
    return bar('act', 'Прикрепите сканы подписанных клиентом документов',
      `Нужны: ДС ${dsHave} из ${ds.length} · УПД ${kitHave} из ${kits.length}. Один файл — один документ, загрузка в панели ниже. Без сканов пакет не уйдёт в архив.`)
  }
  return bar('act', 'Сканы на месте — переведите пакет в архив', 'Оплачено, все документы подписаны.',
    { btn: canEdit ? { label: 'В архив', title: 'Перевести в архив', status: 'архив' } : null })
}

function waitPay(m, docs, canEdit) {
  if (m.issue?.paper) {
    return bar('wait', 'Ждём оплату', 'Документы у клиента. Когда деньги придут — отметьте оплату, дальше сканы подписанных.',
      { btn: canEdit ? { label: 'Оплачено', title: 'Отметить оплату', status: 'ждём сканы' } : null })
  }
  if (docs.length && docs.every(d => d.sign?.state === 'подписан')) {
    return bar('act', 'Подписано в Диадоке — ждём оплату', 'Сканы не нужны. Когда оплата придёт, переведите пакет в архив.',
      { btn: canEdit ? { label: 'В архив', title: 'Перевести в архив', status: 'архив' } : null })
  }
  return bar('wait', 'Ждём подпись клиента в Диадоке и оплату',
    'Всё отправлено. Пока Диадок не подключён, подпись клиента отметьте у документа ниже — «Подписан клиентом».')
}

export function stepBar(m, canEdit) {
  const docs = packDocs(m)
  const href = `/accounts/master/${m.code}`
  const base = (() => {
    if (['ждём 1С', 'выставление'].includes(m.status) && !m.issue?.channel) {
      return bar('bad', 'В договоре не задано, как выставляем: ЭДО или бумага', 'Без этого документы не уйдут клиенту. Укажите канал в карточке договора.',
        { link: { label: 'Открыть договор', href: `/directory/contracts/${m.contract?.id ?? ''}`, tone: 'bad' } })
    }
    const act = nextAction(m)      // сверка, сборка, согласование — тем же текстом, что карточка (владелец 12.11.2026)
    if (act) {
      return bar(act.who === 'юрист' ? 'wait' : 'act', act.text, act.hint || '',
        { link: act.link ? { ...act.link, tone: 'act' } : (act.who === 'юрист' ? null : { label: m.status === 'согласование' ? 'К согласованию ДС →' : 'Перейти к ДС →', href, tone: 'act' }) })
    }
    switch (m.status) {
      case 'черновик': return bar('act', `Соберите пакет: ${m.todo?.text || 'создать ДС'}`, 'Очередь: аккаунт. ДС собирается в конструкторе — дальше согласование у юриста.',
        { link: { label: 'Перейти к ДС →', href, tone: 'act' } })
      case 'согласование': return m.todo?.who === 'юрист'
        ? bar('wait', 'ДС у юриста — ждём согласования', 'От вас ничего не нужно. Правка ДС запустит согласование заново.')
        : bar('act', 'Проверьте и подтвердите ДС', `${m.todo?.text || ''} · после подтверждения пакет уйдёт в 1С.`, { link: { label: 'К согласованию ДС →', href, tone: 'act' } })
      case 'ждём закрытия': return bar('wait', 'ДС на старте выпущен — ждём закрытия сделок', 'От вас ничего не нужно до итоговой сверки.')
      case 'ждём 1С': return bar('wait', 'Ждём счёт и УПД из 1С', 'От вас ничего не нужно. Номера счёта и УПД придут из 1С — после этого пакет перейдёт в «выставление».')
      case 'выставление': return m.issue?.paper ? issuePaper(docs, canEdit) : issueEdo(docs, canEdit)
      case 'ждём оплату': return waitPay(m, docs, canEdit)
      case 'ждём сканы': return scans(docs, canEdit)
      case 'архив': return bar('ok', 'Пакет закрыт', 'Оплачено, документы подписаны.')
      default: return bar('wait', m.todo?.text || m.status, '')
    }
  })()
  return { no: NO[m.status] || 1, ...base }
}
