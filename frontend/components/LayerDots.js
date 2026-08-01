// Индикатор слоя денег: 6 ячеек-прогресс. Планируемые→2, реализуемые→4, фактические→6.
// Цвета по позиции: 1-2 серый прогноз, 3-4 жёлтый в работе, 5-6 зелёный факт.
// «Без группы» — штриховка (требует разбора). Дизайн-хендофф v2 дашборда сейлза.
const CELL_COLOR = ['var(--text-faint)', 'var(--text-faint)', 'var(--dot-current-dz)', 'var(--dot-current-dz)', 'var(--income)', 'var(--income)']
const FILL = { 'планируемые': 2, 'реализуемые': 4, 'фактические': 6 }
const HATCH = 'repeating-linear-gradient(135deg,#C3C9D8 0 3px,#FFFFFF 3px 6px)'

export default function LayerDots({ layer }) {
  const none = !FILL[layer]
  const n = FILL[layer] || 0
  const title = none ? 'Без группы — требует разбора' : `${layer} · слой денег`
  return (
    <div title={title} style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
      {CELL_COLOR.map((c, i) => (
        <div key={i} style={{
          width: 9, height: 14, borderRadius: 2,
          background: none ? HATCH : (i < n ? c : 'var(--border-inner)'),
        }} />
      ))}
    </div>
  )
}
