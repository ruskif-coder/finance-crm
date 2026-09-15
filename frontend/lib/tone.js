/**
 * Тон уведомления на фронте — один словарь.
 *
 * ## Что здесь произошло 14.09.2026
 *
 * Слов для тона было ДВА: реестр событий говорил `danger | warning | success | info`,
 * а сканер, каталог площадок, письмо и панель — `bad | warn | ok | info`. Пересекались
 * они только на `info`, поэтому расхождение не падало ни одним тестом.
 *
 * Бэкенд свели к канону (`app/notify/tone.py`), и ручки стали отдавать только
 * `bad | warn | ok | info`. А два экрана остались со старыми ключами и перестали
 * находить свой цвет:
 *
 * * виджет уведомлений на дашборде — маркер тона у всех строк стал синим, а красная
 *   подсветка срочной кнопки (`n.tone === 'danger'`) не срабатывала больше никогда;
 * * каталог в настройках уведомлений — цветная точка у всех событий, кроме `info`.
 *
 * Ни одно из этого не падает и не пишет в консоль: фон просто берётся из `|| accent`.
 * Ровно та тихая деградация, ради которой здесь заведён общий словарь и гейт
 * `check-tone`, запрещающий локальные карты со старыми ключами.
 *
 * ## Как пользоваться
 *
 *     import { toneOf, TONE } from '@/lib/tone'
 *     const t = TONE[toneOf(n.tone)]
 *     <span style={{ background: t.dot }} />
 *
 * `toneOf` нужен даже когда сервер отдаёт канон: в `notifications.tone` лежат строки,
 * записанные ДО 14.09 старыми словами, и переписывать историю ради словаря незачем.
 */

/** Порядок — это ТЯЖЕСТЬ, а не алфавит: по нему сортируется панель и раскладывается
    дайджест. «К сведению» стоит выше «готово», потому что готовое уже не требует
    внимания. Тот же порядок в `backend/app/notify/tone.py`. */
export const TONE_ORDER = ['bad', 'warn', 'info', 'ok']

/** Цвета по ролям. `dot` — маркер и точка, `tint`/`border`/`fg` — плашка с текстом.
    Текст берётся из семейства `-fg`: цвет смысла на своей же подложке даёт 2.8:1. */
export const TONE = {
  bad: { dot: 'var(--danger)', tint: 'var(--danger-tint)', border: 'var(--danger-border)', fg: 'var(--danger-fg)' },
  warn: { dot: 'var(--warning)', tint: 'var(--warning-tint)', border: 'var(--warning-border)', fg: 'var(--warning-fg)' },
  info: { dot: 'var(--accent)', tint: 'var(--accent-tint)', border: 'var(--accent-border)', fg: 'var(--accent)' },
  ok: { dot: 'var(--income)', tint: 'var(--income-tint)', border: 'var(--income-border)', fg: 'var(--income-fg)' },
}

/** Прежние слова → канон. Односторонний: обратно не переводим нигде. */
const ALIASES = { danger: 'bad', warning: 'warn', success: 'ok', error: 'bad', good: 'ok' }

/** Привести тон к канону. Пустое и незнакомое — «к сведению»: уведомление важнее
    строгости словаря, а опечатки ловит гейт, а не отрисовка. */
export const toneOf = (v) => {
  const s = String(v || '').toLowerCase()
  const k = ALIASES[s] || s
  return TONE[k] ? k : 'info'
}

/** Вес для сортировки: чем меньше, тем важнее. */
export const toneWeight = (v) => TONE_ORDER.indexOf(toneOf(v))
