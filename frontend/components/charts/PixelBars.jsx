// «Пиксельные» бары — язык графиков раздела «Продажи → Аналитика» (24.10.2026: владелец — «из таких же баров собрать»).
// Величина — число одинаковых ячеек с зазором 2 px; стек слоёв — ячейки подряд разными цветами, пустое — `EMPTY`.
// Одна реализация на «Аналитику» и «План продаж»: до этого ячейки рисовались прямо в странице четырьмя копиями.

export const EMPTY = 'var(--border-inner)'

/** Сколько ячеек из `n` занимает значение при шкале `scale`: ненулевое — не меньше одной (видно, что есть). */
export const cellsOf = (v, scale, n) => (v > 0 ? Math.max(1, Math.round(v / scale * n)) : 0)

/** Стек слоёв: [[значение, цвет], …] → ровно `n` цветов ячеек, хвост — пустые. */
export function stack(parts, scale, n) {
  const out = []
  parts.forEach(([v, c]) => { for (let i = cellsOf(v, scale, n); i > 0; i--) out.push(c) })
  const s = out.slice(0, n)
  return [...s, ...Array(Math.max(0, n - s.length)).fill(EMPTY)]
}

/** Горизонтальная полоса из ячеек. */
export function PixelBar({ cells, height = 12, gap = 2, style }) {
  return (
    <div style={{ display: 'flex', gap, height, ...style }}>
      {cells.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}
    </div>
  )
}

/** Вертикальный столбец из ячеек, растёт снизу (`dir="up"`) или сверху (`dir="down"`); высота — родителя. */
export function PixelColumn({ cells, width = '58%', gap = 2, dir = 'up', animate = false, delay = 0 }) {
  return (
    <div style={{ width, height: '100%', margin: '0 auto', display: 'flex', flexDirection: dir === 'up' ? 'column-reverse' : 'column', gap,
      ...(animate ? { animation: 'a2up .55s cubic-bezier(0.22,1,0.36,1) both', animationDelay: `${delay}s`, transformOrigin: dir === 'up' ? 'bottom' : 'top' } : {}) }}>
      {cells.map((c, j) => <div key={j} style={{ flex: 1, borderRadius: 2, background: c }} />)}
    </div>
  )
}
