/**
 * Реестр шаблонов ДС — вкладка «Справочники → Приложения → Шаблоны» (хендофф «шаблоны дс», 31.10.2026).
 * Одна строка — один шаблон. Вёрстка по ТЗ хендоффа (`docs/шаблоны дс.zip`, папки `code/` в нём нет — макет, не компонент).
 *
 * Группы: базовые всегда сверху; дальше юрлицо → договор → основной первым → название. Юрлицо и договор пишутся один раз
 * на группу; между юрлицами линия `--border-card`, внутри — `--border-row`. Сортировка по заголовку работает ВНУТРИ группы
 * договора — группы не рвутся (по «Юрлицу» — переворачивает порядок групп).
 *
 * Данные — `GET /annex-templates` (обогащение в `routers/annex_templates.list_templates`). «Бренд» — память «договор +
 * бренд → шаблон», по которой сборка подставит шаблон в ДС бренда; привязки, о которой сборка не знает, тут нет.
 *
 * «Пересохранить» — вид документа в тексте шаблона записан словом. С 31.10.2026 тумблер договора переименовывает такое
 * слово и сам (`doc_kind.rebrand`), так что это чистка, а не условие работы тумблера.
 */
import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/router'
import { MONO, UI, Segmented, inp, chip } from '@/components/salesTableKit'
import { annexTemplatesApi } from '@/lib/annexTemplatesApi'
import { daysUntil, fmtDate, fmtDateOfMoment } from '@/lib/dates'
import { plural } from '@/components/contractCard/ui'

const COLS = 'minmax(180px,1.1fr) 150px minmax(190px,1.2fr) 140px 112px 64px 110px 52px 170px 100px 128px'
const STALE = 120                                    // дней: «не применялись 4 мес.»
const KIND = (r) => (r.scope === 'base' ? 'базовый' : r.is_main ? 'основной' : 'именованный')
const KIND_TONE = {
  основной: ['var(--accent-tint)', 'var(--accent-fg)'],
  именованный: ['var(--violet-tint)', 'var(--violet-fg)'],
  базовый: ['var(--bg-subtle)', 'var(--text-secondary)'],
}
const ellipsis = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
// Вид документа по договору — как на наших экранах («ДС»), не как в тексте документа (владелец 31.10.2026).
const WORD = { дс: 'ДС', приложение: 'Приложение' }
const SRC_HINT = { 'вне системы': 'по «ДС с» в реестре договоров — выданы вне системы',
                   'в системе': 'последний подтверждённый в системе',
                   'в мастер-сделке': 'стартовый номер, заданный в мастер-сделке' }
const dayKey = (iso) => (iso ? String(iso).slice(0, 10) : '')
// Сколько дней назад был последний ДС. `ds_last_at` — КАЛЕНДАРНЫЙ день, поэтому от сегодняшнего дня по Москве
// (`daysUntil`), а не как момент времени. ДС по шаблону не было — «давно» (9999), как в макете.
const ageDays = (day) => { const n = daysUntil(day); return n == null ? 9999 : -n }
const ent = (r) => (r.entity && r.entity.name) || ''
const stale = (r) => r.scope !== 'base' && ageDays(r.ds_last_at) > STALE
const cno = (r) => (r.contract && r.contract.no) || ''
// Поля строки — к одному виду при загрузке. Недостающее поле не должно ронять всю вкладку белым экраном: при
// выкладке фронт и бэкенд какое-то время живут разных версий, и строка придёт в старом формате (31.10.2026 — упало
// на `r.brands.length`, когда сервер стенда ещё работал на коде до обогащения списка).
const norm = (r) => ({ ...r, brands: r.brands || [], items: r.items ?? 0, ds_count: r.ds_count ?? 0,
                       literal_words: r.literal_words ?? 0, entity: r.entity || null, contract: r.contract || null })

// Ключи сортировки колонок. «ent» — порядок групп; остальные — внутри группы договора.
const HEAD = [
  ['ent', 'Юрлицо'], ['no', 'Договор'], ['name', 'Название шаблона'], ['brand', 'Бренд'], ['kind', 'Вид'],
  ['items', 'Пунктов', true], ['ds', 'ДС по шаблону', true], ['ver', 'Верс.', true], ['author', 'Кто создал · правил'],
  ['date', 'Создан'], [null, ''],
]
const SORT = {
  name: r => (r.title || '').toLowerCase(), brand: r => (r.brands[0] || '').toLowerCase(), kind: r => KIND(r),
  items: r => r.items, ds: r => r.ds_count, ver: r => r.version || 0, author: r => (r.created_by_name || '').toLowerCase(),
  date: r => dayKey(r.created_at),
}

function Head({ k, label, right, sortKey, sortDir, onSort }) {
  const on = k && k === sortKey
  return (
    <span onClick={k ? () => onSort(k) : undefined}
          style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                   color: on ? 'var(--text-primary)' : 'var(--text-faint)', textAlign: right ? 'right' : 'left',
                   cursor: k ? 'pointer' : 'default', userSelect: 'none' }}>
      {label}{on ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}
    </span>
  )
}

function Pin({ on, tone, label, count, onClick }) {
  const dot = tone === 'warning' ? 'var(--warning)' : 'var(--text-faint)'
  return (
    <button type="button" onClick={onClick}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 12px', borderRadius: 9, fontFamily: UI,
                     border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                     background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }} />
      {label}<span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-faint)' }}>{count}</span>
    </button>
  )
}

export default function TemplatesTab({ onOpen, reloadKey = 0 }) {
  const router = useRouter()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('все')
  const [pin, setPin] = useState(null)
  const [sortKey, setSortKey] = useState('ent')
  const [sortDir, setSortDir] = useState(1)

  // Перечитываем после закрытия окна шаблона: пересохранили — флаг «пересохранить» должен уйти сразу.
  useEffect(() => {
    annexTemplatesApi.list().then(r => { setRows((r || []).map(norm)); setErr('') }).catch(() => setErr('Не удалось загрузить шаблоны'))
  }, [reloadKey])

  const all = useMemo(() => rows || [], [rows])
  // «Без основного» считает ДОГОВОРЫ, а не шаблоны: договоры в реестре, у которых ни один шаблон не ★.
  const noMain = useMemo(() => {
    const has = {}
    all.forEach(r => { if (r.scope === 'custom') has[r.contract_id] = has[r.contract_id] || r.is_main })
    return new Set(Object.keys(has).filter(id => !has[id]).map(Number))
  }, [all])
  const counts = {
    все: all.length, основной: all.filter(r => KIND(r) === 'основной').length,
    именованный: all.filter(r => KIND(r) === 'именованный').length, базовый: all.filter(r => r.scope === 'base').length,
  }
  const pins = {
    resave: all.filter(r => r.literal_words > 0).length,
    nomain: noMain.size,
    stale: all.filter(stale).length,
  }

  const view = useMemo(() => {
    const s = q.trim().toLowerCase()
    const hit = r => !s || [r.title, ...(r.brands || []), r.contract && r.contract.no, ent(r), r.entity && r.entity.inn,
                            r.created_by_name, r.author].some(v => (v || '').toLowerCase().includes(s))
    const pass = r => (kind === 'все' || KIND(r) === kind) && hit(r)
      && (pin !== 'resave' || r.literal_words > 0)
      && (pin !== 'nomain' || noMain.has(r.contract_id))
      && (pin !== 'stale' || stale(r))
    const list = all.filter(pass)
    const within = (a, b) => {
      const f = SORT[sortKey]
      if (f) { const x = f(a), y = f(b); if (x !== y) return (x > y ? 1 : -1) * sortDir }
      return (b.is_main - a.is_main) || (a.title || '').localeCompare(b.title || '', 'ru')
    }
    const base = list.filter(r => r.scope === 'base').sort(within)
    const groupDir = sortKey === 'ent' ? sortDir : 1
    const noDir = sortKey === 'no' ? sortDir : 1
    const rest = list.filter(r => r.scope !== 'base').sort((a, b) =>
      (ent(a).localeCompare(ent(b), 'ru') * groupDir)
      || (cno(a).localeCompare(cno(b), 'ru') * noDir)
      || within(a, b))
    return [...base, ...rest]
  }, [all, q, kind, pin, sortKey, sortDir, noMain])

  const onSort = (k) => { if (k === sortKey) setSortDir(d => -d); else { setSortKey(k); setSortDir(1) } }
  const togglePin = (p) => setPin(x => (x === p ? null : p))
  const go = (e, href) => { e.stopPropagation(); if (href) router.push(href) }

  if (err) return <div style={{ padding: '14px 0', fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>
  if (!rows) return <div style={{ padding: '14px 0', fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</div>

  const ents = new Set(view.filter(r => r.scope !== 'base').map(ent)).size
  const contracts = new Set(view.filter(r => r.contract).map(r => r.contract.id)).size
  const summary = `${view.length} ${plural(view.length, 'шаблон', 'шаблона', 'шаблонов')} · ${ents} ${plural(ents, 'юрлицо', 'юрлица', 'юрлиц')} · ${contracts} ${plural(contracts, 'договор', 'договора', 'договоров')}`
  const segLabel = (k, label) => <>{label}<span style={{ marginLeft: 6, fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{counts[k]}</span></>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontFamily: UI, paddingTop: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Шаблон, бренд, договор, юрлицо, автор…"
               style={{ ...inp, width: 300, height: 34 }} />
        <Segmented value={kind} onChange={setKind}
                   options={[['все', 'Все'], ['основной', 'основной'], ['именованный', 'именованный'], ['базовый', 'базовый']]
                     .map(([k, l]) => ({ value: k, label: segLabel(k, l) }))} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {pins.resave > 0 && <Pin on={pin === 'resave'} tone="warning" label="Пересохранить" count={pins.resave} onClick={() => togglePin('resave')} />}
        {pins.nomain > 0 && <Pin on={pin === 'nomain'} tone="warning" label="Без основного" count={pins.nomain} onClick={() => togglePin('nomain')} />}
        {pins.stale > 0 && <Pin on={pin === 'stale'} tone="muted" label="Не применялись 4 мес." count={pins.stale} onClick={() => togglePin('stale')} />}
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{summary}</span>
      </div>

      <div style={{ overflowX: 'auto', maxWidth: '100%' }}>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 1480 }}>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '0 12px 8px', borderBottom: '1px solid var(--border-card)' }}>
            {HEAD.map(([k, label, right], i) => (
              <Head key={k || i} k={k} label={label} right={right} sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            ))}
          </div>

          {view.map((r, i) => {
            const prev = view[i - 1]
            const base = r.scope === 'base'
            const newEnt = !prev || (prev.scope === 'base') !== base || ent(prev) !== ent(r)
            const newContract = newEnt || !prev.contract || !r.contract || prev.contract.id !== r.contract.id
            const k = KIND(r)
            const [kBg, kFg] = KIND_TONE[k]
            const d = ageDays(r.ds_last_at)
            const old = !base && d > STALE
            const edited = r.version > 1
            const editor = edited ? (r.author && r.author !== r.created_by_name ? `правил: ${r.author}` : 'правил: он же') : ''
            const changed = edited && dayKey(r.updated_at) !== dayKey(r.created_at)
            return (
              <div key={r.id} role="button" tabIndex={0} title="Открыть шаблон в конструкторе"
                   onClick={() => onOpen(r)} onKeyDown={e => { if (e.key === 'Enter') onOpen(r) }}
                   style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', minHeight: 44, padding: '0 12px',
                            borderTop: `1px solid ${i === 0 ? 'transparent' : newEnt ? 'var(--border-card)' : 'var(--border-row)'}`, cursor: 'pointer' }}
                   onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }}
                   onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  {newEnt && (base
                    ? <><span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)' }}>Общий для формата</span>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>—</span></>
                    : <><span onClick={e => go(e, r.entity && r.entity.id && `/directory/counterparties/${r.entity.id}`)}
                              title={r.entity && r.entity.id ? 'Открыть карточку контрагента' : ''}
                              style={{ ...ellipsis, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', cursor: r.entity && r.entity.id ? 'pointer' : 'default' }}>{ent(r) || '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{(r.entity && r.entity.inn) || '—'}</span></>)}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  {newContract && (base
                    ? <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>—</span>
                    : <>
                        <span onClick={e => go(e, `/directory/contracts/${r.contract.id}`)} title="Открыть карточку договора"
                              style={{ ...ellipsis, fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', cursor: 'pointer' }}>{r.contract.no || '—'}</span>
                        <span title={r.contract.last_no ? `Последний № ${r.contract.last_no} — ${SRC_HINT[r.contract.last_no_source] || ''}` : 'По договору ещё не выдано ни одного номера'}
                              style={{ display: 'inline-flex', gap: 6, fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                          <span style={{ color: r.contract.annex_word ? 'var(--text-secondary)' : 'var(--warning-fg)', fontWeight: 700 }}>
                            {WORD[r.contract.annex_word] || 'вид не выбран'}
                          </span>
                          <span>{r.contract.last_no ? `посл. № ${r.contract.last_no}` : 'номеров нет'}</span>
                        </span>
                        {noMain.has(r.contract_id) && (
                          <span title="У договора нет основного шаблона — ДС соберётся по базовому"
                                style={{ display: 'inline-flex', alignSelf: 'flex-start', alignItems: 'center', gap: 5, fontFamily: MONO, fontSize: 8.5, fontWeight: 700,
                                         letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--warning-fg)' }}>
                            <span style={{ width: 5, height: 5, borderRadius: 1, background: 'var(--warning)' }} />нет основного
                          </span>
                        )}
                      </>)}
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span title={r.is_main ? 'Основной: подставляется по умолчанию при сборке ДС' : ''}
                        style={{ width: 12, flex: '0 0 12px', fontSize: 12, lineHeight: 1, color: 'var(--accent)' }}>{r.is_main ? '★' : ''}</span>
                  <span title={r.title} style={{ ...ellipsis, fontSize: 13, fontWeight: 700 }}>{r.title || r.base_title || '—'}</span>
                </span>
                <span title={r.brands.join(', ')}
                      style={{ ...ellipsis, fontSize: 12.5, fontWeight: r.brands.length ? 600 : 500,
                               color: r.brands.length ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                  {base ? '—' : (r.brands.length ? r.brands.join(', ') : 'все бренды')}
                </span>
                <span><span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 6,
                                     background: kBg, color: kFg, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{k}</span></span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{r.items}</span>
                <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: r.ds_count ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{r.ds_count}</span>
                  <span title="Последний ДС по шаблону"
                        style={{ fontFamily: MONO, fontSize: 9.5, whiteSpace: 'nowrap', color: old ? 'var(--warning-fg)' : 'var(--text-faint)' }}>
                    {r.ds_last_at ? `посл. ${fmtDate(r.ds_last_at).slice(0, 5)}${old ? ` · ${Math.round(d / 30)} мес.` : ''}` : '—'}
                  </span>
                </span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{r.version ? `v${r.version}` : '—'}</span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  <span style={{ ...ellipsis, fontSize: 12.5, color: 'var(--text-secondary)' }}>{r.created_by_name || '—'}</span>
                  {!!editor && <span style={{ ...ellipsis, fontSize: 10.5, color: 'var(--text-faint)' }}>{editor}</span>}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)' }}>{fmtDateOfMoment(r.created_at)}</span>
                  {changed && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{`изм. ${fmtDateOfMoment(r.updated_at)}`}</span>}
                </span>
                <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }}>
                  {r.literal_words > 0 && (
                    <span title="Вид документа записан словом — пересохраните шаблон в конструкторе"
                          style={{ ...chip('var(--warning-tint)', 'var(--warning-fg)', 'var(--warning-border)'), height: 24, padding: '0 9px', fontSize: 11, fontWeight: 700 }}>
                      пересохранить
                    </span>
                  )}
                </span>
              </div>
            )
          })}
          {!view.length && <div style={{ padding: '18px 12px', fontSize: 13, color: 'var(--text-muted)' }}>Под фильтр ничего не попало</div>}
        </div>
      </div>
    </div>
  )
}
