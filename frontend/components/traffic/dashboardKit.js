/**
 * Элементы дашборда трафика: полоса выполнения, KPI, стена дней, виновники, статусы.
 *
 * Оформление дизайн-хендоффа (`docs/handoff_traffic_dashboard/`) на НАШИХ поверхностях
 * (решение владельца 04.09.2026): стили из общего кита, цвета из `styles/globals.css`,
 * выпадашки на `PortalPopover`, числа через `lib/salesFormat`.
 *
 * Что из хендоффа сюда НЕ переехало и почему:
 *
 *   · его `tokens.css` — вторая палитра из 47 имён, где `--t1` это наш `--text-primary`,
 *     `--canvas` — `--bg-canvas` и так далее. Подключить её значило бы завести в проекте
 *     второй словарь цвета;
 *   · переключатель светлой/тёмной темы — тёмной темы в проекте нет вовсе, и заводить
 *     её на одном экране значит сделать его непохожим на остальные;
 *   · собственный `StatusPicker` с ручным z-index и снятием `overflow` у скроллера —
 *     `PortalPopover` рендерит в портал, и этой проблемы у него просто нет.
 *
 * Числа сюда приходят ПОСЧИТАННЫМИ (`app/ad/flight.py`). Здесь остаётся только то, что
 * действительно оформление: пороги цвета, геометрия полос, подписи.
 */
import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MONO, Modal, PortalPopover, Z } from '../salesTableKit'
import { grp } from '@/lib/salesFormat'
import { cellKind, columnOf } from '@/lib/dynamicsModel.mjs'

/** Прочерк — общий для всего экрана: пустое НЕ рисуется нулём. */
export const DASH = '—'
export const num = (v) => (v == null ? DASH : grp(v))

/**
 * Цвет выполнения. Пороги считаются ОТ ОЖИДАЕМОГО ТЕМПА, а не от ста процентов:
 * 50 % на пятый день из тридцати — это опережение, а на двадцатый — провал.
 *
 * Когда флайт КОНЧИЛСЯ (`pace >= 1`), жёлтой полосы больше нет. «Отстаёт» означает
 * «догоняет и может догнать»; у законченной РК догонять нечем, и недокрут — это итог,
 * а не отставание. `7E2JWE` с 91,8 % на закрытом флайте рисовалась жёлтой и читалась
 * как «идёт с отставанием», хотя это окончательные −135 537 показов. Следить, чтобы
 * такого не было, — работа трафика (владелец 04.09.2026), и цвет обязан это называть.
 */
export function pctTone(pct, pace) {
  if (pct == null) return 'var(--border-inner)'
  const exp = (pace || 0) * 100
  if (pct >= exp - 8) return 'var(--ok)'
  if ((pace || 0) >= 1) return 'var(--danger)'
  if (pct >= exp - 20) return 'var(--warning-text)'
  return 'var(--danger)'
}

/**
 * Полоса выполнения с РИСКОЙ ожидаемого темпа — где РК должна быть сегодня.
 * Без риски число «36 %» не говорит ничего: оно хорошее на пятый день и плохое на
 * двадцатый, а полоса без отметки выглядит одинаково в обоих случаях.
 */
export const PaceBar = ({ pct, pace, height = 8 }) => (
  <span style={{ position: 'relative', display: 'block', height, borderRadius: 4,
    background: 'var(--bg-subtle)', overflow: 'hidden' }}>
    <span style={{ position: 'absolute', inset: 0, width: `${Math.min(100, Math.max(0, pct || 0))}%`,
      background: pctTone(pct, pace), borderRadius: 4, transition: 'width var(--dur-slow) ease' }} />
    {pace != null && (
      <span title="где РК должна быть по календарю"
        style={{ position: 'absolute', top: -1, bottom: -1, left: `${Math.min(100, pace * 100)}%`,
          width: 2, background: 'var(--text-primary)', opacity: 0.55 }} />
    )}
  </span>
)

/* ── KPI-строка: один этаж, разделители между колонками ───────────────────── */

export const KpiRow = ({ items }) => (
  <div style={{ display: 'grid', gridTemplateColumns: `repeat(${items.length}, minmax(0,1fr))`,
    background: 'var(--bg-card)', border: '1px solid var(--border-card)',
    borderRadius: 18, boxShadow: 'var(--shadow-card)', overflow: 'hidden' }}>
    {items.map((k, i) => (
      <div key={k.label} style={{ padding: '14px 18px', minWidth: 0, display: 'flex',
        flexDirection: 'column', gap: 5,
        borderLeft: i ? '1px solid var(--border-inner)' : 'none' }}>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
          textTransform: 'uppercase', color: 'var(--text-faint)' }}>{k.label}</span>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 7, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: MONO, fontSize: 23, fontWeight: 700, lineHeight: 1,
            color: k.color || 'var(--text-primary)' }}>{k.value}</span>
          {!!k.unit && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{k.unit}</span>}
          {!!k.chip && (
            <span style={{ fontFamily: MONO, fontSize: 10, padding: '2px 7px', borderRadius: 7,
              background: k.chipBg || 'var(--accent-tint)', color: k.chipFg || 'var(--accent)' }}>
              {k.chip}
            </span>
          )}
        </span>
        {/* Подсказка объясняет СОСТАВ числа, а не повторяет подпись. Если у плашки есть
            действие, оно встаёт НА МЕСТО подсказки, а подсказка уезжает в title: место
            в плашке дороже, а «соседний экран контура» и так понятно из перехода. */}
        {k.action ? (
          <span onClick={k.action.onClick} title={k.hint || ''}
            style={{ fontSize: 11, fontWeight: 700, color: 'var(--traffic)', cursor: 'pointer',
              width: 'max-content', borderBottom: '1px dashed var(--border-card)' }}>
            {k.action.label} →
          </span>
        ) : !!k.hint && (
          <span style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.35 }}>{k.hint}</span>
        )}
      </div>
    ))}
  </div>
)

/**
 * Переключатель аналитики. Иконка из хендоффа: развёрнутое — СЕТКА (широкая полоса и
 * два блока под ней, то есть виджеты на месте), свёрнутое — СТРОКИ (остался один
 * список). Иконка меняется, а не только цвет: по цвету одной и той же картинки нельзя
 * понять, что будет по нажатию.
 */
// tone — цвет раздела: у трафика свой, у аккаунтов акцентный (дашборд аккаунта берёт
// этот же переключатель — владелец 28.09.2026: «по примеру трафиков»).
const TOGGLE_TONE = {
  traffic: ['var(--traffic-tint)', 'var(--traffic)'],
  accent: ['var(--accent-tint)', 'var(--accent)'],
}
export const WidgetsToggle = ({ open, onToggle, tone = 'traffic', titles }) => (
  <button onClick={onToggle}
    title={open ? (titles?.[0] || 'Свернуть аналитику') : (titles?.[1] || 'Развернуть аналитику')}
    style={{ width: 34, height: 34, display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', borderRadius: 10, cursor: 'pointer',
      background: open ? TOGGLE_TONE[tone][0] : 'var(--bg-card)',
      border: `1px solid ${open ? TOGGLE_TONE[tone][1] : 'var(--border-card)'}`,
      color: open ? TOGGLE_TONE[tone][1] : 'var(--text-secondary)' }}>
    {open ? (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4 5h16v6H4zM4 15h7v4H4zM15 15h5v4h-5z" />
      </svg>
    ) : (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.9" strokeLinecap="round">
        <path d="M4 6h16M4 12h16M4 18h10" />
      </svg>
    )}
  </button>
)

/* ── статус: пилюля и выбор ───────────────────────────────────────────────── */

/**
 * Тон статуса: [фон, текст, рамка]. Схема статусов ПЛОЩАДКИ задана владельцем
 * 04.09.2026 и читается как шкала готовности: пока ждём — контур на белом (работа не
 * идёт), запустили — заливка (работа идёт), отключили — серое.
 *
 * Цвет здесь несёт СТОРОНУ ожидания: синий — наша (трафик), оранжевый — площадки.
 * Поэтому «пауза» синяя: остановку сделали мы.
 */
export const TONE = {
  // РК
  'ожидает сборки': ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--border-card)'],
  'готова': ['var(--bg-card)', 'var(--blue)', 'var(--blue)'],
  'запущена': ['var(--ok)', 'var(--on-accent)', 'var(--ok)'],
  'пауза': ['var(--blue)', 'var(--on-accent)', 'var(--blue)'],
  'остановлена': ['var(--danger-tint)', 'var(--danger)', 'var(--danger-border)'],
  'окончена': ['var(--bg-subtle)', 'var(--text-primary)', 'var(--border-card)'],
  'архив': ['var(--bg-subtle)', 'var(--text-faint)', 'var(--border-card)'],
  // площадки
  // «Ждёт сборки» — приглушённый: по этой площадке ещё ничего не происходит, и цветом
  // работы её красить нельзя (владелец 18.09.2026). Глаз должен отличать «сборка идёт»
  // от «мяч у трафика» с одного взгляда — иначе человек ищет у себя задачу, которой нет.
  'ждёт сборки': ['var(--bg-subtle)', 'var(--text-muted)', 'var(--border-card)'],
  'у трафика': ['var(--bg-card)', 'var(--blue)', 'var(--blue)'],
  'у площадки': ['var(--bg-card)', 'var(--warning-text)', 'var(--warning-text)'],
  'ждёт запуска': ['var(--bg-card)', 'var(--ok)', 'var(--ok)'],
  'запущен': ['var(--ok)', 'var(--on-accent)', 'var(--ok)'],
  'завершена': ['var(--bg-subtle)', 'var(--text-primary)', 'var(--border-card)'],
}

/**
 * Пилюля статуса. `w` задаёт ФИКСИРОВАННУЮ ширину: в колонке статуса РК плашки разной
 * длины («пауза» против «ожидает сборки») превращают ровный столбец в лесенку, и глаз
 * читает её как беспорядок, а не как данные. Ширина берётся по самому широкому статусу.
 */
export const StatusPill = ({ value, title, w }) => {
  const [bg, fg, border] = TONE[value]
    || ['var(--bg-subtle)', 'var(--text-muted)', 'var(--border-card)']
  return (
    <span title={title || ''} style={{ display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', padding: '3px 10px', borderRadius: 8, background: bg,
      color: fg, border: `1px solid ${border}`, fontSize: 11.5, fontWeight: 600,
      whiteSpace: 'nowrap', boxSizing: 'border-box', ...(w ? { width: w } : null) }}>
      {value}
    </span>
  )
}

/**
 * Выбор статуса. `options` — только то, что человек ВПРАВЕ поставить: у площадки
 * первые три статуса ставит конвейер согласования, и предлагать их в списке значит
 * обещать действие, которое сервер откажется выполнить.
 *
 * Открытый поповер ровно один на экран — этим управляет страница через `openKey`.
 */
export const StatusSelect = ({ value, options, disabled, hint, open, onOpen, onPick }) => (
  <span data-pop-root style={{ position: 'relative', display: 'inline-block' }}>
    <span onClick={disabled ? undefined : onOpen}
      title={disabled ? (hint || 'Ставит согласование креативов') : 'Сменить статус'}
      style={{ cursor: disabled ? 'default' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <StatusPill value={value} title={hint} />
      {!disabled && <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>▾</span>}
    </span>
    <PortalPopover open={!!open} minWidth={190} style={{ padding: 5, zIndex: Z.dropdown }}>
      {(options || []).map(o => (
        <span key={o} onClick={() => onPick(o)}
          style={{ display: 'block', padding: '6px 8px', borderRadius: 7, cursor: 'pointer',
            fontSize: 12, background: o === value ? 'var(--accent-tint)' : 'transparent',
            color: o === value ? 'var(--accent)' : 'var(--text-primary)' }}
          onMouseEnter={e => { if (o !== value) e.currentTarget.style.background = 'var(--bg-subtle)' }}
          onMouseLeave={e => { if (o !== value) e.currentTarget.style.background = 'transparent' }}>
          {o}
        </span>
      ))}
    </PortalPopover>
  </span>
)

/** Услуга с маркером цвета из справочника и поверхностью под названием. */
export const ServiceCell = ({ product, color, surface }) => (
  <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 7, minWidth: 0 }}>
    <span style={{ width: 7, height: 7, borderRadius: 2, marginTop: 4, flex: '0 0 7px',
      background: color || 'var(--text-faint)' }} />
    <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, lineHeight: 1.15 }}>
      <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product || DASH}</span>
      {!!surface && (
        <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em',
          color: 'var(--text-faint)' }}>{surface}</span>
      )}
    </span>
  </span>
)


/* ── управление площадкой: старт · пауза · отключить ──────────────────────── */

export const IcoBtn = ({ title, tone, disabled, onClick, children, size = 26, label }) => (
  <button type="button" onClick={disabled ? undefined : onClick} title={title} disabled={disabled} aria-label={label}
    style={{ width: size, height: size, flex: `0 0 ${size}px`, boxSizing: 'border-box', display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', borderRadius: 8, background: 'var(--bg-card)',
      // обводка — как у соседней «Отчёт по РК» (владелец 17.11.2026), цвет действия — только у значка
      border: `1px solid ${disabled ? 'var(--border-inner)' : 'var(--border-card)'}`,
      color: disabled ? 'var(--text-disabled)' : tone,
      cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.55 : 1, padding: 0 }}>
    {children}
  </button>
)

/* Кнопки «старт / пауза» и «стоп» — ОДНИ на весь трафик: строка РК, пульт РК, площадка, креатив, внешний запуск
   (владелец 17.11.2026: «привести все кнопки пауза/стоп к единообразию»). Вид — обводка как у «Отчёт по РК», цвет действия
   у значка: старт и пауза синие, стоп красный. Свою кнопку с «II» текстом или заливкой рядом не заводить. */
const GLYPH = { pause: 'M7 5h3.5v14H7zM13.5 5H17v14h-3.5z', play: 'M8 5v14l11-7z', stop: 'M6 6h12v12H6z' }
const Glyph = ({ d }) => <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={d} /></svg>

export const RunToggle = ({ running, title, disabled, onClick, size, label }) => (
  <IcoBtn tone="var(--blue)" title={title} disabled={disabled} onClick={onClick} size={size} label={label || (running ? 'Пауза' : 'Запустить')}>
    <Glyph d={running ? GLYPH.pause : GLYPH.play} />
  </IcoBtn>
)

export const StopBtn = ({ title, disabled, onClick, size, label = 'Стоп' }) => (
  <IcoBtn tone="var(--danger)" title={title} disabled={disabled} onClick={onClick} size={size} label={label}>
    <Glyph d={GLYPH.stop} />
  </IcoBtn>
)

/**
 * Кнопки площадки. ДВЕ штуки, и первая — тумблер: старт и пауза это одно состояние
 * «крутит / не крутит», а не два разных действия. Двумя кнопками одна из них всегда
 * была бы серой, и глаз каждый раз решал бы, какая сейчас живая.
 *
 * Вторая кнопка — отключение, и разница с паузой не в оттенке:
 *
 *   · пауза — открутка встаёт, из суточного плана площадка НЕ исключается, её доля
 *     остаётся за ней;
 *   · отключить — исключение из распределения (объём уходит остальным) и немедленная
 *     остановка. В DSP снятие уезжает сразу, перераспределение объёма
 *     действует со следующего суточного плана.
 *
 * Тумблер заперт, пока конвейер согласования не довёл площадку до «ждёт запуска»:
 * запустить площадку с несогласованным креативом — то, что цепочка и предотвращает.
 * Запрет объяснён в подсказке, а не спрятан: кнопка, которая молча не нажимается,
 * читается как поломка.
 */
// `titles` — свои подсказки, когда кнопки стоят не на площадке (креатив целиком, 15.10.2026).
export const PlaceActions = ({ status, canStart, uploaded = true, why, onStart, onPause, onOff, titles = {} }) => {
  const running = status === 'запущен'
  const off = status === 'завершена'
  // Старт и пауза — только после выгрузки в DSP (владелец 30.09.2026); сервер держит тот же
  // запрет (409). «Отключить» остаётся: исключить площадку из распределения можно и до.
  return (
    <span style={{ display: 'inline-flex', gap: 5 }}>
      <RunToggle running={running}
        /* Причина с сервера — тем же правилом, что проверяет запуск (02.10.2026). */
        title={titles.start && !running ? (canStart ? titles.start : titles.cannot) : titles.pause && running ? titles.pause
          : running ? 'Пауза: открутка встанет, доля в плане останется'
          : why ? `Запуск заперт: ${why}`
            : !uploaded ? 'Площадка ещё не выгружена в DSP — сначала «В DSP», потом запуск'
              : canStart ? 'Запустить площадку'
                : 'Креатив ещё не согласован — площадку нельзя запустить'}
        disabled={!uploaded || (!running && !canStart)}
        onClick={running ? onPause : onStart} />
      <StopBtn title={titles.off ? (off ? titles.offDone : titles.off) : off ? 'Площадка уже отключена'
        : 'Отключить: немедленная остановка и исключение из распределения'}
        disabled={off} onClick={onOff} label="Отключить" />
    </span>
  )
}

/* ── стена дней ───────────────────────────────────────────────────────────── */

/**
 * Клетка на день флайта, цвет — выполнение дня против нужного темпа.
 * Четыре состояния, и все четыре разные: норма · просадка · провал · нет данных.
 * День впереди сегодняшнего не красится вовсе — красить будущее нечем.
 */
export const cellState = (c) => {
  if (c.ahead) return 'future'
  if (c.ratio == null) return 'none'
  if (c.ratio >= 0.95) return 'ok'
  if (c.ratio >= 0.8) return 'warn'
  return 'bad'
}
/* Клетка стены в тех же полях, что столбец графика: карточка дня одна на два места и
   ждёт именно такую форму. У стены клетка всегда один день, а «будущий» приходит флагом
   `ahead` — в карточке это `days_past`. */
export const cellBucket = (c) => ({
  plan: c.plan, shows: c.shows, clicks: c.clicks,
  days: 1, date_from: c.date, date_to: c.date,
  days_past: c.ahead ? 0 : 1,
})

/* ── динамика показов: план светлым, факт поверх ──────────────────────────── */

const BAR_ROWS = 18
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

/** «2026-09-01» → «1 сентября». Дата в карточке дня читается словами, а не кодом. */
export const dayName = (iso) => {
  const s = String(iso || '')
  if (s.length < 10) return s
  return `${Number(s.slice(8, 10))} ${MONTHS[Number(s.slice(5, 7)) - 1]}`
}

/**
 * Карточка дня — один в один с макетом: заголовок с датой и подписью РК, под ним четыре
 * строки «план · факт · клики · CTR».
 *
 * Факт, клики и CTR у БУДУЩЕГО дня — прочерк, а не ноль: день ещё не наступил, и ноль
 * означал бы «крутили и получили ноль». Ровно то же правило, что на всём экране.
 */
const CARD_W = 290

// Внешность карточки — одна на оба места, чтобы подсказка у графика и подсказка у стены
// дней не разъехались по скруглению и тени, как это уже случалось с цветами банков.
const CARD_SKIN = {
  width: CARD_W, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 16, boxShadow: '0 1px 3px rgba(28,36,51,.06), 0 18px 46px rgba(28,36,51,.16)',
  padding: '13px 16px 6px',
}

/* Содержимое карточки — ОДНО на два места: график динамики в расхлопе и стена дней в
   виджете. Различается только способ поставить её на экран, поэтому разведены обёртки,
   а не две карточки: две разошлись бы по числу строк на первой же правке. */
// Цвет расхождения с Weborama — одна карта на дашборд трафика и карточку сделки.
// Уровень считает сервер (`stat_sources.mismatch_level`), экран только красит.
export const MISMATCH_FG = { ok: 'var(--ok-fg)', warn: 'var(--warning-fg)', bad: 'var(--danger-fg)' }

const DayCardBody = ({ b, label }) => {
  const past = !!b.days_past
  const ctr = past && b.shows ? (b.clicks / b.shows * 100) : null
  const rows = [
    ['Показы план', num(b.plan), 'var(--text-primary)'],
    ...(b.boost_extra ? [['В т. ч. темп размещения', `+${num(b.boost_extra)}`, 'var(--warning-text)']] : []),
    ['Показы факт', past ? num(b.shows) : DASH, past ? 'var(--blue)' : 'var(--text-faint)'],
    ['Клики', past ? num(b.clicks) : DASH, past ? 'var(--text-primary)' : 'var(--text-faint)'],
    ['CTR', ctr == null ? DASH : `${ctr.toFixed(2).replace('.', ',')} %`,
      past ? 'var(--text-primary)' : 'var(--text-faint)'],
    // Weborama за день — рядом с фактом (владелец 27.09.2026), когда её статистика есть.
    ...(b.wr_shows != null ? [
      ['Показы WR', num(b.wr_shows), 'var(--text-secondary)'],
      ['Расхождение с WR', b.mismatch ? `${String(b.mismatch.pct).replace('.', ',')} %` : DASH,
        MISMATCH_FG[b.mismatch?.level]
          || 'var(--text-faint)'],
    ] : []),
  ]
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
          {b.days > 1 ? `${dayName(b.date_from)} — ${dayName(b.date_to)}` : dayName(b.date_from)}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5,
          letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)',
          whiteSpace: 'nowrap' }}>{label}</span>
      </div>
      {rows.map(([l, v, fg]) => (
        <div key={l} style={{ display: 'flex', alignItems: 'baseline', gap: 12,
          padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
            textTransform: 'uppercase', color: 'var(--text-faint)' }}>{l}</span>
          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 15, fontWeight: 700,
            color: fg }}>{v}</span>
        </div>
      ))}
      {b.repaced && (
        <div style={{ fontSize: 10.5, color: 'var(--warning-text)', padding: '6px 0 4px' }}>
          план пересчитан под недокрут
        </div>
      )}
    </>
  )
}

/* Обёртка ГРАФИКА: карточка следует за курсором по горизонтали и остаётся внутри своего
   графика.

   Позиционируется от САМОГО ГРАФИКА (`absolute` в его координатах), а не от окна.
   Версия на `position: fixed` с координатами мыши считала край по `window`, и в модалке —
   где окно заметно шире содержимого — уезжала наружу: чем правее день, тем дальше. Здесь
   уехать некуда по построению: `left` зажат между нулём и шириной графика минус ширина
   карточки, а оба числа локальные.

   `pointerEvents: none` обязателен: иначе карточка попадает под курсор, столбец теряет
   наведение, и она начинает мигать. */
const DayCard = ({ b, label, at }) => {
  const half = CARD_W / 2
  const left = Math.min(Math.max(at.dx - half, 0), Math.max(0, at.w - CARD_W))
  return (
    <div style={{ position: 'absolute', top: '100%', marginTop: 8, left,
      zIndex: Z.dropdown, pointerEvents: 'none', ...CARD_SKIN }}>
      <DayCardBody b={b} label={label} />
    </div>
  )
}

/* Обёртка СТЕНЫ ДНЕЙ: та же карточка, но в портале и на `fixed`.

   Здесь нельзя как у графика: стена стоит в окне с `overflow: auto`, и `absolute` внутри
   неё обрезался бы прокруткой — готча проекта, из-за неё же все выпадашки живут на
   `PortalPopover`. Координаты берутся у САМОЙ КЛЕТКИ, а не у курсора: клеток в стене до
   тысячи, и обновление состояния на каждое движение мыши перерисовывало бы весь виджет.
   Привязка к клетке заодно не дрожит.

   Карточка переворачивается вверх, если внизу не помещается: у нижних рядов стены места
   под ней нет. Высота взята с запасом константой — измерять нечего, состав строк
   фиксирован. */
const CARD_H = 208

export const DayTip = ({ b, label, x, y, bottom }) => {
  if (typeof document === 'undefined') return null
  const vw = window.innerWidth
  const vh = window.innerHeight
  const left = Math.min(Math.max(x - CARD_W / 2, 8), Math.max(8, vw - CARD_W - 8))
  const below = bottom + 10
  const top = below + CARD_H > vh ? Math.max(8, y - 10 - CARD_H) : below
  return createPortal(
    <div style={{ position: 'fixed', left, top, zIndex: Z.dropdown, pointerEvents: 'none',
      ...CARD_SKIN }}>
      <DayCardBody b={b} label={label} />
    </div>, document.body)
}

/* Правило долек — `columnOf`/`cellKind` из lib/dynamicsModel, одно с графиком расхлопа v2; здесь только вид. */
const DYN_BG = { fact: 'var(--blue)', plan: 'var(--blue-soft)', boost: 'var(--warning)', empty: 'var(--bg-subtle)' }

export const Dynamics = ({ data, label }) => {
  // { i, dx, w } — столбец, положение курсора ВНУТРИ графика и его ширина. Именно в
  // локальных координатах, а не в оконных: карточка дня живёт внутри графика, и все
  // её пределы должны считаться там же.
  const [tip, setTip] = useState(null)
  const box = useRef(null)
  if (!data || !data.buckets.length) {
    return (
      <span style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.45 }}>
        Графика нет: у РК не заведён план или не указан флайт.
      </span>
    )
  }
  const max = Math.max(...data.buckets.map(b => Math.max(b.plan || 0, b.shows || 0))) * 1.15 || 1
  // Подпись оси — ДАТА, а не номер дня: флайт живёт не внутри месяца, и «15» на
  // границе августа и сентября не отвечает на вопрос «какое это число».
  // Подписывать каждый столбец нельзя — сольются; шаг зависит от длины окна.
  const tickEvery = data.buckets.length > 20 ? 5 : data.buckets.length > 10 ? 3 : 1
  return (
    <div ref={box} style={{ position: 'relative' }}>
      <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end' }}>
        {data.buckets.map((b, i) => {
          // «Темп размещения»: добавка буста — верхняя часть плана другим цветом, пропорционально.
          const cells = columnOf(b, max, { future: !b.days_past, rows: BAR_ROWS })
          const on = tip && tip.i === i
          const track = (e) => {
            const r = box.current && box.current.getBoundingClientRect()
            setTip({ i, dx: r ? e.clientX - r.left : 0, w: r ? r.width : 0 })
          }
          return (
            <span key={i} onMouseEnter={track} onMouseMove={track}
              onMouseLeave={() => setTip(null)}
              style={{ flex: '1 1 0', minWidth: 5, display: 'flex', flexDirection: 'column',
                gap: 2, padding: '3px 2px', borderRadius: 6, cursor: 'default',
                background: on ? 'var(--blue-tint)' : 'transparent' }}>
              {Array.from({ length: BAR_ROWS }).map((_, k) => {
                const rank = BAR_ROWS - k
                return (
                  <span key={k} style={{ height: 7, borderRadius: 2, background: DYN_BG[cellKind(rank, cells)] }} />
                )
              })}
            </span>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 3, marginTop: 5 }}>
        {data.buckets.map((b, i) => (
          <span key={i} style={{ flex: '1 1 0', minWidth: 5, textAlign: 'center',
            fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
            {i % tickEvery === 0 ? `${String(b.date_from).slice(8, 10)}.${String(b.date_from).slice(5, 7)}` : ''}
          </span>
        ))}
      </div>
      {tip && <DayCard b={data.buckets[tip.i]} label={label} at={tip} />}
    </div>
  )
}

/* ── креативы под площадкой ───────────────────────────────────────────────── */

/** Подсказка счётчика креативов — одна на старый и новый (v2) вид строки площадки. */
export const creativeCountsTitle = (c) => {
  const short = Math.max(0, (c.agreed || 0) - (c.live || 0))
  return `всего ${c.total} · согласовано ${c.agreed} · запущено ${c.live}`
    + (short ? ` — не запущено ${short} из согласованных` : '')
}

/** Креатив пары можно запустить, когда конвейер согласования его отпустил. */
export const creativeCanStart = (c) => !['ждёт сборки', 'у трафика', 'у площадки'].includes(c.status)

/**
 * Обратный вид: креатив → площадки. Та же выборка, другая группировка — соединение тех же
 * пар с другой стороны. Ключ — КОМПЛЕКТ креатива (`root_set_id`): с 23.09.2026
 * доработка — новый порядковый креатив, а не подмена прежнего (владелец), и колонка с
 * тех пор держит сам комплект, а не корень цепочки.
 *
 * ВАЖНО: обратный вид СУММИРУЕТ, а не перераспределяет. Объём идёт по цепочке «вес
 * площадки → план площадки → поровну по креативам», и план креатива здесь — сумма по
 * площадкам. Иначе кто-нибудь решит, что креативам можно задать веса, — а их у них нет.
 */
export function byCreative(placements) {
  const map = new Map()
  for (const p of placements || []) {
    for (const c of p.creatives || []) {
      const key = c.root_set_id || `no${c.creative_no}`
      const acc = map.get(key) || {
        key, name: c.name, ms_title: c.ms_title, places: [], plan: 0, live: 0, set_id: null, aim_off: null,
      }
      // Нацеливание — на САМУЮ свежую версию комплекта (доработка = новый комплект).
      if (c.set_id && (!acc.set_id || c.set_id > acc.set_id)) { acc.set_id = c.set_id; acc.aim_off = c.aim_off || null }
      acc.places.push({ ...c, domain: p.domain || p.publisher, code: p.code })
      acc.plan += c.plan_show || 0
      if (c.ms_creative_xxhash) acc.live += 1
      map.set(key, acc)
    }
  }
  return [...map.values()].sort((a, b) => b.plan - a.plan)
}

/**
 * KPI приёмки размещения — те же пять и в том же порядке, что в конструкторе медиаплана
 * (`MediaPlanBuilder.GOALS`). Порядок повторён намеренно: трафик и аккаунт смотрят на
 * один и тот же список, и переставленные строки читались бы как другой набор.
 *
 * Значения приходят СТРОКАМИ — в конструкторе это свободный ввод («до 10 %», «0,8»), —
 * поэтому показываем как есть и вердикта не выносим: сверяет человек.
 */
export const GOAL_LABELS = [
  ['freq', 'Частота'],
  ['ctr', 'CTR'],
  ['cr', 'CR'],
  ['volume', 'Показы / клики'],
  ['weborama', 'Расхождение'],
]


/**
 * «Задачи РК» — послание аккаунта трафику с карточки сделки (`traffic_brief`).
 *
 * Пиктограмма ЦВЕТНАЯ, только когда послание есть (владелец 05.09.2026): пустая иконка
 * не должна выглядеть как заполненная, иначе к ней перестанут подходить. Пустую всё
 * равно оставляем кликабельной — иначе не узнать, пусто там или экран сломался.
 *
 * Только чтение: текст писал аккаунт на своей карточке, и правка отсюда означала бы,
 * что задачу можно молча переписать за него.
 */
/** Бриф медиаплана для трафика: гео и таргетинг (владелец 29.09.2026). Только чтение. */
function MpBrief({ brief }) {
  if (!brief) {
    return <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5, padding: '10px 0 14px' }}>
      У сделки нет медиаплана в конструкторе — брифа нет.</div>
  }
  const cap = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0 10px' }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {/* Трафику нужно только это (владелец 29.09.2026): гео первой строкой, дальше
            таргетинг; рекламодатель, юр. лицо и прочая шапка ему лишние. */}
        {[{ key: 'geo', label: 'Гео', values: brief.geo ? [brief.geo] : [] }, ...(brief.targeting || [])].map(g => (
          <div key={g.key} style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: 10, padding: '8px 0',
            borderTop: '1px solid var(--border-inner)', alignItems: 'start' }}>
            <span style={{ ...cap, paddingTop: 4 }}>{g.label}</span>
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {g.values.length ? g.values.map((v, i) => (
                <span key={i} style={{ fontSize: 12.5, lineHeight: 1.45, padding: '3px 9px', borderRadius: 8,
                  background: 'var(--accent-tint)', color: 'var(--accent)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{v}</span>
              )) : <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>—</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* Бейдж плитки ряда «Управление РК» — число записей лога, у «Задач» — что задача от аккаунта есть (05.11.2026).
   Одна деталь на все плитки: квадрат плитки — `position: relative`. */
export const TileBadge = ({ n }) => (n > 0 ? (
  <span style={{ position: 'absolute', top: -6, right: -6, minWidth: 18, height: 18, padding: '0 5px', boxSizing: 'border-box',
    borderRadius: 9, background: 'var(--accent)', color: 'var(--on-accent)', border: '2px solid var(--bg-card)',
    fontFamily: MONO, fontSize: 9, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    {n > 99 ? '99+' : n}
  </span>
) : null)

/* Две вкладки (владелец 29.09.2026): первая — задача аккаунта трафику (`traffic_brief`
   с карточки сделки), вторая — шапка брифа из медиаплана: рекламодатель, юр. лицо,
   бренд, период, агентство, гео и таргетинг. */
/* Шапка окна «Задачи РК»: код сделки и название РК, ниже — юр. лицо и ИНН по изначальному договору
   (владелец 13.10.2026). Нет договора — строки нет. */
const taskSummary = (deal, title, advertiser) => {
  const head = `${deal || ''}${title ? ` · ${title}` : ''}`.trim()
  const who = advertiser?.name ? `${advertiser.name}${advertiser.inn ? ` · ИНН ${advertiser.inn}` : ''}` : ''
  if (!head && !who) return null
  return who ? (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {!!head && <span>{head}</span>}
      <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{who}</span>
    </span>
  ) : head
}

// `trigger(onOpen, has)` — своя кнопка вместо плитки (пульт дашборда v2, 17.11.2026); окно то же.
export const TaskDoc = ({ text, brief, deal, title, advertiser, trigger }) => {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('task')
  const has = !!(text || '').trim()
  const any = has || !!brief
  const fg = any ? 'var(--accent)' : 'var(--text-faint)'
  const tabBtn = (k, label) => (
    <span key={k} onClick={() => setTab(k)} style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 700,
      color: tab === k ? 'var(--text-primary)' : 'var(--text-faint)',
      borderBottom: `2px solid ${tab === k ? 'var(--accent)' : 'transparent'}`, marginBottom: -1 }}>{label}</span>
  )
  const openDoc = () => { setTab(has || !brief ? 'task' : 'brief'); setOpen(true) }
  return (
    <>
      {trigger ? trigger(openDoc, has) : <span onClick={openDoc}
        title={has ? 'Задачи РК от аккаунта и бриф медиаплана'
          : brief ? 'Задачи от аккаунта нет — есть бриф медиаплана' : 'Аккаунт не заполнил «Цели и особенности РК»'}
        style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
          gap: 5, cursor: 'pointer' }}>
        <span style={{ position: 'relative', display: 'grid', placeItems: 'center', width: 40, height: 40, boxSizing: 'border-box',
          borderRadius: 10, background: any ? 'var(--accent-tint)' : 'var(--bg-subtle)',
          border: `1px solid ${any ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
          {/* Задача от аккаунта прописана — бейдж, как у лога (владелец 05.11.2026) */}
          <TileBadge n={has ? 1 : 0} />
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={fg}
            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5" />
            <path d="M9 13h6M9 17h4" />
          </svg>
        </span>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
          textTransform: 'uppercase', color: fg, whiteSpace: 'nowrap' }}>задачи</span>
      </span>}
      {open && (
        <Modal title="Задачи РК" width={760} onClose={() => setOpen(false)}
          summary={taskSummary(deal, title, advertiser)}>
          <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-card)', marginBottom: 12 }}>
            {tabBtn('task', 'Задача от аккаунта')}{tabBtn('brief', 'Бриф медиаплана')}
          </div>
          {tab === 'task' && (has
            ? (
              <div style={{ fontSize: 13, lineHeight: 1.55, whiteSpace: 'pre-wrap',
                wordBreak: 'break-word', color: 'var(--text-primary)', padding: '4px 0 10px' }}>
                {text}
              </div>
            )
            : (
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5,
                padding: '10px 0 14px' }}>
                Аккаунт не заполнил блок «Цели и особенности РК» на карточке сделки.
                Бриф из медиаплана — на соседней вкладке.
              </div>
            ))}
          {tab === 'brief' && <MpBrief brief={brief} />}
        </Modal>
      )}
    </>
  )
}
