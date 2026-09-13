/**
 * Очередь трафика — рабочий экран контура «Траффики», а не витрина цифр.
 *
 * Зерно строки — ПАРА «креатив × площадка». Один баннер на восьми площадках это восемь
 * единиц работы, и семь из них могут быть в порядке; сводка по сделке такого не покажет.
 *
 * Строки сгруппированы по КРЕАТИВУ, а не по сделке: материал у всех получателей один,
 * и отметка «всё ок» естественно ставится сразу на всю группу — восемь одинаковых
 * нажатий были бы работой ради интерфейса. Переделка и вовсе бывает только групповой:
 * баннер один, и «переделать его для третьего сайта» ничего не значит.
 *
 * Срочность, причина и порядок приходят с бэкенда (app/traffic/urgency.py) — той же
 * функцией, которая будет порождать уведомления. Считать это на клиенте нельзя: экран
 * и лента разойдутся во мнении о том, что горит.
 *
 * Исходов у трафика ДВА. «Отказ» — решение площадки, и его здесь нет не потому, что
 * кнопку спрятали: сервер такой вердикт отклоняет (routers/traffic.py).
 */
import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, card, CAP, btn, btnSm, chip as pill, inp, ROW_TONE, Modal }
  from '@/components/salesTableKit'
// Предпросмотр — ТОТ ЖЕ компонент, что на карточке сделки: сетка типовых размеров,
// песочница для архива, изолированная рамка для html. Своя, «простая» версия у трафика
// показывала бы баннер не так, как его увидит проверяющий на карточке, — а сверять
// они должны одно и то же.
import { CreativePreview } from '@/components/creatives/AssemblyCreatives'
import api, { auth } from '@/lib/api'
import { dm } from '@/lib/salesFormat'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

/* Что сказать человеку про письмо. Ответ ручки различает пять исходов, и каждый значит
   для него РАЗНОЕ действие: отправлено — ничего не делать, не ушло — отправить самому.
   Свести их в «готово» значило бы, что часть запросов площадка не получит никогда. */
const MAIL_SAID = {
  sent: 'Запрос записан, письмо ушло площадке',
  failed: 'Запрос записан, но письмо НЕ ушло — отправьте текст сами',
  queued: 'Запрос записан, письмо в очереди — уйдёт, когда настроят почту',
  no_address: 'Запрос записан. У площадки не указана почта — отправьте текст сами',
  off: 'Запрос записан. Почта не настроена — отправьте текст сами',
}

const TABS = [
  { key: 'waiting', label: 'Ждут проверки' },
  { key: 'done', label: 'Проверенные' },
  { key: 'all', label: 'Все' },
]


/* Повторяют app/traffic/files.py. Проверка на клиенте не заменяет серверную — она
   отвечает быстрее: перетащив папку с двадцатью файлами, человек должен узнать об этом
   сразу, а не после двадцатой отклонённой загрузки. */
const SHOT_LIMIT = 10
const SHOT_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.pdf']
const shotOk = (name) => SHOT_EXT.some(e => String(name || '').toLowerCase().endsWith(e))

const TONE = {
  ok:      ['var(--income-tint)',  'var(--income)',       'var(--income-border)'],
  rework:  ['var(--danger-tint)',  'var(--danger)',       'var(--danger-border)'],
  warn:    ['var(--warning-tint)', 'var(--warning-text)', 'var(--warning-border)'],
  neutral: ['var(--bg-card)',      'var(--text-secondary)', 'var(--border-card)'],
}

/* Иконки вместо подписей у трёх действий креатива. Не мода: «Предпросмотр · Скачать
   архив · Нацеливание» занимали половину строки и отжимали вправо решение — то, ради
   чего экран открывают. Действия однотипные и опознаются формой; название остаётся в
   подсказке, поэтому ничего не теряется, кроме ширины. */
const Ico = ({ d, size = 15 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
    style={{ display: 'block' }}>{d}</svg>
)
const I_EYE = <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>
const I_DOWN = <><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></>
const I_AIM = <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>
const I_PLUS = <><path d="M12 5v14M5 12h14" /></>
const I_REDO = <><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /></>
const I_SEARCH = <><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>
// Переход на сайт площадки: стрелка наружу из рамки — общепринятый знак «откроется в
// новой вкладке». Рисуем сами, как и остальные: эмодзи прыгало бы по высоте между
// платформами и выбивалось из ряда.
const I_OUT = <><path d="M14 4h6v6" /><path d="M20 4l-9 9" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>

/** Кнопка-иконка. Квадрат 28×28 — палец попадает, а строка не растёт. */
const iconBtn = (on = true) => ({
  width: 28, height: 28, borderRadius: 8, padding: 0, cursor: on ? 'pointer' : 'default',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  color: on ? 'var(--text-secondary)' : 'var(--text-ghost)',
})

/** Свёрнутая сводка креатива — четырьмя плашками в шапке карточки.
 *
 * Плашка, а не текст: тон читается раньше слова, и «где работа» видно, не вчитываясь.
 * Маркером служит точка, а не значок в подложке: значок с квадратом стоил около 130 px
 * на штуку, и пять таких вместе с левым блоком и кнопками не вставали в 1600.
 *
 * Плашек ровно четыре, и это предел. «Размер» уехал в подпись креатива (он один на весь
 * комплект, а не на площадку), «старт» — в колонку строки, где он и различается. Всё,
 * что одинаково у всех получателей, в сводке лишнее по определению.
 */
const setFacts = (rows) => {
  const total = rows.length
  const checked = rows.filter(r => r.verdict).length
  const rework = rows.filter(r => r.verdict === 'на переделку').length
  const shots = rows.reduce((a, r) => a + (r.shots_count || 0), 0)
  const withUrl = rows.filter(r => r.advertiser_url).length
  return [
    { label: 'пров.',  value: `${checked}/${total}`, tone: checked === total ? 'ok' : 'warn' },
    { label: 'посад.', value: `${withUrl}/${total}`, tone: withUrl === total ? 'ok' : 'warn' },
    { label: 'скрин.', value: String(shots), tone: shots ? 'ok' : 'off' },
    { label: 'перед.', value: String(rework), tone: rework ? 'rework' : 'off' },
  ]
}

const DOT = { ok: 'var(--income)', warn: 'var(--warning)', rework: 'var(--danger)',
              off: 'var(--text-ghost)' }
const FACT_BG = { ok: 'var(--income-tint)', warn: 'var(--warning-tint)',
                  rework: 'var(--danger-tint)', off: 'var(--bg-subtle)' }
const FACT_BD = { ok: 'var(--income-border)', warn: 'var(--warning-border)',
                  rework: 'var(--danger-border)', off: 'var(--border-card)' }

function FactLine({ rows }) {
  return (
    /* Свой перенос: если плашки перестают помещаться, на второй ряд уезжают ОНИ, а не
       кнопки решения — иначе «Все ок» прыгало бы под карточку. */
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
      minWidth: 0 }}>
      {setFacts(rows).map((f, i) => (
        <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 9px', borderRadius: 8, background: FACT_BG[f.tone],
          border: `1px solid ${FACT_BD[f.tone]}`, whiteSpace: 'nowrap' }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: DOT[f.tone],
            flex: '0 0 6px' }} />
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.07em',
            textTransform: 'uppercase', color: 'var(--text-muted)' }}>{f.label}</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
            color: 'var(--text-primary)' }}>{f.value}</span>
        </span>
      ))}
    </span>
  )
}


/* Сворачивание своё, а не общим `Section`: тот рисует собственную строку заголовка со
   значениями ПОД ней, а здесь всё требуется одной строкой. Общее у них поведение —
   состояние помнится, иначе нужное разворачивают заново при каждом заходе. */
const OPEN_KEY = 'traffic_queue_open'

/* Сетка ОДНА на шапку колонок и на строки. Две копии разъезжаются при первой же правке
   ширины, и подпись перестаёт стоять над своим столбцом. */
const ROW_GRID = {
  display: 'grid',
  // Колонки «Скрины» больше нет: кнопка переехала в блок решений, к остальным кнопкам
  // (владелец 12.09.2026). Отдельный столбец под один плюсик держал 84 px ради того,
  // чтобы в девяти строках из десяти показывать пустоту.
  gridTemplateColumns: 'minmax(180px,1.6fr) 66px minmax(140px,1.2fr) 100px minmax(130px,1fr) 200px',
  alignItems: 'center', gap: 10,
}

function useOpenSets() {
  const [open, setOpen] = useState({})
  // localStorage читается только после монтирования: на сервере его не существует.
  useEffect(() => {
    try { setOpen(JSON.parse(localStorage.getItem(OPEN_KEY) || '{}')) } catch { /* битое значение не роняет экран */ }
  }, [])
  const toggle = (id) => setOpen(prev => {
    const next = { ...prev, [id]: !prev[id] }
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(next)) } catch { /* приватный режим */ }
    return next
  })
  return [open, toggle]
}

const Chevron = ({ open }) => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" style={{ flex: '0 0 auto',
    transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>
    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

/** Группировка по креативу. Ключ — комплект: он и есть материал, который проверяют. */
function groupBySet(rows) {
  const map = new Map()
  for (const r of rows) {
    const k = r.set.id
    if (!map.has(k)) map.set(k, { set: r.set, deal: r.deal, rows: [] })
    map.get(k).rows.push(r)
  }
  // Порядок групп — по самой срочной строке внутри: бэкенд уже отсортировал строки,
  // поэтому достаточно взять первую вошедшую.
  return [...map.values()]
}

export default function TrafficQueue() {
  const [tab, setTab] = useState('waiting')
  const [q, setQ] = useState('')
  const [today, setToday] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [rework, setRework] = useState(null)     // { pairIds, setNo, reason }
  const [shots, setShots] = useState(null)       // { row, files }
  const [preview, setPreview] = useState(null)   // { files, startId }
  const [open, toggle] = useOpenSets()
  const [aim, setAim] = useState(null)      // { setId, no, url } — ручная ссылка
  // Какой комплект сейчас выпускает ссылку. Не общий `busy`: выпуск ходит наружу, и
  // гасить на это время вердикты по ВСЕЙ очереди значило бы останавливать работу.
  const [aiming, setAiming] = useState(null)
  // Отдельно от ошибки: «письмо ушло» — не ошибка, а красная плашка на успехе учит
  // людей не читать плашки вовсе.
  const [note, setNote] = useState('')
  const [urlAsk, setUrlAsk] = useState(null)   // { targetId, name, text }
  const [phrases, setPhrases] = useState([])
  const [dragOver, setDragOver] = useState(false)

  // Фильтр «чья кампания». По умолчанию пусто — ВСЯ очередь: она общая (03.09.2026),
  // и разбирают её по наличию времени, а не по назначению. Фильтр доступен всем: он
  // сужает уже видимое, а не выдаёт доступ.
  const [repId, setRepId] = useState('')
  const [reps, setReps] = useState([])
  const [myRepId, setMyRepId] = useState(null)
  const [canViewOthers, setCanViewOthers] = useState(false)
  /* Права читаются ИЗ СНИМКА в localStorage, поэтому только после монтирования:
     на сервере localStorage нет, и вычисление прямо в теле компонента дало бы
     расхождение разметки. Аргументов у `can` ТРИ — `(perms, section, action)`;
     вызов с двумя молча возвращал false всем, кроме админа (11.09.2026). */
  const [mayApprove, setMayApprove] = useState(false)
  const [mayEdit, setMayEdit] = useState(false)
  useRefreshOnReturn(() => load())
  useEffect(() => {
    const p = getPermissions()
    setMayApprove(can(p, 'traffic_queue', 'approve'))
    setMayEdit(can(p, 'traffic_queue', 'edit'))
  }, [])

  /* Тянем ВСЮ очередь одним запросом, а вкладки режем на месте. Иначе счётчик на
     вкладке нельзя показать, не сходив за ней же: «Проверенные 0» — это ответ, который
     должен быть виден ДО нажатия, иначе вкладку открывают, чтобы узнать, пуста ли она.
     Порядок и видимость всё равно ставит сервер (`_apply_scope`, сортировка по
     срочности) — здесь только фильтр. */
  const load = useCallback(async () => {
    setLoading(true); setErr('')
    try {
      // Кого показываем: пусто — вся очередь (умолчание), id — конкретного трафика.
      const who = repId ? `&rep_id=${repId}` : ''
      const r = await api.get(`/traffic/queue?status=all${who}`, auth())
      setRows(r.data.rows || [])
      setReps(r.data.reps || [])
      setMyRepId(r.data.my_rep_id ?? null)
      setCanViewOthers(!!r.data.can_view_others)
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось загрузить очередь')
    }
    setLoading(false)
  }, [repId])

  useEffect(() => { load() }, [load])

  // `new Date()` при рендере даёт на сервере и в браузере разное — берём после монтажа.
  useEffect(() => { setToday(new Date()) }, [])

  async function verdict(pairIds, v, reason) {
    setBusy(true); setErr('')
    try {
      if (pairIds.length === 1 && !reason) {
        await api.post(`/traffic/pair/${pairIds[0]}/verdict`, { verdict: v }, auth())
      } else {
        await api.post('/traffic/pairs/verdict',
          { pair_ids: pairIds, verdict: v, reason: reason || null }, auth())
      }
      setRework(null)
      await load()
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось записать вердикт')
    }
    setBusy(false)
  }

  /* «Нацелить на себя» — главная кнопка трафика в этой строке: по ней он открывает сайт
     до старта и видит рекламу, которой в обычном браузере ещё нет.

     Ссылка ВЫПУСКАЕТСЯ по нажатию и нигде не хранится: живёт 48 часов, а согласование
     идёт днями (замер 12.09.2026). Работает она на этой стадии только потому, что
     нацеливание заводится на тестового клиента, а не на наш креатив — нашего в DSP пока
     нет вовсе.

     Вкладку открываем СИНХРОННО по клику, адрес подставляем после ответа: окно,
     открытое из `await`, блокировщик всплывающих окон считает непрошеным и режет. */
  async function aimAtMe(setId) {
    setErr(''); setAiming(setId)
    const tab = window.open('', '_blank')
    try {
      const r = await api.post(`/launch-prep/set/${setId}/targeting-link`, {}, auth())
      if (tab) tab.location = r.data.url
      else window.location.href = r.data.url
    } catch (e) {
      if (tab) tab.close()
      setErr(e.response?.data?.detail || 'Не удалось выпустить ссылку нацеливания')
    } finally { setAiming(null) }
  }

  /* Ручная ссылка нацеливания. Поле заморожено (0 из 33 за две недели), но диалог
     оставлен: то, что в нём когда-то завели, должно оставаться правимым. */
  async function saveAim() {
    setBusy(true); setErr('')
    try {
      await api.put(`/launch-prep/set/${aim.setId}/targeting-url`, { url: aim.url.trim() }, auth())
      setAim(null)
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить ссылку') }
    setBusy(false)
  }

  /* Запрос ссылки. Система НИЧЕГО не отправляет — своего канала до площадки у неё нет:
     ручка фиксирует факт запроса и текст, который человек шлёт почтой или в чат. Делать
     вид, что письмо ушло, хуже, чем не отправлять его вовсе. Та же ручка, что у
     аккаунта, — иначе два запроса одной ссылки писались бы в разные поля. */
  async function saveUrlAsk() {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/launch-prep/target/${urlAsk.targetId}/url-request`,
        { text: urlAsk.text }, auth())
      setUrlAsk(null)
      // Человеку важно знать, отправила ли система письмо или текст нужно слать самому.
      // Молчание здесь означало бы, что запрос уйдёт дважды — или не уйдёт вовсе.
      setNote(MAIL_SAID[r.data?.mail] || MAIL_SAID.off)
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось записать запрос') }
    setBusy(false)
  }

  /* Готовые формулировки — накопитель, общий с окном аккаунта. Его отказ не должен
     ломать запрос: текст можно написать и руками. */
  useEffect(() => {
    if (!urlAsk || phrases.length) return
    api.get('/launch-prep/url-request-phrases', auth())
      .then(r => setPhrases(r.data.items || []))
      // Пустой `catch` оставлял список заготовок пустым молча, и это читалось как
      // «заготовок в базе нет». Вторичные данные тоже обязаны объяснять свою пропажу.
      .catch(() => setErr('Заготовки текста запроса не загрузились — наберите текст руками'))
  }, [urlAsk, phrases.length])

  async function openShots(row) {
    try {
      const r = await api.get(`/traffic/pair/${row.pair_id}/files`, auth())
      setShots({ row, files: r.data.files || [] })
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось открыть файлы') }
  }

  /* Пачкой — так и снимают: пять кадров одного сайта подряд. Но грузим ПО ОЧЕРЕДИ,
     а не разом: имя файла собирается из числа уже приложенных (`cr2-03`), и
     параллельные запросы получили бы один и тот же порядковый номер. Ради скорости
     здесь потерялась бы нумерация — размен явно не в пользу скорости.

     Прерываемся на первой ошибке и говорим, сколько успело лечь: молчаливое
     «загрузилось 3 из 7» неотличимо от «всё хорошо», а разбираться придётся потом,
     когда снимать заново уже негде. */
  async function addShots(row, fileList) {
    const all = Array.from(fileList || [])
    if (!all.length) return
    const good = all.filter(f => shotOk(f.name))
    const bad = all.length - good.length
    const free = Math.max(0, SHOT_LIMIT - (shots?.files?.length || 0))
    const take = good.slice(0, free)

    setBusy(true); setErr('')
    let done = 0
    for (const f of take) {
      const form = new FormData()
      form.append('file', f)
      try {
        await api.post(`/traffic/pair/${row.pair_id}/files`, form,
          { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
        done++
      } catch (e) {
        setErr(`${e.response?.data?.detail || 'Не удалось загрузить'} — принято ${done} из ${take.length}`)
        break
      }
    }
    const skipped = []
    if (bad) skipped.push(`${bad} не той формы`)
    if (good.length > free) skipped.push(`${good.length - free} сверх предела в ${SHOT_LIMIT}`)
    if (skipped.length && done === take.length) setErr(`Пропущено: ${skipped.join(', ')}`)
    await openShots(row)
    await load()
    setBusy(false)
  }

  async function dropShot(row, id) {
    setBusy(true)
    try {
      await api.delete(`/traffic/file/${id}`, auth())
      await openShots(row)
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось удалить') }
    setBusy(false)
  }

  /* Имя файла БЕЗ аргумента берётся из ответа сервера: только он знает, отдал он архив
     или переименованную картинку. Через blob заголовок сам собой не срабатывает — файл
     уже в памяти, и `a.download` перекрывает Content-Disposition, — поэтому читаем его
     руками. Без этого одиночный креатив лёг бы на диск как «file» или с чужим `.zip`. */
  function download(url, name) {
    api.get(url, { ...auth(), responseType: 'blob' }).then(r => {
      const cd = r.headers?.['content-disposition'] || ''
      const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)
      let fromServer = null
      try { fromServer = m ? decodeURIComponent(m[1]) : null } catch { fromServer = m ? m[1] : null }
      const href = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = href; a.download = name || fromServer || 'file'
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(href)
    }).catch(e => setErr(e.response?.data?.detail || 'Не удалось скачать'))
  }

  const waiting = rows.filter(r => !r.verdict).length
  const counts = { waiting, done: rows.length - waiting, all: rows.length }

  /* Поиск идёт по СТРОКЕ, а группа остаётся целой: нашли площадку — видно, в каком она
     креативе и что с остальными. Обратное (показать одну строку без соседей) отвечает
     на вопрос «где это», но не на вопрос «что с этим делать». */
  const hay = (r) => [r.set.title, r.deal.code, r.deal.brand, r.deal.advertiser,
    r.deal.account, r.publisher.name, r.publisher.domain, r.pair_prefix,
    `креатив №${r.set.no}`].filter(Boolean).join(' ').toLowerCase()

  const visible = rows.filter(r => {
    if (tab === 'waiting' && r.verdict) return false
    if (tab === 'done' && !r.verdict) return false
    return !q.trim() || hay(r).includes(q.trim().toLowerCase())
  })
  const groups = groupBySet(visible)

  /* Дней до старта — только ПОДПИСЬ к дате. Тон берётся из `r.urgency`, посчитанного
     сервером той же функцией, что порождает уведомления: разойтись экрану и ленте во
     мнении о том, что горит, нельзя. */
  const daysTo = (d) => {
    if (!d || !today) return null
    const t = new Date(`${d}T00:00:00`)
    return Math.round((t - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 864e5)
  }
  const startNote = (d) => {
    const n = daysTo(d)
    if (n === null) return ''
    return n < 0 ? `${-n} дн. назад` : n === 0 ? 'сегодня' : `через ${n} дн.`
  }

  return (
    <>
      <Head><title>Креативы на проверку</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '22px 20px 60px', fontFamily: UI }}>

        {/* Заголовок, сводка, поиск и вкладки — ОДНОЙ строкой. Три ряда над таблицей
            съедали экран, а очередь читают сверху вниз: чем раньше начинается работа,
            тем меньше прокрутки до неё. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16,
          flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
            Креативы на проверку
          </h1>
          <span style={{ ...CAP, marginBottom: 0 }}>
            {loading ? 'загрузка…'
              : `${waiting} площадок на проверке · ${groupBySet(rows).length} креатива · всего ${rows.length}`}
          </span>
          <span style={{ flex: 1 }} />

          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '0 12px', height: 34, borderRadius: 10, background: 'var(--bg-card)',
            border: '1px solid var(--border-card)', color: 'var(--text-faint)' }}>
            <Ico d={I_SEARCH} size={14} />
            <input value={q} onChange={e => setQ(e.target.value)}
              placeholder="Креатив, ID, площадка, бренд…"
              style={{ border: 0, outline: 'none', background: 'transparent', width: 210,
                fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)' }} />
            {!!q && (
              <button onClick={() => setQ('')} title="Очистить"
                style={{ border: 0, background: 'none', cursor: 'pointer', padding: 0,
                  color: 'var(--text-faint)', fontSize: 15, lineHeight: 1 }}>×</button>
            )}
          </span>

          {/* Фильтр по ответственному — сразу после поиска, как в дашбордах аккаунта и
              сейлза. Умолчание — вся очередь; список показываем, только если кого-то
              вообще назначали, иначе селектор объяснял бы несуществующий выбор. */}
          {canViewOthers && !!reps.length && (
            <select value={repId} onChange={e => setRepId(e.target.value)}
              style={{ height: 34, padding: '0 10px', borderRadius: 10,
                background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)',
                cursor: 'pointer', minWidth: 170 }}>
              <option value="">Вся очередь</option>
              {/* Своя строка помечена звёздочкой: по имени её не угадать. */}
              {!!myRepId && <option value={myRepId}>★ Мои</option>}
              {reps.filter(r => r.id !== myRepId).map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          )}

          {/* Сегмент, а не отдельные кнопки: три взаимоисключающих среза одного списка —
              это один переключатель, и щель между кнопками читалась бы как «три разных
              действия». Счётчик стоит В кнопке: он и есть ответ, стоит ли туда идти. */}
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, padding: 3,
            borderRadius: 10, background: 'var(--bg-subtle)',
            border: '1px solid var(--border-card)' }}>
            {TABS.map(t => {
              const on = tab === t.key
              return (
                <button key={t.key} onClick={() => setTab(t.key)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
                    padding: '5px 12px', borderRadius: 8, border: 0, cursor: 'pointer',
                    fontFamily: UI, fontSize: 12.5, fontWeight: on ? 700 : 600,
                    background: on ? 'var(--accent-tint)' : 'transparent',
                    color: on ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {t.label}
                  <span style={{ fontFamily: MONO, fontSize: 11,
                    color: on ? 'var(--accent)' : 'var(--text-ghost)' }}>
                    {counts[t.key]}
                  </span>
                </button>
              )
            })}
          </span>
        </div>

        {err && (
          <div style={{ ...card, padding: '10px 14px', marginBottom: 14, color: 'var(--danger)',
                        borderColor: ROW_TONE.overdue.border, background: ROW_TONE.overdue.bg }}>
            {err}
          </div>
        )}
        {!!note && (
          <div onClick={() => setNote('')} style={{ ...card, padding: '10px 14px',
            marginBottom: 14, cursor: 'pointer', color: 'var(--text-primary)' }}>
            {note}
          </div>
        )}

        {!loading && !groups.length && (
          <div style={{ ...card, padding: '28px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {tab === 'waiting'
              ? 'Нечего проверять — весь материал разобран.'
              : 'Пусто.'}
          </div>
        )}

        {groups.map(g => {
          const pending = g.rows.filter(r => !r.verdict)
          // Размер из подписи убран (владелец, 31.08.2026): он есть в самом баннере и в
          // предпросмотре, а в шапке занимал место, отведённое под ответ на «чей это
          // материал». Подпись отвечает ровно на этот вопрос.
          const subtitle = [g.deal.advertiser, g.deal.brand, g.deal.account]
            .filter(Boolean).join(' · ')
          return (
            <div key={g.set.id} style={{ ...card, padding: '14px 16px', marginBottom: 14 }}>

              {/* ОДНА строка на свёрнутый креатив: слева — что это и чьё, посередине
                  сводка, справа действия. Раньше было три ряда, и в очереди из десяти
                  креативов нижние уходили за экран. Клик по левой части разворачивает
                  список площадок; кнопки справа — СОСЕДИ переключателя, а не его
                  содержимое, иначе «Все ок» заодно сворачивало бы карточку. */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <button type="button" onClick={() => toggle(g.set.id)}
                  title={open[g.set.id] ? 'Свернуть площадки' : 'Показать площадки'}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none',
                    border: 0, padding: 0, cursor: 'pointer', textAlign: 'left',
                    color: 'var(--text-muted)', fontFamily: UI, minWidth: 0 }}>
                  <Chevron open={!!open[g.set.id]} />
                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700,
                                 color: 'var(--accent)' }}>{g.deal.code}</span>
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1,
                    alignItems: 'flex-start', minWidth: 0, maxWidth: 300 }}>
                    <span title={g.set.title || ''}
                      style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text-primary)',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      maxWidth: '100%' }}>
                      Креатив №{g.set.no}{g.set.title ? ` · ${g.set.title}` : ''}
                    </span>
                    {/* Чей это материал. Трафик сделок не ведёт: без этих трёх имён он не
                        понимает, что смотрит, и не знает, к кому идти с вопросом. */}
                    <span title={subtitle}
                      style={{ ...CAP, marginBottom: 0, whiteSpace: 'nowrap',
                      overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
                      {subtitle}
                    </span>
                  </span>
                </button>

                {g.set.form && (
                  <span style={{ ...pill(...TONE.neutral), fontFamily: MONO }}>
                    {g.set.form === 'BannerHtml5' ? 'Banner Html5' : g.set.form}
                  </span>
                )}

                <FactLine rows={g.rows} />

                <span style={{ flex: 1 }} />

                {/* Три служебных действия — иконками, вплотную: они однотипны («открой,
                    посмотри, забери») и опознаются формой. Решение отделено промежутком,
                    потому что оно другого рода и необратимо. */}
                <span style={{ display: 'inline-flex', gap: 4, marginRight: 6 }}>
                  <button style={iconBtn(!!g.rows[0]?.files?.length)}
                    disabled={!g.rows[0]?.files?.length} title="Предпросмотр баннера"
                    onClick={() => setPreview({ files: g.rows[0].files,
                                                startId: g.rows[0].files[0].id })}>
                    <Ico d={I_EYE} />
                  </button>
                  {/* Имя файла даёт СЕРВЕР: одиночный архив он отдаёт как есть, только
                      переименованным, а расширение у него своё. Захардкоженный `.zip`
                      здесь однажды переименовал бы картинку в архив. */}
                  <button style={iconBtn(!!g.rows.length)} disabled={busy || !g.rows.length}
                    title="Скачать материал архивом"
                    onClick={() => download(`/traffic/pair/${g.rows[0].pair_id}/creative-archive`)}>
                    <Ico d={I_DOWN} />
                  </button>
                  {/* ОДНА кнопка, одно намерение: «нацелить на себя». Раньше их было
                      три — открыть, завести, изменить, — потому что ссылку заводили
                      руками и хранили. Теперь она выпускается по нажатию (12.09.2026):
                      нацеливание заводится на тестового клиента, живёт 48 часов, и
                      хранить её нельзя — сохранённая протухнет раньше, чем понадобится. */}
                  <button style={iconBtn(mayEdit)} disabled={!mayEdit || aiming === g.set.id}
                    title="Нацелить на себя: откроется страница DSP, нажмите «Включить» — и увидите баннер на сайте площадки до старта"
                    onClick={() => aimAtMe(g.set.id)}>
                    <Ico d={I_AIM} />
                  </button>
                  {/* Ручная ссылка, если её когда-то завели: поле заморожено, но то, что
                      в нём лежит, остаётся доступным. Новых так не заводят. */}
                  {!!g.set.test_targeting_url && (
                    <a href={g.set.test_targeting_url} target="_blank" rel="noreferrer"
                       title={`Ручная ссылка · ${g.set.test_targeting_url}`}
                       style={{ ...iconBtn(true), color: 'var(--accent)',
                         borderColor: 'var(--accent-border)', background: 'var(--accent-tint)',
                         textDecoration: 'none', fontSize: 12 }}>
                      ↗
                    </a>
                  )}
                  {!!g.set.test_targeting_url && mayEdit && (
                    <button style={iconBtn(true)} title="Изменить ручную ссылку"
                      onClick={() => setAim({ setId: g.set.id, no: g.set.no,
                                              url: g.set.test_targeting_url })}>
                      <span style={{ fontSize: 12 }}>✎</span>
                    </button>
                  )}
                </span>

                {/* Порядок как в макете: отрицательное решение слева, утвердительное
                    справа — читают слева направо, и последним под курсором остаётся то,
                    что нажимают в девяти случаях из десяти. */}
                {mayApprove && !!pending.length && (
                  <button style={{ ...pill(...TONE.neutral), padding: '6px 13px',
                    fontSize: 12.5, cursor: 'pointer', color: 'var(--danger)',
                    borderColor: 'var(--danger-border)' }} disabled={busy}
                    onClick={() => setRework({ pairIds: pending.map(r => r.pair_id),
                                               setNo: g.set.no, reason: '' })}>
                    На переделку
                  </button>
                )}
                {mayApprove && pending.length > 1 && (
                  <button style={{ ...pill(...TONE.ok), padding: '6px 13px', fontSize: 12.5,
                    cursor: 'pointer', gap: 7 }} disabled={busy}
                    onClick={() => verdict(pending.map(r => r.pair_id), 'ок')}>
                    <span style={{ fontSize: 11 }}>✓</span> Все ок ({pending.length})
                  </button>
                )}
              </div>

              {/* Список получателей свёрнут по умолчанию: работа идёт креативами, а
                  строки нужны только когда с одной из площадок что-то не так. */}
              {!!open[g.set.id] && (<div style={{ marginTop: 12 }}>

              {/* Шапка колонок. Строка без неё заставляет угадывать, что означает «6» и
                  «01.12», — и угадывают по-разному. */}
              <div style={{ ...ROW_GRID, ...CAP, marginBottom: 0,
                padding: '0 6px 7px', borderBottom: '1px solid var(--border-card)' }}>
                <span>Площадка · ID</span><span>Поверхн.</span><span>Посадочная</span>
                <span>Старт</span><span>Статус</span>
                <span style={{ textAlign: 'right' }}>Решение</span>
              </div>

              {g.rows.map(r => {
                /* Строка ПЛОСКАЯ, срочность несут точка и дата. Залитая рамка вокруг
                   каждой строки превращала список из шести площадок в шесть карточек:
                   глаз ищет границы вместо того, чтобы читать столбцы. */
                const tone = ROW_TONE[r.urgency] || ROW_TONE.normal
                const hot = r.urgency === 'overdue' || r.urgency === 'today'
                const st = r.verdict === 'ок' ? ['проверено', TONE.ok]
                  : r.verdict === 'на переделку' ? ['на переделке', TONE.rework]
                    : r.urgency === 'overdue' ? ['ждёт проверки', TONE.rework]
                      : r.urgency === 'today' ? ['ждёт проверки', TONE.warn]
                        : ['ждёт проверки', TONE.neutral]
                return (
                  <div key={r.pair_id} style={{ ...ROW_GRID, padding: '9px 6px',
                    borderBottom: '1px solid var(--border-row)' }}>

                    <div style={{ minWidth: 0 }}>
                      {/* Домен открывает сайт в новой вкладке: первое, что делает трафик,
                          — идёт смотреть площадку. Ссылка на самом домене, а не кнопкой
                          рядом: имя площадки И ЕСТЬ адрес, куда он собирается. */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 7, height: 7, borderRadius: 999,
                                       background: tone.dot, flex: '0 0 7px' }} />
                        {r.publisher.domain ? (
                          <a href={`https://${r.publisher.domain}`} target="_blank" rel="noreferrer"
                             title={`Открыть ${r.publisher.domain} в новой вкладке`}
                             style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap',
                                      overflow: 'hidden', textOverflow: 'ellipsis',
                                      color: 'var(--text-primary)', textDecoration: 'none' }}>
                            {r.publisher.name || r.publisher.domain}
                          </a>
                        ) : (
                          <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap',
                                         overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {r.publisher.name || '—'}
                          </span>
                        )}
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.04em',
                        color: 'var(--text-ghost)', marginTop: 2, paddingLeft: 14 }}>
                        {r.pair_prefix || r.publisher.code || ''}
                      </div>
                    </div>

                    <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
                      {r.surface_kind || '—'}
                    </div>

                    {/* Это ДРУГАЯ ссылка, чем домен слева: посадочная страница
                        рекламодателя на этом сайте. Дыру в ней первым видит трафик,
                        поэтому здесь же и кнопка запроса — та же ручка, что у аккаунта. */}
                    <div style={{ minWidth: 0, display: 'flex', alignItems: 'center', gap: 7 }}>
                      {r.advertiser_url ? (
                        <a href={r.advertiser_url} target="_blank" rel="noreferrer"
                           title={r.advertiser_url}
                           style={{ ...pill('var(--bg-card)', 'var(--accent)', 'var(--accent-border)'),
                             textDecoration: 'none', fontSize: 11.5, maxWidth: '100%',
                             overflow: 'hidden' }}>
                          Посадочная ↗
                        </a>
                      ) : (
                        <>
                          <span style={{ fontSize: 11.5, color: 'var(--text-ghost)' }}>
                            не задана
                          </span>
                          {mayEdit && (
                            <button
                              style={{ ...pill('var(--bg-card)',
                                r.url_state === 'запрошена' ? 'var(--warning-text)' : 'var(--text-secondary)',
                                r.url_state === 'запрошена' ? 'var(--warning-border)' : 'var(--border-card)'),
                                cursor: 'pointer', fontSize: 11.5 }}
                              title={r.url_state === 'запрошена'
                                ? `Уже запрошена: ${r.url_request_text || ''}`
                                : 'Запросить ссылку у площадки'}
                              onClick={() => setUrlAsk({ targetId: r.target_id,
                                name: r.publisher.name || r.publisher.domain,
                                text: r.url_request_text || '' })}>
                              {r.url_state === 'запрошена' ? 'запрошена' : 'запросить'}
                            </button>
                          )}
                        </>
                      )}
                    </div>

                    <div>
                      <div style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
                        color: hot ? 'var(--danger)' : 'var(--text-primary)' }}>
                        {dm(r.period_from)}
                      </div>
                      <div style={{ ...CAP, marginBottom: 0, marginTop: 1 }}>
                        {startNote(r.period_from)}
                      </div>
                    </div>

                    <div>
                      <span style={pill(...st[1])} title={r.urgency_reason || ''}>{st[0]}</span>
                      {r.verdict === 'на переделку' && r.reason && (
                        <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 3 }}>
                          {r.reason}
                        </div>
                      )}
                    </div>

                    {/* Решение по ОДНОЙ площадке. Переделка здесь не дубль групповой:
                        технические требования у каждого сайта свои, и «баннер не проходит
                        по ТТ ASNA» — это про одну строку, а не про весь комплект. */}
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center',
                      justifyContent: 'flex-end' }}>
                      {/* Сайт ЭТОЙ площадки: следующий шаг после нацеливания — пойти и
                          посмотреть баннер там, где он будет крутиться. Ссылка своя у
                          каждой строки, в шапке её быть не может: комплект уходит
                          нескольким площадкам, и одна кнопка на группу открывала бы не
                          тот сайт, о котором человек подумал.

                          Кнопка стоит ПЕРВОЙ в ряду решений и не зависит от вердикта:
                          сходить на сайт бывает нужно и после «Всё ок». */}
                      {!!r.publisher.domain && (
                        <a href={`https://${r.publisher.domain}`} target="_blank"
                           rel="noreferrer" title={`Открыть ${r.publisher.domain} в новой вкладке`}
                           style={{ ...iconBtn(true), textDecoration: 'none' }}>
                          <Ico d={I_OUT} size={13} />
                        </a>
                      )}
                      {/* Скриншоты размещения. Переехали сюда из собственной колонки:
                          действие однотипно соседним, а счётчик читается прямо на
                          кнопке — отдельный столбец под один плюсик держал ширину ради
                          пустоты в большинстве строк. */}
                      {mayEdit && (
                        <button style={{ ...iconBtn(true), width: r.shots_count ? 'auto' : 28,
                          padding: r.shots_count ? '0 7px' : 0, gap: 4 }}
                          onClick={() => openShots(r)}
                          title="Скриншоты размещения на этой площадке">
                          <Ico d={I_PLUS} size={13} />
                          {!!r.shots_count && (
                            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>
                              {r.shots_count}
                            </span>
                          )}
                        </button>
                      )}
                      {!r.verdict && mayApprove && (
                        <>
                          {/* Возврат площадки — НАШ ОРАНЖЕВЫЙ (владелец 12.09.2026), тот
                              же, что у плашек «ждёт проверки». Не красный: красным на
                              этом экране говорит «На переделку» по всему комплекту, и
                              одинаковый цвет у групповой и построчной кнопки стирал бы
                              разницу между «вернуть всё» и «вернуть одну площадку». */}
                          <button disabled={busy}
                            style={{ ...iconBtn(true), background: 'var(--warning-tint)',
                              borderColor: 'var(--warning-border)', color: 'var(--warning-text)' }}
                            title={`Вернуть на переделку только ${r.publisher.name || 'эту площадку'}`}
                            onClick={() => setRework({ pairIds: [r.pair_id], setNo: g.set.no,
                              reason: '', only: r.publisher.name || r.publisher.domain })}>
                            <Ico d={I_REDO} size={13} />
                          </button>
                          <button style={{ ...pill(...TONE.ok), cursor: 'pointer',
                            padding: '5px 12px', fontSize: 11.5 }} disabled={busy}
                            onClick={() => verdict([r.pair_id], 'ок')}>
                            Всё ок
                          </button>
                        </>
                      )}
                      {r.verdict === 'ок' && (
                        <span style={{ ...pill('var(--income)', 'var(--on-accent)', 'var(--income)'),
                          padding: '5px 12px', fontSize: 11.5 }}
                          title={r.decided_by ? `Проверил ${r.decided_by}` : ''}>
                          Проверено
                        </span>
                      )}
                      {r.verdict === 'на переделку' && (
                        <span style={{ ...pill(...TONE.rework), padding: '5px 12px',
                          fontSize: 11.5 }}
                          title={r.decided_by ? `Вернул ${r.decided_by}` : ''}>
                          На переделке
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
              </div>)}
            </div>
          )
        })}
      </div>

      {/* `canApprove={false}`: «Всё работает» — первичная проверка материала, действие
          аккаунта. Трафик отвечает своими кнопками в строке, и два разных вердикта в
          одном окне сливались бы в один жест. */}
      {preview && (
        <CreativePreview files={preview.files} startId={preview.startId}
          set={null} canApprove={false} onReviewed={() => {}}
          onClose={() => setPreview(null)} />
      )}

      {aim && (
        <Modal title={`Ручная ссылка нацеливания · креатив №${aim.no}`}
               summary="Старый путь: ссылка, вставленная руками. Новые так не заводят — кнопка ◎ в строке выпускает свежую сама, потому что ссылка живёт двое суток и хранить её нельзя. Это окно оставлено, чтобы уже заведённую можно было поправить или убрать."
               width={620} onClose={() => setAim(null)}
               footer={
                 <>
                   <button style={btn(false)} onClick={() => setAim(null)}>Отмена</button>
                   <button style={btn(true)} disabled={busy} onClick={saveAim}>Сохранить</button>
                 </>
               }>
          <input autoFocus value={aim.url} placeholder="https://…"
            onChange={e => setAim({ ...aim, url: e.target.value })}
            onKeyDown={e => { if (e.key === 'Enter' && !busy) saveAim() }}
            style={{ ...inp, width: '100%', fontFamily: MONO, fontSize: 12.5 }} />
          {/* Пустое поле — способ ССЫЛКУ СНЯТЬ, а не забытый ввод: заведённая по ошибке
              не должна остаться навсегда. */}
          <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-faint)' }}>
            Пустое поле снимает ссылку.
          </div>
        </Modal>
      )}

      {urlAsk && (
        <Modal title={`Запрос посадочной · ${urlAsk.name}`}
               summary="Текст запишется в карточку, площадка попадёт в ожидающие ответа, и согласовать креатив она уже не сможет, пока не пришлёт ссылку. Письмо система не отправляет — своего канала до площадки у неё нет."
               width={620} onClose={() => setUrlAsk(null)}
               footer={
                 <>
                   <button style={btn(false)} onClick={() => setUrlAsk(null)}>Отмена</button>
                   <button style={btn(true)} disabled={busy || !urlAsk.text.trim()}
                     onClick={saveUrlAsk}>Запросить</button>
                 </>
               }>
          {!!phrases.length && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {/* Пины ДОПИСЫВАЮТ текст, а не заменяют его: готовая фраза — заготовка,
                  нюансы всегда свои. Тот же приём, что в окне аккаунта. */}
              {phrases.map(f => (
                <span key={f.id || f.text} onClick={() => setUrlAsk(a => ({ ...a,
                  text: a.text.trim() ? `${a.text.trim()}\n${f.text}` : f.text }))}
                  style={{ ...pill(...TONE.neutral), cursor: 'pointer', fontWeight: 600 }}>
                  {f.text}
                </span>
              ))}
            </div>
          )}
          <textarea autoFocus rows={3} value={urlAsk.text}
            placeholder="Что именно просим прислать"
            onChange={e => setUrlAsk({ ...urlAsk, text: e.target.value })}
            style={{ ...inp, width: '100%', resize: 'vertical' }} />
        </Modal>
      )}

      {rework && (
        <Modal title={rework.only
                 ? `Вернуть на переделку · ${rework.only}`
                 : `Вернуть креатив №${rework.setNo} на переделку`}
               summary={rework.only
                 ? "Переделка одной площадки: технические требования у каждого сайта свои, и то, что не проходит здесь, могло пройти у остальных. Остальные получатели останутся как есть."
                 : "Материал один на всех получателей, поэтому переделка адресуется всей группе. Аккаунт соберёт новую итерацию."}
               width={560} onClose={() => setRework(null)}
               footer={
                 <>
                   <button style={btn(false)} onClick={() => setRework(null)}>Отмена</button>
                   <button style={btn(true)} disabled={busy || !rework.reason.trim()}
                     onClick={() => verdict(rework.pairIds, 'на переделку', rework.reason)}>
                     Вернуть
                   </button>
                 </>
               }>
          <textarea autoFocus value={rework.reason} rows={4}
            onChange={e => setRework({ ...rework, reason: e.target.value })}
            placeholder="Что переделать"
            style={{ ...inp, width: '100%', resize: 'vertical', fontFamily: UI }} />
        </Modal>
      )}

      {shots && (
        <Modal title={`Файлы · ${shots.row.publisher.name || ''}`}
               summary="Скриншоты размещения — можно выбрать пачкой или перетащить в окно. Имя файла собирается автоматически по цепочке сделка · площадка · креатив, до 10 файлов на пару."
               width={620} onClose={() => setShots(null)}
               footer={
                 <>
                   {!!shots.files.length && (
                     <button style={btn(false)}
                       onClick={() => download(`/traffic/pair/${shots.row.pair_id}/files/archive`,
                                               `${shots.row.pair_prefix || 'shots'}.zip`)}>
                       Скачать архивом
                     </button>
                   )}
                   <button style={btn(true)} onClick={() => setShots(null)}>Готово</button>
                 </>
               }>
          {/* Зона приёма — ВСЁ тело модалки, а не отдельный прямоугольник внизу: человек
              тащит файлы в окно, а не целится в рамку, и промах мимо неё читался бы
              как «перетаскивание не работает». Заголовок и подвал остаются вне зоны —
              там кнопки, и подсветка под ними сбивала бы с толку.

              `preventDefault` на dragOver обязателен — без него браузер не считает
              область принимающей и на drop просто ОТКРОЕТ файл вместо загрузки,
              потеряв заодно всё несохранённое на странице. */}
          <div
            onDragOver={e => { e.preventDefault(); if (mayEdit && !dragOver) setDragOver(true) }}
            onDragLeave={e => { if (e.currentTarget === e.target) setDragOver(false) }}
            onDrop={e => {
              e.preventDefault(); setDragOver(false)
              if (mayEdit) addShots(shots.row, e.dataTransfer?.files)
            }}
            style={{ borderRadius: 12, transition: 'background .12s',
              outline: dragOver ? '2px dashed var(--accent)' : '2px dashed transparent',
              outlineOffset: 4,
              background: dragOver ? 'var(--accent-tint)' : 'transparent' }}>

          {shots.files.map(f => (
            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 10,
                                     padding: '7px 0', borderBottom: '1px solid var(--border-row)' }}>
              <a href="#" onClick={e => { e.preventDefault(); download(`/traffic/file/${f.id}`, f.name) }}
                 style={{ fontFamily: MONO, fontSize: 12, color: 'var(--accent)',
                          textDecoration: 'none' }}>{f.name}</a>
              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                {Math.round((f.size_bytes || 0) / 1024)} КБ
              </span>
              <span style={{ flex: 1 }} />
              {mayEdit && (
                <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy}
                  onClick={() => dropShot(shots.row, f.id)}>Удалить</button>
              )}
            </div>
          ))}
          {!shots.files.length && (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '14px 0' }}>
              {dragOver ? 'Отпустите — заберём все' : 'Пока ничего не приложено. Файлы можно перетащить сюда.'}
            </div>
          )}
          {mayEdit && shots.files.length < SHOT_LIMIT && (
            <label style={{ ...btn(false), display: 'inline-block', marginTop: 12,
                            cursor: busy ? 'progress' : 'pointer' }}>
              {busy ? 'Загрузка…' : `Приложить файлы (${SHOT_LIMIT - shots.files.length} свободно)`}
              <input type="file" multiple accept={SHOT_EXT.join(',')} style={{ display: 'none' }}
                onChange={e => { addShots(shots.row, e.target.files); e.target.value = '' }} />
            </label>
          )}
          {mayEdit && shots.files.length >= SHOT_LIMIT && (
            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-faint)' }}>
              Предел в {SHOT_LIMIT} файлов достигнут — удалите лишние, чтобы добавить новые.
            </div>
          )}
          </div>
        </Modal>
      )}
    </>
  )
}
