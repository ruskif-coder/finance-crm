/**
 * Базовые шаблоны ДС — чистая логика экрана: подстановки, нумерация, зоны, живая проверка шаблона. Без React и без обращений к серверу:
 * ту же проверку сервер повторит при сохранении (docs/Макет_конструктор_ДС.md, п. «Проверка»).
 * Образцы значений подстановок — для предпросмотра в редакторе; настоящие подставляет сервер (`app/annex_tpl/assemble.py`).
 */

/** Подстановка → [образец, защищена]. Защищённые обязаны сходиться с таблицей МП. */
export const SUBS = {
  'рекламодатель': ['АО «Берлин-Хеми»', 0], 'бренд': ['Мезим', 0],
  'период_с': ['01.11.2026', 0], 'период_по': ['30.11.2026', 0],
  'сумма': ['671 000,00', 1], 'сумма_прописью': ['671\u00a0000 (Шестьсот семьдесят одна тысяча) рублей 00 копеек', 1],
  'ндс_ставка': ['22', 0], 'ндс_сумма': ['121 000,00', 1],
  'ндс_сумма_прописью': ['121\u00a0000 (Сто двадцать одна тысяча) рублей 00 копеек', 1],
  'номер_дс': ['68', 0], 'договор_номер': ['РМ 30-11-2023', 0], 'договор_дата': ['30.11.2023', 0],
}

/** Денежный пункт обязан содержать ЛЮБУЮ подстановку из каждой группы (цифра и фраза — от одного числа). */
export const PROTECTED_GROUPS = [['сумма', 'сумма_прописью'], ['ндс_сумма', 'ндс_сумма_прописью']]

export const SUB_INFO = {
  'рекламодатель': 'рекламодатель из сделки — короткое имя',
  'бренд': 'бренд из сделки',
  'период_с': 'начало периода размещения',
  'период_по': 'конец периода размещения',
  'сумма': 'итог таблицы МП, без НДС · защищена',
  'сумма_прописью': 'сумма прописью',
  'ндс_ставка': 'ставка НДС, %',
  'ндс_сумма': 'сумма НДС · защищена',
  'ндс_сумма_прописью': 'сумма НДС прописью',
  'номер_дс': 'номер этого ДС (приложения) — следующий после «ДС с» в реестре договоров',
  'договор_номер': 'номер основного договора',
  'договор_дата': 'дата основного договора',
}

/** Подстановки, которые могут оказаться пустыми у сделки: тогда выгрузка ДС блокируется. */
export const EMPTY = {
  'рекламодатель': ['рекламодатель', 'карточка сделки → «Рекламодатель»'],
  'договор_дата': ['дата договора', 'реестр договоров → «Дата»'],
}

/** Номера из порядка: основной пункт 1., 2.; подпункт — к предыдущему основному. */
export function numbering(blocks) {
  const num = {}
  let main = 0
  let sub = 0
  blocks.forEach(b => {
    if (b.sys) return
    if (b.sub && main) { sub += 1; num[b.id] = `${main}.${sub}.` } else { main += 1; sub = 0; num[b.id] = `${main}.` }
  })
  return num
}

/** Зона — из положения относительно таблицы МП: до неё правит аккаунт, после — юрист. */
export function zoneAt(blocks, i) {
  const t = blocks.findIndex(b => b.sys === 'table')
  return i < t ? 'acc' : 'law'
}

/** Через таблицу МП и системные блоки пункт не перескакивает. */
export function canMove(blocks, i, dir) {
  const j = i + dir
  return j >= 0 && j < blocks.length && !blocks[j].sys
}

export function moved(blocks, id, dir) {
  const i = blocks.findIndex(b => b.id === id)
  if (i < 0 || !canMove(blocks, i, dir)) return blocks
  const next = blocks.slice()
  next[i] = blocks[i + dir]
  next[i + dir] = blocks[i]
  return next
}

/** Разбор текста на куски: обычный, подстановка, неизвестная подстановка, пустая. */
export function segs(text, emptyDemo) {
  const out = []
  const re = /\{([^{}]+)\}/g
  let last = 0
  let m = re.exec(text)
  while (m) {
    if (m.index > last) out.push({ t: text.slice(last, m.index) })
    const key = m[1]
    const s = SUBS[key]
    if (s && emptyDemo && EMPTY[key]) out.push({ t: `нет: ${EMPTY[key][0]}`, bad: 1, empty: 1 })
    else out.push(s ? { t: s[0], sub: key, prot: s[1] } : { t: `{${key}}`, bad: 1 })
    last = re.lastIndex
    m = re.exec(text)
  }
  if (last < text.length) out.push({ t: text.slice(last) })
  return out
}

const unknownKeys = (t) => (t.match(/\{([^{}]+)\}/g) || []).filter(x => !SUBS[x.slice(1, -1)])

/** Проверка ВСЕГО шаблона. Пока есть ошибки, сохранение заблокировано. */
export function check(blocks) {
  const num = numbering(blocks)
  const issues = []
  blocks.forEach(b => {
    if (b.sys) return
    const where = `${num[b.id] || ''} ${b.title} · `
    const t = (b.text || '').trim()
    if (t.length < 3 || t === 'Текст пункта.') issues.push({ id: b.id, where, text: 'пункт не заполнен' })
    const bad = unknownKeys(t)
    if (bad.length) issues.push({ id: b.id, where, text: `неизвестная подстановка ${bad.join(', ')}` })
    if (b.money) {
      PROTECTED_GROUPS.forEach(g => {
        if (!g.some(k => t.indexOf(`{${k}}`) >= 0)) issues.push({ id: b.id, where, text: `убрана защищённая подстановка ${g.map(k => `{${k}}`).join(' или ')}` })
      })
    }
    if (b.title === 'Новый пункт') issues.push({ id: b.id, where, text: 'у пункта нет названия' })
  })
  return issues
}

/** Подстановки шаблона, которые у сделки могут быть пусты, — для баннера блокировки. */
export function emptyFields(blocks) {
  const used = {}
  blocks.forEach(b => ((b.text || '').match(/\{([^{}]+)\}/g) || []).forEach(x => { used[x.slice(1, -1)] = 1 }))
  return Object.keys(EMPTY).filter(k => used[k]).map(k => ({ label: EMPTY[k][0], where: EMPTY[k][1] }))
}

export function plural(n) {
  const a = n % 10
  const b = n % 100
  if (a === 1 && b !== 11) return 'ошибка'
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return 'ошибки'
  return 'ошибок'
}
