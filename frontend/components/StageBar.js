// Полоса «светофор 2/2/2»: шесть стадий сделки по слоям денег.
// Цвет — слой: серый прогноз, оранжевый в работе, зелёный факт.
// Общий компонент реестра и дашборда (был продублирован байт-в-байт).
// Шесть позиций = LIGHT_KEYS бэкенда. Архива здесь нет: он терминальный исход.
export const STAGES = [
  { key: 'media_plan', label: 'Медиаплан', color: 'var(--muted)' },
  { key: 'booking', label: 'Бронь', color: 'var(--muted)' },
  { key: 'launch_prep', label: 'Сбор запуска', color: 'var(--warning, #d97706)' },
  { key: 'launch', label: 'Запуск', color: 'var(--warning, #d97706)' },
  { key: 'closing', label: 'Закрытие подготовка', color: 'var(--success)' },
  { key: 'closing_fact', label: 'Закрытие фактическое', color: 'var(--success)' },
]

/** Полоса из шести стадий: пройденные закрашены, текущая ярче остальных. */
export default function StageBar({ stageKey }) {
  const idx = STAGES.findIndex(s => s.key === stageKey)
  const title = idx >= 0
    ? `${STAGES[idx].label} — ${idx < 2 ? 'планируемые' : idx < 4 ? 'реализуемые' : 'фактические'} деньги`
    : 'Стадия вне маппинга — в слои не попадает'
  return (
    <div title={title} style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
      {STAGES.map((s, i) => (
        <div key={s.key} style={{
          width: 13, height: 9, borderRadius: 2,
          background: idx < 0 ? 'var(--bg-subtle)' : (i <= idx ? s.color : 'var(--bg-subtle)'),
          outline: i === idx ? '1px solid var(--text, #333)' : 'none',
          outlineOffset: 1,
          opacity: idx < 0 ? 0.5 : (i === idx ? 1 : i < idx ? 0.55 : 1),
        }} />
      ))}
      {idx < 0 && <span style={{ fontSize: 10.5, color: 'var(--danger)', marginLeft: 4 }}>вне слоёв</span>}
    </div>
  )
}
