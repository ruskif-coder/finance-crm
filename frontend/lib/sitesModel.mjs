// Таблица площадок в расхлопе РК, дашборд трафика v2 (хендофф design_handoff_traffic_expand_v2, раздел 8).
// Здесь только раскладка: группы «по вниманию», сортировка по столбцу, итоги групп, сводка по креативу.
// Числа приходят ПОСЧИТАННЫМИ с сервера (`app/ad/flight.py`, `app/ad/pace.py`, `app/traffic/expand_view.py`):
// недокрут — от прогноза, темп — по последним суткам с порогами 0,9 / 1,1, расхождение с WR — с пределом
// из цели сделки. Пороги макета (0,85 / 0,95 / 5 и 10 %) не вводим — решение владельца 17.11.2026.
// Модуль без импортов: его гоняет `node --test` (lib/sitesModel.test.mjs, входит в `npm run test-rk`).

/** Темп, который отставанием не считается. Всё прочее из `app/ad/pace.py` (UNDER) — отставание. */
export const PACE_FINE = ['в темпе', 'перебор']

/** Группы «порядок: внимание» — в порядке показа. Пустая группа не показывается, группы не сворачиваются. */
export const GROUPS = [
  { key: 'act', title: 'Требуют действия', dot: 'var(--warning)', hint: 'Креатив у площадки или код на площадке не наш — запуск руками' },
  { key: 'lag', title: 'Отстают', dot: 'var(--warning)', hint: 'Темп последних суток ниже нужного (меньше 90 % нужного в день)' },
  { key: 'ok', title: 'В темпе', dot: 'var(--income)', hint: '' },
  { key: 'over', title: 'План выбран', dot: 'var(--accent)', hint: 'Факт не меньше плана площадки — объём можно перераспределить' },
]

/**
 * Группа площадки. Порядок проверок — приоритет: «требуют действия» сильнее всего, затем «план выбран»
 * (у выбравшей план темп уже ничего не значит), затем «отстают» по темпу с сервера.
 */
export function groupOf(p) {
  if (p.status === 'у площадки' || p.ext_mode === 'external') return 'act'
  if (p.plan_show && p.fact_shows != null && p.fact_shows >= p.plan_show) return 'over'
  if (p.pace && p.fact_shows != null && !PACE_FINE.includes(p.pace.status)) return 'lag'
  return 'ok'
}

/** Цель РК по CTR, % — из `goals.ctr` медиаплана. Там свободный ввод («0,8», «от 0,8 %»): берём первое число. */
export function goalCtr(goals) {
  const m = String(goals?.ctr ?? '').match(/\d+(?:[.,]\d+)?/)
  const v = m ? Number(m[0].replace(',', '.')) : NaN
  return Number.isFinite(v) && v > 0 ? v : null
}

/** Тон CTR против цели РК: good — не ниже цели; low — ниже 0,75 цели; mid — между; none — CTR нет. Без цели — mid. */
export function ctrTone(ctr, goal) {
  if (ctr == null) return 'none'
  if (!goal) return 'mid'
  if (ctr >= goal) return 'good'
  if (ctr < goal * 0.75) return 'low'
  return 'mid'
}

/* ── системы Е · W · D · С ─────────────────────────────────────────────────── */

const SCREEN_TONE = { all: 'ok', part: 'wait' }

/**
 * Четыре системы площадки — те же расчёты и подсказки, что у букв-плашек на бою. `extTone` — `EXT_TONE`
 * из salesTableKit (передаётся снаружи, чтобы модуль оставался без импортов).
 */
export function systemsOf(p, extTone) {
  const wr = p.external?.weborama
  const dsp = p.external?.dsp
  const marks = [
    { l: 'Е', tone: SCREEN_TONE[p.erid?.state] || 'none',
      title: `ЕРИД: ${p.erid ? `${p.erid.got} из ${p.erid.total} креативов` : 'нет данных'}`
        + (p.erid?.state === 'part' ? ' — у части креативов ещё нет, их пиксель и выгрузка ждут' : '') },
    { l: 'W', tone: extTone[wr?.state] || 'none',
      title: `Weborama: ${wr?.state || 'нет данных'}${wr?.why ? ` — ${wr.why}` : ''}` },
    { l: 'D', tone: extTone[dsp?.state] || 'none',
      title: `DSP: ${dsp?.state || 'нет данных'}${dsp?.why ? ` — ${dsp.why}` : ''}` },
    { l: 'С', tone: SCREEN_TONE[p.screens?.state] || 'none',
      title: `Скрины запуска: ${p.screens ? `${p.screens.got} из ${p.screens.total} креативов` : 'нет данных'}`
        + ' — отметка в виде «по креативам»' },
  ]
  const missing = marks.filter(m => m.tone !== 'ok').map(m => m.l)
  const empty = marks.every(m => m.tone === 'none' || m.tone === 'off')
  return {
    marks, missing, empty,
    label: !missing.length ? 'ок' : empty ? '—' : `нет ${missing.join(' ')}`,
    title: marks.map(m => m.title).join('\n'),
  }
}

/**
 * Системы КРЕАТИВА в расхлопе площадки (владелец 17.11.2026): те же четыре буквы и тот же вид, что у площадки, но по
 * самому креативу. Е — ЕРИД креатива; D — заведён ли креатив в DSP (у внешней площадки — состояние площадки: креатив там
 * заводится вручную); С — отмечены ли скрины. W — у креатива своего состояния нет, это пиксель площадки — так и подписано.
 */
export function creativeSystemsOf(c, p, extTone) {
  const wr = p.external?.weborama
  const external = p.ext_mode === 'external'
  const dsp = external ? p.external?.dsp
    : { state: c.ms_creative_xxhash ? 'есть' : 'нет', why: c.ms_creative_xxhash ? '' : 'креатив в DSP не заведён' }
  const marks = [
    { l: 'Е', tone: c.erid ? 'ok' : 'none', title: c.erid ? `ЕРИД: ${c.erid}` : 'ЕРИД у креатива ещё нет' },
    { l: 'W', tone: extTone[wr?.state] || 'none',
      title: `Weborama (пиксель площадки): ${wr?.state || 'нет данных'}${wr?.why ? ` — ${wr.why}` : ''}` },
    { l: 'D', tone: extTone[dsp?.state] || 'none', title: `DSP: ${dsp?.state || 'нет данных'}${dsp?.why ? ` — ${dsp.why}` : ''}` },
    { l: 'С', tone: c.screens_done_at ? 'ok' : 'none',
      title: c.screens_done_at ? 'Скрины запуска сняты' : 'Скрины запуска не отмечены' },
  ]
  const missing = marks.filter(m => m.tone !== 'ok' && m.tone !== 'off').map(m => m.l)
  const empty = marks.every(m => m.tone === 'none' || m.tone === 'off')
  return { marks, missing, empty, label: !missing.length ? 'ок' : `нет ${missing.join(' ')}`, title: marks.map(m => m.title).join('\n') }
}

/* ── сортировка ────────────────────────────────────────────────────────────── */

// «Хуже» — большее число: при сортировке по умолчанию (dir = desc) худшие идут первыми (README 8.4).
const PACE_RANK = { 'нет трафика': 6, 'трафик есть, не открутили': 5, 'мало трафика': 4, 'недобор': 3, 'в темпе': 2, 'перебор': 1 }
const STATUS_RANK = { 'у площадки': 7, 'у трафика': 6, 'ждёт сборки': 5, 'ждёт запуска': 4, 'пауза': 3, 'запущен': 2, 'завершена': 1 }

const ratio = (a, b) => (a != null && b ? a / b : null)

/** Значение для сортировки по столбцу; `null` — в конец при любом направлении. */
export const SORT_VALUE = {
  name: p => String(p.domain || p.publisher || ''),
  cr: p => (p.creative_counts ? (p.creative_counts.live || 0) * 100 + (p.creative_counts.agreed || 0) * 10
    + (p.creative_counts.total || 0) : null),
  weight: p => (p.no_weight ? null : p.weight ?? null),
  share: p => p.share || null,
  plan: p => p.plan_show ?? null,
  fact: p => p.fact_shows ?? null,
  clk: p => p.fact_clicks ?? null,
  ctr: p => p.ctr ?? null,
  exec: p => ratio(p.fact_shows, p.plan_show),
  under: p => p.under ?? null,
  wr: p => (p.wr_mismatch?.pct == null ? null : Math.abs(p.wr_mismatch.pct)),
  pace: p => (p.pace ? (PACE_RANK[p.pace.status] || 0) + (p.pace.chronic ? 0.5 : 0) : null),
  status: p => STATUS_RANK[p.status] ?? 0,
  sys: p => p._sys?.missing.length ?? null,
}

/** Пункты «Порядок» — то же состояние, что заголовки. `attn` — группы. */
export const ORDERS = [
  ['attn', 'внимание', 'Группами: требуют действия, отстают, в темпе, план выбран'],
  ['weight', 'вес', 'По весу площадки, от большего'],
  ['under', 'недокрут', 'По недокруту, от большего'],
  ['wr', 'расх. WR', 'По расхождению с Weborama, от большего по модулю'],
]

/** Клик по заголовку: тот же столбец — переворот, другой — по умолчанию «хуже/больше первым». */
export function nextSort(cur, key) {
  if (key === 'attn') return { key: 'attn', dir: 'desc' }
  return cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }
}

/** Плоская сортировка. Имя — по алфавиту при desc (как в макете); пустые значения всегда в конце. */
export function sortRows(rows, key, dir) {
  const get = SORT_VALUE[key]
  if (!get) return [...rows]
  const sign = dir === 'asc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const va = get(a)
    const vb = get(b)
    if (va == null || vb == null) return va == null && vb == null ? 0 : va == null ? 1 : -1
    if (key === 'name') return sign * String(va).localeCompare(String(vb), 'ru')
    return sign * (vb - va)
  })
}

/* ── группы и итоги ────────────────────────────────────────────────────────── */

const sum = (rows, f) => rows.reduce((s, r) => s + (f(r) || 0), 0)

/** Итоги строки группы: доля, план, факт, клики, средний CTR (клики / показы), недокрут, «N > предел». */
export function groupTotals(rows) {
  const fact = sum(rows, r => r.fact_shows)
  const clicks = sum(rows, r => r.fact_clicks)
  const bad = rows.filter(r => r.wr_mismatch?.level === 'bad')
  const limits = [...new Set(bad.map(r => r.wr_mismatch.limit).filter(v => v != null))]
  return {
    n: rows.length,
    share: sum(rows, r => r.share),
    plan: sum(rows, r => r.plan_show),
    fact,
    clicks,
    ctr: fact ? Math.round(clicks / fact * 10000) / 100 : null,
    under: sum(rows, r => r.under),
    wrBad: bad.length,
    wrLimit: limits.length === 1 ? limits[0] : null,
  }
}

/** Группы «внимание»: пустые выкинуты, внутри — по недокруту от большего. */
export function groupRows(rows) {
  return GROUPS
    .map(g => {
      const rs = sortRows(rows.filter(r => groupOf(r) === g.key), 'under', 'desc')
      return { ...g, rows: rs, totals: groupTotals(rs) }
    })
    .filter(g => g.rows.length)
}

/**
 * Раскладка таблицы: при `attn` — группы, иначе одна безымянная группа (`key: 'flat'`) с плоской сортировкой.
 * `extTone` нужен сортировке «системы».
 */
export function layout(placements, sort, extTone) {
  const rows = (placements || []).map(p => ({ ...p, _sys: systemsOf(p, extTone || {}) }))
  if (sort.key === 'attn') return groupRows(rows)
  return [{ key: 'flat', title: '', rows: sortRows(rows, sort.key, sort.dir), totals: null }]
}

/* ── «площадки →» из пульта: без показов за последние сутки ────────────────── */

/**
 * Площадки в работе без показов за последние отчитанные сутки РК. Сутки — самый поздний `pace.day` по РК:
 * строки факта с нулём сервер не пишет (`app/dsp/stat_store.py`), поэтому площадка без показов в эти сутки
 * приходит с более ранним `pace.day` или без `pace` вовсе. Нет ни одного `pace` — судить не по чему: `null`.
 */
export function noShows(placements) {
  const days = (placements || []).map(p => p.pace?.day).filter(Boolean).sort()
  const day = days[days.length - 1]
  if (!day) return null
  const ids = (placements || [])
    .filter(p => p.status === 'запущен' && (!p.pace || p.pace.day < day || !p.pace.shows))
    .map(p => p.id)
  return { day, ids }
}

/* ── объём площадки против плана РК (владелец 27.09.2026) ─────────────────── */

const volOf = (vol, pid) => vol?.by_publisher?.[String(pid)]
export const volTint = (vol, pid) => {
  const l = volOf(vol, pid)?.level
  return l === 'over' ? 'var(--danger-tint)' : l === 'warn' ? 'var(--warning-tint)' : undefined
}
export const volTitle = (vol, pid) => {
  const v = volOf(vol, pid)
  if (!v || v.level === 'ok') return undefined
  return `На площадке заложено ${Math.round((v.share || 0) * 100)} % плана РК`
    + (v.level === 'over' ? ' — больше плана, запуск заблокирован' : '')
}

/* ── вид «по креативам» ────────────────────────────────────────────────────── */

/**
 * Результат креатива поверх групп `byCreative` (dashboardKit): факт и клики — суммы по его парам,
 * CTR — клики / показы (не среднее CTR пар). «лучший» — у максимального CTR, если креативов с показами
 * больше одного.
 */
export function creativeResults(groups) {
  const out = (groups || []).map(g => {
    const withFact = g.places.filter(c => c.fact != null)
    const fact = withFact.length ? sum(withFact, c => c.fact) : null
    const clicks = withFact.length ? sum(withFact, c => c.clicks) : null
    return { ...g, fact, clicks, ctr: fact ? Math.round(clicks / fact * 10000) / 100 : null }
  })
  const shown = out.filter(g => g.ctr != null)
  const best = shown.length > 1 ? Math.max(...shown.map(g => g.ctr)) : null
  return out.map(g => ({ ...g, best: !!best && g.ctr === best }))
}
