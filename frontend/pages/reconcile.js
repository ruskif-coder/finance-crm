import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '../components/Navbar'
import DirectoryTabs from '../components/DirectoryTabs'
import api, { auth } from '../lib/api'
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
        style={{ ...btn, width: 320, cursor: 'text' }} />
      <button style={{ ...btn, marginLeft: 6, fontSize: 12 }} onClick={() => { setOpen(false); setQ('') }}>×</button>
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 4, maxWidth: 400, background: '#fff' }}>
        {matches.map(o => (
          <div key={o.id} onClick={() => { onPick(o.id); setOpen(false); setQ('') }}
            style={{ padding: '5px 10px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6' }}>
            {o.title} <span style={{ color: '#9ca3af' }}>#{o.id}</span>
          </div>
        ))}
        {matches.length === 0 && <div style={{ padding: '5px 10px', color: '#9ca3af', fontSize: 13 }}>ничего не найдено</div>}
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
  useEffect(() => { load() }, [kind])

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

  const primaryOf = (l) => primary[l.our_id] || l.companies[0].bx_id

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

  const th = { textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid #e5e7eb', fontSize: 13, color: '#6b7280' }
  const td = { padding: '8px 10px', borderBottom: '1px solid #f3f4f6', fontSize: 14, verticalAlign: 'top' }
  const table = { width: '100%', borderCollapse: 'collapse', marginBottom: 8 }
  const chip = { display: 'inline-flex', alignItems: 'center', gap: 6, background: '#eef2ff', borderRadius: 14, padding: '3px 6px 3px 10px', fontSize: 13, margin: '2px 4px 2px 0' }
  const nameCell = (short, full, holding, count) => (
    <>
      <div>{short}{count != null && <span style={{ color: '#9ca3af', fontWeight: 400 }}> · {count} сд.</span>}</div>
      {full && full !== short && <div style={{ color: '#9ca3af', fontSize: 12 }}>{full}</div>}
      {holding && <div style={{ color: '#9ca3af', fontSize: 12 }}>холдинг: {holding}</div>}
    </>
  )
  const section = (title, n, hint) => (
    <h3 style={{ margin: '22px 0 8px', fontSize: 15 }}>{title} <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {n}</span>
      {hint && <span style={{ color: '#9ca3af', fontWeight: 400, fontSize: 12, marginLeft: 8 }}>{hint}</span>}</h3>
  )

  return (
    <>
      <Head><title>Сверка с Битриксом</title></Head>
      <Navbar active="directories" />
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '16px 20px' }}>
        <DirectoryTabs active="reconcile" />
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', margin: '12px 0' }}>
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
        </div>

        {err && <div style={{ color: '#dc2626', padding: '8px 0' }}>{err}</div>}
        {loading && <div style={{ color: '#6b7280', padding: 20 }}>Загрузка…</div>}
        {data && !loading && (
          <>
            {section('Связанные', data.linked.length, 'одна запись может иметь несколько компаний')}
            <table style={table}>
              <thead><tr><th style={{ ...th, width: '30%' }}>Наша запись</th><th style={th}>Компании в Битриксе</th><th style={{ ...th, width: 130 }}>Мастер</th></tr></thead>
              <tbody>{data.linked.map(l => {
                const multi = l.companies.length >= 2
                const pbx = primaryOf(l)
                return (
                <tr key={l.our_id}>
                  <td style={td}>{nameCell(l.our_name, l.our_full, l.our_holding, l.our_deal_count)}</td>
                  <td style={td}>
                    <div>{l.companies.map(c => (
                      <span key={c.bx_id} style={chip}>
                        {multi && (
                          <button title="сделать главной" disabled={busy}
                            onClick={() => setPrimary(p => ({ ...p, [l.our_id]: c.bx_id }))}
                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 14, lineHeight: 1, color: pbx === c.bx_id ? '#f59e0b' : '#cbd5e1' }}>
                            {pbx === c.bx_id ? '★' : '☆'}
                          </button>
                        )}
                        {c.bx_title} <span style={{ color: '#9ca3af' }}>#{c.bx_id}{dealCounts[c.bx_id] != null ? ` · ${dealCounts[c.bx_id]} сд.` : ''}</span>
                        <button title="отвязать" disabled={busy} onClick={() => post('unlink', { our_id: l.our_id, bx_id: c.bx_id })}
                          style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6b7280', fontSize: 15, lineHeight: 1 }}>×</button>
                      </span>
                    ))}</div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 4 }}>
                      <AddCompany options={unlinked} disabled={busy}
                        onPick={bxid => post('link', { our_id: l.our_id, bx_id: bxid, master: l.bx_master || master })} />
                      {multi && <button style={{ ...btn, fontSize: 12, fontWeight: 600, background: '#fef3c7', borderColor: '#fcd34d' }}
                        disabled={busy} onClick={() => consolidate(l)}>⇢ Свести в Битриксе (★ главная)</button>}
                    </div>
                  </td>
                  <td style={td}>
                    <select value={l.bx_master || 'ours'} disabled={busy} style={btn}
                      onChange={e => post('set-master', { our_id: l.our_id, master: e.target.value })}>
                      <option value="ours">Наша база</option>
                      <option value="bitrix">Битрикс</option>
                    </select>
                  </td>
                </tr>)
              })}
                {data.linked.length === 0 && <tr><td style={td} colSpan={3}><span style={{ color: '#9ca3af' }}>пусто</span></td></tr>}
              </tbody>
            </table>

            {section('Кандидаты на связку', data.candidates.length)}
            <table style={table}>
              <thead><tr><th style={{ ...th, width: '30%' }}>Наша запись</th><th style={th}>Матч в Битриксе</th><th style={{ ...th, width: 60 }}>%</th><th style={{ ...th, width: 100 }}></th></tr></thead>
              <tbody>{data.candidates.map(c => (
                <tr key={c.our_id}>
                  <td style={td}>{nameCell(c.our_name, c.our_full, c.our_holding, c.our_deal_count)}</td>
                  <td style={td}>
                    <select value={picks[c.our_id] ?? c.best.bx_id} style={{ ...btn, maxWidth: 460 }}
                      onChange={e => setPicks(p => ({ ...p, [c.our_id]: e.target.value }))}>
                      {[c.best, ...c.alternates].map(a => (
                        <option key={a.bx_id} value={a.bx_id}>{a.bx_title} · #{a.bx_id} ({Math.round(a.score * 100)}%)</option>
                      ))}
                    </select>
                  </td>
                  <td style={td}>{Math.round(c.best.score * 100)}%</td>
                  <td style={td}><button style={{ ...btn, fontWeight: 600 }} disabled={busy}
                    onClick={() => post('link', { our_id: c.our_id, bx_id: picks[c.our_id] ?? c.best.bx_id, master })}>Связать</button></td>
                </tr>))}
                {data.candidates.length === 0 && <tr><td style={td} colSpan={4}><span style={{ color: '#9ca3af' }}>пусто</span></td></tr>}
              </tbody>
            </table>

            {section('Только у нас', data.only_ours.length, 'нет пары в Битриксе')}
            <table style={table}>
              <tbody>{data.only_ours.map(o => (
                <tr key={o.our_id}>
                  <td style={{ ...td, width: '30%' }}>{nameCell(o.our_name, o.our_full, o.our_holding, o.our_deal_count)}</td>
                  <td style={td}><label style={{ fontSize: 13, color: '#6b7280', cursor: 'pointer' }}>
                    <input type="checkbox" checked={!!o.pending_create} disabled={busy}
                      onChange={e => post('flag-create', { our_id: o.our_id, on: e.target.checked })} /> завести в Битриксе
                  </label></td>
                </tr>))}
                {data.only_ours.length === 0 && <tr><td style={td}><span style={{ color: '#9ca3af' }}>пусто</span></td></tr>}
              </tbody>
            </table>

            {section('Только в Битриксе', data.only_bitrix.length, 'нет нашей записи')}
            <table style={table}>
              <tbody>{data.only_bitrix.map(b => (
                <tr key={b.id}>
                  <td style={td}>{b.title} <span style={{ color: '#9ca3af' }}>#{b.id}{dealCounts[b.id] != null ? ` · ${dealCounts[b.id]} сд.` : ''}</span></td>
                  <td style={td}><button style={btn} disabled={busy} onClick={() => post('import', { bx_id: b.id })}>Импортировать к нам</button></td>
                </tr>))}
                {data.only_bitrix.length === 0 && <tr><td style={td}><span style={{ color: '#9ca3af' }}>пусто</span></td></tr>}
              </tbody>
            </table>
          </>
        )}
      </div>
    </>
  )
}
