/**
 * Маппер «наши данные → контракт компонента DealCard».
 *
 * Компонент вставлен из хендоффа дословно и ждёт форму DEMO (см. DealCard.jsx). Держать
 * преобразование отдельно от него — чтобы обновление дизайна не задевало логику, а
 * изменение наших полей не задевало вёрстку.
 *
 * Креативы и сверка пока отдаются демо-данными хендоффа: владелец решил 26.08.2026
 * показать вёрстку целиком, наполнение делаем позже. Демо помечено в docs/rec ниже,
 * чтобы его нельзя было принять за настоящие цифры.
 *
 * Чистая функция без запросов: получает то, что уже есть на странице
 * (frontend/pages/sales/deals/[id].js уже грузит deal/mp/lines/phases/ordSummary),
 * отдаёт готовый объект для <DealCard deal={...} />.
 */
import { DEMO } from './DealCard'
import { DEAL_DOCS } from '../../lib/dealDocs'

const VAT = 0.22

const dec = (v) => v.toFixed(2).replace('.', ',')
const initials = (name) => (name ? name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() : '—')
// дд.мм — для «Период РК» в свёрнутой сводке медиаплана (без года, как в хендоффе)
const ddmm = (iso) => { const s = String(iso || '').slice(0, 10); if (!s) return ''; const [, m, d] = s.split('-'); return d && m ? `${d}.${m}` : '' }
// дд.мм.гггг — для меты доходного договора («от 01.08.2023»)
const ddmmyyyy = (iso) => { const s = String(iso || '').slice(0, 10); if (!s) return ''; const [y, m, d] = s.split('-'); return d && m && y ? `${d}.${m}.${y}` : '' }
// «7 вариантов» / «1 вариант» / «2 варианта» — простая русская плюрализация
const variants = (n) => {
  const mod10 = n % 10, mod100 = n % 100
  const word = (mod10 === 1 && mod100 !== 11) ? 'вариант' : (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) ? 'варианта' : 'вариантов'
  return `${n} ${word}`
}

/**
 * Ступени ОРД в форму хендоффа. Наш ответ /ord/deal/{id}/assembly даёт payer/final/
 * initial/creatives с полями {ok, reason, ...}; компонент ждёт массив из четырёх
 * {label, state, value, briefValue, meta, hint, fill, action, canAdd, canOpen, openTitle}.
 *
 * state: done — наш ok; todo — ждёт человека; lock — ещё не открыта (условия те же,
 * что в components/ord/AssemblyOrd.js, который эта карточка заменяет).
 * hint — наш reason буквально: это и есть обоснование подстановки.
 */
function mapOrd(a) {
  if (!a) {
    const wait = { state: 'lock', value: 'загрузка…', briefValue: 'загрузка…', hint: '' }
    return [
      { label: 'Плательщик', ...wait }, { label: 'Доходный договор', ...wait },
      { label: 'Изначальный договор', ...wait }, { label: 'Креативы и ЕРИД', ...wait },
    ]
  }
  const { payer, final, initial, creatives } = a
  const payerState = payer.ok ? 'done' : 'todo'
  const finalState = final.ok ? 'done' : (payer.ok ? 'todo' : 'lock')
  const initialState = initial.ok ? 'done' : (final.ok ? 'todo' : 'lock')
  const chosen = initial.bound || initial.proposal
  const candN = (initial.candidates || []).length

  return [
    {
      label: 'Плательщик', state: payerState,
      value: payer.ok ? (payer.name || 'без названия') : 'не определён',
      briefValue: payer.ok ? (payer.name || 'без названия') : 'не определён',
      hint: payer.reason || '',
      canOpen: !!payer.counterparty_id, openTitle: 'Открыть карточку контрагента',
    },
    {
      label: 'Доходный договор', state: finalState,
      value: final.ok ? (final.contract.number || 'без номера') : 'не найден',
      briefValue: final.ok ? (final.contract.number || 'без номера') : 'не найден',
      meta: (final.ok && final.contract.date) ? `от ${ddmmyyyy(final.contract.date)}` : undefined,
      hint: final.reason || '',
      fill: final.fill || undefined,
      canAdd: true, canOpen: final.ok, openTitle: 'Открыть договор в реестре',
    },
    {
      label: 'Изначальный договор', state: initialState,
      value: chosen ? (chosen.number || 'без номера') : 'не выбран',
      briefValue: initial.bound ? (chosen.number || 'без номера') : (candN ? `выбрать из ${candN}` : 'нет вариантов'),
      meta: (!initial.bound && candN) ? variants(candN) : undefined,
      hint: initial.reason || '',
      fill: initial.fill || undefined,
      // Кнопка выбора — только пока не привязано (как в DEMO хендоффа). После привязки
      // сменить выбор с этой карточки нечем: у компонента нет второй кнопки под это
      // (см. отчёт по задаче — canOpen ведёт в реестр, не в поповер выбора).
      action: (!initial.bound && candN) ? `Выбрать из ${candN}` : undefined,
      canAdd: true, canOpen: !!initial.bound, openTitle: 'Показать подходящие договоры',
    },
    {
      label: 'Креативы и ЕРИД', state: 'lock',
      value: 'ждёт цепочку', briefValue: 'не выпущен',
      hint: (creatives && creatives.reason) || '',
    },
  ]
}

/** Документы — наш набор (владелец решил 26.08.2026: оставить, не хендоффа девять). */
function mapDocs(d, mp, canEdit) {
  const fileBy = Object.fromEntries((d.files || []).map(f => [f.kind, f]))
  const mpDoc = {
    label: 'Медиаплан',
    note: mp ? `v${mp.version}` : 'не создан',
    ready: !!mp,
    tags: mp ? ['PDF', 'XLS'] : undefined,
  }
  const rest = DEAL_DOCS.map(({ kind, label, bx }) => {
    const f = fileBy[kind]
    const note = f
      ? `${f.filename}${f.size ? ' · ' + Math.max(1, Math.round(f.size / 1024)) + ' КБ' : ''}`
      : (bx ? 'из Битрикса — нет' : 'не загружен')
    // bx (Договор/МП) грузится только синком, ручной загрузки для них нет — как на
    // прежней карточке (frontend/lib/dealDocs.js).
    const action = (!f && !bx && canEdit) ? ((kind === 'invoice' || kind === 'upd') ? 'Создать' : 'Загрузить') : undefined
    return { label, note, ready: !!f, action }
  })
  return [mpDoc, ...rest]
}

/** Ответственные: продавец, аккаунт, трафик — не назначен показывается буквально этой
 * строкой (DealCard.jsx красит имя по сравнению с 'не назначен', см. компонент). */
function mapOwners(d) {
  return [
    { name: d.sales_rep || 'не назначен', role: 'продавец',
      initials: d.sales_rep ? initials(d.sales_rep) : '—', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
    { name: d.account_manager || 'не назначен', role: 'аккаунт',
      initials: d.account_manager ? initials(d.account_manager) : '—', bg: 'var(--income-tint)', fg: 'var(--income-fg)' },
    { name: d.traffic_manager || 'не назначен', role: 'трафик',
      initials: d.traffic_manager ? initials(d.traffic_manager) : '—', bg: 'var(--bg-subtle)', fg: 'var(--text-disabled)' },
  ]
}

/**
 * @param deal          — ответ GET /sales/deals/{id} (то, что страница уже держит в `d`)
 * @param mp             — последний медиаплан сделки (полные данные) либо null
 * @param lines           — строки размещения, уже посчитанные на странице (position/format/
 *                          model/volume/unit/discount/net/freq/reach/clicks)
 * @param tImp            — суммарные ПОКАЗЫ по строкам — для «Показы по прогнозу».
 *                        Не объём: у Фикса и Пакета в объёме лежат штуки закупки.
 * @param net             — сумма сделки до НДС (deal-level, с доп.услугами) — уже посчитана
 * @param chain           — цепочка стадий нашего каталога (phases.flatMap(...) на странице)
 * @param curIdx          — индекс текущей стадии сделки в chain (-1 — не нашлась/сорвалась)
 * @param ordAssembly     — ответ GET /ord/deal/{id}/assembly либо null (ещё грузится)
 * @param canEdit         — есть ли право sales_registry.edit у текущего пользователя
 */
export function toDealCardData({ deal: d, mp, lines, tImp, net, chain, curIdx, ordAssembly, canEdit }) {
  const title = [d.advertiser, d.brand].filter(Boolean).join(' · ') || d.title || '—'
  // Мета шапки — ровно «агентство · услуга · период» (README раздел 2), уже без
  // продавца/аккаунта: у них теперь своя строка «Ответственные» в правой колонке.
  const headMeta = [d.agency, d.product, d.period].filter(Boolean).join(' · ')

  const start = d.period_from ? String(d.period_from).slice(0, 10) : ''
  const end = d.period_to ? String(d.period_to).slice(0, 10) : ''
  const flight = (start && end) ? `${ddmm(start)} — ${ddmm(end)}` : '—'

  // Прогноз считается от ПОКАЗОВ (`l.imp`), а не от объёма строки: у Фикса и Пакета
  // объём это штуки закупки, и CPM от них получался в миллионы рублей. Показы приходят
  // из ручного ввода аккаунта, у CPM совпадают с объёмом (lib/mpRow).
  const forecast = (lines || []).map(l => {
    const imp = l.imp || 0
    const reach = l.freq > 0 ? Math.round(imp / l.freq) : 0
    const clicks = Math.round(l.clicks || 0)
    const cpm = imp ? (l.net / imp * 1000) : 0
    const cpc = l.clicks ? (l.net / l.clicks) : 0
    const cpu = reach ? (l.net / reach) : 0
    return {
      name: l.position,
      freq: l.freq ? String(l.freq) : '—',
      reach, imp, clicks,
      ctr: (imp && l.clicks) ? dec(l.clicks / imp * 100) + ' %' : '—',
      cpm: imp ? dec(cpm) + ' ₽' : '—',
      cpc: l.clicks ? dec(cpc) + ' ₽' : '—',
      cpu: reach ? dec(cpu) + ' ₽' : '—',
    }
  })

  return {
    head: {
      id: d.code || d.bitrix_id || d.id,
      title,
      meta: headMeta,
      // curIdx=-1, пока каталог стадий не загрузился или сделка в терминальной стадии
      // (сорвалась/не случилась — у хендоффа такого состояния нет вовсе, см. отчёт).
      // Зажимаем в 0, чтобы полоса стадий не разъехалась на отрицательном индексе.
      stageIndex: Math.max(0, curIdx),
      // Нигде не считается сегодня (см. отчёт по задаче) — компонент не умеет прятать
      // фразу условно, поэтому «в стадии N дней» останется с пустым местом вместо числа.
      daysInStage: undefined,
    },
    // Пусто, пока phases не подгрузились — тогда деал.stages||STAGES_FALLBACK в
    // компоненте обязан упасть на запасной список (не отправляем сюда [], это truthy).
    stages: (chain && chain.length) ? chain.map(s => s.name) : undefined,
    plan: {
      linked: !!d.year_plan_line_id,
      name: d.year_plan ? (d.year_plan.title || `План ${d.year_plan.year || ''}`) : '',
      note: d.year_plan
        ? [d.year_plan.comment, d.year_plan.month != null ? `мес. ${d.year_plan.month + 1}` : null].filter(Boolean).join(' · ')
        : '',
    },
    mp: {
      // Точка расчёта НДС в компоненте — mp.net (см. DealCard.jsx money[]); передаём
      // сумму сделки уровня страницы (с доп.услугами), а не только сумму строк
      // размещения — README требует, чтобы шапка была единой точкой расчёта.
      net: net != null ? Math.round(net) : 0,
      version: mp ? `v${mp.version}` : '—',
      service: d.product || '—',
      period: d.period || '—',
      flight, start, end,
      impressions: tImp || 0,
      params: [
        ['Агентство', d.agency || '—'], ['Рекламодатель', d.advertiser || '—'], ['Бренд', d.brand || '—'],
        ['Контрагент', d.payer || '—'], ['Период размещения', d.period ? `месяц · ${d.period}` : '—'], ['Гео', '—'],
      ],
      lines: (lines || []).map(l => ({
        position: l.position, format: l.format, model: l.model, volume: l.volume,
        unit: l.unit, discount: Math.round((l.discount || 0) * 100), net: l.net,
      })),
      forecast,
    },
    ord: mapOrd(ordAssembly),
    // Демо хендоффа как есть — решение владельца 26.08.2026 (см. докстринг файла).
    creatives: DEMO.creatives,
    rec: DEMO.rec,
    docs: mapDocs(d, mp, canEdit),
    owners: mapOwners(d),
  }
}
