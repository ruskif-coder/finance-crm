/**
 * Настройки → Статус системы (макет design_handoff_status, 16.11.2026; заменяет экран из восьми плиток 07.09.2026).
 *
 * Одна таблица проверок с секциями, фильтры пинами, скролл только внутри карточек. «Требует внимания» — первая
 * секция; тон секции и экрана считается из строк (`statusModel`). Права — только администратор (владелец 16.11.2026),
 * сервер закрыт `require_admin`.
 *
 * Открытие экрана и «авто · 30 с» живых запросов наружу не делают: связь с Телеграмом и SSL проверяет фоновый прогон
 * (`python -m app.system.watch`, крон раз в 10 минут), экран берёт их последний снимок. «Проверить» — такой прогон
 * сейчас: с записью истории и оповещениями при смене состояния.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { firstAllowedHref } from '@/components/Navbar'
import SettingsTabs from '@/components/SettingsTabs'
import { MONO, UI } from '@/components/salesTableKit'
import api, { auth } from '@/lib/http'
import { isAdmin } from '@/lib/auth'
import { detailText } from '@/lib/loadError'
import { fmtTime } from '@/lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { TONE_DOT, buildView, plural, verdictOf } from '@/components/settings/status/statusModel'
import StatusTable from '@/components/settings/status/StatusTable'
import { DiskCard, OnlineAndActivity } from '@/components/settings/status/SidePanels'
import { MaintBadge, MaintButton, NotifyButton, Toggle, headBtn } from '@/components/settings/status/HeaderActions'

const AUTO_MS = 30000
const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
const cardBox = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const VERDICT = {
  ok: { bg: 'var(--income-tint)', bd: 'var(--income-border)', fg: 'var(--income-fg)' },
  warn: { bg: 'var(--warning-tint)', bd: 'var(--warning-border)', fg: 'var(--warning-fg)' },
  bad: { bg: 'var(--danger-tint)', bd: 'var(--danger-border)', fg: 'var(--danger-fg)' },
}
const groupPin = (on) => ({ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 9, fontSize: 12, whiteSpace: 'nowrap',
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
  color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600 })
const Num = ({ n }) => <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>

export default function SettingsSystem() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [maint, setMaint] = useState(null)
  const [error, setError] = useState('')
  const [f, setF] = useState({ q: '', tone: 'all', group: 'all' })
  const [closed, setClosed] = useState({ cand: true })
  const [open, setOpen] = useState({})
  const [confirm, setConfirm] = useState('')
  const [auto, setAuto] = useState(true)
  const [checking, setChecking] = useState(false)
  const [justChecked, setJustChecked] = useState(false)
  const autoRef = useRef(auto)
  autoRef.current = auto

  const load = useCallback(() => api.get('/system/status', auth())
    .then(r => { setData(r.data); setError('') })
    .catch(e => setError(detailText(e, 'Статус не загрузился'))), [])
  const loadMaint = useCallback(() => api.get('/maintenance', auth()).then(r => setMaint(r.data)).catch(() => {}), [])

  useEffect(() => {
    if (!isAdmin()) {
      let p = {}
      try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { p = {} }
      router.push(firstAllowedHref(p, false))
      return undefined
    }
    load(); loadMaint()
    // «авто · 30 с»: выключенный тумблер действительно останавливает обновление (а не только перестаёт показывать)
    const id = setInterval(() => { if (autoRef.current) { load(); loadMaint() } }, AUTO_MS)
    return () => clearInterval(id)
  }, [load, loadMaint, router])
  useRefreshOnReturn(() => { if (autoRef.current) load() })

  const checkNow = () => {
    setChecking(true)
    api.post('/system/status/check', {}, auth())
      .then(r => { setData(r.data); setError(''); setJustChecked(true); setTimeout(() => setJustChecked(false), 2500) })
      .catch(e => setError(detailText(e, 'Прогон проверок не удался')))
      .finally(() => setChecking(false))
  }
  const runJob = (key) => api.post(`/system/jobs/${key}/run`, {}, auth())
    .then(() => { load(); setTimeout(load, 4000) })
    .catch(e => setError(detailText(e, 'Задание не запустилось')))
  const saveAlerts = (patch) => api.put('/system/alerts', patch, auth())
    .then(r => setData(d => ({ ...d, notify: { ...d.notify, ...r.data } })))
    .catch(e => setError(detailText(e, 'Настройки оповещений не сохранились')))
  const announce = (scope) => api.post('/maintenance', scope, auth()).then(loadMaint).catch(e => setError(detailText(e, 'Техобслуживание не объявлено')))
  const cancelMaint = () => api.delete('/maintenance', auth()).then(loadMaint).catch(e => setError(detailText(e, 'Техобслуживание не снято')))

  const checks = useMemo(() => data?.checks || [], [data])
  const groups = useMemo(() => data?.groups || [], [data])
  const view = useMemo(() => buildView(checks, groups, f), [checks, groups, f])
  const verdict = verdictOf(checks)
  const vt = VERDICT[verdict.tone]
  const filtered = !!(f.q || f.tone !== 'all' || f.group !== 'all')
  const storage = checks.find(c => c.key === 'storage')?.value

  return (
    <>
      <Head><title>Статус системы · Настройки | SIMB-AD ERP</title></Head>
      {/* Навбар и тело — одной колонкой высотой в экран: так прокручиваются только карточки, а не страница */}
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar active="settings" />
      <style>{`
        .st-row:hover { background: var(--bg-tint) !important }
        .st-head:hover, .st-btn:hover { border-color: var(--border-hover) !important }
        .st-btn:hover { color: var(--accent-fg) !important }
        .st-cta:hover, .st-yes:hover { background: var(--accent-hover) !important }
        .st-q:focus { border-color: var(--accent) !important }
      `}</style>
      <div style={{ padding: '20px 26px 22px', background: 'var(--bg-canvas)', flex: '1 1 auto', minHeight: 0, boxSizing: 'border-box',
        display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, color: 'var(--text-primary)' }}>
        <SettingsTabs active="system" />

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em' }}>Статус системы</span>
            <span style={{ ...cap, fontSize: 10 }}>{plural(checks.length, 'проверка', 'проверки', 'проверок')} · {groups.length} групп</span>
          </span>
          {data && (
            <span title="Итог считается из строк: худшее состояние среди всех проверок" style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 10px',
              borderRadius: 8, background: vt.bg, border: `1px solid ${vt.bd}`, fontSize: 12, fontWeight: 700, color: vt.fg, whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: TONE_DOT[verdict.tone] }} />{verdict.label}
            </span>
          )}
          <MaintBadge st={maint} />
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {checking ? 'проверяю…' : justChecked ? 'проверено только что' : data ? `проверено в ${fmtTime(data.checked_at)}` : ''}</span>
            <button type="button" onClick={() => setAuto(a => !a)} className="st-head" title="Автообновление каждые 30 секунд"
              style={{ ...headBtn, gap: 8, padding: '0 12px 0 10px', color: auto ? 'var(--text-primary)' : 'var(--text-muted)' }}>
              <Toggle on={auto} />авто · 30 с</button>
            <button type="button" onClick={checkNow} disabled={checking} className="st-head" title="Прогнать все проверки сейчас, включая живые запросы наружу"
              style={headBtn}>Проверить</button>
            <NotifyButton cfg={data?.notify} onChange={saveAlerts} />
            <MaintButton st={maint} onAnnounce={announce} onCancel={cancelMaint} />
          </span>
        </div>

        {!!error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger-border)', color: 'var(--danger-fg)', borderRadius: 12, padding: '8px 14px', fontSize: 12.5 }}>{error}</div>}

        <div style={{ ...cardBox, display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0,1fr))', padding: '14px 6px' }}>
          {(data?.kpi || []).map((k, i) => (
            <span key={k.key} style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '0 18px', borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}`, minWidth: 0 }}>
              <span style={cap}>{k.label}</span>
              <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>{k.value}</span>
              <span title={k.hint} style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{k.hint}</span>
            </span>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px 12px', flexWrap: 'wrap' }}>
          <input value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Проверка, ключ, файл" aria-label="Поиск" type="search" className="st-q"
            style={{ width: 210, height: 32, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: UI, color: 'var(--text-primary)' }} />
          <span style={{ display: 'inline-flex', padding: 2, borderRadius: 11, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
            {view.tones.map(([k, label, n]) => {
              const on = f.tone === k
              return (
                <button key={k} type="button" onClick={() => setF({ ...f, tone: k })} style={{ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 28,
                  padding: '0 11px', borderRadius: 9, background: on ? 'var(--bg-card)' : 'transparent', boxShadow: on ? 'var(--shadow-card)' : 'none',
                  color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12.5, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap' }}>{label}<Num n={n} /></button>
              )
            })}
          </span>
          {filtered && <button type="button" onClick={() => setF({ q: '', tone: 'all', group: 'all' })}
            style={{ ...plain, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', whiteSpace: 'nowrap' }}>сбросить ×</button>}
          <span style={{ flex: '1 0 100%', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ ...cap, width: 58 }}>Группа</span>
            <button type="button" onClick={() => setF({ ...f, group: 'all' })} style={groupPin(f.group === 'all')}>Все<Num n={view.inToneN} /></button>
            {view.groupPins.map(p => (
              <button key={p.key} type="button" title={p.title} onClick={() => setF({ ...f, group: f.group === p.key ? 'all' : p.key })} style={groupPin(f.group === p.key)}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: TONE_DOT[p.tone] }} />{p.label}<Num n={p.n} />
              </button>
            ))}
          </span>
        </div>

        <div style={{ flex: '1 1 auto', minHeight: 0, display: 'flex', gap: 12 }}>
          {data ? (
            <StatusTable view={view} closed={closed} onSection={k => setClosed(c => ({ ...c, [k]: !c[k] }))}
              open={open} onRow={k => setOpen(o => ({ ...o, [k]: !o[k] }))} confirm={confirm} setConfirm={setConfirm} onRun={runJob} />
          ) : (
            <div style={{ ...cardBox, flex: '1 1 auto', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
              {error ? 'Нет данных' : 'Собираю проверки…'}</div>
          )}
          <div style={{ flex: '0 0 372px', minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <OnlineAndActivity online={data?.online || []} activity={data?.activity} />
            <DiskCard disk={data?.disk} storage={storage} />
          </div>
        </div>
      </div>
      </div>
    </>
  )
}
