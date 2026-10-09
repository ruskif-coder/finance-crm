import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { MONO, UI, card } from '@/components/salesTableKit'
import AudienceMap from '@/components/publishers/AudienceMap'
import AudienceCard from '@/components/publishers/AudienceCard'
import AudienceMeasureModal from '@/components/publishers/AudienceMeasureModal'
import AudienceSummary from '@/components/publishers/AudienceSummary'
import AudienceData from '@/components/publishers/AudienceData'
import { ACTIVE, dataOf, gapText, gapTone, surfacesOf } from '@/components/publishers/audienceKit'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { shortNum, pct } from '@/lib/salesFormat'

// Паблишеры → «Аудитория» (владелец 09.10.2026, визуал — макет Claude Design): заявленное
// площадкой (MAU/DAU/соцдем из медиакитов, с источником и датой) рядом с тем, что намерили мы
// за окно. Право dir_publishers_audience: view — экран, edit — внесение замеров. Мобильной
// версии нет намеренно: экран аналитический, широкая таблица на телефоне не читается.

const WINDOWS = [7, 30, 90]
const COLS = 'minmax(150px, 1.3fr) 90px 100px 72px 100px 96px 110px 90px 70px 64px 150px'
const capMono = (extra) => ({ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)', ...extra })
const num = (v) => (v == null ? -1 : v)
const DASH = 'var(--text-disabled)'

// сегмент-кнопки: контейнер 3px, кнопка 26px радиус 8 — как в «Согласованиях»
const Seg = ({ options, value, onPick, mono }) => (
  <span style={{ display: 'inline-flex', padding: 3, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
    {options.map(([k, label]) => {
      const on = value === k
      return (
        <span key={k} onClick={() => onPick(k)} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 12px', borderRadius: 8,
          background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-secondary)',
          fontFamily: mono ? MONO : UI, fontSize: mono ? 11.5 : 12, fontWeight: on ? 700 : 600, cursor: 'pointer', transition: 'background-color 150ms ease', whiteSpace: 'nowrap' }}>{label}</span>
      )
    })}
  </span>
)

export default function PublisherAudience() {
  const router = useRouter()
  const [ready, setReady] = useState(false)
  const [canEdit, setCanEdit] = useState(false)
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [onlyData, setOnlyData] = useState(false)
  const [onlyActive, setOnlyActive] = useState(true)   // «активные / все» (владелец 09.10.2026)
  const [sort, setSort] = useState({ key: 'uniques', dir: 'desc' })
  const [selId, setSelId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [sources, setSources] = useState([])
  const [modal, setModal] = useState(false)
  const [tab, setTab] = useState('analytics')   // analytics | data
  const [grid, setGrid] = useState(null)

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    let p = {}
    try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch { p = {} }
    if (!can(p, 'dir_publishers_audience', 'view')) {
      router.push(firstAllowedHref(p, localStorage.getItem('is_admin') === '1')); return
    }
    setCanEdit(can(p, 'dir_publishers_audience', 'edit'))
    setReady(true)
  }, [router])

  const load = useCallback(() => {
    api.get(`/publisher-audience?days=${days}`, auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить аудиторию'))
  }, [days])
  const loadDetail = useCallback((id) => {
    if (!id) { setDetail(null); return }
    api.get(`/publisher-audience/${id}?days=${days}`, auth()).then(r => setDetail(r.data))
      .catch(e => { setDetail(null); setErr(e?.response?.data?.detail || 'Не удалось загрузить карточку площадки') })
  }, [days])
  const loadGrid = useCallback(() => {
    api.get('/publisher-audience/grid', auth()).then(r => setGrid(r.data))
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить сетку заполнения'))
  }, [])
  useEffect(() => { if (ready) load() }, [ready, load])
  useEffect(() => { if (ready && tab === 'data') loadGrid() }, [ready, tab, loadGrid])
  useEffect(() => { if (ready) loadDetail(selId) }, [ready, selId, loadDetail])
  useEffect(() => { if (ready) api.get('/publisher-audience/sources', auth()).then(r => setSources(r.data)).catch(() => {}) }, [ready, data])
  useRefreshOnReturn(load)

  // набор по «Активные / Все» — общий для плиток, карты и таблицы
  const scoped = useMemo(() => (data?.publishers || []).filter(p => !onlyActive || p.status === ACTIVE), [data, onlyActive])
  const kinds = useMemo(() => [...new Set(scoped.map(p => p.kind).filter(Boolean))].sort(), [scoped])
  const maxShows = useMemo(() => Math.max(1, ...scoped.map(p => p.measured.shows || 0)), [scoped])
  const rows = useMemo(() => {
    let ps = scoped
    const s = q.trim().toLowerCase()
    if (s) ps = ps.filter(p => `${p.name} ${p.domain} ${p.network || ''}`.toLowerCase().includes(s))
    if (kind) ps = ps.filter(p => p.kind === kind)
    if (onlyData) ps = ps.filter(p => p.declared.mau && p.measured.shows)
    const k = sort.dir === 'asc' ? 1 : -1
    const val = (p) => ({
      name: p.name, kind: p.kind || '', mau: num(p.declared.mau?.value), stickiness: num(p.stickiness), uniques: num(p.measured.uniques),
      gap: num(p.gap_pct), shows: num(p.measured.shows), ver: num(p.measured.verifier_shows), fill: num(p.measured.fill_pct),
      ctr: num(p.measured.ctr_pct), data: dataOf(p)[0],
    })[sort.key]
    return [...ps].sort((a, b) => {
      const x = val(a), y = val(b)
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * k || (num(b.measured.shows) - num(a.measured.shows))
    })
  }, [scoped, q, kind, onlyData, sort])
  const onSort = (key) => setSort(s => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' || key === 'kind' ? 'asc' : 'desc' }))

  const saveMeasure = async (payload) => {
    await api.post(`/publisher-audience/${selId}/measures`, payload, auth())
    setModal(false); load(); loadDetail(selId)
  }
  const delMeasure = async (h) => {
    if (!window.confirm(`Удалить замер ${h.source} от ${h.measured_at}?`)) return
    await api.delete(`/publisher-audience/measures/${h.id}`, auth())
    load(); loadDetail(selId)
  }

  const kpis = useMemo(() => {
    const withD = scoped.filter(p => p.declared.mau), withM = scoped.filter(p => p.measured.shows != null)
    const sum = (arr, f) => arr.reduce((a, p) => a + (f(p) || 0), 0)
    const st = scoped.map(p => p.stickiness).filter(v => v != null)
    return [
      ['площадок с данными', `${scoped.filter(p => dataOf(p)[0] !== 'нет данных').length} / ${scoped.length}`, `${withD.length} с заявленными · ${withM.length} с нашими${onlyActive ? ' · активные' : ''}`],
      ['заявленный MAU, сумма', shortNum(sum(withD, p => p.declared.mau.value) || null), 'последний замер по площадке'],
      [`уники под рекламой, ${days} дн.`, shortNum(sum(scoped, p => p.measured.uniques) || null), 'Adfox, сумма суток — верхняя оценка', 'var(--income-fg)'],
      [`показы, ${days} дн.`, shortNum(sum(scoped, p => p.measured.shows) || null), 'наш счётчик, без верификатора'],
      ['средний DAU/MAU', st.length ? (st.reduce((a, b) => a + b, 0) / st.length).toFixed(2) : '—', 'по площадкам с MAU и DAU'],
    ]
  }, [scoped, days, onlyActive])

  if (!ready) return null
  const heads = [['name', 'Площадка', 'flex-start'], ['kind', 'Вид', 'flex-start'], ['mau', 'MAU заяв.', 'flex-end'], ['stickiness', 'DAU/MAU', 'flex-end'],
    ['uniques', `Уники ${days} дн.`, 'flex-end'], ['gap', 'Разрыв', 'center'], ['shows', 'Показы', 'flex-end'], ['ver', 'Вериф.', 'flex-end'],
    ['fill', 'Fill DSP', 'flex-end'], ['ctr', 'CTR', 'flex-end'], ['data', 'Данные', 'flex-start']]
  const mono = (extra) => ({ fontFamily: MONO, ...extra })
  return (
    <>
      <Head><title>Аудитория · Паблишеры | SIMB-AD ERP</title></Head>
      <Navbar active="publishers" />
      <div style={{ minHeight: 'calc(100vh - var(--navbar-h))', background: 'var(--bg-canvas)', fontFamily: UI, padding: '22px 28px 40px', boxSizing: 'border-box' }}>
        <div style={{ maxWidth: 1600, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-.025em' }}>Паблишеры</h1>
            <span style={capMono({ fontSize: 10, paddingTop: 2 })}>аудитория · заявлено площадкой / подтверждено нами</span>
            <Seg options={[['analytics', 'Аналитика'], ['data', 'Данные · заполнение']]} value={tab} onPick={setTab} />
            {tab === 'analytics' && (
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <span style={capMono()}>окно</span>
                <Seg mono options={WINDOWS.map(d => [d, `${d} дн.`])} value={days} onPick={setDays} />
              </span>
            )}
          </div>

          {tab === 'analytics' && !!kpis.length && data && (
            <div style={{ ...card, padding: '2px 24px', display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
              {kpis.map(([label, value, hint, color], i) => (
                <div key={label} style={{ padding: '16px 22px 16px 0', marginRight: 22, display: 'flex', flexDirection: 'column', gap: 7, minWidth: 0,
                  borderRight: i < kpis.length - 1 ? '1px solid var(--border-inner)' : '1px solid transparent' }}>
                  <span style={capMono({ fontSize: 9.5 })}>{label}</span>
                  <span style={mono({ fontSize: 28, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1, whiteSpace: 'nowrap', color: color || 'var(--text-primary)' })}>{value}</span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.35 }}>{hint}</span>
                </div>
              ))}
            </div>
          )}

          {/* обе карточки одной высоты: карта фиксирована (330px), карточка площадки её не растягивает */}
          {tab === 'analytics' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 14, alignItems: 'stretch' }}>
            <div style={{ ...card, padding: '18px 22px 16px', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              {data && <AudienceMap publishers={scoped} selectedId={selId} onSelect={setSelId} />}
            </div>
            <div style={{ ...card, padding: '18px 22px 16px', minWidth: 0 }}>
              {selId && detail ? (
                <>
                  <span onClick={() => setSelId(null)} style={{ display: 'inline-block', marginBottom: 10, fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>← Сводная по всем площадкам</span>
                  <AudienceCard p={detail} metrics={data?.metrics} days={days} canEdit={canEdit} onAdd={() => setModal(true)} onDelete={delMeasure} />
                </>
              ) : data ? (
                <AudienceSummary publishers={scoped} days={days} onSelect={setSelId} />
              ) : null}
            </div>
          </div>
          )}

          {tab === 'data' && (
            grid ? <AudienceData grid={grid} sources={sources} canEdit={canEdit} onSaved={() => { loadGrid(); load() }} />
              : <div style={{ ...card, padding: 30, color: 'var(--text-muted)' }}>{err || 'Загрузка…'}</div>
          )}

          {tab === 'analytics' && (
          <div style={{ ...card, padding: '16px 22px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 12px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, minWidth: 220 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="1.9" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" /></svg>
                <input value={q} onChange={e => setQ(e.target.value)} placeholder="Площадка, домен, сеть…"
                  style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)' }} />
              </span>
              <Seg options={[['', 'Все виды'], ...kinds.map(k => [k, k])]} value={kind} onPick={setKind} />
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
                <Seg options={[[true, 'Активные'], [false, 'Все']]} value={onlyActive} onPick={setOnlyActive} />
                <span onClick={() => setOnlyData(v => !v)} style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 12px', borderRadius: 10, cursor: 'pointer',
                  background: onlyData ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${onlyData ? 'var(--accent-border)' : 'var(--border-card)'}`,
                  color: onlyData ? 'var(--accent)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600 }}>Только с данными</span>
              </span>
            </div>

            {!!err && <div style={{ padding: 12, color: 'var(--danger-fg)' }}>{err}</div>}
            {!data && !err && <div style={{ padding: 30, color: 'var(--text-muted)' }}>Загрузка…</div>}
            {data && (
              <div style={{ overflowX: 'auto' }}>
                <div style={{ minWidth: 1240 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '6px 10px 8px', borderBottom: '1px solid var(--border-card)' }}>
                    {heads.map(([key, label, justify]) => {
                      const on = sort.key === key
                      return (
                        <span key={key} onClick={() => onSort(key)} style={{ display: 'flex', justifyContent: justify, gap: 4, ...capMono({ color: on ? 'var(--accent)' : 'var(--text-cap)' }), cursor: 'pointer', userSelect: 'none' }}>
                          {label}<span style={{ fontSize: 8 }}>{on ? (sort.dir === 'asc' ? '▲' : '▼') : ''}</span>
                        </span>
                      )
                    })}
                  </div>
                  {rows.map(p => {
                    const on = p.id === selId, [dl, dBg, dFg, dBd, dDot] = dataOf(p), [gBg, gFg] = gapTone(p.gap_pct), m = p.measured
                    const mau = p.declared.mau
                    return (
                      <div key={p.id} onClick={() => setSelId(p.id)} className="aud-row"
                        style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', padding: '7px 10px', borderBottom: '1px solid var(--border-row)', borderRadius: 8,
                          background: on ? 'var(--accent-tint)' : undefined, cursor: 'pointer' }}>
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                          <span style={{ fontSize: 12.5, fontWeight: on ? 800 : 600, color: on ? 'var(--accent-fg)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                          <span style={mono({ fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)' })}>{surfacesOf(p) || p.domain}</span>
                        </span>
                        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{p.kind || '—'}</span>
                        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                          <span style={mono({ fontSize: 12, fontWeight: 600, color: mau ? 'var(--text-primary)' : DASH })}>{shortNum(mau?.value)}</span>
                          <span style={mono({ fontSize: 8.5, color: 'var(--text-faint)' })}>{mau ? mau.source : ''}</span>
                        </span>
                        <span style={mono({ fontSize: 12, textAlign: 'right', color: p.stickiness != null ? 'var(--text-secondary)' : DASH })}>{p.stickiness != null ? p.stickiness.toFixed(2) : '—'}</span>
                        <span style={mono({ fontSize: 12, fontWeight: 700, textAlign: 'right', color: m.uniques != null ? 'var(--text-primary)' : DASH })}>{shortNum(m.uniques)}</span>
                        <span style={{ display: 'flex', justifyContent: 'center' }}>
                          <span style={mono({ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 52, padding: '3px 8px', borderRadius: 7, background: gBg, color: gFg, fontSize: 10.5, fontWeight: 700 })}>{gapText(p)}</span>
                        </span>
                        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                          <span style={mono({ fontSize: 12, fontWeight: 600, color: m.shows ? 'var(--text-primary)' : DASH })}>{m.shows ? shortNum(m.shows) : '—'}</span>
                          <span style={{ width: 60, height: 3, background: 'var(--border-inner)', borderRadius: 2, overflow: 'hidden' }}>
                            <span style={{ display: 'block', height: '100%', width: `${((m.shows || 0) / maxShows) * 100}%`, background: 'var(--accent-soft)' }} />
                          </span>
                        </span>
                        <span style={mono({ fontSize: 11.5, textAlign: 'right', color: 'var(--text-muted)' })}>{m.verifier_shows != null ? shortNum(m.verifier_shows) : '—'}</span>
                        <span style={mono({ fontSize: 11.5, textAlign: 'right', color: m.fill_pct != null ? 'var(--text-secondary)' : DASH })}>{m.fill_pct != null ? pct(m.fill_pct) : '—'}</span>
                        <span style={mono({ fontSize: 11.5, textAlign: 'right', color: m.shows ? 'var(--text-secondary)' : DASH })}>{m.shows ? pct(m.ctr_pct) : '—'}</span>
                        <span style={{ display: 'flex', justifyContent: 'flex-start' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 7, background: dBg, color: dFg, border: `1px solid ${dBd}`, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap' }}>
                            <span style={{ width: 6, height: 6, borderRadius: 2, background: dDot }} />{dl}
                          </span>
                        </span>
                      </div>
                    )
                  })}
                  {!rows.length && <div style={{ padding: 28, textAlign: 'center', fontSize: 12.5, color: 'var(--text-faint)' }}>Ничего не найдено по фильтрам</div>}
                </div>
              </div>
            )}
            <span style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.45 }}>
              Разрыв — уники под рекламой ÷ заявленный MAU: красным меньше 10 %, жёлтым меньше 25 %. Уники — отчёт Adfox, сумма по суткам (верхняя оценка; DSP уников не отдаёт).
              Показы — наш счётчик; верификатор (Weborama) рядом, в сумму не входит. Fill — показы DSP ÷ предложено DSP. Показано {rows.length} из {scoped.length}.
            </span>
          </div>
          )}
        </div>
        <style>{'.aud-row:hover{background:var(--bg-subtle)}'}</style>
      </div>
      {modal && detail && tab === 'analytics' && <AudienceMeasureModal publisher={detail} metrics={data.metrics} sources={sources} onSave={saveMeasure} onClose={() => setModal(false)} />}
    </>
  )
}
