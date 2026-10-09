import { useState } from 'react'
import { Modal, inp, sel, btn, primaryBtn, PickValue } from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import { todayMsk } from '@/lib/dates'

// Форма одного замера: метрика, значение, источник (накопительный список — ValuePopover),
// дата замера, поверхность, сегмент (для долей), заметка. Источник обязателен.
const row = { display: 'grid', gridTemplateColumns: '140px 1fr', gap: 10, alignItems: 'center', fontSize: 13 }
const lab = { color: 'var(--text-secondary)', fontWeight: 600 }

export default function AudienceMeasureModal({ publisher, metrics, sources, onSave, onClose }) {
  const [f, setF] = useState({ metric: 'mau', value: '', source: sources[0] || 'медиакит', measured_at: todayMsk(),
    surface_kind: '', segment: '', note: '' })
  const [vpop, setVpop] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF(s => ({ ...s, [k]: e?.target ? e.target.value : e }))
  const isShare = f.metric === 'share'

  const save = async () => {
    const v = Number(String(f.value).replace(/\s/g, '').replace(',', '.'))
    if (!Number.isFinite(v) || v < 0) { setErr('Значение — неотрицательное число'); return }
    if (!f.source.trim()) { setErr('Источник обязателен'); return }
    if (isShare && !f.segment.trim()) { setErr('Для доли нужен сегмент: «Ж 25–54», «Москва»'); return }
    setBusy(true); setErr('')
    try {
      await onSave({ ...f, value: v, surface_kind: f.surface_kind || null, segment: f.segment || null, note: f.note || null })
    } catch (e) { setErr(e?.response?.data?.detail || 'Не сохранилось') } finally { setBusy(false) }
  }

  return (
    <Modal title={`Замер аудитории · ${publisher.name}`} width={560} onClose={onClose}
      footer={<>
        <span style={{ color: 'var(--danger-fg)', fontSize: 12, marginRight: 'auto' }}>{err}</span>
        <button style={btn(false)} onClick={onClose}>Отмена</button>
        <button style={primaryBtn} disabled={busy} onClick={save}>Сохранить</button>
      </>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
        <div style={row}><span style={lab}>Метрика</span>
          <select style={sel} value={f.metric} onChange={set('metric')}>
            {Object.entries(metrics).map(([k, m]) => <option key={k} value={k}>{m.label} ({m.unit})</option>)}
          </select></div>
        <div style={row}><span style={lab}>Значение</span>
          <input style={inp} value={f.value} onChange={set('value')} placeholder={isShare ? 'в процентах, напр. 71' : 'напр. 5200000'} inputMode="decimal" /></div>
        {isShare && <div style={row}><span style={lab}>Сегмент</span>
          <input style={inp} value={f.segment} onChange={set('segment')} placeholder="Ж 25–54 · Москва · доход B+" /></div>}
        <div style={row}><span style={lab}>Источник</span>
          <span data-pop-root><PickValue value={f.source} placeholder="выбрать" onOpen={e => setVpop(e.currentTarget.getBoundingClientRect())} /></span></div>
        <div style={row}><span style={lab}>Дата замера</span>
          <input style={inp} type="date" value={f.measured_at} max={todayMsk()} onChange={set('measured_at')} /></div>
        <div style={row}><span style={lab}>Поверхность</span>
          <select style={sel} value={f.surface_kind} onChange={set('surface_kind')}>
            <option value="">площадка целиком</option><option value="web">web</option><option value="app">app</option>
          </select></div>
        <div style={row}><span style={lab}>Заметка</span>
          <input style={inp} value={f.note} onChange={set('note')} placeholder="страница медиакита, оговорки" /></div>
      </div>
      {vpop && <ValuePopover anchor={vpop} title="Источник" value={f.source}
        options={sources.map(s => ({ value: s, label: s }))}
        onPick={v => { if (v) setF(s => ({ ...s, source: v })); setVpop(null) }}
        onAddNew={v => { setF(s => ({ ...s, source: v })); setVpop(null) }}
        onClose={() => setVpop(null)} />}
    </Modal>
  )
}
