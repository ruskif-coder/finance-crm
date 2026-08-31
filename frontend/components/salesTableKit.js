import { useState, useEffect, useRef, useLayoutEffect, Fragment } from 'react'
import { createPortal } from 'react-dom'
import { overlayClose } from '@/lib/overlay'

// Общий набор для v2-таблиц реестра (/sales/deals) и дашборда (/sales/dashboard):
// шрифты, цвета слоёв, конфиг фильтров, компактный мультиселект и иконка-кнопка.
// Раньше эти определения были продублированы байт-в-байт в обеих страницах.

export const MONO = "'JetBrains Mono', ui-monospace, monospace"
export const UI = "'Manrope', system-ui, sans-serif"

// ─── Единая шкала z-index ──────────────────────────────────────────────
// ЕДИНЫЙ источник правды для наложений. Не хардкодить zIndex по месту — брать отсюда,
// иначе слои разъезжаются и «выпадающие списки уходят под элементы».
export const Z = { base: 1, sticky: 20, dropdown: 3000, overlay: 10000, toast: 20000 }

// ─── Modal — модальная панель ──────────────────────────────────────────
// Геометрия та же, что у формы создания сделки (радиус 18, та же тень и riseIn):
// заводить третий визуальный язык для окон незачем. Нужна там, где решение
// принимается по списку, который в window.confirm не читается.
// Закрытие — кликом строго по подложке (e.target === e.currentTarget), иначе
// клик по содержимому закрывал бы окно.
export function Modal({ title, summary, footer, width = 760, onClose, children }) {
  return (
    <div {...overlayClose(onClose)}
      style={{
        position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'rgba(28,36,51,.32)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
        overflow: 'auto', fontFamily: UI,
      }}>
      <div style={{
        width, maxWidth: '100%', maxHeight: '88vh', margin: 'auto', display: 'flex',
        flexDirection: 'column', background: 'var(--bg-card)', borderRadius: 18,
        boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)',
        animation: 'riseIn .28s cubic-bezier(0.22,1,0.36,1) both',
      }}>
        <style>{`@keyframes riseIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}`}</style>
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--border-card)',
          fontSize: 16, fontWeight: 700, color: 'var(--text-primary)',
        }}>{title}</div>
        {summary != null && (
          <div style={{
            padding: '10px 20px', borderBottom: '1px solid var(--border-card)',
            fontSize: 13, color: 'var(--text-secondary)', background: 'var(--bg-subtle)',
          }}>{summary}</div>
        )}
        <div style={{ padding: '10px 20px', overflowY: 'auto', flex: 1 }}>{children}</div>
        {footer != null && (
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--border-card)',
            display: 'flex', gap: 8, alignItems: 'center',
          }}>{footer}</div>
        )}
      </div>
    </div>
  )
}

// ─── PortalPopover — выпадашка, которую НИЧТО не обрежет ────────────────
// Рендерится порталом в document.body с position:fixed от прямоугольника триггера,
// поэтому никакой родительский overflow / transform / стекинг-контекст её не клипает
// и не задвигает под соседние карточки (главная причина «списки уходят под элементы»).
// Использование: обернуть триггер в контейнер и положить рядом <PortalPopover open=...>.
//   <span data-pop-root style={{ position:'relative' }}>
//     <span onClick={()=>toggle()}>Лейбл ▾</span>
//     <PortalPopover open={isOpen} minWidth={220}>…опции…</PortalPopover>
//   </span>
// data-pop-root на панели — чтобы клик внутри не считался «кликом вне» (dismiss по closest).
export function PortalPopover({ open, minWidth = 220, maxHeight = 320, offset = 4, align = 'left', style, children }) {
  const anchor = useRef(null)   // скрытый маркер на месте вызова: его parentElement — триггер
  const [pos, setPos] = useState(null)
  useLayoutEffect(() => {
    if (!open) { setPos(null); return }
    const trigger = anchor.current && anchor.current.parentElement
    if (!trigger) return
    const place = () => {
      const r = trigger.getBoundingClientRect()
      const left = align === 'right'
        ? Math.max(8, Math.min(r.right - minWidth, window.innerWidth - minWidth - 8))
        : Math.max(8, Math.min(r.left, window.innerWidth - minWidth - 8))
      setPos({ top: r.bottom + offset, left })
    }
    place()
    window.addEventListener('scroll', place, true)   // capture: ловим скролл любого предка
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place) }
  }, [open, minWidth, offset, align])
  if (!open || !pos || typeof document === 'undefined') return <span ref={anchor} style={{ display: 'none' }} />
  return (
    <>
      <span ref={anchor} style={{ display: 'none' }} />
      {createPortal(
        // stopPropagation: события портала всплывают по РЕАКТ-дереву (не DOM), иначе клик по
        // опции доходит до onClick родителя-триггера (напр. тумблера ячейки) и переключает его.
        <div data-pop-root onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()} style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: Z.dropdown, minWidth, maxHeight,
          overflowY: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
          borderRadius: 12, boxShadow: 'var(--shadow-card, 0 8px 28px rgba(28,36,51,.14))',
          display: 'flex', flexDirection: 'column', padding: 6, ...style,
        }}>{children}</div>,
        document.body
      )}
    </>
  )
}

// цвета слоя денег: 1-2 серый, 3-4 жёлтый, 5-6 зелёный; none — штриховка
export const PIP = ['var(--text-faint)', 'var(--text-faint)', 'var(--dot-current-dz)', 'var(--dot-current-dz)', 'var(--income)', 'var(--income)']
export const FILL = { 'планируемые': 2, 'реализуемые': 4, 'фактические': 6 }
export const HATCH = 'repeating-linear-gradient(135deg,#C3C9D8 0 3px,#FFFFFF 3px 6px)'
// Красный штрих — «Сделка провалена» (как серый HATCH для неразобранных).
export const HATCH_RED = 'repeating-linear-gradient(135deg,#E5484D 0 3px,#FFFFFF 3px 6px)'
// Зелёный штрих — положительный терминальный исход («Архив успешных сделок»).
// Именно штрих, а не шесть залитых клеток: закрытая сделка — это не «шестая стадия»,
// а выход из конвейера, и читаться должна так же особо, как провал.
export const HATCH_GREEN = 'repeating-linear-gradient(135deg,#2FA37C 0 3px,#FFFFFF 3px 6px)'

// Порядок 6 под-этапов светофора 2\2\2 (по 2 на денежный слой) — совпадает с LIGHT_KEYS
// бэкенда (app/sales/stages.py). 'archive' в список НЕ входит: это терминальный исход,
// он красится зелёной штриховкой по всей полосе, а не шестой клеткой.
export const STAGE_ORDER = ['media_plan', 'booking', 'launch_prep', 'launch', 'closing', 'closing_fact']
// Индикатор 2\2\2: 6 позиций, закрашено до под-этапа стадии (stage_key). Откат — по слою (2/4/6).
// Единый для реестра /sales, дашборда и раскрытой сводки — не дублировать в страницах.
export const StageLayerBar = ({ os, h = 12, w = 7, full }) => {
  const idx = STAGE_ORDER.indexOf(os?.stage_key)
  const n = idx >= 0 ? idx + 1 : (FILL[os?.money_layer] || 0)
  // Три особых состояния красятся штриховкой по всем шести клеткам: это выходы из
  // конвейера и «непонятно где», а не позиции на лестнице.
  //   срыв            → красный штрих
  //   успешный архив  → зелёный штрих
  //   стадии нет      → серый штрих («требует разбора»)
  const hatch = os?.is_lost ? HATCH_RED
    : (os?.is_terminal ? HATCH_GREEN
      : (!os || (!os.stage_key && !os.money_layer) ? HATCH : null))
  const title = os?.is_lost ? 'сделка провалена'
    : (os?.is_terminal ? 'сделка закрыта успешно'
      : (hatch ? 'стадия не определена — требует разбора'
        : `${os?.money_layer || 'слой'} · под-этап ${n}/6`))
  return (
    <span style={{ display: full ? 'flex' : 'inline-flex', gap: 2, flex: full ? '1 1 auto' : '0 0 auto', width: full ? '100%' : undefined }}
      title={title}>
      {PIP.map((c, i) => <span key={i} style={{ flex: full ? '1 1 0' : undefined, width: full ? undefined : w, height: h, borderRadius: 2,
        background: hatch || (i < n ? c : 'var(--border-inner)') }} />)}
    </span>
  )
}

export const FILTER_DROPS = [
  // «Стадия» — НАША лестница (our_stage_id), а не имена из Битрикса: там стадии
  // дублируются по воронкам и содержат имена сотрудников («Закрывающие документы |
  // Мария»), выбирать по ним нельзя. Битриксовая стадия осталась колонкой таблицы.
  ['pipeline', 'Воронка'], ['product', 'Услуга'], ['our_stage_id', 'Стадия'], ['stage_key', 'Слой денег'],
  ['advertiser_id', 'Рекламодатель'], ['brand_id', 'Бренд'], ['agency_id', 'Агентство'], ['account_manager_id', 'Аккаунт'],
]
export const GAP_FIELDS = [
  { value: 'advertiser_id', label: 'без рекламодателя' }, { value: 'brand_id', label: 'без бренда' },
  { value: 'agency_id', label: 'без агентства' }, { value: 'sales_rep_id', label: 'без сейлза' }, { value: 'account_manager_id', label: 'без аккаунта' },
  { value: 'period_from', label: 'без старта РК' }, { value: 'payer', label: 'контрагент не из базы' },
]

// ─── Единый шаблон настраиваемых колонок таблиц сделок ─────────────────
// ОДИН источник правды для реестра (/sales/deals) и дашборда (/sales/dashboard):
// обе таблицы настраиваются как внешний шаблон, а не по отдельности.
// Здесь только «средние» (переставляемые/скрываемые) колонки. Служебные
// prob/sel/brief — фиксированный префикс, задаётся на странице (у реестра есть
// чекбоксы выбора, у дашборда — нет), в меню «Колонки» они не участвуют.
export const DEAL_COLS = [
  { key: 'bitrix_id', w: '82px', label: 'Код', sortable: true },
  { key: 'agency', w: '92px', label: 'Агентство', sortable: true },
  { key: 'advertiser', w: '1.1fr', label: 'Рекламодатель', sortable: true },
  { key: 'brand', w: '1fr', label: 'Бренд', sortable: true },
  { key: 'product', w: '1fr', label: 'Услуга', sortable: true },
  { key: 'period', w: '78px', label: 'Период', sortable: true },
  { key: 'bitrix_stage', w: '1.25fr', label: 'Стадия', sortable: true },
  { key: 'amount', w: '88px', label: 'Сумма', sortable: true, right: true },
  { key: 'sales_rep', w: '92px', label: 'Продавец', sortable: true },
  { key: 'account_manager', w: '88px', label: 'Аккаунт', sortable: true },
  { key: 'payer', w: '1.15fr', label: 'Контрагент', sortable: true },
  { key: 'pipeline', w: '92px', label: 'Воронка', sortable: true },
  { key: 'period_from', w: '84px', label: 'Старт РК', sortable: true },
  { key: 'period_to', w: '84px', label: 'Конец РК', sortable: true },
  { key: 'title', w: '2.5fr', label: 'Сделка', sortable: true },
  { key: 'files', w: '120px', label: 'Файлы' },
]
export const DEAL_DEFAULT_HIDDEN = ['pipeline', 'period_from', 'period_to']
export const DEAL_COL_BY_KEY = Object.fromEntries(DEAL_COLS.map(c => [c.key, c]))
export const DEAL_MIDDLE_KEYS = DEAL_COLS.map(c => c.key)

// Меню «Колонки ▾» — общий компонент: чекбокс скрытия + drag-перестановка.
// Порядок/скрытие хранит страница (в своём localStorage), сюда приходят как пропсы —
// так обе таблицы рисуют ОДИН и тот же список.
export function ColumnsMenu({ open, setOpen, colOrder, hidden, onToggle, onReorder }) {
  const [dragIdx, setDragIdx] = useState(null)
  const drop = (i) => { if (dragIdx === null || dragIdx === i) { setDragIdx(null); return } onReorder(dragIdx, i); setDragIdx(null) }
  return (
    <div style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '8px 13px', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>Колонки ▾</div>
      {open && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setOpen(false)} />
        <div style={{ position: 'absolute', right: 0, top: '110%', marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, minWidth: 210 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Колонки (тащите за ⠿ для порядка)</div>
          {colOrder.map((k, i) => {
            const c = DEAL_COL_BY_KEY[k]; if (!c) return null
            return (
              <div key={k} draggable
                onDragStart={() => setDragIdx(i)} onDragOver={e => e.preventDefault()} onDrop={() => drop(i)} onDragEnd={() => setDragIdx(null)}
                style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, padding: '4px 2px', borderRadius: 6, background: dragIdx === i ? 'var(--accent-tint)' : 'transparent' }}>
                <span title="перетащить" style={{ cursor: 'grab', color: 'var(--text-faint)', userSelect: 'none' }}>⠿</span>
                <input type="checkbox" checked={!hidden.has(k)} onChange={() => onToggle(k)} style={{ cursor: 'pointer' }} />
                <span style={{ flex: 1 }}>{c.label || k}</span>
              </div>
            )
          })}
        </div>
      </>)}
    </div>
  )
}

// ─── Рабочая очередь аккаунта: подсветка строки ────────────────────────
// Обе таблицы (реестр и дашборд) красят строку по состоянию сделки на ПЕРВОЙ стадии
// цепочки («МП Подготовка»). Первую стадию берём по признаку our_stage.is_first —
// не по названию (его переименуют) и не по числовому id (зависит от засева).
//
//   ЗЕЛЁНЫЙ  — МП нет вообще (ни нашего, ни из Битрикса): сделку надо посчитать.
//   ЖЁЛТЫЙ   — МП есть, но сделка всё ещё на первой стадии: план не завизирован.
//              Откуда он — из конвейера годового плана или собран руками — не важно,
//              признак один: сделка не сошла с первой стадии. Гаснет, когда аккаунт откроет МП,
//              отметит обе «Проверено» и сохранит — тогда сделка уходит на
//              следующую стадию (см. _advance_deal_after_verify на бэкенде).
// Границы подсветок строк: зелёная «нужен расчёт», жёлтая «не завизирован».
// Объявлены раньше тонов, потому что тона на них ссылаются.
const NEEDS_MP_BORDER_HEX = '#CDEBDD'
const UNVERIFIED_BORDER_HEX = '#F2E0B8'

// ─── Тона строк по срочности и кнопок по виду действия ────────────────
// Живут в ките, а не на экране: дашборд аккаунта, реестр и будущий кабинет трафика
// красят одно и то же одинаково. Раньше эти же значения были продублированы хексами
// в pages/accounts/dashboard.js — так в проекте уже разъехались BANK_COLORS.
export const ROW_TONE = {
  overdue: { bg: '#FEF7F7', border: '#F0C9CA', dot: 'var(--danger)' },
  today:   { bg: '#FFFBF3', border: '#F2DFC0', dot: 'var(--dot-current-dz)' },
  soon:    { bg: 'var(--bg-card)', border: 'var(--border-row)', dot: 'var(--accent)' },
  normal:  { bg: 'var(--bg-card)', border: 'var(--border-row)', dot: 'var(--text-faint)' },
}

// Тон кнопки — по ВИДУ действия (Verdict.kind с бэкенда), а не один синий на всё:
// «Собрать МП» зелёная, «Проверить» оранжевая, «Пингануть» синяя, «Переделать» красная.
// [фон, текст, рамка]. Рамки берут те же значения, что NEEDS_MP_BORDER/UNVERIFIED_BORDER
// ниже — они здесь же, чтобы не расползались по страницам.
export const CTA_TONE = {
  deal_mp_missing: ['var(--income-tint)', 'var(--income)', NEEDS_MP_BORDER_HEX],
  mp_verify:       ['var(--warning-tint)', 'var(--warning-text)', UNVERIFIED_BORDER_HEX],
  mp_unapproved:   ['var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
  mp_rework:       ['var(--danger-tint)', 'var(--danger)', ROW_TONE.overdue.border],
  booking_confirm: ['var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
  launch_prep:     ['var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
  launch_ready:    ['var(--income-tint)', 'var(--income)', NEEDS_MP_BORDER_HEX],
  act_missing:     ['var(--warning-tint)', 'var(--warning-text)', UNVERIFIED_BORDER_HEX],
  stage_stuck:     ['var(--warning-tint)', 'var(--warning-text)', UNVERIFIED_BORDER_HEX],
  stage_unmapped:  ['var(--danger-tint)', 'var(--danger)', ROW_TONE.overdue.border],
  payment_overdue: ['var(--danger-tint)', 'var(--danger)', ROW_TONE.overdue.border],
}

/** Кнопка действия в строке очереди: пастельный фон, цветной текст, рамка того же тона. */
export const ctaStyle = (kind) => {
  const [bg, fg, border] = CTA_TONE[kind || ''] || ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--border-card)']
  return { background: bg, color: fg, border: `1px solid ${border}`, borderRadius: 9,
           padding: '5px 10px', fontSize: 12, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }
}

export const NEEDS_MP_BG = '#EEF9F4'        // мягкая зелёная заливка строки
export const NEEDS_MP_BORDER = NEEDS_MP_BORDER_HEX
export const UNVERIFIED_BG = '#FFF8E8'      // мягкая жёлтая заливка строки
export const UNVERIFIED_BORDER = UNVERIFIED_BORDER_HEX

const onFirstStage = (d) => !!(d && d.our_stage && d.our_stage.is_first)
const hasAnyMp = (d) => !!((d.our_mps || []).length || (d.files || []).some(f => f.kind === 'mp'))

export const needsMp = (d) => onFirstStage(d) && !hasAnyMp(d)          // зелёный
export const needsMpCheck = (d) => onFirstStage(d) && hasAnyMp(d)      // жёлтый

export const shortLabel = (lab) => (lab ? String(lab).split(' | ')[0].trim() : null)

// компактный мультиселект-дропдаун фильтра
export function MultiDrop({ label, options, selected, onChange, block }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const opts = options || []
  const shown = opts.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase()))
  const active = selected.length > 0
  const box = block
    ? { display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', boxSizing: 'border-box', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontWeight: 600, color: active ? 'var(--accent)' : 'var(--text-primary)', cursor: 'pointer' }
    : { flex: '0 1 auto', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600, color: active ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', cursor: 'pointer' }
  const panel = block
    ? { position: 'static', marginTop: 6, width: '100%', boxSizing: 'border-box', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, maxHeight: 260, overflow: 'hidden', display: 'flex', flexDirection: 'column' }
    : { position: 'absolute', top: '110%', left: 0, marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', minWidth: 220, maxHeight: 320, overflow: 'hidden', display: 'flex', flexDirection: 'column' }
  return (
    <div ref={ref} style={{ position: 'relative', flex: block ? '1 1 auto' : '0 1 auto', width: block ? '100%' : undefined }}>
      <div style={box} onClick={() => setOpen(o => !o)}>{block ? <span>{label}</span> : `${label}${active ? ` · ${selected.length}` : ''} ▾`}{block && <span style={{ fontFamily: 'inherit', color: active ? 'var(--accent)' : 'var(--text-muted)', fontWeight: 600 }}>{active ? `${selected.length} ▾` : 'все ▾'}</span>}</div>
      {open && (
        <div style={panel}>
          {opts.length > 8 && <div style={{ padding: 8 }}>
            <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
              style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
          </div>}
          <div style={{ overflowY: 'auto', padding: 5 }}>
            {active && <div onClick={() => onChange([])} style={{ fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer', padding: '4px 6px' }}>снять все</div>}
            {(() => { let prevGroup = null; return shown.map((o, i) => {
              const on = selected.includes(o.value)
              // Заголовок группы (напр. воронка над её стадиями) — когда o.group меняется.
              const header = o.group && o.group !== prevGroup ? o.group : null
              if (o.group) prevGroup = o.group
              return (
                <Fragment key={`${o.group ?? ''}:${String(o.value)}:${i}`}>
                  {header && <div style={{ padding: '7px 6px 3px', fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{header}</div>}
                  <label style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 6px', fontSize: 12.5, cursor: 'pointer', borderRadius: 7, background: on ? 'var(--accent-tint)' : 'transparent' }}>
                    <input type="checkbox" checked={on} onChange={() => onChange(on ? selected.filter(v => v !== o.value) : [...selected, o.value])} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: o.tone === 'danger' ? 'var(--dot-overdue)' : undefined, fontWeight: o.tone === 'danger' ? 700 : undefined }}>{o.label}</span>
                    {o.count !== undefined && <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{o.count}</span>}
                  </label>
                </Fragment>
              )
            }) })()}
            {!shown.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  )
}

export const IconBtn = ({ title, active, onClick, children }) => (
  <div title={title} onClick={onClick}
    style={{ flex: '0 0 32px', width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 10, cursor: 'pointer',
      background: active ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${active ? '#D7DEFA' : 'var(--border-card)'}`, color: active ? 'var(--accent)' : 'var(--text-muted)' }}>
    {children}
  </div>
)

// ─────────────────────────────────────────────────────────────────────────────
// Канон стилей реестров и форм (карточка / инпут / селект / кнопка / ячейки
// таблицы и CSS-grid). Единый источник: раньше эти объекты дублировались
// байт-в-байт в справочниках (contracts/advertisers/agencies), статьях и на
// всех страницах настроек. Значения — «причёсанный» вид дизайн-системы (ds.jsx):
// var(--*) токены + шрифты MONO/UI. Не заводить локальные копии в страницах.
export const card = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }

export const inp = { padding: '8px 11px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', fontFamily: UI, outline: 'none', boxSizing: 'border-box' }
export const sel = { ...inp, cursor: 'pointer' }
export const inpSm = (w) => ({ ...inp, width: w, padding: '6px 9px' })
export const selSm = (w) => ({ ...sel, width: w, padding: '6px 9px' })
// компактные поля во всю ширину ячейки (инлайн-редактирование строк реестра)
export const ci = { ...inp, padding: '6px 8px', width: '100%' }
export const cs = { ...sel, padding: '6px 6px', width: '100%' }

// btn(primary): primary — акцентная заливка, иначе контурная светлая
export const btn = (p) => ({ padding: '8px 15px', borderRadius: 10, border: p ? 'none' : '1px solid var(--border-card)', cursor: 'pointer', fontSize: 13, fontWeight: p ? 700 : 600, background: p ? 'var(--accent)' : 'var(--bg-card)', color: p ? '#fff' : 'var(--text-secondary)', fontFamily: UI })
export const primaryBtn = btn(true)
export const btnSm = (p) => ({ ...btn(p), padding: '4px 10px', fontSize: 12 })

// заголовок/ячейка обычной <table>
export const th = { padding: '0 10px 10px', textAlign: 'left', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-faint)', borderBottom: '1px solid var(--border-card)', whiteSpace: 'nowrap' }
export const td = { padding: '10px 10px', fontSize: 13, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-row)', verticalAlign: 'middle' }

// ячейка/заголовок CSS-grid реестра (advertisers/agencies)
export const cell = { padding: '0 8px', fontSize: 13, color: 'var(--text-primary)', minWidth: 0 }
export const headCell = (label, right) => <div style={{ padding: '0 8px 10px', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', textAlign: right ? 'right' : 'left', whiteSpace: 'nowrap' }}>{label}</div>

// ─────────────────────────────────────────────────────────────────────────────
// Раскрытая сводка сделки (DealDetail): заголовок колонки, карточка документа,
// кнопки и иконки. По ТЗ «форма сделки» + ds.jsx. Единый источник — не плодить копии.
// Подпись-капс над колонкой блока: Mono 10px uppercase.
/** Плашка состояния: мягкая заливка, цветной текст, рамка того же тона.
 *
 *  Кит не экспортировал ни одной, и к 30.08.2026 в проекте набралось ШЕСТЬ локальных
 *  `chip`/`pill`, из них две — байт в байт одинаковые (реестр сделок и дашборд продаж).
 *  Три оставшихся не сводятся и не должны: у них разные задачи (одна возвращает JSX,
 *  другая раскрашивает по тону, третья — статический объект на своих токенах).
 *  Свести стоило именно повторяющуюся форму, а не совпадение имени.
 */
export const chip = (bg, fg, bd) => ({
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 10px',
  borderRadius: 8, fontSize: 11, fontWeight: 700, fontFamily: UI, whiteSpace: 'nowrap',
  background: bg, color: fg, border: `1px solid ${bd}`,
})

/** Мелкая кликабельная метка в ячейке таблицы — фильтр по значению.
 *  Цвета приходят спредом: они зависят от того, что метка означает в этой колонке. */
export const tagSm = (extra) => ({
  display: 'inline-flex', alignItems: 'center', gap: 3, padding: '1px 6px',
  borderRadius: 6, fontSize: 10.5, cursor: 'pointer', whiteSpace: 'nowrap', ...extra,
})

export const CAP = { fontFamily: MONO, fontSize: 10, letterSpacing: '.09em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)', marginBottom: 13 }
// Белая карточка документа: две строки текста слева + действия справа.
export const docCard = { display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '7px 8px 7px 10px' }
// Кнопка «+ Добавить» — пунктирная рамка, акцентный текст, центр по вертикали.
export const addBtn = { display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 8, border: '1px dashed var(--accent-border)', background: 'transparent', color: 'var(--accent)', fontSize: 11, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: UI, flex: '0 0 auto' }
// Квадратная иконка-кнопка 26×26 (скачать/карандаш/плюс).
export const iconSq = (accent) => ({ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, border: `1px ${accent ? 'solid' : 'solid'} ${accent ? 'var(--accent-border)' : 'var(--border-card)'}`, background: accent ? 'var(--accent-tint)' : 'var(--bg-card)', color: accent ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer', flex: '0 0 auto', padding: 0 })
const sk = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
export const DocIcon = () => <svg width="17" height="17" viewBox="0 0 24 24" style={{ ...sk, stroke: 'var(--text-faint)', flexShrink: 0 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>
export const DownloadIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" style={sk}><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M4 21h16" /></svg>
export const EditIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" style={sk}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>

// Значение, открывающее ValuePopover: выглядит как ЗНАЧЕНИЕ, а не как поле ввода —
// текст плюс пунктирная рамка. Так в проекте сделан выбор из накопительных списков
// (бренд в реестре сделок, вид паблишера, должность контакта).
// Локальная копия осталась в components/publishers/PublisherCard.jsxx — это долг на
// миграцию, а не второй канон.
export const PickValue = ({ value, placeholder, onOpen, size = 16 }) => (
  <span onClick={onOpen} title="Выбрать из списка"
    style={{ fontSize: size, cursor: 'pointer', padding: '5px 8px', borderRadius: 8,
      border: '1px dashed var(--border-card)', display: 'inline-block',
      color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>
    {value || placeholder}
  </span>
)

// Полоса показателей: одна карточка, значения через вертикальные разделители.
// Заведена в ките, а не на странице: такая же полоса нужна ещё на двух экранах, и
// тринадцать локальных форматтеров денег этот проект уже проходил.
//
// `value` приходит готовой строкой — сюда не встраивается форматирование чисел, иначе
// полоса начнёт решать, что такое «ноль»: в реестре это значащий ноль, а в отчёте —
// пустая клетка (`grp0` против `grpDash` в lib/salesFormat).
export const KpiStrip = ({ items }) => (
  <div style={{ ...card, display: 'grid', padding: 0,
    gridTemplateColumns: `repeat(${items.length}, 1fr)` }}>
    {items.map((k, i) => (
      <div key={k.label} style={{ padding: '16px 20px', display: 'flex',
        flexDirection: 'column', gap: 7, minWidth: 0,
        borderLeft: i ? '1px solid var(--border-inner)' : 'none' }}>
        <span style={{ ...CAP, marginBottom: 0 }}>{k.label}</span>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700,
            lineHeight: 1, color: k.color || 'var(--text-primary)' }}>{k.value}</span>
          {!!k.unit && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{k.unit}</span>}
        </span>
        {/* Подсказка объясняет СОСТАВ числа, а не повторяет подпись: «2 активных ·
            1 черновик» отвечает на вопрос, который возникает следом за цифрой. */}
        {!!k.hint && <span style={{ fontSize: 11.5, color: 'var(--text-faint)',
          lineHeight: 1.35 }}>{k.hint}</span>}
      </div>
    ))}
  </div>
)
