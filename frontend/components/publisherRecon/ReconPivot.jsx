// «Взаимодействие → Сводная» (хендофф 26.10.2026): площадки × месяцы года; значение — итог сверки, до согласования —
// наши данные. Клик по ячейке — детализация, «Открыть сверку» ведёт во вкладку «Сверки» с этим месяцем.
import { useEffect, useMemo, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, card } from '@/components/salesTableKit'
import { MONTHS_FULL, grpDash, monthLabel } from '@/lib/salesFormat'
import { ST } from '@/lib/publisherRecon.mjs'
import { CAPS, Dot, MonthSwitch } from './reconKit'

const FIRST_YEAR = 2024
const LEGEND = [['var(--income)', 'согласовано — итог'], ['var(--violet-fg)', 'есть ответ'], ['var(--warning)', 'ожидает площадку'],
  ['var(--accent)', 'готово к отправке'], ['var(--text-disabled)', 'ждёт закрытия'], ['var(--border-hover)', 'до сверок (наши данные)']]
const dotOf = (c) => (!c.status ? 'var(--border-hover)' : c.status === 'ждёт закрытия' ? 'var(--text-disabled)' : ST[c.status]?.dot || 'var(--text-faint)')

export default function ReconPivot({ year, setYear, current, onOpenRecon }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [mode, setMode] = useState('money')
  const [sel, setSel] = useState(null)
  const curYear = Number(current.slice(0, 4))

  useEffect(() => {
    setSel(null)
    api.get(`/publisher-recon/summary?year=${year}`, auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => { setData(null); setErr(e?.response?.data?.detail || 'Не удалось загрузить сводную') })
  }, [year])

  const months = useMemo(() => data?.months || [], [data])
  const val = (c) => (!c ? null : mode === 'money' ? c.amount : c.shows)
  const foot = months.map(m => (data?.rows || []).reduce((a, r) => a + (val(r.cells[m]) || 0), 0))
  const cols = `minmax(160px,1.2fr) repeat(${months.length},minmax(104px,1fr)) minmax(130px,1fr)`
  const fmt = (v) => (v ? grpDash(v) : '—')

  const pd = sel && data ? (() => {
    const r = data.rows.find(x => x.publisher_id === sel.pid), c = r?.cells[sel.m]
    if (!c) return null
    const agreed = c.status === 'согласовано'
    return { r, c, agreed }
  })() : null

  return (
    <div style={{ ...card, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 16, fontWeight: 700, whiteSpace: 'nowrap' }}>Сводная · закрытие по месяцам</span>
        <span style={{ ...CAPS, fontSize: 9.5, fontWeight: 400, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>итог сверки, до согласования — наши данные</span>
        <span style={{ marginLeft: 'auto' }}>
          <MonthSwitch title={String(year)} mono minWidth={56} canPrev={year > FIRST_YEAR} canNext={year < curYear}
            onPrev={() => setYear(year - 1)} onNext={() => setYear(year + 1)} /></span>
        <span style={{ display: 'inline-flex', padding: 3, gap: 2, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
          {[['money', 'Деньги, ₽'], ['shows', 'Показы']].map(([k, label]) => (
            <span key={k} onClick={() => setMode(k)} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 11px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer',
              background: mode === k ? 'var(--bg-card)' : 'transparent', color: mode === k ? 'var(--text-primary)' : 'var(--text-muted)', boxShadow: mode === k ? 'var(--shadow-card)' : 'none' }}>{label}</span>))}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-muted)' }}>
        {LEGEND.map(([c, t]) => <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot c={c} size={8} />{t}</span>)}
      </div>
      {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
      {data && !months.length && (
        <div style={{ padding: '28px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>За {year} год размещений нет</div>)}
      {data && !!months.length && (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 900, display: 'grid', gridTemplateColumns: cols, borderTop: '1px solid var(--border-card)' }}>
            <Head>Площадка</Head>
            {months.map(m => (
              <Head key={m} right color={m === current ? 'var(--accent-fg)' : undefined} bold={m === current}>{MONTHS_FULL[Number(m.slice(5)) - 1]} {m.slice(2, 4)}</Head>))}
            <Head right>Итого</Head>
            {data.rows.map(r => {
              const total = months.reduce((a, m) => a + (val(r.cells[m]) || 0), 0)
              return [
                <span key={r.publisher_id} style={{ padding: '9px 10px', fontFamily: MONO, fontSize: 12, fontWeight: 700, borderBottom: '1px solid var(--border-row)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.site}</span>,
                ...months.map(m => {
                  const c = r.cells[m], v = val(c), on = sel && sel.pid === r.publisher_id && sel.m === m
                  const agreed = c?.status === 'согласовано'
                  return (
                    <span key={m} onClick={() => c && setSel(on ? null : { pid: r.publisher_id, m })}
                      title={c ? `${r.site} · ${monthLabel(m)} · ${c.status || 'до сверок'}` : ''}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 7, padding: '9px 10px', borderBottom: '1px solid var(--border-row)',
                        background: on ? 'var(--bg-tint)' : 'transparent', boxShadow: on ? 'inset 0 0 0 1px var(--accent)' : 'none', cursor: c ? 'pointer' : 'default' }}>
                      {c && <Dot c={dotOf(c)} />}
                      <span style={{ fontFamily: MONO, fontSize: 12, whiteSpace: 'nowrap', fontWeight: agreed ? 700 : 500,
                        color: !v ? 'var(--text-disabled)' : agreed ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        {!c ? '' : v ? grpDash(v) : (mode === 'money' && c.no_cpm && c.shows ? 'нет CPM' : '—')}</span>
                    </span>
                  )
                }),
                <span key="t" style={{ padding: '9px 10px', textAlign: 'right', fontFamily: MONO, fontSize: 12, fontWeight: 700, borderBottom: '1px solid var(--border-row)', whiteSpace: 'nowrap' }}>{fmt(total)}</span>,
              ]
            })}
            <span style={{ padding: 10, ...CAPS, fontSize: 9, letterSpacing: '0.08em' }}>Итого</span>
            {foot.map((v, i) => <span key={months[i]} style={{ padding: 10, textAlign: 'right', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{fmt(v)}</span>)}
            <span style={{ padding: 10, textAlign: 'right', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{fmt(foot.reduce((a, v) => a + v, 0))}</span>
          </div>
        </div>
      )}
      {pd && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', padding: '12px 14px', background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 14 }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingRight: 18, borderRight: '1px solid var(--accent-border)' }}>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>{pd.r.site}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700, color: pd.c.status ? (ST[pd.c.status]?.fg || 'var(--text-muted)') : 'var(--text-muted)' }}>
              <Dot c={dotOf(pd.c)} />{monthLabel(sel.m)} · {pd.c.status || 'до сверок'}</span>
          </span>
          {[['Показы · наши', grpDash(pd.c.ours)], ['Показы · площадки', pd.c.theirs != null ? grpDash(pd.c.theirs) : '—'],
            ['Итог', pd.agreed ? grpDash(pd.c.shows) : 'не согласован'], ['Сумма до НДС', pd.c.amount != null ? grpDash(pd.c.amount) + ' ₽' : 'нет CPM'],
            ['Кампаний', String(pd.c.total ?? '—')]].map(([k, v]) => (
            <span key={k} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <span style={{ ...CAPS, fontSize: 8.5, fontWeight: 400, letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>{k}</span>
              <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, whiteSpace: 'nowrap',
                color: k === 'Итог' ? (pd.agreed ? 'var(--income-fg)' : 'var(--warning-fg)') : 'var(--text-primary)' }}>{v}</span>
            </span>))}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
            {sel.m >= (data.start || '2026-10') && (
              <span onClick={() => onOpenRecon(sel.m, sel.pid)} style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', borderRadius: 10, background: 'var(--accent)', color: 'var(--on-accent)', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>Открыть сверку</span>)}
            <span onClick={() => setSel(null)} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, border: '1px solid var(--border-card)', color: 'var(--text-muted)', cursor: 'pointer' }}>×</span>
          </span>
        </div>
      )}
    </div>
  )
}

const Head = ({ children, right, color, bold }) => (
  <span style={{ padding: '8px 10px', textAlign: right ? 'right' : 'left', ...CAPS, fontSize: 9, letterSpacing: '0.08em', fontWeight: bold ? 700 : 500,
    color: color || 'var(--text-cap)', borderBottom: '1px solid var(--border-card)' }}>{children}</span>
)
