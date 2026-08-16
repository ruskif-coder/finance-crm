import { Children, Fragment, isValidElement, cloneElement } from 'react'
import { MONO, UI } from '../salesTableKit'
import { CARD, RISE_KEYFRAMES, rise } from './kit'

// Оболочка мобильного отчёта: заголовок с правой подписью · строка фильтров ·
// последовательность карточек. Лесенку появления раздаёт оболочка, чтобы порядок
// задержек не приходилось поддерживать руками в каждом отчёте.
export default function ReportShell({ title, meta, filters, children }) {
  // Фрагменты (<>...</>) намеренно не поддерживаются: раздать _riseIndex их детям означало бы
  // разворачивать вложенность произвольной глубины, а навесить проп на сам Fragment React не даст
  // (не валидный DOM/компонентный проп) — такой ребёнок пропускается без индекса и без предупреждения
  // в консоли. Секциям отчёта нужно быть прямыми детьми ReportShell, не обёрнутыми во фрагмент.
  let i = 0
  const sections = Children.map(children, (ch) => {
    if (!isValidElement(ch) || ch.type === Fragment) return ch
    return cloneElement(ch, { _riseIndex: i++ })
  })

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
      <style>{RISE_KEYFRAMES}</style>

      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
        <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--text-primary)' }}>{title}</span>
        {meta && <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{meta}</span>}
      </div>

      {filters && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, position: 'relative' }}>{filters}</div>
      )}

      {sections}
    </div>
  )
}

// Карточка отчёта. padded=false — когда внутри сетка во всю ширину (KPI 2×2),
// иначе внутренние отступы съедают разделители.
// padding/gap — необязательное переопределение отступов поверх умолчаний (16 / 12-или-0),
// для карточек с точечно иной вёрсткой (см. «Счета», «Детализация по месяцам» в CashflowMobile).
export function ReportSection({ title, aside, padded = true, padding, gap, children, _riseIndex = 0 }) {
  const resolvedPadding = padding !== undefined ? padding : (padded ? 16 : undefined)
  const resolvedGap = gap !== undefined ? gap : (title ? 12 : 0)
  return (
    <div style={{ ...CARD, ...(resolvedPadding !== undefined ? { padding: resolvedPadding } : null), display: 'flex', flexDirection: 'column', gap: resolvedGap, ...rise(_riseIndex) }}>
      {title && (
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
          {aside}
        </div>
      )}
      {children}
    </div>
  )
}
