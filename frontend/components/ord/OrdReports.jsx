// «Аккаунты → ОРД → Отчёты» (владелец 11.11.2026): отчёт для ОРД за месяц — строка «сделка × площадка × ЕРИД», выгрузка
// в Excel (колонки образца «пример по выгрузке.xlsx» + мастер-сделка и сумма сделки в УПД) и загрузка правленого файла:
// сервер хранит только отличия от расчёта, «Сбросить правки» возвращает расчёт. Допы в ОРД не идут.
import { useEffect, useMemo, useRef, useState } from 'react'
import api, { auth } from '@/lib/api'
import { can, getPermissions } from '@/lib/auth'
import { downloadFile } from '@/lib/download'
import { fmtDate, fmtDateTimeShort } from '@/lib/dates'
import { grp0, rub2 } from '@/lib/salesFormat'
import { MONO, card, inp, btn, btnSm, th, td, LoadError } from '@/components/salesTableKit'

const monthLabel = (ym) => {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
}
const NUM = { textAlign: 'right', fontFamily: MONO, whiteSpace: 'nowrap' }
const CODE = { fontFamily: MONO, whiteSpace: 'nowrap' }

function MonthList({ months, current, onPick }) {
  return (
    <div style={{ ...card, padding: '14px 8px 6px', minWidth: 300 }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr>
          <th style={th}>Месяц</th>
          <th style={{ ...th, textAlign: 'right' }}>УПД из 1С</th>
          <th style={{ ...th, textAlign: 'right' }}>Правки</th>
        </tr></thead>
        <tbody>
          {months.map(m => (
            <tr key={m.month} onClick={() => onPick(m.month)}
              style={{ cursor: 'pointer', background: m.month === current ? 'var(--accent-tint)' : 'transparent' }}>
              <td style={{ ...td, fontWeight: m.month === current ? 700 : 500 }}>{monthLabel(m.month)}</td>
              <td style={{ ...td, ...NUM, color: m.with_upd < m.kits ? 'var(--warning-fg)' : 'var(--text-primary)' }}>
                {m.with_upd} из {m.kits}</td>
              <td style={{ ...td, ...NUM }}>{m.overrides || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Summary({ s, ov }) {
  const item = (label, value, warn) => (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{label}</span>
      <b style={{ fontFamily: MONO, fontSize: 15, color: warn ? 'var(--warning-fg)' : 'var(--text-primary)' }}>{value}</b>
    </span>
  )
  return (
    <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'flex-end' }}>
      {item('Сделок', grp0(s.deals))}
      {item('Строк', grp0(s.rows))}
      {item('УПД', grp0(s.upds))}
      {item('Без № УПД из 1С', grp0(s.no_upd), s.no_upd > 0)}
      {item('Показы', grp0(s.shows))}
      {item('Сумма на площадки', rub2(s.amount))}
      {item('С пометкой', grp0(s.flagged), s.flagged > 0)}
      {ov && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Правки из файла «{ov.filename}»: {ov.count} · {fmtDateTimeShort(ov.at)}{ov.by ? ` · ${ov.by}` : ''}</span>}
    </div>
  )
}

function Rows({ rows }) {
  return (
    <div style={{ ...card, padding: '14px 8px 6px', overflow: 'auto', maxHeight: 'calc(100vh - 330px)' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-card)' }}><tr>
          {['ID РК', 'Мастер', 'УПД', 'Дата УПД', 'Бюджет УПД', 'Сделка в УПД', 'Площадка', 'Показы', 'Клики', 'ЕРИД', 'На площадку', 'Пометка']
            .map((h, i) => <th key={h} style={{ ...th, textAlign: [4, 5, 7, 8, 10].includes(i) ? 'right' : 'left' }}>{h}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ background: r.edited ? 'var(--warning-bg)' : 'transparent' }}>
              <td style={{ ...td, ...CODE }} title={r.deal_title}>{r.deal_code}</td>
              <td style={{ ...td, ...CODE }}>{r.master_code || '—'}</td>
              <td style={{ ...td, ...CODE }}>{r.upd_no || '—'}</td>
              <td style={{ ...td, ...CODE }}>{fmtDate(r.upd_date)}</td>
              <td style={{ ...td, ...NUM }}>{rub2(r.upd_gross)}</td>
              <td style={{ ...td, ...NUM }}>{rub2(r.deal_gross)}</td>
              <td style={td}>{r.domain || '—'}</td>
              <td style={{ ...td, ...NUM }}>{grp0(r.shows)}</td>
              <td style={{ ...td, ...NUM }}>{grp0(r.clicks)}</td>
              <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{r.erid || '—'}</td>
              <td style={{ ...td, ...NUM }}>{rub2(r.amount)}</td>
              <td style={{ ...td, fontSize: 12, color: 'var(--warning-fg)' }}>{r.edited ? ['правка из файла', r.note].filter(Boolean).join('; ') : r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function OrdReports() {
  const [months, setMonths] = useState(null)
  const [month, setMonth] = useState('')
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [mayEdit, setMayEdit] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => { setMayEdit(can(getPermissions(), 'ord', 'edit')) }, [])

  const loadMonths = async () => {
    try {
      const r = (await api.get('/ord/reports/months', auth())).data
      setMonths(r)
      setMonth(cur => cur || (r[0] && r[0].month) || '')
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить месяцы') }
  }
  // ответ на месяц, с которого уже ушли, не рисуем: иначе при быстром переключении под шапкой нового месяца
  // оказываются строки прошлого (ревью 11.11.2026)
  const shownMonth = useRef('')
  const loadMonth = async (m) => {
    if (!m) return
    shownMonth.current = m
    setData(null); setErr('')
    try {
      const d = (await api.get(`/ord/reports/${m}`, auth())).data
      if (shownMonth.current === m) setData(d)
    } catch (e) { if (shownMonth.current === m) setErr(e.response?.data?.detail || 'Не удалось загрузить отчёт') }
  }
  useEffect(() => { loadMonths() }, [])
  useEffect(() => { loadMonth(month) }, [month])

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!data) return []
    return s ? data.rows.filter(r => [r.deal_code, r.domain, r.erid, r.master_code, r.upd_no].some(v => (v || '').toLowerCase().includes(s))) : data.rows
  }, [data, q])

  const act = async (label, fn) => {
    setBusy(label); setMsg(''); setErr('')
    try { await fn(); await loadMonths(); await loadMonth(month) }
    catch (e) { setErr(e.response?.data?.detail || 'Не получилось') }
    finally { setBusy('') }
  }
  const upload = (e) => {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f) return
    act('import', async () => {
      const fd = new FormData()
      fd.append('file', f)
      const c = (await api.post(`/ord/reports/${month}/import`, fd, auth())).data
      setMsg(`Загружено: правок ${c['правка']}, добавлено строк ${c['добавлена']}, убрано ${c['убрана']}`)
    })
  }
  const reset = () => {
    if (!window.confirm(`Сбросить правки из файла за ${monthLabel(month)}? Отчёт вернётся к расчёту.`)) return
    act('reset', async () => { await api.delete(`/ord/reports/${month}/overrides`, auth()); setMsg('Правки сброшены — отчёт по расчёту') })
  }
  const snapshot = () => act('snap', async () => {
    const r = (await api.post(`/ord/reports/${month}/snapshot`, {}, auth())).data
    setMsg(`Разрез по ЕРИД снят: ${r.rows} строк`)
  })

  if (months === null) return err ? <LoadError text={err} onRetry={loadMonths} /> : <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>
  if (!months.length) return <div style={{ color: 'var(--text-muted)' }}>Мастер-сделок с комплектами УПД пока нет — отчитываться не о чем.</div>

  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      <MonthList months={months} current={month} onPick={setMonth} />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <b style={{ fontSize: 18 }}>Отчёт ОРД · {month && monthLabel(month)}</b>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="сделка, площадка, ЕРИД, УПД" style={{ ...inp, width: 240 }} />
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button style={btn(true)} disabled={!!busy || !data}
              onClick={() => { setBusy('xlsx'); downloadFile(`/ord/reports/${month}/xlsx`, null, setErr).finally(() => setBusy('')) }}>
              {busy === 'xlsx' ? 'Готовлю…' : 'Скачать Excel'}</button>
            {mayEdit && <>
              <button style={btn(false)} disabled={!!busy} onClick={() => fileRef.current && fileRef.current.click()}
                title="Правленый файл этого месяца: сохраняются только отличия от расчёта">
                {busy === 'import' ? 'Загружаю…' : 'Загрузить правки'}</button>
              <input ref={fileRef} type="file" accept=".xlsx" onChange={upload} style={{ display: 'none' }} />
              {data?.overrides && <button style={btnSm(false)} disabled={!!busy} onClick={reset}>Сбросить правки</button>}
              <button style={btnSm(false)} disabled={!!busy} onClick={snapshot}
                title="Разрез показов площадки по ЕРИД из сырья DSP — снимается каждую ночь, кнопка — снять сейчас">
                {busy === 'snap' ? 'Снимаю…' : 'Снять ЕРИД'}</button>
            </>}
          </span>
        </div>
        {err && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{err}</div>}
        {msg && <div style={{ color: 'var(--income-fg)', fontSize: 13 }}>{msg}</div>}
        {data ? <>
          <Summary s={data.summary} ov={data.overrides} />
          <Rows rows={shown} />
        </> : !err && <div style={{ color: 'var(--text-muted)' }}>Считаю…</div>}
      </div>
    </div>
  )
}
