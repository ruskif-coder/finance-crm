/**
 * Колонки таблицы МП в шаблоне ДС (владелец 17.11.2026: клиент просит в ДС свой формат таблицы — вариант «колонки в шаблоне»).
 * Колонки живут в системном блоке таблицы (`columns`); пусто — прежние 13 колонок. Поля — с сервера (`/annex-templates/table-columns`),
 * проверка — тоже на сервере при сохранении версии (`table_cols.normalize`), здесь только правка списка.
 */
import { useEffect, useState } from 'react'
import { MONO, inp, sel as selStyle } from '@/components/salesTableKit'
import { annexTemplatesApi } from '@/lib/annexTemplatesApi'
import { detailText } from '@/lib/loadError'

const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const small = { ...inp, height: 30, padding: '0 9px', fontSize: 12.5 }
const btnS = (on = true) => ({ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 24, height: 24, padding: '0 6px', borderRadius: 6,
  border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: on ? 'var(--text-secondary)' : 'var(--text-disabled)', fontSize: 11, cursor: on ? 'pointer' : 'default' })

/** «APP = IN-APP / (Desktop+Mobile)» по строке ↔ словарь замен. */
const mapToText = (m) => Object.entries(m || {}).map(([k, v]) => `${k} = ${v}`).join('\n')
const textToMap = (t) => Object.fromEntries((t || '').split('\n').map(l => l.split('=')).filter(p => p.length >= 2)
  .map(([k, ...v]) => [k.trim(), v.join('=').trim()]).filter(([k, v]) => k && v))

function Column({ c, i, n, field, onChange, onMove, onRemove }) {
  const [mapText, setMapText] = useState(mapToText(c.map))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '9px 10px', border: '1px solid var(--border-card)', borderRadius: 10, background: 'var(--bg-card)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--accent)', flex: '0 0 20px' }}>{i + 1}</span>
        <span style={{ fontSize: 12, fontWeight: 700, flex: '1 1 auto', minWidth: 0 }}>{field?.title || c.key}</span>
        <span style={btnS(i > 0)} onClick={() => i > 0 && onMove(i, -1)} title="левее">←</span>
        <span style={btnS(i < n - 1)} onClick={() => i < n - 1 && onMove(i, 1)} title="правее">→</span>
        <span style={{ ...btnS(), color: 'var(--danger-fg)' }} onClick={() => onRemove(i)} title="убрать колонку">×</span>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ ...CAP, flex: '0 0 70px' }}>Шапка</span>
        <input value={c.label ?? ''} placeholder={(field?.label || '').replace(/\n/g, ' ')} onChange={e => onChange(i, { label: e.target.value })}
               style={{ ...small, flex: 1 }} />
      </label>
      {c.key === 'const' && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ ...CAP, flex: '0 0 70px' }}>Текст</span>
          <input value={c.value ?? ''} placeholder="в каждой строке, например Simb-ad" onChange={e => onChange(i, { value: e.target.value })} style={{ ...small, flex: 1 }} />
        </label>
      )}
      {!!field?.text && (
        <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <span style={{ ...CAP, flex: '0 0 70px', paddingTop: 7 }}>Замены</span>
          <textarea value={mapText} rows={Math.max(1, Math.min(4, mapText.split('\n').length))} placeholder="наше = как у клиента, по строке: APP = IN-APP / (Desktop+Mobile)"
                    onChange={e => { setMapText(e.target.value); onChange(i, { map: textToMap(e.target.value) }) }}
                    style={{ ...inp, flex: 1, padding: '6px 9px', fontSize: 12.5, resize: 'vertical' }} />
        </label>
      )}
      {c.key === 'volume' && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <input type="checkbox" checked={c.sum !== false} onChange={e => onChange(i, { sum: e.target.checked ? undefined : false })} />
          складывать объём в ИТОГО
        </label>
      )}
    </div>
  )
}

const clean = (c) => Object.fromEntries(Object.entries(c).filter(([k, v]) => v !== undefined && v !== '' && !(k === 'map' && !Object.keys(v).length)))

export default function TableColumnsEditor({ b, onPatch }) {
  const [cat, setCat] = useState(null)
  const [err, setErr] = useState('')
  const [adding, setAdding] = useState('')
  useEffect(() => { annexTemplatesApi.tableColumns().then(setCat).catch(e => setErr(detailText(e, 'Не удалось загрузить поля таблицы'))) }, [])
  if (!cat) return <div style={{ flex: '1 1 0', padding: 20, fontSize: 13, color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{err || 'Загружаю…'}</div>

  const byKey = Object.fromEntries(cat.items.map(x => [x.key, x]))
  const cols = b.columns?.length ? b.columns : cat.default.map(key => ({ key }))
  const isDefault = !b.columns?.length
  const set = (next) => {
    const out = next.map(clean)
    const same = out.length === cat.default.length && out.every((c, i) => Object.keys(c).length === 1 && c.key === cat.default[i])
    onPatch(b.id, { columns: same ? undefined : out })
  }
  const change = (i, patch) => set(cols.map((c, k) => (k === i ? { ...c, ...patch } : c)))
  const move = (i, d) => { const next = [...cols]; [next[i], next[i + d]] = [next[i + d], next[i]]; set(next) }
  const remove = (i) => set(cols.filter((_, k) => k !== i))
  const add = (key) => { if (key) set([...cols, { key, ...(key === 'const' ? { label: 'Свой текст' } : {}) }]); setAdding('') }
  const noMoney = !cols.some(c => byKey[c.key]?.money)

  return (
    <div style={{ flex: '1 1 0', minWidth: 0, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Таблица МП · колонки</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{isDefault ? 'стандартные 13 колонок' : `свои, ${cols.length}`} · ИТОГО считается по строкам</span>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Порядок слева направо. Шапку можно переписать как у клиента; «Замены» подменяют наше значение в ячейке его словом.
        Рекламодатель по юр. названию берётся из справочника рекламодателей — пустое запирает выгрузку ДС.
      </span>
      {cols.map((c, i) => (
        <Column key={`${c.key}-${i}-${cols.length}`} c={c} i={i} n={cols.length} field={byKey[c.key]} onChange={change} onMove={move} onRemove={remove} />
      ))}
      {noMoney && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>Нужна хотя бы одна колонка с деньгами — иначе документ не сверить с суммой.</span>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4, borderTop: '1px solid var(--border-row)' }}>
        <select value={adding} onChange={e => add(e.target.value)} style={{ ...selStyle, height: 32, fontSize: 12.5 }}>
          <option value="">+ Добавить колонку…</option>
          {cat.items.map(x => <option key={x.key} value={x.key}>{x.title}</option>)}
        </select>
        {!isDefault && (
          <span onClick={() => onPatch(b.id, { columns: undefined })} title="вернуть прежние 13 колонок"
                style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 9, border: '1px solid var(--border-card)', color: 'var(--text-secondary)', background: 'var(--bg-card)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
            Вернуть стандартные
          </span>
        )}
      </div>
    </div>
  )
}
