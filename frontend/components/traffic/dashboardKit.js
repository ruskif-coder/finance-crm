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
import { MONO, UI, Modal, PortalPopover, Z, selSm } from '../salesTableKit'
import { grp } from '@/lib/salesFormat'

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
  if (pct >= exp - 8) return 'var(--income)'
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
      background: pctTone(pct, pace), borderRadius: 4, transition: 'width .35s ease' }} />
    {pace != null && (
      <span title="где РК должна быть по календарю"
        style={{ position: 'absolute', top: -1, bottom: -1, left: `${Math.min(100, pace * 100)}%`,
          width: 2, background: 'var(--text-primary)', opacity: 0.55 }} />
    )}
  </span>
)

/**
 * Пипсы площадок — ТА ЖЕ ШКАЛА, что у полосы выполнения, только по одной площадке.
 *
 * Решение владельца 05.09.2026. До этого пипсы отвечали «включено ли», а полоса рядом
 * «как идёт»: два языка про один процесс, и жёлтый в одной колонке означал «отстаём по
 * показам», а в соседней «согласовано, но не включили». Теперь цвет и там и там читает
 * открутку, и строка складывается: «17 из 19 крутят, из них четыре красных» — видно не
 * только сколько работает, но и на каких площадках собрался недокрут РК.
 *
 * Два состояния добавляются к шкале, потому что у площадки они есть, а у РК нет:
 *   · контур — согласована, но не включена (мяч у трафика, не у площадки);
 *   · сплошной серый — не крутит вовсе либо крутит, но замеров ещё нет.
 *
 * `pace` берётся у РК: флайт общий, и «где мы должны быть по календарю» у всех её
 * площадок одинаково.
 */
export const Pips = ({ total, on, items, pace }) => {
  const pips = items || []
  return (
    // Пипсы прижаты к левому краю колонки, счётчик — к правому. Иначе счётчик едет
    // вслед за числом площадок: у РК с тремя площадками он стоит на 25 px левее, чем у
    // РК с девятью, и столбец цифр перестаёт читаться как столбец.
    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 8, width: '100%' }}>
      <span style={{ display: 'inline-flex', gap: 2 }}>
        {pips.map((p, i) => {
          const ready = p.s === 'ready'
          const tone = p.s === 'run' ? pctTone(p.pct, pace) : 'var(--border-inner)'
          return (
            <span key={i} title={`${p.domain || ''}${p.s === 'run'
              ? (p.pct == null ? ' · крутит, замеров нет' : ` · ${p.pct} %`)
              : ready ? ' · согласована, не включена' : ' · не крутит'}`}
              style={{ width: 5, height: 11, borderRadius: 2,
                background: ready ? 'transparent' : tone,
                border: ready ? '1px solid var(--warning-text)' : 'none',
                boxSizing: 'border-box' }} />
          )
        })}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>
        {on || 0} / {total || 0}
      </span>
    </span>
  )
}

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
export const WidgetsToggle = ({ open, onToggle }) => (
  <button onClick={onToggle} title={open ? 'Свернуть аналитику' : 'Развернуть аналитику'}
    style={{ width: 34, height: 34, display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', borderRadius: 10, cursor: 'pointer',
      background: open ? 'var(--traffic-tint)' : 'var(--bg-card)',
      border: `1px solid ${open ? 'var(--traffic)' : 'var(--border-card)'}`,
      color: open ? 'var(--traffic)' : 'var(--text-secondary)' }}>
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
  'запущена': ['var(--income)', 'var(--on-accent)', 'var(--income)'],
  'пауза': ['var(--blue)', 'var(--on-accent)', 'var(--blue)'],
  'остановлена': ['var(--danger-tint)', 'var(--danger)', 'var(--danger-border)'],
  'окончена': ['var(--bg-subtle)', 'var(--text-primary)', 'var(--border-card)'],
  'архив': ['var(--bg-subtle)', 'var(--text-faint)', 'var(--border-card)'],
  // площадки
  'у трафика': ['var(--bg-card)', 'var(--blue)', 'var(--blue)'],
  'у площадки': ['var(--bg-card)', 'var(--warning-text)', 'var(--warning-text)'],
  'ждёт запуска': ['var(--bg-card)', 'var(--income)', 'var(--income)'],
  'запущен': ['var(--income)', 'var(--on-accent)', 'var(--income)'],
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

const IcoBtn = ({ title, tone, disabled, onClick, children }) => (
  <button onClick={disabled ? undefined : onClick} title={title} disabled={disabled}
    style={{ width: 26, height: 26, display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', borderRadius: 8, background: 'var(--bg-card)',
      border: `1px solid ${disabled ? 'var(--border-inner)' : tone}`,
      color: disabled ? 'var(--text-disabled)' : tone,
      cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.55 : 1, padding: 0 }}>
    {children}
  </button>
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
export const PlaceActions = ({ status, canStart, onStart, onPause, onOff }) => {
  const running = status === 'запущен'
  const off = status === 'завершена'
  return (
    <span style={{ display: 'inline-flex', gap: 5 }}>
      <IcoBtn
        title={running ? 'Пауза: открутка встанет, доля в плане останется'
          : canStart ? 'Запустить площадку'
            : 'Креатив ещё не согласован — площадку нельзя запустить'}
        tone="var(--blue)"
        disabled={!running && !canStart}
        onClick={running ? onPause : onStart}>
        {running ? (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        )}
      </IcoBtn>
      <IcoBtn title={off ? 'Площадка уже отключена'
        : 'Отключить: немедленная остановка и исключение из распределения'}
        tone="var(--danger)" disabled={off} onClick={onOff}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 6h12v12H6z" />
        </svg>
      </IcoBtn>
    </span>
  )
}

/* ── стена дней ───────────────────────────────────────────────────────────── */

/**
 * Клетка на день флайта, цвет — выполнение дня против нужного темпа.
 * Четыре состояния, и все четыре разные: норма · просадка · провал · нет данных.
 * День впереди сегодняшнего не красится вовсе — красить будущее нечем.
 */
const cellTone = (c) => {
  if (c.ahead) return 'var(--bg-subtle)'
  if (c.ratio == null) return 'var(--border-inner)'
  if (c.ratio >= 0.95) return 'var(--income)'
  if (c.ratio >= 0.8) return 'var(--warning-text)'
  return 'var(--danger)'
}

/**
 * Оба виджета — ОДНОЙ высоты, и задаёт её самый большой (владелец 05.09.2026).
 *
 * Высота одна на двоих, потому что виджеты стоят рядом: разные низы читаются как
 * недоделанная вёрстка, а растянутый до соседа блок с пустой третью — как потерянные
 * данные. Считаем её из окна виновников (десять строк, владелец 04.09.2026), а стена
 * дней показывает СКОЛЬКО ВЛЕЗЕТ в ту же высоту — восемнадцать рядов вместо прежних
 * двенадцати — и скроллит остаток.
 *
 * Число берётся из шага строки, а не подобрано на глаз: поменяется высота клетки —
 * окно поедет вместе с ней.
 */
const CULPRIT_ROW = 38  // содержимое 36 + gap 2
const CULPRITS_SHOWN = 10
export const WIDGET_BODY = CULPRIT_ROW * CULPRITS_SHOWN

// Отступ снизу и справа внутри окна прокрутки: без него последняя строка упирается в
// край, и непонятно, кончился список или обрезан. Справа — чтобы данные не липли к
// полосе прокрутки.
const SCROLL_PAD = { paddingBottom: 14, paddingRight: 8 }

export const DayWall = ({ rows, onOpen }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 7, ...SCROLL_PAD,
    height: WIDGET_BODY, overflowY: 'auto', overflowX: 'hidden' }}>
    {rows.map(r => (
      <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span onClick={() => onOpen?.(r.id)}
          style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)',
            width: 72, flex: '0 0 72px', cursor: onOpen ? 'pointer' : 'default' }}>{r.deal_code}</span>
        <span style={{ display: 'flex', gap: 2, flex: '1 1 auto', minWidth: 0 }}>
          {r.cells.map((c, i) => (
            <span key={i} title={`${c.date}${c.shows == null ? ' · нет данных' : ` · ${grp(c.shows)}`}`}
              style={{ flex: '1 1 0', minWidth: 3, height: 14, borderRadius: 2,
                background: cellTone(c) }} />
          ))}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 11, width: 46, textAlign: 'right',
          flex: '0 0 46px', color: r.done_pct == null ? 'var(--text-faint)' : 'var(--text-secondary)' }}>
          {r.done_pct == null ? DASH : `${r.done_pct} %`}
        </span>
      </div>
    ))}
    {!rows.length && (
      <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
        Пока нечего показывать: ни у одной РК нет ни флайта, ни плана.
      </span>
    )}
  </div>
)

/**
 * Легенда таблицы. Первая группа — ОДИН язык на обе колонки: и полоса выполнения, и
 * пипсы площадок красятся одним правилом, только на разных этажах (05.09.2026). Раньше
 * групп было две, и жёлтый означал в них разное.
 *
 * Вторая группа — то, что есть у площадки и чего нет у РК: согласована, но не включена.
 * Это про очередь, а не про открутку, поэтому не цвет, а контур.
 */
export const TABLE_LEGEND = [
  ['цвет — как идёт открутка', [
    ['идёт по темпу', 'var(--income)'],
    ['отстаёт, но догоняет', 'var(--warning-text)'],
    ['недокрут', 'var(--danger)'],
    ['нет данных', 'var(--border-inner)'],
  ]],
  ['у пипсов ещё', [
    ['согласована, не включена', 'transparent', 'var(--warning-text)'],
  ]],
]

export const WALL_LEGEND = [
  ['норма', 'var(--income)'], ['просадка', 'var(--warning-text)'],
  ['провал', 'var(--danger)'], ['нет данных', 'var(--border-inner)'],
]

/* ── площадки-виновники ───────────────────────────────────────────────────── */

export const Culprits = ({ rows }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 2, ...SCROLL_PAD,
    height: WIDGET_BODY, overflowY: 'auto', overflowX: 'hidden' }}>
    {rows.map(r => (
      <div key={r.publisher_id || r.domain} style={{ display: 'grid',
        gridTemplateColumns: 'minmax(0,1fr) 34px minmax(90px,1.1fr) 92px 92px',
        gap: 10, alignItems: 'center', padding: '7px 0',
        borderTop: '1px solid var(--border-row)' }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.domain}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)',
          textAlign: 'center' }}>{r.campaigns}</span>
        <span style={{ height: 7, borderRadius: 3, background: 'var(--bg-subtle)' }}>
          <span style={{ display: 'block', height: 7, borderRadius: 3,
            width: `${Math.round((r.share || 0) * 100)}%`, background: 'var(--warning-text)' }} />
        </span>
        <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right',
          color: 'var(--danger)' }}>−{grp(r.under)}</span>
        <span style={{ justifySelf: 'end' }}><StatusPill value={r.status} /></span>
      </div>
    ))}
    {!rows.length && (
      <span style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.45 }}>
        Недокрута по площадкам нет. Он появится, когда коннектор принесёт суточный срез
        с разрезом по площадкам.
      </span>
    )}
  </div>
)

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

const DayCard = ({ b, label, at }) => {
  const past = !!b.days_past
  const ctr = past && b.shows ? (b.clicks / b.shows * 100) : null
  const rows = [
    ['Показы план', num(b.plan), 'var(--text-primary)'],
    ['Показы факт', past ? num(b.shows) : DASH, past ? 'var(--blue)' : 'var(--text-faint)'],
    ['Клики', past ? num(b.clicks) : DASH, past ? 'var(--text-primary)' : 'var(--text-faint)'],
    ['CTR', ctr == null ? DASH : `${ctr.toFixed(2).replace('.', ',')} %`,
      past ? 'var(--text-primary)' : 'var(--text-faint)'],
  ]
  /* Карточка следует за курсором ПО ГОРИЗОНТАЛИ и остаётся внутри своего графика.
     
     Позиционируется от САМОГО ГРАФИКА (`absolute` в его координатах), а не от окна.
     Версия на `position: fixed` с координатами мыши считала край по `window`, и в
     модалке — где окно заметно шире содержимого — уезжала наружу: чем правее день, тем
     дальше. Здесь уехать некуда по построению: `left` зажат между нулём и шириной
     графика минус ширина карточки, а оба числа локальные.
     
     `pointerEvents: none` обязателен: иначе карточка попадает под курсор, столбец
     теряет наведение, и она начинает мигать. */
  const half = CARD_W / 2
  const left = Math.min(Math.max(at.dx - half, 0), Math.max(0, at.w - CARD_W))
  return (
    <div style={{ position: 'absolute', top: '100%', marginTop: 8, left,
      zIndex: Z.dropdown, pointerEvents: 'none',
      width: CARD_W, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
      borderRadius: 16, boxShadow: '0 1px 3px rgba(28,36,51,.06), 0 18px 46px rgba(28,36,51,.16)',
      padding: '13px 16px 6px' }}>
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
    </div>
  )
}

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
          const planCells = Math.round((b.plan || 0) / max * BAR_ROWS)
          const factCells = b.days_past ? Math.round((b.shows || 0) / max * BAR_ROWS) : 0
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
                  <span key={k} style={{ height: 7, borderRadius: 2,
                    background: rank <= factCells ? 'var(--blue)'
                      : rank <= planCells ? 'var(--blue-soft)' : 'var(--bg-subtle)' }} />
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

/**
 * Счётчик в строке площадки: всего / согласовано / запущено.
 *
 * Три числа, а не одно: они отвечают на разные вопросы и расходятся в жизни. «Согласовано»
 * — одобрено ПЛОЩАДКОЙ, «запущено» — креатив есть в кабинете DSP. Согласованный
 * может ещё не уехать в DSP, и склеить их значило бы обещать открутку, которой нет.
 *
 * Цвет точки — состояние площадки одним взглядом: зелёная — что-то крутит, оранжевая —
 * согласовано, но в DSP не уехало, серая — согласовывать ещё нечего.
 */
export const CreativeCounts = ({ counts }) => {
  const c = counts || { total: 0, agreed: 0, live: 0 }
  const tone = c.live ? 'var(--income)' : c.agreed ? 'var(--warning-text)' : 'var(--border-inner)'
  const title = `всего ${c.total} · согласовано ${c.agreed} · запущено ${c.live}`
  return (
    <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: tone, flex: '0 0 7px' }} />
      <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>
        {c.total}
        <span style={{ color: 'var(--text-faint)' }}> / </span>
        <span style={{ color: c.agreed ? 'var(--income)' : 'var(--text-faint)' }}>{c.agreed}</span>
        <span style={{ color: 'var(--text-faint)' }}> / </span>
        <span style={{ color: c.live ? 'var(--blue)' : 'var(--text-faint)' }}>{c.live}</span>
      </span>
    </span>
  )
}

const CR_GRID = 'minmax(0,1.6fr) 96px 110px 96px 96px 132px 68px'

/**
 * Строки креативов внутри площадки. Имя человеческое — первой строкой, полный индекс
 * (`<код сделки>-<код площадки>-cr<№>`) — второй: имя дал человек, а индекс видно в
 * кабинете DSP, и по нему сходятся наши и их цифры.
 *
 * Версия комплекта показывается подписью там, где креатив дорабатывали: сообщение одно,
 * но знать, какая правка сейчас в эфире, нужно.
 */
export const CreativeRows = ({ rows, manual, mayEdit, onStatus }) => {
  if (!rows || !rows.length) {
    return (
      <div style={{ fontSize: 11.5, color: 'var(--text-faint)', padding: '8px 0 2px' }}>
        Креативов нет: материал этой площадке ещё не отправляли.
      </div>
    )
  }
  return (
    <div style={{ padding: '6px 0 2px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: CR_GRID, gap: 9, padding: '0 0 5px',
        borderBottom: '1px solid var(--border-inner)' }}>
        {['Креатив', 'ЕРИД', 'Хеш в МС', 'Доля', 'План', 'Статус', ''].map((h, i) => (
          <span key={h + i} style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em',
            textTransform: 'uppercase', color: 'var(--text-faint)',
            textAlign: i >= 3 && i <= 4 ? 'right' : 'left' }}>{h}</span>
        ))}
      </div>
      {rows.map(c => (
        <div key={c.id} style={{ display: 'grid', gridTemplateColumns: CR_GRID, gap: 9,
          alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, lineHeight: 1.2 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.name || `креатив №${c.set_no ?? c.creative_no}`}
              {c.origin === 'доработка' && (
                <span title="в эфире доработанная версия сообщения"
                  style={{ marginLeft: 6, fontSize: 9, padding: '1px 5px', borderRadius: 5,
                    background: 'var(--bg-subtle)', color: 'var(--text-muted)' }}>
                  правка №{c.version_no}
                </span>
              )}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>
              {c.ms_title || DASH}
            </span>
          </span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: c.erid ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
            {c.erid || DASH}</span>
          <span style={{ fontFamily: MONO, fontSize: 10,
            color: c.ms_creative_xxhash ? 'var(--blue)' : 'var(--text-faint)' }}>
            {c.ms_creative_xxhash || 'не заведён'}</span>
          <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
            {c.share ? `${(c.share * 100).toFixed(1)} %` : DASH}</span>
          <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
            {num(c.plan_show)}</span>
          <span><StatusPill value={c.status}
            title={(manual || []).includes(c.status) ? '' : 'Ставит согласование креативов'} /></span>
          <span style={{ justifySelf: 'end' }}>
            {mayEdit && (
              <PlaceActions status={c.status === 'отклонён' ? 'завершена' : c.status}
                canStart={c.status !== 'у трафика' && c.status !== 'у площадки'}
                onStart={() => onStatus(c, 'запущен')}
                onPause={() => onStatus(c, 'пауза')}
                onOff={() => onStatus(c, 'отклонён')} />
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * Обратный вид: креатив → площадки. Та же выборка, другая группировка — соединение тех же
 * пар с другой стороны. Ключ — КОРЕНЬ цепочки доработок (`root_set_id`): креатив как
 * рекламное сообщение един, правки технические (владелец 04.09.2026).
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
        key, name: c.name, ms_title: c.ms_title, places: [], plan: 0, live: 0,
      }
      acc.places.push({ ...c, domain: p.domain || p.publisher, code: p.code })
      acc.plan += c.plan_show || 0
      if (c.ms_creative_xxhash) acc.live += 1
      map.set(key, acc)
    }
  }
  return [...map.values()].sort((a, b) => b.plan - a.plan)
}


/**
 * Кто ведёт РК с нашей стороны — две строки рядом с управлением: аккаунт и трафик.
 *
 * Аккаунт только показывается: он хозяин сделки до размещения и после сверки, и менять
 * его из дашборда трафика значило бы переставлять чужую ответственность мимо той
 * карточки, где её видно.
 *
 * Трафика мастер МЕНЯЕТ прямо здесь (владелец 04.09.2026): решение «передать кампанию»
 * принимают, глядя на её ход, а не открывая сборку запуска. Рядовому та же строка
 * показывается текстом — знать, на ком РК, нужно всем.
 */
export const Owners = ({ owners, reps, onPick }) => {
  if (!owners) return null
  const line = (label, node) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minHeight: 26 }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
        textTransform: 'uppercase', color: 'var(--text-faint)', width: 62,
        flex: '0 0 auto' }}>{label}</span>
      {node}
    </div>
  )
  const txt = (v, faint) => (
    <span style={{ fontSize: 12.5, fontWeight: 600,
      color: faint ? 'var(--text-faint)' : 'var(--text-primary)' }}>{v}</span>
  )
  return (
    <div style={{ marginLeft: 'auto', minWidth: 260, display: 'flex',
      flexDirection: 'column', gap: 4 }}>
      {line('аккаунт', txt(owners.account || 'не назначен', !owners.account))}
      {line('трафик', owners.can_change_traffic
        ? (
          <select style={{ ...selSm(190), fontSize: 12.5 }}
            value={owners.traffic_user_id == null ? '' : String(owners.traffic_user_id)}
            onChange={e => onPick(e.target.value === '' ? null : Number(e.target.value))}>
            <option value="">— не назначен —</option>
            {(reps || []).map(r => (
              <option key={r.user_id} value={String(r.user_id)}>
                {r.is_master ? '★ ' : ''}{r.name}
              </option>
            ))}
          </select>
        )
        : txt(owners.traffic || 'не назначен', !owners.traffic))}
    </div>
  )
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
export const TaskDoc = ({ text, deal, title }) => {
  const [open, setOpen] = useState(false)
  const has = !!(text || '').trim()
  const fg = has ? 'var(--accent)' : 'var(--text-faint)'
  return (
    <>
      <span onClick={() => setOpen(true)} title={has ? 'Задачи РК от аккаунта'
        : 'Аккаунт не заполнил «Цели и особенности РК»'}
        style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
          gap: 5, cursor: 'pointer', padding: '2px 8px' }}>
        <span style={{ display: 'grid', placeItems: 'center', width: 44, height: 44,
          borderRadius: 13, background: has ? 'var(--accent-tint)' : 'var(--bg-subtle)',
          border: `1px solid ${has ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={fg}
            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5" />
            <path d="M9 13h6M9 17h4" />
          </svg>
        </span>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
          textTransform: 'uppercase', color: fg, whiteSpace: 'nowrap' }}>задачи рк</span>
      </span>
      {open && (
        <Modal title="Задачи РК" width={620} onClose={() => setOpen(false)}
          summary={`${deal || ''}${title ? ` · ${title}` : ''}`.trim() || null}>
          {has
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
                Пока его нет, цели размещения известны только из медиаплана.
              </div>
            )}
        </Modal>
      )}
    </>
  )
}
