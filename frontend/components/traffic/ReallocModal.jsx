// «Темп размещения → Перераспределить объём» (хендофф docs/перераспределение.zip, 26.10.2026).
// Каркас: KPI → 4 действия → фильтры → таблица площадок → динамика по дням | история; футер — баланс, причина, «Применить · N».
// «Перенести» только раскладывает новые планы в таблицу; записывает «Применить» — при сохранённой сумме планов и с причиной
// (уходит в журнал РК). «Поднять темп» и «Снять» действуют сразу, после подтверждения. Расчёт — сервер (`app/ad/realloc`).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Modal, MONO } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api from '@/lib/api'
import { grp } from '@/lib/salesFormat'
import { balance, changedRows, chart, movedOf, passes } from '@/lib/reallocView.mjs'
import { ReallocActions, ReallocKpis } from './realloc/ReallocTop'
import { ReallocFilters, ReallocTable } from './realloc/ReallocTable'
import { ReallocChart, ReallocHistory } from './realloc/ReallocChart'

const ghost = { display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 15px', borderRadius: 10, background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit' }
const nf = (v) => grp(Math.round(v || 0))
const ddmm = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : '')

export default function ReallocModal({ row, auth, canEdit = true, onClose, onDone, onBack }) {
  const [v, setV] = useState(null)
  const [edits, setEdits] = useState({})
  const [filter, setFilter] = useState('all')
  const [sel, setSel] = useState(null)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')

  const load = useCallback(() => api.get(`/traffic-dashboard/campaign/${row.id}/realloc`, auth())
    .then(r => { setV(r.data); setErr('') })
    .catch(e => setErr(e?.response?.data?.detail || 'Не удалось посчитать перераспределение')), [row.id, auth])
  useEffect(() => { load() }, [load])

  const rows = useMemo(() => (v?.rows || []).filter(r => r.running), [v])
  const sc = useMemo(() => Object.fromEntries((v?.scenarios || []).map(s => [s.key, s])), [v])
  const setEdit = (id, val) => setEdits(e => { const n = { ...e }; if (val == null) delete n[id]; else n[id] = val; return n })
  const changed = changedRows(rows, edits)
  const bal = balance(v?.rows || [], edits)
  const moved = movedOf(rows, edits)
  const days = v?.days_left || 0

  // Действие, которое пишет сразу (буст, снять, сбросить записанное): подтверждение → ручка → пересчёт окна.
  const act = async (ask, fn, msg) => {
    if (!window.confirm(ask)) return
    setBusy(true); setErr('')
    try { await fn(); await load(); setEdits({}); setDone(msg); onDone && onDone() }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось выполнить') } finally { setBusy(false) }
  }
  const apply = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/traffic-dashboard/campaign/${row.id}/realloc`,
        { plans: Object.fromEntries(changed.map(x => [x.id, edits[x.id]])), reason }, auth())
      setV(r.data.view); setEdits({}); setReason(''); setDone('планы записаны, лимиты ушли в DSP'); onDone && onDone()
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось применить') } finally { setBusy(false) }
  }

  if (!v) {
    return (
      <Modal title="Перераспределить объём" width={560} onClose={onClose}>
        <div style={{ display: 'flex', gap: 8, padding: 16, color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
          {err || <><Cube variant="spinner" size={14} /> считаю…</>}</div>
      </Modal>
    )
  }

  const donors = rows.filter(r => (r.note || '').startsWith('успеет'))
  const takers = rows.filter(r => r.role === 'запас' || r.role === 'получатель')
  const s = (k) => sc[k] || {}
  // Тексты карточек и подтверждений — с сервера (`app/ad/realloc.scenarios`, 26.10.2026): одна фраза в одном месте
  const acts = [
    { key: 'move', title: 'Перенести недобор', tone: 'var(--income)', btn: 'Перенести', on: canEdit && s('move').enabled,
      text: s('move').text,
      run: () => setEdits(e => ({ ...e, ...s('move').plans })) },
    { key: 'lagging', title: 'Поднять темп не открутившим', tone: 'var(--warning)', btn: 'Поднять темп', on: canEdit && s('lagging').enabled,
      text: s('lagging').text,
      run: () => act(s('lagging').confirm,
        () => api.post(`/traffic-dashboard/campaign/${row.id}/boost`, { pct: s('lagging').pct, days: s('lagging').days, placement_ids: s('lagging').placement_ids }, auth()),
        `темп поднят на ${s('lagging').pct} %`) },
    { key: 'drop', title: 'Снять площадки без трафика', tone: 'var(--danger)', btn: 'Снять', on: canEdit && s('drop').enabled,
      text: s('drop').text,
      run: () => act(s('drop').confirm, async () => {
        for (const id of s('drop').placement_ids) await api.put(`/traffic-dashboard/placement/${id}/status`, { status: 'завершена' }, auth())
      }, 'площадки сняты') },
    // План РК урезали ниже ручных планов (26.10.2026): карточка подсвечена, сбрасывает человек — сами планы не трогаются
    { key: 'reset', title: 'Сбросить ручные планы', tone: s('reset').urgent ? 'var(--danger)' : 'var(--text-muted)', urgent: !!s('reset').urgent,
      btn: 'Сбросить', on: canEdit && (changed.length > 0 || s('reset').enabled),
      // «Ручных правок: N» — несохранённые правки в окне, их знает только окно
      text: changed.length ? `Ручных правок: ${changed.length}` : s('reset').text,
      run: () => (changed.length ? setEdits({})
        : act(s('reset').confirm,
          () => api.delete(`/traffic-dashboard/campaign/${row.id}/realloc`, auth()), 'ручные планы сняты')) },
  ]
  const kpis = [
    ['Недобор · показы', v.shortfall, 'var(--danger-fg)', donors.length ? `${donors.map(r => r.name).join(', ')} упёрлись в сеть` : 'никто не упёрся в сеть'],
    ['Запас в темпе', v.spare, 'var(--accent-fg)', `${takers.length} площадок`],
    ['Переносим', moved, moved ? 'var(--income-fg)' : 'var(--text-disabled)', moved ? 'после правок' : 'пока ничего'],
    ['Не пристроить', v.unplaced, v.unplaced ? 'var(--danger-fg)' : 'var(--text-primary)', v.unplaced ? 'запаса не хватает' : 'запаса хватает',
      v.unplaced ? 'var(--danger-fg)' : undefined],
  ]
  const shown = rows.filter(r => passes(r, filter, edits))
  const picked = rows.find(r => r.id === sel)
  const c = chart(picked ? [picked] : rows, edits, v.daily, days)
  const ok = canEdit && changed.length > 0 && bal.diff === 0 && reason.trim() && v.can_apply && !busy
  const h = v.head || {}

  const title = (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: '-0.02em' }}>Перераспределить объём</span>
      <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 400, color: 'var(--text-muted)' }}>
        <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{h.code || row.deal_code}</span>
        {[h.brand, h.service, h.date_start && `флайт ${ddmm(h.date_start)}–${ddmm(h.date_end)}`, `до конца флайта ${days} дн.`].filter(Boolean).map(x => ` · ${x}`).join('')}
      </span>
    </span>
  )
  const footer = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', width: '100%' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: err ? 'var(--danger-fg)' : bal.diff ? 'var(--danger-fg)' : 'var(--income-fg)' }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: err || bal.diff ? 'var(--danger)' : 'var(--income)' }} />
        {err || (bal.diff ? `План РК не сходится на ${bal.diff > 0 ? '+' : '−'}${nf(Math.abs(bal.diff))} — перенос должен сохранять сумму`
          : done && !changed.length ? done : `План РК сохранён: сумма новых планов = ${nf(bal.before)}`)}
      </span>
      {canEdit && (
        <input value={reason} onChange={e => setReason(e.target.value)} maxLength={300} placeholder="Причина переноса — обязательно, уйдёт в журнал РК"
          style={{ flex: '1 1 280px', minWidth: 220, height: 34, boxSizing: 'border-box', padding: '0 11px', borderRadius: 12, fontSize: 12.5, outline: 'none',
            fontFamily: 'inherit', color: 'var(--text-primary)', background: 'var(--bg-card)',
            border: `1px solid ${changed.length && !reason.trim() ? 'var(--warning-border)' : 'var(--border-card)'}` }} />)}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 10 }}>
        {!!onBack && <button type="button" style={ghost} onClick={onBack} disabled={busy}>Назад</button>}
        {canEdit && (
          <button type="button" onClick={ok ? apply : undefined} disabled={!ok}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 16px', border: 'none', borderRadius: 10, fontSize: 12.5, fontWeight: 700,
              whiteSpace: 'nowrap', fontFamily: 'inherit', background: ok ? 'var(--accent)' : 'var(--text-disabled)', color: 'var(--on-accent)', cursor: ok ? 'pointer' : 'not-allowed' }}>
            {busy && <Cube variant="spinner" size={14} />}Применить{changed.length ? ` · ${changed.length}` : ''}</button>)}
      </span>
    </div>
  )

  return (
    // Шапка (KPI, действия, фильтры) и низ (график, история) стоят; площадки — в прокрутке между ними (владелец 26.10.2026).
    <Modal title={title} width={1480} footer={footer} fill onClose={() => { if (!busy) onClose() }}>
      <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0 10px' }}>
        <ReallocKpis items={kpis} />
        {!!v.over_plan && <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--danger-fg)' }}>
          План РК уменьшили в медиаплане: ручные планы площадок {nf(v.over_plan.manual)} больше плана РК {nf(v.over_plan.plan)} — РК
          перекрутит. Сбросьте ручные планы или перенесите заново.</div>}
        {!!v.boost_live && <div style={{ fontSize: 12.5, color: 'var(--warning-fg)' }}>
          Идёт «Поднять темп»: планы площадок подняты на его процент, переносить их сейчас нельзя — снимите буст или дождитесь его конца.</div>}
        <ReallocActions acts={acts} busy={busy} />
        <ReallocFilters rows={rows} edits={edits} filter={filter} setFilter={setFilter} />
      </div>
      <div style={{ flex: '1 1 auto', minHeight: 140, overflow: 'auto', borderTop: '1px solid var(--border-inner)', borderBottom: '1px solid var(--border-inner)' }}>
        <ReallocTable rows={shown} all={v.rows || []} edits={edits} setEdit={setEdit} days={days} sel={sel} setSel={setSel} canEdit={canEdit} busy={busy} />
      </div>
      <div style={{ flex: '0 0 auto', display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr)', gap: 12, paddingTop: 10 }}>
        <ReallocChart c={c} scopeName={picked?.name} onClear={() => setSel(null)} changed={changed.length > 0} />
        <ReallocHistory code={h.code || row.deal_code} items={v.history || []} />
      </div>
    </Modal>
  )
}
