import { useState, useEffect } from 'react'
import api, { auth } from '../lib/api'
import useIsMobile from './mobile/useIsMobile'

const VAT = 1.22
const MONO = "'JetBrains Mono', ui-monospace, monospace"
const UI = "'Manrope', system-ui, sans-serif"

const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 5, display: 'block' }
const INP = { width: '100%', boxSizing: 'border-box', padding: '9px 11px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', fontFamily: UI }

// Выпадашка с поиском (v2). disabled — заблокированный вид (бренд до рекламодателя).
function Search({ placeholder, options, value, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const opts = options || []
  const sel = opts.find(o => String(o.value) === String(value))
  const shown = opts.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase())).slice(0, 80)
  const box = { ...INP, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6, cursor: disabled ? 'default' : 'pointer', whiteSpace: 'nowrap', overflow: 'hidden',
    background: disabled ? 'var(--bg-subtle)' : 'var(--bg-card)', borderColor: disabled ? 'var(--border-inner)' : 'var(--border-card)',
    color: sel ? 'var(--text-primary)' : 'var(--text-faint)', fontWeight: sel ? 600 : 400 }
  return (
    <div style={{ position: 'relative' }}>
      <button type="button" disabled={disabled} style={box} onClick={() => !disabled && setOpen(!open)}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{sel ? sel.label : placeholder}</span>
        <span style={{ color: 'var(--text-faint)', flexShrink: 0 }}>▾</span>
      </button>
      {open && (<>
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }} onClick={() => setOpen(false)} />
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, minWidth: 220, zIndex: 61, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, marginTop: 4, maxHeight: 260, overflowY: 'auto', padding: 6, boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)' }}>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск" style={{ ...INP, padding: '6px 8px', marginBottom: 6 }} />
          <div style={{ padding: '5px 8px', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13 }} onClick={() => { onChange(''); setOpen(false) }}>— не выбрано —</div>
          {shown.map(o => <div key={o.value} style={{ padding: '6px 8px', cursor: 'pointer', fontSize: 13, borderRadius: 6, fontWeight: String(o.value) === String(value) ? 600 : 400, color: String(o.value) === String(value) ? 'var(--accent)' : 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            onClick={() => { onChange(String(o.value)); setOpen(false); setQ('') }}>{o.label}{o.count !== undefined ? <span style={{ color: 'var(--text-muted)' }}> · {o.count}</span> : null}</div>)}
          {!shown.length && <div style={{ padding: 6, color: 'var(--text-muted)', fontSize: 13 }}>ничего не найдено</div>}
        </div>
      </>)}
    </div>
  )
}

// Сумма с разбивкой разрядов: в фокусе — сырое, вне — «1 500 000». Моноширинный.
function AmountInput({ value, onChange }) {
  const [focused, setFocused] = useState(false)
  const group = (v) => {
    if (v === '' || v == null) return ''
    const s = String(v).replace(/\s/g, ''); const [i, d] = s.split('.')
    const gi = (i || '').replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
    return d !== undefined ? `${gi}.${d}` : gi
  }
  return (
    <input style={{ ...INP, fontFamily: MONO }} inputMode="decimal" placeholder="0 ₽"
      value={focused ? (value ?? '') : group(value)}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      onChange={e => onChange(e.target.value.replace(/\s/g, '').replace(',', '.'))} />
  )
}

const IcoBtn = ({ title, onClick, active, children }) => (
  <button type="button" title={title} onClick={onClick}
    style={{ width: 38, height: 38, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${active ? 'var(--accent)' : 'var(--border-card)'}`, background: active ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, color: active ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer' }}>
    {children}
  </button>
)

export default function DealCreateForm({ open, onClose, canPickRep, onCreated }) {
  const [opts, setOpts] = useState({})
  const [services, setServices] = useState([])
  const [pipelines, setPipelines] = useState([])
  const [stages, setStages] = useState([])
  const [brands, setBrands] = useState([])
  const [f, setF] = useState({ agency_id: '', advertiser_id: '', brand_id: '', product: '', pipeline: '', bitrix_stage: '', period: '', amount: '', amount_with_vat: '', sales_rep_id: '', account_manager_id: '', title: '' })
  const [brief, setBrief] = useState('')
  const [briefOpen, setBriefOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const isMobile = useIsMobile()
  const set = (k, v) => setF(p => ({ ...p, [k]: v }))

  useEffect(() => {
    if (!open) return
    api.get('/sales/filters', auth()).then(r => setOpts(r.data || {})).catch(() => {})
    api.get('/sales/directories/services?only_active=true', auth()).then(r => setServices(r.data.items || [])).catch(() => {})
    api.get('/sales/directories/pipelines', auth()).then(r => {
      const items = r.data.items || []; setPipelines(items)
      const gen = items.find(p => p.name === 'Общая') || items[0]
      if (gen) set('pipeline', String(gen.id))
    }).catch(() => {})
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey); return () => document.removeEventListener('keydown', onKey)
  }, [open])

  useEffect(() => {
    if (!f.pipeline) { setStages([]); return }
    api.get(`/sales/directories/pipelines/${f.pipeline}/stages`, auth())
      .then(r => { const it = r.data.items || []; setStages(it); if (it[0]) set('bitrix_stage', it[0].name) })
      .catch(() => setStages([]))
  }, [f.pipeline])

  useEffect(() => {
    if (!f.advertiser_id) { setBrands([]); return }
    api.get('/sales/brands-by-advertiser', auth())
      .then(r => setBrands(r.data[String(f.advertiser_id)] || r.data[f.advertiser_id] || []))
      .catch(() => setBrands([]))
  }, [f.advertiser_id])

  const onAmount = (withVat, v) => {
    const n = parseFloat(String(v).replace(',', '.'))
    if (withVat) setF(p => ({ ...p, amount_with_vat: v, amount: isNaN(n) ? '' : (n / VAT).toFixed(2) }))
    else setF(p => ({ ...p, amount: v, amount_with_vat: isNaN(n) ? '' : (n * VAT).toFixed(2) }))
  }

  const genTitle = () => {
    const short = o => (o ? String(o.label).split(' | ')[0].trim() : '')
    const adv = (opts.advertiser_id || []).find(o => String(o.value) === String(f.advertiser_id))
    const ag = (opts.agency_id || []).find(o => String(o.value) === String(f.agency_id))
    const br = brands.find(o => String(o.value) === String(f.brand_id))
    set('title', [short(adv), short(br), short(ag), f.product, f.period].filter(x => x && String(x).trim()).join(' | '))
  }

  const pipeName = (pipelines.find(p => String(p.id) === String(f.pipeline)) || {}).name || ''

  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.post('/sales/deals', {
        agency_id: f.agency_id ? +f.agency_id : null, advertiser_id: f.advertiser_id ? +f.advertiser_id : null,
        brand_id: f.brand_id ? +f.brand_id : null, product: f.product || null,
        pipeline: pipeName, bitrix_stage: f.bitrix_stage, period: f.period,
        amount: f.amount ? parseFloat(f.amount) : null, amount_with_vat: f.amount_with_vat ? parseFloat(f.amount_with_vat) : null,
        sales_rep_id: (canPickRep && f.sales_rep_id) ? +f.sales_rep_id : null,
        account_manager_id: f.account_manager_id ? +f.account_manager_id : null, title: f.title || null,
      }, auth())
      if (brief.trim() && r.data?.id) { try { await api.put(`/sales/deals/${r.data.id}/brief`, { brief }, auth()) } catch (e) {} }
      setF({ agency_id: '', advertiser_id: '', brand_id: '', product: '', pipeline: f.pipeline, bitrix_stage: f.bitrix_stage, period: '', amount: '', amount_with_vat: '', sales_rep_id: '', account_manager_id: '', title: '' })
      setBrief(''); setBriefOpen(false)
      onCreated && onCreated(); onClose()
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось создать сделку') }
    finally { setBusy(false) }
  }

  if (!open) return null
  // обязательны: агентство, рекламодатель, услуга, период, сумма
  const canSubmit = f.agency_id && f.advertiser_id && f.product && f.period && (f.amount || f.amount_with_vat)
  const st = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

  // Поля формы (общие для десктопа и мобилы); на мобиле — одна колонка
  const fields = (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(5,1fr)', gap: 14 }}>
        <div><span style={LBL}>Агентство</span><Search placeholder="не выбрано" options={opts.agency_id} value={f.agency_id} onChange={v => set('agency_id', v)} /></div>
        <div><span style={LBL}>Рекламодатель</span><Search placeholder="не выбран" options={opts.advertiser_id} value={f.advertiser_id} onChange={v => { set('advertiser_id', v); set('brand_id', '') }} /></div>
        <div><span style={LBL}>Бренд</span><Search placeholder={f.advertiser_id ? 'не выбран' : 'сначала рекламодатель'} options={brands} value={f.brand_id} onChange={v => set('brand_id', v)} disabled={!f.advertiser_id} /></div>
        <div><span style={LBL}>Услуга</span><Search placeholder="не выбрана" options={services.map(s => ({ value: s.name, label: s.name }))} value={f.product} onChange={v => set('product', v)} /></div>
        <div><span style={LBL}>Планируется в период</span><input type="month" style={{ ...INP, fontFamily: MONO }} value={f.period} onChange={e => set('period', e.target.value)} /></div>

        <div><span style={LBL}>Воронка</span><select style={INP} value={f.pipeline} onChange={e => set('pipeline', e.target.value)}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div><span style={LBL}>Стадия</span><select style={INP} value={f.bitrix_stage} onChange={e => set('bitrix_stage', e.target.value)}>{stages.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}</select></div>
        <div><span style={LBL}>Сумма с НДС</span><AmountInput value={f.amount_with_vat} onChange={v => onAmount(true, v)} /></div>
        <div><span style={LBL}>Без НДС · клиентская ⇄</span><AmountInput value={f.amount} onChange={v => onAmount(false, v)} /></div>
        <div><span style={LBL}>Продавец</span>
          {canPickRep
            ? <Search placeholder="не выбран" options={opts.sales_rep_id} value={f.sales_rep_id} onChange={v => set('sales_rep_id', v)} />
            : <div style={{ ...INP, background: 'var(--bg-subtle)', color: 'var(--text-muted)' }}>вы (текущий)</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 3fr 42px 42px', gap: 14, alignItems: 'end' }}>
        <div><span style={LBL}>Аккаунт</span><Search placeholder="не выбран" options={opts.account_manager_id} value={f.account_manager_id} onChange={v => set('account_manager_id', v)} /></div>
        {isMobile ? (
          <div>
            <span style={LBL}>Название сделки</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <input style={{ ...INP, flex: 1, minWidth: 0 }} placeholder="Рекл. | Бренд | Агентство | Услуга | Период" value={f.title} onChange={e => set('title', e.target.value)} />
              <IcoBtn title="Сгенерировать название" onClick={genTitle}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={st}><path d="M5 3v4" /><path d="M3 5h4" /><path d="M17 15v4" /><path d="M15 17h4" /><path d="M12.5 4.5l1.9 4.6 4.6 1.9-4.6 1.9-1.9 4.6-1.9-4.6L6 11l4.6-1.9z" /></svg>
              </IcoBtn>
              <IcoBtn title={brief.trim() ? 'Бриф добавлен' : 'Добавить бриф'} active={!!brief.trim() || briefOpen} onClick={() => setBriefOpen(o => !o)}>
                <svg width="16" height="16" viewBox="0 0 24 24" style={st}><path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M9 12h6" /><path d="M9 16h4" /></svg>
              </IcoBtn>
            </div>
          </div>
        ) : (<>
          <div><span style={LBL}>Название сделки</span><input style={INP} placeholder="Рекламодатель | Бренд | Агентство | Услуга | Период" value={f.title} onChange={e => set('title', e.target.value)} /></div>
          <IcoBtn title="Сгенерировать название" onClick={genTitle}>
            <svg width="16" height="16" viewBox="0 0 24 24" style={st}><path d="M5 3v4" /><path d="M3 5h4" /><path d="M17 15v4" /><path d="M15 17h4" /><path d="M12.5 4.5l1.9 4.6 4.6 1.9-4.6 1.9-1.9 4.6-1.9-4.6L6 11l4.6-1.9z" /></svg>
          </IcoBtn>
          <IcoBtn title={brief.trim() ? 'Бриф добавлен' : 'Добавить бриф'} active={!!brief.trim() || briefOpen} onClick={() => setBriefOpen(o => !o)}>
            <svg width="16" height="16" viewBox="0 0 24 24" style={st}><path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M9 12h6" /><path d="M9 16h4" /></svg>
          </IcoBtn>
        </>)}
      </div>

      {briefOpen && (
        <div>
          <span style={LBL}>Бриф (сохранится вместе со сделкой)</span>
          <textarea value={brief} onChange={e => setBrief(e.target.value)} placeholder="Задачи, ЦА, гео, форматы, KPI, бюджет…"
            style={{ ...INP, minHeight: 120, resize: 'vertical', lineHeight: 1.5 }} />
        </div>
      )}
    </>
  )

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: isMobile ? '14px 16px' : '18px 24px', borderBottom: '1px solid var(--border-inner)', position: isMobile ? 'sticky' : 'static', top: 0, background: 'var(--bg-card)', zIndex: 3 }}>
      <span style={{ width: 30, height: 30, borderRadius: 9, background: 'var(--accent-tint)', color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700 }}>+</span>
      <span style={{ flex: 1, fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>Новая сделка</span>
      <button onClick={onClose} title="Закрыть" style={{ width: 32, height: 32, borderRadius: 9, border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>✕</button>
    </div>
  )

  // ── Мобиль: полноэкранная форма (как форма редактирования) ──
  if (isMobile) {
    return (
      <div style={{ position: 'fixed', inset: 0, zIndex: 500, background: 'var(--bg-canvas)', overflowY: 'auto', fontFamily: UI, paddingBottom: 84 }}>
        {header}
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>{fields}</div>
        <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 14px', background: 'var(--bg-card)', borderTop: '1px solid var(--border-inner)', display: 'flex', gap: 8 }}>
          <button onClick={onClose} disabled={busy} style={{ flex: '0 0 auto', padding: '14px 20px', borderRadius: 12, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>Отмена</button>
          <button onClick={submit} disabled={busy || !canSubmit} style={{ flex: 1, background: canSubmit ? 'var(--accent)' : 'var(--bg-subtle)', color: canSubmit ? '#fff' : 'var(--text-faint)', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: canSubmit ? 'pointer' : 'default' }}>{busy ? 'Создание…' : 'Создать сделку'}</button>
        </div>
      </div>
    )
  }

  // ── Десктоп: центрированная модалка ──
  return (
    <div onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 55, background: 'rgba(28,36,51,.32)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40, overflow: 'auto', fontFamily: UI }}>
      <div style={{ width: 1080, maxWidth: '100%', margin: 'auto', background: 'var(--bg-card)', borderRadius: 18, overflow: 'hidden', boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 24px 64px rgba(28,36,51,.22)', animation: 'riseIn .28s cubic-bezier(0.22,1,0.36,1) both' }}>
        <style>{`@keyframes riseIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}`}</style>
        {header}
        <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>{fields}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px', borderTop: '1px solid var(--border-inner)', background: 'var(--bg-subtle)' }}>
          <button onClick={submit} disabled={busy || !canSubmit}
            style={{ padding: '9px 20px', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 700, fontFamily: MONO,
              background: canSubmit ? 'var(--accent)' : 'var(--accent-tint)', color: canSubmit ? '#fff' : '#A9B6F2', cursor: canSubmit ? 'pointer' : 'not-allowed' }}>
            {busy ? 'Создание…' : 'Создать сделку'}</button>
          <button onClick={onClose} style={{ padding: '9px 16px', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-primary)', borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>Отмена</button>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>суммы пересчитываются в обе стороны по НДС 22% · обязательны: агентство, рекламодатель, услуга, период, сумма</span>
        </div>
      </div>
    </div>
  )
}
