// «Статусы продаж» — матрица клиент × месяц × вероятность (владелец 22.10.2026; хендофф docs/статусы продаж.zip).
// Данные — сделки (/api/sales-status), встречи и комментарии — на бренд (sales_status_notes). Переносы и новые сделки копятся
// в панели «В реестр запишется» и уходят по «Сохранить»; встречи, комментарии и дата статуса сохраняются сразу.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import api, { auth } from '@/lib/api'
import Navbar, { can as canDo } from '@/components/Navbar'
import { PortalPopover } from '@/components/salesTableKit'
import { Header, Kpi, Pending } from '@/components/salesStatus/Top'
import Matrix from '@/components/salesStatus/Matrix'
import NewDealForm from '@/components/salesStatus/NewDealForm'
import { grp } from '@/lib/salesFormat'
import { todayMsk } from '@/lib/dates'
import { COL_LABEL, COL_LIGHT, colOf, monthName, noteKey, quarterList, quarterOf, quarterStart, shiftMonth, window3 } from '@/lib/salesStatus'
import { buildTitle } from '@/lib/dealTitle'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const MONO = "'JetBrains Mono', monospace"
const UI = "'Manrope', system-ui, sans-serif"
const chip = { display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }

// Выбор продажника / аккаунта. На уровне модуля: объявленный внутри страницы терял бы состояние при каждой перерисовке.
function Pick({ label, value, options, onPick }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const close = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  return (
    <span data-pop-root style={{ position: 'relative' }}>
      <span onClick={() => setOpen(o => !o)} style={chip}>{label} · {value || 'все'}<span style={{ fontSize: 10, color: 'var(--text-faint)' }}>▾</span></span>
      <PortalPopover open={open} minWidth={220}>
        {['', ...options].map(o => (
          <div key={o || '—'} onClick={() => { onPick(o); setOpen(false) }}
            style={{ padding: '7px 10px', fontSize: 13, cursor: 'pointer', borderRadius: 6, fontWeight: o === value ? 700 : 400, color: o === value ? 'var(--accent)' : 'inherit' }}>
            {o || 'все'}
          </div>
        ))}
      </PortalPopover>
    </span>
  )
}

function Toggle({ on, label, flip }) {
  return (
    <span onClick={flip} style={{ ...chip, gap: 7, padding: '0 11px', fontSize: 12, background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
      border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`, color: on ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
      <span style={{ position: 'relative', width: 26, height: 14, borderRadius: 7, background: on ? 'var(--accent)' : 'var(--text-disabled)', flex: '0 0 26px' }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 14 : 2, width: 10, height: 10, borderRadius: 3, background: 'var(--bg-card)', transition: 'left 150ms ease' }} />
      </span>{label}
    </span>
  )
}

export default function SalesStatusPage() {
  const now = todayMsk().slice(0, 7)
  const [mode, setMode] = useState('q')
  const [q, setQ] = useState(quarterOf(now))
  const [mon, setMon] = useState(now)
  const months = mode === 'q' ? window3(quarterStart(q)) : window3(mon)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [dirs, setDirs] = useState({ advertisers: [], brands: {}, services: [], vat: null })
  const [st, setSt] = useState({ open: {}, showLost: false, expandAll: false, hideEmpty: false, drag: null, over: null, sales: '', account: '', search: '' })
  const set = useCallback((patch) => setSt(s => ({ ...s, ...patch })), [])
  const [moves, setMoves] = useState({})
  const [created, setCreated] = useState([])
  const [form, setForm] = useState(null)
  const [toast, setToast] = useState('')
  const [saving, setSaving] = useState(false)
  const [mayEdit, setMayEdit] = useState(false)
  useEffect(() => { setMayEdit(canDo('sales_status', 'edit')) }, [])

  const flash = useCallback((t) => { setToast(t); setTimeout(() => setToast(''), 2400) }, [])
  const load = useCallback(() => {
    api.get('/sales-status', { ...auth(), params: { frm: months[0], to: months[2] } })
      .then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e.response?.data?.detail || 'Не удалось загрузить статусы продаж'))
  }, [months[0]]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [load])
  // Вернулись на вкладку — свежие сделки; пока в панели несохранённые переносы и новые сделки, не перечитываем
  useRefreshOnReturn(load, { enabled: !Object.keys(moves).length && !created.length })
  useEffect(() => {
    Promise.all([
      api.get('/sales/filters', auth()).catch(() => ({ data: {} })),
      api.get('/sales/brands-by-advertiser', auth()).catch(() => ({ data: {} })),
      api.get('/sales/directories/services?only_active=true', auth()).catch(() => ({ data: { items: [] } })),
      api.get('/sales/own-company', auth()).catch(() => ({ data: {} })),
    ]).then(([f, b, s, o]) => setDirs({ advertisers: f.data.advertiser_id || [], brands: b.data || {}, services: (s.data.items || []).map(x => x.name),
      vat: o.data?.vat_current ?? null }))
  }, [])

  const can = mayEdit && !!data?.can_edit
  // Сделки окна с отложенными переносами и новыми; колонка — по светофору (lib/salesStatus.colOf)
  const deals = useMemo(() => {
    const list = (data?.deals || []).map(d => {
      const mv = moves[d.id]
      const x = mv ? { ...d, moved: { month: d.month, light: d.light }, month: mv.month, light: mv.light } : d
      return { ...x, col: colOf(x) }
    }).concat(created.map(c => ({ ...c, col: colOf(c) })))
    const qx = st.search.trim().toLowerCase()
    const notes = new Map((data?.notes || []).map(n => [noteKey(n), n]))
    return list.filter(d => (!st.sales || d.sales === st.sales) && (!st.account || d.account === st.account) && (!qx ||
      [d.advertiser, d.brand, d.agency, d.code, d.title, notes.get(`a:${d.advertiser_id}|b:${d.brand_id ?? ''}`)?.comment_sales,
        notes.get(`a:${d.advertiser_id}|b:${d.brand_id ?? ''}`)?.comment_head].some(v => (v || '').toLowerCase().includes(qx))))
  }, [data, moves, created, st.sales, st.account, st.search])
  const notes = useMemo(() => new Map((data?.notes || []).map(n => [noteKey(n), n])), [data])
  const inWindow = deals.filter(d => months.includes(d.month))

  // «Без сделки»: клиенты из таблицы и бренды с заметкой, у которых в окне нет сделок
  const leads = useMemo(() => {
    const has = new Set(inWindow.map(d => `a:${d.advertiser_id}|b:${d.brand_id ?? ''}`))
    const qx = st.search.trim().toLowerCase()
    return (data?.notes || []).filter(n => n.client_name && !has.has(noteKey(n)))
      .map(n => ({ ...n, key: noteKey(n), title: n.client_name || [n.advertiser, n.brand].filter(Boolean).join(' · ') || `рекламодатель ${n.advertiser_id}` }))
      .filter(l => !qx || [l.title, l.comment_sales, l.comment_head].some(v => (v || '').toLowerCase().includes(qx)))
  }, [data, inWindow, st.search]) // eslint-disable-line react-hooks/exhaustive-deps

  const kpi = useMemo(() => {
    const live = inWindow.filter(d => !d.lost)
    const sum = (pred) => live.filter(pred).reduce((a, d) => a + d.amount, 0)
    const byMonth = (c) => months.map(m => live.filter(d => d.col === c && d.month === m).reduce((a, d) => a + d.amount, 0))
    const fact = sum(d => d.col === 'fact'), mid = sum(d => d.col === 'mid'), low = sum(d => d.col === 'low')
    const grand = fact + mid + low || 1
    const cnt = (pred) => live.filter(pred).length
    const barsOf = (vals, colors, t) => vals.map((v, i) => ({ w: `${(v / (t || 1) * 100).toFixed(1)}%`, bg: v ? colors[i] : 'transparent', title: `${monthName(months[i]) || ''} ${grp(v)}` }))
    const cards = [
      { label: 'Факт (брони)', dot: 'var(--income)', color: 'var(--income-fg)', bar: 'var(--income)', fg: 'var(--income-fg)', value: fact, pick: d => d.col === 'fact',
        hint: `${cnt(d => d.col === 'fact')} сд. · ${Math.round(fact / grand * 100)} % портфеля`, bars: barsOf(byMonth('fact'), Array(3).fill('var(--income)'), fact) },
      { label: 'Средняя', dot: 'var(--warning)', color: 'var(--warning-fg)', bar: 'var(--warning)', fg: 'var(--warning-fg)', value: mid, pick: d => d.col === 'mid',
        hint: `${cnt(d => d.col === 'mid')} сд.`, bars: barsOf(byMonth('mid'), Array(3).fill('var(--warning)'), mid) },
      { label: 'Низкая', dot: 'var(--danger)', color: 'var(--danger-fg)', bar: 'var(--danger)', fg: 'var(--danger-fg)', value: low, pick: d => d.col === 'low',
        hint: `${cnt(d => d.col === 'low')} сд.`, bars: barsOf(byMonth('low'), Array(3).fill('var(--danger)'), low) },
      { label: 'Прогноз · факт + средняя', dot: 'var(--accent)', color: 'var(--text-primary)', bar: 'var(--accent)', fg: 'var(--text-primary)', value: fact + mid,
        pick: d => d.col !== 'low', hint: `${cnt(d => d.col !== 'low')} сд. · без низкой ${grp(low)}`,
        bars: [fact, mid, low].map((v, i) => ({ w: `${(v / grand * 100).toFixed(1)}%`, bg: v ? ['var(--income)', 'var(--warning)', 'var(--danger)'][i] : 'transparent', title: '' })) },
    ]
    return cards.map(k => {
      const by = {}
      live.filter(k.pick).forEach(d => { const n = d.sales || '—'; by[n] = by[n] || { sum: 0, cnt: 0 }; by[n].sum += d.amount; by[n].cnt += 1 })
      const total = Object.values(by).reduce((a, x) => a + x.sum, 0) || 1
      const sales = Object.keys(by).filter(n => by[n].sum > 0).sort((a, b) => by[b].sum - by[a].sum).map(n => ({ name: n, value: grp(by[n].sum), w: `${(by[n].sum / total * 100).toFixed(1)}%`,
        title: `${n} · ${grp(by[n].sum)} ₽ · ${by[n].cnt} сд. · ${Math.round(by[n].sum / total * 100)} %` }))
      return { ...k, sales: sales.length ? sales : [{ name: 'сделок нет', value: '—', w: '0%', title: '', empty: true }] }
    })
  }, [inWindow, months]) // eslint-disable-line react-hooks/exhaustive-deps

  const pending = [
    // Из самих переносов, а не из окна: перенос, сделанный в другом квартале, виден в панели и уходит вместе (ревью 22.10.2026)
    ...Object.entries(moves).map(([id, mv]) => {
      const c = colOf({ light: mv.light, stage_key: mv.stage_key })
      const parts = [mv.month !== mv.fromMonth && `${monthName(mv.fromMonth)} → ${monthName(mv.month)}`,
        mv.light !== mv.fromLight && `светофор → ${COL_LABEL[c].toLowerCase()}`].filter(Boolean)
      return { key: `m${id}`, id: Number(id), code: mv.code, text: parts.join(' · ') }
    }),
    ...created.map(c => ({ key: c.id, id: c.id, isNew: true, code: 'новая', text: `${c.brand || c.advertiser} · ${monthName(c.month)} · ${COL_LABEL[colOf(c)].toLowerCase()} · ${grp(c.amount)}` })),
  ]

  const act = {
    toggle: (key) => set({ open: { ...st.open, [key]: !st.open[key] } }),
    newDeal: (p) => setForm(p),
    drop: (d, m, c) => {
      const light = COL_LIGHT[c]
      if (d.isNew) setCreated(cs => cs.map(x => (x.id === d.id ? { ...x, month: m, light } : x)))
      else {
        const orig = data.deals.find(x => x.id === d.id)
        setMoves(ms => {
          const next = { ...ms }
          const from = ms[d.id] ? { fromMonth: ms[d.id].fromMonth, fromLight: ms[d.id].fromLight } : { fromMonth: orig.month, fromLight: orig.light }
          if (from.fromMonth === m && from.fromLight === light) delete next[d.id]
          else next[d.id] = { month: m, light, code: d.code, stage_key: d.stage_key, ...from }
          return next
        })
      }
      set({ drag: null, over: null })
      flash(`${d.code || 'новая'}: ${monthName(m)}, ${COL_LABEL[c].toLowerCase()}`)
    },
    note: (tgt, field, value) => {
      api.put('/sales-status/note', { ...tgt, field, value }, auth())
        .then(r => setData(dd => ({ ...dd, notes: [...dd.notes.filter(n => noteKey(n) !== noteKey(r.data)), r.data] })))
        .then(() => flash(field.startsWith('meet') ? 'Встреча сохранена' : 'Комментарий сохранён'))
        .catch(e => flash(e.response?.data?.detail || 'Не сохранилось'))
    },
    date: (d, iso) => {
      api.put(`/sales-status/deal/${d.id}/date`, { date: iso }, auth())
        .then(() => setData(dd => ({ ...dd, deals: dd.deals.map(x => (x.id === d.id ? { ...x, status_date: iso, status_date_kind: 'manual' } : x)) })))
        .then(() => flash(`${d.code}: дата статуса ${iso.slice(8, 10)}.${iso.slice(5, 7)}`))
        .catch(e => flash(e.response?.data?.detail || 'Дата не сохранилась'))
    },
  }

  const createLocal = (f) => {
    setCreated(cs => [...cs, { id: `n${Date.now()}`, isNew: true, code: null, advertiser_id: f.adv.id, advertiser: f.adv.name, brand_id: f.brand?.id ?? null,
      brand: f.brand?.name ?? null, service: f.service, month: f.month, amount: f.amount, light: COL_LIGHT[f.col], stage: 'МП Подготовка', stage_key: 'media_plan',
      locked: false, lost: false, status_date: todayMsk(), status_date_kind: 'manual', sales: null, account: null, agency: null }])
    if (f.brand?.id) set({ open: { ...st.open, [`${f.adv.id}|${f.brand.id}`]: true } })
    setForm(null)
    flash(`Новая сделка: ${f.brand?.name || f.adv.name} · ${monthName(f.month)} · ${grp(f.amount)}`)
  }

  const save = async () => {
    setSaving(true)
    const failed = []
    try {
      const mv = Object.entries(moves).map(([id, m]) => ({ deal_id: Number(id), month: m.month, light: m.light, from_month: m.fromMonth, from_light: m.fromLight ?? null }))
      if (mv.length) await api.post('/sales-status/apply', { moves: mv }, auth())
      setMoves({})
    } catch (e) {
      setSaving(false)
      flash(e.response?.data?.detail || 'Переносы не сохранились')
      return
    }
    // Сделка, уже созданная в прошлую попытку (`dealId`), второй раз не создаётся — повтор ставит только светофор (ревью 22.10.2026)
    const left = []
    for (const c of created) {
      let dealId = c.dealId
      try {
        if (!dealId) {
          const title = buildTitle({ advertiser: c.advertiser, brand: c.brand, product: c.service, period: c.month, separate: new Set() })
          const r = await api.post('/sales/deals', { advertiser_id: c.advertiser_id, brand_id: c.brand_id, product: c.service, pipeline: 'Песочница',
            bitrix_stage: 'МП Подготовка', period: c.month, amount: c.amount, title }, auth())
          dealId = r.data.id
        }
        await api.post(`/sales/deals/${dealId}/probability`, { color: c.light }, auth())
      } catch (e) {
        failed.push(`${c.brand || c.advertiser}: ${e.response?.data?.detail || 'ошибка'}`)
        left.push({ ...c, dealId })
      }
    }
    setCreated(left)
    setSaving(false)
    flash(failed.length ? `Не создались: ${failed.join('; ')}` : 'Сохранено в реестр')
    load()
  }

  const quarters = quarterList(data?.range, now)
  const range = data?.range
  const canPrev = !range?.min || months[0] > range.min
  const canNext = !range?.max || months[2] < range.max
  const salesOpts = Array.from(new Set((data?.deals || []).map(d => d.sales).filter(Boolean))).sort()
  const accOpts = Array.from(new Set((data?.deals || []).map(d => d.account).filter(Boolean))).sort()

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI, color: 'var(--text-primary)' }}>
      <Head><title>Статусы продаж · Продажи | SIMB-AD ERP</title></Head>
      <Navbar active="sales" />
      <style>{`
        @keyframes ssRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes ssPop { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { [style*="animation"] { animation:none !important } }
      `}</style>
      <div style={{ boxSizing: 'border-box', padding: '22px 28px 40px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Header mode={mode} setMode={(m) => { setMode(m); if (m === 'm') setMon(months[0]); set({ drag: null, over: null }) }} quarters={quarters} q={q}
          setQ={(x) => { setQ(x); set({ drag: null, over: null }) }} win={months} canPrev={canPrev} canNext={canNext} step={(n) => setMon(shiftMonth(mon, n))}
          onNew={() => setForm({ month: months[0], col: 'low' })} canEdit={can} />
        {err && <div style={{ padding: 14, borderRadius: 12, background: 'var(--danger-tint)', color: 'var(--danger-fg)', fontSize: 13 }}>{err}</div>}
        <Kpi cards={kpi} />
        <Pending items={pending} saving={saving} onReset={() => { setMoves({}); setCreated([]) }} onSave={save}
          onRemove={(p) => (p.isNew ? setCreated(cs => cs.filter(c => c.id !== p.id)) : setMoves(ms => { const n = { ...ms }; delete n[p.id]; return n }))} />
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, display: 'flex',
          flexDirection: 'column', overflow: 'hidden', animation: 'ssRise .4s cubic-bezier(.22,1,.36,1) .1s both' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '12px 16px', borderBottom: '1px solid var(--border-inner)' }}>
            <input value={st.search} onChange={e => set({ search: e.target.value })} placeholder="клиент, бренд, РА, код, комментарий"
              style={{ height: 32, padding: '0 11px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, minWidth: 240, outline: 'none' }} />
            <Pick label="Продажник" value={st.sales} options={salesOpts} onPick={v => set({ sales: v })} />
            <Pick label="Аккаунт" value={st.account} options={accOpts} onPick={v => set({ account: v })} />
            <span style={{ width: 1, height: 20, background: 'var(--border-inner)', margin: '0 4px' }} />
            <Toggle on={st.showLost} label="сорванные" flip={() => set({ showLost: !st.showLost })} />
            <Toggle on={st.expandAll} label="развернуть бренды" flip={() => set({ expandAll: !st.expandAll, open: {} })} />
            <Toggle on={st.hideEmpty} label="скрыть пустое" flip={() => set({ hideEmpty: !st.hideEmpty })} />
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 14, fontSize: 11, color: 'var(--text-muted)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ padding: '1px 5px', border: '1px solid var(--border-card)', borderRadius: 5, fontFamily: MONO, fontSize: 9 }}>⠿ сумма</span>тащить</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ padding: '1px 5px', background: 'var(--income-tint)', border: '1px solid var(--income-border)', borderRadius: 5, fontFamily: MONO, fontSize: 9, color: 'var(--income-fg)' }}>🔒</span>запущен</span>
            </span>
          </div>
          {data ? <Matrix months={months} deals={inWindow} notes={notes} leads={leads} directory={data.directory || []}
              showDirectory={!st.hideEmpty && !st.sales && !st.account} search={st.search} st={st} set={set} can={can} act={act} />
            : !err && <div style={{ padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>}
        </div>
      </div>
      {form && <NewDealForm init={form} months={months} dirs={dirs} onClose={() => setForm(null)} onCreate={createLocal} />}
      {toast && <div style={{ position: 'fixed', left: '50%', bottom: 28, transform: 'translateX(-50%)', zIndex: 50, display: 'inline-flex', alignItems: 'center', gap: 10,
        padding: '10px 16px', background: 'var(--text-primary)', color: 'var(--bg-card)', borderRadius: 12, boxShadow: 'var(--shadow-float)', fontSize: 12.5 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--income)' }} />{toast}</div>}
    </div>
  )
}
