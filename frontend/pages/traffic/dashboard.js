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
 * Раскладка v2 — хендофф `design_handoff_traffic_expand_v2` (17.11.2026): шапка, виджеты со строкой-итогом, строка
 * РК, пульт, площадки группами, аналитика 680px справа. Куски — в `components/traffic/v2/`, здесь состояние и действия.
 * «Обновить из сделок» — только админу (инструмент разбора, крон делает то же в 06:00).
 *
 * Пока коннектор не подключён (этап 2c), факта нет ни у одной РК: факт, процент, прогноз
 * и недокрут показываются ПРОЧЕРКОМ, а не нулём. Это норма экрана, а не поломка.
 */
import { Collapse } from '@/lib/motion'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { useNavObject } from '@/lib/navObject'
import { MONO, UI, card, CAP, btn, inp, Modal } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { downloadDealCreatives } from '@/lib/dealDocs'
import StartRkModal from '@/components/traffic/StartRkModal'
import DspRefreshModal from '@/components/traffic/DspRefreshModal'
import TempoModal from '@/components/traffic/TempoModal'
import AdfoxImportModal from '@/components/traffic/AdfoxImportModal'
import { useTargetingCampaign } from '@/components/traffic/TargetingCampaign'
import RkLog from '@/components/traffic/RkLog'
import CulpritsWidget from '@/components/traffic/platforms/CulpritsWidget'
import { toReport } from '@/lib/platformsReport'
import { downloadFile } from '@/lib/download'
import { DASH, KpiRow, num } from '@/components/traffic/dashboardKit'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { isAdmin as isAdminNow } from '@/lib/auth'
import HungAttempts from '@/components/traffic/HungAttempts'
import { detailText } from '@/lib/loadError'
import DashHeader, { ListPanel } from '@/components/traffic/v2/DashHeader'
import RkRow, { RkHead } from '@/components/traffic/v2/RkRow'
import { nextRkSort, sortRk } from '@/components/traffic/v2/rkModel'
import RkPult, { ANALYTICS_W } from '@/components/traffic/v2/RkPult'
import { DayWallV2, WidgetsSummary } from '@/components/traffic/v2/DayWallV2'
import SitesPanel from '@/components/traffic/v2/SitesPanel'
import RkAnalytics from '@/components/traffic/v2/RkAnalytics'
import ReallocModal from '@/components/traffic/ReallocModal'

// Свёрнута ли аналитика — помнится между заходами. Читается ТОЛЬКО в useEffect:
// localStorage на сервере не существует, а первый рендер идёт там же. Умолчание —
// свёрнуто; сохранённый выбор человека сильнее умолчания и в обе стороны.
const WIDGETS_KEY = 'traffic_dashboard_widgets'


// Таргетинги, которые уйдут в DSP вместе с выгрузкой (app/dsp/targeting.py). Показываются
// всегда: решение о настройках принимается по живым числам этой РК. Пока выключатель
// `dsp_targeting_enabled` не включён, в DSP они не отправляются — и это сказано словами.
const TargetingPreview = ({ t }) => {
  if (!t) return null
  if (t.error) {
    return <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>Таргетинги не собрались: {t.error}</div>
  }
  const line = (label, value) => (
    <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 10, fontSize: 12.5 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5 }}>{value}</span>
    </div>
  )
  return (
    <div style={{ display: 'grid', gap: 5, padding: '10px 12px', borderRadius: 9,
      background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ ...CAP, marginBottom: 0 }}>Таргетинги</span>
        <span style={{ fontSize: 11.5, fontWeight: 700,
          color: t.enabled ? 'var(--ok-fg)' : 'var(--warning-text)' }}>
          {t.enabled ? 'будут поставлены' : 'выключены настройкой dsp_targeting_enabled'}</span>
      </div>
      {line('Источники', `${(t.sources || []).join(', ')} · ставка ${t.source_bid}`)}
      {line('Регион', (t.geo || []).join(' + '))}
      {line('Частота', `${(t.frequency || []).join(', ')}${t.frequency_from_plan != null
        ? ` · из МП: ${t.frequency_from_plan}` : ' · в МП нет — по умолчанию 5'}`)}
      {line('Соцдем', `${(t.socdem || []).join(', ')} · ${t.socdem_from_plan ? `из МП: ${t.socdem_from_plan}` : 'по умолчанию М/Ж 25–55'}`)}
      {line('Блоки площадок', `${t.blocks} блоков у ${t.creatives_with_blocks} креативов`
        + (t.creatives_without_blocks?.length ? ` · без блоков: ${t.creatives_without_blocks.length}` : ''))}
    </div>
  )
}

// Обмен с внешней системой идёт десятки секунд: без признака жизни окно выглядит
// зависшим, и человек жмёт повторно или закрывает (владелец 28.09.2026).
const ExtProgress = ({ wb, n }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '18px 4px' }}>
    <style>{''}</style>
    <span style={{ width: 22, height: 22, borderRadius: '50%', flex: '0 0 22px',
      border: '3px solid var(--accent-tint)', borderTopColor: 'var(--accent)',
      animation: 'm-spin .8s linear infinite' }} />
    <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 13.5, fontWeight: 700 }}>
        {wb ? `Заводим вставки в Weborama (${n})…` : `Выгружаем креативы в DSP (${n} площадок)…`}</span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Идёт обмен — не закрывайте окно. Итог появится здесь же.</span>
    </span>
  </div>
)

const ExtResult = ({ wb, result }) => {
  if (result.error) {
    return (
      <div style={{ padding: '10px 12px', borderRadius: 9, fontSize: 13, background: 'var(--danger-tint)',
        color: 'var(--danger-fg)' }}>Не выполнено: {result.error}</div>
    )
  }
  const { done, failed, targeting: tg } = result
  return (
    <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
      {!!tg && (
        <div style={{ fontSize: 12.5, color: tg.skipped ? 'var(--text-muted)'
          : (tg.failed?.length ? 'var(--warning-text)' : 'var(--ok-fg)') }}>
          Таргетинги: {tg.skipped ? 'не отправлялись (ждут решения по настройкам)'
            : `поставлено ${tg.done?.length || 0}${tg.failed?.length
              ? ` · отказов ${tg.failed.length}: ${tg.failed.map(f => `${f.what} — ${f.error}`).join('; ')}` : ''}`}
        </div>
      )}
      <div style={{ padding: '10px 12px', borderRadius: 9, fontWeight: 700,
        background: failed.length ? 'var(--warning-tint)' : 'var(--ok-tint)',
        color: failed.length ? 'var(--warning-text)' : 'var(--ok-fg)' }}>
        {wb ? 'Пикселей получено' : 'Креативов заведено'}: {done.length}
        {failed.length ? ` · отказов: ${failed.length}` : ' · без отказов'}
      </div>
      {!!failed.length && (
        <div style={{ display: 'grid', gap: 6 }}>
          {failed.map((x, i) => (
            <div key={i} style={{ fontSize: 12.5, lineHeight: 1.5 }}>
              <b>{x.name}</b> — <span style={{ color: 'var(--danger-fg)' }}>{x.error}</span>
            </div>
          ))}
        </div>
      )}
      {/* Заведено, но ссылка правила площадки не встала: в ней нет кликового макроса DSP
          (05.10.2026, код 2051) — в баннере оставлен макрос DSP. */}
      {!!(result.warnings || []).length && (
        <div style={{ display: 'grid', gap: 6 }}>
          {result.warnings.map((x, i) => (
            <div key={i} style={{ fontSize: 12.5, lineHeight: 1.5 }}>
              <b>{x.name}</b> — <span style={{ color: 'var(--warning-text)' }}>{x.warning}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* Привязка РК к проекту и кампании, уже заведённым в кабинете Weborama (владелец
   28.09.2026). Номера — из их кабинета: список по API нам не прочитать. После привязки
   кнопка W заводит только вставки, а не второй проект с тем же именем. */
function WrAttach({ campaignId, pl, onDone }) {
  const [open, setOpen] = useState(false)
  const [proj, setProj] = useState(pl.project_id || '')
  const [camp, setCamp] = useState(pl.campaign_id || '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.post(`/traffic-dashboard/campaign/${campaignId}/weborama/attach`,
        { project_id: pl.project_id ? null : proj.trim(), campaign_id: camp.trim() }, auth())
      onDone('РК привязана к проекту и кампании Weborama')
    } catch (e) { setErr(detailText(e, 'Не удалось привязать')) }
    setBusy(false)
  }
  if (!open) return (
    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
      Проект и кампания уже заведены в Weborama?{' '}
      <span onClick={() => setOpen(true)} style={{ color: 'var(--accent)', cursor: 'pointer' }}>Привязать</span>
    </div>
  )
  const box = { ...inp, width: 150, fontFamily: MONO }
  return (
    <div style={{ display: 'grid', gap: 8, padding: '10px 12px', borderRadius: 9, border: '1px solid var(--border-card)' }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Номера из кабинета Weborama. Связь перезаписать нельзя — сверьтесь с кабинетом.
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12 }}>проект</span>
        <input value={proj} disabled={!!pl.project_id} onChange={e => setProj(e.target.value.replace(/\D/g, ''))} style={box} />
        <span style={{ fontSize: 12 }}>кампания</span>
        <input value={camp} onChange={e => setCamp(e.target.value.replace(/\D/g, ''))} style={box} />
        <button style={btn(true)} disabled={busy || !camp || (!pl.project_id && !proj)} onClick={send}>
          {busy ? '…' : 'Привязать'}</button>
      </div>
      {!!err && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{err}</div>}
    </div>
  )
}


export default function TrafficDashboard() {
  const router = useRouter()
  const [data, setData] = useState(null)
  // Открыт РОВНО ОДИН расхлоп (владелец 04.09.2026): в нём таблица площадок и график,
  // и два раскрытых сразу уводят реестр за экран — сравнивать всё равно приходится
  // по строкам, а не по расхлопам.
  const [open, setOpen] = useState(null)      // id открытой РК или null
  // Панель списка прилипла к меню? Подложка нужна только тогда: в обычном положении она закрашивала тень виджетов над ней (18.11.2026)
  const stickyRef = useRef(null)
  const [stuck, setStuck] = useState(false)
  useEffect(() => {
    const check = () => {
      const el = stickyRef.current
      if (!el) return
      const top = parseFloat(getComputedStyle(el).top) || 0
      setStuck(el.getBoundingClientRect().top <= top + 0.5 && window.scrollY > 0)
    }
    check()
    window.addEventListener('scroll', check, { passive: true })
    window.addEventListener('resize', check)
    return () => { window.removeEventListener('scroll', check); window.removeEventListener('resize', check) }
  }, [])
  const [detail, setDetail] = useState({})    // id РК → площадки
  // Лог РК (05.11.2026): открыт ли и записи — по id РК; грузится при первом открытии, счётчик до того — из расхлопа
  const [logOpen, setLogOpen] = useState({})
  const [rkNotes, setRkNotes] = useState({})
  const [stat, setStat] = useState({})        // id РК → динамика
  const [grain, setGrain] = useState({})      // id РК → день/неделя
  const [range, setRange] = useState({})      // id РК → {from, to} или null
  const [q, setQ] = useState('')
  const [rkSort, setRkSort] = useState(null)   // сортировка списка РК по заголовку; null — порядок сервера
  const [tab, setTab] = useState('all')
  // Чьи РК показывать: 'mine' | 'all' | id учётки. null означает «как решит сервер»:
  // умолчание считается там (рядовому — свои, мастеру — все), и в состояние не кладётся,
  // иначе ответ сервера тут же дёрнул бы вторую загрузку тем же фильтром.
  const [scope, setScope] = useState(null)
  // Архив — РК закрытых сделок (владелец 22.10.2026): по умолчанию скрыт, как «скрыть архив» в продажах.
  const [archive, setArchive] = useState(false)
  // Аналитика по умолчанию СВЁРНУТА (владелец 17.09.2026). Экран открывают ради
  // реестра РК: два виджета наверху отодвигают строки вниз, и первое, что видит
  // трафик, — не его работа. Кому аналитика нужна постоянно, разворачивает её один
  // раз: выбор помнится между заходами и переживает перезаход.
  const [widgets, setWidgets] = useState(false)
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
  // «Отчёт по РК» — своё право, его раздаёт владелец (13.10.2026).
  const [mayReport, setMayReport] = useState(false)
  useEffect(() => { setMayReport(can(getPermissions(), 'rk_report', 'view')) }, [])
  /* Роль читаем В useEffect, а не при рендере: `localStorage` на сервере не существует,
     и обращение к нему в теле компонента роняет страницу при SSR. */
  const [isAdmin, setIsAdmin] = useState(false)
  useEffect(() => { setIsAdmin(isAdminNow()) }, [])

  const load = useCallback(async () => {
    const p = new URLSearchParams()
    if (scope) p.set('scope', scope)
    if (archive) p.set('archive', 'true')
    try {
      const r = await api.get(`/traffic-dashboard/dashboard?${p}`, auth())
      setData(r.data)
      return r.data
    } catch (e) { fail(detailText(e, 'Не удалось загрузить дашборд')) }
    return null
  }, [scope, archive, fail])
  useEffect(() => { load() }, [load])
  // Виджет «Площадки-виновники» кормится отчётом «Площадки × РК» (хендофф 05.11.2026) — тем же фильтром трафика.
  const [platRaw, setPlatRaw] = useState(null)
  const [platErr, setPlatErr] = useState('')
  // Грузится и при свёрнутых виджетах: строка-итог показывает те же числа виновников (v2, 17.11.2026).
  const loadPlat = useCallback(() => {
    const p = new URLSearchParams()
    if (scope) p.set('scope', scope)
    api.get(`/traffic-dashboard/platforms?${p}`, auth())
      .then(r => { setPlatRaw(r.data); setPlatErr('') })
      .catch(e => setPlatErr(detailText(e, 'Не удалось загрузить площадки-виновники')))
  }, [scope])
  useEffect(() => { loadPlat() }, [loadPlat])
  useRefreshOnReturn(loadPlat)
  const platData = useMemo(() => toReport(platRaw), [platRaw])

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
  // Сводка «всё ли в порядке с РК» — записанный ночной прогон проверок (`app/ad/rk_check.py`). Отдельным
  // запросом: она не про строки реестра и не должна ронять экран, если прогонов ещё не было.
  const [summary, setSummary] = useState(null)
  const loadSummary = useCallback(async () => {
    try {
      const r = await api.get('/rk-check/summary', auth())
      setSummary(r.data)
    } catch (e) { setSummary(null) }
  }, [])
  useEffect(() => { loadSummary() }, [loadSummary])
  /* ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ — только админу.

     Кнопку «Обновить из сделок» убрали 04.09.2026 со словами «РК появляются по цепочке,
     а не по кнопке». Мысль верная, но 17.09.2026 выяснилось, что цепочка эту сборку не
     зовёт ВООБЩЕ: ЕРИД согласованного креатива не доезжал до кампании, пока прогон не
     запустили руками из консоли. Пока вызов из цепочки не сделан, ручной ход должен
     быть у того, кто разбирает такие случаи, — то есть у админа, и только у него: это
     не рабочее действие трафика, а инструмент разбора. Крон делает то же по расписанию.
  */
  const [syncing, setSyncing] = useState(false)
  const [syncSaid, setSyncSaid] = useState('')
  const forceSync = async () => {
    setSyncing(true); setSyncSaid('')
    try {
      const r = await api.post('/traffic-dashboard/sync', {}, auth())
      // Говорим ЧИСЛАМИ сервера, а не «готово»: «готово» одинаково выглядит и когда
      // прогон собрал сотню строк, и когда не сделал ничего.
      setSyncSaid(`РК создано ${r.data?.created ?? 0}, обновлено ${r.data?.updated ?? 0}, `
        + `площадок ${r.data?.placements_added ?? 0}, креативов `
        + `${(r.data?.creatives_added ?? 0) + (r.data?.creatives_updated ?? 0)}`)
      await load()
    } catch (e) { setSyncSaid(detailText(e, 'Не удалось обновить')) }
    finally { setSyncing(false) }
  }

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
      fail(detailText(e, 'Не удалось забрать статистику Weborama'))
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

  const loadStat = useCallback(async (id, g, win) => {
    const q = new URLSearchParams({ grain: g || 'day' })
    if (win && win.from) q.set('date_from', win.from)
    if (win && win.to) q.set('date_to', win.to)
    const r = await api.get(`/traffic-dashboard/campaign/${id}/stat?${q}`, auth())
    setStat(s => ({ ...s, [id]: r.data }))
  }, [])

  // Раскрытая РК встаёт строкой под липкую шапку: расхлоп виден целиком сразу, без ручной прокрутки
  // (владелец 11.10.2026). Прокрутка плавная и разовая — колесо после неё работает как обычно.
  // Ждём кадр и долю секунды: если сверху закрылась прежняя открытая РК, разметка ещё съезжает.
  const alignRow = (id) => {
    setTimeout(() => {
      const el = document.getElementById(`rk-row-${id}`)
      if (!el) return
      // Высота липкой шапки: измеряем, но не меньше 58px (её штатная высота) — иначе при нулевом замере строка
      // РК уходит под шапку (11.10.2026, снимок владельца).
      const navH = Math.max(58, ...Array.from(document.querySelectorAll('[data-navbar]')).map(n => n.getBoundingClientRect().height))
        + (document.querySelector('[data-tp-sticky]')?.getBoundingClientRect().height || 0)   // закреплённая панель списка (18.11.2026)
      const top = el.getBoundingClientRect().top + window.scrollY - navH - 8
      window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
    }, 60)
  }
  const toggle = async (id) => {
    const next = open === id ? null : id
    setOpen(next)
    if (next) alignRow(next)
    if (next && !detail[id]) {
      const r = await api.get(`/traffic-dashboard/campaign/${id}`, auth())
      setDetail(d => ({ ...d, [id]: r.data }))
      loadStat(id, 'day')
    }
  }

  /* Запуск РК — окном с планом по каждой площадке (владелец 01.10.2026): что поднимется,
     что уже крутит, что не поднимется и почему. Прежний confirm спрашивал только про
     отключённые и не поднимал «ждёт запуска» вовсе. */
  const startCampaign = (row) => { setStartAsk(row) }

  /* Сверка с DSP после нажатия (владелец 30.09.2026): статусы перечитываются из DSP,
     лимиты креативов при запуске уходят сразу. Расхождение или сбой сверки — вслух. */
  const dspCheckNote = (chk) => {
    if (!chk) return ''
    // Отказ DSP по отдельному креативу (К-6, 01.10.2026) — видно всегда, даже когда
    // перечитать статусы не вышло: кампания принята, а этот креатив не переключился.
    const refused = chk.refused?.length
      ? ' ⚠ DSP не принял: ' + chk.refused.map(r => `${r.what} → ${r.want}`).join('; ') : ''
    if (chk.error) return ` ⚠ ${chk.error}` + refused
    if (chk.mismatch?.length) return ' ⚠ DSP в другом состоянии: '
      + chk.mismatch.map(m => `${m.what} — ждали ${m.want}, в DSP ${m.got || 'нет ответа'}`).join('; ') + refused
    const lim = chk.limits
    return ' · сверено с DSP' + (lim?.updated ? `, лимитов обновлено: ${lim.updated}` : '')
      + (lim?.failed?.length ? `, лимит не ушёл: ${lim.failed.length}` : '')
  }

  const setCampaignStatus = async (row, s, withPlacements) => {
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/status`,
        { status: s, with_placements: !!withPlacements }, auth())
      // Каскад называется вслух: решение над РК меняет 19 строк ниже, и молчаливое
      // изменение того, чего не видно, читается как сбой.
      // Кнопка управляет и кампанией в DSP — это тоже называется вслух.
      const inDsp = { LAUNCHED: 'запущена', STOPPED: 'остановлена', ARCHIVE: 'в архиве' }[r.data.dsp_status]
      const dspNote = inDsp ? `. В DSP кампания ${inDsp}${dspCheckNote(r.data.dsp_check)}` : ''
      if (r.data.placements_raised) say(`Площадок поднято: ${r.data.placements_raised}${dspNote}`)
      else if (r.data.placements_stopped) say((s === 'пауза'
        ? `РК на паузе, площадок приостановлено: ${r.data.placements_stopped}`
        : `Площадок остановлено: ${r.data.placements_stopped}`) + dspNote)
      else if (dspNote) say(dspNote.slice(2))
      await load()
      if (open === row.id) {
        const d = await api.get(`/traffic-dashboard/campaign/${row.id}`, auth())
        setDetail(x => ({ ...x, [row.id]: d.data }))
      }
    } catch (e) { fail(detailText(e, 'Не удалось сменить статус')) }
  }

  /* Смена ответственного трафика. Пишет ручка дашборда, а та зовёт ручку сборки —
     назначение живёт в одном месте. Перезагружаем и строку, и расхлоп: ответственный
     виден в расхлопе, а фильтр «чьи РК» в шапке считается по нему же. */
  const toggleLog = (row) => {
    const open = !logOpen[row.id]
    setLogOpen(o => ({ ...o, [row.id]: open }))
    if (open && !rkNotes[row.id]) {
      api.get(`/traffic-dashboard/campaign/${row.id}/notes`, auth())
        .then(r => setRkNotes(n => ({ ...n, [row.id]: r.data.items || [] })))
        .catch(() => setRkNotes(n => ({ ...n, [row.id]: [] })))
    }
  }
  // Ошибка — исключением с текстом сервера: компонент оставит запись в поле и покажет причину
  const addNote = async (row, note) => {
    try {
      const saved = (await api.post(`/traffic-dashboard/campaign/${row.id}/notes`, note, auth())).data
      setRkNotes(n => ({ ...n, [row.id]: [saved, ...(n[row.id] || [])] }))
      return saved
    } catch (e) {
      throw new Error(detailText(e, 'Не сохранилось — текст остался в поле, попробуйте ещё раз'))
    }
  }

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
    } catch (e) { fail(detailText(e, 'Не удалось сменить трафика')) }
  }

  /* «Завершить РК»: конец открутки — момент, когда хозяином сделки снова становится
     аккаунт, поэтому кнопка не просто меняет статус, а двигает сделку на «Итоговую
     сверку». Спрашиваем подтверждение: переход стадии назад откатывать некому. */
  const finish = async (row) => {
    const ok = window.confirm(
      `Завершить РК «${row.deal_title}»? Статус станет «окончена», `
      + 'сделка уедет на «Итоговую сверку» — дальше её ведёт аккаунт. '
      + 'Креативы, которые ещё ждут согласования площадок, будут отозваны.')
    if (!ok) return
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/finish`, {}, auth())
      say((r.data.moved ? `РК окончена, сделка на стадии «${r.data.stage}»` : 'РК окончена')
        + (r.data.placements_stopped ? `; площадок остановлено: ${r.data.placements_stopped}` : '')
        + (r.data.approvals_withdrawn ? `; отозвано согласований: ${r.data.approvals_withdrawn}` : '')
        + (r.data.withdraw_errors?.length ? `; не отозвано: ${r.data.withdraw_errors.length}` : ''))
      await load()
    } catch (e) { fail(detailText(e, 'Не удалось завершить РК')) }
  }

  /* ── внешние системы: пиксель Weborama и выгрузка в DSP ────────────────────
     Оба действия НЕОБРАТИМЫ — ни вставку Weborama, ни креатив в DSP нельзя удалить или
     переименовать по их API. Поэтому нажатие идёт в два шага: сперва спрашиваем сервер,
     ЧТО именно произойдёт, и показываем это числами, и только после подтверждения
     отправляем. Подтверждение без цифры «19 площадок» ничем не отличается от случайного
     нажатия, а откатывать нечем. */
  const [extAsk, setExtAsk] = useState(null)     // { row, kind, plan }
  const [startAsk, setStartAsk] = useState(null) // строка РК в окне запуска
  const [boostAsk, setBoostAsk] = useState(null)       // строка РК в окне «Темп размещения»
  const [reallocAsk, setReallocAsk] = useState(null)   // строка РК в окне «Перераспределить» (v2: кнопка у «Откуда недокрут»)
  // «площадки →» в шаге «Сбор» пульта — таблица только по площадкам без показов за последний день (v2)
  const [noShows, setNoShows] = useState({})
  const [refreshAsk, setRefreshAsk] = useState(null) // строка РК в окне «Обновить данные в DSP»
  const [adfoxOpen, setAdfoxOpen] = useState(false) // окно «Импорт ADFOX»
  const tgt = useTargetingCampaign()              // демо-кампания нацеливания: «протухла» ли
  const [extBusy, setExtBusy] = useState(false)

  const askExternal = async (row, kind) => {
    try {
      const r = await api.get(`/traffic-dashboard/campaign/${row.id}/external-plan`, auth())
      setExtAsk({ row, kind, plan: r.data })
    } catch (e) { fail(detailText(e, 'Не удалось узнать, что будет сделано')) }
  }

  const runExternal = async () => {
    if (!extAsk) return
    const { row, kind } = extAsk
    setExtBusy(true)
    // Итог остаётся В ОКНЕ, а не строкой над таблицей (владелец 28.09.2026): обмен идёт
    // десятки секунд, и человек должен видеть и что он идёт, и чем закончился. Отказы —
    // поимённо: «заведено 14 из 19» без причин заставляет разбираться заново.
    try {
      const r = await api.post(`/traffic-dashboard/campaign/${row.id}/${kind}`, {}, auth())
      setExtAsk(x => x && ({ ...x, result: { done: r.data.done || [], failed: r.data.failed || [],
        targeting: r.data.targeting || null } }))
      const d = await api.get(`/traffic-dashboard/campaign/${row.id}`, auth())
      setDetail(x => ({ ...x, [row.id]: d.data }))
      await load()
    } catch (e) {
      setExtAsk(x => x && ({ ...x, result: { error: detailText(e, 'Не удалось выполнить') } }))
    } finally { setExtBusy(false) }
  }

  const setCreativeStatus = async (campId, cr, s) => {
    try {
      await api.put(`/traffic-dashboard/creative/${cr.id}/status`, { status: s }, auth())
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
    } catch (e) { fail(detailText(e, 'Не удалось сменить статус креатива')) }
  }

  // Массовое действие на креатив целиком — по всем его парам в РК (владелец 15.10.2026): чтобы не выключать поштучно.
  // Сервер тот же, что у кнопки пары (проверки согласования, отправка в DSP); пары, к которым статус неприменим, пропускаются.
  // Запросы — по очереди, а не разом: каждый пересчитывает доли площадки, параллельные гонялись бы за ними.
  const setCreativeGroupStatus = async (campId, g, s) => {
    const fit = g.places.filter(c => (s === 'отклонён' ? c.status !== 'отклонён'
      : ['согласован', 'пауза', 'запущен'].includes(c.status) && c.status !== s))
    if (!fit.length) { say('Менять нечего: у всех площадок креатив уже в этом статусе или не согласован'); return }
    if (s === 'отклонён' && !window.confirm(`Отключить креатив «${g.name || 'без названия'}» на ${fit.length} площадк. сразу? `
      + 'Его объём уйдёт остальным креативам этих площадок.')) return
    let done = 0
    const errs = []
    for (const c of fit) {
      try { await api.put(`/traffic-dashboard/creative/${c.id}/status`, { status: s }, auth()); done += 1 }
      catch (e) { errs.push(`${c.domain}: ${detailText(e, 'ошибка')}`) }
    }
    try {
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
    } catch { /* сообщение ниже важнее перечитывания */ }
    const skipped = g.places.length - fit.length
    const head = `Креатив «${g.name || 'без названия'}»: ${s} — ${done} из ${fit.length}${skipped ? `, пропущено ${skipped}` : ''}`
    if (errs.length) fail(`${head}. Не вышло: ${errs.join('; ')}`)
    else say(head)
  }

  // «Скрины запуска сняты» на паре «креатив × площадка» (владелец 01.10.2026).
  const setCreativeScreens = async (campId, cr, done) => {
    try {
      await api.put(`/traffic-dashboard/creative/${cr.id}/screens`, { done }, auth())
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
    } catch (e) { fail(detailText(e, 'Не удалось отметить скрины')) }
  }

  const setPlacementStatus = async (campId, p, s) => {
    try {
      const w = await api.put(`/traffic-dashboard/placement/${p.id}/status`, { status: s }, auth())
      const st = w.data?.stage
      const stageNote = st?.moved ? `. Сделка переведена в «${st.stage}»` : st?.refused ? `. ⚠ ${st.refused}` : ''
      const note = dspCheckNote(w.data?.dsp_check) + stageNote
      if (note) say(`Площадка: ${s}${note}`)
      const r = await api.get(`/traffic-dashboard/campaign/${campId}`, auth())
      setDetail(d => ({ ...d, [campId]: r.data }))
      await load()
    } catch (e) { fail(detailText(e, 'Не удалось сменить статус площадки')) }
  }

  const all = data?.rows || []
  // ?open=КОД — «На дашборд» со страницы разбора раскрывает эту РК. toggle пересоздаётся на каждом
  // рендере, поэтому эффект зовёт его через ref, а не держит в зависимостях.
  // Раскрытая РК — третьим уровнем пилюли меню («Трафики · Дашборд · РК 54SLGF»); клик по «Дашборд» в пилюле сворачивает её.
  const openRow = open ? all.find(x => x.id === open) : null
  const collapse = useCallback(() => setOpen(null), [])
  useNavObject(router.asPath, openRow?.deal_code ? `РК ${openRow.deal_code}` : '', collapse)
  const openCode = String(router.query.open || '')
  const toggleRef = useRef(null)
  toggleRef.current = toggle
  // `?open=` — один раз на код: раскрытие РК меняет `open`, эффект запускался снова и делал второй replace подряд
  const openHandled = useRef('')
  useEffect(() => {
    if (!openCode || !data?.rows || openHandled.current === openCode) return
    openHandled.current = openCode
    const row = data.rows.find(x => String(x.deal_code).toUpperCase() === openCode.toUpperCase())
    if (row && open !== row.id) toggleRef.current(row.id)
    router.replace('/traffic/dashboard', undefined, { shallow: true })
  }, [openCode, data, open, router])
  const sumOf = (r) => summary?.by_campaign?.[r.id]
  // Ссылка-действие сводки ведёт в блок расхлопа, а не на новый экран (макет 11.10.2026).
  const goTo = (r, target, act) => {
    // v2: «площадки без показов» фильтрует таблицу площадок, «перераспределить» открывает окно сразу (17.11.2026).
    if (act?.check === 'delivery') setNoShows(x => ({ ...x, [r.id]: true }))
    if (target === 'alloc') { setReallocAsk(r); return }
    if (target === 'deal') { window.open(`/sales/deals/${encodeURIComponent(r.deal_code || r.deal_id)}`, '_blank', 'noopener'); return }
    if (target === 'adfox') { setAdfoxOpen(true); return }
    if (target === 'start' && mayEdit) { startCampaign(r); return }
    const id = { pixel: 'ext', dsp: 'ext', placements: 'placements', alloc: 'placements', start: 'placements', wr: 'wr', stats: 'stats' }[target]
    const el = id && document.getElementById(`rk-${r.id}-${id}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.style.outline = '2px solid var(--accent-soft)'
    el.style.outlineOffset = '3px'
    setTimeout(() => { el.style.outline = ''; el.style.outlineOffset = '' }, 1800)
  }
  const needsAttention = (r) => !r.plan_show || !r.placements || (r.under || 0) > 0
  // «Ожидает старта» (владелец 02.11.2026): новые РК от сборки до фактического старта — расчётные статусы до
  // «запущена» (`CAMPAIGN_DERIVED` в app/ad/flight.py). Стартовала — уходит в «Запущенные».
  const waitingStart = (r) => r.status === 'ожидает сборки' || r.status === 'готова'
  // Переключатель списка (v2, 17.11.2026): пять пунктов, пункты с нулём скрыты. «Без плана» и «Без площадок» — внутри
  // «Требует внимания», отдельными кнопками их больше нет.
  const TABS = [
    ['all', 'Все', all.length],
    ['waiting', 'Ожидает старта', all.filter(waitingStart).length],
    ['running', 'Запущенные', all.filter(r => r.status === 'запущена').length],
    ['action', 'Нужно действие', all.filter(r => sumOf(r)?.worst === 'red').length,
      'Красная проверка заведения, сбора или раскладки (ночной прогон)'],
    ['attention', 'Требует внимания', all.filter(needsAttention).length, 'Без плана, без площадок или с недокрутом'],
  ]
  const rows = sortRk(all.filter(r => {
    if (tab === 'running' && r.status !== 'запущена') return false
    if (tab === 'waiting' && !waitingStart(r)) return false
    if (tab === 'action' && sumOf(r)?.worst !== 'red') return false
    if (tab === 'attention' && !needsAttention(r)) return false
    const s = q.trim().toLowerCase()
    return !s || [r.deal_code, r.deal_title, r.brand, r.product, r.stage].some(
      v => String(v || '').toLowerCase().includes(s))
  }), rkSort)

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
      color: k.attention ? 'var(--signal-num)' : 'var(--text-primary)',      // NAVY: «действуй сейчас» — оранжевый
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
      <div className="tp-dash navy-scr navy-norm" style={{ maxWidth: 2500, margin: '0 auto', padding: '18px 28px 60px', fontFamily: UI }}>

        <DashHeader data={data} scope={scope} onScope={setScope} archive={archive} onArchive={() => setArchive(v => !v)}
          mayEdit={mayEdit} isAdmin={isAdmin} noFact={noFact} total={all.length} verifier={verifier} wbBusy={wbBusy}
          onWbRefresh={refreshVerifier} widgets={widgets} onWidgets={toggleWidgets} onAdfox={() => setAdfoxOpen(true)}
          sync={{ syncing, syncSaid, onSync: forceSync }} />

        {!!msg && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--danger)' }}>{msg}</div>}
        {!!note && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--blue)' }}>{note}</div>}

        {/* NAVY (17.11.2026): полоса показателей — «стекло», ночью светлая зона; в прежних темах атрибуты ничего не меняют */}
        <div className="navy-glass" data-tone="light" style={{ marginBottom: 14 }}><KpiRow items={KPI} /></div>

        {/* аналитика: свёрнута — строка-итог, развёрнута — виновники и стена дней одной высоты (v2, 17.11.2026) */}
        {!widgets && !!data && (
          <div style={{ marginBottom: 12 }}>
            <WidgetsSummary platData={platData} wall={data.wall || []} rows={all} onOpen={toggleWidgets} />
          </div>
        )}
        {widgets && (
          // Виджет виновников по макету шире (≈1090 px, хендофф 05.11.2026) — левая колонка больше; уже — прокрутка внутри.
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.12fr) minmax(0,1fr)',
            gap: 12, marginBottom: 12 }}>
            {/* «Площадки-виновники» — компонент хендоффа (05.11.2026) на том же ответе, что отчёт «Площадки × РК»:
                один запрос кормит и виджет, и экран, числа не расходятся. */}
            {platData ? (
              <div data-tone="dark" style={{ minWidth: 0, overflowX: 'auto', borderRadius: 18 }}><CulpritsWidget data={platData}
                onOpenReport={code => router.push(`/traffic/platforms?scope=${encodeURIComponent(scope || data?.scope || 'mine')}${code ? `&p=${encodeURIComponent(code)}` : ''}`)}
                onOpenRk={code => router.push(`/traffic/dashboard?open=${encodeURIComponent(code)}`, undefined, { shallow: true })}
                onExcel={() => downloadFile(`/traffic-dashboard/platforms.xlsx?scope=${encodeURIComponent(scope || data?.scope || 'mine')}`)} /></div>
            ) : (
              <div style={{ ...card, padding: '16px 18px', fontSize: 12, color: platErr ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
                Площадки-виновники · {platErr || 'загрузка…'}</div>
            )}

            {/* Ряд — по высоте большего виджета; при «ещё N ▾» оба растут вниз, без прокрутки внутри (владелец 17.11.2026, вечер) */}
            <div data-tone="dark" style={{ minWidth: 0, display: 'flex', flexDirection: 'column', borderRadius: 18 }}>
              <DayWallV2 fill wall={data?.wall || []} rows={all} activeId={open}
                onPick={id => { if (open !== id) toggle(id); else alignRow(id) }} />
            </div>
          </div>
        )}

        {/* реестр — v2 (17.11.2026): панель списка, шапка колонок, РК — отдельными карточками */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Панель списка и шапка колонок закреплены вместе под меню (владелец 18.11.2026); подложка — фон страницы (в NAVY — тот же градиент,
              fixed, чтобы вокруг не было полосы другого тона). Предупреждение «Факт не боевой» остаётся в потоке. */}
          <div ref={stickyRef} data-tp-sticky style={{ position: 'sticky', top: 'var(--nav-h, 58px)', zIndex: 20, display: 'flex', flexDirection: 'column', gap: 10,
            padding: '6px 0 8px', margin: '-6px 0 -8px', background: stuck ? 'var(--sticky-bg, var(--bg-canvas))' : 'transparent', backgroundAttachment: 'fixed' }}>
          <ListPanel q={q} onQ={setQ} shown={rows.length} total={all.length} tabs={TABS} tab={tab} onTab={setTab} />
          <RkHead sort={rkSort} onSort={k => setRkSort(cur => nextRkSort(cur, k))} />
          </div>

          {!!(data?.fact_sources || []).length && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap',
              padding: '9px 13px', marginBottom: 10, borderRadius: 10,
              background: 'var(--warning-tint)', color: 'var(--warning-text)', fontSize: 12.5 }}>
              <b>Факт не боевой</b>
              <span>
                источник данных: {data.fact_sources.join(', ')} — не из кабинета DSP,
                выводы по этим цифрам делать нельзя.
              </span>
            </div>
          )}

          {rows.map(r => {
            const d = detail[r.id]
            return (
              <div key={r.id} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)',
                borderRadius: 18, overflow: open === r.id ? 'visible' : 'hidden' }}>
                <RkRow r={r} open={open === r.id} mayEdit={mayEdit} mayReport={mayReport} onToggle={() => toggle(r.id)}
                  onStart={() => startCampaign(r)} onPause={() => setCampaignStatus(r, 'пауза')}
                  onStop={() => setCampaignStatus(r, 'остановлена')} />

                {/* Расхлоп v2 (17.11.2026): пульт одной строкой, площадки слева, аналитика справа — тёмной половиной на всю высоту (NAVY: не липкая) */}
                {open === r.id && (
                  <Collapse><div>
                    <RkPult rk={r} d={d} sum={sumOf(r)} mayEdit={mayEdit} mayReport={mayReport} reps={data?.reps}
                      notesCount={rkNotes[r.id] ? rkNotes[r.id].length : (d?.notes_count || 0)} logOpen={!!logOpen[r.id]}
                      onToggleLog={() => toggleLog(r)} onAction={(t, act) => goTo(r, t, act)} onPickTraffic={uid => setTraffic(r, uid)}
                      onStart={() => startCampaign(r)} onPause={() => setCampaignStatus(r, 'пауза')}
                      onStop={() => setCampaignStatus(r, 'остановлена')} onFinish={() => finish(r)}
                      onDspRefresh={data?.can_dsp_refresh && r.ms_campaign_xxhash ? () => setRefreshAsk(r) : null} />
                    {!!logOpen[r.id] && d && (
                      <div style={{ padding: '10px 14px 0 18px' }}>
                        <RkLog rkCode={r.deal_code} notes={rkNotes[r.id] || []} canWrite={!!d.can_write_notes}
                          onAdd={note => addNote(r, note)} onClose={() => toggleLog(r)} />
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'stretch' }}>
                      <div style={{ flex: '1 1 auto', minWidth: 0, borderRight: '1px solid var(--border-card)' }}>
                        <SitesPanel rk={r} d={d} mayEdit={mayEdit} tgt={tgt} filterNoShows={!!noShows[r.id]}
                          onClearNoShows={() => setNoShows(x => ({ ...x, [r.id]: false }))}
                          handlers={{
                            setPlacementStatus: (p, st) => setPlacementStatus(r.id, p, st),
                            setCreativeStatus: (cr, st) => setCreativeStatus(r.id, cr, st),
                            setCreativeGroupStatus: (g, st) => setCreativeGroupStatus(r.id, g, st),
                            setCreativeScreens: (cr, done) => setCreativeScreens(r.id, cr, done),
                            askExternal: (kind) => askExternal(r, kind),
                            downloadCreatives: () => downloadDealCreatives(r.deal_id, fail),
                          }} />
                      </div>
                      <div data-tone="dark" style={{ flex: `0 0 ${ANALYTICS_W}px`, width: ANALYTICS_W, boxSizing: 'border-box', borderRadius: '0 0 18px 0' }}>
                        <RkAnalytics rk={r} d={d} st={stat[r.id]} grain={grain[r.id] || 'day'} range={range[r.id] || null}
                          onGrain={g => { setGrain(x => ({ ...x, [r.id]: g })); setRange(x => ({ ...x, [r.id]: null })); loadStat(r.id, g) }}
                          onRange={win => { setRange(x => ({ ...x, [r.id]: win })); loadStat(r.id, grain[r.id] || 'day', win || undefined) }}
                          onTempo={() => setBoostAsk(r)} onRealloc={() => setReallocAsk(r)} mayEdit={mayEdit}
                          onWrLinkChange={wl => { setDetail(prev => ({ ...prev, [r.id]: { ...prev[r.id], wr_link: wl } })); loadStat(r.id, grain[r.id] || 'day') }} />
                      </div>
                    </div>
                  </div></Collapse>
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

      {adfoxOpen && (
        <AdfoxImportModal auth={auth} onClose={() => setAdfoxOpen(false)} onDone={load} />
      )}
      {boostAsk && (
        <TempoModal row={boostAsk} auth={auth} canEdit={mayEdit} onClose={() => setBoostAsk(null)}
          onDone={async () => {
            const [d] = await Promise.all([
              api.get(`/traffic-dashboard/campaign/${boostAsk.id}`, auth()),
              loadStat(boostAsk.id, grain[boostAsk.id] || 'day', range[boostAsk.id]),
            ])
            setDetail(x => ({ ...x, [boostAsk.id]: d.data }))
          }} />
      )}
      {reallocAsk && (
        <ReallocModal row={reallocAsk} auth={auth} canEdit={mayEdit} onClose={() => setReallocAsk(null)}
          onDone={async () => {
            const [d] = await Promise.all([
              api.get(`/traffic-dashboard/campaign/${reallocAsk.id}`, auth()),
              loadStat(reallocAsk.id, grain[reallocAsk.id] || 'day', range[reallocAsk.id]),
            ])
            setDetail(x => ({ ...x, [reallocAsk.id]: d.data }))
          }} />
      )}
      {refreshAsk && (
        <DspRefreshModal row={refreshAsk} auth={auth} onClose={() => setRefreshAsk(null)}
          onDone={async () => {
            if (open === refreshAsk.id) {
              const d = await api.get(`/traffic-dashboard/campaign/${refreshAsk.id}`, auth())
              setDetail(x => ({ ...x, [refreshAsk.id]: d.data }))
            }
          }} />
      )}
      {startAsk && (
        <StartRkModal row={startAsk} auth={auth} note={(r) => dspCheckNote(r.dsp_check)}
          onClose={() => setStartAsk(null)}
          onDone={async () => {
            await load()
            if (open === startAsk.id) {
              const d = await api.get(`/traffic-dashboard/campaign/${startAsk.id}`, auth())
              setDetail(x => ({ ...x, [startAsk.id]: d.data }))
            }
          }} />
      )}
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
          <Modal width={620} onClose={() => { if (!extBusy) setExtAsk(null) }}
            title={wb ? 'Получить пиксели Weborama' : 'Выгрузить креативы в DSP'}
            summary={`РК ${extAsk.row.deal_code} · ${extAsk.row.deal_title}`}
            footer={extAsk.result ? (
              <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button style={btn(true)} onClick={() => setExtAsk(null)}>Готово</button>
              </span>
            ) : (
              <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button style={{ ...btn(false), opacity: extBusy ? 0.5 : 1 }} disabled={extBusy}
                  onClick={() => setExtAsk(null)}>Отмена</button>
                <button style={{ ...btn(true), opacity: (!n || extBusy) ? 0.5 : 1,
                  cursor: (!n || extBusy) ? 'not-allowed' : 'pointer' }}
                  disabled={!n || extBusy} onClick={runExternal}>
                  {extBusy ? 'Идёт обмен…' : (wb ? `Завести ${n} вставок` : `Выгрузить ${n} площадок`)}
                </button>
              </span>
            )}>
            {extBusy ? <ExtProgress wb={wb} n={n} />
              : extAsk.result ? <ExtResult wb={wb} result={extAsk.result} /> : (
            <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
              {/* Зависшие попытки ЭТОЙ системы — первыми: пока они не сверены, повтор по
                  ним заперт, и число «будет заведено» их не включает. */}
              <HungAttempts campaignId={extAsk.row.id}
                items={(extAsk.plan.unknown || []).filter(u => u.system === (wb ? 'weborama' : 'dsp'))}
                onDone={(t) => { say(t); askExternal(extAsk.row, extAsk.kind) }} />
              {blocked && (
                <div style={{ padding: '9px 12px', borderRadius: 9, fontSize: 12.5,
                  background: 'var(--warning-tint)', color: 'var(--warning-text)' }}>{blocked}</div>
              )}
              {wb && !!pl.account && !(pl.project_id && pl.campaign_id) && (
                <WrAttach campaignId={extAsk.row.id} pl={pl}
                  onDone={(t) => { say(t); askExternal(extAsk.row, extAsk.kind) }} />
              )}
              {wb ? (
                <>
                  {/* ПРИ ЗАСЛОНЕ ЧИСЛА НЕ ПОКАЗЫВАЕМ. «Площадок готово: 1» рядом с
                      «пиксель не заказан» читается как «всё готово, но почему-то ноль»,
                      и человек ищет поломку вместо галочки (владелец 18.09.2026).
                      Когда ход закрыт — на экране остаётся причина и путь к ней. */}
                  {blocked ? (
                    <div style={{ color: 'var(--text-muted)' }}>
                      Пиксель заказывается на сделке, а не здесь: карточка сделки →
                      «Доп. параметры РК» → галочка «Пиксель Weborama». После этого
                      вернитесь сюда — площадок, готовых к заведению, сейчас {pl.ready ?? 0}.
                    </div>
                  ) : (
                  <div>Площадок готово к заведению: <b>{pl.ready ?? 0}</b>.
                    Пиксель уже есть у <b>{pl.have ?? 0}</b>, будет получено ещё <b>{pl.todo ?? 0}</b>.</div>
                  )}
                  {!!pl.wait_erid && (
                    <div style={{ color: 'var(--warning-fg)' }}>
                      {pl.wait_erid} площадок ждут ЕРИД — пиксель им заведётся после выпуска ЕРИД
                      (автовыпуск раз в 30 минут), без ЕРИД заводить нельзя.</div>
                  )}
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
                      Посадочная кампании: {pl.landing}
                      <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                        У Weborama это поле одно на кампанию и справочное — пишем туда
                        свой сайт. В креатив каждой площадки уезжает ЕЁ собственная
                        ссылка, и на счёт показов это поле не влияет.
                      </div>
                    </div>
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
                  {/* Рекламная метка — ИНН и название рекламодателя из изначального договора ОРД
                      (владелец 28.09.2026: слать всегда, идёт в подсказку метки рядом с ЕРИД). */}
                  <div style={{ fontSize: 12.5 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Рекламная метка: </span>
                    {pl.ad_label
                      ? <b>{pl.ad_label.name}, ИНН {pl.ad_label.inn}</b>
                      : <span style={{ color: 'var(--danger-fg)' }}>нет изначального договора ОРД — креативы не пойдут</span>}
                  </div>
                  <TargetingPreview t={pl.targeting} />
                  <div style={{ color: 'var(--text-faint)', fontSize: 11.5 }}>
                    В каждый креатив вшиваются пиксель Weborama, счётчик площадки и скрипт
                    видимости. Заведённый креатив удалить по API нечем.</div>
                </>
              )}
            </div>
            )}
          </Modal>
        )
      })()}
    </>
  )
}
