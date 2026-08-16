import { MONO, UI, MultiDrop, FILTER_DROPS, GAP_FIELDS } from '../salesTableKit'
import BottomSheet from '../mobile/BottomSheet'

// Общие мобильные контролы реестра сделок (эталон-тулбар + шторка фильтров).
// Используются и на /sales/deals, и на /sales/dashboard — единственный источник правды,
// чтобы правки не приходилось дублировать в обеих страницах.
const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
const plur = (n) => { const a = Math.abs(n) % 100, b = a % 10; if (a > 10 && a < 20) return 'сделок'; if (b === 1) return 'сделку'; if (b > 1 && b < 5) return 'сделки'; return 'сделок' }

export default function DealsMobileControls({
  dealsTotal, search, setSearch, mobSearchOpen, setMobSearchOpen,
  mobView, setMobView, filtersOpen, setFiltersOpen, activeFilterCount,
  sel, setSel, gaps, setGaps, dateFrom, setDateFrom, dateTo, setDateTo,
  hideArchive, setHideArchive, fopts, productOpts, resetFilters, exportCsv,
  filterDrops = FILTER_DROPS,   // реестр /sales передаёт свой список (+ Продавец); дашборд — дефолт
}) {
  return (
    <>
      {/* тулбар: Сделки N · поиск(раскрытие) · карточки/таблица · Фильтры */}
      {mobSearchOpen ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--accent)', background: 'var(--bg-card)', borderRadius: 12, padding: '10px 12px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" style={{ ...stroke, color: 'var(--text-faint)', flexShrink: 0 }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
            <input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder="ID, агентство, рекл, бренд"
              style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, color: 'var(--text-secondary)', fontFamily: UI }} />
            {search && <span onClick={() => setSearch('')} style={{ color: 'var(--text-faint)', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>✕</span>}
          </div>
          <button onClick={() => setMobSearchOpen(false)} style={{ flexShrink: 0, border: 'none', background: 'transparent', color: 'var(--accent)', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>Готово</button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Сделки</span>
          <span style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>{dealsTotal}</span>
          <div style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => setMobSearchOpen(true)} aria-label="Поиск" style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${search ? 'var(--accent)' : 'var(--border-card)'}`, background: search ? 'var(--accent-tint)' : 'var(--bg-card)', color: search ? 'var(--accent)' : 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
            </button>
            <div style={{ display: 'inline-flex', border: '1px solid var(--border-card)', borderRadius: 10, overflow: 'hidden' }}>
              <button onClick={() => setMobView('cards')} aria-label="Карточки" style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: 'none', background: mobView === 'cards' ? 'var(--accent-tint)' : 'var(--bg-card)', color: mobView === 'cards' ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><rect x="4" y="4" width="16" height="7" rx="1.5" /><rect x="4" y="14" width="16" height="6" rx="1.5" /></svg>
              </button>
              <button onClick={() => setMobView('table')} aria-label="Таблица" style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: 'none', borderLeft: '1px solid var(--border-card)', background: mobView === 'table' ? 'var(--accent-tint)' : 'var(--bg-card)', color: mobView === 'table' ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={stroke}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
              </button>
            </div>
            <button onClick={() => setFiltersOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${activeFilterCount > 0 ? 'var(--accent)' : 'var(--border-card)'}`, background: 'var(--bg-card)', borderRadius: 10, padding: '0 13px', height: 40, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" style={stroke}><path d="M3 5h18M6 12h12M10 19h4" /></svg>
              Фильтры{activeFilterCount > 0 && <span style={{ background: 'var(--accent-tint)', color: 'var(--accent)', borderRadius: 8, padding: '0 6px', fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{activeFilterCount}</span>}
            </button>
          </div>
        </div>
      )}

      {/* шторка фильтров */}
      <BottomSheet open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Фильтры"
        footer={<div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setFiltersOpen(false)} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>Показать {dealsTotal} {plur(dealsTotal)}</button>
          <button onClick={exportCsv} aria-label="Скачать CSV" style={{ flexShrink: 0, width: 52, borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" style={stroke}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
          </button>
        </div>}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{activeFilterCount > 0 ? `выбрано ${activeFilterCount}` : 'фильтры не заданы'}</span>
          <span onClick={resetFilters} style={{ fontSize: 13, fontWeight: 600, color: activeFilterCount > 0 ? 'var(--accent)' : 'var(--text-faint)', cursor: 'pointer' }}>Сбросить</span>
        </div>
        <div style={{ display: 'inline-flex', width: '100%', boxSizing: 'border-box', alignItems: 'center', gap: 8, border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', marginBottom: 10 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" style={{ ...stroke, color: 'var(--text-faint)', flexShrink: 0 }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="ID, агентство, рекл, бренд…" style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, color: 'var(--text-secondary)', fontFamily: UI }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', fontSize: 13, fontFamily: MONO, outline: 'none' }} />
          <span style={{ color: 'var(--text-faint)' }}>—</span>
          <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, padding: '11px 12px', fontSize: 13, fontFamily: MONO, outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filterDrops.map(([k, lbl]) => (
            <MultiDrop key={k} label={lbl} options={k === 'product' ? (productOpts || fopts[k]) : fopts[k]} selected={sel[k]} onChange={v => { setSel(s => ({ ...s, [k]: v })); if (k === 'bitrix_stage' && hideArchive && v.some(x => /архив/i.test(x))) setHideArchive(false) }} block />
          ))}
          <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={gaps} onChange={setGaps} block />
        </div>
        <div onClick={() => setHideArchive(v => !v)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, padding: '12px 14px', border: '1px solid var(--border-card)', borderRadius: 12, cursor: 'pointer' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Показывать архивные</span>
          <span style={{ width: 42, height: 24, borderRadius: 999, background: !hideArchive ? 'var(--accent)' : 'var(--border-inner)', position: 'relative', transition: 'background .18s', flexShrink: 0 }}>
            <span style={{ position: 'absolute', top: 2, left: !hideArchive ? 20 : 2, width: 20, height: 20, borderRadius: '50%', background: '#fff', transition: 'left .18s', boxShadow: '0 1px 3px rgba(0,0,0,.25)' }} />
          </span>
        </div>
      </BottomSheet>
    </>
  )
}
