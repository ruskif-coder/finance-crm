import { MONO, UI } from '../salesTableKit'
import { CARD, RISE_KEYFRAMES, rise } from './kit'

// Оболочка мобильной карточки сущности (карточка контрагента, карточка сделки):
// шапка (заголовок · подпись · бейджи) → необязательный слот kpi → ряд табов →
// содержимое активного таба рисует потребитель через children.
//
// Слоты и их назначение:
// - title/subtitle/badges — содержимое шапки; потребитель обычно передаёт уже
//   готовую разметку строки «назад · имя · кнопка редактирования» через title,
//   а не только строку — шапка это допускает.
// - badges — лента чипов под шапкой. Обёрнута в overflowX:auto с явным
//   minWidth:0 у самого контейнера (он лежит в flex-column) — это то, что не
//   даёт одному длинному чипу (например, ссылке на сайт) раздуть ширину
//   страницы вбок. Не убирать overflowX/minWidth без замены на другой способ
//   с тем же результатом: нулевая горизонтальная прокрутка страницы при любой
//   длине чипов.
// - kpi — необязательный слот между шапкой и рядом табов, для сводных цифр,
//   которые должны быть видны на первом экране без скролла (см. карточку
//   контрагента). Участвует в общей лесенке появления наравне с шапкой и
//   основным содержимым.
// - tabs/tab/setTab — ряд табов. tabsLayout переключает раскладку:
//   'scroll' (по умолчанию) — таб шириной по тексту, ряд скроллится вбок,
//   рамка активного таба акцентная; так выглядит карточка сделки (3 таба,
//   не обязаны делить ширину экрана).
//   'equal' — табы равной ширины (flex:1), без горизонтального скролла,
//   рамка активного таба мягче (#D7DEFA); так выглядит карточка контрагента
//   (4 таба, изначальный дизайн до перевода на эту оболочку).
//   Раскладку задаёт потребитель — оболочка не решает это сама по числу табов,
//   чтобы не завязываться на то, сколько их будет у будущих карточек.
// - children — контент активного таба, последняя ступень лесенки появления.
export default function CardShell({ title, subtitle, badges, kpi, tabs = [], tab, setTab, tabsLayout = 'scroll', children }) {
  let riseIdx = 0
  const headerRise = rise(riseIdx++)
  const kpiRise = kpi ? rise(riseIdx++) : null
  const bodyRise = rise(riseIdx++)

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, paddingBottom: 90 }}>
      <style>{RISE_KEYFRAMES}</style>

      <div style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 6, ...headerRise }}>
        <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--text-primary)' }}>{title}</span>
        {subtitle && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{subtitle}</span>}
      </div>

      {badges && <div style={{ display: 'flex', gap: 8, flexWrap: 'nowrap', overflowX: 'auto', minWidth: 0, paddingBottom: 2, WebkitOverflowScrolling: 'touch', ...headerRise }}>{badges}</div>}

      {kpi && <div style={kpiRise}>{kpi}</div>}

      {tabs.length > 0 && (
        tabsLayout === 'equal' ? (
          <div style={{ display: 'flex', gap: 6 }}>
            {tabs.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                flex: 1, padding: '9px 4px', borderRadius: 10, cursor: 'pointer',
                border: `1px solid ${tab === t.key ? '#D7DEFA' : 'var(--border-card)'}`,
                background: tab === t.key ? 'var(--accent-tint)' : 'var(--bg-card)',
                color: tab === t.key ? 'var(--accent)' : 'var(--text-secondary)',
                fontFamily: UI, fontSize: 12, fontWeight: tab === t.key ? 700 : 600,
              }}>{t.label}</button>
            ))}
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 6, overflowX: 'auto', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
            {tabs.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                flex: '0 0 auto', height: 36, padding: '0 14px', borderRadius: 10, cursor: 'pointer',
                border: `1px solid ${tab === t.key ? 'var(--accent)' : 'var(--border-card)'}`,
                background: tab === t.key ? 'var(--accent-tint)' : 'var(--bg-card)',
                color: tab === t.key ? 'var(--accent)' : 'var(--text-primary)',
                fontFamily: UI, fontSize: 13, fontWeight: tab === t.key ? 700 : 600,
              }}>{t.label}</button>
            ))}
          </div>
        )
      )}

      <div style={bodyRise}>{children}</div>
    </div>
  )
}
