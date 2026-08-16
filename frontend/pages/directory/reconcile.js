import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import api, { auth } from '@/lib/api'
import { can } from '@/components/Navbar'
import SectionTabs from '@/components/SectionTabs'
const THRESHOLDS = [['Точное', 0.95], ['Высокое', 0.80], ['Среднее', 0.60]]

const btn = { padding: '5px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', fontSize: 13 }

// Поиск компании Битрикса для добавления ещё одной привязки к записи.
function AddCompany({ options, onPick, disabled }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    const base = s ? options.filter(o => o.title.toLowerCase().includes(s) || o.id.includes(s)) : options
    return base.slice(0, 8)
  }, [q, options])
  if (!open) return <button style={{ ...btn, fontSize: 12 }} disabled={disabled} onClick={() => setOpen(true)}>+ привязать компанию</button>
  return (
    <div style={{ marginTop: 6 }}>
      <input autoFocus placeholder="поиск компании в Битриксе…" value={q} onChange={e => setQ(e.target.value)}
        style={{ ...btn, width: '100%', boxSizing: 'border-box', cursor: 'text' }} />
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 4, background: '#fff' }}>
        {matches.map(o => (
          <div key={o.id} onClick={() => { onPick(o.id); setOpen(false); setQ('') }}
            style={{ padding: '5px 10px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6' }}>
            {o.title} <span style={{ color: '#9ca3af' }}>#{o.id}</span>
          </div>
        ))}
        {matches.length === 0 && <div style={{ padding: '5px 10px', color: '#9ca3af', fontSize: 13 }}>ничего не найдено</div>}
        <div onClick={() => { setOpen(false); setQ('') }} style={{ padding: '5px 10px', cursor: 'pointer', fontSize: 12, color: '#6b7280' }}>× закрыть</div>
      </div>
    </div>
  )
}

export default function Reconcile() {
  const router = useRouter()
  const [kind, setKind] = useState('agencies')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [master, setMaster] = useState('ours')       // приоритет по умолчанию
  const [threshold, setThreshold] = useState(0.80)
  const [busy, setBusy] = useState(false)
  const [picks, setPicks] = useState({})             // our_id -> выбранный bx_id в кандидатах
  const [primary, setPrimary] = useState({})         // our_id -> bx_id главной при склейке
  const [dealCounts, setDealCounts] = useState({})   // bx_id -> кол-во сделок Битрикса (грузится отдельно)
  const [countsLoading, setCountsLoading] = useState(false)
  const [dragOver, setDragOver] = useState(null)     // ключ карточки под курсором при перетаскивании

  const load = async (refresh = false) => {
    setLoading(true); setErr('')
    try {
      const r = await api.get(`/sales/reconcile/${kind}${refresh ? '?refresh=1' : ''}`, auth())
      setData(r.data)
      const p = {}
      ;(r.data.candidates || []).forEach(c => { p[c.our_id] = c.best.bx_id })
      setPicks(p)
    } catch (e) {
      if (e.response?.status === 401) return router.push('/login')
      setErr(e.response?.data?.detail || 'Ошибка загрузки')
    } finally { setLoading(false) }
    loadDealCounts(refresh)   // счётчики сделок — отдельно, не блокируют рендер страницы
  }

  const loadDealCounts = async (refresh = false) => {
    setCountsLoading(true)
    try {
      const r = await api.get(`/sales/reconcile/${kind}/deal-counts${refresh ? '?refresh=1' : ''}`, auth())
      setDealCounts(r.data.counts || {})
    } catch (e) { /* счётчики некритичны — молчим */ }
    finally { setCountsLoading(false) }
  }
  useEffect(() => {
    const role = localStorage.getItem('role') || ''
    const perms = JSON.parse(localStorage.getItem('permissions') || '{}')
    if (role !== 'admin' && !can(perms, 'bx_reconcile', 'view')) {
      router.replace('/'); return
    }
    load()
  }, [kind])

  const post = async (path, body) => {
    setBusy(true)
    try { await api.post(`/sales/reconcile/${kind}/${path}`, body, auth()); await load() }
    catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBusy(false) }
  }

  const autoLink = async () => {
    setBusy(true)
    try {
      const r = await api.post(`/sales/reconcile/${kind}/auto-link`, { threshold, master }, auth())
      alert(`Связано: ${r.data.linked}, пропущено: ${r.data.skipped}`)
      await load()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBusy(false) }
  }

  // Главная компания записи: явно выбранная звёздочкой, иначе первая привязанная.
  // primary хранится строго по our_id — каждая запись независима.
  const primaryOf = (l) => primary[l.our_id] ?? l.companies[0]?.bx_id

  const consolidate = async (l) => {
    const pbx = primaryOf(l)
    setBusy(true)
    try {
      const pv = (await api.post(`/sales/reconcile/${kind}/consolidate/preview`, { our_id: l.our_id, primary_bx_id: pbx }, auth())).data
      const lines = [
        `Свести «${l.our_name}» в Битриксе:`, '',
        `ГЛАВНАЯ: ${pv.primary.title} (#${pv.primary.bx_id}, ${pv.primary.deal_count} сделок)`,
        `  → переименую в: ${pv.primary.rename_to}`,
        `  → получит +${pv.total_deals_to_move} сделок`, '',
        `РЕТАЙР (переименую в XXX_, НЕ удаляю):`,
        ...pv.redundant.map(r => `  • ${r.title} (${r.deal_count} сделок) → ${r.rename_to}`), '',
        `Это запись в боевой Битрикс. Бэкап сохранится на сервере. Продолжить?`,
      ]
      if (!window.confirm(lines.join('\n'))) { setBusy(false); return }
      const res = (await api.post(`/sales/reconcile/${kind}/consolidate`, { our_id: l.our_id, primary_bx_id: pbx }, auth())).data
      alert(`Готово: переброшено ${res.moved_deals} сделок, ретайр ${res.retired}.\nБэкап: ${res.backup}`)
      await load()
    } catch (e) { alert(e.response?.data?.detail || 'Ошибка') }
    finally { setBusy(false) }
  }

  // Свободные (непривязанные) компании Битрикса — для добавления ещё одной привязки.
  const unlinked = useMemo(() => {
    if (!data) return []
    const taken = new Set()
    data.linked.forEach(l => l.companies.forEach(c => taken.add(c.bx_id)))
    return data.all_bitrix.filter(c => !taken.has(c.id))
  }, [data])

  // ── Drag & drop ─────────────────────────────────────────────────────────────
  // Перетаскиваемый токен несёт одну сторону связи (our_id ИЛИ bx_id), а если это
  // уже привязанная компания — ещё from_our_id (откуда её забрали). Цель несёт свою
  // сторону. На дропе объединяем: получаем пару (our_id, bx_id) → связываем.
  const startDrag = (e, payload) => {
    e.dataTransfer.setData('text/plain', JSON.stringify(payload))
    e.dataTransfer.effectAllowed = 'move'
  }
  const allowDrop = (e, key) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOver !== key) setDragOver(key)
  }
  const doDrop = async (e, target) => {
    e.preventDefault()
    setDragOver(null)
    let src
    try { src = JSON.parse(e.dataTransfer.getData('text/plain')) } catch { return }
    const our_id = target.our_id ?? src.our_id
    const bx_id = target.bx_id ?? src.bx_id
    if (our_id == null || bx_id == null) return          // нужна ровно одна наша + одна bx-сторона
    if (src.from_our_id === our_id) return                // компания уже на этой записи
    setBusy(true)
    try {
      // перенос между связанными: сначала снять со старой записи, чтобы link не упал 409
      if (src.from_our_id != null && src.from_our_id !== our_id) {
        await api.post(`/sales/reconcile/${kind}/unlink`, { our_id: src.from_our_id, bx_id }, auth())
      }
      await api.post(`/sales/reconcile/${kind}/link`, { our_id, bx_id, master }, auth())
      await load()
    } catch (err) { alert(err.response?.data?.detail || 'Ошибка связывания') }
    finally { setBusy(false) }
  }

  const nameCell = (short, full, holding, count) => (
    <>
      <div style={{ fontSize: 14 }}>{short}{count != null && <span style={{ color: '#9ca3af', fontWeight: 400 }}> · {count} сд.</span>}</div>
      {full && full !== short && <div style={{ color: '#9ca3af', fontSize: 12 }}>{full}</div>}
      {holding && <div style={{ color: '#9ca3af', fontSize: 12 }}>холдинг: {holding}</div>}
    </>
  )

  // ── Стили колонок/карточек ──────────────────────────────────────────────────
  const colWrap = { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', border: '1px solid #e5e7eb', borderRadius: 12, background: '#fafafa', overflow: 'hidden' }
  const colHead = { padding: '10px 12px', borderBottom: '1px solid #e5e7eb', fontSize: 14, fontWeight: 600, background: '#fff', flexShrink: 0 }
  const colBody = { overflowY: 'auto', padding: 10, flex: 1 }
  const subHead = { fontSize: 12, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.03em', margin: '4px 2px 6px' }
  const cardS = (hl) => ({ background: '#fff', border: `1px solid ${hl ? '#6366f1' : '#e5e7eb'}`, boxShadow: hl ? '0 0 0 2px #c7d2fe' : 'none', borderRadius: 10, padding: 10, marginBottom: 8, transition: 'box-shadow .1s, border-color .1s' })
  const chip = { display: 'inline-flex', alignItems: 'center', gap: 6, background: '#eef2ff', borderRadius: 14, padding: '3px 8px 3px 8px', fontSize: 13, margin: '2px 4px 2px 0' }
  const handle = { cursor: 'grab', color: '#cbd5e1', fontSize: 15, lineHeight: 1, userSelect: 'none', marginRight: 6 }
  const count = (n) => n != null ? <span style={{ color: '#9ca3af' }}> · {n} сд.</span> : null

  return (
    <>
      <Head><title>Сверка с Битриксом</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '12px 20px', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)', boxSizing: 'border-box' }}>
        <SectionTabs section="directory" />
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', margin: '10px 0', flexShrink: 0 }}>
          <select value={kind} onChange={e => setKind(e.target.value)} style={btn}>
            <option value="agencies">Агентства</option>
            <option value="advertisers">Рекламодатели</option>
          </select>
          <label style={{ fontSize: 13, color: '#374151' }}>Приоритет:&nbsp;
            <select value={master} onChange={e => setMaster(e.target.value)} style={btn}>
              <option value="ours">Наша база</option>
              <option value="bitrix">Битрикс</option>
            </select>
          </label>
          <label style={{ fontSize: 13, color: '#374151' }}>Порог:&nbsp;
            <select value={threshold} onChange={e => setThreshold(parseFloat(e.target.value))} style={btn}>
              {THRESHOLDS.map(([l, v]) => <option key={v} value={v}>{l} ({Math.round(v * 100)}%)</option>)}
            </select>
          </label>
          <button onClick={autoLink} disabled={busy || loading} style={{ ...btn, fontWeight: 600, background: '#eef2ff' }}>Авто-связать всё ≥ порога</button>
          <button onClick={() => load(true)} disabled={busy || loading} style={btn}>Обновить из Битрикса</button>
          {countsLoading && <span style={{ color: '#9ca3af', fontSize: 12 }}>считаю сделки Битрикса…</span>}
          <span style={{ color: '#9ca3af', fontSize: 12, marginLeft: 'auto' }}>перетащите карточку из «Только в одной системе» на пару, чтобы связать</span>
        </div>

        {err && <div style={{ color: '#dc2626', padding: '8px 0', flexShrink: 0 }}>{err}</div>}
        {loading && <div style={{ color: '#6b7280', padding: 20 }}>Загрузка…</div>}
        {data && !loading && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'stretch', flex: 1, minHeight: 0 }}>

            {/* ── Колонка 1: Связанные ─────────────────────────────────────── */}
            <div style={colWrap}>
              <div style={colHead}>Связанные <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {data.linked.length}</span></div>
              <div style={colBody}>
                {data.linked.map(l => {
                  const multi = l.companies.length >= 2
                  const pbx = primaryOf(l)
                  const key = `L${l.our_id}`
                  return (
                    <div key={l.our_id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { our_id: l.our_id })}>
                      <div style={{ fontWeight: 500 }}>{nameCell(l.our_name, l.our_full, l.our_holding, l.our_deal_count)}</div>
                      <div style={{ marginTop: 6 }}>{l.companies.map(c => (
                        <span key={c.bx_id} style={chip}>
                          <span style={{ cursor: 'grab', color: '#c7c9d1', fontSize: 13, lineHeight: 1, userSelect: 'none' }} draggable
                            onDragStart={e => startDrag(e, { bx_id: c.bx_id, from_our_id: l.our_id })} title="перетащите на другую запись, чтобы перенести">⠿</span>
                          {multi && (
                            <button type="button" title="сделать главной" disabled={busy}
                              onClick={() => setPrimary(p => ({ ...p, [l.our_id]: c.bx_id }))}
                              style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0, color: pbx === c.bx_id ? '#f59e0b' : '#cbd5e1' }}>
                              {pbx === c.bx_id ? '★' : '☆'}
                            </button>
                          )}
                          {c.bx_title} <span style={{ color: '#9ca3af' }}>#{c.bx_id}{dealCounts[c.bx_id] != null ? ` · ${dealCounts[c.bx_id]} сд.` : ''}</span>
                          <button type="button" title="отвязать" disabled={busy} onClick={() => post('unlink', { our_id: l.our_id, bx_id: c.bx_id })}
                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6b7280', fontSize: 15, lineHeight: 1, padding: 0 }}>×</button>
                        </span>
                      ))}</div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 }}>
                        <select value={l.bx_master || 'ours'} disabled={busy} style={{ ...btn, fontSize: 12 }}
                          onChange={e => post('set-master', { our_id: l.our_id, master: e.target.value })}>
                          <option value="ours">мастер: наша</option>
                          <option value="bitrix">мастер: Битрикс</option>
                        </select>
                        {multi && <button style={{ ...btn, fontSize: 12, fontWeight: 600, background: '#fef3c7', borderColor: '#fcd34d' }}
                          disabled={busy} onClick={() => consolidate(l)}>⇢ Свести (★ главная)</button>}
                      </div>
                      <AddCompany options={unlinked} disabled={busy}
                        onPick={bxid => post('link', { our_id: l.our_id, bx_id: bxid, master: l.bx_master || master })} />
                    </div>
                  )
                })}
                {data.linked.length === 0 && <div style={{ color: '#9ca3af', padding: 12, fontSize: 13 }}>пусто</div>}
              </div>
            </div>

            {/* ── Колонка 2: Кандидаты ─────────────────────────────────────── */}
            <div style={colWrap}>
              <div style={colHead}>Кандидаты на связку <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {data.candidates.length}</span></div>
              <div style={colBody}>
                {data.candidates.map(c => {
                  const key = `C${c.our_id}`
                  return (
                    <div key={c.our_id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { our_id: c.our_id })}>
                      <div style={{ fontWeight: 500 }}>{nameCell(c.our_name, c.our_full, c.our_holding, c.our_deal_count)}</div>
                      <div style={{ marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
                        <select value={picks[c.our_id] ?? c.best.bx_id} style={{ ...btn, flex: 1, minWidth: 0 }}
                          onChange={e => setPicks(p => ({ ...p, [c.our_id]: e.target.value }))}>
                          {[c.best, ...c.alternates].map(a => (
                            <option key={a.bx_id} value={a.bx_id}>{a.bx_title} · #{a.bx_id} ({Math.round(a.score * 100)}%)</option>
                          ))}
                        </select>
                        <span style={{ fontSize: 12, color: '#9ca3af', whiteSpace: 'nowrap' }}>{Math.round(c.best.score * 100)}%</span>
                      </div>
                      <button style={{ ...btn, fontWeight: 600, marginTop: 6 }} disabled={busy}
                        onClick={() => post('link', { our_id: c.our_id, bx_id: picks[c.our_id] ?? c.best.bx_id, master })}>Связать</button>
                    </div>
                  )
                })}
                {data.candidates.length === 0 && <div style={{ color: '#9ca3af', padding: 12, fontSize: 13 }}>пусто</div>}
              </div>
            </div>

            {/* ── Колонка 3: Только в одной системе ────────────────────────── */}
            <div style={colWrap}>
              <div style={colHead}>Только в одной системе <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {data.only_ours.length + data.only_bitrix.length}</span></div>
              <div style={colBody}>
                <div style={subHead}>Только у нас · {data.only_ours.length}</div>
                {data.only_ours.map(o => {
                  const key = `O${o.our_id}`
                  return (
                    <div key={o.our_id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { our_id: o.our_id })}>
                      <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                        <span style={handle} draggable onDragStart={e => startDrag(e, { our_id: o.our_id })} title="перетащить, чтобы связать">⠿</span>
                        <div style={{ flex: 1, minWidth: 0 }}>{nameCell(o.our_name, o.our_full, o.our_holding, o.our_deal_count)}</div>
                      </div>
                      <label style={{ fontSize: 12, color: '#6b7280', cursor: 'pointer', display: 'block', marginTop: 4 }}>
                        <input type="checkbox" checked={!!o.pending_create} disabled={busy}
                          onChange={e => post('flag-create', { our_id: o.our_id, on: e.target.checked })} /> завести в Битриксе
                      </label>
                    </div>
                  )
                })}
                {data.only_ours.length === 0 && <div style={{ color: '#9ca3af', padding: '4px 8px 8px', fontSize: 13 }}>пусто</div>}

                <div style={{ ...subHead, marginTop: 14 }}>Только в Битриксе · {data.only_bitrix.length}</div>
                {data.only_bitrix.map(b => {
                  const key = `B${b.id}`
                  return (
                    <div key={b.id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { bx_id: b.id })}>
                      <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                        <span style={handle} draggable onDragStart={e => startDrag(e, { bx_id: b.id })} title="перетащить, чтобы связать">⠿</span>
                        <div style={{ flex: 1, minWidth: 0, fontSize: 14 }}>{b.title} <span style={{ color: '#9ca3af' }}>#{b.id}{count(dealCounts[b.id])}</span></div>
                      </div>
                      <button style={{ ...btn, fontSize: 12, marginTop: 4 }} disabled={busy} onClick={() => post('import', { bx_id: b.id })}>Импортировать к нам</button>
                    </div>
                  )
                })}
                {data.only_bitrix.length === 0 && <div style={{ color: '#9ca3af', padding: '4px 8px 8px', fontSize: 13 }}>пусто</div>}
              </div>
            </div>

          </div>
        )}
      </div>
    </>
  )
}
