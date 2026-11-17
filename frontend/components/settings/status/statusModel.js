// Логика экрана «Статус системы» (макет design_handoff_status, 16.11.2026) — без React.
//
// Тон секции и тон экрана — худший по строкам, считается здесь, руками не задаётся. `idle` («данных нет — норма стенда»)
// серый и в счёт отказов не идёт (допущение 8 хендоффа). Фильтры складываются по «И»: поиск → состояние → группа;
// счётчики на пинах групп учитывают поиск и состояние.
import { findByPath } from '@/lib/nav'
import { dm as dmShared } from '@/lib/salesFormat'

export const plural = (n, a, b, c) => {
  const m = n % 10, h = n % 100
  return `${n} ${h >= 11 && h <= 14 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c}`
}

export const TONE_DOT = { ok: 'var(--income)', warn: 'var(--warning)', bad: 'var(--danger)', idle: 'var(--text-faint)' }
const RANK = { ok: 0, idle: 1, warn: 2, bad: 3 }
export const worst = (rows) => rows.reduce((w, c) => (RANK[c.tone] > RANK[w] ? c.tone : w), 'ok')
export const needsAttention = (c) => c.tone === 'bad' || c.tone === 'warn'

/** Подпись плашки состояния. Жёлтый у ключей — «истекает», у ненастроенной связи — «не настроено», прочее — «внимание». */
export function stateLabel(c) {
  if (c.running) return 'выполняется'
  if (c.tone === 'ok') return 'в норме'
  if (c.tone === 'bad') return 'отказ'
  if (c.tone === 'idle') return 'нет данных'
  if (c.gkey === 'keys') return 'истекает'
  return c.keys && c.keys.length ? 'не настроено' : 'внимание'
}

/** Детали — последствие, если оно есть (у warn/bad), вторая строка Mono — то, что было фактом. */
export const detailsOf = (c) => ({
  det: c.consequence || c.note || '',
  keyLine: c.consequence ? (c.note || (c.keys || []).join(', ')) : '',
})

export function sectionSum(rows) {
  const b = rows.filter(c => c.tone === 'bad').length, w = rows.filter(c => c.tone === 'warn').length
  if (!b && !w) return { text: `всё в норме · ${rows.length}`, tone: 'ok' }
  const wl = stateLabel(rows.find(c => c.tone === 'warn') || { tone: 'warn' })
  return { text: [b && `${b} из ${rows.length} · отказ`, w && `${w} из ${rows.length} · ${wl}`].filter(Boolean).join(' · '),
    tone: b ? 'bad' : 'warn' }
}

const hit = (ql) => (c) => !ql || [c.title, c.value, c.note, c.consequence, (c.keys || []).join(' ')]
  .filter(Boolean).join(' ').toLowerCase().includes(ql)

export function verdictOf(checks) {
  const b = checks.filter(c => c.tone === 'bad').length, w = checks.filter(c => c.tone === 'warn').length
  const tone = b ? 'bad' : w ? 'warn' : 'ok'
  const label = tone === 'ok' ? 'всё в норме'
    : [b && plural(b, 'отказ', 'отказа', 'отказов'), w && plural(w, 'предупреждение', 'предупреждения', 'предупреждений')]
      .filter(Boolean).join(' · ')
  return { tone, label }
}

/** Проверки, которых на экране пока нет (хендофф). Строку «Расхождение с Битриксом» не берём: Битрикс больше не источник. */
export const CANDIDATES = [
  ['Целостность связок', 'Контрагенты без юрлица, договоры без контрагента, стадии без слоя денег — одним числом', 'справочники · stage_catalog'],
  ['Очередь уведомлений', 'Сколько уведомлений ждёт отправки и сколько провалилось', 'notifications'],
  ['Свежесть статистики площадок', 'Дата последнего замера по каждой поверхности: если факт вчерашний, недокрут на экранах трафика врёт', 'publisher_traffic'],
  ['Медленные запросы', 'Топ-5 самых долгих запросов за сутки', 'pg_stat_statements'],
  ['Последний успешный бэкап', 'Дата, размер и результат тестового восстановления, а не факт наличия каталога', 'каталог бэкапов · шаг 2'],
]

/**
 * Секции таблицы: [{ key, title, hint, tone, sum, sumTone, rows, cand? }].
 * «Требует внимания» — первой и только в общем виде (без фильтра состояния и группы); её строки тогда в своих группах
 * не дублируются. «Чем дополнить» — последней, только без фильтров.
 */
export function buildView(checks, groups, f) {
  const ql = (f.q || '').trim().toLowerCase()
  const base = checks.filter(hit(ql))
  const byTone = (c) => f.tone === 'all' || (f.tone === 'bad') === needsAttention(c)
  const inTone = base.filter(byTone)
  const list = inTone.filter(c => f.group === 'all' || c.gkey === f.group)
  const HINT = { services: 'отвечают ли', external: 'настроены ли ключи и когда был обмен',
    keys: 'сколько осталось до истечения · жёлтый порог 14 дней, красный 3', jobs: 'когда отработали в последний раз' }

  const sections = []
  const attn = list.filter(needsAttention).sort((a, b) => RANK[b.tone] - RANK[a.tone])
  const pinTop = f.tone === 'all' && f.group === 'all' && attn.length > 0
  if (pinTop) sections.push({ key: 'attn', title: 'Требует внимания', hint: 'что сломано и к чему это приведёт', tone: worst(attn),
    sum: `${attn.length} из ${checks.length}`, sumTone: 'plain', rows: attn })
  groups.forEach(g => {
    const all = checks.filter(c => c.gkey === g.key)
    const rows = list.filter(c => c.gkey === g.key && !(pinTop && needsAttention(c)))
    if (!rows.length) return
    const s = sectionSum(all)
    sections.push({ key: g.key, title: g.label, hint: HINT[g.key] || '', tone: worst(all), sum: s.text, sumTone: s.tone, rows })
  })
  const cand = CANDIDATES.filter(c => !ql || c.join(' ').toLowerCase().includes(ql))
  if (f.tone === 'all' && f.group === 'all' && cand.length) sections.push({ key: 'cand', cand: true, title: 'Чем дополнить',
    hint: 'проверки, которых на экране пока нет — считаются из того, что уже есть в базе', tone: 'none',
    sum: plural(cand.length, 'кандидат', 'кандидата', 'кандидатов'), sumTone: 'plain', rows: cand })

  const groupPins = groups.map(g => {
    const all = checks.filter(c => c.gkey === g.key)
    return { key: g.key, label: g.label, n: inTone.filter(c => c.gkey === g.key).length, tone: worst(all), title: sectionSum(all).text }
  })
  return {
    sections, empty: list.length === 0, groupPins, inToneN: inTone.length,
    tones: [['all', 'Все', base.length], ['bad', 'Требует внимания', base.filter(needsAttention).length],
      ['ok', 'В норме', base.filter(c => !needsAttention(c)).length]],
  }
}

/** История строки: 14 квадратов, «N из M в норме», текст сбоя. Дни без данных — серые, в счёт не идут. */
export function historyOf(c) {
  const hist = c.hist || []
  const known = hist.filter(h => h.tone)
  const fails = known.filter(h => h.tone === 'bad' || h.tone === 'warn').length
  const okN = known.length - fails
  const dm = (iso) => dmShared(iso, '')
  const word = { ok: 'норма', idle: 'нет данных · норма стенда', warn: 'предупреждение', bad: 'отказ' }
  return {
    cap: 'Последние 14 дней',          // и у заданий — худшее за день: журнала прогонов по ним одного на всех нет
    squares: hist.map(h => ({ tone: h.tone, t: `${dm(h.day)} · ${h.tone ? word[h.tone] : 'данных нет'}` })),
    from: dm(hist[0]?.day),
    sum: known.length ? `${okN} из ${known.length} в норме` : 'данных пока нет',
    errCap: fails ? (c.tone === 'ok' || c.tone === 'idle' ? 'Последний сбой' : 'Что происходит') : 'Сбои',
    err: fails ? (c.last_failure || detailsOf(c).det || c.value) : (known.length ? `Сбоев за ${known.length === 14 ? '14 дней' : plural(known.length, 'день', 'дня', 'дней')} не было` : 'История копится с первого фонового прогона'),
    errOn: !!fails,
  }
}

/** Подпись страницы для «Онлайн сейчас» — из карты навигации; настройки и прочее вне карты — по разделу. */
export function pageLabel(path) {
  const p = (path || '').split('?')[0]
  const hitNav = findByPath(p)
  if (hitNav) return hitNav.item.label
  if (p.startsWith('/settings')) return 'Настройки'
  if (p.startsWith('/directory')) return 'Справочники'
  return p || '—'
}

export const initials = (name) => (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase()

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
/** «конец января» — когда наступит жёлтый порог, если рост продолжится. */
export function whenLabel(weeks, today = new Date()) {
  const d = new Date(today.getTime() + weeks * 7 * 864e5)
  const part = d.getDate() <= 10 ? 'начало' : d.getDate() <= 20 ? 'середина' : 'конец'
  return `${part} ${MONTHS[d.getMonth()]}`
}

export const fmtGb = (x) => (Math.round(x * 10) / 10).toString().replace('.', ',')
