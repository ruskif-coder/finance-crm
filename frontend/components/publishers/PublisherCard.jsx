import { useState, useEffect, useRef } from 'react'
import { docCard } from '@/components/salesTableKit'
import { MONO, UI, INTEG_TONE, STATUS_TONE, TRAFFIC_ROWS, SURFACE_CYCLE, SURFACE_LABEL,
  PLATFORM_LABEL, ChatBtn, ServiceChip, tgHref, fmtMoney, fmtCompact, fmtUnit,
  tzLabel, localTime } from '@/components/publishers/kit'
import ValuePopover from '@/components/ValuePopover'

/**
 * Карточка площадки. Порт экрана «Карточка паблишера» из дизайн-хендоффа
 * (docs/паблишеры.zip): один экран и два состояния — просмотр и правка, без отдельных
 * форм, вкладок и модалок. Каждое значение превращается в поле на своём месте.
 *
 * Данные приходят готовым деревом из GET /api/publishers/{id} (+ /finance), сохранение
 * идёт через колбэки: карточка ничего не знает про axios и роуты.
 */

const card = { background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
  color: 'var(--text-muted)' }
const inp = { padding: '7px 9px', border: '1px solid var(--border-card)', borderRadius: 9,
  fontSize: 15, background: 'var(--bg-card)', color: 'var(--text-primary)', fontFamily: UI,
  outline: 'none', boxSizing: 'border-box', width: '100%' }

// Компоненты объявлены на модульном уровне: объявленный внутри рендера теряет фокус
// после каждого набранного символа.
// Подпись поля. В шапке карточки она мельче (там своя типографика), в виджетах —
// на два пункта крупнее: их читают, а не проглядывают.
const capBig = { ...cap, fontSize: 11 }
const Cap = ({ children, style, big }) => (
  <div style={{ ...(big ? capBig : cap), ...style }}>{children}</div>
)

const Badge = ({ label, bg, fg, border, title, children }) => (
  <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
    padding: '5px 11px', borderRadius: 9, background: bg, color: fg,
    border: `1px solid ${border}`, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
    <span style={{ width: 7, height: 7, borderRadius: 2, background: fg }} />
    {label}{children}
  </span>
)

const Kpi = ({ label, value, unit, color, size, first, big }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 5,
    paddingLeft: first ? 0 : 26, borderLeft: first ? 'none' : '1px solid var(--border-inner)' }}>
    <Cap big={big}>{label}</Cap>
    <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
      <span style={{ fontFamily: MONO, fontSize: size, fontWeight: 700, letterSpacing: '-.03em',
        lineHeight: 1, color, whiteSpace: 'nowrap' }}>{value}</span>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
    </span>
  </span>
)

// Текстовое поле, растущее по содержимому: данные не должны прятаться во внутреннем
// скролле. Вне режима правки открывается двойным кликом и сохраняется по уходу фокуса —
// заметку правят чаще, чем всю карточку, и ради строчки текста включать правку незачем.
const Grow = ({ value, onChange, onCommit, placeholder, disabled, minHeight = 44 }) => {
  const ref = useRef(null)
  const [live, setLive] = useState(false)
  const [draft, setDraft] = useState(value || '')
  const open = !disabled || live
  useEffect(() => { setDraft(value || '') }, [value])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.max(el.scrollHeight, minHeight)}px`
  }, [draft, minHeight, live])

  const commit = async () => {
    setLive(false)
    if (draft !== (value || '') && onCommit) await onCommit(draft)
  }

  return (
    <textarea ref={ref} value={draft} placeholder={placeholder} readOnly={!open}
      title={disabled && !live ? 'Двойной клик — править' : undefined}
      onDoubleClick={() => { if (disabled && onCommit) { setLive(true); setTimeout(() => ref.current?.focus(), 0) } }}
      onChange={e => { setDraft(e.target.value); if (!disabled) onChange(e.target.value) }}
      onBlur={() => { if (live) commit() }}
      onKeyDown={e => { if (e.key === 'Escape' && live) { setDraft(value || ''); setLive(false) } }}
      style={{ ...inp, resize: 'none', overflow: 'hidden', minHeight, lineHeight: 1.45,
        cursor: open ? 'text' : 'default',
        background: open ? 'var(--bg-card)' : 'transparent',
        border: open ? '1px solid var(--border-card)' : '1px solid transparent',
        color: draft ? 'var(--text-primary)' : 'var(--text-faint)' }} />
  )
}

// Значение, открывающее поповер выбора. Выглядит как значение, а не как поле:
// выбор из сохранённых списков в проекте везде сделан так (бренд в реестре сделок).
const PickValue = ({ value, placeholder, onOpen }) => (
  <span onClick={onOpen} title="Выбрать из списка"
    style={{ fontSize: 16, cursor: 'pointer', padding: '5px 8px', borderRadius: 8,
      border: '1px dashed var(--border-card)', display: 'inline-block',
      color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>
    {value || placeholder}
  </span>
)

const Param = ({ label, children, divider }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0,
    // Линия рисуется на каждой ячейке и в ряду сетки сходится в сплошную полосу —
    // одним элементом её не провести, ячейки переносятся по auto-fit.
    borderTop: divider ? '1px solid var(--border-inner)' : 'none',
    paddingTop: divider ? 10 : 0 }}>
    <Cap>{label}</Cap>
    {children}
  </div>
)

const Check = ({ label, checked, onChange, disabled }) => (
  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 11.5,
    fontWeight: 600, whiteSpace: 'nowrap', cursor: disabled ? 'default' : 'pointer',
    color: checked ? 'var(--text-primary)' : 'var(--text-muted)', opacity: disabled ? .5 : 1 }}>
    <input type="checkbox" checked={!!checked} disabled={disabled}
      onChange={e => onChange(e.target.checked)} />
    {label}
  </label>
)

const IntegPin = ({ status, onClick, dim }) => {
  const [bg, fg, bd] = INTEG_TONE[status] || INTEG_TONE['НЕТ']
  return (
    <span onClick={onClick} title={onClick ? 'Нажмите, чтобы сменить статус' : status}
      style={{ display: 'inline-block', padding: '3px 9px', borderRadius: 7, background: bg,
        color: fg, border: `1px solid ${bd}`, fontFamily: MONO, fontSize: 9.5, fontWeight: 700,
        letterSpacing: '.06em', textTransform: 'uppercase', opacity: dim ? .45 : 1,
        cursor: onClick ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>{status}</span>
  )
}

// parts: [{label, working}] — поверхность, с которой мы не работаем, показывается
// бледной и с пометкой в подсказке. Услуга там отмечена как поддерживаемая площадкой,
// но продавать её нельзя, и шапка не должна обещать обратное.
export default function PublisherCard({ data, meta, finance, editing, canEdit, form, setForm, api }) {
  const [tick, setTick] = useState(0)
  const [cpSearch, setCpSearch] = useState(null)   // null — поиск закрыт
  const [cpHits, setCpHits] = useState([])
  const [cpContracts, setCpContracts] = useState({})   // договоры юрлица из реестра
  const [contractRole, setContractRole] = useState('с площадкой')
  const [contactDraft, setContactDraft] = useState(null)   // null — модалка закрыта
  const [docDraft, setDocDraft] = useState(null)     // {doc_type} — форма загрузки открыта
  const [archived, setArchived] = useState(null)     // архивные договоры; null — скрыты
  const [newDocType, setNewDocType] = useState('')
  const [vpop, setVpop] = useState(null)   // {rect, title, options, value, apply, onAddNew}
  // По умолчанию — период, свежие сверху: в блоке смотрят «что было в последние месяцы».
  const [finSort, setFinSort] = useState({ key: 'period', dir: 'desc' })

  // Поиск на сервере с задержкой: печатают быстрее, чем отвечает реестр.
  useEffect(() => {
    const q = (cpSearch || '').trim()
    if (!q) { setCpHits([]); return }
    const t = setTimeout(async () => setCpHits(await api.searchCounterparties(q)), 250)
    return () => clearTimeout(t)
  }, [cpSearch])
  // Время площадки идёт само: карточку держат открытой, а «сейчас» должно оставаться «сейчас».
  useEffect(() => { const t = setInterval(() => setTick(x => x + 1), 30000); return () => clearInterval(t) }, [])

  if (!data) return null
  // В режиме правки карточка целиком читает черновик: сохранённое состояние остаётся
  // нетронутым, поэтому «Отмена» — это просто выбросить черновик, без отката запросами.
  const p = editing ? { ...data, ...form } : data
  const view = editing ? form : data
  const surfacesView = view.surfaces || {}
  const servicesView = view.services || []
  const trafficView = view.traffic || {}
  const services = meta.services || []
  const svcOn = (id, kind) => servicesView.some(x => x.service_id === id && x.surface_kind === kind)
  const svcTotal = new Set(servicesView.map(x => x.service_id)).size
  // Услуги на поверхностях, с которыми мы работаем, — это и есть продаваемое.
  const svcWorking = new Set(servicesView
    .filter(x => (editing ? form.surfaces : data.surfaces)?.[x.surface_kind]?.we_work)
    .map(x => x.service_id)).size
  const svcIdle = svcTotal - svcWorking
  const [stBg, stFg] = STATUS_TONE[p.status] || STATUS_TONE['ПЕРЕГОВОРЫ']
  const tz = tzLabel(p.timezone_offset)
  const time = localTime(p.timezone_offset)
  const tr = (scope) => trafficView[scope]?.value

  // Основной контакт показывается первым: к нему обращаются, остальные — справочно.
  const contactsSorted = [...(data.contacts || [])]
    .sort((a, b) => (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0))

  const flags = [
    ['Код наш', 'our_code', 'var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
    ['Эксклюзив', 'is_exclusive', 'var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
    ['DSP', 'has_dsp', 'var(--income-tint)', 'var(--income)', '#CDE9DE'],
    ['Самореклама', 'self_promo_on', 'var(--warning-tint)', 'var(--warning-text)', '#F2DFC0'],
  ]
  const flagValue = (key) => (key === 'self_promo_on' ? (p.self_promo === 'ДА') : !!p[key])

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))

  // Одна пара действий на каждую вложенную сущность: в правке пишем в черновик,
  // вне правки (клик по пину в просмотре) отправляем сразу.
  const stageSurface = (kind, patch) => setForm(f => ({
    ...f, surfaces: { ...f.surfaces, [kind]: { ...(f.surfaces?.[kind] || {}), ...patch } } }))

  const editSurface = (kind, patch) => (editing ? stageSurface(kind, patch)
    : api.saveSurface(kind, { ...(data.surfaces?.[kind] || {}), ...patch }))

  const editSurfaceExists = (kind, exists) => {
    if (!editing) return exists ? api.addSurface(kind) : api.dropSurface(kind)
    setForm(f => {
      const next = { ...f.surfaces }
      if (exists) next[kind] = { integration_status: 'НЕТ', we_work: false, platforms: {} }
      else delete next[kind]
      // Услуги несуществующей поверхности снимаются вместе с ней.
      return { ...f, surfaces: next,
        services: exists ? f.services : (f.services || []).filter(x => x.surface_kind !== kind) }
    })
  }

  const editPlatform = (kind, patch) => {
    if (!editing) return api.savePlatform(kind, patch)
    setForm(f => {
      const app = f.surfaces?.app || {}
      const platforms = { ...(app.platforms || {}) }
      platforms[kind] = { ...(platforms[kind] || {}), exists: true, ...patch }
      return { ...f, surfaces: { ...f.surfaces, app: { ...app, platforms } } }
    })
  }

  const editService = (kind, serviceId, on) => {
    if (!editing) return api.toggleService(kind, serviceId, on)
    setForm(f => {
      const list = (f.services || []).filter(x => !(x.surface_kind === kind && x.service_id === serviceId))
      return { ...f, services: on ? [...list, { surface_kind: kind, service_id: serviceId }] : list }
    })
  }

  const editTraffic = (scope, patch) => {
    if (!editing) return api.saveTraffic(scope, patch)
    setForm(f => ({ ...f, traffic: { ...f.traffic, [scope]: { ...(f.traffic?.[scope] || {}), ...patch } } }))
  }

  const cycle = (current) => SURFACE_CYCLE[(SURFACE_CYCLE.indexOf(current) + 1) % SURFACE_CYCLE.length]

  const sortBy = (key) => setFinSort(s0 => (
    s0.key === key ? { key, dir: s0.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  // Сортировка на клиенте: операций тут максимум пятьсот, за ними на сервер не ходят.
  // При равном значении оплаченное остаётся выше плана — факт важнее намерения.
  const finRows = [...((finance && finance.items) || [])].sort((a, b) => {
    const dir = finSort.dir === 'asc' ? 1 : -1
    const A = a[finSort.key], B = b[finSort.key]
    const num = typeof A === 'number' || typeof B === 'number'
    const cmp = num
      ? ((A || 0) - (B || 0))
      : String(A == null ? '' : A).localeCompare(String(B == null ? '' : B), 'ru')
    if (cmp) return cmp * dir
    return (a.status === 'ОПЛАЧЕНО' ? 0 : 1) - (b.status === 'ОПЛАЧЕНО' ? 0 : 1)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: UI }}>

      {editing && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          padding: '11px 16px', background: '#F6F8FF', border: '1px solid var(--accent-border)', borderRadius: 14 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--accent)' }} />
          <span style={{ ...cap, color: 'var(--accent)', fontWeight: 700 }}>Режим правки</span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            поля открыты на своих местах. Домен — ключ записи, менять осторожно.
          </span>
        </div>
      )}

      {/* ── ШАПКА ── */}
      <div style={{ ...card, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.025em' }}>{p.name}</span>
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
              {[p.kind, p.network ? `сеть ${p.network}` : 'независимая',
                p.cpm_contract != null ? `CPM ${p.cpm_contract} ₽ до НДС` : null,
                p.deal_type ? `договор ${p.deal_type}` : null].filter(Boolean).join(' · ')}
            </span>
          </span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: stBg,
              color: stFg, borderRadius: 10, padding: '7px 13px', fontFamily: MONO, fontSize: 11.5,
              fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: stFg }} />{p.status}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: 'var(--bg-subtle)',
              border: '1px solid var(--border-card)', borderRadius: 10, padding: '6px 12px' }}>
              <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{time}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.06em', color: 'var(--text-faint)' }}>{tz}</span>
            </span>
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 26, flexWrap: 'wrap' }}>
          <Kpi first label="CPM до НДС" value={p.cpm_contract ?? '—'} unit="₽" color="var(--text-primary)" size="32px" />
          <Kpi label="Трафик WEB / мес" value={fmtCompact(tr('web'))} unit={fmtUnit(tr('web'))} color="var(--accent)" size="26px" />
          <Kpi label="APP Android / мес" value={fmtCompact(tr('app_android'))} unit={fmtUnit(tr('app_android'))} color="#7B62D6" size="26px" />
          <Kpi label="APP iOS / мес" value={fmtCompact(tr('app_ios'))} unit={fmtUnit(tr('app_ios'))} color="#7B62D6" size="26px" />
          <Kpi label="Запросы рекл. кода" value={fmtCompact(tr('ad_requests'))} unit={fmtUnit(tr('ad_requests'))} color="var(--income)" size="26px" />
          {/* Считаем то, что реально продаём: услуга на поверхности «не работаем» в
              числитель не идёт, иначе счётчик обещает больше, чем есть. */}
          <Kpi label="Услуг подключено" value={`${svcWorking}\\${services.length}`} unit=""
            color="var(--text-primary)" size="26px" />
        </div>

        {/* Отметки показываются только включённые; приоритезация живёт услугой. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
          {flags.filter(([, key]) => flagValue(key)).map(([label, key, bg, fg, bd]) => (
            <Badge key={key} label={label} bg={bg} fg={fg} border={bd} title={`${label} — да`} />
          ))}
          {!!svcTotal && <span style={{ fontSize: 13, color: '#C7D0E8', padding: '0 2px' }}>|</span>}
          {services.map(svc => {
            const parts = ['web', 'app'].filter(k => svcOn(svc.id, k))
              .map(k => ({ label: SURFACE_LABEL[k], working: !!surfacesView[k]?.we_work }))
            if (!parts.length) return null
            return <ServiceChip key={svc.id} name={svc.name} parts={parts}
              isTarget={svc.name === 'Альфарм-Таргет'} sharesData={p.shares_data} />
          })}
          {editing && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
              padding: '8px 12px', background: '#F6F8FF', borderRadius: 10 }}>
              <span style={cap}>переключить</span>
              {flags.map(([label, key]) => (
                <Check key={key} label={label} checked={flagValue(key)}
                  onChange={v => set(key === 'self_promo_on' ? 'self_promo' : key,
                    key === 'self_promo_on' ? (v ? 'ДА' : 'НЕТ') : v)} />
              ))}
            </span>
          )}
        </div>
      </div>

      {/* ── ДВЕ КОЛОНКИ ── */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' }}>

        <div style={{ flex: '1 1 0', minWidth: 420, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Параметры */}
          <div style={{ ...card, padding: '20px 24px 18px' }}>
            <Cap big style={{ marginBottom: 14 }}>Параметры площадки</Cap>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
              <Param divider label="Название">
                {editing ? <input style={inp} value={p.name || ''} onChange={e => set('name', e.target.value)} />
                  : <span style={{ fontSize: 16, fontWeight: 600 }}>{p.name}</span>}
              </Param>
              <Param divider label="Домен · ключ записи">
                {editing ? <input style={{ ...inp, fontFamily: MONO }} value={p.domain || ''} onChange={e => set('domain', e.target.value)} />
                  : <span style={{ fontFamily: MONO, fontSize: 15.5 }}>{p.domain}</span>}
              </Param>
              <Param divider label="Вид паблишера">
                {editing ? (
                  <PickValue value={p.kind} placeholder="не задан"
                    onOpen={e => setVpop({
                      rect: e.currentTarget.getBoundingClientRect(),
                      title: 'Вид паблишера', value: p.kind, clearLabel: '— не задан —',
                      options: (meta.kinds || []).map(k => ({ value: k.name, label: k.name })),
                      apply: (v) => set('kind', v || ''),
                      // Новый вид уходит в общий накопитель и дальше предлагается всем.
                      onAddNew: async (name) => { set('kind', await api.addKind(name)); setVpop(null) },
                    })} />
                ) : <span style={{ fontSize: 16 }}>{p.kind || '—'}</span>}
              </Param>
              <Param divider label="Сеть">
                {editing ? <input style={inp} placeholder="пусто = независимая" value={p.network || ''} onChange={e => set('network', e.target.value)} />
                  : <span style={{ fontSize: 16, color: p.network ? 'var(--text-primary)' : 'var(--text-faint)' }}>{p.network || 'независимая'}</span>}
              </Param>
              <Param divider label="Статус работы">
                {editing ? (
                  <select style={inp} value={p.status || ''} onChange={e => set('status', e.target.value)}>
                    {(meta.statuses || []).map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                ) : <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: stFg }}>{p.status}</span>}
              </Param>
              <Param divider label="Часовой пояс">
                {editing ? (
                  <select style={inp} value={p.timezone_offset ?? 0}
                    onChange={e => set('timezone_offset', parseInt(e.target.value, 10))}>
                    {[-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(o => (
                      <option key={o} value={o}>{tzLabel(o)}</option>
                    ))}
                  </select>
                ) : <span style={{ fontFamily: MONO, fontSize: 15, color: 'var(--accent)' }}>{tz} · {time}</span>}
              </Param>
              <Param divider label="Вид договора">
                {editing ? (
                  <select style={inp} value={p.deal_type || ''} onChange={e => set('deal_type', e.target.value)}>
                    <option value="">—</option>
                    {(meta.deal_types || []).map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                ) : <span style={{ fontSize: 16 }}>{p.deal_type || '—'}</span>}
              </Param>
              <Param divider label="Посредник">
                <span style={{ fontSize: 16, color: data.intermediary_name ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                  {data.intermediary_name || 'не указан'}
                </span>
              </Param>
              <Param divider label="CPM до НДС по договору">
                {editing ? <input style={{ ...inp, fontFamily: MONO }} value={p.cpm_contract ?? ''}
                  onChange={e => set('cpm_contract', e.target.value)} />
                  : <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>{p.cpm_contract ?? '—'} ₽</span>}
              </Param>
            </div>
          </div>

          {/* Поверхности и услуги */}
          <div style={{ ...card, padding: '20px 24px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
              <Cap big>Поверхности и услуги</Cap>
              <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>
                услуга считается один раз, даже если отмечена на двух поверхностях
              </span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent)' }}>
                {svcWorking} из {services.length}
              </span>
            </div>

            {/* Расхождение, которое иначе видно только при сверке вручную: услуга
                отмечена, а поверхность не в работе — продать её нельзя. */}
            {!!svcIdle && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '9px 13px',
                background: 'var(--warning-tint)', border: '1px solid #F2DFC0', borderRadius: 12,
                marginBottom: 12, fontSize: 13.5, color: 'var(--warning-text)' }}>
                ⚠ Услуг отмечено {svcTotal}, из них {svcIdle} — на поверхностях со снятым
                флагом «работаем». В продаже они не участвуют.
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
              {['web', 'app'].map(kind => {
                const s = surfacesView[kind]
                const trafficScope = kind === 'web' ? 'web' : null
                return (
                  <div key={kind} style={{ borderRadius: 14, padding: '14px 16px',
                    // Заливка — про то, работаем ли мы с поверхностью. «Подключено» и
                    // «работаем» намеренно разные вещи: подключённая, но не продаваемая
                    // поверхность не должна выглядеть боевой.
                    border: `1px solid ${s ? (s.we_work ? 'var(--accent-border)' : 'var(--border-card)') : 'var(--border-inner)'}`,
                    background: s ? (s.we_work ? '#F6F8FF' : 'var(--bg-card)') : 'var(--bg-subtle)',
                    opacity: s ? 1 : .75 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{SURFACE_LABEL[kind]}</span>
                      {s ? <IntegPin status={s.integration_status} dim={!s.we_work}
                        onClick={canEdit ? () => editSurface(kind, { integration_status: cycle(s.integration_status) }) : undefined} />
                        : <span style={{ fontSize: 14, color: 'var(--text-faint)' }}>нет у площадки</span>}
                      {s && !s.we_work && (
                        <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>не работаем</span>
                      )}
                      {s?.figma_url && !editing && (
                        <a href={s.figma_url} target="_blank" rel="noreferrer"
                          style={{ marginLeft: 'auto', fontSize: 14, color: 'var(--accent)' }}>макет в фигме →</a>
                      )}
                      {editing && (
                        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12 }}>
                          <Check label="есть" checked={!!s} onChange={v => editSurfaceExists(kind, v)} />
                          <Check label="работаем" checked={!!s?.we_work} disabled={!s}
                            onChange={v => editSurface(kind, { we_work: v })} />
                        </span>
                      )}
                    </div>

                    {s && (
                      <>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))',
                          gap: 12, marginBottom: 12 }}>
                          <Param label="покрытие мест, %">
                            {editing
                              ? <input style={{ ...inp, fontFamily: MONO }} defaultValue={s.coverage_percent ?? ''}
                                  onBlur={e => editSurface(kind, { coverage_percent: e.target.value })} />
                              : <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>
                                  {s.coverage_percent != null ? `${s.coverage_percent} %` : '—'}</span>}
                          </Param>
                          <Param label="трафик / мес">
                            <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>
                              {kind === 'web' ? fmtMoney(tr('web'))
                                : fmtMoney((tr('app_android') || 0) + (tr('app_ios') || 0))}
                            </span>
                          </Param>
                          <Param label="отмечено услуг">
                            <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: 'var(--accent)' }}>
                              {servicesView.filter(x => x.surface_kind === kind).length}
                            </span>
                          </Param>
                        </div>

                        {editing && (
                          <div style={{ marginBottom: 12 }}>
                            <Cap big style={{ marginBottom: 5 }}>ссылка на фигму</Cap>
                            <input style={inp} defaultValue={s.figma_url || ''}
                              onBlur={e => editSurface(kind, { figma_url: e.target.value })} />
                          </div>
                        )}

                        {/* Платформы — только у приложения: Android бывает подключён,
                            когда iOS ещё в подготовке. */}
                        {kind === 'app' && (
                          <div style={{ marginBottom: 12 }}>
                            <Cap big style={{ marginBottom: 6 }}>платформы приложения</Cap>
                            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                              {['android', 'ios'].map(pk => {
                                const pl = s.platforms?.[pk]
                                return (
                                  <span key={pk} style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
                                    padding: '5px 10px', borderRadius: 9, background: 'var(--bg-subtle)',
                                    border: '1px solid var(--border-card)' }}>
                                    <span style={{ fontSize: 13.5, fontWeight: 700 }}>{PLATFORM_LABEL[pk]}</span>
                                    {pl ? <IntegPin status={pl.integration_status} dim={!pl.is_active}
                                      onClick={canEdit ? () => editPlatform(pk, { integration_status: cycle(pl.integration_status) }) : undefined} />
                                      : <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>нет</span>}
                                    {editing && (
                                      <Check label="работаем" checked={!!pl?.is_active}
                                        onChange={v => editPlatform(pk, { integration_status: pl?.integration_status || 'ПОДГОТОВКА', is_active: v })} />
                                    )}
                                    <span style={{ fontFamily: MONO, fontSize: 12.5, color: 'var(--text-muted)' }}>
                                      {fmtMoney(tr(pk === 'android' ? 'app_android' : 'app_ios'))}
                                    </span>
                                  </span>
                                )
                              })}
                            </div>
                          </div>
                        )}

                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {editing
                            ? services.map(svc => {
                                const on = svcOn(svc.id, kind)
                                const isTarget = svc.name === 'Альфарм-Таргет'
                                return (
                                  <span key={svc.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                                    <Check label={svc.name} checked={on}
                                      onChange={v => editService(kind, svc.id, v)} />
                                    {/* Данные спрашиваем в месте включения услуги: от них
                                        зависят доступные механики таргета, и уходить за
                                        этим в шапку — лишний шаг при заполнении. */}
                                    {isTarget && on && (
                                      <span style={{ display: 'inline-flex', gap: 4 }}>
                                        {[[true, 'DATA'], [false, 'NO DATA']].map(([val, lab]) => (
                                          <button key={lab} onClick={() => set('shares_data', val)}
                                            title={val ? 'Площадка делится данными' : 'Площадка данными не делится'}
                                            style={{ padding: '2px 8px', borderRadius: 6, cursor: 'pointer',
                                              fontFamily: MONO, fontSize: 10, fontWeight: 700,
                                              border: '1px solid ' + (p.shares_data === val ? 'transparent' : 'var(--border-card)'),
                                              background: p.shares_data === val
                                                ? (val ? 'var(--income-tint)' : 'var(--warning-tint)') : 'var(--bg-card)',
                                              color: p.shares_data === val
                                                ? (val ? 'var(--income)' : 'var(--warning-text)') : 'var(--text-faint)' }}>
                                            {lab}
                                          </button>
                                        ))}
                                      </span>
                                    )}
                                  </span>
                                )
                              })
                            : services.filter(svc => svcOn(svc.id, kind)).map(svc => (
                                <ServiceChip key={svc.id} name={svc.name}
                                  parts={[{ label: SURFACE_LABEL[kind], working: !!s.we_work }]}
                                  isTarget={svc.name === 'Альфарм-Таргет'} sharesData={p.shares_data} />
                              ))}
                          {!editing && !services.some(svc => svcOn(svc.id, kind)) &&
                            <span style={{ fontSize: 14, color: 'var(--text-faint)' }}>услуги не отмечены</span>}
                        </div>

                        {(editing || s.note) && (
                          <div style={{ marginTop: 10 }}>
                            <Grow value={s.note} disabled={!editing} placeholder="заметка по поверхности"
                              onChange={v => stageSurface(kind, { note: v })}
                              onCommit={v => api.saveSurface(kind, { ...(data.surfaces?.[kind] || {}), note: v })}
                              minHeight={38} />
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Трафик, материалы, механики */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px,1fr))', gap: 14 }}>
            <div style={{ ...card, padding: '18px 22px 16px' }}>
              <Cap big style={{ marginBottom: 12 }}>Трафик за месяц</Cap>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 110px 76px', gap: 8, alignItems: 'center' }}>
                <Cap big>показатель</Cap><Cap big style={{ textAlign: 'right' }}>за месяц</Cap><Cap big style={{ textAlign: 'right' }}>глубина</Cap>
                {TRAFFIC_ROWS.map(([scope, label, hasDepth]) => {
                  const t = trafficView[scope]
                  return (
                    <TrafficRow key={scope} scope={scope} label={label} hasDepth={hasDepth}
                      value={t?.value} depth={t?.depth} editing={editing} onSave={editTraffic} />
                  )
                })}
              </div>

              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
                <Cap big style={{ marginBottom: 8 }}>материалы</Cap>
                {/* Документ — карточка с заливкой, как в расхлопе сделки. Пусто —
                    одно поле с «+» посередине, чтобы было видно, куда класть файл. */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(data.documents || []).map(d => (
                    <div key={d.id} style={docCard}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)"
                        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
                      </svg>
                      <span style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 14.5, fontWeight: 600, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</div>
                        <div style={cap}>{d.doc_type}</div>
                      </span>
                      <button style={linkBtn} onClick={() => api.downloadDocument(d.id, d.filename)}>скачать</button>
                      {canEdit && <button style={xBtn} title="Удалить документ"
                        onClick={() => api.deleteDocument(d.id)}>×</button>}
                    </div>
                  ))}
                  {!(data.documents || []).length && (
                    <div onClick={() => canEdit && setDocDraft({ doc_type: (meta.doc_types || [])[0]?.name || '' })}
                      style={{ ...docCard, justifyContent: 'center', minHeight: 58, cursor: canEdit ? 'pointer' : 'default',
                        borderStyle: 'dashed', borderColor: 'var(--accent-border)', color: 'var(--accent)',
                        background: 'var(--bg-subtle)' }}>
                      <span style={{ fontSize: 22, fontWeight: 700, lineHeight: 1 }}>+</span>
                      <span style={{ fontSize: 14.5, fontWeight: 600 }}>документов нет</span>
                    </div>
                  )}
                  {canEdit && !!(data.documents || []).length && (
                    <button style={dashedBtn}
                      onClick={() => setDocDraft({ doc_type: (meta.doc_types || [])[0]?.name || '' })}>
                      + Добавить документ
                    </button>
                  )}
                </div>
                <div style={sectionRule} />
                <Cap big style={{ margin: '0 0 6px' }}>техрегламент · критерии к креативам</Cap>
                <Grow value={p.tech_requirements} disabled={!editing}
                  placeholder="форматы, вес, сроки подачи, запреты"
                  onChange={v => set('tech_requirements', v)} onCommit={v => api.patchField('tech_requirements', v)} />
              </div>
            </div>

            <div style={{ ...card, padding: '18px 22px 16px' }}>
              <Cap big style={{ marginBottom: 12 }}>Механики на площадке</Cap>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 15, fontWeight: 600 }}>Самореклама</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, fontWeight: 700,
                  color: p.self_promo === 'ДА' ? 'var(--warning-text)' : 'var(--text-faint)' }}>
                  {p.self_promo || 'не выяснено'}
                </span>
              </div>
              <Grow value={p.self_promo_note} disabled={!editing}
                placeholder="что именно площадка размещает у себя"
                onChange={v => set('self_promo_note', v)} onCommit={v => api.patchField('self_promo_note', v)} />
              <div style={sectionRule} />
              <Cap big style={{ margin: '0 0 6px' }}>корзина и избранное</Cap>
              <Grow value={p.basket_note} disabled={!editing}
                placeholder="есть ли отложенный товар и какие коммуникации возможны"
                onChange={v => set('basket_note', v)} onCommit={v => api.patchField('basket_note', v)} />
            </div>
          </div>
        </div>

        {/* ── ПРАВАЯ КОЛОНКА ── */}
        {/* Правая колонка — 30 % ширины полотна: доля, а не фикс, иначе на узком экране
            она давит левую, а на широком висит пустой. */}
        <div style={{ flex: '0 0 30%', minWidth: 300, display: 'flex', flexDirection: 'column', gap: 14 }}>

          <div style={{ ...card, padding: '18px 20px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Cap big>Юрлица и договоры</Cap>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>
                {(data.contracts || []).length} дог.
              </span>
              {canEdit && (
                <button title="Прикрепить юрлицо из справочника контрагентов"
                  onClick={() => { setCpSearch(cpSearch == null ? '' : null); setCpHits([]) }}
                  style={{ ...plusBtn, background: cpSearch == null ? 'var(--bg-card)' : 'var(--accent-tint)' }}>+</button>
              )}
            </div>

            {canEdit && cpSearch != null && (
              <div style={{ marginBottom: 10 }}>
                <input autoFocus style={inp} placeholder="поиск юрлица в справочнике…"
                  value={cpSearch} onChange={e => setCpSearch(e.target.value)} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
                  {cpHits.map(c => (
                    <button key={c.id} onClick={async () => { await api.attachCounterparty(c.id); setCpSearch(null); setCpHits([]) }}
                      style={{ ...linkBtn, textAlign: 'left', justifyContent: 'flex-start' }}>{c.name}</button>
                  ))}
                  {!cpHits.length && !!cpSearch.trim() && (
                    <span style={{ fontSize: 14, color: 'var(--text-faint)' }}>ничего не найдено</span>
                  )}
                </div>
              </div>
            )}
            {(data.counterparties || []).map(c => {
              const list = cpContracts[c.counterparty_id]
              return (
                <div key={c.counterparty_id} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} />
                    <span style={{ fontSize: 15, fontWeight: 700 }}>{c.name}</span>
                    <span style={{ ...cap, marginLeft: 'auto', color: 'var(--accent)' }}>плательщик</span>
                    {canEdit && (
                      <button title="Показать договоры юрлица из реестра" style={{ ...linkBtn, padding: '2px 8px' }}
                        onClick={async () => {
                          if (list) { setCpContracts(m => ({ ...m, [c.counterparty_id]: undefined })); return }
                          setCpContracts(m => ({ ...m, [c.counterparty_id]: [] }))
                          const rows = await api.contractsByCounterparty(c.counterparty_id)
                          setCpContracts(m => ({ ...m, [c.counterparty_id]: rows }))
                        }}>договоры</button>
                    )}
                    {canEdit && <button style={xBtn} onClick={() => api.detachCounterparty(c.counterparty_id)}>×</button>}
                  </div>
                  {canEdit && list && (
                    <div style={{ margin: '6px 0 0 15px' }}>
                      <select style={{ ...inp, padding: '4px 6px', fontSize: 14, marginBottom: 5 }}
                        value={contractRole} onChange={e => setContractRole(e.target.value)}>
                        {(meta.contract_roles || []).map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                      {!list.length && (
                        <div style={{ fontSize: 14, color: 'var(--text-faint)' }}>
                          у этого юрлица нет договоров в реестре
                        </div>
                      )}
                      {list.map(ct => {
                        const link = (data.contracts || []).find(x => x.contract_id === ct.id)
                        return (
                          <label key={ct.id} style={{ display: 'flex', alignItems: 'center', gap: 7,
                            fontSize: 14.5, padding: '2px 0', cursor: 'pointer' }}>
                            <input type="checkbox" checked={!!link}
                              onChange={e => (e.target.checked
                                ? api.attachContract(ct.id, contractRole)
                                : api.detachContract(link.id))} />
                            <span style={{ fontFamily: MONO, fontSize: 13.5 }}>{ct.number || `#${ct.id}`}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{ct.kind || ''}</span>
                          </label>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
            {!data.counterparties?.length && (
              <div style={{ fontSize: 14.5, color: 'var(--text-faint)', marginBottom: 8 }}>юрлицо не сопоставлено</div>
            )}

            {(data.contracts || []).map(c => (
              <div key={c.id} style={{ padding: '8px 0', borderTop: '1px solid var(--border-inner)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontFamily: MONO, fontSize: 14.5, fontWeight: 700 }}>{c.number}</span>
                  {!c.linked && <span title="В реестре «Договора» такого номера нет">⚠</span>}
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                    {c.document_source === 'edo' && c.document_url && (
                      <a href={c.document_url} target="_blank" rel="noreferrer" style={linkBtn}>ЭДО</a>
                    )}
                    {c.document_source === 'file' && (
                      <button style={linkBtn} onClick={() => api.downloadContractDoc(c.id)}>документ</button>
                    )}
                    {canEdit && (
                      <label style={{ ...linkBtn, cursor: 'pointer' }} title="Приложить файл договора">＋
                        <input type="file" style={{ display: 'none' }}
                          onChange={e => e.target.files?.[0] && api.uploadContractDoc(c.id, e.target.files[0])} />
                      </label>
                    )}
                    {/* Второй источник документа — ЭДО: файла у нас нет, есть адрес. */}
                    {canEdit && c.document_source !== 'file' && (
                      <button style={linkBtn} title="Указать ссылку на договор в ЭДО"
                        onClick={() => api.setContractEdo(c.id, c.document_url)}>ЭДО+</button>
                    )}
                    {canEdit && (
                      <button style={xBtn} title="Убрать договор в архив — запись сохранится"
                        onClick={async () => {
                          await api.archiveContract(c.id)
                          // Открытый список архива иначе остался бы без только что
                          // убранного договора до повторного открытия.
                          if (archived) setArchived(await api.archivedContracts())
                        }}>⌫</button>
                    )}
                  </span>
                </div>
                <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>
                  {c.role}{c.counterparty ? ` · ${c.counterparty}` : ' · юрлицо не сопоставлено'}
                </div>
              </div>
            ))}
            {!data.contracts?.length && (
              <div style={{ fontSize: 14.5, color: 'var(--text-faint)', padding: '6px 0' }}>договоры не привязаны</div>
            )}
            {/* Архив договоров: убранный договор не исчезает, его видно по кнопке —
                иначе «в архив» ничем не отличалось бы от удаления. */}
            <button style={{ ...linkBtn, marginTop: 8 }}
              onClick={async () => setArchived(archived ? null : await api.archivedContracts())}>
              {archived ? 'Скрыть архив' : 'Архив договоров'}
            </button>
            {archived && !archived.length && (
              <div style={{ fontSize: 13, color: 'var(--text-faint)', marginTop: 6 }}>архив пуст</div>
            )}
            {(archived || []).map(c => (
              <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6,
                fontSize: 13, color: 'var(--text-muted)' }}>
                <span style={{ fontFamily: MONO, fontSize: 12.5 }}>{c.number}</span>
                <span>{c.role}</span>
                {canEdit && (
                  <button style={{ ...linkBtn, padding: '2px 8px' }} title="Вернуть договор из архива"
                    onClick={async () => { await api.restoreContract(c.id); setArchived(await api.archivedContracts()) }}>
                    вернуть
                  </button>
                )}
              </div>
            ))}
            {canEdit && ((data.counterparties || []).length
              ? (
                <button style={dashedBtn} title="Выбрать договор из реестра — только у юрлиц этой площадки"
                  onClick={async () => {
                    // Раскрываем договоры сразу всех прикреплённых юрлиц: у площадки их
                    // бывает несколько, и прятать половину выбора незачем.
                    for (const cp of data.counterparties) {
                      const rows = await api.contractsByCounterparty(cp.counterparty_id)
                      setCpContracts(m => ({ ...m, [cp.counterparty_id]: rows }))
                    }
                  }}>+ Привязать договор</button>
              )
              : (
                <button style={{ ...dashedBtn, borderColor: 'var(--border-card)', color: 'var(--text-faint)' }}
                  title="Договор заключается с юрлицом — сначала прикрепите его"
                  onClick={() => { setCpSearch(''); setCpHits([]) }}>
                  сначала прикрепите юрлицо
                </button>
              ))}
          </div>

          <div style={{ ...card, padding: '18px 20px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 12 }}>
              <Cap big>Контакты</Cap>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>
                {(data.contacts || []).length}
              </span>
            </div>
            {/* Колонка узкая: имя и почта длиннее, чем кажется («i.lagoyskaya@asna.ru»),
                поэтому здесь шрифт мельче остальных виджетов, а длинное имя обрезается
                многоточием, а не ломает строку. */}
            {contactsSorted.map(c => (
              <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start',
                padding: '8px 0', borderBottom: '1px solid var(--border-inner)' }}>
                <span style={{ minWidth: 0, flex: '1 1 40%' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center',
                    gap: 5, lineHeight: 1.25 }}>
                    <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap' }} title={c.name || ''}>{c.name || 'без имени'}</span>
                    {c.is_primary && <span title="Основной контакт"
                      style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)', flex: '0 0 auto' }} />}
                  </div>
                  <div style={{ ...cap, fontSize: 8.5 }}>{c.role || 'должность не указана'}</div>
                </span>
                <span style={{ textAlign: 'right', minWidth: 0, flex: '1 1 60%' }}>
                  {/* Телефон и почту копируют — они текстом; в мессенджеры переходят. */}
                  <div style={{ fontFamily: MONO, fontSize: 11, lineHeight: 1.3,
                    color: c.phone ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                    {c.phone || 'телефон не указан'}
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 11, lineHeight: 1.3, overflow: 'hidden',
                    textOverflow: 'ellipsis', color: 'var(--text-muted)' }} title={c.email || ''}>{c.email || ''}</div>
                </span>
                <span style={{ display: 'inline-flex', gap: 5 }}>
                  <ChatBtn href={tgHref(c.telegram)} kind="tg" title="Телеграм" size={24} />
                  <ChatBtn href={c.max_url} kind="max" title="MAX" size={24} />
                </span>
                {canEdit && (
                  <span style={{ display: 'inline-flex', gap: 4 }}>
                    <button style={xBtn} title="Править контакт"
                            onClick={() => setContactDraft({ ...c })}>✎</button>
                    <button style={xBtn} title="Удалить контакт"
                      onClick={() => api.deleteContact(c.id)}>×</button>
                  </span>
                )}
              </div>
            ))}
            {canEdit && (
              <button style={dashedBtn}
                onClick={() => setContactDraft({ ...EMPTY_CONTACT })}>
                + Добавить контакт
              </button>
            )}
          </div>

          <div style={{ ...card, padding: '18px 20px 16px', flex: '1 1 auto' }}>
            <Cap big style={{ marginBottom: 12 }}>Связь и заметки</Cap>
            <Cap big style={{ marginBottom: 5 }}>рабочий чат</Cap>
            {/* Название чата и кнопки мессенджеров — одной строкой: кнопки прижаты
                вправо, чтобы взгляд не искал их под значением. */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {editing
                ? <input style={inp} value={p.chat_title || ''} onChange={e => set('chat_title', e.target.value)} />
                : <span style={{ fontSize: 15, fontWeight: 600 }}>{p.chat_title || '—'}</span>}
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flex: '0 0 auto' }}>
                <ChatBtn href={p.chat_url} kind="tg" title="Телеграм" />
                <ChatBtn href={p.chat_url_max} kind="max" title="MAX" />
              </span>
            </div>
            {editing && (
              <>
                <Cap big style={{ margin: '12px 0 5px' }}>ссылка в телеграме</Cap>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <input style={inp} value={p.chat_url || ''} onChange={e => set('chat_url', e.target.value)} />
                  <ChatBtn href={p.chat_url} kind="tg" title="Телеграм" />
                </div>
                <Cap big style={{ margin: '10px 0 5px' }}>ссылка в MAX</Cap>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <input style={inp} value={p.chat_url_max || ''} onChange={e => set('chat_url_max', e.target.value)} />
                  <ChatBtn href={p.chat_url_max} kind="max" title="MAX" />
                </div>
              </>
            )}
            <div style={sectionRule} />
            <Cap big style={{ margin: '0 0 6px' }}>доп. каналы связи</Cap>
            <Grow value={p.messenger_note} disabled={!editing}
              placeholder="альтернативные чаты, дублирование срочного" onChange={v => set('messenger_note', v)} onCommit={v => api.patchField('messenger_note', v)} />
            <div style={sectionRule} />
            <Cap big style={{ margin: '0 0 6px' }}>заметки</Cap>
            <Grow value={p.note} disabled={!editing} placeholder="что важно помнить по площадке"
              onChange={v => set('note', v)} onCommit={v => api.patchField('note', v)} />
          </div>
        </div>
      </div>

      {/* Модалка контакта: все поля разом. По одному полю через prompt контакт
          заводится в четыре захода, и половина остаётся незаполненной. */}
      {contactDraft && (
        <div onClick={() => setContactDraft(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ ...card, width: 480, maxWidth: '100%', padding: '20px 22px' }}>
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 14 }}>
              {contactDraft.id ? 'Контакт' : 'Новый контакт'}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label style={{ gridColumn: '1 / -1' }}>
                <Cap big>ФИО</Cap>
                <input style={{ ...inp, marginTop: 4 }} autoFocus value={contactDraft.name || ''}
                  onChange={e => setContactDraft(d => ({ ...d, name: e.target.value }))} />
              </label>
              <div style={{ gridColumn: '1 / -1' }}>
                <Cap big>должность · общий каталог</Cap>
                <div style={{ marginTop: 4 }}>
                  <PickValue value={contactDraft.role} placeholder="не указана"
                    onOpen={e => setVpop({
                      rect: e.currentTarget.getBoundingClientRect(),
                      title: 'Должность', value: contactDraft.role, clearLabel: '— не указана —',
                      options: (meta.positions || []).map(x => ({ value: x.name, label: x.name })),
                      apply: (v) => setContactDraft(d => ({ ...d, role: v || '' })),
                      onAddNew: async (name) => {
                        const saved = await api.addPosition(name)
                        setContactDraft(d => ({ ...d, role: saved }))
                        setVpop(null)
                      },
                    })} />
                </div>
              </div>
              <label>
                <Cap big>телефон</Cap>
                <input style={{ ...inp, marginTop: 4, fontFamily: MONO }} value={contactDraft.phone || ''}
                  onChange={e => setContactDraft(d => ({ ...d, phone: e.target.value }))} />
              </label>
              <label>
                <Cap big>email</Cap>
                <input style={{ ...inp, marginTop: 4, fontFamily: MONO }} value={contactDraft.email || ''}
                  onChange={e => setContactDraft(d => ({ ...d, email: e.target.value }))} />
              </label>
              <label>
                <Cap big>телеграм</Cap>
                <input style={{ ...inp, marginTop: 4 }} placeholder="@ник или ссылка"
                  value={contactDraft.telegram || ''}
                  onChange={e => setContactDraft(d => ({ ...d, telegram: e.target.value }))} />
              </label>
              <label>
                <Cap big>MAX</Cap>
                <input style={{ ...inp, marginTop: 4 }} placeholder="ссылка" value={contactDraft.max_url || ''}
                  onChange={e => setContactDraft(d => ({ ...d, max_url: e.target.value }))} />
              </label>
              <label style={{ gridColumn: '1 / -1' }}>
                <Cap big>заметка</Cap>
                <input style={{ ...inp, marginTop: 4 }} value={contactDraft.note || ''}
                  onChange={e => setContactDraft(d => ({ ...d, note: e.target.value }))} />
              </label>
              <div style={{ gridColumn: '1 / -1' }}>
                <Check label="основной контакт" checked={contactDraft.is_primary}
                  onChange={v => setContactDraft(d => ({ ...d, is_primary: v }))} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
              <button style={linkBtn} onClick={() => setContactDraft(null)}>Отмена</button>
              <button style={{ ...linkBtn, background: 'var(--accent)', color: '#fff',
                borderColor: 'var(--accent)' }}
                onClick={async () => {
                  const saved = await api.saveContact({ ...contactDraft })
                  if (saved) setContactDraft(null)
                }}>Сохранить</button>
            </div>
          </div>
        </div>
      )}

      {/* Форма загрузки документа: тип из общего каталога, новый тип заводится тут же. */}
      {docDraft && (
        <div onClick={() => setDocDraft(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ ...card, width: 440, maxWidth: '100%', padding: '20px 22px' }}>
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 14 }}>Документ площадки</div>
            <Cap big>тип документа</Cap>
            <div style={{ display: 'flex', gap: 8, marginTop: 4, marginBottom: 14 }}>
              <select style={inp} value={docDraft.doc_type}
                onChange={e => { setDocDraft(d => ({ ...d, doc_type: e.target.value })); setNewDocType('') }}>
                {(meta.doc_types || []).map(t => <option key={t.id} value={t.name}>{t.name}</option>)}
              </select>
              <input style={inp} placeholder="или новый" value={newDocType}
                onChange={e => setNewDocType(e.target.value)} />
              <button style={{ ...plusBtn, flex: '0 0 auto' }} title="Добавить тип в общий каталог"
                disabled={!newDocType.trim()}
                onClick={async () => {
                  const saved = await api.addDocType(newDocType.trim())
                  setDocDraft(d => ({ ...d, doc_type: saved })); setNewDocType('')
                }}>+</button>
            </div>
            <label style={{ ...dashedBtn, marginTop: 0 }}>
              выбрать файл и загрузить
              <input type="file" style={{ display: 'none' }}
                onChange={async e => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  const done = await api.uploadDocument(docDraft.doc_type, f)
                  if (done) setDocDraft(null)
                }} />
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
              <button style={linkBtn} onClick={() => setDocDraft(null)}>Отмена</button>
            </div>
          </div>
        </div>
      )}

      {vpop && (
        <ValuePopover anchor={vpop.rect} title={vpop.title} options={vpop.options}
          value={vpop.value} clearLabel={vpop.clearLabel} onAddNew={vpop.onAddNew}
          onPick={(v) => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />
      )}

      {/* ── ФИНАНСЫ ── */}
      {finance && (
        <div style={{ ...card, padding: '20px 24px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>Финансы по площадке</span>
            <span style={{ ...cap }}>
              операции по привязанным юрлицам · {(finance.items || []).length} операций
            </span>
          </div>

          {/* Честность цифры: операция привязана к юрлицу, а не к площадке. */}
          {!!(finance.shared_entities || []).length && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '9px 13px',
              background: 'var(--warning-tint)', border: '1px solid #F2DFC0', borderRadius: 12,
              marginBottom: 14, fontSize: 14.5, color: 'var(--warning-text)' }}>
              ⚠ Суммы общие по юрлицу, а не по этой площадке:{' '}
              {finance.shared_entities.map(e => `${e.name} обслуживает ${e.publishers} площадок`).join('; ')}.
            </div>
          )}

          <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', marginBottom: 16 }}>
            <Kpi big first label="Выплачено площадке" value={fmtMoney(finance.kpi?.paid_out)} unit="₽"
              color="var(--text-primary)" size="26px" />
            <Kpi big label="В плане оплат" value={fmtMoney(finance.kpi?.planned)} unit="₽"
              color="var(--warning-text)" size="26px" />
            <Kpi big label="Поступления" value={fmtMoney(finance.kpi?.refunds)} unit="₽"
              color="var(--income)" size="26px" />
            <Kpi big label="Средний чек" value={fmtMoney(finance.kpi?.avg_check)} unit="₽"
              color="var(--text-primary)" size="26px" />
          </div>

          <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 900 }}>
              <div style={{ display: 'grid', gridTemplateColumns: FIN_GRID, gap: 10,
                borderBottom: '1px solid var(--border-card)', paddingBottom: 8 }}>
                {FIN_COLS.map(c => (
                  <button key={c.key} onClick={() => sortBy(c.key)}
                    title="Сортировать по колонке"
                    style={{ ...capBig, background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                      textAlign: c.right ? 'right' : 'left', fontFamily: MONO,
                      color: finSort.key === c.key ? 'var(--accent)' : 'var(--text-muted)' }}>
                    {c.label}{finSort.key === c.key ? (finSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                  </button>
                ))}
              </div>
              {finRows.slice(0, 50).map(op => (
                <div key={op.id} style={{ display: 'grid', gridTemplateColumns: FIN_GRID, gap: 10,
                  padding: '8px 0', borderBottom: '1px solid var(--border-row)', fontSize: 14.5 }}>
                  <span style={{ fontFamily: MONO }}>{op.date || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5,
                    color: op.status === 'ОПЛАЧЕНО' ? 'var(--income)' : 'var(--warning-text)' }}>{op.status}</span>
                  <span style={{ fontFamily: MONO, textAlign: 'right', color: op.income ? 'var(--income)' : 'var(--text-faint)' }}>
                    {op.income ? fmtMoney(op.income) : '—'}
                  </span>
                  <span style={{ fontFamily: MONO, textAlign: 'right' }}>{op.expense ? fmtMoney(op.expense) : '—'}</span>
                  <span>{op.counterparty}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13.5, color: 'var(--text-muted)' }}>{op.ds_num || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13.5 }}>{op.period || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13.5, color: 'var(--text-muted)' }}>{op.invoice || '—'}</span>
                </div>
              ))}
              {!finRows.length && (
                <div style={{ padding: '14px 0', fontSize: 15, color: 'var(--text-faint)' }}>
                  Операций по юрлицам площадки нет.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const EMPTY_CONTACT = { name: '', role: '', phone: '', email: '', telegram: '',
  max_url: '', note: '', is_primary: false }

// Разделитель между смысловыми блоками внутри карточки: в макете они есть везде,
// без них подписи и значения слипаются в одну простыню.
const sectionRule = { height: 1, background: 'var(--border-inner)', margin: '14px 0 10px' }

const dashedBtn = { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  width: '100%', marginTop: 10, padding: '8px 12px', borderRadius: 10,
  border: '1px dashed var(--accent-border)', background: 'transparent', color: 'var(--accent)',
  fontSize: 14.5, fontWeight: 700, cursor: 'pointer', fontFamily: UI }

// Банк и статья убраны: в карточке площадки смотрят «сколько и когда», а разрез по
// банкам и статьям живёт в ДДС.
const FIN_COLS = [
  { key: 'date', label: 'дата' },
  { key: 'status', label: 'статус' },
  { key: 'income', label: 'приход', right: true },
  { key: 'expense', label: 'расход', right: true },
  { key: 'counterparty', label: 'юрлицо' },
  { key: 'ds_num', label: '№ ДС' },
  { key: 'period', label: 'период' },
  { key: 'invoice', label: '№ счёта' },
]
const FIN_GRID = '104px 104px 120px 130px minmax(150px,1fr) 104px 92px 104px'

const linkBtn = { display: 'inline-flex', alignItems: 'center', padding: '4px 10px', borderRadius: 8,
  border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--accent)',
  fontSize: 13.5, fontWeight: 600, cursor: 'pointer', fontFamily: UI, textDecoration: 'none' }

const plusBtn = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 24, height: 24, borderRadius: 8, border: '1px solid var(--border-card)',
  color: 'var(--accent)', fontSize: 17, fontWeight: 700, cursor: 'pointer', lineHeight: 1 }

const xBtn = { border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-faint)',
  fontSize: 17, lineHeight: 1, padding: 0 }

// Строка трафика: значение и глубина правятся на месте, сохранение по потере фокуса —
// каждый ввод создаёт (или исправляет) замер текущего месяца.
function TrafficRow({ scope, label, hasDepth, value, depth, editing, onSave }) {
  return (
    <>
      <span style={{ fontSize: 14.5, color: 'var(--text-secondary)' }}>{label}</span>
      {editing
        ? <input style={{ ...inp, fontFamily: MONO, textAlign: 'right', padding: '5px 8px' }}
            defaultValue={value ?? ''} onBlur={e => onSave(scope, { value: e.target.value, depth })} />
        : <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, textAlign: 'right',
            color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>{fmtMoney(value)}</span>}
      {hasDepth
        ? (editing
            ? <input style={{ ...inp, fontFamily: MONO, textAlign: 'right', padding: '5px 8px' }}
                defaultValue={depth ?? ''} onBlur={e => onSave(scope, { value, depth: e.target.value })} />
            : <span style={{ fontFamily: MONO, fontSize: 14.5, textAlign: 'right',
                color: depth ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
                {depth != null ? String(depth).replace('.', ',') : '—'}</span>)
        : <span style={{ textAlign: 'right', color: 'var(--text-faint)' }}>—</span>}
    </>
  )
}
