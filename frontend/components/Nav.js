/**
 * Навигация приложения. Компонент из дизайн-хендоффа «Навигация 1a», данные подключены.
 * Ниже 1024px — мобильная шапка с меню-аккордеоном, выше — строка контуров с панелями.
 *
 * Данные берутся из @/lib/nav — единственной карты приложения. Здесь нет ни одного
 * списка экранов: добавление раздела делается правкой nav.data.json и ничего больше.
 */
import React, { Fragment, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/router'
// Уровень выпадашек из общей шкалы `Z` кита: одна лестница на весь проект.
const Z_DROPDOWN = 3000
import axios from 'axios'
import { getPermissions, can } from '@/lib/auth'
import { freshMark, hasFresh } from '@/lib/notify.mjs'
import { ago } from '@/lib/dates'
import { TONE, toneOf, toneWeight } from '@/lib/tone'
import { allowedSections, allowedItems, findByPath, entryHref, firstAllowedHref, resolveLegacy } from '@/lib/nav'

/* Сброс дефолтов <button>: вся навигация — настоящие кнопки (фокус с клавиатуры,
   Enter/Space, роль для скринридера), но выглядят ровно как в макете. */
const btnReset = {
  border: 'none', background: 'transparent', padding: 0, margin: 0,
  font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left',
}

/* ── токены ─────────────────────────────────────────────────────────── */
export const T = {
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', hoverBorder: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)',
  accent: 'var(--accent)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)', accentSoft: 'var(--accent-soft)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  pop: '0 8px 28px rgba(28,36,51,.14)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
  bp: 1024,
}

/* ── бейджи ─────────────────────────────────────────────────────────── */
/* Пока не подключены: считать не из чего, источником станет модуль уведомлений.
   Код оставлен нетронутым — он оживёт, когда появится эндпоинт. */
const sumBadges = items => items.reduce((a, i) => a + (i.badge ? parseInt(i.badge, 10) || 0 : 0), 0)
const hasPlus = items => items.some(i => i.badge && i.badge.endsWith('+'))
export const badgeText = list => {
  const total = list.reduce((a, s) => a + sumBadges(s.items), 0)
  return list.some(s => hasPlus(s.items)) ? total + '+' : String(total)
}

const Badge = ({ children, size = 16 }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    minWidth: size, height: size, padding: '0 5px', borderRadius: 6,
    background: T.dangerTint, color: T.danger, fontFamily: T.mono, fontSize: 9.5, fontWeight: 700,
  }}>{children}</span>
)

const BellIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" /><path d="M10 19a2 2 0 0 0 4 0" />
  </svg>
)

const GearIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
    <circle cx="12" cy="12" r="3.2" />
    <path d="M12 4v2M12 18v2M4 12h2M18 12h2M6.5 6.5l1.4 1.4M16.1 16.1l1.4 1.4M17.5 6.5l-1.4 1.4M7.9 16.1l-1.4 1.4" />
  </svg>
)

// Рубль — ярлык на «Операции». Только для админа: раздел с первичными данными,
// в контурном меню ему места не нашлось, а заходить туда приходится часто.
const RubleIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 20V5h4.2a4 4 0 0 1 0 8H9" />
    <path d="M6.5 15.5h7" />
    <path d="M6.5 12.5H9" />
  </svg>
)

// Отчёт — ярлык на сводку руководителя. Только админу, как и рубль: экран показывает
// маржу и всю воронку денег. Столбики, а не документ: при 16 px документ неотличим от
// шестерёнки соседним глазом, а столбики читаются сразу.
const ReportIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 20h16" />
    <path d="M7 20v-6M12 20V8M17 20v-9" />
  </svg>
)

const SearchIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" />
  </svg>
)

/* ══════════════════════════════════════════════════════════════════════
   УВЕДОМЛЕНИЯ — панель канала `app`.

   Собрана по спеке хендоффа 14.09.2026. До неё панель показывала заголовок с
   текстом и ничего больше: тон, группа, объект и кнопка действия приезжали с
   сервера и выбрасывались. Плюс открытие колокольчика отмечало ВСЁ прочитанным —
   человек заглядывал посмотреть и терял список того, что не разобрал.

   Правила, которые легко нарушить обратно:

   · ПРОЧТЕНИЕ НЕ ГАСИТ СОБЫТИЕ. Прочитано — свойство доставки; строка уходит из
     панели сама, когда исчезла причина. Поэтому «прочитать» ничего не удаляет.
   · БЕЙДЖ СЧИТАЕТ НЕПРОЧИТАННЫЕ, а счётчик вкладки — размер выборки. Это разные
     числа, и путать их значит показывать «12» там, где не сделано три.
   · СОРТИРОВКА ПО ТОНУ, потом по времени. Непрочитанные НЕ всплывают наверх:
     иначе после «прочитать все» список перетасовывается под руками.
   · «ПРОЧИТАТЬ ВСЕ» — про текущую вкладку, а не про всё подряд.
   ══════════════════════════════════════════════════════════════════════ */
const authHdr = () => ({ headers: { Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('token') : ''}` } })

// Порядок тонов: сначала то, что блокирует работу. Цвета — те же, что у плашек
// состояния в реестре событий, второй палитры для уведомлений не заводим.
// Вес для сортировки — из общего словаря: порядок тяжести один на систему.

/* ТОН берётся из общего словаря `lib/tone.js` — того же, что у виджета на дашборде и
   у каталога событий. Панель и почта показывают одно событие, и расходиться им нельзя:
   человек, увидевший «срочно» в письме, ищет то же слово в колокольчике.

   Важность несёт СЛОВО, а не только цвет: квадратный маркер 8×8 не читается ни в
   чёрно-белой печати, ни при дальтонизме. Само слово приходит с сервера полем `pill`. */

/* В СПИСКЕ пилюлю получают только `bad` и `warn`. Панель просматривают, чтобы понять,
   что требует действия, и пилюля у каждой строки снова превратила бы её в светофор.
   В письме пилюля есть у всех четырёх тонов — там она отвечает на другой вопрос,
   «стоит ли читать дальше», и карточка в письме одна-две, а не двадцать. */
const ROW_PILL = ['bad', 'warn']

/** Пилюля важности. `compact` — вариант для строки списка: плотнее и без точки.

    СЛОВО приходит с сервера (`pill`), а не берётся из таблицы здесь: оно уже написано
    в письме, и вторая копия разошлась бы с первой — так у тона однажды и завелось два
    словаря. Здесь остаются только цвета: они токены, а в почте литералы. */
function Pill({ tone, word, compact }) {
  const t = TONE[toneOf(tone)]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, flex: '0 0 auto',
      padding: compact ? '2px 7px' : '3px 9px', borderRadius: 9,
      background: t.tint, border: `1px solid ${t.bd}`, color: t.fg,
      fontFamily: T.mono, fontSize: 8.5, fontWeight: 700,
      letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      {!compact && (
        <span style={{ width: 6, height: 6, borderRadius: 2, flex: '0 0 6px',
          background: 'currentColor' }} />
      )}
      {word}
    </span>
  )
}

/** Одно значение для строки «где · сколько · когда».

    В плашки событие кладёт 2–4 числа, и все они нужны в письме. В список из двадцати
    строк помещается одно — то, ради которого уведомление пришло, то есть помеченное
    `hot`. Ключ не выводится: «15 дн.» после «7E2JWE · Эспумизан 09» понятно и без слова
    «просрочка», а место в строке дорогое. */
function rowFact(facts, title) {
  const list = facts || []
  const hot = list.find(f => f && f.hot)
  const v = (hot || list[0] || {}).v || ''
  // Если число уже произнесено в заголовке — в строке его нет. Иначе «просрочено
  // 14 дн.» и «14 дн.» стоят друг под другом и выглядят как два разных факта.
  return v && String(title || '').includes(v) ? '' : v
}

/** Строка панели уведомлений.

    Вынесена отдельно не ради красоты: панель живёт за логином, и посмотреть на неё
    глазами иначе нельзя — а две правки подряд «применились» только на бумаге.
    Компонент чистый, всё приходит пропсами. */
export function NotifyRow({ n, onOpen }) {
  const fact = rowFact(n.facts, n.title)
  const meta = [n.where, fact, ago(n.created_at)].filter(Boolean)
  return (
    /* СТРОКА, А НЕ КАРТОЧКА. Пилюля важности, заголовок, под ним одна служебная
       строка. Ни текста события, ни плашек, ни кнопки: строка целиком нажимаема и
       ведёт на объект, а кнопка действия вела бы туда же — второй элемент управления
       с той же целью только отнимает место и внимание. */
    <button type="button" onClick={() => onOpen(n)}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }}
      onMouseLeave={e => {
        e.currentTarget.style.background = n.is_read ? 'transparent' : 'var(--bg-tint)'
      }}
      style={{
        ...btnReset, textAlign: 'left', cursor: n.link ? 'pointer' : 'default',
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '9px 11px',
        borderRadius: 12, marginBottom: 1,
        background: n.is_read ? 'transparent' : 'var(--bg-tint)',
        borderBottom: `1px solid ${T.inner}`,
      }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3,
        minWidth: 0, flex: 1 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7,
          flexWrap: 'wrap', minWidth: 0 }}>
          {ROW_PILL.includes(n.tone) && <Pill tone={n.tone} word={n.pill} compact />}
          <span style={{ fontSize: 12.5, fontWeight: 600, color: T.t1,
            lineHeight: 1.35, minWidth: 0 }}>{n.title}</span>
        </span>
        {!!meta.length && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 7,
            flexWrap: 'wrap', fontFamily: T.mono, fontSize: 9,
            letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>
            {meta.map((x, k) => (
              <Fragment key={k}>
                {k > 0 && (
                  <span style={{ width: 3, height: 3, borderRadius: 1, flex: '0 0 3px',
                    background: 'var(--border-hover)' }} />
                )}
                <span style={{ minWidth: 0, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x}</span>
              </Fragment>
            ))}
          </span>
        )}
      </span>
      {!n.is_read && (
        /* Метка непрочитанного — квадрат, а не точка: круглая читается как
           статус объекта, квадратная в этой системе означает «моё внимание». */
        <span title="Не прочитано" style={{ width: 7, height: 7, borderRadius: 2,
          marginTop: 5, flex: '0 0 7px', background: T.accent }} />
      )}
    </button>
  )
}

// Ключ «до какого момента уведомления уже показаны человеку». Хранится у него в
// браузере, а не на сервере: это не состояние уведомления (прочитано/нет), а состояние
// ЭТОГО экрана — «колокольчик уже мигал, я посмотрел».
const SEEN_KEY = 'notif_seen_at'

function useNotifications() {
  const [notifs, setNotifs] = useState([])
  const [unread, setUnread] = useState(0)
  const [fresh, setFresh] = useState(false)   // есть непоказанное → колокольчик мигает
  const mark = useRef('')
  const load = () => {
    if (typeof window === 'undefined' || !localStorage.getItem('token')) return
    axios.get('/api/notifications?limit=60', authHdr())
      .then(r => {
        const items = r.data.items || []
        setNotifs(items)
        setUnread(r.data.unread || 0)
        mark.current = freshMark(items)
        let seen = ''
        try { seen = localStorage.getItem(SEEN_KEY) || '' } catch (e) { seen = '' }
        setFresh(hasFresh(mark.current, seen))
      })
      .catch(() => {})
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])

  /** Колокольчик открыли — мигание снято. Именно ОТКРЫТИЕ, а не прочтение строк:
      человек увидел список, и повторно звать его к тому же нечестно. Непрочитанными
      строки при этом остаются — их метку ставит он сам. */
  const markSeen = () => {
    setFresh(false)
    try { localStorage.setItem(SEEN_KEY, mark.current || '') } catch (e) { /* приватный режим */ }
  }

  /** Отметить прочитанными переданные. Пустой список — ничего не делаем: запрос
      без `ids` на сервере означает «все», и случайно отправить его нельзя. */
  const markRead = (ids) => {
    const list = (ids || []).filter(Boolean)
    if (!list.length) return
    axios.post('/api/notifications/read', { ids: list }, authHdr())
      .then(() => {
        setNotifs(ns => ns.map(n => (list.includes(n.id) ? { ...n, is_read: true } : n)))
        setUnread(u => Math.max(0, u - list.length))
      })
      .catch(() => {})
  }
  return { notifs, unread, markRead, fresh, markSeen }
}

// Число креативов, ждущих проверки трафика, — для значка на пункте меню. Отдельная
// лёгкая ручка (`/traffic/queue/count`), обновление раз в минуту, молчит без токена.
function useTrafficWaiting(enabled) {
  const [waiting, setWaiting] = useState(0)
  useEffect(() => {
    if (!enabled) { setWaiting(0); return }
    let alive = true
    const load = () => {
      if (typeof window === 'undefined' || !localStorage.getItem('token')) return
      axios.get('/api/traffic/queue/count', authHdr())
        .then(r => { if (alive) setWaiting(r.data.waiting || 0) })
        .catch(() => {})
    }
    load()
    const t = setInterval(load, 60000)
    return () => { alive = false; clearInterval(t) }
  }, [enabled])
  return waiting
}

function Bell({ onGoto, size = 32 }) {
  const { notifs, unread, markRead, fresh, markSeen } = useNotifications()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('')          // '' — «Все»
  const ref = useRef(null)
  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  // Вкладки — группы из реестра событий, как они там названы. Схлопывать их в
  // пользовательские («Кампании», «Документы») пока не стал: это отдельное
  // соответствие, и придумать его молча значит решить за людей, что куда относится.
  const groups = []
  notifs.forEach(n => { if (n.group && !groups.includes(n.group)) groups.push(n.group) })

  const shown = notifs
    .filter(n => !tab || n.group === tab)
    .slice()
    .sort((a, b) => toneWeight(a.tone) - toneWeight(b.tone)
      || String(b.created_at || '').localeCompare(String(a.created_at || '')))
  const unreadHere = shown.filter(n => !n.is_read).map(n => n.id)

  const openRow = (n) => {
    setOpen(false)
    if (!n.is_read) markRead([n.id])
    if (n.link) onGoto?.(resolveLegacy(n.link))
  }

  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-flex', flex: `0 0 ${size}px` }}>
      <button type="button" className={'nav-icon' + (fresh ? ' nav-bell-new' : '')}
        onClick={() => { const next = !open; setOpen(next); if (next) markSeen() }}
        title={fresh ? 'Новые уведомления' : 'Уведомления'} aria-label="Уведомления" style={{
          ...btnReset,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size,
          borderRadius: 10, border: size >= 36 ? `1px solid ${T.border}` : 'none',
          background: size >= 36 ? T.card : 'transparent', color: T.t3,
        }}>
        <BellIcon />
        {/* Бейдж при нуле не показывается вовсе — не «0». */}
        {unread > 0 && (
          <span className="nav-bell-badge" style={{
            position: 'absolute', top: -4, right: -4, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            minWidth: 17, height: 17, padding: '0 4px', borderRadius: 6, background: T.danger, color: 'var(--bg-card)',
            fontFamily: T.mono, fontSize: 9, fontWeight: 700,
          }}>{unread > 9 ? '9+' : unread}</span>
        )}
      </button>

      {open && (
        <span style={{
          position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 3000,
          width: 420, maxWidth: '92vw', maxHeight: '78vh',
          background: T.card, border: `1px solid ${T.border}`, borderRadius: 16,
          boxShadow: T.pop, display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 14px 8px' }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: T.t1 }}>Уведомления</span>
            {unread > 0 && (
              <span style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, padding: '1px 6px',
                borderRadius: 9, background: T.accentTint, color: T.accent }}>{unread}</span>
            )}
            <span style={{ flex: 1 }} />
            {!!unreadHere.length && (
              <button type="button" onClick={() => markRead(unreadHere)} style={{
                ...btnReset, fontSize: 11.5, color: T.accent, cursor: 'pointer',
              }}>Прочитать все</button>
            )}
          </span>

          {groups.length > 1 && (
            <span style={{ display: 'flex', gap: 5, padding: '0 14px 10px', flexWrap: 'wrap' }}>
              {[['', 'Все', notifs.length], ...groups.map(g =>
                [g, g, notifs.filter(n => n.group === g).length])].map(([k, label, cnt]) => (
                  <button key={k || 'all'} type="button" onClick={() => setTab(k)} style={{
                    ...btnReset, cursor: 'pointer', borderRadius: 9, padding: '4px 9px',
                    fontSize: 11.5, fontWeight: 600,
                    border: `1px solid ${tab === k ? T.accentBorder : T.inner}`,
                    background: tab === k ? T.accentTint : 'transparent',
                    color: tab === k ? T.accent : T.t3,
                  }}>
                    {label}
                    <span style={{ fontFamily: T.mono, fontSize: 9.5, marginLeft: 5,
                      color: tab === k ? T.accent : T.t4 }}>{cnt}</span>
                  </button>
                ))}
            </span>
          )}

          <span style={{ overflowY: 'auto', padding: '0 8px 8px', display: 'flex',
            flexDirection: 'column' }}>
            {!shown.length && (
              <span style={{ padding: '18px 10px', fontSize: 12.5, color: T.t3 }}>
                {notifs.length ? 'Здесь пусто' : 'Уведомлений нет — всё под контролем'}
              </span>
            )}
            {shown.map(n => (
              <NotifyRow key={n.id} n={n} onOpen={openRow} />
            ))}
          </span>
        </span>
      )}
    </span>
  )
}

/* Профиль: имя, роль, «Настройки», «Мои уведомления», «Выйти», версия админу —
   всё перенесено из components/Navbar.js. */
const useSession = () => {
  const [s, setS] = useState({ name: '', role: '', roleLabel: '' })
  useEffect(() => {
    const role = localStorage.getItem('role') || ''
    setS({ name: localStorage.getItem('name') || '', role, roleLabel: localStorage.getItem('role_label') || role })
  }, [])
  return s
}

const menuItem = color => ({
  display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', fontSize: 13,
  color, background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontFamily: 'inherit',
})

function Profile({ onGoto, canSettings, compact = false }) {
  const { name, role, roleLabel } = useSession()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const logout = () => { localStorage.clear(); onGoto?.('/login') }
  const initial = (name || '?').trim().charAt(0).toUpperCase() || '?'
  const size = compact ? 36 : 32
  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <button type="button" onClick={() => setOpen(o => !o)} title={name || ''} aria-label="Профиль" style={{
        ...btnReset,
        display: 'inline-flex', alignItems: 'center', gap: 9, userSelect: 'none',
        paddingLeft: compact ? 0 : 12, borderLeft: compact ? 'none' : `1px solid ${T.inner}`,
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size,
          borderRadius: 10, background: T.t1, color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, flex: `0 0 ${size}px`,
        }}>{initial}</span>
        {!compact && (
          <>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1, maxWidth: 140 }}>
              <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name || '—'}</span>
              {roleLabel && <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{roleLabel}</span>}
            </span>
            <span style={{ fontSize: 10, color: T.t4 }}>▾</span>
          </>
        )}
      </button>
      {open && (
        <span style={{
          position: 'absolute', top: 'calc(100% + 10px)', right: 0, minWidth: 180, zIndex: 3000,
          background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, boxShadow: T.pop,
          overflow: 'hidden', display: 'flex', flexDirection: 'column', animation: `popIn .15s ${T.ease} both`,
        }}>
          <span style={{ padding: '11px 14px', borderBottom: `1px solid ${T.inner}` }}>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.t1 }}>{name || '—'}</span>
            {roleLabel && <span style={{ display: 'block', fontFamily: T.mono, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4, marginTop: 2 }}>{roleLabel}</span>}
          </span>
          {canSettings && <button onClick={() => { setOpen(false); onGoto?.('/settings') }} style={menuItem(T.t2)}>Настройки</button>}
          {/* Личная часть настроек уведомлений — доступна всем, а не только тем,
              у кого есть доступ в «Настройки»: каждый правит свои и ничьи больше. */}
          <button onClick={() => { setOpen(false); onGoto?.('/settings/notifications') }} style={menuItem(T.t2)}>Мои уведомления</button>
          <button onClick={logout} style={menuItem(T.danger)}>Выйти</button>
          {role === 'admin' && (
            <span style={{ padding: '8px 14px', borderTop: `1px solid ${T.inner}`, fontFamily: T.mono, fontSize: 10, letterSpacing: '.04em', color: T.t4 }}>
              версия v{process.env.NEXT_PUBLIC_APP_VERSION}
            </span>
          )}
        </span>
      )}
    </span>
  )
}

/* Раздел с выпадающей панелью. Используется и строкой контуров, и кнопкой
   «Справочники»: у справочников экранов пять, и без панели попасть с контрагентов
   на договоры было бы некуда — раньше это делали табы внутри страницы.
   variant: 'tab' — пункт строки, 'ghost' — контурная кнопка справа.
   align: 'right' — панель прижимается к правому краю, иначе уезжает за окно. */
function Section({ s, variant = 'tab', align = 'left', hover, open, close, closeNow,
                perms, isAdmin, active, onNavigate }) {
  const isOpen = hover === s.key
  /* Панель уходит В ПОРТАЛ, к body. Внутри шапки она жила в её стопке (`zIndex: 40`)
     и оказывалась ПОД модалками карточки сделки (60 и 300): курсор попадал на
     перекрывающий слой, наведение с раздела слетало, и меню мигало. Портал ставит её
     поверх содержимого страницы и по-прежнему ниже модальных подложек (10000) —
     окно должно накрывать меню, а карточка нет.
     Координаты замеряются при открытии: `position: fixed` считает от окна. */
  const wrapRef = useRef(null)
  const [rect, setRect] = useState(null)
  useEffect(() => {
    if (isOpen && wrapRef.current) setRect(wrapRef.current.getBoundingClientRect())
    else setRect(null)
  }, [isOpen])
  /* Активность — по ключу. Индексы сравнивать нельзя: строка контуров отфильтрована,
     а если экран вне карты (active === null) — не активен никто. */
  const isCurrent = s.key === active?.section?.key
  const total = sumBadges(s.items)
  const ghost = variant === 'ghost'
  return (
    /* Мышь — открытие по наведению, закрытие с задержкой 120 мс. Клавиатура —
       фокус открывает панель, Escape закрывает и возвращает фокус на триггер,
       уход фокуса за пределы раздела тоже закрывает. */
    <span
      ref={wrapRef}
      onMouseEnter={() => open(s.key)} onMouseLeave={close}
      onFocus={() => open(s.key)}
      onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) closeNow() }}
      onKeyDown={e => {
        if (e.key === 'Escape' && isOpen) {
          e.stopPropagation()
          e.currentTarget.querySelector('button')?.focus()
          closeNow()
        }
      }}
      style={{ position: 'relative', display: ghost ? 'inline-flex' : undefined }}>
      <button type="button" aria-haspopup="true" aria-expanded={isOpen}
        className={ghost ? 'nav-ghost' : undefined}
        onClick={() => { const h = entryHref(s.key, perms, isAdmin); if (h) onNavigate?.({ href: h }) }} style={{
        ...btnReset,
        display: 'inline-flex', alignItems: 'center', gap: 7,
        ...(ghost
          ? { height: 32, padding: '0 13px', border: `1px solid ${isCurrent ? T.accentBorder : T.border}`, borderRadius: 10, fontSize: 13, background: isCurrent ? T.accentTint : T.card }
          : { padding: '8px 12px', borderRadius: 10, fontSize: 13.5, background: isCurrent ? T.accentTint : isOpen ? T.subtle : 'transparent' }),
        color: isCurrent ? T.accent : T.t2, fontWeight: isCurrent ? 700 : 600,
        whiteSpace: 'nowrap', cursor: 'pointer', transition: 'background-color 150ms ease, color 150ms ease',
      }}>
        {s.title}
        {total > 0 && <Badge>{hasPlus(s.items) ? total + '+' : total}</Badge>}
        <span style={{ fontSize: 9, color: isCurrent ? T.accentSoft : T.t4 }}>▾</span>
      </button>

      {isOpen && rect && createPortal(
        <span
          /* События портала всплывают по РЕАКТ-дереву, а не по DOM: панель остаётся
             ребёнком того же span, и наведение на неё не считается уходом с раздела. */
          onMouseEnter={() => open(s.key)} onMouseLeave={close}
          style={{
            position: 'fixed', top: rect.bottom, minWidth: 212, paddingTop: 6,
            ...(align === 'right' ? { right: Math.max(8, window.innerWidth - rect.right) }
              : { left: rect.left }),
            zIndex: Z_DROPDOWN,
            display: 'flex', flexDirection: 'column', animation: `popIn .18s ${T.ease} both`,
          }}>
          <span style={{
            background: T.card, border: `1px solid ${T.border}`, boxShadow: T.pop, borderRadius: 14,
            padding: 7, display: 'flex', flexDirection: 'column',
          }}>
            {allowedItems(s, perms, isAdmin).map(it => {
              const isActiveItem = active && active.item.href === it.href
              return (
                <button type="button" key={it.key} className="nav-item" onClick={() => onNavigate?.(it)} style={{
                  ...btnReset,
                  display: 'flex', alignItems: 'center', gap: 9, padding: '8px 11px', borderRadius: 10,
                  background: isActiveItem ? T.accentTint : 'transparent',
                }}>
                  <span style={{ width: 7, height: 7, borderRadius: 2, background: isActiveItem ? T.accent : T.hoverBorder }} />
                  <span style={{ fontSize: 13, fontWeight: isActiveItem ? 700 : 600, color: isActiveItem ? T.accent : T.t1, whiteSpace: 'nowrap' }}>{it.label}</span>
                  {it.badge && <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9.5, fontWeight: 700, color: T.danger }}>{it.badge}</span>}
                </button>
              )
            })}
          </span>
        </span>,
        document.body)}
    </span>
  )
}


/* ══════════════════════════════════════════════════════════════════════
   ДЕСКТОП (≥ 1024px)
   ══════════════════════════════════════════════════════════════════════ */
export function NavDesktop({ sections, active, perms, isAdmin, onNavigate, onGear, bell, canSettings, hasDirectory, onLogo, logo = '/logo.png', children }) {
  const [hover, setHover] = useState(null)
  const timer = useRef(null)
  const open = key => { clearTimeout(timer.current); setHover(key) }
  const close = () => { timer.current = setTimeout(() => setHover(null), 120) }
  /* Клавиатура закрывает панель сразу, без «мышиной» задержки. */
  const closeNow = () => { clearTimeout(timer.current); setHover(null) }
  useEffect(() => () => clearTimeout(timer.current), [])

  /* `Section` живёт на уровне модуля (ниже по файлу) — НЕ здесь.

     Объявленный внутри рендера, он пересоздавался как новый тип компонента на каждый
     рендер `NavDesktop`, то есть на каждое движение мыши между разделами: React
     размонтировал панель и монтировал заново, `mouseleave` от удаляемого узла запускал
     закрытие, а `mouseenter` на новый без движения мыши не приходил. Панель открывалась
     и тут же гасла — заметно было при наведении снизу, когда курсор останавливается
     на пункте. Ловушка №2 из навыка `styling-new-page`. */

  const directory = sections.find(s => s.key === 'directory')

  return (
    /* Внешний контейнер липкий целиком: строка фильтров страницы (children)
       прилипает вместе с шапкой — как в старом Navbar.js. */
    /* Оформление (фон, нижняя граница, тень) рисуется ровно один раз — на внешнем
       контейнере, поэтому вид шапки одинаков и с фильтрами, и без них. */
    <div style={{
      position: 'sticky', top: 0, zIndex: 40,
      background: T.card, borderBottom: `1px solid ${T.inner}`, boxShadow: T.shadow,
    }}>
    <div style={{
      padding: '12px 20px',
      display: 'flex', alignItems: 'center', gap: 20, fontFamily: T.sans, color: T.t1,
    }}>
      <button type="button" onClick={onLogo} aria-label="На главную"
        style={{ ...btnReset, display: 'block', paddingRight: 20, borderRight: `1px solid ${T.inner}` }}>
        <img src={logo} alt="Simb-AD" onError={e => { e.target.style.display = 'none' }}
          style={{ height: 22, width: 'auto', display: 'block' }} />
      </button>

      <span style={{ display: 'flex', gap: 2, flex: '1 1 auto', minWidth: 0, flexWrap: 'wrap' }}>
        {/* «Справочники» — не пункт строки контуров, а контурная кнопка справа (как в макете). */}
        {sections.filter(s => s.key !== 'directory').map(s => (
          <Section key={s.key} s={s} hover={hover} open={open} close={close} closeNow={closeNow}
            perms={perms} isAdmin={isAdmin} active={active} onNavigate={onNavigate} />
        ))}
      </span>

      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
        {/* Панель у справочников такая же, как у контуров: попасть в нужный справочник
            из любого раздела, а не только в первый по списку. */}
        {/* Ярлык «Операции» — перед справочниками и только админу (см. RubleIcon). */}
        {isAdmin && (
          <button type="button" className="nav-icon" onClick={() => onNavigate?.({ href: '/exec' })}
            title="Сводка руководителя" aria-label="Сводка руководителя"
            style={{ ...btnReset, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, color: T.t3 }}>
            <ReportIcon />
          </button>
        )}
        {isAdmin && (
          <button type="button" className="nav-icon" onClick={() => onNavigate?.({ href: '/finance/operations' })}
            title="Операции" aria-label="Операции"
            style={{ ...btnReset, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, color: T.t3 }}>
            <RubleIcon />
          </button>
        )}
        {hasDirectory && directory && (
          <Section s={directory} variant="ghost" align="right"
            hover={hover} open={open} close={close} closeNow={closeNow}
            perms={perms} isAdmin={isAdmin} active={active} onNavigate={onNavigate} />
        )}
        {bell}
        {canSettings && (
          <button type="button" className="nav-icon" onClick={onGear} title="Настройки" aria-label="Настройки" style={{ ...btnReset, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, color: T.t3 }}>
            <GearIcon />
          </button>
        )}
        <Profile onGoto={h => onNavigate?.({ href: h })} canSettings={canSettings} />
      </span>
    </div>
    {children && <div style={{ padding: '10px 24px', borderTop: `1px solid ${T.inner}`, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>{children}</div>}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   МОБИЛЬНЫЙ (< 1024px)
   ══════════════════════════════════════════════════════════════════════ */
export function NavMobile({ sections, active, perms, isAdmin, onNavigate, bell, canSettings, onSearch, onLogo, logo = '/logo.png', children }) {
  const [menu, setMenu] = useState(false)
  const curKey = active?.section?.key || null       // null — активного контура нет
  const [exp, setExp] = useState(curKey)            // раскрытый в аккордеоне раздел; null — все свёрнуты
  /* Экран вне карты (curKey === null) — ленты нет вовсе: показывать чужой раздел
     нельзя, десктоп в этой же ситуации тоже не подсвечивает ничего. */
  const cur = curKey ? sections.find(s => s.key === curKey) || null : null
  const rootRef = useRef(null)
  const [menuTop, setMenuTop] = useState(0)         // меню начинается ровно под шапкой

  useEffect(() => { setExp(curKey) }, [curKey])
  useEffect(() => {
    if (!menu || !rootRef.current) return
    setMenuTop(rootRef.current.getBoundingClientRect().bottom)
  }, [menu, children])

  /* блокировка скролла body под открытым меню + закрытие по Esc */
  useEffect(() => {
    if (!menu) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const esc = e => { if (e.key === 'Escape') setMenu(false) }
    document.addEventListener('keydown', esc)
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', esc) }
  }, [menu])

  /* Шапка рисуется всегда: пользователь без доступных разделов должен видеть
     профиль и «Выйти». Без разделов просто нет ленты экранов. */
  return (
    <div ref={rootRef} data-navbar style={{ position: 'sticky', top: 0, zIndex: 50, background: T.card, borderBottom: `1px solid ${T.inner}`, fontFamily: T.sans, color: T.t1 }}>
      {/* строка 1 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px' }}>
        <button type="button" onClick={() => setMenu(m => !m)} title="Разделы" aria-label="Разделы" style={{
          ...btnReset,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
          border: `1px solid ${menu ? T.accentBorder : T.border}`, background: menu ? T.accentTint : T.card,
          borderRadius: 10, color: menu ? T.accent : T.t2, flex: '0 0 36px', cursor: 'pointer',
          transition: 'background-color 150ms ease, color 150ms ease',
        }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
            <path d={menu ? 'M6 6l12 12M18 6L6 18' : 'M4 7h16M4 12h16M4 17h16'} />
          </svg>
        </button>
        <button type="button" onClick={onLogo} aria-label="На главную" style={{ ...btnReset, display: 'block' }}>
          <img src={logo} alt="Simb-AD" onError={e => { e.target.style.display = 'none' }} style={{ height: 18, width: 'auto', display: 'block' }} />
        </button>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          {onSearch && (
            <button type="button" onClick={onSearch} aria-label="Поиск" style={{ ...btnReset, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, border: `1px solid ${T.border}`, borderRadius: 10, color: T.t2, flex: '0 0 36px' }}>
              <SearchIcon />
            </button>
          )}
          {bell}
          <Profile onGoto={h => onNavigate?.({ href: h })} canSettings={canSettings} compact />
        </span>
      </div>

      {/* строка 2 — текущий раздел + лента его экранов */}
      {cur && <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px 10px',
        overflowX: 'auto', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
        /* `#000` здесь — АЛЬФА-КАНАЛ маски, а не цвет: непрозрачное слева, прозрачное
           справа. Переменная темы тут не нужна и вредна — маску красить нечем. */
        maskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
        WebkitMaskImage: 'linear-gradient(to right, #000 calc(100% - 24px), transparent)',
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', paddingRight: 4, flex: '0 0 auto' }}>{cur.title}</span>
        <span style={{ width: 1, height: 16, background: T.inner, flex: '0 0 1px' }} />
        {allowedItems(cur, perms, isAdmin).map(it => {
          const isActiveItem = active && active.item.href === it.href
          return (
            <button type="button" key={it.key} onClick={() => onNavigate?.(it)} style={{
              ...btnReset,
              display: 'inline-flex', alignItems: 'center', padding: '7px 13px', borderRadius: 10,
              background: isActiveItem ? T.accentTint : 'transparent', color: isActiveItem ? T.accent : T.t1,
              fontSize: 13, fontWeight: isActiveItem ? 700 : 600, whiteSpace: 'nowrap', flex: '0 0 auto',
            }}>{it.label}</button>
          )
        })}
      </div>}

      {/* строка фильтров страницы — внутри липкой шапки, прилипает вместе с ней */}
      {children && <div style={{ padding: '10px 14px', borderTop: `1px solid ${T.inner}`, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>{children}</div>}

      {/* полноэкранное меню-аккордеон */}
      {menu && (
        <div style={{
          position: 'fixed', left: 0, right: 0, top: menuTop, bottom: 0, zIndex: 50, background: T.card,
          padding: '12px 14px 18px', display: 'flex', flexDirection: 'column', gap: 8,
          overflowY: 'auto', animation: `popIn .2s ${T.ease} both`,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '0 2px 2px' }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>Все разделы</span>
          </div>

          {sections.map(s => {
            const open = exp === s.key
            const isCurrent = s.key === curKey
            const total = sumBadges(s.items)
            return (
              /* flex:0 0 auto ОБЯЗАТЕЛЕН — иначе карточки сжимаются вместо скролла панели */
              <div key={s.key} style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', border: `1px solid ${open ? T.accentBorder : T.border}`, borderRadius: 14, overflow: 'hidden' }}>
                <button type="button" onClick={() => setExp(open ? null : s.key)} aria-expanded={open} style={{
                  ...btnReset, width: '100%',
                  display: 'flex', alignItems: 'center', gap: 9, padding: '12px 13px',
                  background: open ? T.tint : T.card,
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.accent, flex: '0 0 8px' }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: isCurrent ? T.accent : T.t1 }}>{s.title}</span>
                  {total > 0 && <Badge size={17}>{hasPlus(s.items) ? total + '+' : total}</Badge>}
                  {isCurrent && <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.accentSoft }}>текущий</span>}
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: T.t4 }}>{open ? '▴' : '▾'}</span>
                </button>

                {open && (
                  <div style={{ display: 'flex', flexDirection: 'column', padding: '4px 8px 8px', background: T.card, animation: `popIn .18s ${T.ease} both` }}>
                    {allowedItems(s, perms, isAdmin).map(it => {
                      const isActiveItem = active && active.item.href === it.href
                      return (
                        <button type="button" key={it.key} className="nav-item" onClick={() => { onNavigate?.(it); setMenu(false) }} style={{
                          ...btnReset,
                          display: 'flex', alignItems: 'center', gap: 9, minHeight: 44, padding: '0 10px', borderRadius: 10,
                          background: isActiveItem ? T.accentTint : 'transparent', color: isActiveItem ? T.accent : T.t2,
                          fontSize: 13.5, fontWeight: isActiveItem ? 700 : 600,
                        }}>
                          {it.label}
                          {it.badge && <span style={{ marginLeft: 'auto' }}><Badge size={17}>{it.badge}</Badge></span>}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   ЕДИНАЯ ТОЧКА ВХОДА
   ══════════════════════════════════════════════════════════════════════ */
export default function Nav({ children, onSearch }) {
  const router = useRouter()
  const [mobile, setMobile] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(`(max-width:${T.bp - 1}px)`)
    setMobile(mq.matches)
    const on = e => setMobile(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  /* Права читаются только на клиенте: localStorage на сервере нет, а чтение во время
     рендера давало рассинхрон гидратации и пустую шапку в первом кадре. */
  /* mounted — флаг «первый эффект отработал». Пока он false, состав пунктов не
     считается вовсе: can() внутри allowedSections синхронно читает localStorage
     (admin-bypass), поэтому на сервере разделов ноль, а в первом клиентском кадре
     у админа — все, и React ругается на несовпадение гидратации. Шапка, логотип
     и профиль при этом рисуются сразу. */
  const [mounted, setMounted] = useState(false)
  const [session, setSession] = useState({ perms: null, isAdmin: false })
  useEffect(() => {
    setSession({ perms: getPermissions(), isAdmin: localStorage.getItem('role') === 'admin' })
    setMounted(true)
  }, [])
  const { perms, isAdmin } = session

  const rawSections = mounted ? allowedSections(perms, isAdmin) : []
  // Значок ставим только если пункт вообще виден — иначе и запрос лишний.
  const hasQueue = rawSections.some(s => s.items?.some(i => i.href === '/traffic/queue'))
  const trafficWaiting = useTrafficWaiting(hasQueue)
  // Клонируем ветку с пунктом очереди и вешаем `badge`: механика карты дальше сама
  // покажет число и на пункте, и в значке раздела (sumBadges). Мутировать nav.data.json
  // нельзя — он общий и кэшируется между рендерами.
  const sections = trafficWaiting > 0
    ? rawSections.map(sec => (sec.items?.some(i => i.href === '/traffic/queue')
        ? { ...sec, items: sec.items.map(i => (i.href === '/traffic/queue'
            ? { ...i, badge: String(trafficWaiting) } : i)) }
        : sec))
    : rawSections
  const active = findByPath(router.pathname)

  const go = href => router.push(href)
  // Доступ в «Настройки» — тот же набор ключей, что и в старом Navbar.
  // can() сам пропускает админа — дублировать bypass нельзя.
  const canSettings = mounted && ['settings_balances', 'settings_articles', 'settings_pipelines', 'settings_services', 'settings_field_audit', 'settings_audit'].some(k => can(perms, k))
  const props = {
    sections, perms, isAdmin, active,
    onNavigate: it => go(it.href),
    onGear: () => go('/settings'),
    onLogo: () => { const h = mounted && firstAllowedHref(perms, isAdmin); if (h) go(h) },
    canSettings,
    hasDirectory: mounted && sections.some(s => s.key === 'directory'),
    bell: <Bell onGoto={go} size={mobile ? 36 : 32} />,
    onSearch,
    children,
  }
  return (
    <>
      <style>{`
        @keyframes popIn { from { opacity:0; transform:translateY(-4px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important } }
        .nav-item:hover { background:${T.subtle} }
        .nav-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
        .nav-icon:hover { background:${T.subtle}; color:${T.accent} }
        /* Колокольчик мигает, пока есть непоказанное (владелец 15.09.2026). Признак
           снимается ОТКРЫТИЕМ панели, не прочтением строк, — см. markSeen.
           !important нужен: цвет иконки задан инлайном, а инлайн бьёт класс.
           Общее правило prefers-reduced-motion выше глушит саму анимацию, но цвет
           остаётся — то есть сигнал переживает отключение движения. */
        .nav-bell-new { color:${T.danger} !important }
        .nav-bell-new svg { animation: bellRing 2.6s ease-in-out infinite; transform-origin: 50% 15% }
        .nav-bell-new .nav-bell-badge { animation: bellBlink 1.3s ease-in-out infinite }
        @keyframes bellRing {
          0%, 58%, 100% { transform: rotate(0) }
          62% { transform: rotate(-12deg) }  68% { transform: rotate(10deg) }
          74% { transform: rotate(-7deg) }   80% { transform: rotate(4deg) }
          86% { transform: rotate(-2deg) }
        }
        @keyframes bellBlink { 0%, 100% { opacity:1 } 50% { opacity:.25 } }
      `}</style>
      {mobile ? <NavMobile {...props} /> : <NavDesktop {...props} />}
    </>
  )
}
