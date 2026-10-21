/**
 * Список имён в ячейке: первые N чипами, остальные — «+N» с полным списком в подсказке.
 * Часть реестра мастер-сделок (`pages/finance/master-deals.js`), вынесено при аудите 20.10.2026.
 */

export default function Chips({ list, keep, max }) {
  if (!list.length) return <span style={{ color: 'var(--text-disabled)' }}>—</span>
  const chip = { display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 8px', borderRadius: 6, fontSize: 11.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }
  return (
    <span title={list.join(', ')} style={{ display: 'flex', gap: 4, minWidth: 0, overflow: 'hidden' }}>
      {list.slice(0, keep).map(x => <span key={x} style={{ ...chip, background: 'var(--bg-subtle)', color: 'var(--text-primary)', fontWeight: 600, maxWidth: max, flex: '0 1 auto' }}>{x}</span>)}
      {list.length > keep && <span style={{ ...chip, background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontWeight: 700, flex: '0 0 auto' }}>+{list.length - keep}</span>}
    </span>
  )
}
