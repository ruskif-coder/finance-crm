/**
 * Приоритезация — вкладка админки трафика (владелец 13.11.2026:
 * «раздел приоритезация с подключением площадок и их id»).
 *
 * Список активных площадок и их номер в сервисе приоритезации. Без номера запрос
 * площадке не уходит, а «Запустить» не заводит РК. Номер правится карандашом прямо
 * в строке (право traffic_catalog → edit); пустое значение отключает площадку.
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, card, CAP, inp, chip, cell, SortHead, EditIcon } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'

const GRID = 'minmax(220px,2fr) 150px 220px 150px'
const FILTERS = [['all', 'все'], ['on', 'подключены'], ['off', 'не подключены']]
const BAD_ID = 'целое число больше нуля'

/** '' → null (отключить); положительное целое → число; иначе undefined (ошибка ввода). */
const parseId = (raw) => {
  const v = String(raw).trim()
  if (!v) return null
  if (!/^\d+$/.test(v)) return undefined
  const n = Number(v)
  return n > 0 && Number.isSafeInteger(n) ? n : undefined
}

function FilterPill({ active, label, onClick }) {
  return (
    <span onClick={onClick} style={{
      ...chip(active ? 'var(--accent-tint)' : 'var(--bg-card)',
        active ? 'var(--accent-fg)' : 'var(--text-secondary)',
        active ? 'var(--accent-border)' : 'var(--border-card)'),
      cursor: 'pointer', userSelect: 'none',
    }}>{label}</span>
  )
}

function StatusPill({ connected }) {
  return connected
    ? <span style={chip('var(--income-tint)', 'var(--income-fg)', 'transparent')}>подключена</span>
    : <span style={chip('transparent', 'var(--text-faint)', 'var(--border-card)')}>не подключена</span>
}

/** Ячейка номера: значение с карандашом → поле ввода (Enter — сохранить, Esc — отмена). */
function IdCell({ row, mayEdit, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const shown = row.site_id ?? '—'
  if (!mayEdit) {
    return <div style={{ ...cell, fontFamily: MONO }}>{shown}</div>
  }

  const open = () => { setDraft(row.site_id == null ? '' : String(row.site_id)); setErr(''); setEditing(true) }
  const cancel = () => { setEditing(false); setErr('') }
  const save = async () => {
    const id = parseId(draft)
    if (id === undefined) { setErr(BAD_ID); return }
    if (id === (row.site_id ?? null)) { cancel(); return }
    setSaving(true); setErr('')
    try {
      await onSave(row.id, id)
      setEditing(false)
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось сохранить')
    }
    setSaving(false)
  }
  const onKey = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); save() }
    if (e.key === 'Escape') { e.preventDefault(); cancel() }
  }

  return (
    <div style={cell}>
      {editing ? (
        <input autoFocus type="text" inputMode="numeric" value={draft} disabled={saving}
          placeholder="пусто — отключить" onChange={e => setDraft(e.target.value)} onKeyDown={onKey}
          style={{ ...inp, width: 150, padding: '5px 8px', fontFamily: MONO, fontSize: 12.5 }} />
      ) : (
        <span onClick={open} title="Изменить номер (пусто — отключить)" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
          fontFamily: MONO, color: row.site_id == null ? 'var(--text-faint)' : 'var(--text-primary)',
        }}>{shown}<span style={{ color: 'var(--text-faint)', display: 'inline-flex' }}><EditIcon /></span></span>
      )}
      {!!err && <div style={{ fontSize: 11.5, color: 'var(--danger-fg)', marginTop: 4 }}>{err}</div>}
    </div>
  )
}

export default function PrioSites({ mayEdit }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows((await api.get('/prio/sites', auth())).data || []); setMsg('') }
    catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось загрузить список площадок') }
    setLoading(false)
  }, [])
  useEffect(() => { load() }, [load])

  // Ошибку пробрасываем дальше — её показывает ячейка рядом со строкой.
  const saveId = useCallback(async (id, siteId) => {
    const updated = (await api.put(`/prio/sites/${id}`, { site_id: siteId }, auth())).data
    setRows(prev => prev.map(r => (r.id === id ? { ...r, ...updated } : r)))
  }, [])

  const s = q.trim().toLowerCase()
  const shown = rows
    .filter(r => filter === 'all' || (filter === 'on' ? r.connected : !r.connected))
    .filter(r => !s || String(r.name || '').toLowerCase().includes(s))
  const connectedCount = rows.filter(r => r.connected).length

  return (
    <div>
      <div style={{ ...card, padding: '14px 18px', marginBottom: 14 }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-primary)' }}>
          Площадки в системе приоритезации</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 4 }}>
          Номер площадки в сервисе приоритезации. Без него запрос не уходит площадке, а «Запустить» не заводит РК.
        </div>
      </div>

      {!!msg && (
        <div style={{ ...card, padding: '9px 14px', marginBottom: 14, fontSize: 12.5,
          color: 'var(--danger-fg)' }}>{msg}</div>
      )}

      <div style={{ ...card, padding: '14px 18px 16px', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <input style={{ ...inp, width: 240 }} placeholder="Площадка…"
            value={q} onChange={e => setQ(e.target.value)} />
          <div style={{ display: 'flex', gap: 6 }}>
            {FILTERS.map(([k, l]) => (
              <FilterPill key={k} label={l} active={filter === k} onClick={() => setFilter(k)} />
            ))}
          </div>
          <span style={{ flex: 1 }} />
          <span style={{ ...CAP, marginBottom: 0 }}>
            подключено <span style={{ color: 'var(--text-primary)' }}>{connectedCount}</span> из {rows.length}
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 760 }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, borderBottom: '1px solid var(--border-card)' }}>
              {['Площадка', 'Статус', 'ID в системе приоритезации', 'Запросов в работе']
                .map((l, i) => <SortHead key={l} label={l} right={i === 3} />)}
            </div>
            {shown.map(r => (
              <div key={r.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center',
                padding: '8px 0', borderBottom: '1px solid var(--border-row)' }}>
                <div style={{ ...cell, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  title={r.name}>{r.name}</div>
                <div style={cell}><StatusPill connected={!!r.connected} /></div>
                <IdCell row={r} mayEdit={mayEdit} onSave={saveId} />
                <div style={{ ...cell, fontFamily: MONO, textAlign: 'right' }}>{r.requests ?? 0}</div>
              </div>
            ))}
            {!shown.length && (
              <div style={{ padding: '18px 8px', fontSize: 13, color: 'var(--text-faint)' }}>
                {loading ? 'Загрузка…' : rows.length ? 'Ничего не найдено' : 'Активных площадок нет'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
