// Вкладка «Расчёт» по хендоффу 27.10.2026: СК за месяц или квартал по закрытым сделкам (мастер-сделка прошла согласования
// в ДО), группировка «по агентству» / «по мастер-сделке», «не закрыты» отдельно. Партнёрская — во вкладке спец. условий.
// Открытый месяц — на лету, закрытый — снимком. Считает сервер (`app/agency_terms/calc.py`).
// Сделки без условия СК подсвечены с причиной (владелец 27.10.2026): нет договора закрытия — ждём договор; договор есть, условия к
// нему нет — «задать →» открывает правило на этот договор.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO } from '@/components/salesTableKit'
import { downloadFile } from '@/lib/download'
import { rub2 } from '@/lib/salesFormat'
import { fmtDayOfMoment, monthMsk } from '@/lib/dates'
import useLatest from '@/lib/useLatest'
import { calcPeriods, groupCalc, newRuleFor, periodLabel, skGap } from '@/lib/agencyTerms.mjs'
import { plural } from '@/lib/publisherRecon.mjs'
import { CAPS, Card, FilterChip, fmtPct, KpiStrip, MiniSeg, modeTone, NUM, Scroll, Title } from './kit'

const CCOLS = 'minmax(220px,1.6fr) minmax(220px,1.5fr) 80px 130px 190px 56px 120px'
const OCOLS = '80px minmax(180px,1.6fr) 100px 120px minmax(170px,1fr)'
// фильтр по способу; цвет точки — от `modeTone`, как у плашек способа
const MODE_FILTERS = [['', 'любой способ', 'var(--text-disabled)'], ['постоплата', 'постоплата', modeTone('постоплата')[2]],
  ['скидка в счёт', 'скидка в счёт', modeTone('скидка в счёт')[2]], ['не задано', 'условие не задано', 'var(--warning)']]

const GAP_BG = 'var(--warning-bg)'
const GAP_EDGE = 'inset 3px 0 0 var(--warning)'

// Причина без СК и «задать →» (правило на договор сделки); без договора — подсказка, кнопки нет
function GapNote({ row, gap, onOpenRule }) {
  const rule = onOpenRule ? newRuleFor(row) : null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap', fontSize: 11.5, fontWeight: 700, color: 'var(--warning-fg)' }}
      title={gap.kind === 'no_contract' ? 'Договор закрытия выбирается на итоговой сверке сделки — после него подберётся условие' : 'Задайте основное условие СК на этот договор'}>
      {gap.label}
      {!!rule && <span onClick={() => onOpenRule(rule)} style={{ color: 'var(--accent)', cursor: 'pointer' }}>задать →</span>}
    </span>
  )
}

function CalcRow({ r, onOpenRule }) {
  if (r.type === 'side') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: CCOLS, gap: 14, alignItems: 'center', padding: '9px 10px', background: 'var(--bg-subtle)',
        borderBottom: '1px solid var(--border-row)', borderRadius: 9 }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 7, minWidth: 0 }}>
          <span style={{ fontSize: 13.5, fontWeight: 700 }}>{r.name}</span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.packs > 1 ? `${r.packs} ${plural(r.packs, 'пакет', 'пакета', 'пакетов')} · ` : ''}{r.deals} {plural(r.deals, 'сделка', 'сделки', 'сделок')}</span>
        </span>
        <span /><span /><span style={{ ...NUM, fontWeight: 700 }}>{rub2(r.base)}</span><span /><span /><span style={{ ...NUM, fontWeight: 700 }}>{rub2(r.sk)}</span>
      </div>)
  }
  if (r.type === 'pack') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: CCOLS, gap: 14, alignItems: 'center', padding: '8px 10px 8px 22px', background: 'var(--accent-tint)',
        borderBottom: '1px solid var(--border-row)', borderRadius: 9 }}>
        <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{r.code}</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.contract}</span>
        <span /><span style={{ ...NUM, fontWeight: 700 }}>{rub2(r.base)}</span><span /><span /><span style={{ ...NUM, fontWeight: 700 }}>{rub2(r.sk)}</span>
      </div>)
  }
  const d = r.d
  const m = d.main
  const gap = skGap(d)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: CCOLS, gap: 14, alignItems: 'center', padding: `7px 10px 7px ${r.inPack ? 34 : 22}px`,
      borderBottom: '1px solid var(--border-row)', ...(gap ? { background: GAP_BG, boxShadow: GAP_EDGE } : {}) }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 7, minWidth: 0 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', whiteSpace: 'nowrap' }}>{d.code}</span>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</span>
        {!!d.late && <span title="Сделка прошлого закрытого месяца, закрыта в ДО позже — учтена здесь"
          style={{ ...CAPS, color: 'var(--violet-fg)', whiteSpace: 'nowrap' }}>закрыта позже</span>}
      </span>
      <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {r.inPack ? '' : `${d.contract} · ${d.entity}`}</span>
      <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{r.inPack ? '' : d.master_code}</span>
      <span style={NUM}>{rub2(d.base_net)}</span>
      {gap ? <GapNote row={d} gap={gap} onOpenRule={onOpenRule} /> : (
        <span style={{ fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap',
          color: modeTone(m.mode)[1] }}>{m.mode}</span>)}
      <span style={NUM}>{fmtPct(m.percent)}</span>
      <span style={NUM}>{rub2(m.amount)}</span>
    </div>
  )
}

export default function CalcView({ canEdit, isAdmin, tick, onGoEmpty, onOpenRule }) {
  const { periods, initial } = calcPeriods(monthMsk())
  const [period, setPeriod] = useState(initial)
  const [mode, setMode] = useState('')
  const [by, setBy] = useState('agency')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const latest = useLatest()
  const query = () => new URLSearchParams(Object.entries({ period, mode }).filter(([, v]) => v !== '')).toString()

  const load = () => {
    const fresh = latest()
    setErr('')
    api.get(`/agency-terms/calc?${query()}`, auth())
      .then((r) => { if (fresh()) setData(r.data) })
      .catch((e) => { if (fresh()) setErr(e.response?.data?.detail || 'Расчёт не загрузился') })
  }
  useEffect(load, [period, mode, tick])        // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn, done) => {
    setBusy(true); setMsg('')
    try { await fn(); setMsg(done); load() } catch (e) { setMsg(e.response?.data?.detail || 'Не получилось') } finally { setBusy(false) }
  }
  const month = period.length === 7 ? (data?.months || []).find((m) => m.period === period) : null
  const noRule = data?.totals.no_rule || 0
  const noContract = data ? data.rows.filter((x) => skGap(x)?.kind === 'no_contract').length : 0
  const openRule = canEdit ? onOpenRule : null
  const rows = data ? groupCalc(data.rows, by) : []
  const t = data?.totals

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <MiniSeg value={period} opts={periods} onPick={setPeriod} />
        {MODE_FILTERS.map(([k, label, dot]) => <FilterChip key={label} on={mode === k} label={label} dot={dot} h={34} onClick={() => setMode(k)} />)}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {!!month && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, whiteSpace: 'nowrap',
            color: month.closed ? 'var(--income-fg)' : 'var(--text-muted)' }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: month.closed ? 'var(--income)' : 'var(--accent)' }} />
            {month.closed ? `месяц закрыт ${fmtDayOfMoment(month.closed_at)} — снимок` : 'месяц открыт — считается на лету'}</span>}
          {!!month && !month.closed && canEdit && (
            <button type="button" disabled={busy || noRule > 0} title={noRule ? `Сделок без условия СК: ${noRule} — задайте условия, потом закрывайте` : ''}
              onClick={() => {
                if (window.confirm(`Закрыть ${periodLabel(period)}? СК зафиксируется снимком, правка правил его больше не изменит.`)) {
                  act(() => api.post(`/agency-terms/months/${period}/close`, {}, auth()), 'месяц закрыт')
                }
              }}
              style={{ height: 34, padding: '0 15px', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 700, fontFamily: 'inherit', whiteSpace: 'nowrap',
                background: noRule ? 'var(--text-disabled)' : 'var(--accent)', color: 'var(--on-accent)', cursor: noRule ? 'not-allowed' : 'pointer' }}>Закрыть месяц</button>)}
          {!!month && month.closed && isAdmin && (
            <button type="button" disabled={busy} onClick={() => {
              if (window.confirm(`Открыть ${periodLabel(period)} заново? Снимок снимется, расчёт пойдёт по текущим правилам.`)) {
                act(() => api.delete(`/agency-terms/months/${period}`, auth()), 'месяц открыт заново')
              }
            }} style={{ height: 34, padding: '0 14px', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, fontSize: 12.5,
              fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit' }}>Открыть заново</button>)}
          <button type="button" title="Выгрузить в Excel — расчёт и «не закрыты»" onClick={() => downloadFile(`/agency-terms/calc.xlsx?${query()}`, `СК ${period}.xlsx`, setMsg)}
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 34, height: 34, boxSizing: 'border-box',
              border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14" /></svg>
          </button>
        </span>
      </div>
      {!!msg && <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{msg}</div>}
      {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
      {data && <>
        <KpiStrip size={26} min={260} items={[
          ['База ДС без НДС', rub2(t.base_net), 'var(--text-primary)', `${data.rows.length} закрытых сделок`],
          ['СК · постоплата', rub2(t.by_mode['постоплата'] || 0), 'var(--violet-fg)', 'выплата агентству после оплаты'],
          ['СК · скидка в счёт', rub2(t.by_mode['скидка в счёт'] || 0), 'var(--accent-fg)', 'уменьшает сумму ДС'],
        ]} />
        {noRule > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '10px 14px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
            borderRadius: 12, fontSize: 12.5, color: 'var(--warning-fg)' }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--warning)', flex: '0 0 7px' }} />
            <span style={{ flex: '1 1 auto', minWidth: 0, lineHeight: 1.4 }}>Сделок без условия СК: {noRule}
              {noContract ? ` (без договора закрытия — ${noContract}, у остальных нет условия к договору)` : ' — у их договоров нет условия'}. Месяц с ними не закрыть; строки подсвечены.</span>
            <span onClick={onGoEmpty} style={{ marginLeft: 'auto', fontWeight: 700, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap' }}>задать условия →</span>
          </span>)}
        <Card title={<Title>Закрытые сделки · {periodLabel(period)}</Title>}
          right={<><MiniSeg subtle h={26} value={by} opts={[['agency', 'по агентству'], ['pack', 'по мастер-сделке']]} onPick={setBy} />
            <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
              мастер-сделка в «ждём 1С» и дальше · база — ДС без НДС до вычета скидки в счёт</span></>}>
          <Scroll min={1200}>
            <div style={{ display: 'grid', gridTemplateColumns: CCOLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
              <span>Сделка</span><span>Договор · юрлицо</span><span>{by === 'pack' ? '' : 'Пакет'}</span><span style={{ textAlign: 'right' }}>База без НДС</span>
              <span>Способ</span><span style={{ textAlign: 'right' }}>%</span><span style={{ textAlign: 'right' }}>СК</span>
            </div>
            {rows.map((r) => <CalcRow key={r.key} r={r} onOpenRule={openRule} />)}
            {!!data.rows.length && (
              <div style={{ display: 'grid', gridTemplateColumns: CCOLS, gap: 14, padding: '10px 10px 2px', fontWeight: 700 }}>
                <span style={CAPS}>Итого · {data.rows.length}</span><span /><span />
                <span style={{ ...NUM, fontSize: 12.5 }}>{rub2(t.base_net)}</span><span /><span />
                <span style={{ ...NUM, fontSize: 12.5 }}>{rub2(Object.values(t.by_mode).reduce((a, v) => a + v, 0))}</span>
              </div>)}
          </Scroll>
          {!data.rows.length && <span style={{ padding: '22px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
            Закрытых сделок за {periodLabel(period)} нет — сделка попадает в расчёт, когда её мастер-сделка прошла согласования в ДО.</span>}
        </Card>
        {!!data.open.length && (
          <Card title={<><span style={{ fontSize: 14, fontWeight: 700 }}>Не закрыты — в итог не входят</span>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--text-faint)' }}>{data.open.length}</span></>}
            right={<span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>оценка по сумме сделки и текущему правилу</span>}>
            <Scroll min={640}>
              <div style={{ display: 'grid', gridTemplateColumns: OCOLS, gap: 14, padding: '0 4px 6px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
                <span>Сделка</span><span>Агентство · юрлицо</span><span>Пакет</span><span style={{ textAlign: 'right' }}>Сумма</span><span>Правило</span>
              </div>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                {data.open.map((o) => { const gap = skGap(o); return (
                  <div key={`${o.deal_id}:${o.period}`} style={{ display: 'grid', gridTemplateColumns: OCOLS, gap: 14, alignItems: 'center', padding: '6px 4px',
                    borderBottom: '1px solid var(--border-row)', ...(gap ? { background: GAP_BG, boxShadow: GAP_EDGE } : {}) }}>
                    <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>{o.code}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.side} · {o.entity}</span>
                    <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{o.master_code || 'не в пакете'}</span>
                    <span style={NUM}>{rub2(o.estimate_net)}</span>
                    {gap ? <GapNote row={o} gap={gap} onOpenRule={openRule} /> : (
                      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
                        {`${o.mode === 'скидка в счёт' ? 'скидка' : o.mode} ${fmtPct(o.percent)}`}</span>)}
                  </div>) })}
              </div>
            </Scroll>
          </Card>)}
      </>}
    </>
  )
}
