import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import api, { auth } from '@/lib/api'
import { can } from '@/components/Navbar'
import SectionTabs from '@/components/SectionTabs'
import { Modal, primaryBtn } from '@/components/salesTableKit'
const THRESHOLDS = [['Точное', 0.95], ['Высокое', 0.80], ['Среднее', 0.60]]

const btn = { padding: '5px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', fontSize: 13 }

// ── Пакетный прогон: план и отчёт ────────────────────────────────────────────
// Показываем панелью, а не window.confirm: решение принимается по списку из
// десятков строк, а системное окно такой список не показывает читаемо.
const ACT_LABEL = { consolidate: 'свести', rename: 'переименовать', create: 'создать',
  nothing: 'не требуется', skip: 'пропустить', link: 'связано' }
const ACT_COLOR = { consolidate: 'var(--warning-text)', rename: 'var(--text-primary)',
  create: 'var(--income)', nothing: 'var(--text-faint)', skip: 'var(--text-faint)',
  link: 'var(--income)' }
// Текст ошибки обязан называть себя: раньше окно показывало только detail и глотало
// код ответа, а detail у 422 — не строка, а список, и alert печатал «[object Object]».
// По такому окну причину восстановить нельзя, а спрашивать пользователя — дорого.
const errText = (e, fallback = 'Ошибка') => {
  if (!e?.response) return `Сервер не ответил: ${e?.message || 'нет связи'}`
  const { status, data } = e.response
  const d = data?.detail
  if (Array.isArray(d)) {
    return `HTTP ${status}: ` + d.map(x => `${(x.loc || []).slice(1).join('.')} — ${x.msg}`).join('; ')
  }
  if (typeof d === 'string' && d) return `HTTP ${status}: ${d}`
  if (status === 401) return 'HTTP 401: сессия истекла, войдите заново'
  return `HTTP ${status}: ${fallback}`
}

const planRow = { padding: '8px 0', borderBottom: '1px solid var(--border-row)' }
const planNote = { fontSize: 12, color: 'var(--text-secondary)', marginTop: 3, lineHeight: 1.5 }
const dim = { color: 'var(--text-faint)' }

function SyncPlan({ plan, counts, dealsToMove, busy, onRun, onClose }) {
  const willWrite = (counts.consolidate || 0) + (counts.rename || 0) + (counts.create || 0)
  return (
    <Modal title="Что будет сделано в Битриксе" onClose={busy ? undefined : onClose}
      summary={<>свести {counts.consolidate || 0} · переименовать {counts.rename || 0} · создать {counts.create || 0}
        {!!counts.nothing && <> · не требуется {counts.nothing}</>}
        {!!counts.skip && <> · пропустить {counts.skip}</>}
        {!!dealsToMove && <> · переедет сделок <b>{dealsToMove}</b></>}</>}
      footer={<>
        <span style={{ ...dim, fontSize: 12, flex: 1 }}>
          Запись в боевой Битрикс. Удаление помеченных XXX_ в пакет не входит.
        </span>
        <button style={btn} onClick={onClose} disabled={busy}>Отмена</button>
        <button style={primaryBtn} onClick={onRun} disabled={busy || !willWrite}>
          {busy ? 'Выполняю…' : `Выполнить (${willWrite})`}
        </button>
      </>}>
      {plan.map(p => (
        <div key={p.our_id} style={planRow}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
            <span style={{ fontWeight: 600, minWidth: 150 }}>{p.name}</span>
            <span style={{ color: ACT_COLOR[p.action], fontSize: 12, fontWeight: 600 }}>{ACT_LABEL[p.action]}</span>
          </div>
          {p.action === 'consolidate' && (
            <div style={planNote}>
              <div>главная: {p.primary.title} <span style={dim}>#{p.primary.bx_id} · {p.primary.deal_count} сд.</span></div>
              <div>→ имя: <b>{p.primary.rename_to}</b>, получит +{p.deals_to_move} сделок</div>
              {p.redundant.map(r => <div key={r.bx_id} style={dim}>• {r.title} ({r.deal_count} сд.) → {r.rename_to}</div>)}
            </div>
          )}
          {p.action === 'rename' && <div style={planNote}>{p.was} → <b>{p.now}</b></div>}
          {p.action === 'create' && <div style={planNote}>новая компания: <b>{p.now}</b></div>}
          {(p.action === 'skip' || p.action === 'nothing') && <div style={planNote}>{p.reason}</div>}
        </div>
      ))}
    </Modal>
  )
}

function SyncReport({ report, onClose }) {
  const { done, skipped, failed } = report
  return (
    <Modal title="Синхронизация завершена" onClose={onClose}
      summary={<>сделано {done.length} · пропущено {skipped.length} · ошибок {failed.length}</>}
      footer={<><span style={{ flex: 1 }} /><button style={primaryBtn} onClick={onClose}>Закрыть</button></>}>
      {failed.map(f => (
        <div key={`f${f.our_id}`} style={planRow}>
          <b>{f.name}</b> <span style={{ color: 'var(--danger)', fontSize: 12, fontWeight: 600 }}>ошибка</span>
          <div style={planNote}>{f.error}</div>
        </div>
      ))}
      {done.map(d => (
        <div key={`d${d.our_id}`} style={planRow}>
          <b>{d.name}</b> <span style={{ color: 'var(--income)', fontSize: 12, fontWeight: 600 }}>{ACT_LABEL[d.action]}</span>
          <div style={planNote}>{d.detail}</div>
        </div>
      ))}
      {skipped.map(s => (
        <div key={`s${s.our_id}`} style={planRow}>
          <b>{s.name}</b> <span style={{ ...dim, fontSize: 12 }}>пропущено</span>
          <div style={planNote}>{s.reason}</div>
        </div>
      ))}
    </Modal>
  )
}

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
  const [sel, setSel] = useState({})                 // our_id -> true, выбор для пакетного прогона
  const [plan, setPlan] = useState(null)             // предпросмотр пакетного прогона
  const [report, setReport] = useState(null)         // отчёт после прогона
  const [side, setSide] = useState('ours')           // третья колонка: 'ours' | 'bitrix'
  const [selC, setSelC] = useState({})               // our_id -> true, выбор кандидатов на связку

  const load = async (refresh = false) => {
    setLoading(true); setErr(''); setSel({}); setSelC({})
    try {
      const r = await api.get(`/sales/reconcile/${kind}${refresh ? '?refresh=1' : ''}`, auth())
      setData(r.data)
      const p = {}
      ;(r.data.candidates || []).forEach(c => { p[c.our_id] = c.best.bx_id })
      setPicks(p)
    } catch (e) {
      if (e.response?.status === 401) return router.push('/login')
      setErr(errText(e, 'ошибка загрузки'))
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
    catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  const autoLink = async () => {
    setBusy(true)
    try {
      const r = await api.post(`/sales/reconcile/${kind}/auto-link`, { threshold, master }, auth())
      alert(`Связано: ${r.data.linked}, пропущено: ${r.data.skipped}`)
      await load()
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // Главная компания записи — ТОЛЬКО явно выбранная звёздочкой.
  // Раньше сюда падала «первая привязанная», но порядок связей в базе не задан:
  // у Roki первой оказывается компания с нулём сделок, и склейка увезла бы туда обе
  // сделки, переименовав пустышку в имя агентства. Без выбора не склеиваем.
  // primary хранится строго по our_id — каждая запись независима.
  const primaryOf = (l) => primary[l.our_id] || null

  const consolidate = async (l) => {
    const pbx = primaryOf(l)
    if (!pbx) return alert('Сначала отметьте звёздочкой главную компанию — она получит все сделки.')
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
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // Привести имена связанных компаний к нашему стандарту. Склейка делает это
  // попутно, но требует ≥2 компаний — агентству с одной привязкой было недоступно.
  const renameToStandard = async (l) => {
    setBusy(true)
    try {
      const res = (await api.post(`/sales/reconcile/${kind}/rename-to-standard`, { our_id: l.our_id }, auth())).data
      if (!res.renamed.length) alert(`Уже по стандарту: ${res.standard}`)
      else {
        const lines = res.renamed.map(r => `  • ${r.was} → ${r.now}`)
        alert(`Переименовано в Битриксе (${res.renamed.length}):
` + lines.join('\n'))
      }
      await load()
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // Завести нашу запись компанией в Битриксе. Имя — тот же стандарт, иначе созданная
  // компания сразу разойдётся с остальными.
  const createInBitrix = async (c) => {
    if (!window.confirm(`Создать «${c.our_name}» компанией в Битриксе?

Это запись в боевой Битрикс.`)) return
    setBusy(true)
    try {
      const res = (await api.post(`/sales/reconcile/${kind}/create-in-bitrix`, { our_id: c.our_id }, auth())).data
      alert(`Создана компания #${res.bx_id}: ${res.title}`)
      await load(true)
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // Шаг 2 склейки: удалить компании, помеченные XXX_. Отдельной кнопкой намеренно —
  // между склейкой и удалением должен быть момент, когда результат видно и его
  // ещё можно поправить. Битрикс без корзины, удаление необратимо.
  const deleteRetired = async () => {
    setBusy(true)
    try {
      const pv = (await api.get(`/sales/reconcile/${kind}/retired`, auth())).data
      if (!pv.items.length) { alert('Компаний с пометкой XXX_ нет.'); setBusy(false); return }
      const lines = [
        `УДАЛЮ БЕЗВОЗВРАТНО (${pv.deletable.length}):`,
        ...pv.deletable.map(x => `  • ${x.title} (#${x.bx_id})`),
      ]
      if (pv.blocked.length) lines.push('', `ПРОПУЩУ — на них есть сделки (${pv.blocked.length}):`,
        ...pv.blocked.map(x => `  • ${x.title} — ${x.deal_count === null ? 'не удалось посчитать' : x.deal_count + ' сделок'}`))
      lines.push('', 'В Битриксе нет корзины: удаление не отменить. Продолжить?')
      if (!pv.deletable.length) { alert(lines.join('\n')); setBusy(false); return }
      if (!window.confirm(lines.join('\n'))) { setBusy(false); return }
      const res = (await api.post(`/sales/reconcile/${kind}/retired/delete`, {}, auth())).data
      alert(`Удалено: ${res.deleted.length}, пропущено: ${res.skipped.length}.
Бэкап: ${res.backup}`)
      await load(true)
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // ── Пакетный прогон по выбранным записям ───────────────────────────────────
  // Одна кнопка вместо 84 нажатий (16 склеек + 62 переименования + 6 созданий).
  // Главная для склейки берётся только из явного выбора звёздочкой — записи без
  // выбора бэкенд пропустит и назовёт в плане причину.
  const selIds = useMemo(() => Object.keys(sel).filter(k => sel[k]).map(Number), [sel])
  const toggleSel = (id) => setSel(s => ({ ...s, [id]: !s[id] }))
  const selectLinked = () => {
    const next = {}
    ;(data?.linked || []).forEach(l => { next[l.our_id] = true })
    setSel(next)
  }
  const syncItems = () => selIds.map(id => ({ our_id: id, primary_bx_id: primary[id] || null }))

  const openPlan = async () => {
    setBusy(true)
    try {
      const r = await api.post(`/sales/reconcile/${kind}/sync/preview`, { items: syncItems() }, auth())
      setPlan(r.data)
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  const runSync = async () => {
    setBusy(true)
    try {
      const r = await api.post(`/sales/reconcile/${kind}/sync`, { items: syncItems() }, auth())
      setPlan(null)
      setReport(r.data)
      await load(true)
    } catch (e) { alert(errText(e)) }
    finally { setBusy(false) }
  }

  // ── Пакетная привязка кандидатов (вторая колонка) ──────────────────────────
  // Компания берётся из выпадающего списка карточки, поэтому предпросмотр не нужен:
  // что связываем — видно прямо в строке. И привязка не трогает Битрикс, её снимают
  // крестиком. Отдельный набор выбора от первой колонки: там галочка означает
  // «синхронизировать», а у записи без связей это «завести компанию в Битриксе».
  const selCIds = useMemo(() => Object.keys(selC).filter(k => selC[k]).map(Number), [selC])
  const toggleSelC = (id) => setSelC(s => ({ ...s, [id]: !s[id] }))
  const selectAllCandidates = () => {
    const next = {}
    ;(data?.candidates || []).forEach(c => { next[c.our_id] = true })
    setSelC(next)
  }

  const linkSelected = async () => {
    const items = selCIds.map(id => {
      const c = (data?.candidates || []).find(x => x.our_id === id)
      return { our_id: id, bx_id: picks[id] ?? c?.best?.bx_id }
    }).filter(x => x.bx_id)
    if (!items.length) return
    if (!window.confirm(`Связать выбранных: ${items.length}.\n\n`
      + 'Правка только нашей базы — в Битрикс ничего не уходит, связь снимается крестиком.')) return
    setBusy(true)
    try {
      const r = await api.post(`/sales/reconcile/${kind}/link-many`, { items, master }, auth())
      setReport(r.data)
      await load()
    } catch (e) { alert(errText(e)) }
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
    } catch (err) { alert(errText(err, 'не удалось связать')) }
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
          <button onClick={deleteRetired} disabled={busy || loading}
            title="Шаг 2 склейки: удалить компании, помеченные XXX_, если на них нет сделок"
            style={{ ...btn, background: '#fef2f2', borderColor: '#fca5a5', color: '#b91c1c' }}>Удалить ретайрнутые (XXX_)</button>
          <button onClick={() => load(true)} disabled={busy || loading} style={btn}>Обновить из Битрикса</button>
          {countsLoading && <span style={{ color: '#9ca3af', fontSize: 12 }}>считаю сделки Битрикса…</span>}
          <span style={{ color: '#9ca3af', fontSize: 12, marginLeft: 'auto' }}>перетащите карточку из «Только в одной системе» на пару, чтобы связать</span>
        </div>

        {/* Пакетный прогон: выбор галочками в колонках слева, одна кнопка на всё. */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', margin: '0 0 10px', flexShrink: 0 }}>
          <span style={{ fontSize: 13, color: '#374151' }}>Выбрано: <b>{selIds.length}</b></span>
          <button style={btn} disabled={busy || loading} onClick={selectLinked}>Выделить связанные</button>
          <button style={btn} disabled={busy || loading || !selIds.length} onClick={() => setSel({})}>Снять</button>
          <button style={{ ...primaryBtn, padding: '6px 14px', fontSize: 13 }}
            disabled={busy || loading || !selIds.length} onClick={openPlan}>Провести синхронизацию</button>
          <span style={{ color: '#9ca3af', fontSize: 12 }}>
            свести · переименовать · создать. Удаление помеченных XXX_ — отдельной кнопкой
          </span>
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
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <input type="checkbox" checked={!!sel[l.our_id]} disabled={busy}
                          title="выбрать для пакетной синхронизации"
                          onChange={() => toggleSel(l.our_id)} style={{ marginTop: 4, flexShrink: 0 }} />
                        <div style={{ fontWeight: 500, flex: 1, minWidth: 0 }}>{nameCell(l.our_name, l.our_full, l.our_holding, l.our_deal_count)}</div>
                      </div>
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
                        <button style={{ ...btn, fontSize: 12 }} disabled={busy}
                          title="Переименовать связанные компании Битрикса по нашему шаблону"
                          onClick={() => renameToStandard(l)}>Aa По стандарту</button>
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
              <div style={{ ...colHead, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', padding: '7px 8px' }}>
                <span>Кандидаты <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {data.candidates.length}</span></span>
                <button style={{ ...btn, fontSize: 12, marginLeft: 'auto' }} disabled={busy || loading}
                  onClick={selectAllCandidates}>все</button>
                <button style={{ ...btn, fontSize: 12 }} disabled={busy || loading || !selCIds.length}
                  onClick={() => setSelC({})}>снять</button>
                <button style={{ ...primaryBtn, padding: '5px 11px', fontSize: 12 }}
                  disabled={busy || loading || !selCIds.length}
                  onClick={linkSelected}>Связать ({selCIds.length})</button>
              </div>
              <div style={colBody}>
                {data.candidates.map(c => {
                  const key = `C${c.our_id}`
                  return (
                    <div key={c.our_id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { our_id: c.our_id })}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <input type="checkbox" checked={!!selC[c.our_id]} disabled={busy}
                          title="выбрать для пакетной привязки"
                          onChange={() => toggleSelC(c.our_id)} style={{ marginTop: 4, flexShrink: 0 }} />
                        <div style={{ fontWeight: 500, flex: 1, minWidth: 0 }}>{nameCell(c.our_name, c.our_full, c.our_holding, c.our_deal_count)}</div>
                      </div>
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
              {/* Тумблер вместо двух списков подряд: у рекламодателей «только в
                  Битриксе» — 220 карточек, и нужный блок иначе не найти. */}
              <div style={{ ...colHead, display: 'flex', gap: 6, alignItems: 'center', padding: '7px 8px' }}>
                {[['ours', 'Только у нас', data.only_ours.length],
                  ['bitrix', 'Только в Битриксе', data.only_bitrix.length]].map(([v, label, n]) => (
                  <button key={v} onClick={() => setSide(v)} style={{
                    ...btn, fontSize: 13, flex: 1,
                    fontWeight: side === v ? 700 : 500,
                    background: side === v ? 'var(--accent-tint)' : '#fff',
                    borderColor: side === v ? 'var(--accent-border)' : '#d1d5db',
                    color: side === v ? 'var(--accent)' : '#374151',
                  }}>{label} <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {n}</span></button>
                ))}
              </div>
              <div style={colBody}>
                {side === 'ours' && <>
                {data.only_ours.map(o => {
                  const key = `O${o.our_id}`
                  return (
                    <div key={o.our_id} style={cardS(dragOver === key)}
                      onDragOver={e => allowDrop(e, key)} onDragLeave={() => setDragOver(null)}
                      onDrop={e => doDrop(e, { our_id: o.our_id })}>
                      <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                        <input type="checkbox" checked={!!sel[o.our_id]} disabled={busy}
                          title="выбрать для пакетной синхронизации (будет создана компания)"
                          onChange={() => toggleSel(o.our_id)} style={{ marginTop: 4, marginRight: 8, flexShrink: 0 }} />
                        <span style={handle} draggable onDragStart={e => startDrag(e, { our_id: o.our_id })} title="перетащить, чтобы связать">⠿</span>
                        <div style={{ flex: 1, minWidth: 0 }}>{nameCell(o.our_name, o.our_full, o.our_holding, o.our_deal_count)}</div>
                      </div>
                      <label style={{ fontSize: 12, color: '#6b7280', cursor: 'pointer', display: 'block', marginTop: 4 }}>
                        <input type="checkbox" checked={!!o.pending_create} disabled={busy}
                          onChange={e => post('flag-create', { our_id: o.our_id, on: e.target.checked })} /> завести в Битриксе
                      </label>
                      {/* Галочка выше — только пометка «надо завести». Кнопка реально
                          создаёт компанию в Битриксе и сразу связывает её с записью. */}
                      <button style={{ ...btn, fontSize: 12, marginTop: 4 }} disabled={busy}
                        onClick={() => createInBitrix(o)}>+ Создать в Битриксе</button>
                    </div>
                  )
                })}
                {data.only_ours.length === 0 && <div style={{ color: '#9ca3af', padding: '4px 8px 8px', fontSize: 13 }}>пусто</div>}
                </>}

                {side === 'bitrix' && <>
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
                </>}
              </div>
            </div>

          </div>
        )}

        {plan && <SyncPlan plan={plan.plan} counts={plan.counts} dealsToMove={plan.deals_to_move}
          busy={busy} onRun={runSync} onClose={() => setPlan(null)} />}
        {report && <SyncReport report={report} onClose={() => setReport(null)} />}
      </div>
    </>
  )
}
