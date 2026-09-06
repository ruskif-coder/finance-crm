import { useState, useEffect, useMemo, Fragment, useCallback } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, card, CAP, btnSm, sel, inp, PIP, STAGE_ORDER, FILL, StageLayerBar,
         MultiDrop, GAP_FIELDS, IconBtn, PortalPopover, ROW_TONE, CTA_TONE, ctaStyle, UNVERIFIED_BORDER } from '@/components/salesTableKit'
import NotificationsWidget, { toItem } from '@/components/dashboard/NotificationsWidget'
import DealDetail from '@/components/sales/DealDetail'
import MoveDealDialog from '@/components/sales/MoveDealDialog'
import { SnoozeDialog, BookingConfirm, LaunchPrepDialog } from '@/components/accounts/QueueDialogs'
import api, { auth } from '@/lib/api'
import { surfaceTag } from '@/lib/dealTitle'
import { dm } from '@/lib/salesFormat'

// Дашборд аккаунта — рабочий экран, а не витрина цифр: очередь действий.
// ТЗ и референс — docs/«кабинет аккаунта v1» (README + dc.html). Срочность, причина и
// подпись кнопки приходят с бэкенда (app/sales/urgency.py) — той же функцией, что
// порождает уведомления; пересчитывать это на клиенте нельзя, иначе экран и лента
// разойдутся. Группировка и сортировка — наоборот, чисто клиентские: они не меняют
// смысл строки, только её место.
//
// Раскрывашка строки, диалог движения и виджет уведомлений — существующие компоненты.

const mln = (n) => {
  if (!n) return '—'
  if (n >= 1e6) return `${(n / 1e6).toFixed(2).replace('.', ',')} млн`
  return `${Math.round(n / 1e3)} тыс`
}
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

// Короткие подписи стадий ТОЛЬКО для виджета «В работе»: там узкая колонка и важен
// смысл участка, а не полное имя из справочника. Сама стадия не переименовывается —
// в реестре, в движении сделки и в истории она остаётся «Подготовка ДС».
const STAGE_SHORT = { 'Подготовка ДС': 'Закрытие' }

// Группы очереди — разметка по НАШИМ стадиям (согласована с владельцем 2026-08-17).
// Группа = участок конвейера, на котором мяч у аккаунта. Стадия старше причины: сделка
// попадает в группу по тому, где она стоит, а причина (kind) внутри объясняет, что именно
// не так и какой кнопкой это лечить.
//
// stages — по позиции 2/2/2 (stage_key). Там, где одной позиции соответствуют две наши
// стадии («В размещении» и «Предварительная сверка» обе launch), различаем по ИМЕНИ:
// в этом проекте русские строки сравниваются буквально во многих местах, но переименование
// такой стадии в справочнике требует правки и здесь — на это указывает поле stageNames.
const GROUPS = [
  { key: 'mp_needed', title: 'Нужен МП', hint: 'новая сделка без медиаплана',
    dot: 'var(--income)', kinds: ['deal_mp_missing'] },
  // Отдельная группа: план уже есть, но его никто не открывал. Не «нужен МП» (он есть)
  // и не «ждём клиента» (ему ещё нечего показывать). Откуда план — не важно: путей два,
  // конвейер годового плана и ручной МП с кнопкой «Создать сделку».
  { key: 'mp_verify', title: 'МП завизировать', hint: 'аккаунт его ещё не открывал',
    dot: 'var(--dot-current-dz)', kinds: ['mp_verify'] },
  { key: 'mp_sent', title: 'МП отправлен', hint: 'ждём ответа клиента',
    dot: 'var(--dot-current-dz)', kinds: ['mp_unapproved'] },
  // Бронь под подтверждение + всё, что уже на сборе запуска: один участок работы.
  { key: 'prep', title: 'Готовятся к старту', hint: 'подтвердить бронь и собрать запуск',
    dot: 'var(--accent)', kinds: ['booking_confirm'], stages: ['launch_prep'],
    // Кнопка здесь одна, но её состояние зависит от того, где стоит сделка:
    // бронь → «Подтвердить бронь», сбор запуска → «Сбор запуска» (чек-лист),
    // собранный чек-лист → «В размещение». См. prepButton ниже.
    prep: true },
  // watch: аккаунту тут делать нечего — РК идёт, мяч у трафика. Причину строки
  // показываем (она может быть полезна: «период закрыт N дн. назад» = трафик не двинул
  // сделку дальше), но кнопки нет: действие на этой стадии не его.
  { key: 'live', title: 'В размещении', hint: 'РК идёт, мяч у трафика — наблюдаем',
    dot: 'var(--income)', kinds: [], stages: ['launch'], stageNames: ['В размещении'],
    watch: true },

  // Сверка одна: размещение закончилось, трафик отчитался — финализируем цифры
  // и готовим документальное закрытие.
  { key: 'recon', title: 'Итоговая сверка', hint: 'размещение закончилось: финализация цифр',
    dot: 'var(--dot-current-dz)', kinds: [], stages: ['launch'], stageNames: ['Итоговая сверка'] },
  // Этап ДО размечен по участникам (согласовано 2026-08-17): у каждой группы свой
  // держатель мяча, и для аккаунта это разные вещи — где он делает и где ждёт.
  // cta на группе перебивает причинную кнопку строки: на стадии «Подготовка ДС»
  // с закрытым периодом правило скажет «Прикрепить документы», а нужно «Прикрепить ДС».
  // ДС отдельной группой не выделяется: для аккаунта это один участок работы —
  // собрать пакет документов по сделке. Разные бумаги — не разные очереди, а разные
  // чипы «чего не хватает» в строке.
  { key: 'closing_docs', title: 'Готовим закрывающие', hint: 'юрист, бухгалтерия и аккаунт · в планах — шаблоны и выгрузка из 1С',
    dot: 'var(--accent)', kinds: ['act_missing'],
    stageNames: ['Подготовка ДС', 'Согласование ДС', 'Подготовка закрывающих'],
    cta: { label: 'Прикрепить документы', tone: 'act_missing' } },
  // Мяч у фин. менеджера (он же админ). Для аккаунта — наблюдение.
  { key: 'edo', title: 'Выгрузка в ЭДО', hint: 'фин. менеджер · в планах — отправка по API',
    dot: 'var(--dot-current-dz)', kinds: [], stageNames: ['ЭДО'], watch: true },
  { key: 'ord', title: 'Отчёт в ОРД', hint: 'аккаунт вручную · есть API, изучаем',
    dot: 'var(--accent)', kinds: [], stageNames: ['Отчёты в ОРД'],
    cta: { label: 'Отчитаться в ОРД', tone: 'mp_unapproved' } },
  { key: 'await_pay', title: 'Ожидание оплаты', hint: 'срок оплаты идёт, дебиторка у финансов',
    dot: 'var(--text-faint)', kinds: [], stageNames: ['Оплата'], watch: true },
  { key: 'stuck', title: 'Стадия зависла', hint: 'стоит дольше нормы этапа',
    dot: 'var(--dot-current-dz)', kinds: ['stage_stuck'] },
  { key: 'unmapped', title: 'Требует разбора', hint: 'стадия не отнесена к слою денег',
    dot: 'var(--danger)', kinds: ['stage_unmapped'] },
  { key: 'pay', title: 'Просрочка оплаты', hint: 'срок оплаты прошёл',
    dot: 'var(--danger)', kinds: ['payment_overdue'] },
  { key: 'calm', title: 'Без срочности', hint: 'в работе, ничего не горит',
    dot: 'var(--text-faint)', kinds: [''] },
]

const GROUP_OF_KIND = {}
GROUPS.forEach(g => g.kinds.forEach(k => { GROUP_OF_KIND[k] = g }))

// Группа строки. Порядок разбора: точное имя стадии → позиция 2/2/2 → причина.
// Стадия старше причины: иначе сделка на сборе запуска с зависшей стадией ушла бы
// в «Стадия зависла», а участок конвейера остался бы пустым, хотя работа по нему есть.
const groupOf = (r) => {
  const st = r.our_stage
  return GROUPS.find(g => (g.stageNames || []).includes(st?.name))
    || GROUPS.find(g => !g.stageNames && (g.stages || []).includes(st?.stage_key))
    || GROUP_OF_KIND[r.kind || ''] || GROUPS[GROUPS.length - 1]
}

// Срочность красит строку и точку — она ортогональна виду действия и в группировке
// не участвует (ТЗ 1.1: это разные оси, одна из другой не выводится).
// Значения тонов — из кита (ROW_TONE), чтобы реестр и будущие экраны красили так же.

const EVENT_KIND = {
  start: ['Старт РК', 'var(--income)'],
  // фиолетовый закрытия периода токена не имеет — он локальный для этой легенды
  closing: ['Закрытие периода', 'var(--violet-fg)'],
  docs: ['Дедлайн документов', 'var(--dot-current-dz)'],
}

// Обязательный состав документов по стадиям закрытия (согласовано 2026-08-17):
// ДС · УПД или АКТ (любой из двух) · Счёт. Отчёт — опционально, поэтому в требования
// не входит и в «чего не хватает» не показывается.
// any: список видов, из которых достаточно одного — УПД и акт закрывают одно и то же
// событие, и требовать оба значило бы держать сделку в очереди из-за формы бумаги.
const DOC_REQ = {
  closing_docs: [
    { label: 'ДС', any: ['ds'] },
    { label: 'УПД / Акт', any: ['upd', 'act'] },
    { label: 'Счёт', any: ['invoice'] },
  ],
}
const missingDocs = (groupKey, docs) => (DOC_REQ[groupKey] || [])
  .filter(req => !req.any.some(k => (docs || []).includes(k)))
  .map(req => req.label)

// Пины-фильтры тулбара. Одно описание задаёт и подпись, и способ достать значение
// из строки: без этого список пинов и код фильтрации разъезжаются на первой правке
// (ровно так в реестре сделок когда-то появились фильтры, ничего не фильтрующие).
// Значение — id, где он есть: имена рекламодателей и брендов меняются, id нет.
const PINS = [
  { key: 'pipeline', label: 'Воронка', val: r => r.pipeline, text: r => r.pipeline },
  { key: 'product', label: 'Услуга', val: r => r.product, text: r => r.product },
  { key: 'stage', label: 'Стадия', val: r => r.our_stage?.id, text: r => r.our_stage?.name },
  { key: 'layer', label: 'Слой денег', val: r => r.our_stage?.money_layer, text: r => r.our_stage?.money_layer },
  { key: 'advertiser', label: 'Рекламодатель', val: r => r.advertiser_id, text: r => r.advertiser },
  { key: 'brand', label: 'Бренд', val: r => r.brand_id, text: r => r.brand },
  { key: 'agency', label: 'Агентство', val: r => r.agency_id, text: r => r.agency },
  { key: 'account', label: 'Аккаунт', val: r => r.account_manager_id, text: r => r.account_manager },
]

// Пин сортировки — те же колонки, что и в шапке таблицы, чтобы способов сортировать
// было два, а состояние одно: кликнул по шапке — видно в пине, и наоборот.
const SORTABLE = [
  ['code', 'Код'], ['advertiser', 'Рекламодатель'], ['agency', 'Агентство'], ['product', 'Услуга'],
  ['start', 'Старт'], ['stage', 'Стадия'], ['kind', 'Что сделать'], ['amount', 'Сумма'],
]

// Колонки строки очереди — раскладка референса (dc.html, ряд flatRows).
// Ширины: у каждой кнопки своя ячейка, иначе они наезжают на сумму — в одной
// ячейке «Собрать МП» и «⏰» тянут её ширину непредсказуемо, и правый край строки
// перестаёт быть выровненным (то, что видно на широком экране в первую очередь).
const COLS = [
  { key: 'code', w: '84px', label: 'Код' },
  { key: 'advertiser', w: 'minmax(180px, 1.5fr)', label: 'Рекламодатель / бренд' },
  { key: 'agency', w: 'minmax(120px, 1fr)', label: 'Агентство' },
  { key: 'product', w: 'minmax(120px, 1fr)', label: 'Услуга' },
  { key: 'start', w: '70px', label: 'Старт' },
  { key: 'stage', w: 'minmax(150px, 1.3fr)', label: 'Стадия' },
  { key: 'kind', w: 'minmax(190px, 1.5fr)', label: 'Что сделать' },
  { key: 'amount', w: '104px', label: 'Сумма', right: true },
  { key: 'cta', w: '156px', label: '', nosort: true },
  { key: 'snooze', w: '38px', label: '', nosort: true },
  { key: 'caret', w: '20px', label: '', nosort: true },
]
const GRID = COLS.map(c => c.w).join(' ')

// Значение для сортировки. Дефолт (sortKey=null) — порядок очереди с бэкенда:
// срочность, внутри — ближайший дедлайн. Он и есть смысловой порядок, поэтому
// сортировка по колонке его заменяет, а не дополняет.
const sortVal = (r, key) => {
  switch (key) {
    case 'code': return r.code || ''
    case 'advertiser': return (r.advertiser || r.title || '').toLowerCase()
    case 'agency': return (r.agency || '').toLowerCase()
    case 'product': return (r.product || '').toLowerCase()
    case 'start': return r.period_from || '9999'
    case 'stage': return STAGE_ORDER.indexOf(r.our_stage?.stage_key)
    case 'kind': return groupOf(r).title || ''
    case 'amount': return r.amount || 0
    default: return 0
  }
}

export default function AccountDashboard() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [cal, setCal] = useState([])
  const [notifs, setNotifs] = useState([])
  // Селектор сотрудника, как в дашборде сейлза: '' — я, 'all' — раздел целиком,
  // число — конкретный аккаунт.
  const [repId, setRepId] = useState('')
  const [reps, setReps] = useState([])
  const [myRepId, setMyRepId] = useState(null)
  const [day, setDay] = useState(null)
  const [view, setView] = useState('groups')          // groups (по статусу) | list (списком)
  const [qtext, setQtext] = useState('')
  const [range, setRange] = useState({ from: '', to: '' })
  const [pins, setPins] = useState(() => Object.fromEntries(PINS.map(p => [p.key, []])))
  const [gaps, setGaps] = useState([])
  const [rangeOpen, setRangeOpen] = useState(false)
  const [workOpen, setWorkOpen] = useState(false)
  // Табличный вид — обычная таблица со страницами, а не бесконечный скролл внутри
  // карточки: 100 строк по умолчанию, табуляция снизу. Скролл внутри блока годится
  // для короткой группы, но не для реестра на 600 строк.
  const [pageSize, setPageSize] = useState(100)
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [expandedId, setExpandedId] = useState(null)
  // Строка очереди умышленно короткая (её задача — очередь, не карточка), поэтому
  // при раскрытии сделка догружается целиком. Иначе раскрывашка сказала бы
  // «документов нет» там, где они есть, — то есть соврала бы про то самое,
  // из-за чего сделка попала в очередь.
  const [detail, setDetail] = useState(null)
  const [closed, setClosed] = useState({ calm: true, snoozed: true })
  const [moveDeal, setMoveDeal] = useState(null)
  const [snoozeFor, setSnoozeFor] = useState(null)
  const [prepFor, setPrepFor] = useState(null)      // модалка сбора запуска
  const [confirmFor, setConfirmFor] = useState(null) // меню подтверждения брони
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  const canEdit = can('accounts_dashboard', 'edit')
  const myName = useMemo(() => (reps.find(r => r.id === myRepId) || {}).name, [reps, myRepId])

  const load = useCallback(() => {
    setLoading(true)
    const who = repId === 'all' ? 'all_reps=true' : (repId ? `rep_id=${repId}` : '')
    const q = [who, day ? `day=${day}` : ''].filter(Boolean).join('&')
    Promise.all([
      api.get(`/sales/account-queue${q ? `?${q}` : ''}`, auth()),
      api.get(`/sales/account-calendar${who ? `?${who}` : ''}`, auth()),
      api.get('/notifications?limit=50', auth()).catch(() => ({ data: { items: [] } })),
    ]).then(([q1, q2, q3]) => {
      setData(q1.data)
      setCal(q2.data.days || [])
      setNotifs((q3.data.items || []).map(toItem))
      setMyRepId(q1.data.my_rep_id ?? null)
      setErr('')
    }).catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить очередь'))
      .finally(() => setLoading(false))
  }, [repId, day])

  useEffect(() => { load() }, [load])

  // Диапазон периода закрывается по клику мимо: PortalPopover рисует панель, но
  // за её жизненный цикл отвечает вызывающий (клики внутри портала он гасит сам).
  useEffect(() => {
    if (!rangeOpen) return
    const off = (e) => { if (!e.target.closest('[data-range-root]')) setRangeOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [rangeOpen])

  // Любая смена выборки возвращает на первую страницу: иначе человек остаётся
  // на седьмой странице списка, в котором после фильтра всего две.
  useEffect(() => { setPage(0) }, [view, pageSize, qtext, range, pins, gaps, sortKey, sortDir, day])

  useEffect(() => {
    api.get('/sales/reps?role=account', auth())
      .then(r => { setReps(r.data.items || []); setMyRepId(x => x ?? r.data.mine ?? null) })
      .catch(() => {})
  }, [])

  const markRead = (ids) => {
    setNotifs(list => list.map(n => (!ids || ids.includes(n.id)) ? { ...n, unread: false } : n))
    api.post('/notifications/read', { ids: ids || null }, auth()).catch(() => {})
  }

  // Все строки в порядке, который прислал бэкенд (срочность → дедлайн). Группа
  // «Отложено» приходит отдельной, поэтому признак несём флагом, а не датой:
  // заметка без даты возврата строку из очереди не убирает.
  const allRows = useMemo(() => (data?.groups || [])
    .flatMap(g => g.rows.map(r => ({ ...r, snoozed: g.key === 'snoozed' }))), [data])

  // Опции считаются по ПОЛНОМУ набору строк, а не по отфильтрованному: иначе, сняв
  // галочку, человек не смог бы вернуть её обратно — значение исчезло бы из списка.
  const pinOptions = useMemo(() => {
    const out = {}
    PINS.forEach(p => {
      const m = new Map()
      allRows.forEach(r => {
        const v = p.val(r)
        if (v == null || v === '') return
        const cur = m.get(v) || { value: v, label: p.text(r) || String(v), count: 0 }
        cur.count += 1
        m.set(v, cur)
      })
      out[p.key] = [...m.values()].sort((a, b) => b.count - a.count)
    })
    return out
  }, [allRows])

  const filtered = useMemo(() => {
    const q = qtext.trim().toLowerCase()
    return allRows.filter(r => {
      if (q && !`${r.code || ''} ${r.advertiser || ''} ${r.brand || ''} ${r.title || ''}`.toLowerCase().includes(q)) return false
      // Диапазон сверяем по ПЕРЕСЕЧЕНИЮ с периодом РК, а не по попаданию старта:
      // сделка, начавшаяся в июне и идущая в июле, в июльском диапазоне обязана быть.
      if (range.from && (r.period_to || r.period_from || '9999') < range.from) return false
      if (range.to && (r.period_from || r.period_to || '0000') > range.to) return false
      for (const p of PINS) {
        const selv = pins[p.key]
        if (selv.length && !selv.includes(p.val(r))) return false
      }
      // «Незаполненные» — ИЛИ по выбранным дырам: человек ищет, что дозаполнить,
      // и ждёт все проблемные строки, а не пересечение всех пропусков сразу.
      if (gaps.length && !gaps.some(f => f === 'payer' ? !r.payer_counterparty_id : !r[f])) return false
      return true
    })
  }, [allRows, qtext, range, pins, gaps])

  const filtersOn = !!(qtext || range.from || range.to || gaps.length
    || PINS.some(p => pins[p.key].length))
  const resetFilters = () => {
    setQtext(''); setRange({ from: '', to: '' }); setGaps([])
    setPins(Object.fromEntries(PINS.map(p => [p.key, []])))
    setDay(null)
  }

  const snoozedHint = useMemo(
    () => (data?.groups || []).find(g => g.key === 'snoozed')?.hint, [data])

  const applySort = useCallback((list) => {
    if (!sortKey) return list
    const k = sortDir === 'desc' ? -1 : 1
    return [...list].sort((a, b) => {
      const va = sortVal(a, sortKey), vb = sortVal(b, sortKey)
      return (va > vb ? 1 : va < vb ? -1 : 0) * k
    })
  }, [sortKey, sortDir])

  const onSort = (key, nosort) => {
    if (nosort) return
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    if (sortDir === 'asc') { setSortDir('desc'); return }
    setSortKey(null); setSortDir('asc')    // третий клик — назад к порядку очереди
  }

  // Вид «по статусу»: группы = виды действий. Вид «списком»: одна таблица.
  const groups = useMemo(() => {
    const live = filtered.filter(r => !r.snoozed)
    const snoozed = filtered.filter(r => r.snoozed)
    const snoozedGroup = snoozed.length
      ? [{ key: 'snoozed', title: 'Отложено', dot: 'var(--text-faint)', hint: snoozedHint, rows: applySort(snoozed) }]
      : []
    if (view === 'list') {
      return [...snoozedGroup,
              { key: 'all', title: 'Все строки', dot: 'var(--text-faint)', rows: applySort(live) }]
    }
    const out = GROUPS.map(g => ({
      ...g, rows: applySort(live.filter(r => groupOf(r).key === g.key)),
    })).filter(g => g.rows.length)
    return [...snoozedGroup, ...out]
  }, [filtered, view, applySort, snoozedHint])

  const loadDetail = (r) => api.get(`/sales/deals/${r.code || r.id}`, auth())
    .then(res => setDetail({ id: r.id, deal: res.data }))
    .catch(() => setDetail({ id: r.id, deal: null }))

  const toggleRow = (r) => {
    if (expandedId === r.id) { setExpandedId(null); setDetail(null); return }
    setExpandedId(r.id); setDetail(null); loadDetail(r)
  }

  // «В работе»: раскладка по стадиям считается из тех же строк, что видит человек —
  // то есть из ОТФИЛЬТРОВАННЫХ. Считать из полного набора нельзя: выбрав пин
  // «Рекламодатель = X», человек видел бы в очереди 12 строк, а в виджете рядом
  // по-прежнему 618 — два ответа на один вопрос. Порядок — по лестнице (STAGE_ORDER),
  // а не по количеству: полоса должна читаться как путь сделки.
  const byStage = useMemo(() => {
    const m = new Map()
    filtered.forEach(r => {
      const s = r.our_stage
      const key = s?.name || 'Без стадии'
      const cur = m.get(key) || { name: key, os: s, n: 0 }
      cur.n += 1
      m.set(key, cur)
    })
    return [...m.values()].sort((a, b) =>
      STAGE_ORDER.indexOf(a.os?.stage_key) - STAGE_ORDER.indexOf(b.os?.stage_key))
  }, [filtered])

  // Полоса «В работе»: сегмент на стадию, ширина — доля, цвет — слой денег.
  // Цвета берём из PIP/FILL кита, чтобы полоса и светофор не разъехались.
  const stageMix = useMemo(() => {
    const total = byStage.reduce((s, x) => s + x.n, 0) || 1
    return byStage.map(x => {
      const n = STAGE_ORDER.indexOf(x.os?.stage_key) + 1 || FILL[x.os?.money_layer] || 0
      return { ...x, width: `${(x.n / total * 100).toFixed(2)}%`, color: n ? PIP[n - 1] : 'var(--border-inner)' }
    })
  }, [byStage])

  // Четыре плитки макета. «Не оплачено» посчитать нечем: связи сделки с операцией
  // в схеме нет, факт оплаты на этом уровне не читается (см. urgency.py) — вместо
  // выдуманной цифры показываем прочерк с подсказкой.
  const budgets = useMemo(() => {
    const of = (keys) => filtered.filter(r => keys.includes(r.our_stage?.stage_key))
      .reduce((s, r) => s + (r.amount || 0), 0)
    return [
      ['Под управлением', of(['booking', 'launch_prep', 'launch', 'closing', 'closing_fact'])],
      ['В размещении', of(['launch'])],
      ['Ждут закрывающих', of(['closing'])],
      ['Не оплачено', null, 'появится вместе с мостом сделка → операция'],
    ]
  }, [filtered])

  // «Загрузка вперёд» — шесть месяцев от текущего. Сделка попадает в КАЖДЫЙ месяц
  // своего периода размещения, а не только в месяц старта: РК июль-сентябрь занимает
  // все три, иначе полоса покажет пустой август при полной загрузке.
  // Подтверждённые — слои «реализуемые» и «фактические» (деньги в работе), в проработке —
  // «планируемые». Разметка слоёв берётся со стадии, руками её задать нельзя.
  const forward = useMemo(() => {
    const now = new Date(data?.today || Date.now())
    const months = []
    for (let i = 0; i < 6; i++) {
      const d0 = new Date(now.getFullYear(), now.getMonth() + i, 1)
      months.push({ ym: `${d0.getFullYear()}-${String(d0.getMonth() + 1).padStart(2, '0')}`,
                    label: ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'][d0.getMonth()],
                    ok: 0, plan: 0 })
    }
    const idx = Object.fromEntries(months.map((m, i) => [m.ym, i]))
    filtered.forEach(r => {
      const from = r.period_from || r.period_to
      const to = r.period_to || r.period_from
      if (!from) return
      const layer = r.our_stage?.money_layer
      const confirmed = layer === 'реализуемые' || layer === 'фактические'
      for (const m of months) {
        if (m.ym >= from.slice(0, 7) && m.ym <= to.slice(0, 7)) {
          if (confirmed) months[idx[m.ym]].ok += 1; else months[idx[m.ym]].plan += 1
        }
      }
    })
    const totals = months.map(m => m.ok + m.plan)
    const avg = totals.reduce((a, b) => a + b, 0) / (months.length || 1)
    const max = Math.max(1, ...totals)
    // Перегруз — больше 1,5 среднего: месяц, в который набрали заметно выше обычного.
    return months.map(m => ({ ...m, total: m.ok + m.plan, max,
                              hot: avg > 0 && (m.ok + m.plan) > avg * 1.5 }))
  }, [filtered, data])

  const doSnooze = async (row, note, return_at) => {
    try {
      await api.post(`/sales/deals/${row.code || row.id}/snooze`, { note, return_at }, auth())
      setSnoozeFor(null); load()
    } catch (e) { alert(e?.response?.data?.detail || 'Не удалось отложить') }
  }
  const unsnooze = async (row) => {
    try { await api.delete(`/sales/deals/${row.code || row.id}/snooze`, auth()); load() }
    catch { alert('Не удалось вернуть в очередь') }
  }

  // Кнопка строки ведёт туда, где действие реально совершается. Подпись — с бэкенда.
  const runCta = (row) => {
    if (row.kind === 'deal_mp_missing') return router.push('/accounts/mp')
    // Проверка автоплана делается в конструкторе МП: отметки «Проверено» там,
    // и сохранение оттуда само двигает сделку на следующую стадию. Открываем в НОВОЙ
    // вкладке — очередь остаётся на месте, аккаунт разбирает пачку планов не теряя её.
    // Плана нет в конструкторе (МП приехал файлом из Битрикса) — тогда карточка сделки:
    // там его можно скачать. Отправлять в конструктор по несуществующему id нельзя.
    if (row.kind === 'mp_verify') {
      if (row.mp_id) return window.open(`/accounts/mp/${row.mp_id}`, '_blank', 'noopener')
      return router.push(`/sales/deals/${row.code || row.id}`)
    }
    // Подтверждение брони — не одно движение, а выбор из двух: подтвердили → сбор
    // запуска, не подтвердили → срыв. Кнопка поэтому открывает меню, а не диалог.
    if (row.kind === 'booking_confirm') return setConfirmFor(row)
    if (row.kind === 'stage_unmapped' || row.kind === 'stage_stuck') return setMoveDeal(row)
    if (row.kind === 'payment_overdue') return router.push('/finance/receivables')
    return router.push(`/sales/deals/${row.code || row.id}`)
  }

  const viewBtn = (key, title, path) => (
    <span onClick={() => { setView(key); setExpandedId(null) }} title={title}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 24, borderRadius: 7, cursor: 'pointer',
        background: view === key ? 'var(--accent-tint)' : 'transparent', color: view === key ? 'var(--accent)' : 'var(--text-secondary)', transition: 'background-color 150ms ease, color 150ms ease' }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">{path}</svg>
    </span>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Дашборд аккаунта — Finance CRM</title></Head>
      <Navbar />
      {/* Во всю ширину экрана: ограничение 1720 из ТЗ снято по просьбе владельца.
          Правая колонка при этом фиксирована по ширине, а не в процентах — весь
          прирост экрана достаётся таблице, а виджеты остаются такими, как были
          (в процентах они бы растягивались и разъезжались на широком мониторе). */}
      <div style={{ margin: '0 auto', padding: '26px 24px 40px' }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24, marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Что делать</span>
            {/* В шапке — то, что требует действия; всего в очереди уходит в подсказку.
                Раньше здесь стоял total, и «Что делать 618» спорило с «Требует
                действия 443» строкой ниже. */}
            {!!data && (
              <span title={`всего в очереди ${data.total}`}
                style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>{data.actionable ?? data.total}</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Список сотрудников, как в дашборде сейлза. Своя строка помечена ★ —
                по имени её не угадать, id профиля приходит с бэкенда (my_rep_id). */}
            {(data?.can_view_others ?? true) ? (
              <select value={repId} onChange={e => setRepId(e.target.value)}
                style={{ ...sel, minWidth: 210, padding: '8px 11px' }}>
                {!!myRepId && <option value="">★ {myName || 'Мои сделки'}</option>}
                <option value="all">Все аккаунты</option>
                {reps.filter(r => r.id !== myRepId).map(r => (
                  <option key={r.id} value={r.id}>{r.name}{r.linked ? '' : ' (без юзера)'}</option>
                ))}
              </select>
            ) : (
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{myName || 'Мои сделки'}</span>
            )}
            {/* Подписи «профиль не привязан…» тут нет намеренно: в селекторе и так
                выбрано «Все аккаунты», режим виден без пояснений. */}
          </div>
        </div>

        {err && <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div>}

        {/* полоса событий */}
        <div style={{ ...card, padding: '14px 16px', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <span style={CAP}>События</span>
            <span style={{ display: 'inline-flex', gap: 14, flexWrap: 'wrap' }}>
              {Object.entries(EVENT_KIND).map(([k, [label, color]]) => (
                <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />{label}
                </span>
              ))}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cal.length || 10}, minmax(0, 1fr))`, gap: 8 }}>
            {cal.map(dd => {
              const active = day === dd.date
              const empty = !dd.total
              return (
                // Контраст плиток из макета: пустой день — белый, день с активностями —
                // серый, рамка чёткая у обоих. Приглушение прозрачностью убрано: оно
                // ослабляло и рамку, из-за чего полоса выглядела размытой, а пустой день
                // читался как «выключенный», а не как «свободный».
                <div key={dd.date} onClick={() => !empty && setDay(active ? null : dd.date)}
                  style={{ border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-card)'}`, borderRadius: 12, padding: '9px 10px',
                    background: active ? 'var(--accent-tint)' : (empty ? 'var(--bg-card)' : 'var(--bg-subtle)'),
                    cursor: empty ? 'default' : 'pointer' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: empty ? 'var(--text-faint)' : 'var(--text-primary)' }}>{dm(dd.date)}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{WD[new Date(dd.date).getDay()]}</span>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, color: empty ? 'var(--text-faint)' : 'var(--text-primary)', lineHeight: 1.3 }}>{dd.total}</div>
                  <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', minHeight: 14 }}>
                    {Object.entries(dd.kinds || {}).map(([k, n]) => (
                      <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: (EVENT_KIND[k] || [])[1] || 'var(--text-faint)' }} />{n}
                      </span>
                    ))}
                  </div>
                  {!!(dd.brands || []).length && (
                    <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {dd.brands.join(' · ')}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {!!day && (
            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>
              Очередь отфильтрована по {dm(day)} · <span onClick={() => setDay(null)} style={{ color: 'var(--accent)', cursor: 'pointer' }}>снять</span>
            </div>
          )}
        </div>

        {/* ряд: очередь + правая колонка */}
        <div style={{ display: 'flex', gap: 16, alignItems: 'stretch' }}>
          <div style={{ flex: '1 1 0', minWidth: 0 }}>
            <div style={{ ...card, padding: '14px 18px 12px' }}>

              {/* заголовок блока */}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Требует действия</span>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--danger)' }}>
                  {groups.filter(g => g.key !== 'snoozed' && g.key !== 'calm')
                         .reduce((n, g) => n + g.rows.length, 0)} сделок
                </span>
                {filtersOn && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>отфильтровано из {allRows.length}</span>}
              </div>

              {/* тулбар: поиск - период - пины - сортировка - сброс - вид */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 12 }}>
                <span style={{ position: 'relative', flex: '0 0 190px' }}>
                  <input value={qtext} onChange={e => setQtext(e.target.value)} placeholder="Код, бренд"
                    style={{ ...inp, width: '100%', padding: '8px 10px 8px 28px', fontSize: 12 }} />
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="2"
                    style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }}>
                    <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
                  </svg>
                </span>

                {/* Диапазон периода РК. Своя выпадашка, а не PeriodSelect: тот выбирает
                    ОДИН месяц или квартал, а здесь нужны две границы. */}
                <span data-range-root style={{ position: 'relative' }}>
                  <span onClick={() => setRangeOpen(o => !o)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${range.from || range.to ? 'var(--accent)' : 'var(--border-card)'}`,
                      background: range.from || range.to ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600,
                      color: range.from || range.to ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: MONO }}>
                    {range.from || range.to ? `${dm(range.from)} — ${dm(range.to)}` : 'Период РК'} ▾
                  </span>
                  {/* PortalPopover, а не position:absolute: тулбар живёт в карточке
                      с overflow, и собственная панель обрезалась бы её краем. */}
                  <PortalPopover open={rangeOpen} minWidth={300}
                    style={{ padding: 12, gap: 8 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Пересечение с периодом размещения</span>
                    <span style={{ display: 'flex', gap: 8 }}>
                      <input type="date" value={range.from} onChange={e => setRange(r => ({ ...r, from: e.target.value }))} style={{ ...inp, fontFamily: MONO, fontSize: 12 }} />
                      <input type="date" value={range.to} onChange={e => setRange(r => ({ ...r, to: e.target.value }))} style={{ ...inp, fontFamily: MONO, fontSize: 12 }} />
                    </span>
                    <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span onClick={() => setRange({ from: '', to: '' })} style={{ fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer' }}>сбросить</span>
                      <span onClick={() => setRangeOpen(false)} style={{ fontSize: 11.5, color: 'var(--text-muted)', cursor: 'pointer' }}>готово</span>
                    </span>
                  </PortalPopover>
                </span>

                {PINS.map(p => (
                  <MultiDrop key={p.key} label={p.label} options={pinOptions[p.key]}
                    selected={pins[p.key]} onChange={v => setPins(st => ({ ...st, [p.key]: v }))} />
                ))}
                <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={gaps} onChange={setGaps} />

                {/* Пин сортировки — то же состояние, что и клик по шапке колонки:
                    способов сортировать два, состояние одно. */}
                <MultiDrop label={sortKey ? `Сортировка · ${(SORTABLE.find(x => x[0] === sortKey) || [])[1]} ${sortDir === 'desc' ? '↓' : '↑'}` : 'Сортировка'}
                  options={SORTABLE.flatMap(([k, l]) => [
                    { value: `${k}:asc`, label: `${l} ↑` }, { value: `${k}:desc`, label: `${l} ↓` }])}
                  selected={sortKey ? [`${sortKey}:${sortDir}`] : []}
                  onChange={v => {
                    const last = v[v.length - 1]
                    if (!last) { setSortKey(null); setSortDir('asc'); return }
                    const parts = last.split(':')
                    setSortKey(parts[0]); setSortDir(parts[1])
                  }} />

                <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                  <IconBtn title={filtersOn ? 'Сбросить фильтры' : 'Фильтры не заданы'} active={filtersOn} onClick={resetFilters}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                      <path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" />
                    </svg>
                  </IconBtn>
                  <span style={{ display: 'inline-flex', gap: 4, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 9, padding: 3 }}>
                    {viewBtn('groups', 'Вид: по статусу', <><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h10" /><path d="M2 6h.01M2 12h.01M2 18h.01" /></>)}
                    {viewBtn('list', 'Вид: списком', <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /><path d="M3 14h18" /><path d="M9 4v16" /></>)}
                  </span>
                </span>
              </div>

              {loading && !data && <div style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div>}

              {groups.map(g => {
                const isClosed = !!closed[g.key]
                // Раскрыта ли строка ИМЕННО этой группы — от этого зависит, режем ли высоту.
                const groupExpanded = g.rows.some(r => r.id === expandedId)
                // В табличном виде показываем страницу, в группах — все строки группы.
                const paged = view === 'list' && g.key !== 'snoozed'
                const shownRows = paged ? g.rows.slice(page * pageSize, (page + 1) * pageSize) : g.rows
                const pages = paged ? Math.max(1, Math.ceil(g.rows.length / pageSize)) : 1
                return (
                  <div key={g.key} style={{ marginBottom: 12 }}>
                    {/* Шапку группы в виде «списком» не рисуем — там одна таблица. */}
                    {(view === 'groups' || g.key === 'snoozed') && (
                      <div onClick={() => setClosed(c => ({ ...c, [g.key]: !isClosed }))}
                        style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', borderRadius: 10, cursor: 'pointer',
                          background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', marginBottom: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: g.dot }} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{g.title}</span>
                        <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: g.dot }}>{g.rows.length}</span>
                        {!!g.hint && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{g.hint}</span>}
                        {/* Подпись действия справа в шапке — как в макете: видно, чем
                            занята вся группа, не читая строк. */}
                        {!g.watch && (g.cta || g.rows[0]?.cta) && (
                          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase',
                            color: (CTA_TONE[g.cta ? g.cta.tone : (g.rows[0].kind || '')] || [])[1] || 'var(--text-faint)' }}>
                            {g.cta ? g.cta.label : g.rows[0].cta}
                          </span>
                        )}
                        <span style={{ marginLeft: (!g.watch && (g.cta || g.rows[0]?.cta)) ? 10 : 'auto', color: 'var(--text-faint)', fontSize: 11 }}>{isClosed ? '▾' : '▴'}</span>
                      </div>
                    )}

                    {!isClosed && (
                      <div>
                        {/* Шапка колонок — она же кнопки сортировки. */}
                        <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '0 10px 8px', borderBottom: '1px solid var(--border-inner)' }}>
                          {COLS.map(c => (
                            <span key={c.key} onClick={() => onSort(c.key, c.nosort)}
                              style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                                textAlign: c.right ? 'right' : 'left', cursor: c.nosort ? 'default' : 'pointer',
                                color: sortKey === c.key ? 'var(--accent)' : 'var(--text-faint)' }}>
                              {c.label}{sortKey === c.key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                            </span>
                          ))}
                        </div>

                        {/* Раскрытая строка снимает ограничение по высоте (ТЗ 2.3):
                            иначе раскрывашка обрезается скроллом и уезжает под
                            следующую группу. В табличном виде высота не режется вовсе —
                            там страницы. */}
                        <div style={{
                          maxHeight: (view === 'groups' && g.rows.length > 8 && !groupExpanded) ? 396 : undefined,
                          overflowY: (view === 'groups' && g.rows.length > 8 && !groupExpanded) ? 'auto' : 'visible',
                          overflowX: 'hidden', margin: '0 -10px', padding: '0 10px' }}>
                        {shownRows.map(r => {
                          const u = ROW_TONE[r.urgency] || ROW_TONE.normal
                          const gk = groupOf(r)
                          const startPassed = r.period_from && r.period_from < (data?.today || '')
                          return (
                            <Fragment key={r.id}>
                              <div onClick={e => { if (e.target.closest('button')) return; toggleRow(r) }}
                                style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', boxSizing: 'border-box',
                                  padding: '7px 10px', borderRadius: 9, border: `1px solid ${u.border}`, marginBottom: 4, cursor: 'pointer',
                                  background: expandedId === r.id ? 'var(--accent-tint)' : u.bg, color: 'var(--text-primary)' }}>
                                <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>{r.code || r.id}</span>

                                {/* рекламодатель и бренд — двумя строками, как в референсе */}
                                <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                                  <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                    title={r.title || ''}>{r.advertiser || r.title || '—'}</span>
                                  <span style={{ fontSize: 10, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {r.brand || '—'}
                                  </span>
                                </span>

                                {/* Агентство — своя колонка: раньше подмешивалось в строку
                                    бренда и появлялось только у сделок без бренда, то есть
                                    увидеть его было делом случая. */}
                                <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                  title={r.agency || ''}>{r.agency || '—'}</span>

                                {/* Маркер — цвет УСЛУГИ (справочник или авто), а не срочности:
                                    срочность уже сказана фоном строки, и дублировать её тут
                                    значило бы потерять единственное место, где видно услугу. */}
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                                  <span style={{ width: 7, height: 7, borderRadius: 2, background: r.product_color || 'var(--text-faint)', flex: '0 0 7px' }} />
                                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, lineHeight: 1.15 }}>
                                    <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {r.product || '—'}
                                    </span>
                                    {/* Поверхность — подписью под услугой, как в реестре сделок и в
                                        дашборде трафика. Считает сервер (row_context.inventory) и
                                        только у услуг с раздельным прайсом: у остальных web и app —
                                        один продукт, и метка была бы шумом. */}
                                    {!!surfaceTag(r.inventory) && (
                                      <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em', color: 'var(--text-faint)' }}>
                                        {surfaceTag(r.inventory)}
                                      </span>
                                    )}
                                  </span>
                                </span>

                                <span style={{ fontFamily: MONO, fontSize: 11.5, whiteSpace: 'nowrap',
                                  fontWeight: startPassed ? 700 : 400,
                                  color: startPassed ? 'var(--danger)' : 'var(--text-secondary)' }}>{dm(r.period_from)}</span>

                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}
                                  title={r.our_stage?.name || 'стадия не определена'}>
                                  <StageLayerBar os={r.our_stage} h={8} w={9} />
                                  <span style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {r.our_stage?.name || '—'}
                                  </span>
                                </span>

                                {/* На стадиях закрытия показываем НЕХВАТАЮЩИЕ документы поимённо:
                                    «документов нет» не говорит, что нести. Всё приложено —
                                    пишем это прямо, чтобы строка не выглядела недоделанной. */}
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }} title={r.reason || ''}>
                                  <span style={{ width: 7, height: 7, borderRadius: 2, background: gk.dot, flex: '0 0 7px' }} />
                                  {DOC_REQ[gk.key] ? (
                                    (() => {
                                      const miss = missingDocs(gk.key, r.docs)
                                      return (
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0, fontSize: 11 }}>
                                          {miss.length ? miss.map(m => (
                                            <span key={m} style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.04em', padding: '2px 6px', borderRadius: 6,
                                              background: 'var(--warning-tint)', color: 'var(--warning-text)', border: `1px solid ${UNVERIFIED_BORDER}`, whiteSpace: 'nowrap' }}>{m}</span>
                                          )) : (
                                            <span style={{ fontSize: 11, color: 'var(--income)', fontWeight: 600 }}>всё приложено</span>
                                          )}
                                        </span>
                                      )
                                    })()
                                  ) : (
                                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {r.reason || gk.title}
                                    </span>
                                  )}
                                </span>

                                <span style={{ textAlign: 'right', fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap', paddingRight: 4 }}>{mln(r.amount)}</span>

                                {/* Кнопка действия занимает всю свою ячейку — тогда у всех
                                    строк группы она одной ширины и правый край ровный.
                                    Кнопки участка (у сбора запуска их две) идут вместо
                                    причинной, когда причины нет. */}
                                <span style={{ display: 'flex', gap: 4 }}>
                                  {canEdit && !gk.watch && (gk.cta || r.cta) && (() => {
                                    // Документы собраны — просить прикрепить нечего, сделку
                                    // надо двигать дальше. Кнопка меняет и подпись, и действие.
                                    const ready = DOC_REQ[gk.key] && !missingDocs(gk.key, r.docs).length
                                    const label = ready ? 'Двинуть' : (gk.cta ? gk.cta.label : r.cta)
                                    const tone = ready ? 'launch_ready' : (gk.cta ? gk.cta.tone : r.kind)
                                    return (
                                      <button
                                        onClick={() => ready ? setMoveDeal(r)
                                          : (gk.cta ? router.push(`/sales/deals/${r.code || r.id}`) : runCta(r))}
                                        title={ready ? 'Все обязательные документы приложены' : (gk.cta ? 'Открыть сделку — документы во вкладке сделки' : (r.reason || ''))}
                                        style={{ ...ctaStyle(tone), width: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {label}
                                      </button>
                                    )
                                  })()}
                                  {!r.cta && canEdit && gk.prep && (
                                    <button onClick={() => setPrepFor(r)} title="Сбор запуска"
                                      style={{ ...ctaStyle('launch_prep'), width: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                      Сбор запуска
                                    </button>
                                  )}
                                </span>

                                <span style={{ display: 'flex', justifyContent: 'center' }}>
                                  {canEdit && (r.snoozed
                                    ? <button onClick={() => unsnooze(r)} style={{ ...btnSm(false), padding: '4px 7px' }} title="Вернуть в очередь">↩</button>
                                    : <button onClick={() => setSnoozeFor(r)} style={{ ...btnSm(false), padding: '4px 7px' }} title={r.note || 'Отложить или оставить заметку'}>{r.note ? '📎' : '⏰'}</button>)}
                                </span>

                                <span style={{ fontSize: 10, color: 'var(--text-faint)', textAlign: 'center' }}>{expandedId === r.id ? '▴' : '▾'}</span>
                              </div>
                              {expandedId === r.id && (
                                detail?.id === r.id
                                  ? <DealDetail deal={detail.deal || r} canEdit={canEdit}
                                      onOpen={() => router.push(`/sales/deals/${r.code || r.id}`)}
                                      onEdit={() => router.push(`/sales/deals/${r.code || r.id}`)}
                                      onChanged={() => { load(); loadDetail(r) }} />
                                  : <div style={{ padding: '14px 12px', fontSize: 12, color: 'var(--text-muted)' }}>Загрузка сделки…</div>
                              )}
                            </Fragment>
                          )
                        })}
                        </div>
                        {/* Скрытых строк быть не должно молча: если группа скроллится,
                            подписываем, сколько видно сразу — иначе «8 сделок» читается
                            как «их всего восемь». */}
                        {view === 'groups' && g.rows.length > 8 && !groupExpanded && (
                          <div style={{ padding: '8px 10px 0', fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                            показано 8 из {g.rows.length} · скролл внутри группы
                          </div>
                        )}

                        {/* Табуляция табличного вида */}
                        {paged && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', paddingTop: 12, marginTop: 6, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-muted)' }}>
                            <span>показано {shownRows.length} из {g.rows.length}</span>
                            {pages > 1 && (
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                <span onClick={() => setPage(x => Math.max(0, x - 1))}
                                  style={{ ...btnSm(false), cursor: page ? 'pointer' : 'default', opacity: page ? 1 : 0.4 }}>←</span>
                                {Array.from({ length: pages }).map((_, i) => (
                                  <span key={i} onClick={() => setPage(i)}
                                    style={{ borderRadius: 8, padding: '4px 9px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, fontWeight: page === i ? 700 : 600,
                                      background: page === i ? 'var(--accent-tint)' : 'transparent', color: page === i ? 'var(--accent)' : 'var(--text-secondary)' }}>{i + 1}</span>
                                ))}
                                <span onClick={() => setPage(x => Math.min(pages - 1, x + 1))}
                                  style={{ ...btnSm(false), cursor: page < pages - 1 ? 'pointer' : 'default', opacity: page < pages - 1 ? 1 : 0.4 }}>→</span>
                              </span>
                            )}
                            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                              <span>строк на странице</span>
                              <span style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
                                {[100, 300, 500].map(n => (
                                  <span key={n} onClick={() => setPageSize(n)}
                                    style={{ borderRadius: 8, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 12, fontWeight: pageSize === n ? 700 : 600,
                                      background: pageSize === n ? 'var(--accent-tint)' : 'transparent', color: pageSize === n ? 'var(--accent)' : 'var(--text-secondary)' }}>{n}</span>
                                ))}
                              </span>
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}

              {!!data && !data.total && (
                <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                  Очередь пуста — всё под контролем
                </div>
              )}
            </div>
          </div>

          <div style={{ flex: '0 0 414px', maxWidth: 414, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* в работе */}
            <div style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
                <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>В работе</span>
                <span title={filtersOn ? `отфильтровано из ${allRows.length}` : ''}
                  style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-faint)' }}>{filtered.length} сделок</span>
                <span onClick={() => setWorkOpen(o => !o)}
                  style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>
                  {workOpen ? 'свернуть' : 'весь список'}
                </span>
              </div>

              {/* Полоса-разбивка по светофору: сегмент на стадию, ширина — доля,
                  цвет — слой денег из того же PIP, что и сам светофор. */}
              <div style={{ display: 'flex', gap: 2, height: 9, marginBottom: 4 }}>
                {stageMix.map(s => (
                  <span key={s.name} title={`${s.name} · ${s.n}`}
                    style={{ width: s.width, borderRadius: 3, background: s.color }} />
                ))}
                {!stageMix.length && <span style={{ flex: 1, borderRadius: 3, background: 'var(--border-inner)' }} />}
              </div>

              {byStage.map(s => (
                <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', borderTop: '1px solid var(--border-row)' }}>
                  <StageLayerBar os={s.os} h={8} w={8} />
                  <span title={s.name} style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', flex: '1 1 auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{STAGE_SHORT[s.name] || s.name}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{s.n}</span>
                </div>
              ))}
              {!byStage.length && <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 8 }}>Пусто</div>}

              {/* весь список — раскрывается в самой карточке, как в референсе */}
              {workOpen && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-card)' }}>
                  <span style={CAP}>Полный список</span>
                  <div style={{ maxHeight: 260, overflowY: 'auto', overflowX: 'hidden', display: 'flex', flexDirection: 'column', gap: 3, margin: '0 -4px', padding: '0 4px' }}>
                    {filtered.map(r => (
                      <div key={r.id} onClick={() => router.push(`/sales/deals/${r.code || r.id}`)}
                        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 9, border: '1px solid var(--border-inner)', cursor: 'pointer' }}>
                        <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--accent)', flex: '0 0 auto' }}>{r.code || r.id}</span>
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: '1 1 auto' }}>
                          <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {[r.advertiser || r.title, r.brand].filter(Boolean).join(' · ')}
                          </span>
                          <span style={{ fontSize: 9.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {r.our_stage?.name || 'стадия не определена'}
                          </span>
                        </span>
                        <StageLayerBar os={r.our_stage} h={7} w={7} />
                      </div>
                    ))}
                    {!filtered.length && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Пусто</span>}
                  </div>
                </div>
              )}

              {/* загрузка вперёд */}
              <div style={{ marginTop: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={CAP}>Загрузка вперёд</span>
                  <span style={{ display: 'inline-flex', gap: 10, marginBottom: 13 }}>
                    {[['подтв.', 'var(--income)'], ['в проработке', 'var(--text-faint)']].map(([l, c]) => (
                      <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, color: 'var(--text-muted)' }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: c }} />{l}
                      </span>
                    ))}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 6, alignItems: 'end' }}>
                  {forward.map(m => (
                    <div key={m.ym} title={`${m.label}: подтверждено ${m.ok}, в проработке ${m.plan}`}
                      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: m.hot ? 'var(--dot-current-dz)' : 'var(--text-secondary)' }}>{m.total}</span>
                      <span style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 1, width: '100%', height: 62,
                        background: m.hot ? 'var(--warning-tint)' : 'transparent', borderRadius: 4, padding: '0 1px' }}>
                        {/* Каждая сделка — пиксельная полоска: высота столбца читается
                            как счёт, а не как абстрактная площадь. */}
                        {Array.from({ length: m.plan }).map((_, i) => (
                          <span key={`p${i}`} style={{ height: Math.max(2, Math.floor(58 / Math.max(m.max, 1))), background: 'var(--text-faint)', borderRadius: 1 }} />
                        ))}
                        {Array.from({ length: m.ok }).map((_, i) => (
                          <span key={`o${i}`} style={{ height: Math.max(2, Math.floor(58 / Math.max(m.max, 1))), background: 'var(--income)', borderRadius: 1 }} />
                        ))}
                      </span>
                      <span style={{ fontSize: 10, color: m.hot ? 'var(--dot-current-dz)' : 'var(--text-faint)' }}>{m.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <span style={CAP}>Бюджеты под управлением</span>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {budgets.map(([label, sum, note]) => (
                    <div key={label} title={note || ''} style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 12, padding: '9px 11px' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</div>
                      <div style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: sum == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                        {sum == null ? '—' : mln(sum)}
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 8, lineHeight: 1.4 }}>
                  справочно, суммы до НДС — не показатель работы аккаунта
                </div>
              </div>
            </div>

            {/* уведомления */}
            <div style={{ flex: '1 1 0', position: 'relative', minHeight: 360 }}>
              <NotificationsWidget items={notifs}
                onOpen={n => { markRead([n.id]); if (n.href) router.push(n.href) }}
                onAction={n => { markRead([n.id]); if (n.href) router.push(n.href) }}
                onReadAll={() => markRead(null)} />
            </div>
          </div>
        </div>
      </div>

      {moveDeal && <MoveDealDialog deal={moveDeal} toStageKey={moveDeal.__to} toLost={moveDeal.__lost}
        onClose={() => setMoveDeal(null)} onMoved={() => { setMoveDeal(null); load() }} />}
      {confirmFor && (
        <BookingConfirm row={confirmFor} onClose={() => setConfirmFor(null)}
          onPick={(target) => { setMoveDeal({ ...confirmFor, ...target }); setConfirmFor(null) }} />
      )}
      {prepFor && (
        <LaunchPrepDialog row={prepFor} onClose={() => setPrepFor(null)}
          onToLaunch={() => { setMoveDeal({ ...prepFor, __to: 'launch' }); setPrepFor(null) }} />
      )}
      {snoozeFor && <SnoozeDialog row={snoozeFor} onClose={() => setSnoozeFor(null)} onSave={doSnooze} />}
    </div>
  )
}
