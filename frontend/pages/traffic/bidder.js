// «Трафики → Биддер» (владелец 05.10.2026): правила раскладки объёма РК по площадкам и
// раскладка выбранной РК — почему у площадки такой план. Расчёт — backend app/bidder и
// build.campaign_layout (тот же, что у ночного пересчёта): страница объясняет ровно то
// число, которое уходит в DSP. Право — bidder (пока только владелец). Только десктоп.
// План на экране — записанный ночью (= лимиты в DSP); расчёт по правилам сейчас — рядом,
// если разошёлся. Журнал ночных прогонов — bidder_run / bidder_run_change.
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import { MONO, UI, card, inp, th, td } from '@/components/salesTableKit'
import { grp, grpDash } from '@/lib/salesFormat'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const ru = (d) => (d ? String(d).split('-').reverse().join('.') : '—')

// Цвет пометки «откуда план» — переменные темы, не хексы.
const REASON_TONE = {
  settled: 'var(--warning-text)',
  floored: 'var(--warning-text)',
  capped: 'var(--text-secondary)',
  fixed: 'var(--income)',
  weight: 'var(--text-primary)',
  no_weight: 'var(--text-faint)',
  out: 'var(--text-faint)',
}

function Part({ label, value, hint }) {
  return (
    <div style={{ minWidth: 150 }}>
      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{label}</div>
      <div style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
      {!!hint && <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{hint}</div>}
    </div>
  )
}

const dt = (v) => (v ? v.split(' ').map((x, i) => (i ? x : ru(x))).join(' ') : '—')   // уже МСК с сервера
const STATE_TONE = { 'ок': 'var(--income)', 'идёт': 'var(--text-secondary)', 'предупреждения': 'var(--warning-text)',
  'ошибки': 'var(--expense)', 'оборвался': 'var(--expense)' }
const LEVEL_TONE = { error: 'var(--expense)', warning: 'var(--warning-text)' }
// Раскрыть можно любой закрытый прогон: в нём есть разбор и проверки (06.10.2026).
const canOpen = (r) => r.state !== 'идёт'

// Разбор по причинам и проверки прогона — над списком изменений площадок.
function RunDetails({ r, det }) {
  const checks = det ? det.checks : (r.checks || [])
  return (
    <tr style={{ background: 'var(--bg-subtle)' }}>
      <td style={{ ...td, paddingLeft: 28 }} colSpan={6}>
        {!!det && !!det.summary.length && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 4 }}>Что поменялось</div>
            {det.summary.map((s, i) => <div key={i} style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>· {s}</div>)}
          </div>
        )}
        <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 4 }}>Проверки</div>
        {r.checks == null && <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>прогон до 06.10.2026 — проверок тогда не было</div>}
        {r.checks != null && !checks.length && <div style={{ fontSize: 12.5, color: 'var(--income)' }}>все проверки пройдены</div>}
        {checks.map(c => (
          <div key={c.code} style={{ fontSize: 12.5, marginBottom: 4 }}>
            <span style={{ color: LEVEL_TONE[c.level], fontWeight: 700 }}>{c.level === 'error' ? 'ошибка' : 'предупреждение'}</span>
            {' · '}{c.title}: {c.count}
            {c.examples.map((e, i) => <div key={i} style={{ paddingLeft: 14, fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{e}</div>)}
          </div>
        ))}
      </td>
    </tr>
  )
}

function RunRow({ r, open, onToggle, det }) {
  const changes = det ? det.changes : null
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: canOpen(r) ? 'pointer' : 'default' }}>
        <td style={{ ...td, fontFamily: MONO }}>{canOpen(r) ? (open ? '▾ ' : '▸ ') : ''}{dt(r.started_msk)} МСК</td>
        <td style={{ ...td, color: STATE_TONE[r.state] }}>
          {r.state}{r.limits_failed > 0 ? ` · лимитов не ушло: ${r.limits_failed}` : ''}
        </td>
        <td style={td}>{r.by_fact ? `по ${ru(r.fact_as_of)}` : 'нет — по весам'}</td>
        <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grp(r.campaigns)}</td>
        <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grp(r.plans_changed)}</td>
        <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grp(r.limits_updated)}</td>
      </tr>
      {open && <RunDetails r={r} det={det} />}
      {open && (r.errors || []).map((e, i) => (
        <tr key={`e${i}`} style={{ background: 'var(--bg-subtle)' }}>
          <td style={{ ...td, paddingLeft: 28, color: 'var(--expense)' }} colSpan={6}>
            {e.creative_id ? `креатив ${e.creative_id}: ` : ''}{e.error || JSON.stringify(e)}
          </td>
        </tr>
      ))}
      {open && (changes || []).map((c, i) => (
        <tr key={i} style={{ background: 'var(--bg-subtle)' }}>
          <td style={{ ...td, paddingLeft: 28, fontFamily: MONO }}>{c.code}</td>
          <td style={{ ...td, fontFamily: MONO }} colSpan={2}>{c.site || c.placement_id}</td>
          <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grpDash(c.plan_before)}</td>
          <td style={{ ...td, textAlign: 'right', fontFamily: MONO, fontWeight: 700 }}>{grpDash(c.plan_after)}</td>
          <td style={{ ...td, color: REASON_TONE[c.reason] }}>{c.reason_label}</td>
        </tr>
      ))}
      {open && !det && <tr><td style={td} colSpan={6}>Загрузка…</td></tr>}
    </>
  )
}

const Op = ({ c }) => <div style={{ fontFamily: MONO, fontSize: 20, color: 'var(--text-faint)', alignSelf: 'center' }}>{c}</div>

export default function BidderPage() {
  const [info, setInfo] = useState(null)
  const [camps, setCamps] = useState([])
  const [cid, setCid] = useState('')
  const [lay, setLay] = useState(null)
  const [err, setErr] = useState('')
  const [runs, setRuns] = useState([])
  const [openRun, setOpenRun] = useState(null)
  const [runChanges, setRunChanges] = useState({})

  const load = useCallback(async () => {
    try {
      const [a, b, c] = await Promise.all([api.get('/bidder', auth()), api.get('/bidder/campaigns', auth()),
        api.get('/bidder/runs', auth())])
      setInfo(a.data)
      setCamps(b.data)
      setRuns(c.data)
      setErr('')
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить биддер') }
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  useEffect(() => {
    if (!cid) { setLay(null); return }
    let alive = true
    api.get(`/bidder/layout/${cid}`, auth())
      .then(r => { if (alive) { setLay(r.data); setErr('') } })
      .catch(e => { if (alive) setErr(e?.response?.data?.detail || 'Не удалось загрузить раскладку') })
    return () => { alive = false }
  }, [cid])

  const toggleRun = (r) => {
    if (!canOpen(r)) return
    if (openRun === r.id) { setOpenRun(null); return }
    setOpenRun(r.id)
    if (!runChanges[r.id]) {
      api.get(`/bidder/runs/${r.id}`, auth())
        .then(x => setRunChanges(m => ({ ...m, [r.id]: x.data })))
        .catch(e => {
          // Без этого «Загрузка…» висела бы до перезагрузки страницы (ревью 06.10.2026).
          setErr(e?.response?.data?.detail || 'Не удалось загрузить изменения прогона')
          setOpenRun(null)
        })
    }
  }

  return (
    <>
      <Head><title>Биддер · Трафики | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '18px 24px 60px', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>Биддер</h1>
          <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
            раскладка объёма РК по площадкам · пересчёт {info?.cron || '…'}
          </span>
        </div>
        {!!err && <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--expense)' }}>{err}</div>}

        {!!info && (
          <div style={{ ...card, padding: 16, marginBottom: 14, display: 'flex', gap: 28, flexWrap: 'wrap' }}>
            <Part label="Факт по" value={ru(info.fact_as_of)}
              hint={info.stale ? 'статистика устарела — раскладка по весам' : 'учитывается в раскладке'} />
            <Part label="Потолок доли" value={info.cap_pct != null ? `${String(info.cap_pct).replace('.', ',')} %` : 'нет'} hint="правится в балансировщике" />
            <Part label="Удержание долей" value={`${info.hold_days} дн.`} hint="с начала РК, факт не учитывается" />
          </div>
        )}

        {!!info && (
          <div style={{ ...card, padding: 16, marginBottom: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 10, color: 'var(--text-primary)' }}>Правила</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 10 }}>
              {info.rules.map(r => (
                <div key={r.title} style={{ border: '1px solid var(--border-row)', borderRadius: 12, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>{r.title}</span>
                    <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>с {r.since}</span>
                  </div>
                  <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.45 }}>{r.text}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ ...card, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>Раскладка РК</div>
            <select style={{ ...inp, cursor: 'pointer', minWidth: 360 }} value={cid} onChange={e => setCid(e.target.value)}>
              <option value="">— выберите РК —</option>
              {[['Запущены — крутится хотя бы одна площадка', camps.filter(c => c.running > 0)],
                ['Не запущены', camps.filter(c => !c.running)]].map(([label, list]) => !!list.length && (
                <optgroup key={label} label={label}>
                  {list.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.running > 0 ? `▶ ${c.running} пл. · ` : ''}{c.code || c.id} · {c.title} · {ru(c.date_start)}–{ru(c.date_end)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {!!lay && (
            <>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 6 }}>
                <Part label="План РК" value={grp(lay.plan_show)} hint="разложение по правилам сейчас" />
                <Op c="=" />
                <Part label="Заданные объёмы" value={grp(lay.totals.fixed)} />
                <Op c="+" />
                <Part label="Выбывшие по факту" value={grp(lay.totals.settled)} />
                <Op c="+" />
                <Part label="По весам" value={grp(lay.totals.by_weight)} />
              </div>
              {lay.over > 0 && (
                <div style={{ fontSize: 12.5, color: 'var(--warning-text)', fontWeight: 600, marginBottom: 4 }}>
                  Сумма планов площадок больше плана РК на {grp(lay.over)}: открученное уже превышает план или это округление по площадкам.
                </div>
              )}
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
                {lay.facts_used ? 'Факт площадок учтён.' : 'Факт не учтён: первые дни РК или статистика за вчера не пришла — раскладка по весам.'}
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={th}>Площадка</th>
                    <th style={th}>Статус</th>
                    <th style={{ ...th, textAlign: 'right' }}>Вес</th>
                    <th style={{ ...th, textAlign: 'right' }}>Доля</th>
                    <th style={{ ...th, textAlign: 'right' }}>План в DSP</th>
                    <th style={{ ...th, textAlign: 'right' }} title="расчёт по правилам на текущих данных; ночью факт будет на день новее">По правилам сейчас</th>
                    <th style={{ ...th, textAlign: 'right' }}>Факт</th>
                    <th style={th}>Откуда план</th>
                  </tr>
                </thead>
                <tbody>
                  {lay.rows.map(r => (
                    <tr key={r.id}>
                      <td style={{ ...td, fontFamily: MONO }}>{r.site || r.id}</td>
                      <td style={td}>{r.status}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grpDash(r.weight)}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{r.share ? `${(r.share * 100).toFixed(1).replace('.', ',')} %` : '—'}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: MONO, fontWeight: 700 }}>{grpDash(r.plan_stored)}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: MONO, color: r.changes_tonight ? 'var(--warning-text)' : 'var(--text-faint)' }}>
                        {r.changes_tonight ? grpDash(r.plan_show) : 'без изменений'}
                      </td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grp(r.fact)}</td>
                      <td style={{ ...td, color: REASON_TONE[r.reason], fontWeight: 600 }}>{r.reason_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        <div style={{ ...card, padding: 16, marginTop: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 10, color: 'var(--text-primary)' }}>Журнал ночных прогонов</div>
          {!runs.length ? (
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Прогонов ещё не было — журнал ведётся с 05.10.2026.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={th}>Начало</th>
                  <th style={th}>Итог</th>
                  <th style={th}>Факт</th>
                  <th style={{ ...th, textAlign: 'right' }}>РК / план до</th>
                  <th style={{ ...th, textAlign: 'right' }}>Планов изменено / после</th>
                  <th style={{ ...th, textAlign: 'right' }}>Лимитов в DSP / причина</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <RunRow key={r.id} r={r} open={openRun === r.id} onToggle={() => toggleRun(r)} det={runChanges[r.id]} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
