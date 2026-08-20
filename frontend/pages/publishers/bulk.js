import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { MONO, UI, IconBtn, inp, sel, btn, headCell, card, CAP } from '@/components/salesTableKit'
import { INTEG_TONE_SOLID as INTEG_TONE, STATUS_TONE, nextStatus, Pin }
  from '@/components/publishers/kit'

// Экран быстрого заполнения: строка на площадку, всё правится одним кликом.
// Заведён под первичное наполнение реестра — переносить из Excel было нечего, и на
// 41 площадку приходилось 8 отметок услуг; по карточкам это 41 заход.
//
// Сюда вынесено только то, что помещается в клетку: галочки, короткие числа и пины.
// Списки (юрлица, договоры, контакты, документы) и замеры трафика остаются в карточке —
// таблица в таблице не заполняется быстрее, она просто перестаёт читаться.
//
// Сохранение идёт сразу по клику: «Отмены» тут нет, обратное действие — снять галочку.
// Состояние обновляется на месте, без перезагрузки списка: иначе после каждой отметки
// таблица прыгает к началу.

const SURFACES = [['web', 'WEB'], ['app', 'APP']]
const PLATFORMS = [['android', 'AND'], ['ios', 'IOS']]
const FLAGS = [['our_code', 'К', 'код наш'], ['is_exclusive', 'ЭКС', 'эксклюзив'],
  ['has_dsp', 'DSP', 'DSP'], ['self_promo', 'САМ', 'самореклама']]
const TZ = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

const cellBox = { padding: '0 6px', minWidth: 0, display: 'flex', alignItems: 'center' }
const tick = { width: 16, height: 16, cursor: 'pointer' }
const numInp = { ...inp, padding: '3px 6px', fontSize: 12, fontFamily: MONO, textAlign: 'right',
  width: '100%' }

// Ячейка услуги: пусто → WEB → APP → WEB·APP → пусто. Поверхность, которой у площадки
// нет, из цикла выпадает — база запрещает услугу на несуществующей поверхности.
const SvcCell = ({ on, available, onPick, title }) => {
  const label = on.length ? on.map(k => k.toUpperCase().slice(0, 1)).join('·') : ''
  const dead = !available.length
  return (
    <span title={dead ? 'Поверхностей нет — сначала отметьте WEB или APP' : title}
      onClick={() => { if (!dead) onPick() }}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 58, height: 26, borderRadius: 8, fontFamily: MONO, fontSize: 11, fontWeight: 700,
        cursor: dead ? 'not-allowed' : 'pointer', userSelect: 'none',
        background: on.length ? 'var(--accent-tint)' : (dead ? 'transparent' : 'var(--bg-subtle)'),
        color: on.length ? 'var(--accent)' : 'var(--text-faint)',
        border: `1px ${dead ? 'dashed' : 'solid'} ${on.length ? 'var(--accent-border)' : 'var(--border-card)'}`,
        opacity: dead ? .45 : 1 }}>
      {label || (dead ? '—' : '·')}
    </span>
  )
}

export default function PublishersBulk() {
  const router = useRouter()
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ services: [], statuses: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(0)      // сколько запросов в полёте
  const [perms, setPerms] = useState({})
  const [search, setSearch] = useState('')
  const [onlyEmpty, setOnlyEmpty] = useState(false)

  // Правит либо тот, кому открыты «Площадки» целиком, либо тот, кого посадили на одно
  // «Заполнение» (первичное наполнение реестра) — второму карточка доступна на чтение.
  const mayEdit = can(perms, 'dir_publishers_bulk', 'edit') || can(perms, 'dir_publishers', 'edit')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [r, m] = await Promise.all([
        api.get('/publishers', auth()),
        api.get('/publishers/meta', auth()),
      ])
      setItems(r.data.items); setMeta(m.data)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить площадки') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    let p = {}
    try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { p = {} }
    setPerms(p)
    // Экран закрыт своим правом: без него уводим на первый доступный раздел, а не
    // оставляем пустую таблицу с 403 — по прямой ссылке это выглядело как поломка.
    if (!can(p, 'dir_publishers_bulk', 'view')) { router.push(firstAllowedHref(p, localStorage.getItem('role'))); return }
    load()
  }, [])

  // Общая обёртка: сначала правим строку на месте, потом шлём. Если сервер отказал —
  // возвращаем как было и показываем причину, а не оставляем ложную галочку.
  const send = async (id, apply, request) => {
    const before = items.find(x => x.id === id)
    setItems(prev => prev.map(x => (x.id === id ? apply(x) : x)))
    setSaving(n => n + 1)
    try {
      await request()
      setError('')
    } catch (e) {
      setItems(prev => prev.map(x => (x.id === id ? before : x)))
      setError(e.response?.data?.detail || 'Не удалось сохранить')
    } finally { setSaving(n => n - 1) }
  }

  const setSurface = (p, kind, patch) => {
    const cur = p.surfaces?.[kind] || {}
    const body = { integration_status: cur.integration_status || 'НЕТ', we_work: !!cur.we_work,
      coverage_percent: cur.coverage_percent ?? null, figma_url: cur.figma_url || null,
      note: cur.note || null, ...patch }
    return send(p.id,
      x => ({ ...x, surfaces: { ...x.surfaces, [kind]: { ...cur, ...body } } }),
      () => api.put(`/publishers/${p.id}/surfaces/${kind}`, body, auth()))
  }

  const dropSurface = (p, kind) => send(p.id,
    x => {
      const next = { ...x.surfaces }
      delete next[kind]
      // Услуги несуществующей поверхности снимаются вместе с ней — так же, как это
      // делает база каскадом.
      return { ...x, surfaces: next,
        services: (x.services || [])
          .map(s => ({ ...s, surfaces: s.surfaces.filter(k => k !== kind) }))
          .filter(s => s.surfaces.length) }
    },
    () => api.delete(`/publishers/${p.id}/surfaces/${kind}`, auth()))

  const setPlatform = (p, pk, isActive) => {
    const app = p.surfaces?.app
    if (!app) return
    const cur = app.platforms?.[pk] || {}
    const body = { integration_status: cur.integration_status || 'ПОДГОТОВКА', is_active: isActive }
    return send(p.id,
      x => ({ ...x, surfaces: { ...x.surfaces,
        app: { ...x.surfaces.app, platforms: { ...(x.surfaces.app.platforms || {}), [pk]: { ...cur, ...body } } } } }),
      () => api.put(`/publishers/${p.id}/surfaces/app/platforms/${pk}`, body, auth()))
  }

  const toggleService = (p, svc, kind, on) => send(p.id,
    x => {
      const list = (x.services || []).filter(s => s.service_id !== svc.id)
      const cur = (x.services || []).find(s => s.service_id === svc.id)
      const kinds = new Set(cur ? cur.surfaces : [])
      if (on) kinds.add(kind); else kinds.delete(kind)
      const next = kinds.size ? [...list, { service_id: svc.id, name: svc.name, surfaces: [...kinds] }] : list
      return { ...x, services: next.sort((a, b) => a.name.localeCompare(b.name, 'ru')) }
    },
    () => api.put(`/publishers/${p.id}/services`,
      { surface_kind: kind, service_id: svc.id, is_active: on }, auth()))

  // Цикл ячейки услуги: пусто → первая доступная поверхность → вторая → обе → пусто.
  const cycleService = async (p, svc) => {
    const available = SURFACES.map(([k]) => k).filter(k => p.surfaces?.[k])
    const cur = (p.services || []).find(s => s.service_id === svc.id)
    const on = new Set(cur ? cur.surfaces : [])
    const states = [[], ...available.map(k => [k]), available.length > 1 ? available : null].filter(Boolean)
    const now = states.findIndex(st => st.length === on.size && st.every(k => on.has(k)))
    const next = states[(now + 1) % states.length]
    for (const k of available) {
      const was = on.has(k), will = next.includes(k)
      if (was !== will) await toggleService(p, svc, k, will)
    }
  }

  const patchField = (p, key, value) => send(p.id,
    x => ({ ...x, [key]: value }),
    () => api.patch(`/publishers/${p.id}`, { [key]: value }, auth()))

  const services = meta.services || []
  const filtered = items.filter(p => {
    if (p.status === 'АРХИВ') return false
    if (onlyEmpty && (p.services_supported || 0) > 0) return false
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [p.name, p.domain, p.network].some(v => (v || '').toLowerCase().includes(q))
  })

  const GRID = `260px 150px 190px 190px 130px ${services.map(() => '76px').join(' ')} 190px 84px 104px`

  return (
    <>
      <Head><title>Заполнение · Паблишеры</title></Head>
      <Navbar active="publishers" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <div style={{ ...card, padding: '18px 22px 14px' }}>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: '0 6px 0 0' }}>Быстрое заполнение</h1>
            <span style={{ ...CAP, marginBottom: 0 }}>площадок {filtered.length} из {items.length}</span>
            <input style={{ ...inp, width: 240 }} placeholder="площадка, домен, сеть…"
              value={search} onChange={e => setSearch(e.target.value)} />
            <button style={btn(onlyEmpty)} onClick={() => setOnlyEmpty(v => !v)}
              title="Площадки, у которых не отмечено ни одной услуги">
              {onlyEmpty ? 'Показать все' : 'Только без услуг'}
            </button>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              <span style={{ ...CAP, marginBottom: 0, color: saving ? 'var(--accent)' : 'var(--text-faint)' }}>
                {saving ? 'сохраняю…' : 'сохранено'}
              </span>
              <IconBtn title="Перечитать с сервера" onClick={load}>
                <svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg>
              </IconBtn>
              <a href="/publishers" style={{ ...btn(false), textDecoration: 'none' }}>К реестру</a>
            </span>
          </div>

          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
            padding: '8px 12px', background: '#F6F8FF', border: '1px solid var(--accent-border)',
            borderRadius: 12, marginBottom: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
            <span style={{ ...CAP, marginBottom: 0, color: 'var(--accent)' }}>как заполнять</span>
            <span>клетка услуги листает: пусто → WEB → APP → оба</span>
            <span>пин статуса листает цикл подключения</span>
            <span>всё сохраняется сразу, «Отмены» нет</span>
            <span style={{ marginLeft: 'auto' }}>списки и трафик — в карточке площадки</span>
          </div>

          {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
            color: 'var(--danger)', padding: '9px 13px', borderRadius: 10, marginBottom: 10, fontSize: 13 }}>{error}</div>}
          {loading && <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>}

          {!loading && (
            <div style={{ overflowX: 'auto', maxWidth: '100%' }}>
              <div style={{ minWidth: 2100 }}>

                <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10,
                  borderBottom: '1px solid var(--border-card)', alignItems: 'end' }}>
                  <div style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', zIndex: 2 }}>
                    {headCell('Площадка')}
                  </div>
                  {headCell('Статус')}
                  {headCell('WEB · есть · работаем')}
                  {headCell('APP · есть · работаем')}
                  {headCell('Платформы')}
                  {services.map(s => (
                    <div key={s.id} title={s.name} style={{ ...CAP, marginBottom: 8, textAlign: 'center',
                      lineHeight: 1.25, wordBreak: 'break-word' }}>
                      {s.name}
                    </div>
                  ))}
                  {headCell('Отметки')}{headCell('CPM', true)}{headCell('Пояс')}
                </div>

                {filtered.map(p => {
                  const web = p.surfaces?.web
                  const app = p.surfaces?.app
                  const [stBg, stFg] = STATUS_TONE[p.status] || STATUS_TONE['ПЕРЕГОВОРЫ']
                  return (
                    <div key={p.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10,
                      alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-row)' }}>

                      <div style={{ ...cellBox, position: 'sticky', left: 0, background: 'var(--bg-card)',
                        zIndex: 1, flexDirection: 'column', alignItems: 'flex-start', gap: 1 }}>
                        <a href={`/publishers/${p.id}`} style={{ fontSize: 13, fontWeight: 700,
                          color: 'var(--text-primary)', textDecoration: 'none' }}>{p.name}</a>
                        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{p.domain}</span>
                      </div>

                      <div style={cellBox}>
                        <select style={{ ...sel, padding: '3px 5px', fontSize: 11.5, width: '100%',
                          color: stFg, background: stBg, border: 'none', borderRadius: 8, fontWeight: 700 }}
                          disabled={!mayEdit} value={p.status}
                          onChange={e => patchField(p, 'status', e.target.value)}>
                          {(meta.statuses || []).map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </div>

                      {SURFACES.map(([kind]) => {
                        const s = kind === 'web' ? web : app
                        return (
                          <div key={kind} style={{ ...cellBox, gap: 8 }}>
                            <input type="checkbox" style={tick} checked={!!s} disabled={!mayEdit}
                              title="Поверхность есть у площадки"
                              onChange={e => (e.target.checked
                                ? setSurface(p, kind, { integration_status: 'НЕТ', we_work: false })
                                : dropSurface(p, kind))} />
                            <input type="checkbox" style={tick} checked={!!s?.we_work} disabled={!mayEdit || !s}
                              title="Мы с ней работаем"
                              onChange={e => setSurface(p, kind, { we_work: e.target.checked })} />
                            {s
                              ? <Pin text={s.integration_status}
                                  tone={INTEG_TONE[s.integration_status] || INTEG_TONE['НЕТ']}
                                  title="Нажмите, чтобы сменить статус"
                                  onClick={mayEdit ? () => setSurface(p, kind,
                                    { integration_status: nextStatus(s.integration_status) }) : undefined} />
                              : <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>нет</span>}
                          </div>
                        )
                      })}

                      <div style={{ ...cellBox, gap: 10 }}>
                        {PLATFORMS.map(([pk, label]) => {
                          const pl = app?.platforms?.[pk]
                          return (
                            <label key={pk} title={app ? `${label}: работаем` : 'Сначала отметьте APP'}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10.5,
                                fontFamily: MONO, color: app ? 'var(--text-secondary)' : 'var(--text-faint)',
                                cursor: app && mayEdit ? 'pointer' : 'default' }}>
                              <input type="checkbox" style={tick} disabled={!mayEdit || !app}
                                checked={!!pl?.is_active}
                                onChange={e => setPlatform(p, pk, e.target.checked)} />
                              {label}
                            </label>
                          )
                        })}
                      </div>

                      {services.map(svc => {
                        const cur = (p.services || []).find(s => s.service_id === svc.id)
                        const available = SURFACES.map(([k]) => k).filter(k => p.surfaces?.[k])
                        return (
                          <div key={svc.id} style={{ ...cellBox, justifyContent: 'center' }}>
                            <SvcCell on={cur ? cur.surfaces : []} available={mayEdit ? available : []}
                              title={`${svc.name}: ${cur ? cur.surfaces.join(' · ') : 'не отмечена'}`}
                              onPick={() => cycleService(p, svc)} />
                          </div>
                        )
                      })}

                      <div style={{ ...cellBox, gap: 6 }}>
                        {FLAGS.map(([key, label, title]) => {
                          const on = key === 'self_promo' ? p.self_promo === 'ДА' : !!p[key]
                          return (
                            <label key={key} title={title}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 3,
                                fontFamily: MONO, fontSize: 9.5,
                                color: on ? 'var(--accent)' : 'var(--text-faint)',
                                cursor: mayEdit ? 'pointer' : 'default' }}>
                              <input type="checkbox" style={tick} checked={on} disabled={!mayEdit}
                                onChange={e => patchField(p, key === 'self_promo' ? 'self_promo' : key,
                                  key === 'self_promo' ? (e.target.checked ? 'ДА' : 'НЕТ') : e.target.checked)} />
                              {label}
                            </label>
                          )
                        })}
                      </div>

                      <div style={cellBox}>
                        <input style={numInp} disabled={!mayEdit} defaultValue={p.cpm_contract ?? ''}
                          onBlur={e => {
                            const raw = e.target.value.trim()
                            const v = raw === '' ? null : parseFloat(raw.replace(',', '.'))
                            if (v !== (p.cpm_contract ?? null) && !Number.isNaN(v)) patchField(p, 'cpm_contract', v)
                          }} />
                      </div>

                      <div style={cellBox}>
                        <select style={{ ...sel, padding: '3px 4px', fontSize: 11, fontFamily: MONO, width: '100%' }}
                          disabled={!mayEdit} value={p.timezone_offset ?? 0}
                          onChange={e => patchField(p, 'timezone_offset', parseInt(e.target.value, 10))}>
                          {TZ.map(o => <option key={o} value={o}>{o === 0 ? 'МСК' : `МСК${o > 0 ? '+' : '−'}${Math.abs(o)}`}</option>)}
                        </select>
                      </div>
                    </div>
                  )
                })}

                {!filtered.length && (
                  <div style={{ padding: '18px 8px', color: 'var(--text-muted)', fontSize: 13 }}>Ничего не найдено.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
