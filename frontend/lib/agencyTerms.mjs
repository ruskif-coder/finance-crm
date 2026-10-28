// «Агентские условия» (владелец 27.10.2026, docs/СХЕМА_СК.md): подписи правил и периоды. Подбор правила и расчёт —
// на сервере (`app/agency_terms`); здесь только то, что экран показывает. Тест — lib/agencyTerms.test.mjs.

export const FEATURES = [['contract_id', 'договор'], ['agency_id', 'агентство'], ['advertiser_id', 'рекламодатель'],
  ['brand_id', 'бренд'], ['service_id', 'услуга']]
export const MODES = ['постоплата', 'скидка в счёт']

const dmy = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || '')); return m ? `${m[3]}.${m[2]}.${m[1]}` : '' }
const pctText = (v) => (v == null ? '—' : `${String(v).replace('.', ',')} %`)

/** Точность правила — сколько признаков задано (чем больше, тем правило главнее). */
export const specificity = (r) => FEATURES.filter(([k]) => r[k] != null).length

/** «постоплата 10 % · с 01.01.2026 по 31.12.2026». */
export function ruleLabel(r) {
  const period = `с ${dmy(r.valid_from)}${r.valid_to ? ` по ${dmy(r.valid_to)}` : ''}`
  return `${r.mode} ${pctText(r.percent)} · ${period}`
}

/** Признаки правила словами: «бренд Нурофен · услуга еФарм». `names` — {agency_id: {id: имя}, …}; `skip` — уже видимые. */
export function featureText(r, names, skip = []) {
  return FEATURES.filter(([k]) => r[k] != null && !skip.includes(k))
    .map(([k, label]) => `${label} ${(names[k] || {})[r[k]] || `№${r[k]}`}`).join(' · ')
}

/** Действует ли правило в день `iso` (ГГГГ-ММ-ДД). */
export const isActive = (r, iso) => r.valid_from <= iso && (!r.valid_to || iso <= r.valid_to)

/** Месяцы и кварталы для выбора периода расчёта: последние `n` месяцев от `ym` и их кварталы, новые сверху. */
export function periodOptions(ym, n = 12) {
  let [y, m] = ym.split('-').map(Number)
  const months = [], quarters = []
  for (let i = 0; i < n; i++) {
    months.push(`${y}-${String(m).padStart(2, '0')}`)
    const q = `${y}-Q${Math.floor((m - 1) / 3) + 1}`
    if (!quarters.includes(q)) quarters.push(q)
    m -= 1
    if (!m) { m = 12; y -= 1 }
  }
  return { months, quarters }
}

const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
/** «2026-10» → «октябрь 2026», «2026-Q4» → «4 квартал 2026». */
export function periodLabel(p) {
  const q = /^(\d{4})-Q([1-4])$/.exec(p || '')
  if (q) return `${q[2]} квартал ${q[1]}`
  const m = /^(\d{4})-(\d{2})$/.exec(p || '')
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : '—'
}

/** Ввод процента: «12,5» → 12.5; пусто или мусор — null. */
export function parsePct(s) {
  const t = String(s ?? '').trim().replace(',', '.')
  if (!t || !/^\d+(\.\d+)?$/.test(t)) return null
  const v = Number(t)
  return v >= 0 && v <= 100 ? v : null
}

/** Имена по id из справочников `options`: {agency_id: {id: имя}, …}. */
export function namesOf(o) {
  const by = (list, f = (x) => x.name) => Object.fromEntries((list || []).map((x) => [x.id, f(x)]))
  return {
    agency_id: by(o.agencies), advertiser_id: by(o.advertisers), brand_id: by(o.brands), service_id: by(o.services),
    contract_id: by(o.contracts, (c) => `${c.number || 'без номера'}${c.date ? ` от ${dmy(c.date)}` : ''}`),
    recipient_id: by(o.counterparties),
  }
}

// ── вкладки «Агентства» / «Рекламодатели» по хендоффу 27.10.2026: плоская таблица «договор × правило» ─────────────

/** Состояние срока правила на день `iso`: null — действует, иначе «срок вышел» / «ещё не начало». */
export const inactiveLabel = (r, iso) => (iso < r.valid_from ? 'ещё не начало' : r.valid_to && iso > r.valid_to ? 'срок вышел' : null)

/** Дерево сервера → строки: одна на правило, договор без правила — одна строка без правила. Шапка группы — в первой строке. */
export function flattenSide(items, iso) {
  const rows = []
  for (const o of items) {
    const contracts = o.entities.reduce((a, e) => a + e.contracts.length, 0)
    let first = true
    for (const e of o.entities) {
      for (const c of e.contracts) {
        const base = { ownerId: o.id, owner: o.name, ownerSub: `юрлиц ${o.entities.length} · договоров ${contracts}`,
          entity: e.name, contractId: c.id }
        const list = c.rules.length ? c.rules : [null]
        for (const r of list) {
          rows.push({ ...base, first, rule: r, inactive: r ? inactiveLabel(r, iso) : null, key: `${o.id}:${c.id}:${r ? r.id : 'none'}` })
          first = false
        }
      }
    }
  }
  return rows
}

export function sideKpi(items, rows) {
  const ruled = rows.filter((r) => r.rule)
  const live = ruled.filter((r) => !r.inactive)
  return {
    owners: items.length,
    entities: items.reduce((a, o) => a + o.entities.length, 0),
    contracts: items.reduce((a, o) => a + o.entities.reduce((b, e) => b + e.contracts.length, 0), 0),
    noRule: rows.filter((r) => !r.rule).length,
    active: live.length,
    post: live.filter((r) => r.rule.mode === MODES[0]).length,
    disc: live.filter((r) => r.rule.mode === MODES[1]).length,
    inactive: ruled.length - live.length,
  }
}

export const SIDE_FILTERS = [['all', 'все'], ['empty', 'без условия'], [MODES[0], 'постоплата'], [MODES[1], 'скидка в счёт']]

/** Фильтр чипом и поиском (агентство, юрлицо, договор), затем порядок: без условия сверху, дальше по имени. */
export function filterSide(rows, { q = '', mode = 'all', contractName = (id) => '' } = {}) {
  const s = q.trim().toLowerCase()
  const pass = (r) => (mode === 'all' || (mode === 'empty' ? !r.rule : mode === 'inactive' ? !!(r.rule && r.inactive)
    : r.rule && r.rule.mode === mode))
    && (!s || [r.owner, r.entity, contractName(r.contractId)].some((x) => String(x || '').toLowerCase().includes(s)))
  const out = rows.filter(pass)
  const groups = new Map()
  for (const r of out) {
    const g = groups.get(r.ownerId) || { name: r.owner, empty: false, rows: [] }
    g.empty = g.empty || !r.rule
    g.rows.push(r)
    groups.set(r.ownerId, g)
  }
  return [...groups.values()]
    .sort((a, b) => (a.empty === b.empty ? String(a.name).localeCompare(String(b.name), 'ru') : a.empty ? -1 : 1))
    .flatMap((g) => g.rows.sort((a, b) => (!!a.rule === !!b.rule ? 0 : a.rule ? 1 : -1)).map((r, i) => ({ ...r, first: i === 0 })))
}

/** Точность квадратами: 4 ячейки, заполнено — число признаков (больше 4 — все четыре). */
export const precisionCells = (r) => { const n = Math.min(4, specificity(r)); return [0, 1, 2, 3].map((i) => i < n) }

// ── расчёт: группировка «по агентству» / «по мастер-сделке» ──────────────────────────────────────────────────

const sum = (xs, f) => Math.round(xs.reduce((a, x) => a + (f(x) || 0), 0) * 100) / 100

/** Строки сделок → строки таблицы: агентство (итоги) → [пакет (итоги, договор)] → сделки. `by` — 'agency' | 'pack'. */
export function groupCalc(rows, by) {
  const out = []
  const bySide = new Map()
  for (const r of rows) {
    if (!bySide.has(r.side)) bySide.set(r.side, [])
    bySide.get(r.side).push(r)
  }
  for (const side of [...bySide.keys()].sort((a, b) => a.localeCompare(b, 'ru'))) {
    const ds = bySide.get(side)
    const packs = [...new Set(ds.map((d) => d.master_code || '—'))]
    out.push({ type: 'side', key: `s:${side}`, name: side, deals: ds.length, packs: packs.length,
      base: sum(ds, (d) => d.base_net), sk: sum(ds, (d) => d.main.amount) })
    if (by === 'pack') {
      for (const p of packs.sort()) {
        const pd = ds.filter((d) => (d.master_code || '—') === p)
        out.push({ type: 'pack', key: `p:${side}:${p}`, code: p, contract: `${pd[0].contract} · ${pd[0].entity}`, deals: pd.length,
          base: sum(pd, (d) => d.base_net), sk: sum(pd, (d) => d.main.amount) })
        pd.forEach((d) => out.push({ type: 'deal', key: `d:${d.deal_id}:${d.period}`, d, inPack: true }))
      }
    } else {
      ds.forEach((d) => out.push({ type: 'deal', key: `d:${d.deal_id}:${d.period}`, d, inPack: false }))
    }
  }
  return out
}

// ── «Условия работы»: какие показать под брифом медиаплана (владелец 27.10.2026) ─────────────────────────────────

/** Условия, подходящие брифу: заданные признаки совпадают, период МП внутри срока. Все совпавшие, точные выше.
    `ctx` — {agency_id, advertiser_id, brand_id, services: [названия позиций строк], period: 'ГГГГ-ММ'}. Условие на договор
    в МП не показывается: договор закрытия на этом этапе обычно не выбран. */
export function matchWork(terms, ctx) {
  const ym = ctx.period || ''
  const inTerm = (t) => !ym || ((t.valid_from || '').slice(0, 7) <= ym && (!t.valid_to || t.valid_to.slice(0, 7) >= ym))
  const same = (a, b) => a != null && b != null && String(a) === String(b)
  const svc = new Set((ctx.services || []).map((s) => String(s).trim().toLowerCase()))
  const fits = (t) => t.contract_id == null
    && (t.agency_id == null || same(t.agency_id, ctx.agency_id))
    && (t.advertiser_id == null || same(t.advertiser_id, ctx.advertiser_id))
    && (t.brand_id == null || same(t.brand_id, ctx.brand_id))
    && (t.service_id == null || svc.has(String(t.names?.service || '').trim().toLowerCase()))
  return terms.filter((t) => inTerm(t) && fits(t)).sort((a, b) => specificity(b) - specificity(a) || a.id - b.id)
}

// «Расчёт» (владелец 27.10.2026): почему у сделки нет СК — подсветить строку и сказать, что делать. Строка расчёта несёт способ
// в `main`, строка «не закрыты» — в себе. Без договора закрытия правило не заводим — ждём договор.
export function skGap(row) {
  const mode = row.main ? row.main.mode : row.mode
  if (mode) return null
  return row.contract_id ? { kind: 'no_terms', label: 'нет условия к договору' } : { kind: 'no_contract', label: 'нет договора закрытия' }
}

export function newRuleFor(row) {
  if (!row.contract_id) return null
  return row.agency_id ? { kind: 'основная', contract_id: row.contract_id, agency_id: row.agency_id }
    : { kind: 'основная', contract_id: row.contract_id, advertiser_id: row.advertiser_id }
}

// Срок условия работы для карточки плашки в МП: «01.01.2026 – 31.12.2026», «с …», «по …»; не задан — пусто
export const workPeriod = (t) => (t.valid_from && t.valid_to ? `${dmy(t.valid_from)} – ${dmy(t.valid_to)}`
  : t.valid_from ? `с ${dmy(t.valid_from)}` : t.valid_to ? `по ${dmy(t.valid_to)}` : '')

// Креативы / отчёты бонусом у условия работы (владелец 27.10.2026): одни подписи для списка «Условия работы» и плашки в МП
const BONUS = [['creatives', 'Креативы бонусом'], ['reports', 'Отчёты бонусом']]
export const workBonuses = (t) => BONUS.filter(([k]) => t[`${k}_bonus`]).map(([key, label]) => ({ key, label, note: t[`${key}_bonus_note`] || '' }))

// Периоды вкладок «Расчёт» и «Спец. условия»: три последних месяца (текущий — с годом) и квартал текущего месяца
export function calcPeriods(ym) {
  const { months } = periodOptions(ym, 3)
  const q = `${months[0].slice(0, 4)}-Q${Math.floor((Number(months[0].slice(5, 7)) - 1) / 3) + 1}`
  const periods = [...[...months].reverse().map((m, i) => [m, i === months.length - 1 ? periodLabel(m) : periodLabel(m).split(' ')[0]]), [q, periodLabel(q)]]
  return { periods, initial: months[0] }
}

// «Действует с» нового правила / условия по умолчанию — 1 января текущего года
export const defaultValidFrom = (iso) => `${iso.slice(0, 4)}-01-01`
