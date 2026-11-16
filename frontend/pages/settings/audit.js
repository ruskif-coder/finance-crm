import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '../../components/Navbar'
import { isAdmin } from '../../lib/auth'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { MONO, UI, LoadError, PAGE_W } from '../../components/salesTableKit'
import { errText, isAuth } from '@/lib/loadError'
import useLatest from '@/lib/useLatest'
import api, { auth } from '../../lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { downloadFile } from '@/lib/download'
import { COLS, OneRow, GroupRow } from '@/components/settings/journal/JournalRow'
import WhoPicker from '@/components/settings/journal/WhoPicker'
import { daysOf, periodDates, plural } from '@/components/settings/journal/journalModel'

// ── Журнал действий — раздел «Настройки» (макет design_handoff_journal, 16.11.2026) ──
// Только чтение. Контур (сотрудники / кабинеты паблишеров / все), разделы пинами и действия выбранного раздела второй
// строкой, повторы свёрнуты в «× N», лента по дням. Фильтры и счётчики считает сервер (`/api/journal`). Выгрузка в
// Excel — всё найденное по фильтрам, только администратор (решение 16.11.2026). Содержимое — под 1600 (владелец 16.11).

const PAGE = 200
// Действий в разделе на бою десятки (в «Аккаунтах» — 74): строка пинов разворачивалась в стену и уводила ленту вниз.
// Видны самые частые, остальные — по «ещё N»; выбранное действие видно всегда.
const ACTIONS_SHOWN = 12
const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
const pin = (on, h = 28) => ({ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: h, padding: h === 28 ? '0 10px' : '0 9px',
  borderRadius: h === 28 ? 9 : 7, fontSize: h === 28 ? 12 : 11.5, whiteSpace: 'nowrap', background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
  border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`, color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600 })
const Num = ({ n, s = 10 }) => <span style={{ fontFamily: MONO, fontSize: s, color: 'var(--text-faint)' }}>{n}</span>
const PERIODS = [['all', 'Всё время'], ['today', 'Сегодня'], ['7', '7 дней'], ['30', '30 дней'], ['range', 'Период']]
const CONTOURS = [['staff', 'Сотрудники'], ['cabinet', 'Кабинеты паблишеров'], ['all', 'Все']]
const EMPTY = { q: '', period: 'all', from: '', to: '', actor: '', section: '', action: '' }
const dateField = { width: 84, height: 28, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 9, fontFamily: MONO, fontSize: 11.5, outline: 'none', color: 'var(--text-primary)' }

export default function SettingsAudit() {
  const router = useRouter()
  const [contour, setContour] = useState('staff')
  const [f, setF] = useState(EMPTY)
  const [qDebounced, setQDebounced] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [facets, setFacets] = useState(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState({})
  const [whoOpen, setWhoOpen] = useState(false)
  const [allActions, setAllActions] = useState(false)
  const [xls, setXls] = useState('')         // '' | 'run' | 'done'
  const [xlsErr, setXlsErr] = useState('')
  const [admin, setAdmin] = useState(false)
  const latest = useLatest()
  const timer = useRef(null)

  const params = (offset) => {
    const pd = periodDates(f.period, f.from, f.to)
    return { contour, q: qDebounced || undefined, actor: f.actor || undefined, section: f.section || undefined, action: f.action || undefined,
      ...pd, offset, limit: PAGE }
  }

  const load = async (offset = 0) => {
    setLoading(true); setErr('')
    const fresh = latest()
    try {
      const res = await api.get('/journal/', { ...auth(), params: params(offset) })
      if (!fresh()) return
      setItems(prev => (offset ? [...prev, ...res.data.items] : res.data.items))
      setTotal(res.data.total); setFacets(res.data.facets); setHasMore(res.data.has_more)
      if (!offset) setOpen({})
    } catch (e) {
      if (!fresh()) return
      if (isAuth(e)) { router.push('/login'); return }
      setItems([]); setTotal(0); setErr(errText(e))
    } finally { if (fresh()) setLoading(false) }
  }

  useRefreshOnReturn(() => load(0))
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('audit')) { let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}; router.push(firstAllowedHref(p, isAdmin())); return }
    setAdmin(isAdmin())
    const outside = (e) => { if (!e.target.closest?.('[data-pop-root]')) setWhoOpen(false) }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [])
  useEffect(() => { clearTimeout(timer.current); timer.current = setTimeout(() => setQDebounced(f.q.trim()), 300); return () => clearTimeout(timer.current) }, [f.q])
  // Смена фильтра — первая страница заново. `load` берётся через ref: эффект зависит только от фильтров.
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => { loadRef.current(0) }, [contour, qDebounced, f.period, f.from, f.to, f.actor, f.section, f.action])

  const pickContour = (c) => { setContour(c); setF(prev => ({ ...prev, actor: '', section: '', action: '' })) }
  const filtered = !!(f.q || f.period !== 'all' || f.actor || f.section || f.action)

  const exportXls = async () => {
    if (!total || xls === 'run') return
    setXls('run'); setXlsErr('')
    const p = params(0); delete p.offset; delete p.limit
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== '')).toString()
    const ok = await downloadFile(`/journal/export?${qs}`, undefined, (msg) => setXlsErr(msg))
    setXls(ok ? 'done' : '')
    if (ok) setTimeout(() => setXls(''), 2000)
  }

  const sections = Object.fromEntries((facets?.section_list || []).map(s => [s.id, s]))
  const secCounts = facets?.sections || {}
  const secAll = Object.values(secCounts).reduce((a, b) => a + b, 0)
  const actions = Object.entries(facets?.actions || {}).sort((a, b) => b[1].n - a[1].n)
  const days = daysOf(items)
  const showCab = contour === 'all'

  return (
    <>
      <Head><title>Журнал · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 22px', background: 'var(--bg-canvas)', height: '100vh', boxSizing: 'border-box',
        display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
        <SettingsTabs active="audit" />
        {/* Ряд вкладок — на всю ширину, содержимое — под 1600 по левому краю (владелец 16.11.2026). */}
        <div style={{ maxWidth: PAGE_W.base, width: '100%', flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-primary)' }}>Журнал действий</span>
              <span style={{ ...cap, fontSize: 10 }}>
                {facets ? `${plural(facets.contours.all, 'запись', 'записи', 'записей')} · сотрудники и кабинеты паблишеров` : ''}
              </span>
            </span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span style={cap}>Чья активность</span>
              <span style={{ display: 'inline-flex', padding: 2, borderRadius: 11, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
                {CONTOURS.map(([k, l]) => {
                  const on = contour === k
                  return (
                    <button key={k} type="button" onClick={() => pickContour(k)}
                      style={{ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 12px', borderRadius: 9,
                        background: on ? 'var(--bg-card)' : 'transparent', boxShadow: on ? 'var(--shadow-card)' : 'none',
                        color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12.5, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap' }}>
                      {l}<Num n={facets?.contours?.[k] ?? ''} />
                    </button>
                  )
                })}
              </span>
            </span>
          </div>

          <div data-no-unsaved style={{ position: 'relative', zIndex: 10, display: 'flex', alignItems: 'center', gap: '8px 12px', flexWrap: 'wrap' }}>
            <input value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Код сделки, площадка, текст" aria-label="Поиск" type="search"
              style={{ width: 240, height: 32, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: UI, color: 'var(--text-primary)' }} />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {PERIODS.map(([k, l]) => <button key={k} type="button" onClick={() => setF({ ...f, period: k })} style={pin(f.period === k)}>{l}</button>)}
              {f.period === 'range' && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <input value={f.from} onChange={e => setF({ ...f, from: e.target.value })} placeholder="с дд.мм" aria-label="Дата с" style={dateField} />
                  <span style={{ color: 'var(--text-faint)' }}>—</span>
                  <input value={f.to} onChange={e => setF({ ...f, to: e.target.value })} placeholder="по дд.мм" aria-label="Дата по" style={dateField} />
                </span>
              )}
            </span>
            <WhoPicker actors={facets?.actors || []} value={f.actor} contour={contour} open={whoOpen} setOpen={setWhoOpen}
              onPick={(id) => { setF({ ...f, actor: id }); setWhoOpen(false) }} />
            {filtered && <button type="button" onClick={() => setF(EMPTY)} style={{ ...plain, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', whiteSpace: 'nowrap' }}>сбросить ×</button>}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                {loading ? 'загрузка…' : `найдено ${total} · показано ${items.length}`}</span>
              {admin && (
                <button type="button" onClick={exportXls} disabled={!total || xls === 'run'}
                  title={total ? `Скачать найденное по текущим фильтрам: ${plural(total, 'запись', 'записи', 'записей')}` : 'Нечего выгружать'}
                  style={{ ...pin(false), fontWeight: 700, color: xls === 'done' ? 'var(--income)' : 'var(--text-secondary)', opacity: total ? 1 : 0.45,
                    cursor: total ? 'pointer' : 'default' }}>
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v8M4.5 7 8 10.5 11.5 7M2.5 13.5h11" /></svg>
                  {xls === 'done' ? 'Выгружено' : xls === 'run' ? 'Выгружаю…' : 'Скачать в Excel'}<Num n={xls === 'done' ? '✓' : total} />
                </button>
              )}
            </span>
          </div>
          {!!xlsErr && <div style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>{xlsErr}</div>}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ ...cap, paddingRight: 4, width: 92 }}>Раздел</span>
              <button type="button" onClick={() => setF({ ...f, section: '', action: '' })} style={pin(!f.section)}>Все<Num n={secAll} /></button>
              {(facets?.section_list || []).filter(s => secCounts[s.id] || f.section === s.id).map(s => (
                <button key={s.id} type="button" onClick={() => { setF({ ...f, section: f.section === s.id ? '' : s.id, action: '' }); setAllActions(false) }} style={pin(f.section === s.id)}>
                  <span style={{ width: 7, height: 7, borderRadius: 2, background: s.color }} />{s.title}<Num n={secCounts[s.id] || 0} />
                </button>
              ))}
            </span>
            {!!f.section && actions.length > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span style={{ ...cap, paddingRight: 4, width: 92 }}>Действие</span>
                {actions.filter(([k], i) => allActions || i < ACTIONS_SHOWN || k === f.action).map(([k, a]) => (
                  <button key={k} type="button" title={`Раздел: ${sections[f.section]?.title || ''}`} onClick={() => setF({ ...f, action: f.action === k ? '' : k })}
                    style={pin(f.action === k, 24)}>{a.label}<Num n={a.n} s={9.5} /></button>
                ))}
                {actions.length > ACTIONS_SHOWN && (
                  <button type="button" onClick={() => setAllActions(!allActions)}
                    style={{ ...plain, fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', whiteSpace: 'nowrap', padding: '0 4px' }}>
                    {allActions ? 'свернуть' : `ещё ${actions.length - ACTIONS_SHOWN} ▾`}</button>
                )}
              </span>
            )}
          </div>

          {!!err && <LoadError text={err} onRetry={() => load(0)} />}

          <div style={{ flex: '1 1 auto', minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, overflow: 'auto' }}>
            <div style={{ minWidth: 1240 }}>
              <div style={{ position: 'sticky', top: 0, zIndex: 5, display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center',
                padding: '12px 20px 10px', background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)', ...cap }}>
                <span>Время</span><span>Кто</span><span>Действие</span><span>Объект</span><span>Детали</span>
              </div>
              {days.map(d => (
                <div key={d.day}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '7px 20px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
                    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--text-primary)' }}>{d.day}</span>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>{d.title}</span>
                    <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--text-faint)' }}>{d.count}</span>
                  </div>
                  {d.rows.map(r => (r.kind === 'group'
                    ? <GroupRow key={r.key} items={r.items} open={!!open[r.key]} sections={sections} showCab={showCab}
                        onToggle={() => setOpen(prev => ({ ...prev, [r.key]: !prev[r.key] }))} />
                    : <OneRow key={r.item.id} item={r.item} sections={sections} showCab={showCab} />))}
                </div>
              ))}
              {!loading && !err && days.length === 0 && (
                <div style={{ padding: '36px 20px', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Записей нет — измените фильтры или период</div>
              )}
              {hasMore && (
                <div style={{ display: 'flex', justifyContent: 'center', padding: 14 }}>
                  <button type="button" onClick={() => load(items.length)} disabled={loading} className="j-more"
                    style={{ ...plain, display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', background: 'var(--bg-card)',
                      border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {loading ? 'Загрузка…' : 'Показать ещё'}</button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <style jsx global>{`
        .j-row:hover { background: var(--bg-tint) !important }
        .j-opt:hover { background: var(--bg-subtle) !important }
        .j-more:hover { border-color: var(--border-hover) !important; color: var(--accent) !important }
      `}</style>
    </>
  )
}
