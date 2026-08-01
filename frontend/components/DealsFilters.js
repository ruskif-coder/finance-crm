import { useState, useEffect } from 'react'
import api, { auth as authH } from '../lib/api'

// Общая панель фильтров сделок — 1 к 1 как в реестре (/sales). Управляет своим состоянием
// и вызывает onChange(params) с готовыми query-параметрами для /sales/deals.
// exclude — ключи фильтров, которые скрыть (напр. 'sales_rep_id' на дашборде, где сейлз задан сверху).

function MultiSelect({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = {
    padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: selected.length ? 'var(--accent-tint)' : 'var(--bg-card)',
    color: selected.length ? 'var(--accent)' : 'inherit', cursor: 'pointer', whiteSpace: 'nowrap',
  }
  const shown = (options || []).filter(o =>
    !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div style={{ position: 'relative' }}>
      <div style={box} onClick={() => setOpen(!open)}>
        {label}{selected.length ? ` · ${selected.length}` : ''} ▾
      </div>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9 }} onClick={() => setOpen(false)} />
          <div style={{
            position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 10,
            background: 'var(--bg-card)', border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-card-sm)', boxShadow: 'var(--shadow-card)',
            minWidth: 250, maxHeight: 320, overflowY: 'auto', padding: 8,
          }}>
            {(options || []).length > 8 && (
              <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
                style={{ width: '100%', padding: '6px 8px', marginBottom: 6, fontSize: 12.5,
                  border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
                  background: 'var(--bg-card)', color: 'inherit' }} />
            )}
            {selected.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', padding: '3px 4px' }}
                onClick={() => onChange([])}>снять все</div>
            )}
            {shown.map(o => (
              <label key={String(o.value)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 4px', fontSize: 12.5, cursor: 'pointer' }}>
                <input type="checkbox" checked={selected.includes(o.value)}
                  onChange={() => onChange(selected.includes(o.value)
                    ? selected.filter(v => v !== o.value)
                    : [...selected, o.value])} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{o.label}</span>
                {o.count !== undefined && <span style={{ color: 'var(--muted)', fontSize: 11 }}>{o.count}</span>}
              </label>
            ))}
            {!shown.length && <div style={{ fontSize: 12, color: 'var(--muted)', padding: 6 }}>ничего не найдено</div>}
          </div>
        </>
      )}
    </div>
  )
}

const GAP_FIELDS = [
  { value: 'advertiser_id', label: 'без рекламодателя' },
  { value: 'brand_id', label: 'без бренда' },
  { value: 'agency_id', label: 'без агентства' },
  { value: 'sales_rep_id', label: 'без продавца' },
  { value: 'account_manager_id', label: 'без аккаунта' },
  { value: 'period_from', label: 'без старта РК' },
  { value: 'period_to', label: 'без конца РК' },
  { value: 'payer', label: 'плательщик не из базы' },
]

const FILTER_FIELDS = [
  { key: 'pipeline', label: 'Воронка' },
  { key: 'product', label: 'Услуга' },
  { key: 'bitrix_stage', label: 'Стадия' },
  { key: 'stage_key', label: 'Слой денег' },
  { key: 'advertiser_id', label: 'Рекламодатель' },
  { key: 'brand_id', label: 'Бренд' },
  { key: 'agency_id', label: 'Агентство' },
  { key: 'sales_rep_id', label: 'Сейлз' },
  { key: 'account_manager_id', label: 'Аккаунт' },
]

const inputStyle = {
  padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
  fontSize: 13, background: 'var(--bg-card)', color: 'inherit',
}

export default function DealsFilters({ onChange, exclude = [], defaultHideArchive = false }) {
  const [f, setF] = useState({ date_from: '', date_to: '', search: '' })
  const [sel, setSel] = useState(Object.fromEntries(FILTER_FIELDS.map(x => [x.key, []])))
  const [gaps, setGaps] = useState([])
  const [hideArchive, setHideArchive] = useState(defaultHideArchive)
  const [options, setOptions] = useState({})

  useEffect(() => { api.get('/sales/filters', authH()).then(r => setOptions(r.data || {})).catch(() => {}) }, [])

  // Debounce: без него onChange дёргался на каждую букву поиска, а родитель
  // (дашборд) бил в /deals+/dashboard на каждый keystroke. 300 мс — как в реестре.
  useEffect(() => {
    const p = {}
    Object.entries(f).forEach(([k, v]) => { if (v) p[k] = v })
    Object.entries(sel).forEach(([k, v]) => { if (v.length) p[k] = v })
    if (gaps.length) p.gaps = gaps
    if (hideArchive) p.hide_archive = true
    const t = setTimeout(() => onChange(p), 300)
    return () => clearTimeout(t)
  }, [f, sel, gaps, hideArchive])

  const fields = FILTER_FIELDS.filter(x => !exclude.includes(x.key))
  const reset = () => {
    setF({ date_from: '', date_to: '', search: '' })
    setSel(Object.fromEntries(FILTER_FIELDS.map(x => [x.key, []])))
    setGaps([]); setHideArchive(false)
  }

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
      <input style={{ ...inputStyle, width: 240 }} placeholder="поиск: название, ID, рекламодатель, бренд"
        value={f.search} onChange={e => setF({ ...f, search: e.target.value })} />
      <input type="month" style={{ ...inputStyle, width: 108 }} value={f.date_from}
        onChange={e => setF({ ...f, date_from: e.target.value })} />
      <span style={{ color: 'var(--muted)' }}>—</span>
      <input type="month" style={{ ...inputStyle, width: 108 }} value={f.date_to}
        onChange={e => setF({ ...f, date_to: e.target.value })} />
      {fields.map(x => (
        <MultiSelect key={x.key} label={x.label} options={options[x.key]}
          selected={sel[x.key]} onChange={v => setSel({ ...sel, [x.key]: v })} />
      ))}
      <MultiSelect label="Незаполненные" options={GAP_FIELDS} selected={gaps} onChange={setGaps} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, cursor: 'pointer', whiteSpace: 'nowrap' }}>
        <input type="checkbox" checked={hideArchive} onChange={e => setHideArchive(e.target.checked)} />
        скрывать архив
      </label>
      <button style={{ padding: '7px 12px', border: '1px solid var(--border-card)', borderRadius: 8, background: 'var(--bg-card)', color: 'inherit', cursor: 'pointer', fontSize: 13 }}
        onClick={reset}>Сбросить</button>
    </div>
  )
}
