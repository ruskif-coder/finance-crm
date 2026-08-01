import { useState, useEffect, useRef } from 'react'

// Общий набор для v2-таблиц реестра (/sales) и дашборда (/sales-dashboard):
// шрифты, цвета слоёв, конфиг фильтров, компактный мультиселект и иконка-кнопка.
// Раньше эти определения были продублированы байт-в-байт в обеих страницах.

export const MONO = "'JetBrains Mono', ui-monospace, monospace"
export const UI = "'Manrope', system-ui, sans-serif"

// цвета слоя денег: 1-2 серый, 3-4 жёлтый, 5-6 зелёный; none — штриховка
export const PIP = ['var(--text-faint)', 'var(--text-faint)', 'var(--dot-current-dz)', 'var(--dot-current-dz)', 'var(--income)', 'var(--income)']
export const FILL = { 'планируемые': 2, 'реализуемые': 4, 'фактические': 6 }
export const HATCH = 'repeating-linear-gradient(135deg,#C3C9D8 0 3px,#FFFFFF 3px 6px)'

export const FILTER_DROPS = [
  ['pipeline', 'Воронка'], ['product', 'Услуга'], ['bitrix_stage', 'Стадия'], ['stage_key', 'Слой денег'],
  ['advertiser_id', 'Рекламодатель'], ['brand_id', 'Бренд'], ['agency_id', 'Агентство'], ['account_manager_id', 'Аккаунт'],
]
export const GAP_FIELDS = [
  { value: 'advertiser_id', label: 'без рекламодателя' }, { value: 'brand_id', label: 'без бренда' },
  { value: 'agency_id', label: 'без агентства' }, { value: 'account_manager_id', label: 'без аккаунта' },
  { value: 'period_from', label: 'без старта РК' }, { value: 'payer', label: 'плательщик не из базы' },
]

export const shortLabel = (lab) => (lab ? String(lab).split(' | ')[0].trim() : null)

// компактный мультиселект-дропдаун фильтра
export function MultiDrop({ label, options, selected, onChange }) {
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
  const box = { flex: '0 1 auto', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600, color: active ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', cursor: 'pointer' }
  return (
    <div ref={ref} style={{ position: 'relative', flex: '0 1 auto' }}>
      <div style={box} onClick={() => setOpen(o => !o)}>{label}{active ? ` · ${selected.length}` : ''} ▾</div>
      {open && (
        <div style={{ position: 'absolute', top: '110%', left: 0, marginTop: 4, zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', minWidth: 220, maxHeight: 320, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {opts.length > 8 && <div style={{ padding: 8 }}>
            <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
              style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} />
          </div>}
          <div style={{ overflowY: 'auto', padding: 5 }}>
            {active && <div onClick={() => onChange([])} style={{ fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer', padding: '4px 6px' }}>снять все</div>}
            {shown.map(o => {
              const on = selected.includes(o.value)
              return (
                <label key={String(o.value)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 6px', fontSize: 12.5, cursor: 'pointer', borderRadius: 7, background: on ? 'var(--accent-tint)' : 'transparent' }}>
                  <input type="checkbox" checked={on} onChange={() => onChange(on ? selected.filter(v => v !== o.value) : [...selected, o.value])} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                  {o.count !== undefined && <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>{o.count}</span>}
                </label>
              )
            })}
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
