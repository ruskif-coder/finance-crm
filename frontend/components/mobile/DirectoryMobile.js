import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'

// Общий мобильный шелл справочников (§2 хендоффа «Справочник контрагентов»):
// тулбар с раскрывающимся поиском · строка фильтр-чипов + синяя «+» ·
// карточки с одиночным раскрытием (riseIn) · подвал «Показать ещё».
// Контент карточки задаёт страница через renderCard(row, expanded, toggle).
const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

export default function DirectoryMobile({
  title, total, shownCount, loading, canEdit,
  search, setSearch, searchPlaceholder = 'поиск…',
  filterChips, onAdd,
  rows, renderCard, keyOf = (r) => r.id,
  hasMore, onMore, moreLabel = 'Показать ещё',
  emptyText = 'Ничего не найдено',
}) {
  const [expandedId, setExpandedId] = useState(null)
  const [searchOpen, setSearchOpen] = useState(false)

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, paddingBottom: 90 }}>
      <style>{`@keyframes riseIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@media (prefers-reduced-motion:reduce){[style*="animation"]{animation:none!important}}`}</style>

      {/* тулбар */}
      {searchOpen ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--accent)', background: 'var(--bg-card)', borderRadius: 12, padding: '10px 12px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" style={{ ...stroke, color: 'var(--text-faint)' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
            <input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder={searchPlaceholder} style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, color: 'var(--text-secondary)', fontFamily: UI }} />
            {search && <span onClick={() => setSearch('')} style={{ color: 'var(--text-faint)', cursor: 'pointer', fontSize: 16 }}>✕</span>}
          </div>
          <button onClick={() => setSearchOpen(false)} style={{ border: 'none', background: 'transparent', color: 'var(--accent)', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Готово</button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 19, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{new Intl.NumberFormat('ru-RU').format(shownCount)} из {new Intl.NumberFormat('ru-RU').format(total)}</span>
          <button onClick={() => setSearchOpen(true)} aria-label="Поиск" style={{ marginLeft: 'auto', width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${search ? 'var(--accent)' : 'var(--border-card)'}`, background: search ? 'var(--accent-tint)' : 'var(--bg-card)', color: search ? 'var(--accent)' : 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
          </button>
        </div>
      )}

      {/* строка фильтр-чипов + «+» */}
      {(filterChips || (canEdit && onAdd)) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', overflowX: 'auto' }}>
          {filterChips}
          {canEdit && onAdd && (
            <button onClick={onAdd} aria-label="Добавить" style={{ marginLeft: 'auto', flex: '0 0 auto', width: 38, height: 38, borderRadius: 10, background: 'var(--accent)', color: '#fff', border: 'none', fontSize: 22, lineHeight: 1, cursor: 'pointer' }}>+</button>
          )}
        </div>
      )}

      {/* список карточек */}
      {loading && !rows.length ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
        : !rows.length ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>{emptyText}</div>
          : rows.map((r, i) => {
            const id = keyOf(r)
            return (
              <div key={id} style={{ animation: `riseIn .4s ease both`, animationDelay: `${Math.min(i, 6) * 0.07}s` }}>
                {renderCard(r, expandedId === id, () => setExpandedId(x => x === id ? null : id))}
              </div>
            )
          })}

      {/* показать ещё */}
      {hasMore && (
        <button onClick={onMore} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '13px', fontSize: 13, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer', fontFamily: UI }}>{moreLabel}</button>
      )}
    </div>
  )
}

// Чип-фильтр (белый, рамка, каретка ▾) для строки фильтров мобильного справочника.
export function FilterChip({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{ flex: '0 0 auto', height: 38, border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '0 12px', fontSize: 13, fontWeight: 600, color: active ? 'var(--accent)' : 'var(--text-primary)', cursor: 'pointer', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {label}<span style={{ color: 'var(--text-faint)' }}>▾</span>
    </button>
  )
}
