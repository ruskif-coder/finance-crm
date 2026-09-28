// Тулбар очереди — фильтры внутри карточки таблицы (шаблон реестра): поиск, диапазон
// периода РК, пины справочников, «Незаполненные», сброс. Значения и опции живут на
// странице: по отфильтрованным строкам считаются и лестница, и счётчики пинов.
import { useEffect, useState } from 'react'
import { MONO, inp, MultiDrop, GAP_FIELDS, IconBtn, PortalPopover } from '@/components/salesTableKit'
import { dm } from '@/lib/salesFormat'

// Пины-фильтры. Одно описание задаёт и подпись, и способ достать значение из строки:
// без этого список пинов и код фильтрации разъезжаются на первой правке. Значение — id,
// где он есть: имена рекламодателей и брендов меняются, id нет.
export const PINS = [
  { key: 'pipeline', label: 'Воронка', val: r => r.pipeline, text: r => r.pipeline },
  { key: 'product', label: 'Услуга', val: r => r.product, text: r => r.product },
  { key: 'stage', label: 'Стадия', val: r => r.our_stage?.id, text: r => r.our_stage?.name },
  { key: 'layer', label: 'Слой денег', val: r => r.our_stage?.money_layer, text: r => r.our_stage?.money_layer },
  { key: 'advertiser', label: 'Рекламодатель', val: r => r.advertiser_id, text: r => r.advertiser },
  { key: 'brand', label: 'Бренд', val: r => r.brand_id, text: r => r.brand },
  { key: 'agency', label: 'Агентство', val: r => r.agency_id, text: r => r.agency },
  { key: 'account', label: 'Аккаунт', val: r => r.account_manager_id, text: r => r.account_manager },
]

export const emptyPins = () => Object.fromEntries(PINS.map(p => [p.key, []]))

/** Фильтр строк тулбаром. Диапазон — по ПЕРЕСЕЧЕНИЮ с периодом РК, а не по старту:
 *  сделка июнь–июль в июльском диапазоне обязана быть. «Незаполненные» — ИЛИ по дырам. */
export function applyToolbar(rows, { qtext, range, pins, gaps }) {
  const q = qtext.trim().toLowerCase()
  return rows.filter(r => {
    if (q && !`${r.code || ''} ${r.advertiser || ''} ${r.brand || ''} ${r.title || ''}`.toLowerCase().includes(q)) return false
    if (range.from && (r.period_to || r.period_from || '9999') < range.from) return false
    if (range.to && (r.period_from || r.period_to || '0000') > range.to) return false
    for (const p of PINS) {
      const selv = pins[p.key]
      if (selv.length && !selv.includes(p.val(r))) return false
    }
    if (gaps.length && !gaps.some(f => f === 'payer' ? !r.payer_counterparty_id : !r[f])) return false
    return true
  })
}

/** Опции пинов — по ПОЛНОМУ набору строк: иначе снятое значение нельзя было бы вернуть. */
export function pinOptions(rows) {
  const out = {}
  PINS.forEach(p => {
    const m = new Map()
    rows.forEach(r => {
      const v = p.val(r)
      if (v == null || v === '') return
      const cur = m.get(v) || { value: v, label: p.text(r) || String(v), count: 0 }
      cur.count += 1
      m.set(v, cur)
    })
    out[p.key] = [...m.values()].sort((a, b) => b.count - a.count)
  })
  return out
}

export default function QueueToolbar({ f, setF, options, filtersOn, onReset }) {
  const [rangeOpen, setRangeOpen] = useState(false)
  // Диапазон закрывается по клику мимо: PortalPopover рисует панель, а жизненный цикл —
  // за вызывающим (клики внутри портала он гасит сам).
  useEffect(() => {
    if (!rangeOpen) return
    const off = (e) => { if (!e.target.closest('[data-range-root]')) setRangeOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [rangeOpen])
  const set = (k) => (v) => setF(s => ({ ...s, [k]: v }))
  const rangeOn = !!(f.range.from || f.range.to)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <span style={{ position: 'relative', flex: '0 0 170px' }}>
        <input value={f.qtext} onChange={e => set('qtext')(e.target.value)} placeholder="Код, бренд"
          style={{ ...inp, width: '100%', padding: '7px 10px 7px 28px', fontSize: 12 }} />
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="2"
          style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }}>
          <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
        </svg>
      </span>
      {/* Диапазон периода РК. Своя выпадашка, а не PeriodSelect: тот выбирает один месяц
          или квартал, а здесь нужны две границы. */}
      <span data-range-root style={{ position: 'relative' }}>
        <span onClick={() => setRangeOpen(o => !o)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${rangeOn ? 'var(--accent)' : 'var(--border-card)'}`,
            background: rangeOn ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600,
            color: rangeOn ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: MONO }}>
          {rangeOn ? `${dm(f.range.from)} — ${dm(f.range.to)}` : 'Период РК'} ▾
        </span>
        <PortalPopover open={rangeOpen} minWidth={300} style={{ padding: 12, gap: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Пересечение с периодом размещения</span>
          <span style={{ display: 'flex', gap: 8 }}>
            <input type="date" value={f.range.from} onChange={e => set('range')({ ...f.range, from: e.target.value })} style={{ ...inp, fontFamily: MONO, fontSize: 12 }} />
            <input type="date" value={f.range.to} onChange={e => set('range')({ ...f.range, to: e.target.value })} style={{ ...inp, fontFamily: MONO, fontSize: 12 }} />
          </span>
          <span style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span onClick={() => set('range')({ from: '', to: '' })} style={{ fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer' }}>сбросить</span>
            <span onClick={() => setRangeOpen(false)} style={{ fontSize: 11.5, color: 'var(--text-muted)', cursor: 'pointer' }}>готово</span>
          </span>
        </PortalPopover>
      </span>
      {PINS.map(p => (
        <MultiDrop key={p.key} label={p.label} options={options[p.key]} selected={f.pins[p.key]}
          onChange={v => setF(s => ({ ...s, pins: { ...s.pins, [p.key]: v } }))} />
      ))}
      <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={f.gaps} onChange={set('gaps')} />
      <IconBtn title={filtersOn ? 'Сбросить фильтры' : 'Фильтры не заданы'} active={filtersOn} onClick={onReset}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" />
        </svg>
      </IconBtn>
    </div>
  )
}
