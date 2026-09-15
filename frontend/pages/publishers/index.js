import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, IconBtn, inp, sel, btn, cell, headCell, card, CAP,
         PortalPopover, Z } from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import { INTEG_TONE_SOLID as INTEG_TONE, STATUS_TONE, NEUTRAL_TONE, EMPTY_TONE,
  nextStatus, tzLabel, localTime, Pin, ChatBtn } from '@/components/publishers/kit'
import PublisherSummary from '@/components/publishers/PublisherSummary'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { downloadFile } from '@/lib/download'

// Реестр площадок. Собран по экрану «Справочник паблишеров» из дизайн-хендоффа
// (docs/паблишеры.zip): строка L1 — то, по чему площадку выбирают, не открывая;
// клик разворачивает сводку L2; ✎ ведёт в карточку в режим правки, а не открывает
// форму в строке (правка живёт на одном экране — в карточке).
//
// Грань записи — сайт: веб и приложение показаны метками внутри строки, а не двумя
// строками; в исходной таблице шесть сайтов из-за этого двоились.

const EMPTY = { name: '', domain: '', kind: '', status: 'ПЕРЕГОВОРЫ', network: '',
  deal_type: '', cpm_contract: '' }

// Светофор отметок: буква + цвет. Приоритезация тут не живёт — она услуга каталога.
const FLAGS = [
  ['our_code', 'К', 'код наш', 'var(--accent)'],
  ['has_dsp', 'D', 'DSP', 'var(--income)'],
  ['self_promo_on', 'С', 'самореклама', 'var(--warning-text)'],
]
const SURFACE_STATUS_FILTER = ['есть WEB', 'есть APP', 'работаем WEB', 'работаем APP']

const FlagCell = ({ row }) => (
  <span style={{ display: 'inline-flex', gap: 3 }}>
    {FLAGS.map(([key, letter, title, color]) => {
      const on = key === 'self_promo_on' ? row.self_promo === 'ДА' : !!row[key]
      return (
        <span key={key} title={`${title} — ${on ? 'да' : 'нет'}`}
          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 18, height: 18, borderRadius: 5, fontFamily: MONO, fontSize: 10, fontWeight: 700,
            background: on ? 'var(--bg-card)' : 'transparent',
            border: `1px solid ${on ? color : 'var(--border-card)'}`,
            color: on ? color : 'var(--text-faint)' }}>{letter}</span>
      )
    })}
  </span>
)

// Метки поверхностей строки: WEB, а у приложения — Android и iOS отдельными метками,
// потому что подключаются они врозь.
const SurfaceCell = ({ row }) => {
  const out = []
  const web = row.surfaces?.web
  if (web) out.push({ key: 'web', label: 'WEB', s: web })
  const app = row.surfaces?.app
  if (app) {
    const platforms = app.platforms || {}
    if (!Object.keys(platforms).length) out.push({ key: 'app', label: 'APP', s: app })
    else {
      if (platforms.android) out.push({ key: 'and', label: 'AND', s: platforms.android, work: 'is_active' })
      if (platforms.ios) out.push({ key: 'ios', label: 'IOS', s: platforms.ios, work: 'is_active' })
    }
  }
  if (!out.length) return <span style={{ color: 'var(--text-faint)' }}>не заведены</span>
  return (
    <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
      {out.map(x => {
        const working = x.work ? x.s.is_active : x.s.we_work
        return <Pin key={x.key} text={x.label} dim={!working}
          title={`${x.label}: ${x.s.integration_status}${working ? '' : ' · не работаем'}`}
          tone={INTEG_TONE[x.s.integration_status] || INTEG_TONE['НЕТ']} />
      })}
    </span>
  )
}

// Фильтр-мультивыбор. Все фильтры реестра работают одинаково: галочки и счётчик
// выбранного, а не одиночный select — площадку одинаково часто ищут «в паузе ИЛИ
// в переговорах», и одиночный выбор заставлял фильтровать в два захода.
const MultiFilter = ({ label, options, selected, onChange, open, setOpen, width = 150 }) => {
  const picked = options.filter(o => selected.includes(o.value))
  const title = picked.length === 0 ? label
    : picked.length === 1 ? picked[0].label
      : `${label}: ${picked.length}`
  return (
    <span data-pop-root style={{ position: 'relative', display: 'inline-block' }}>
      <button style={{ ...btn(!!picked.length), minWidth: width, textAlign: 'left' }}
        onClick={() => setOpen(open ? null : label)}>{title}</button>
      <PortalPopover open={!!open} minWidth={Math.max(width, 210)} maxHeight={320}
        offset={6} style={{ padding: 8, zIndex: Z.dropdown }}>
          {options.map(o => (
            <label key={String(o.value)} style={{ display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 6px', fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={selected.includes(o.value)}
                onChange={e => onChange(e.target.checked
                  ? [...selected, o.value]
                  : selected.filter(x => x !== o.value))} />
              <span style={{ flex: 1 }}>{o.label}</span>
              {o.count != null && (
                <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{o.count}</span>
              )}
            </label>
          ))}
          {!options.length && <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>нет значений</span>}
          <button style={{ ...btn(false), width: '100%', marginTop: 6 }}
            onClick={() => { onChange([]); setOpen(null) }}>Сбросить</button>
      </PortalPopover>
    </span>
  )
}

export default function Publishers() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ statuses: [], kinds: [], networks: [], deal_types: [], services: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [search, setSearch] = useState('')
  const [fStatus, setFStatus] = useState([])
  const [fKind, setFKind] = useState([])
  const [fNetwork, setFNetwork] = useState([])
  const [fSurface, setFSurface] = useState([])
  const [fFlag, setFFlag] = useState([])
  const [fServices, setFServices] = useState([])   // id услуг
  const [openFilter, setOpenFilter] = useState(null)   // какой фильтр раскрыт

  // Закрытие по клику ВНЕ панели. До 05.09.2026 фильтр закрывался только повторным
  // кликом по своей же кнопке: открыл, ушёл мышью в таблицу — панель осталась висеть.
  // `closest('[data-pop-root]')` — канон проекта: клик внутри триггера или самой панели
  // (она рендерится порталом и тоже помечена) закрытием не считается.
  useRefreshOnReturn(() => load())
  useEffect(() => {
    if (!openFilter) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setOpenFilter(null) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [openFilter])
  const [showArchive, setShowArchive] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [vpop, setVpop] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [limit, setLimit] = useState(50)
  const [tick, setTick] = useState(0)

  const mayEdit = can(perms, 'dir_publishers', 'edit')
  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }
  // Время площадок идёт само: реестр держат открытым.
  useEffect(() => { const t = setInterval(() => setTick(x => x + 1), 30000); return () => clearInterval(t) }, [])

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [r, m] = await Promise.all([
        api.get('/publishers', auth()),
        api.get('/publishers/meta', auth()),
      ])
      setItems(r.data.items); setMeta(m.data)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить справочник') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [])

  const patch = async (id, body, localApply) => {
    try {
      await api.patch(`/publishers/${id}`, body, auth())
      setItems(prev => prev.map(x => (x.id === id ? { ...x, ...(localApply || body) } : x)))
      if (detail?.id === id) setDetail(d => ({ ...d, ...(localApply || body) }))
      return true
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить'); return false }
  }

  const openRow = async (p) => {
    if (openId === p.id) { setOpenId(null); return }
    setOpenId(p.id); setDetail(null)
    try { const r = await api.get(`/publishers/${p.id}`, auth()); setDetail(r.data) }
    catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить площадку') }
  }

  // Точечная правка прямо из сводки: статус интеграции, заметка, замер трафика.
  const cycleSurface = async (pid, kind, s) => {
    const next = nextStatus(s.integration_status)
    try {
      await api.put(`/publishers/${pid}/surfaces/${kind}`, { ...s, integration_status: next }, auth())
      const r = await api.get(`/publishers/${pid}`, auth())
      setDetail(r.data)
      setItems(prev => prev.map(x => (x.id === pid ? { ...x, surfaces: r.data.surfaces } : x)))
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сменить статус') }
  }

  const saveTraffic = async (pid, scope, value, depth) => {
    const num = (v) => {
      if (v === '' || v == null) return null
      const n = parseFloat(String(v).replace(/\s/g, '').replace(',', '.'))
      return isNaN(n) ? null : n
    }
    try {
      await api.put(`/publishers/${pid}/traffic`,
        { scope, value: num(value), depth: scope === 'ad_requests' ? null : num(depth) }, auth())
      const r = await api.get(`/publishers/${pid}`, auth())
      setDetail(r.data)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить замер') }
  }

  const cyclePlatform = async (pid, pk, pl) => {
    const next = nextStatus(pl?.integration_status || 'НЕТ')
    try {
      await api.put(`/publishers/${pid}/surfaces/app/platforms/${pk}`,
        { integration_status: next, is_active: !!pl?.is_active }, auth())
      await reloadDetail(pid)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сменить статус платформы') }
  }

  const reloadDetail = async (pid) => {
    const r = await api.get(`/publishers/${pid}`, auth())
    setDetail(r.data)
    // Счётчик пересобираем по тому же правилу, что и сервер: активные связи на
    // поверхностях, с которыми работаем. Иначе строка после правки и после
    // перезагрузки показывает разные числа.
    const working = new Set(Object.entries(r.data.surfaces || {})
      .filter(([, sf]) => sf.we_work).map(([k]) => k))
    setItems(prev => prev.map(x => (x.id === pid
      ? { ...x, surfaces: r.data.surfaces, contracts: r.data.contracts,
          services_supported: new Set((r.data.services || [])
            .filter(s => s.is_active !== false && working.has(s.surface_kind))
            .map(s => s.service_id)).size }
      : x)))
  }

  const patchDetail = async (pid, key, value) => {
    try { await api.patch(`/publishers/${pid}`, { [key]: value }, auth()); await reloadDetail(pid) }
    catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
  }

  // Имя файла не выдумываем: если своего нет, downloadFile берёт то, что прислал
  // сервер в Content-Disposition. Раньше документ договора сохранялся как «contract» —
  // без расширения, такой файл не открывается двойным щелчком.
  const downloadDoc = (pid, docId, filename) =>
    downloadFile(`/publishers/${pid}/documents/${docId}`, filename, setError)
  const downloadContractDoc = (pid, linkId) =>
    downloadFile(`/publishers/${pid}/contracts/${linkId}/document`, null, setError)
  const uploadContractDoc = async (pid, linkId, file) => {
    const fd = new FormData(); fd.append('file', file)
    try { await api.post(`/publishers/${pid}/contracts/${linkId}/document`, fd, auth()); await reloadDetail(pid) }
    catch (e) { setError(e.response?.data?.detail || 'Не удалось приложить документ') }
  }

  const openPin = (field, p, e) => {
    if (!mayEdit) return
    e.stopPropagation()
    const rect = e.currentTarget.getBoundingClientRect()
    const cfg = {
      status: { title: 'Статус работы', value: p.status,
        options: (meta.statuses || []).map(s => ({ value: s, label: s })),
        apply: (v) => patch(p.id, { status: v || 'ПЕРЕГОВОРЫ' }) },
      kind: { title: 'Вид паблишера', value: p.kind, clearLabel: '— не задан —',
        options: (meta.kinds || []).map(k => ({ value: k.name, label: k.name })),
        apply: (v) => patch(p.id, { kind: v || '' }, { kind: v || null }),
        onAddNew: async (name) => {
          try {
            const r = await api.post('/publishers/kinds', { name }, auth())
            setMeta(m => ({ ...m, kinds: [...(m.kinds || []), { id: r.data.id, name: r.data.name }] }))
            await patch(p.id, { kind: r.data.name }); setVpop(null)
          } catch (e) { setError(e.response?.data?.detail || 'Не удалось добавить вид') }
        } },
      network: { title: 'Сеть', value: p.network, clearLabel: '— независимая —',
        options: (meta.networks || []).map(n => ({ value: n, label: n })),
        apply: (v) => patch(p.id, { network: v || '' }, { network: v || null }),
        onAddNew: async (name) => {
          setMeta(m => ({ ...m, networks: [...new Set([...(m.networks || []), name])].sort() }))
          await patch(p.id, { network: name }); setVpop(null)
        } },
    }[field]
    if (!cfg) return
    setVpop({ rect, dealLabel: p.domain, ...cfg })
  }

  const save = async () => {
    setError('')
    if (!form.domain.trim()) { setError('Домен обязателен'); return }
    try {
      const r = await api.post('/publishers', {
        ...form,
        cpm_contract: form.cpm_contract === '' ? null
          : parseFloat(String(form.cpm_contract).replace(',', '.')),
      }, auth())
      setShowForm(false); setForm(EMPTY)
      flash('Площадка заведена')
      router.push(`/publishers/${r.data.id}`)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось сохранить') }
  }

  const archiveCount = items.filter(p => p.status === 'АРХИВ').length
  const totalServices = (meta.services || []).length

  // Несколько условий в одном фильтре складываются по ИЛИ: «покажи, где есть веб или
  // где работаем с аппом» — обычный запрос, и требовать оба сразу было бы неверно.
  const matchSurface = (p) => {
    if (!fSurface.length) return true
    return fSurface.some(v => {
      const s = v.includes('WEB') ? p.surfaces?.web : p.surfaces?.app
      if (!s) return false
      return v.startsWith('работаем') ? !!s.we_work : true
    })
  }

  const matchFlag = (p) => {
    if (!fFlag.length) return true
    return fFlag.some(v => (v === 'exclusive' ? p.is_exclusive
      : v === 'our_code' ? p.our_code
        : v === 'dsp' ? p.has_dsp
          : v === 'self_promo' ? p.self_promo === 'ДА' : false))
  }

  const filtered = items.filter(p => {
    if (!showArchive && p.status === 'АРХИВ') return false
    if (fStatus.length && !fStatus.includes(p.status)) return false
    if (fKind.length && !fKind.includes(p.kind)) return false
    if (fNetwork.length && !fNetwork.includes(p.network || '')) return false
    if (!matchSurface(p)) return false
    if (!matchFlag(p)) return false
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [p.name, p.domain, p.network, p.kind].some(v => (v || '').toLowerCase().includes(q))
      || (p.contracts || []).some(c => (c.number || '').toLowerCase().includes(q))
  })

  // Фильтр по услугам считает сервер: связь лежит в отдельной таблице, и тянуть её
  // в каждую строку списка ради фильтра незачем. Первый прогон пропускаем — список
  // уже загружен при монтировании, второй запрос был бы холостым.
  const [svcTouched, setSvcTouched] = useState(false)
  useEffect(() => {
    if (!svcTouched) return
    if (!fServices.length) { load(); return }
    const t = setTimeout(async () => {
      try {
        const r = await api.get('/publishers', {
          params: { service_id: fServices }, ...auth() })
        setItems(r.data.items)
      } catch (e) { setError('Не удалось отфильтровать по услугам') }
    }, 150)
    return () => clearTimeout(t)
  }, [fServices.join(',')])

  const dash = <span style={{ color: 'var(--text-faint)' }}>—</span>
  const GRID = 'minmax(150px,1.1fr) 70px 120px minmax(96px,0.8fr) 104px 58px minmax(190px,1.3fr) 58px 66px 84px minmax(150px,1fr) 58px 38px'
  const shown = filtered.slice(0, limit)

  return (
    <>
      <Head><title>Площадки · Паблишеры | SIMB-AD ERP</title></Head>
      <Navbar active="publishers" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>

        <div style={{ ...card, padding: '18px 24px 14px' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: '0 6px 0 0', color: 'var(--text-primary)' }}>Паблишеры</h1>
            <span style={{ ...CAP, marginBottom: 0, marginRight: 4 }}>показано {shown.length} из {items.length}</span>
            <input style={{ ...inp, width: 230 }} placeholder="площадка, домен, сеть, договор…"
              value={search} onChange={e => setSearch(e.target.value)} />
            <MultiFilter label="Все статусы" width={140} options={(meta.statuses || []).map(x => ({ value: x, label: x }))}
              selected={fStatus} onChange={setFStatus}
              open={openFilter === 'Все статусы'} setOpen={setOpenFilter} />
            <MultiFilter label="Все виды" width={120} options={(meta.kinds || []).map(k => ({ value: k.name, label: k.name }))}
              selected={fKind} onChange={setFKind}
              open={openFilter === 'Все виды'} setOpen={setOpenFilter} />
            {/* Пустое значение сети — это «независимая площадка», а не пропуск: без
                такого пункта два десятка площадок нельзя отобрать фильтром. */}
            <MultiFilter label="Все сети" width={130}
              options={[{ value: '', label: 'независимые' },
                ...(meta.networks || []).map(n => ({ value: n, label: n }))]}
              selected={fNetwork} onChange={setFNetwork}
              open={openFilter === 'Все сети'} setOpen={setOpenFilter} />
            <MultiFilter label="Поверхности" width={140} options={SURFACE_STATUS_FILTER.map(x => ({ value: x, label: x }))}
              selected={fSurface} onChange={setFSurface}
              open={openFilter === 'Поверхности'} setOpen={setOpenFilter} />
            <MultiFilter label="Отметки" width={130} selected={fFlag} onChange={setFFlag}
              open={openFilter === 'Отметки'} setOpen={setOpenFilter}
              options={[{ value: 'exclusive', label: 'Эксклюзив' }, { value: 'our_code', label: 'Код наш' },
                { value: 'dsp', label: 'DSP' }, { value: 'self_promo', label: 'Самореклама' }]} />
            {/* Услуги фильтрует сервер: связь лежит в отдельной таблице. */}
            <MultiFilter label="Все услуги" width={140} selected={fServices}
              onChange={(v) => { setSvcTouched(true); setFServices(v) }}
              open={openFilter === 'Все услуги'} setOpen={setOpenFilter}
              options={(meta.services || []).map(x => ({ value: x.id, label: x.name, count: x.publishers }))} />
            <button style={btn(showArchive)} onClick={() => setShowArchive(v => !v)}
              title="Площадки со статусом АРХИВ">
              {showArchive ? 'Прятать архив' : `Архив${archiveCount ? ` (${archiveCount})` : ''}`}
            </button>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <IconBtn title="Сбросить фильтры" onClick={() => {
                setSearch(''); setFStatus([]); setFKind([]); setFNetwork([])
                setFSurface([]); setFFlag([]); setSvcTouched(true); setFServices([])
                setOpenFilter(null)
              }}>
                <svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg>
              </IconBtn>
              {mayEdit && (
                <button style={btn(true)} onClick={() => { setShowForm(v => !v); setError('') }}>
                  {showForm ? 'Отмена' : '+ Площадка'}
                </button>
              )}
            </span>
          </div>

          {/* Как читать: тона поверхностей и буквы светофора иначе приходится угадывать. */}
          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
            padding: '8px 12px', background: 'var(--bg-tint)', border: '1px solid var(--accent-border)',
            borderRadius: 12, marginBottom: 12 }}>
            <span style={{ ...CAP, marginBottom: 0, color: 'var(--accent)' }}>как читать</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Pin text="WEB" tone={INTEG_TONE['ПОДКЛЮЧЕНО']} /><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>подключено</span>
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Pin text="WEB" tone={INTEG_TONE['ПОДГОТОВКА']} /><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>в работе</span>
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Pin text="WEB" tone={INTEG_TONE['НЕТ']} dim /><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>есть, не работаем</span>
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>К · D · С</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>код наш · DSP · самореклама</span>
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>⚠ договора нет в реестре</span>
            <span style={{ ...CAP, marginBottom: 0, marginLeft: 'auto' }}>строка — сводка · ✎ — правка в карточке</span>
          </div>

          {mayEdit && showForm && (
            <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              borderRadius: 'var(--radius-card)', padding: '14px 16px', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Новая площадка</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input style={{ ...inp, width: 190 }} placeholder="Домен (обязательно)" autoFocus
                  value={form.domain} onChange={e => setForm({ ...form, domain: e.target.value })}
                  onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setShowForm(false) }} />
                <input style={{ ...inp, width: 190 }} placeholder="Название (по умолч. домен)"
                  value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
                <select style={{ ...sel, width: 150 }} value={form.kind}
                  onChange={e => setForm({ ...form, kind: e.target.value })}>
                  <option value="">Вид паблишера…</option>
                  {(meta.kinds || []).map(k => <option key={k.id} value={k.name}>{k.name}</option>)}
                </select>
                <select style={{ ...sel, width: 150 }} value={form.status}
                  onChange={e => setForm({ ...form, status: e.target.value })}>
                  {(meta.statuses || []).map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <input style={{ ...inp, width: 150 }} placeholder="Сеть (пусто = независимая)"
                  value={form.network} onChange={e => setForm({ ...form, network: e.target.value })} />
                <select style={{ ...sel, width: 140 }} value={form.deal_type}
                  onChange={e => setForm({ ...form, deal_type: e.target.value })}>
                  <option value="">Вид договора…</option>
                  {(meta.deal_types || []).map(d => <option key={d} value={d}>{d}</option>)}
                </select>
                <input style={{ ...inp, width: 120 }} placeholder="CPM до НДС"
                  value={form.cpm_contract} onChange={e => setForm({ ...form, cpm_contract: e.target.value })} />
                <button style={btn(true)} onClick={save}>Завести</button>
                <button style={btn(false)} onClick={() => { setShowForm(false); setForm(EMPTY) }}>Отмена</button>
              </div>
            </div>
          )}

          {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
            color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{error}</div>}
          {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
            padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}
          {loading && <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>}

          {!loading && (
            <div style={{ overflowX: 'auto', maxWidth: '100%', margin: '4px -4px 0' }}>
              <div style={{ minWidth: 1720 }}>
                <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12,
                  borderBottom: '1px solid var(--border-card)' }}>
                  {headCell('Площадка')}{headCell('Время')}{headCell('Статус')}{headCell('Сеть')}{headCell('Поверхности')}
                  {headCell('Услуг', true)}{headCell('Подключенные услуги')}{headCell('CPM', true)}{headCell('Отметки')}{headCell('Эксклюзив')}
                  {headCell('Договор · юрлицо')}{headCell('Связь')}<div />
                </div>

                {shown.map(p => {
                  const open = openId === p.id
                  const [stBg, stFg] = STATUS_TONE[p.status] || STATUS_TONE['ПЕРЕГОВОРЫ']
                  return (
                    <div key={p.id}>
                      <div onClick={() => openRow(p)}
                        style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center',
                          padding: '10px 0', cursor: 'pointer', borderRadius: 10,
                          borderBottom: open ? 'none' : '1px solid var(--border-row)',
                          opacity: p.status === 'АРХИВ' ? .55 : 1,
                          background: open ? 'var(--bg-subtle)' : 'transparent' }}>

                        <div style={cell}>
                          <a href={`/publishers/${p.id}`} onClick={e => e.stopPropagation()}
                            style={{ color: 'var(--text-primary)', fontWeight: 700, textDecoration: 'none' }}>{p.name}</a>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{p.domain}</span>
                            <Pin text={p.kind || 'вид'} title="Вид паблишера — нажмите, чтобы изменить"
                              tone={p.kind ? NEUTRAL_TONE : EMPTY_TONE}
                              onClick={mayEdit ? (e => openPin('kind', p, e)) : undefined} />
                          </div>
                        </div>

                        {/* Часовой пояс площадки: звонок в 8 утра по Москве во
                            владивостокскую аптеку приходится на конец их дня. */}
                        <div style={cell}>
                          <div style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
                            color: p.timezone_offset ? 'var(--accent)' : 'var(--text-primary)' }}>
                            {localTime(p.timezone_offset)}
                          </div>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>
                            {tzLabel(p.timezone_offset)}
                          </div>
                        </div>

                        <div style={cell}>
                          <Pin text={p.status} tone={[stBg, stFg]} title="Статус работы — нажмите, чтобы изменить"
                            onClick={mayEdit ? (e => openPin('status', p, e)) : undefined} />
                        </div>

                        {/* Сеть правится пином прямо в строке: значений мало, они
                            повторяются, и уходить за этим в карточку незачем. */}
                        <div style={cell}>
                          <Pin text={p.network || 'независимая'} title="Сеть — нажмите, чтобы изменить"
                            tone={p.network ? NEUTRAL_TONE : EMPTY_TONE}
                            onClick={mayEdit ? (e => openPin('network', p, e)) : undefined} />
                        </div>

                        <div style={cell}><SurfaceCell row={p} /></div>

                        <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, fontSize: 12 }}
                          title={`Работаем с ${p.services_supported || 0} услугами из ${totalServices} в каталоге`}>
                          <span style={{ fontWeight: 700, color: p.services_supported ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                            {p.services_supported || 0}
                          </span>
                          <span style={{ color: 'var(--text-faint)' }}>\{totalServices}</span>
                        </div>

                        {/* Сами услуги плашками: за составом не нужно открывать сводку.
                            Высота ограничена двумя строками — иначе площадка с семью
                            услугами растягивает всю таблицу. */}
                        <div style={{ ...cell, display: 'flex', gap: 4, flexWrap: 'wrap',
                          maxHeight: 42, overflow: 'hidden' }}
                          title={(p.services || []).map(x => `${x.name} — ${x.surfaces.map(k => k.toUpperCase()).join(', ')}`).join(String.fromCharCode(10))}>
                          {(p.services || []).map(x => {
                            const live = x.surfaces.some(k => p.surfaces?.[k]?.we_work)
                            return (
                              <span key={x.service_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                                padding: '2px 7px', borderRadius: 7, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
                                background: live ? 'var(--accent-tint)' : 'var(--bg-subtle)',
                                color: live ? 'var(--accent)' : 'var(--text-faint)',
                                border: `1px solid ${live ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
                                {x.name}
                                <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '.06em', opacity: .7 }}>
                                  {x.surfaces.map(k => k.toUpperCase()).join('·')}
                                </span>
                              </span>
                            )
                          })}
                          {!(p.services || []).length && <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>—</span>}
                        </div>

                        <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, fontSize: 12 }}>
                          {p.cpm_contract != null ? p.cpm_contract : dash}
                        </div>

                        <div style={cell}><FlagCell row={p} /></div>

                        <div style={cell}>
                          {p.is_exclusive
                            ? <Pin text="эксклюзив" tone={['var(--accent)', 'var(--bg-card)']} title="Работаем эксклюзивно" />
                            : <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>нет</span>}
                        </div>

                        {/* Вид договора, счётчик и юрлица; номера и файлы — в сводке. */}
                        <div style={cell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                            <span style={{ color: p.deal_type ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
                              {p.deal_type || 'вид не указан'}
                            </span>
                            {!!(p.contracts || []).length && (
                              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
                                {p.contracts.length} дог.
                              </span>
                            )}
                            {(p.contracts || []).some(c => !c.linked) && (
                              <span title="Договора нет в реестре — записан номером">⚠</span>
                            )}
                          </div>
                          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {[...new Set((p.contracts || []).map(c => c.counterparty).filter(Boolean))].join(' · ')
                              || 'юрлицо не сопоставлено'}
                          </div>
                        </div>

                        <div style={{ ...cell, display: 'flex', gap: 5 }}>
                          <ChatBtn href={p.chat_url} kind="tg" title="Телеграм" size={24} />
                          <ChatBtn href={p.chat_url_max} kind="max" title="MAX" size={24} />
                        </div>

                        <div style={{ ...cell, display: 'flex', justifyContent: 'flex-end' }}>
                          {mayEdit && (
                            <IconBtn title="Править в карточке"
                              onClick={(e) => { e.stopPropagation(); router.push(`/publishers/${p.id}?edit=1`) }}>
                              <svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                            </IconBtn>
                          )}
                        </div>
                      </div>

                      {open && (
                        <div style={{ padding: '12px 14px 16px', background: 'var(--bg-tint)',
                          border: '1px solid var(--accent-border)', borderRadius: 14, marginBottom: 10 }}>
                          {!detail && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>}
                          {detail && detail.id === p.id && (
                            <PublisherSummary data={detail} meta={meta} canEdit={mayEdit} api={{
                              cycleSurface: (kind, sf) => cycleSurface(p.id, kind, sf),
                              cyclePlatform: (pk, pl) => cyclePlatform(p.id, pk, pl),
                              saveTraffic: (scope, value, depth) => saveTraffic(p.id, scope, value, depth),
                              patchField: (key, value) => patchDetail(p.id, key, value),
                              downloadDocument: (docId, filename) => downloadDoc(p.id, docId, filename),
                              downloadContractDoc: (linkId) => downloadContractDoc(p.id, linkId),
                              uploadContractDoc: (linkId, file) => uploadContractDoc(p.id, linkId, file),
                              openEdit: () => router.push(`/publishers/${p.id}?edit=1`),
                              openCard: () => router.push(`/publishers/${p.id}`),
                            }} />
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
                {!filtered.length && (
                  <div style={{ padding: '18px 8px', color: 'var(--text-muted)', fontSize: 13 }}>Ничего не найдено.</div>
                )}
              </div>
            </div>
          )}

          {!loading && filtered.length > limit && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
              <button style={btn(false)} onClick={() => setLimit(l => l + 50)}>Показать ещё</button>
              <span style={{ ...CAP, marginBottom: 0, marginLeft: 'auto' }}>строк на странице</span>
              {[50, 100, 300, 500].map(n => (
                <button key={n} style={btn(limit === n)} onClick={() => setLimit(n)}>{n}</button>
              ))}
            </div>
          )}
        </div>
      </div>

      {vpop && <ValuePopover anchor={vpop.rect} title={vpop.title} dealLabel={vpop.dealLabel}
        options={vpop.options} value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
        onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />}
    </>
  )
}
