/**
 * Дашборд трафика — первый экран контура «Трафики».
 *
 * Вёрстка по дизайн-хендоффу (`docs/handoff_traffic_dashboard/`), приведённая к нашим
 * стандартам (владелец 04.09.2026): стили из общего кита, цвета из `globals.css`,
 * выпадашки на `PortalPopover`, числа через `lib/salesFormat`. Элементы экрана —
 * `components/traffic/dashboardKit.js`, там же записано, что из хендоффа не переехало.
 *
 * **Экран ничего не считает.** Флайт, темп, прогноз, недокрут, доли площадок и пересчёт
 * плана на остаток считает `app/ad/flight.py` — решение владельца 04.09.2026. Здесь
 * остаётся оформление: пороги цвета, геометрия полос, подписи. Два калькулятора
 * разошлись бы молча, правдоподобными числами.
 *
 * Чего на экране НЕТ и почему:
 *   · «Обновить статистику» и «Обновить из сделок» — РК появляются по цепочке, а не по
 *     кнопке (владелец 04.09.2026);
 *   · переключателя тёмной темы — тёмной темы в проекте нет.
 *
 * Пока коннектор не подключён (этап 2c), факта нет ни у одной РК: факт, процент, прогноз
 * и недокрут показываются ПРОЧЕРКОМ, а не нулём. Это норма экрана, а не поломка.
 */
import { Fragment, useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, card, CAP, btnSm, btn, inp, sel, Modal, PortalPopover, ROW_TONE, Z,
  EXT_TONE, ExtChip, ExtCover } from '@/components/salesTableKit'
import { surfaceTag } from '@/lib/dealTitle'
import api, { auth } from '@/lib/api'
import {
  CreativeCounts, CreativeRows, Culprits, DASH, DayWall, Dynamics, KpiRow, PaceBar, Pips,
  GOAL_LABELS, Owners, PlaceActions, ServiceCell, StatusPill, TABLE_LEGEND, TaskDoc, WALL_LEGEND,
  VerifierStrip, WidgetsToggle, byCreative, num, pctTone,
} from '@/components/traffic/dashboardKit'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const DashIcon = ({ size = 21 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M3 3v18h18" /><path d="M7 15l4-5 3 3 5-7" />
  </svg>
)

// Свёрнута ли аналитика — помнится между заходами. Читается ТОЛЬКО в useEffect:
// localStorage на сервере не существует, а первый рендер идёт там же.
const WIDGETS_KEY = 'traffic_dashboard_widgets'

const dm = (d) => (d ? String(d).slice(8, 10) + '.' + String(d).slice(5, 7) : DASH)
const pctText = (v) => (v == null ? DASH : `${Number(v).toFixed(1)} %`)

/* Колонки реестра. Ширины фиксированы у числовых и управляющих: иначе правый край
   строки перестаёт быть выровненным, и это первое, что видно на широком экране. */
/* Колонка описывается ЧЕТВЕРКОЙ: подпись, ширина, ключ сортировки, край.
   Край задан ОДИН РАЗ и применяется и к заголовку, и к ячейке — до 04.09.2026 они
   задавались порознь, и половина колонок разъехалась: пипсы жались вправо под левым
   заголовком, числа стояли по правому краю под левой подписью. */
const COLS = [
  ['', '20px', null, 'left'],
  ['Сделка', '78px', 'deal_code', 'left'],
  ['Название РК', 'minmax(200px,1.6fr)', 'deal_title', 'left'],
  ['Услуга', 'minmax(120px,1fr)', 'product', 'left'],
  ['Площадки', '110px', 'placements_on', 'left'],
  ['Статус РК', '150px', 'status', 'left'],
  // Покрытие внешними системами: две плашки на РК. Стоят СРАЗУ за статусом — так
  // же, как на карточке сделки, чтобы одно и то же читалось в одном месте.
  ['WR · DSP', '58px', null, 'center'],
  ['Период', '120px', 'date_start', 'left'],
  ['План', '104px', 'plan_show', 'right'],
  ['Факт', '104px', 'fact_shows', 'right'],
  // «Выполнение» — полоса во всю ширину ячейки, край ей не нужен: подпись процента
  // стоит под левым краем полосы, «флайт N %» под правым.
  ['Выполнение', 'minmax(150px,1.2fr)', 'done_pct', 'left'],
  ['Прогноз', '104px', 'forecast', 'right'],
  ['Недокрут', '110px', 'under', 'right'],
  ['', '72px', null, 'right'],
]
const GRID = COLS.map(c => c[1]).join(' ')

/* Значение для сортировки. Пустое уходит В КОНЕЦ в обе стороны, а не притворяется нулём:
   РК без факта не «худшая по факту», у неё факта нет — и всплывать в топ ей не за что. */
const EMPTY = { asc: Infinity, desc: -Infinity }
const sortVal = (r, key, dir) => {
  const v = r[key]
  if (v == null || v === '') return typeof r[key] === 'string' ? '' : EMPTY[dir]
  return typeof v === 'string' ? v.toLowerCase() : v
}

/** Флаги строки — дефекты данных и состояние площадок, словами. */
function flagsOf(r) {
  const out = []
  if (!r.plan_show) out.push(['нет плана', 'У сделки не заведён медиаплан'])
  if (!r.placements) out.push(['нет площадок', 'К РК не подключена ни одна площадка'])
  else if (!r.placements_on) out.push(['ни одна не крутит', 'Площадки подключены, но ни одна не запущена'])
  const noWeight = (r.placements || 0) - (r.placements_weighted || 0)
  if (noWeight > 0) out.push([`${noWeight} без веса`, 'Нет индекса в балансировщике — в раскладку не попадут'])
  if (r.plan_show && r.fact_shows == null) out.push(['нет статистики', 'Коннектор ещё не приносил суточный срез'])
  // Недокрут — словом в строке, а не только числом в своей колонке: у законченной РК
  // это итог работы, и он должен читаться без сопоставления двух чисел глазами.
  if (r.under > 0 && r.plan_show) {
    out.push([`недокрут ${Math.round(r.under / r.plan_show * 100)} %`,
      `Не откручено ${num(r.under)} показов из плана`])
  }
  return out
}

export default function TrafficDashboard() {
  const router = useRouter()
  const [data, setData] = useState(null)
  // Открыт РОВНО ОДИН расхлоп (владелец 04.09.2026): в нём таблица площадок и график,
  // и два раскрытых сразу уводят реестр за экран — сравнивать всё равно приходится
  // по строкам, а не по расхлопам.
  const [open, setOpen] = useState(null)      // id открытой РК или null
  const [detail, setDetail] = useState({})    // id РК → площадки
  const [stat, setStat] = useState({})        // id РК → динамика
  const [grain, setGrain] = useState({})      // id РК → день/неделя
  const [range, setRange] = useState({})      // id РК → {from, to} или null
  const [q, setQ] = useState('')
  const [tab, setTab] = useState('all')
  // Чьи РК показывать: 'mine' | 'all' | id учётки. null означает «как решит сервер»:
  // умолчание считается там (рядовому — свои, мастеру — все), и в состояние не кладётся,
  // иначе ответ сервера тут же дёрнул бы вторую загрузку тем же фильтром.
  const [scope, setScope] = useState(null)
  const [widgets, setWidgets] = useState(true)
  const [pop, setPop] = useState(null)        // один открытый поповер на экран
  const [openPlace, setOpenPlace] = useState(null)   // id раскрытой площадки (одна)
  // Вид расхлопа: площадки → креативы или наоборот. Обратный СУММИРУЕТ по площадкам,
  // а не перераспределяет — весов у креативов нет.
  const [byCr, setByCr] = useState(false)
  // Сортировка по шапке. Умолчание (null) — порядок с сервера: месяц по убыванию,
  // внутри код сделки. Он смысловой, поэтому клик его ЗАМЕНЯЕТ, а не дополняет.
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [msg, setMsg] = useState('')     // отказ — красным
  const [note, setNote] = useState('')    // подтверждение — синим

  // Одно сообщение на экране: свежий отказ гасит старое подтверждение и наоборот,
  // иначе рядом висят «РК передана» и «не удалось» от разных действий.
  // `useCallback` здесь не украшение: `load` завёрнут в `useCallback([scope])` и зовёт
  // `fail`. Функция, пересоздаваемая каждый рендер, в его зависимостях дала бы вечный
  // цикл запросов — эта готча в проекте уже стоила отладки.
  const fail = useCallback((t) => { setNote(''); setMsg(t) }, [])
  const say = useCallback((t) => { setMsg(''); setNote(t) }, [])

  /* Права читаются ИЗ СНИМКА в localStorage, поэтому только после монтирования:
     на сервере localStorage нет, и вычисление прямо в теле компонента дало бы
     расхождение разметки. Аргументов у `can` ТРИ — `(perms, section, action)`;
     вызов с двумя молча возвращал false всем, кроме админа (11.09.2026). */
  const [mayEdit, setMayEdit] = useState(false)
  useRefreshOnReturn(() => load())
  useEffect(() => { setMayEdit(can(getPermissions(), 'traffic_dashboard', 'edit')) }, [])

  const load = useCallback(async () => {
    const p = new URLSearchParams()
    if (scope) p.set('scope', scope)
    try {
      const r = await api.get(`/traffic-dashboard/dashboard?${p}`, auth())
      setData(r.data)
      return r.data
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось загрузить дашборд') }
    return null
  }, [scope, fail])
  useEffect(() => { load() }, [load])

  // Сверка с верификатором. Отдельным запросом, а не полем в дашборде: она НЕ про
  // кампании — состояние одно на весь аккаунт Weborama, и тащить его в ответ,
  // отфильтрованный по области видимости, значило бы показывать разным людям разное
  // состояние одного и того же коннектора.
  const [verifier, setVerifier] = useState(null)
  const [wbBusy, setWbBusy] = useState(false)
  const loadVerifier = useCallback(async () => {
    try {
      const r = await api.get('/traffic-dashboard/weborama/stats', auth())
      setVerifier(r.data)
    } catch (e) { setVerifier(null) }
  }, [])
  useEffect(() => { loadVerifier() }, [loadVerifier])
  const refreshVerifier = async () => {
    setWbBusy(true)
    try {
      const r = await api.post('/traffic-dashboard/weborama/stats', {}, auth())
      const d = r.data
      say(`Weborama ${d.start}…${d.end}: строк ${d.rows}`
        + (d.discrepancy ? `, РАСХОЖДЕНИЕ с их итогом ${d.discrepancy}` : '')
        + (d.absent_metrics?.length ? `, не пришли метрики: ${d.absent_metrics.join(', ')}` : '')
        + `, на дашборд легло ${d.written}, без соответствия ${d.skipped}`)
      await Promise.all([loadVerifier(), load()])
    } catch (e) {
      fail(e?.response?.data?.detail || 'Не удалось забрать статистику Weborama')
    } finally { setWbBusy(false) }
  }

  useEffect(() => {
    try {
      const v = localStorage.getItem(WIDGETS_KEY)
      if (v !== null) setWidgets(v === '1')
    } catch (e) { /* приватный режим — просто оставляем умолчание */ }
  }, [])
  const toggleWidgets = () => setWidgets(w => {
    try { localStorage.setItem(WIDGETS_KEY, w ? '0' : '1') } catch (e) { /* см. выше */ }
    return !w
  })

  // Закрытие поповера по клику мимо — как в остальных экранах раздела.
  useEffect(() => {
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setPop(null) }
    document.addEventListener('click', off)
    return () => document.removeEventListener('click', off)
  }, [])

  const loadStat = useCallback(async (id, g, win) => {
    const q = new URLSearchParams({ grain: g || 'day' })
    if (win && win.from) q.set('date_from', win.from)
    if (win && win.to) q.set('date_to', win.to)
    const r = await api.get(`/traffic-dashboard/campaign/${id}/stat?${q}`, auth())
    setStat(s => ({ ...s, [id]: r.data }))
  }, [])

  const toggle = async (id) => {
    const next = open === id ? null : id
    setOpen(next)
    if (next && !detail[id]) {
      const r = await api.get(`/traffic-dashboard/campaign/${id}`, auth())
      setDetail(d => ({ ...d, [id]: r.data }))
      loadStat(id, 'day')
    }
  }

  /* Запуск РК. Если в ней есть ОТКЛЮЧЁННЫЕ площадки — спрашиваем, поднимать ли их:
     «остановлена» могла быть осознанным решением, и включить её молча значит отменить
     чужое решение, ничего об этом не сказав. */
  const startCampaign = async (row) => {
    let withPlaces = false
    if (row.placements_off) {
      withPlaces = window.confirm(
        `В РК ${row.placements_off} отключённых площадок. `
        + 'Включить все, включая остановленные?\n\n'
        + 'Отмена — запустить РК, оставив их выключенными.')
    }
    await setCampaignStatus(row, 'запущена', withPlaces)
  }

  const setCampaignStatus = async (row, s, withPlacements) => {
    setPop(null)
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/status`,
        { status: s, with_placements: !!withPlacements }, auth())
      // Каскад называется вслух: решение над РК меняет 19 строк ниже, и молчаливое
      // изменение того, чего не видно, читается как сбой.
      if (r.data.placements_raised) say(`Площадок поднято: ${r.data.placements_raised}`)
      else if (r.data.placements_stopped) say(s === 'пауза'
        ? `РК на паузе, площадок приостановлено: ${r.data.placements_stopped}`
        : `Площадок остановлено: ${r.data.placements_stopped}`)
      await load()
      if (open === row.id) {
        const d = await api.get(`/traffic-dashboard/campaign/${row.id}`, auth())
        setDetail(x => ({ ...x, [row.id]: d.data }))
      }
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось сменить статус') }
  }

  /* Смена ответственного трафика. Пишет ручка дашборда, а та зовёт ручку сборки —
     назначение живёт в одном месте. Перезагружаем и строку, и расхлоп: ответственный
     виден в расхлопе, а фильтр «чьи РК» в шапке считается по нему же. */
  const setTraffic = async (row, userId) => {
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/traffic-manager`,
        { user_id: userId }, auth())
      const d = await api.get(`/traffic-dashboard/campaign/${row.id}`, auth())
      setDetail(x => ({ ...x, [row.id]: d.data }))
      const fresh = await load()
      // Под фильтром «Мои» переданная РК из списка УХОДИТ — это и есть смысл передачи.
      // Строка исчезает прямо под курсором, поэтому уход объясняется словами, а расхлоп
      // закрывается: иначе он остался бы раскрытым на строке, которой уже нет, и
      // всплыл бы при возврате к «Всем трафикам».
      const gone = fresh && !fresh.rows.some(x => x.id === row.id)
      if (gone) setOpen(null)
      say(userId
        ? `РК ${row.deal_code} передана: ${r.data.name}${gone ? ' — и ушла из вашего среза' : ''}`
        : `РК ${row.deal_code} — ответственный снят`)
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось сменить трафика') }
  }

  /* «Завершить РК»: конец открутки — момент, когда хозяином сделки снова становится
     аккаунт, поэтому кнопка не просто меняет статус, а двигает сделку на «Итоговую
     сверку». Спрашиваем подтверждение: переход стадии назад откатывать некому. */
  const finish = async (row) => {
    const ok = window.confirm(
      `Завершить РК «${row.deal_title}»? Статус станет «окончена», `
      + 'сделка уедет на «Итоговую сверку» — дальше её ведёт аккаунт.')
    if (!ok) return
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/finish`, {}, auth())
      say((r.data.moved ? `РК окончена, сделка на стадии «${r.data.stage}»` : 'РК окончена')
        + (r.data.placements_stopped ? `; площадок остановлено: ${r.data.placements_stopped}` : ''))
      await load()
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось завершить РК') }
  }

  /* ── внешние системы: пиксель Weborama и выгрузка в DSP ────────────────────
     Оба действия НЕОБРАТИМЫ — ни вставку Weborama, ни креатив в DSP нельзя удалить или
     переименовать по их API. Поэтому нажатие идёт в два шага: сперва спрашиваем сервер,
     ЧТО именно произойдёт, и показываем это числами, и только после подтверждения
     отправляем. Подтверждение без цифры «19 площадок» ничем не отличается от случайного
     нажатия, а откатывать нечем. */
  const [extAsk, setExtAsk] = useState(null)     // { row, kind, plan }
  const [extBusy, setExtBusy] = useState(false)

  const askExternal = async (row, kind) => {
    try {
      const r = await api.get(`/traffic-dashboard/campaign/${row.id}/external-plan`, auth())
      setExtAsk({ row, kind, plan: r.data })
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось узнать, что будет сделано') }
  }

  const runExternal = async () => {
    if (!extAsk) return
    const { row, kind } = extAsk
    setExtBusy(true)
    try {
      const r = await api.post(`/traffic-dashboard/campaign/${row.id}/${kind}`, {}, auth())
      const done = r.data.done?.length || 0
      const bad = r.data.failed?.length || 0
      // Отказы называем поимённо: «заведено 14 из 19» без причин заставляет разбираться
      // заново, а причина у каждой своя и уже посчитана сервером.
      say((kind === 'weborama' ? `Пикселей получено: ${done}` : `Креативов заведено: ${done}`)
        + (bad ? `; отказов ${bad} — ${r.data.failed.map(x => `${x.name}: ${x.error}`).join('; ')}` : ''))
      setExtAsk(null)
      const d = await api.get(`/traffic-dashboard/campaign/${row.id}`, auth())
      setDetail(x => ({ ...x, [row.id]: d.data }))
      await load()
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось выполнить') }
    finally { setExtBusy(false) }
  }

  const setCreativeStatus = async (campId, cr, s) => {
    try {
      await api.put(`/traffic-dashboard/creative/${cr.id}/status`, { status: s }, auth())
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось сменить статус креатива') }
  }

  const setPlacementStatus = async (campId, p, s) => {
    setPop(null)
    try {
      await api.put(`/traffic-dashboard/placement/${p.id}/status`, { status: s }, auth())
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
      await load()
    } catch (e) { fail(e?.response?.data?.detail || 'Не удалось сменить статус площадки') }
  }

  const all = data?.rows || []
  const needsAttention = (r) => !r.plan_show || !r.placements || (r.under || 0) > 0
  const TABS = [
    ['all', 'Все', all.length],
    ['running', 'Запущенные', all.filter(r => r.status === 'запущена').length],
    ['attention', 'Требует внимания', all.filter(needsAttention).length],
    ['noplan', 'Без плана', all.filter(r => !r.plan_show).length],
    ['noplaces', 'Без площадок', all.filter(r => !r.placements).length],
  ]
  const onSort = (key) => {
    if (!key) return
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    // Третий клик снимает сортировку и возвращает порядок сервера — иначе из неё
    // невозможно выйти, не перезагрузив страницу.
    if (sortDir === 'asc') setSortDir('desc')
    else { setSortKey(null); setSortDir('asc') }
  }

  const rows = all.filter(r => {
    if (tab === 'running' && r.status !== 'запущена') return false
    if (tab === 'attention' && !needsAttention(r)) return false
    if (tab === 'noplan' && r.plan_show) return false
    if (tab === 'noplaces' && r.placements) return false
    const s = q.trim().toLowerCase()
    return !s || [r.deal_code, r.deal_title, r.stage, r.product].some(
      v => String(v || '').toLowerCase().includes(s))
  })
  if (sortKey) {
    rows.sort((a, b) => {
      const x = sortVal(a, sortKey, sortDir)
      const y = sortVal(b, sortKey, sortDir)
      const c = x < y ? -1 : x > y ? 1 : 0
      return sortDir === 'desc' ? -c : c
    })
  }

  const k = data?.kpi || {}
  const qb = k.queue || {}
  const KPI = [
    { label: 'РК в работе', value: `${k.running ?? 0} / ${k.campaigns ?? 0}`,
      hint: 'запущенных из видимых' },
    // План и факт — по ЗАПУЩЕННЫМ РК (владелец 04.09.2026). Подпись говорит это словами:
    // без неё число молча не сходится с суммой колонки «План» в таблице ниже.
    { label: 'План показов', value: num(k.plan_show),
      hint: `по ${k.plan_campaigns ?? 0} запущенным РК · из медиапланов` },
    { label: 'Факт показов', value: k.fact_shows ? num(k.fact_shows) : DASH,
      color: 'var(--traffic)',
      chip: k.done_pct != null && k.fact_shows ? `${k.done_pct} %` : '',
      chipBg: 'var(--traffic-tint)', chipFg: 'var(--traffic)',
      hint: k.avg_pace != null ? `ожидалось ${Math.round(k.avg_pace * 100)} % по флайтам`
        : 'по запущенным РК' },
    { label: 'Площадок крутит', value: `${k.placements_on ?? 0} / ${k.placements ?? 0}`,
      color: 'var(--blue)', hint: 'запущенных из подключённых' },
    { label: 'Требует внимания', value: String(k.attention ?? 0), unit: 'РК',
      color: k.attention ? 'var(--danger)' : 'var(--text-primary)',
      hint: 'без плана, без площадок, недокрут' },
    { label: 'Креативы на проверке', value: String(qb.waiting ?? 0), unit: 'в очереди',
      color: 'var(--blue)',
      chip: qb.overdue ? `${qb.overdue} просрочено` : '',
      chipBg: 'var(--danger-tint)', chipFg: 'var(--danger)',
      hint: 'соседний экран контура',
      // Переход стоит В ПЛАШКЕ, а не в шапке: счётчик и действие по нему — одно место,
      // и глазу не нужно искать кнопку на другом краю экрана (владелец 04.09.2026).
      action: { label: 'Проверить', onClick: () => router.push('/traffic/queue') } },
  ]

  const noFact = all.filter(r => r.plan_show && r.fact_shows == null).length

  return (
    <>
      <Head><title>Дашборд · Трафики | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 2500, margin: '0 auto', padding: '18px 28px 60px', fontFamily: UI }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 14, flexWrap: 'wrap' }}>
          <span style={{ width: 40, height: 40, borderRadius: 12, flex: '0 0 auto',
            background: 'var(--traffic-tint)', color: 'var(--traffic)',
            display: 'grid', placeItems: 'center' }}><DashIcon /></span>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
              Дашборд трафика</h1>
            <div style={{ ...CAP, marginBottom: 0, marginTop: 2 }}>
              Трафики · открутка рекламных кампаний
              {data?.today ? ` · на ${dm(data.today)}` : ''}
            </div>
          </div>

          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input style={{ ...inp, width: 250 }} value={q} onChange={e => setQ(e.target.value)}
              placeholder="Сделка, РК, услуга, стадия…" />
            {/* Выбор трафика — у всех, а не только у мастера: очередь общая, и «чьи РК»
                здесь фильтр экрана, а не право. В списке ВСЕ активные учётки трафика,
                мастера сверху и со звёздочкой. */}
            <select style={{ ...sel, minWidth: 190 }} value={scope || data?.scope || 'mine'}
              onChange={e => setScope(e.target.value)}>
              <option value="mine">Мои</option>
              <option value="all">Все трафики</option>
              {/* Разбор невыбранного: РК без ответственного. Отдельный пункт, а не
                  человек в списке — фильтр по ОТСУТСТВИЮ назначения. */}
              <option value="none">Не распределено</option>
              {(data?.reps || []).filter(r => r.user_id !== data?.my_user_id).map(r => (
                <option key={r.user_id} value={String(r.user_id)}>
                  {r.is_master ? '★ ' : ''}{r.name}
                </option>
              ))}
            </select>
            <WidgetsToggle open={widgets} onToggle={toggleWidgets} />
          </span>
        </div>

        {!!msg && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--danger)' }}>{msg}</div>}
        {!!note && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--blue)' }}>{note}</div>}

        <div style={{ marginBottom: 14 }}><KpiRow items={KPI} /></div>

        {/* Плашка о дырах: пока коннектор не подключён, факта нет — и экран говорит это
            словами, а не рисует нули. */}
        {!!noFact && (
          <div style={{ ...card, padding: '12px 16px', marginBottom: 14,
            background: 'var(--warning-bg)', borderColor: 'var(--warning-border)' }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning-text)' }}>
              По {noFact} из {all.length} РК факта нет — коннектор статистики ещё не подключён
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
              У этих РК факт, процент, прогноз и недокрут показаны прочерком, а не нулём:
              экран не выдумывает данные, которых нет.
            </div>
          </div>
        )}

        {/* аналитика */}
        {/* Карточки тянутся по высокой (умолчание grid), и это теперь верно: окна
            прокрутки у обоих виджетов одной высоты `WIDGET_BODY`, поэтому растягивать
            нечего — низы сходятся сами. */}
        {widgets && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.25fr)',
            gap: 14, marginBottom: 14 }}>
            <div style={{ ...card, padding: '16px 18px' }}>
              {/* Отступ такой же, как у шапки соседнего виджета: разница в шесть
                  пикселей сдвигает низы карточек, а они стоят рядом. */}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>площадки-виновники</span>
                <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                  поперёк всех видимых РК · недокрут в показах</span>
              </div>
              <Culprits rows={data?.culprits || []} />
            </div>

            <div style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                <span style={{ ...CAP, marginBottom: 0 }}>стена дней</span>
                <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>день против нужного темпа</span>
                <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12 }}>
                  {WALL_LEGEND.map(([l, c]) => (
                    <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5,
                      fontSize: 10.5, color: 'var(--text-muted)' }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}
                    </span>
                  ))}
                </span>
              </div>
              <DayWall rows={data?.wall || []} onOpen={toggle} />
            </div>
          </div>
        )}

        {/* реестр */}
        <div style={{ ...card, padding: '16px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em',
              color: 'var(--text-primary)' }}>Рекламные кампании</span>
            <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>
              {rows.length} из {all.length}</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
              {TABS.map(([key, label, n]) => (
                <button key={key} style={btnSm(tab === key)} onClick={() => setTab(key)}>
                  {label} <span style={{ fontFamily: MONO, opacity: .7 }}>{n}</span>
                </button>
              ))}
            </span>
          </div>

          {/* Легенда и подпись про риску — над колонками: цвет полосы и цвет пипсов
              иначе приходится угадывать, а риска без объяснения читается как дефект. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            marginBottom: 10 }}>
            <span style={{ display: 'inline-flex', gap: 13, flexWrap: 'wrap' }}>
              {TABLE_LEGEND.map(([title, items], gi) => (
                <Fragment key={title}>
                  {gi > 0 && <span style={{ width: 1, alignSelf: 'stretch',
                    background: 'var(--border-inner)' }} />}
                  <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
                    textTransform: 'uppercase', color: 'var(--text-faint)' }}>{title}</span>
                  {items.map(([label, color, border]) => (
                    <span key={label} style={{ display: 'inline-flex', alignItems: 'center',
                      gap: 5, fontSize: 10.5, color: 'var(--text-muted)' }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: color,
                        border: border ? `1px solid ${border}` : 'none', boxSizing: 'border-box' }} />
                      {label}
                    </span>
                  ))}
                </Fragment>
              ))}
            </span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9,
              letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
              риска на полосе — где должны быть по календарю
            </span>
          </div>

          {/* Факт бывает НЕ настоящим. На стенде он весь из демо-скрипта, а тянучка
              статистики ещё не написана — то есть боевому факту пока взяться неоткуда.
              Молчать об этом нельзя: по этим числам перераспределяют объём. */}
          {!!(data?.fact_sources || []).filter(s => s !== 'ms').length && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap',
              padding: '9px 13px', marginBottom: 10, borderRadius: 10,
              background: 'var(--warning-tint)', color: 'var(--warning-text)', fontSize: 12.5 }}>
              <b>Факт не боевой</b>
              <span>
                источник данных: {data.fact_sources.join(', ')}. Эти показы и клики
                не приходили из кабинета — выводы по ним делать нельзя.
              </span>
            </div>
          )}

          <VerifierStrip state={verifier} busy={wbBusy} mayEdit={mayEdit}
            onRefresh={refreshVerifier} />

          {/* Шапка сдвинута на 9 px: у строк ниже 8 px внутреннего отступа плюс 1 px
              рамки — без поправки заголовки уезжают от своих колонок ровно на рамку. */}
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10,
            padding: '0 9px 8px', borderBottom: '1px solid var(--border-card)',
            marginBottom: 4 }}>
            {COLS.map(([label, , key, align], i) => (
              <span key={i} onClick={() => onSort(key)}
                style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
                  textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden',
                  cursor: key ? 'pointer' : 'default',
                  color: sortKey === key ? 'var(--accent)' : 'var(--text-faint)',
                  textAlign: align }}>
                {label}{sortKey === key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
              </span>
            ))}
          </div>

          {rows.map(r => {
            const flags = flagsOf(r)
            const d = detail[r.id]
            // Тон строки — по СРОЧНОСТИ, а не по заполненности карточки (13.09.2026).
            //
            // Было: `r.traffic_rep_id ? normal : today`, то есть кремовая заливка означала
            // «ответственный трафик не назначен». Замер базы: 920 сделок, трафик задан у
            // ТРЁХ. Признак стоял практически на каждой строке — и единственный приём
            // выделения в списке из 57 РК не выделял ничего: таблица читалась как сплошное
            // предупреждение, а пять строк с реальным недокрутом терялись в ней.
            //
            // Теперь заливку получает только то, что требует действия сегодня:
            //   розовая  — недокрут: план не откручен, это потеря денег;
            //   кремовая — РК числится идущей, а крутить нечем (нет плана или площадок);
            //   без тона  — всё остальное. «Ожидает сборки» — нормальное начало жизни
            //               кампании, а не тревога, и красить его нечем.
            //
            // Ответственный трафик из строки не пропал: он остался в подсказке строки и
            // отдельным полем в расхлопе. Он и не был срочностью — он свойство карточки.
            const live = r.status === 'запущена' || r.status === 'пауза'
            const u = (r.under || 0) > 0 ? ROW_TONE.overdue
              : (live && (!r.plan_show || !r.placements)) ? ROW_TONE.today
                : ROW_TONE.normal
            return (
              <div key={r.id}>
                {/* Строка — ОБВЕДЁННАЯ карточка, тонами из общего кита `ROW_TONE`: ровно
                    так устроен реестр дашборда аккаунтов и так же нарисовано в макете.
                    Заливка сама по себе почти белая — читается именно рамка, поэтому
                    подсветка живёт парой, а не одним фоном. Тон выбирается выше, по
                    срочности; большинство строк остаётся без тона намеренно — цвет
                    имеет смысл ровно до тех пор, пока им покрашено меньшинство.
                    Раскрытая строка перекрывает тон: где ты находишься важнее
                    напоминания. */}
                <div onClick={() => toggle(r.id)}
                  title={r.traffic ? `Ответственный трафик: ${r.traffic}`
                    : 'Ответственный трафик не назначен'}
                  style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center',
                    padding: '8px 8px', boxSizing: 'border-box', cursor: 'pointer',
                    // Раскрытая строка срастается с расхлопом: нижние углы выпрямляются
                    // и зазор убирается, иначе карточка и её содержимое выглядят как две
                    // разные плашки, случайно оказавшиеся рядом.
                    borderRadius: open === r.id ? '9px 9px 0 0' : 9,
                    marginBottom: open === r.id ? 0 : 4,
                    border: `1px solid ${u.border}`,
                    borderBottom: open === r.id ? 'none' : `1px solid ${u.border}`,
                    background: open === r.id ? 'var(--accent-tint)' : u.bg }}>
                  <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{open === r.id ? '▾' : '▸'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>
                    {r.deal_code}</span>

                  <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.deal_title}>
                      {r.deal_title}</span>
                    {!!flags.length && (
                      <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                        {flags.map(([t, hint]) => (
                          <span key={t} title={hint} style={{ fontSize: 9.5, padding: '1px 6px',
                            borderRadius: 6, background: 'var(--warning-tint)',
                            color: 'var(--warning-text)', whiteSpace: 'nowrap' }}>{t}</span>
                        ))}
                      </span>
                    )}
                  </span>

                  <ServiceCell product={r.product} color={r.product_color}
                    surface={surfaceTag(r.inventory)} />

                  {/* Ячейка тянется на всю колонку — по её краям и разводятся пипсы
                      со счётчиком. Без ширины `space-between` разводить нечего. */}
                  <span style={{ display: 'block', width: '100%' }}>
                    <Pips total={r.placements} on={r.placements_on}
                      items={r.pips} pace={r.pace} /></span>

                  {/* Статус РК ПОКАЗЫВАЕМ, а не выбираем (владелец 04.09.2026). Он
                      следствие цепочки и действий над РК, а не значение из списка:
                      выпадашка предлагала бы проставить «окончена» вместо того, чтобы
                      завершить кампанию. Меняется он кнопками справа и в расхлопе. */}
                  {/* Ширина по самому длинному статусу («ожидает сборки»): столбец
                      должен читаться ровным краем, а не лесенкой. */}
                  <span><StatusPill value={r.status} w={132} /></span>

                  {/* Свёртка по РК: серый — ни одной площадки, жёлтый — часть,
                      зелёный — все (владелец 09.09.2026). Числа считает сервер
                      тем же расчётом, что и плашки внутри расхлопа: два счёта
                      одного и того же разошлись бы молча. */}
                  <span style={{ display: 'inline-flex', gap: 4, justifySelf: 'center' }}>
                    <ExtCover letter="W" size={17} label="Пиксель Weborama"
                      totals={r.external_totals?.weborama} />
                    <ExtCover letter="D" size={17} label="Заведено в DSP"
                      totals={r.external_totals?.dsp} />
                  </span>

                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, lineHeight: 1.2 }}>
                    <span style={{ fontFamily: MONO, fontSize: 11 }}>
                      {dm(r.date_start)} … {dm(r.date_end)}</span>
                    {/* До старта считаем ДО СТАРТА, а не «осталось»: у РК, которая
                        начнётся послезавтра, «осталось 30 дней» читается как «идёт и
                        вот-вот кончится». Число то же, смысл противоположный. */}
                    <span style={{ fontSize: 9.5,
                      color: r.days_to_start ? 'var(--blue)' : 'var(--text-faint)' }}>
                      {r.days_to_start
                        ? (r.days_to_start === 1 ? 'старт завтра' : `до старта ${r.days_to_start} дн`)
                        : r.days_left == null ? DASH
                          : r.flight_over ? 'флайт закончен' : `${r.days_left} дн осталось`}</span>
                  </span>

                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right' }}>
                    {r.plan_show ? num(r.plan_show) : (
                      <span style={{ color: 'var(--warning-text)' }}>нет МП</span>)}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right',
                    color: r.fact_shows == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                    {num(r.fact_shows)}</span>

                  <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <PaceBar pct={r.done_pct} pace={r.pace} />
                    <span style={{ display: 'flex', justifyContent: 'space-between', gap: 6 }}>
                      <span style={{ fontFamily: MONO, fontSize: 10,
                        color: pctTone(r.done_pct, r.pace) }}>{pctText(r.done_pct)}</span>
                      <span style={{ fontSize: 9.5, color: 'var(--text-faint)' }}>
                        {r.pace == null ? '' : `флайт ${Math.round(r.pace * 100)} %`}</span>
                    </span>
                  </span>

                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right',
                    color: r.forecast == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                    {num(r.forecast)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right',
                    color: r.under ? 'var(--danger)' : 'var(--text-faint)' }}>
                    {r.under == null ? DASH : r.under ? `−${num(r.under)}` : 'нет'}</span>

                  {/* Действия над ВСЕЙ РК — дубль кнопок расхлопа: решение «стоп» часто
                      принимают, глядя на строку, и раскрывать её ради двух кнопок незачем. */}
                  <span style={{ justifySelf: 'end' }} onClick={e => e.stopPropagation()}>
                    {mayEdit && (
                      <PlaceActions
                        status={r.status === 'запущена' ? 'запущен'
                          : r.status === 'пауза' ? 'пауза' : 'ждёт запуска'}
                        canStart={r.status !== 'окончена' && r.status !== 'архив'}
                        onStart={() => startCampaign(r)}
                        onPause={() => setCampaignStatus(r, 'пауза')}
                        onOff={() => setCampaignStatus(r, 'остановлена')} />
                    )}
                  </span>
                </div>

                {/* Расхлоп — продолжение своей карточки: та же рамка, только без
                    верхнего края, иначе он отрывается от строки и читается как
                    отдельный блок посреди реестра. */}
                {open === r.id && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)',
                    gap: 16, padding: '14px 12px 20px', marginBottom: 8,
                    border: '1px solid var(--border-row)', borderTop: 'none',
                    borderRadius: '0 0 9px 9px', background: 'var(--bg-card)' }}>
                    {/* площадки и распределение */}
                    <div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
                        <span style={{ ...CAP, marginBottom: 0 }}>
                          {byCr ? 'креативы и площадки' : 'площадки и распределение'}</span>
                        {/* Обратный вид — та же выборка с другой стороны. Он СУММИРУЕТ по
                            площадкам: объём идёт «вес площадки → план площадки → поровну
                            по креативам», и весов у креативов нет. */}
                        <span style={{ display: 'inline-flex', gap: 5 }}>
                          {[[false, 'по площадкам'], [true, 'по креативам']].map(([v, l]) => (
                            <button key={l} style={btnSm(byCr === v)} onClick={() => setByCr(v)}>{l}</button>
                          ))}
                        </span>
                        {d && (
                          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                            {r.placements_on} из {r.placements} крутят · доля по весам
                          </span>
                        )}
                        {d && d.share_sum > 0 && d.share_sum < 0.99 && (
                          <span style={{ fontSize: 10.5, color: 'var(--warning-text)' }}>
                            сумма долей {Math.round(d.share_sum * 100)} % — часть объёма стоит на выключенных
                          </span>
                        )}
                        {/* Две кнопки внешних систем. Порядок между ними НЕ косметика:
                            пиксель показа вшивается в креатив, поэтому Weborama идёт
                            первой, а DSP без пикселя площадку не берёт. Обе спрашивают
                            подтверждение с числами — см. `askExternal`. */}
                        {d && mayEdit && (
                          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                            <button style={btnSm(false)} onClick={() => askExternal(r, 'weborama')}
                              title="Завести вставки в Weborama и забрать пиксели показа">
                              ПИКСЕЛЬ WR</button>
                            <button style={btnSm(false)} onClick={() => askExternal(r, 'dsp')}
                              title="Выгрузить креативы согласованных площадок в DSP">
                              выгрузить в DSP</button>
                          </span>
                        )}
                      </div>
                      {!d && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>загрузка…</span>}
                      {d && !d.placements.length && (
                        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                          К этой РК не подключена ни одна площадка.
                        </span>
                      )}
                      {/* Обратный вид: креатив → площадки. Группировка по КОРНЮ цепочки
                          доработок — креатив как рекламное сообщение един. Суммирует, а
                          не перераспределяет: весов у креативов нет. */}
                      {d && !!d.placements.length && byCr && (
                        <>
                          {byCreative(d.placements).map(g => (
                            <div key={g.key} style={{ padding: '9px 0',
                              borderBottom: '1px solid var(--border-row)' }}>
                              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 12.5, fontWeight: 600 }}>
                                  {g.name || 'без названия'}</span>
                                <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>
                                  {g.ms_title || DASH}</span>
                                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11 }}>
                                  план {num(g.plan)}</span>
                                <span style={{ fontFamily: MONO, fontSize: 11,
                                  color: g.live ? 'var(--blue)' : 'var(--text-faint)' }}>
                                  в МС {g.live} / {g.places.length}</span>
                              </div>
                              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 6 }}>
                                {g.places.map(pl => (
                                  <span key={pl.id} style={{ display: 'inline-flex', alignItems: 'center',
                                    gap: 6, padding: '3px 9px', borderRadius: 8,
                                    border: '1px solid var(--border-card)', background: 'var(--bg-card)' }}>
                                    <span style={{ fontFamily: MONO, fontSize: 10.5 }}>{pl.domain}</span>
                                    <StatusPill value={pl.status} />
                                    <span style={{ fontFamily: MONO, fontSize: 10,
                                      color: 'var(--text-faint)' }}>{num(pl.plan_show)}</span>
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                          <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 8,
                            lineHeight: 1.45 }}>
                            Обратный вид СУММИРУЕТ по площадкам. Объём идёт «вес площадки →
                            план площадки → поровну по креативам»; весов у креативов нет.
                          </div>
                        </>
                      )}

                      {d && !!d.placements.length && !byCr && (
                        <>
                          <div style={{ display: 'grid', gap: 9, padding: '0 0 6px',
                            gridTemplateColumns: 'minmax(0,1.3fr) 96px 46px 84px 62px 96px 96px 96px 132px 52px 68px',
                            borderBottom: '1px solid var(--border-inner)' }}>
                            {['Площадка', 'Креативы', 'Код', 'Вес', 'Доля', 'План', 'Факт', 'Недокрут', 'Статус', 'WR·DSP', '']
                              .map((h, i) => (
                                <span key={h} style={{ fontFamily: MONO, fontSize: 9,
                                  letterSpacing: '.08em', textTransform: 'uppercase',
                                  color: 'var(--text-faint)',
                                  textAlign: i >= 3 && i <= 7 ? 'right'
                                    : (i === 8 || i === 9) ? 'center' : 'left' }}>{h}</span>
                              ))}
                          </div>
                          {d.placements.map(p => (
                            <Fragment key={p.id}>
                            <div onClick={() => setOpenPlace(x => (x === p.id ? null : p.id))}
                              style={{ display: 'grid', gap: 9, alignItems: 'center', cursor: 'pointer',
                              gridTemplateColumns: 'minmax(0,1.3fr) 96px 46px 84px 62px 96px 96px 96px 132px 52px 68px',
                              padding: '7px 0', borderBottom: '1px solid var(--border-row)' }}>
                              <span style={{ fontFamily: MONO, fontSize: 11.5, overflow: 'hidden',
                                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {p.domain || p.publisher}
                                {p.is_direct && (
                                  <span title="Площадка крутит сама — факт вводится руками"
                                    style={{ marginLeft: 6, fontSize: 9, padding: '1px 5px',
                                      borderRadius: 5, background: 'var(--bg-subtle)',
                                      color: 'var(--text-muted)' }}>сама</span>
                                )}
                              </span>
                              {/* Счётчик креативов — здесь же, где клик раскрывает их
                                  список: число и то, что за ним стоит, в одном месте. */}
                              <span><CreativeCounts counts={p.creative_counts} /></span>
                              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>
                                {p.code || DASH}</span>
                              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                                color: p.no_weight ? 'var(--warning-text)' : 'var(--text-secondary)' }}>
                                {p.no_weight ? 'нет индекса' : num(p.weight)}</span>
                              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                                {p.share ? `${(p.share * 100).toFixed(1)} %` : DASH}</span>
                              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                                {num(p.plan_show)}</span>
                              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                                color: p.fact_shows == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                                {num(p.fact_shows)}</span>
                              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                                color: p.under ? 'var(--danger)' : 'var(--text-faint)' }}>
                                {p.under == null ? DASH : `−${num(p.under)}`}</span>
                              {/* Статус ПОКАЗЫВАЕМ, а меняем кнопками: первые три значения
                                  ставит конвейер согласования, и выпадашка предлагала бы
                                  выбрать то, что человек не выбирает. */}
                              {/* Ширина по самому широкому статусу («ждёт запуска») и
                                  по центру колонки: разной длины плашки в столбце дают
                                  лесенку, и она читается как беспорядок, а не как данные.
                                  То же правило, что в колонке статуса РК. */}
                              <span style={{ justifySelf: 'center' }}>
                                <StatusPill value={p.status} w={116}
                                  title={d.placement_manual.includes(p.status) ? ''
                                    : 'Ставит согласование креативов'} /></span>
                              {/* Внешние системы — СРАЗУ за статусом, как на карточке
                                  сделки. Тот же расчёт, те же буквы, тот же тон: одно
                                  состояние не должно называться на двух экранах
                                  по-разному. */}
                              <span style={{ justifySelf: 'center', display: 'inline-flex', gap: 3 }}>
                                <ExtChip letter="W" size={17}
                                  tone={EXT_TONE[p.external?.weborama?.state] || 'none'}
                                  title={`Weborama: ${p.external?.weborama?.state || 'нет данных'}`
                                    + (p.external?.weborama?.why ? ` — ${p.external.weborama.why}` : '')} />
                                <ExtChip letter="D" size={17}
                                  tone={EXT_TONE[p.external?.dsp?.state] || 'none'}
                                  title={`DSP: ${p.external?.dsp?.state || 'нет данных'}`
                                    + (p.external?.dsp?.why ? ` — ${p.external.dsp.why}` : '')} />
                              </span>
                              <span style={{ justifySelf: 'end' }} onClick={e => e.stopPropagation()}>
                                {mayEdit && (
                                  <PlaceActions status={p.status} canStart={p.can_start}
                                    onStart={() => setPlacementStatus(r.id, p, 'запущен')}
                                    onPause={() => setPlacementStatus(r.id, p, 'пауза')}
                                    onOff={() => setPlacementStatus(r.id, p, 'завершена')} />
                                )}
                              </span>
                            </div>
                            {openPlace === p.id && (
                              <div style={{ padding: '0 0 10px 18px',
                                borderBottom: '1px solid var(--border-row)' }}>
                                <CreativeRows rows={p.creatives} manual={d.creative_manual}
                                  mayEdit={mayEdit}
                                  onStatus={(cr, st) => setCreativeStatus(r.id, cr, st)} />
                              </div>
                            )}
                            </Fragment>
                          ))}
                          <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 8,
                            lineHeight: 1.45 }}>
                            Пауза останавливает открутку, доля площадки в плане сохраняется.
                            Отключение убирает её из распределения — объём уходит остальным.
                          </div>
                        </>
                      )}
                    </div>

                    {/* динамика */}
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10,
                        marginBottom: 10, flexWrap: 'wrap' }}>
                        <span style={{ ...CAP, marginBottom: 0 }}>динамика показов</span>
                        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 5,
                          alignItems: 'center' }}>
                          {[['day', 'дни'], ['week', 'недели']].map(([g, l]) => (
                            <button key={g} style={btnSm((grain[r.id] || 'day') === g)}
                              onClick={() => { setGrain(x => ({ ...x, [r.id]: g }))
                                setRange(x => ({ ...x, [r.id]: null }))
                                loadStat(r.id, g) }}>
                              {l}</button>
                          ))}
                          {/* Третья кнопка — окно дат. Интервал КЛИПУЕТСЯ К ФЛАЙТУ на
                              сервере: выбрал месяц, а РК шла две недели — покажем эти
                              две недели, а не пустоту по краям. */}
                          <span data-pop-root style={{ position: 'relative', display: 'inline-block' }}>
                            <button style={btnSm(!!range[r.id])}
                              onClick={() => setPop(x => (x === `dt${r.id}` ? null : `dt${r.id}`))}>
                              {range[r.id]
                                ? `${dm(range[r.id].from)} — ${dm(range[r.id].to)}`
                                : 'даты'}
                            </button>
                            <PortalPopover open={pop === `dt${r.id}`} minWidth={280}
                              style={{ padding: 12, gap: 9, zIndex: Z.dropdown }}>
                              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                Окно внутри флайта РК
                              </span>
                              {/* Поля тянутся поровну и умеют сжиматься (`minWidth: 0`):
                                  иначе два `input[type=date]` держат собственную ширину,
                                  панель раздувается сверх `minWidth`, и у правого края
                                  экрана из неё уезжает кнопка «показать». */}
                              <span style={{ display: 'flex', gap: 8 }}>
                                <input type="date" style={{ ...inp, fontFamily: MONO, fontSize: 12,
                                  flex: '1 1 0', minWidth: 0, padding: '7px 8px' }}
                                  defaultValue={r.date_start}
                                  onChange={e => setRange(x => ({ ...x,
                                    [r.id]: { ...(x[r.id] || { to: r.date_end }), from: e.target.value } }))} />
                                <input type="date" style={{ ...inp, fontFamily: MONO, fontSize: 12,
                                  flex: '1 1 0', minWidth: 0, padding: '7px 8px' }}
                                  defaultValue={r.date_end}
                                  onChange={e => setRange(x => ({ ...x,
                                    [r.id]: { ...(x[r.id] || { from: r.date_start }), to: e.target.value } }))} />
                              </span>
                              <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span onClick={() => { setRange(x => ({ ...x, [r.id]: null }))
                                  setPop(null); loadStat(r.id, grain[r.id] || 'day') }}
                                  style={{ fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer' }}>
                                  сбросить</span>
                                <span onClick={() => { setPop(null)
                                  loadStat(r.id, grain[r.id] || 'day', range[r.id]) }}
                                  style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--blue)', cursor: 'pointer' }}>
                                  показать</span>
                              </span>
                            </PortalPopover>
                          </span>
                          {/* Подсказка по цветам — в правом верхнем углу блока: без неё
                              светлый и сплошной столбцы читаются как «мало» и «много». */}
                          <span style={{ display: 'inline-flex', gap: 10, marginLeft: 6 }}>
                            {[['план', 'var(--blue-soft)'], ['факт', 'var(--blue)']].map(([l, c]) => (
                              <span key={l} style={{ display: 'inline-flex', alignItems: 'center',
                                gap: 5, fontSize: 10.5, color: 'var(--text-muted)' }}>
                                <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}
                              </span>
                            ))}
                          </span>
                        </span>
                      </div>
                      <Dynamics data={stat[r.id]}
                        label={`${r.deal_code} · ${r.product || ''}`.trim()} />

                      {stat[r.id] && (
                        <>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10,
                            marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border-inner)' }}>
                            {[['средний темп', stat[r.id].speed == null ? DASH : `${num(stat[r.id].speed)} / дн`],
                              ['нужно в день', stat[r.id].need_per_day == null
                                ? (r.flight_over ? 'флайт закончен' : DASH)
                                : `${num(stat[r.id].need_per_day)} / дн`],
                              ['дней осталось', stat[r.id].days_left == null ? DASH : String(stat[r.id].days_left)],
                            ].map(([l, v]) => (
                              <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                <span style={{ ...CAP, marginBottom: 0 }}>{l}</span>
                                <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>{v}</span>
                              </span>
                            ))}
                          </div>

                          {stat[r.id].totals && (
                            /* Третий столбец — ЦЕЛЬ из медиаплана рядом с фактом
                               (владелец 05.09.2026): трафик должен видеть, к чему его
                               открутку будут принимать, не открывая карточку сделки.
                               Строки у цели свои: частота и CR фактом пока не меряются,
                               поэтому столбцы самостоятельные, а не пары «план/факт» —
                               выдуманное соответствие врало бы про то, что сверено. */
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14,
                              marginTop: 12, borderTop: '1px solid var(--border-inner)' }}>
                              {[['сегодня', stat[r.id].totals.today], ['всего за период', stat[r.id].totals.period]]
                                .map(([l, t]) => (
                                  /* Верхний отступ равен отступу плашки цели: три
                                     заголовка обязаны стоять на одной линии, а плашку
                                     подтягивать вверх нельзя — она наезжает на строку
                                     над блоком. Значит опускаем соседей, а не поднимаем её. */
                                  <span key={l} style={{ display: 'flex', flexDirection: 'column',
                                    gap: 3, paddingTop: 10 }}>
                                    <span style={{ ...CAP, marginBottom: 0 }}>{l}</span>
                                    {[['Показы', num(t.shows)], ['Переходы', num(t.clicks)],
                                      ['CTR', t.ctr == null ? DASH : `${t.ctr} %`]].map(([a, b]) => (
                                        <span key={a} style={{ display: 'flex', justifyContent: 'space-between',
                                          fontSize: 11.5 }}>
                                          <span style={{ color: 'var(--text-muted)' }}>{a}</span>
                                          <span style={{ fontFamily: MONO }}>{b}</span>
                                        </span>
                                      ))}
                                  </span>
                                ))}
                              {/* Цель выделена плашкой — тем же приёмом, что «Услуги от»
                                  на карточке сделки: подложка, рамка, скругление 12.
                                  Слева факт, который мы намеряли, справа обязательство
                                  из медиаплана — и это разные по природе числа, а не
                                  третий столбец той же таблицы.

                                  Вверх плашку НЕ подтягиваем: отрицательный отступ ради
                                  выравнивания подписи с соседними наезжал на строку
                                  «дней осталось» над блоком. */}
                              <span style={{ display: 'flex', flexDirection: 'column', gap: 3,
                                background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
                                borderRadius: 12, padding: '10px 12px', alignSelf: 'start' }}>
                                <span style={{ ...CAP, marginBottom: 2 }}>цель · kpi приёмки</span>
                                {GOAL_LABELS.filter(([k]) => d.goals && d.goals[k]).length
                                  ? GOAL_LABELS.filter(([k]) => d.goals && d.goals[k]).map(([k, label]) => (
                                    <span key={k} style={{ display: 'flex', justifyContent: 'space-between',
                                      gap: 8, fontSize: 11.5 }}>
                                      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                                      <span style={{ fontFamily: MONO, textAlign: 'right' }}>
                                        {String(d.goals[k]).trim()}</span>
                                    </span>
                                  ))
                                  : (
                                    <span style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.45 }}>
                                      В медиаплане не заданы — принимать не по чему.
                                    </span>
                                  )}
                              </span>
                            </div>
                          )}

                          <div style={{ marginTop: 12, paddingTop: 10, display: 'flex',
                            gap: 18, alignItems: 'flex-start', flexWrap: 'wrap',
                            borderTop: '1px solid var(--border-inner)' }}>
                            <div style={{ flex: '1 1 340px' }}>
                              {/* Подпись живёт вместе с кнопками: без права правки под ней
                                  было бы пусто, а заголовок обещал бы действия. */}
                              {mayEdit && (<>
                              <span style={{ ...CAP, marginBottom: 8, display: 'block' }}>управление рк</span>
                              {/* Цвета — из макета один в один: основное действие заливкой,
                                  «Стоп» красным контуром (он разрушительный и обязан
                                  отличаться), «Завершить» синим контуром. Подпись первой
                                  кнопки зависит от статуса: пауза и возобновление — одно
                                  состояние, а не два действия. */}
                              <span style={{ display: 'inline-flex', gap: 8, flexWrap: 'wrap' }}>
                                <button onClick={() => setCampaignStatus(r,
                                  r.status === 'запущена' ? 'пауза' : 'запущена')}
                                  style={{ padding: '7px 14px', borderRadius: 10, cursor: 'pointer',
                                    border: '1px solid var(--blue)', background: 'var(--blue)',
                                    color: 'var(--on-accent)', fontFamily: UI, fontSize: 12.5, fontWeight: 700 }}>
                                  {r.status === 'запущена' ? 'Пауза РК'
                                    : r.status === 'пауза' ? 'Возобновить' : 'Принудительный старт'}
                                </button>
                                <button onClick={() => setCampaignStatus(r, 'остановлена')}
                                  style={{ padding: '7px 14px', borderRadius: 10, cursor: 'pointer',
                                    border: '1px solid var(--danger-border)', background: 'var(--bg-card)',
                                    color: 'var(--danger)', fontFamily: UI, fontSize: 12.5, fontWeight: 700 }}>
                                  Стоп
                                </button>
                                <button onClick={() => finish(r)}
                                  style={{ padding: '7px 14px', borderRadius: 10, cursor: 'pointer',
                                    border: '1px solid var(--blue-soft)', background: 'var(--bg-card)',
                                    color: 'var(--blue)', fontFamily: UI, fontSize: 12.5, fontWeight: 700 }}>
                                  Завершить РК
                                </button>
                              </span>
                              {/* Подпись называет НАШУ стадию: в макете стоит «Предварительная
                                  сверка», но в каталоге такой стадии нет — после размещения
                                  идёт «Итоговая сверка». */}
                              <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8,
                                lineHeight: 1.45 }}>
                                «Завершить РК» двигает сделку на стадию «Итоговая сверка» —
                                хозяином снова становится аккаунт.
                              </div>
                              </>)}
                            </div>
                            {/* Послание аккаунта — между кнопками и ответственными:
                                читают его перед тем, как что-то нажать. */}
                            <TaskDoc text={d.traffic_brief} deal={r.deal_code}
                              title={r.deal_title} />
                            <Owners owners={d.owners} reps={data?.reps}
                              onPick={uid => setTraffic(r, uid)} />
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {!rows.length && (
            <div style={{ padding: '40px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
              {all.length ? 'Под фильтр ничего не попало.'
                : (scope || data?.scope) === 'none'
                  ? 'Нераспределённых РК нет: ответственный трафик стоит на каждой.'
                  : (scope || data?.scope) !== 'all'
                    ? 'На выбранного трафика не записано ни одной РК. Ответственного ставят в расхлопе РК или на карточке сделки — переключитесь на «Все трафики», чтобы увидеть остальные.'
                    : 'Рекламных кампаний нет: они появляются, когда сделка входит в стадию «Сборка».'}
            </div>
          )}

          <div style={{ ...CAP, marginBottom: 0, marginTop: 12 }}>
            план — из медиаплана сделки · факт — суточный срез коннектора
            {data?.fact_last_ingest
              ? ` · последнее поступление факта: ${String(data.fact_last_ingest).slice(0, 16).replace('T', ' ')}`
              : ' · факт не поступал ни разу'}{(data?.fact_sources || []).length ? ` · источники факта: ${data.fact_sources.join(', ')}` : ''}
          </div>
        </div>
      </div>

      {/* Подтверждение внешнего действия. Числа берутся с СЕРВЕРА (`external-plan`), а не
          пересчитываются здесь: экран ничего не считает, и второй счёт разошёлся бы с
          тем, что действительно уйдёт наружу. */}
      {extAsk && (() => {
        const wb = extAsk.kind === 'weborama'
        const pl = wb ? extAsk.plan.weborama : extAsk.plan.dsp
        const blocked = wb ? pl.blocked : null
        // Кнопка не обещает того, чего сервер не сделает: у Weborama `blocked` —
        // причина отказа целиком, и «Завести 10 вставок» при ней означало бы
        // нажатие ради 400-го ответа.
        const n = wb ? (pl.blocked ? 0 : pl.todo) : pl.placements
        return (
          <Modal width={620} onClose={() => setExtAsk(null)}
            title={wb ? 'Получить пиксели Weborama' : 'Выгрузить креативы в DSP'}
            summary={`РК ${extAsk.row.deal_code} · ${extAsk.row.deal_title}`}
            footer={(
              <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button style={btn(false)} onClick={() => setExtAsk(null)}>Отмена</button>
                <button style={{ ...btn(true), opacity: (!n || extBusy) ? 0.5 : 1,
                  cursor: (!n || extBusy) ? 'not-allowed' : 'pointer' }}
                  disabled={!n || extBusy} onClick={runExternal}>
                  {extBusy ? 'Идёт обмен…' : (wb ? `Завести ${n} вставок` : `Выгрузить ${n} площадок`)}
                </button>
              </span>
            )}>
            <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
              {blocked && (
                <div style={{ padding: '9px 12px', borderRadius: 9, fontSize: 12.5,
                  background: 'var(--warning-tint)', color: 'var(--warning-text)' }}>{blocked}</div>
              )}
              {wb ? (
                <>
                  <div>Площадок готово к заведению: <b>{pl.ready ?? 0}</b>.
                    Пиксель уже есть у <b>{pl.have ?? 0}</b>, будет получено ещё <b>{pl.todo ?? 0}</b>.</div>
                  {!!pl.not_ready && (
                    <div style={{ color: 'var(--text-muted)' }}>
                      Ещё {pl.not_ready} площадок не дошли до «ждёт запуска» — им рано.</div>
                  )}
                  {!!pl.skipped_direct && (
                    <div style={{ color: 'var(--text-muted)' }}>
                      {pl.skipped_direct} площадок крутят сами — они не заводятся.</div>
                  )}
                  {!!pl.landing && (
                    <div style={{ color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                      Посадочная кампании: {pl.landing}</div>
                  )}
                  <div style={{ color: 'var(--text-faint)', fontSize: 11.5 }}>
                    Заведение необратимо: вставку у Weborama нельзя ни удалить, ни переименовать.
                    Уже заведённые пропускаются.</div>
                </>
              ) : (
                <>
                  <div>Будет заведено креативов: <b>{pl.todo ?? 0}</b> на <b>{pl.placements ?? 0}</b> площадках.
                    Уже в кабинете: <b>{pl.have ?? 0}</b> из {pl.creatives ?? 0}.</div>
                  {!pl.campaign_ready && (
                    <div style={{ color: 'var(--text-muted)' }}>
                      Кампания в DSP ещё не заведена — она будет создана первой, в статусе
                      «остановлена».</div>
                  )}
                  {!!pl.blocked?.length && (
                    <div>
                      <div style={{ ...CAP, marginBottom: 4 }}>не пойдут</div>
                      {pl.blocked.map(b => (
                        <div key={b.why} style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          {b.count} × {b.why}</div>
                      ))}
                    </div>
                  )}
                  <div style={{ color: 'var(--text-faint)', fontSize: 11.5 }}>
                    В каждый креатив вшиваются пиксель Weborama, счётчик площадки и скрипт
                    видимости. Заведённый креатив удалить по API нечем.</div>
                </>
              )}
            </div>
          </Modal>
        )
      })()}
    </>
  )
}
