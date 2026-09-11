/**
 * Админка трафика — три вкладки: «Настройка блоков», «Балансировщик» и «Скрипт».
 *
 * Вкладка 1 (этот файл): каталог площадок и блоков для DSP.
 * Вкладка 2 (components/traffic/Balancer): расчётная ёмкость площадки на поверхность.
 * Вкладка 3 (components/traffic/SiteScript): наш счётчик для вставки в <head> площадки
 * и разделение площадок на «код стоит» / «кода нет» по sales_publishers.our_code.
 * Право на обе одно — traffic_catalog (ключ неизменяем; переименование раздела его не трогает).
 *
 * Слева реестр площадок (из реестра паблишеров — сюда попадают только заведённые там).
 * Справа выбранная площадка: вкладки поверхностей web/app (`sales_publisher_surfaces`), у
 * каждой свой ms_publisher_id и блок по умолчанию «кукуха2» (авто-цепляется к креативу, но
 * скрыт из статистики кабинета), ниже — наполняемая таблица блоков. Первичное наполнение —
 * импорт из xlsx (scripts.import_publisher_blocks), дальше правится здесь.
 *
 * Право traffic_catalog (view/create/edit/delete). ios/android — на будущее (платформы).
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, card, CAP, btn, btnSm, inp, sel, th, td, chip }
  from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import Balancer from '@/components/traffic/Balancer'
import SiteScript from '@/components/traffic/SiteScript'
import api, { auth } from '@/lib/api'

const PAGE_TYPES = ['главная', 'каталог', 'карточка товара', 'корзина', 'статьи', 'акции', 'лк']
const NETWORKS = ['x-simb-web', 'x-simb']
const SURFACE_LABEL = { web: 'Web', app: 'App', ios: 'iOS', android: 'Android' }
// Web всегда первым; app — следом, ios/android — на будущее. РК одной поверхности,
// и веб — основной носитель, поэтому он открывается по умолчанию (app — только если веба нет).
const SURFACE_ORDER = { web: 0, app: 1, ios: 2, android: 3 }
const sortSurfaces = (ss) => [...(ss || [])].sort(
  (a, b) => (SURFACE_ORDER[a.kind] ?? 9) - (SURFACE_ORDER[b.kind] ?? 9))
const defaultSurface = (ss) => (ss || []).find((s) => s.kind === 'web') || (ss || [])[0]

// Иконка-пиктограмма раздела (сетка блоков) перед заголовком.
const CatalogIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
  </svg>
)

// Карандаш — код площадки прячем под него, чтобы случайно не изменить.
const PencilIcon = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </svg>
)
const NET_TONE = {
  'x-simb-web': ['var(--accent-tint, #e6eeff)', 'var(--accent)'],
  'x-simb': ['var(--warning-tint)', 'var(--warning-text)'],
}

export default function TrafficCatalog() {
  const [pubs, setPubs] = useState([])
  const [q, setQ] = useState('')
  const [selId, setSelId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [tab, setTab] = useState(null)
  const [saving, setSaving] = useState(false)
  const [editCode, setEditCode] = useState(false)
  const [codeVal, setCodeVal] = useState('')
  const [codeErr, setCodeErr] = useState('')   // отказ по коду — строкой рядом с полем
  const [types, setTypes] = useState([])        // типовые разделы (накопитель)
  const [vpop, setVpop] = useState(null)         // {rect, blockId, value} — выбор раздела
  const [adminTab, setAdminTab] = useState('blocks')   // вкладка админки: blocks | balancer | script

  /* Права читаются ИЗ СНИМКА в localStorage, поэтому только после монтирования:
     на сервере localStorage нет, и вычисление прямо в теле компонента дало бы
     расхождение разметки. Аргументов у `can` ТРИ — `(perms, section, action)`;
     вызов с двумя молча возвращал false всем, кроме админа (11.09.2026). */
  const [rights, setRights] = useState({})
  useEffect(() => {
    const p = getPermissions()
    setRights({ edit: can(p, 'traffic_catalog', 'edit'),
                create: can(p, 'traffic_catalog', 'create'),
                del: can(p, 'traffic_catalog', 'delete') })
  }, [])
  const mayEdit = !!rights.edit
  const mayCreate = !!rights.create
  const mayDelete = !!rights.del

  const loadPubs = useCallback(async () => {
    // Обработчика ошибки не было ВОВСЕ (не пустой catch, а необработанный отказ):
    // каталог площадок оставался пустым, и это выглядело как «площадок нет».
    try {
      const r = await api.get('/traffic-catalog/publishers', auth())
      setPubs(r.data || [])
    } catch (e) {
      setCodeErr('Каталог площадок не загрузился — обновите страницу')
    }
  }, [])
  useEffect(() => { loadPubs() }, [loadPubs])

  useEffect(() => {
    api.get('/traffic-catalog/page-types', auth()).then((r) => setTypes(r.data || []))
      // Пустой справочник разделов = пустая выпадашка, которая читается как «значений
      // нет», а не как «не смогли спросить».
      .catch(() => setCodeErr('Справочник разделов не загрузился — выпадающий список пуст'))
  }, [])

  const openPub = async (id) => {
    setSelId(id)
    setEditCode(false)
    const r = await api.get(`/traffic-catalog/publisher/${id}`, auth())
    const surfaces = sortSurfaces(r.data.surfaces)
    setDetail({ ...r.data, surfaces })
    setTab(defaultSurface(surfaces)?.id ?? null)   // web первым, app — если веба нет
  }

  const exportBlocks = async () => {
    const r = await api.get('/traffic-catalog/blocks/export', { ...auth(), responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([r.data]))
    const a = document.createElement('a')
    a.href = url; a.download = 'Каталог блоков.xlsx'; document.body.appendChild(a); a.click()
    a.remove(); URL.revokeObjectURL(url)
  }

  /* Код площадки — средняя часть кода пары размещения. Уникален по всем площадкам:
     два одинаковых кода означают два разных размещения с одним именем, и разобрать их
     потом нельзя. Проверку делает сервер (409), здесь она ещё и ЖИВАЯ — по уже
     загруженному списку, — чтобы отказ пришёл до нажатия, а не после. */
  const codeDup = (val) => {
    const v = (val || '').trim().toUpperCase()
    if (!v) return null
    return pubs.find(x => x.id !== selId && (x.code || '').toUpperCase() === v) || null
  }

  const saveCode = async () => {
    const dup = codeDup(codeVal)
    if (dup) { setCodeErr(`Код «${codeVal.trim().toUpperCase()}» уже у площадки ${dup.name}`); return }
    try {
      await api.put(`/traffic-catalog/publisher/${selId}/code`,
        { code: codeVal.trim() || null }, auth())
      setEditCode(false)
      setCodeErr('')
      await reloadDetail()
      await loadPubs()          // список держит коды — по ним считается «без кода» и дубли
    } catch (e) {
      setCodeErr(e?.response?.data?.detail || 'Не удалось сохранить код')
    }
  }

  const reloadDetail = async () => {
    if (selId) {
      const r = await api.get(`/traffic-catalog/publisher/${selId}`, auth())
      setDetail({ ...r.data, surfaces: sortSurfaces(r.data.surfaces) })
    }
    loadPubs()
  }

  const surface = detail?.surfaces?.find((s) => s.id === tab) || null

  // локальная правка поля поверхности/блока — правим detail в состоянии, пишем по действию
  const patchSurface = (patch) => setDetail((d) => ({
    ...d, surfaces: d.surfaces.map((s) => s.id === tab ? { ...s, ...patch } : s),
  }))
  const patchBlock = (bid, patch) => setDetail((d) => ({
    ...d,
    surfaces: d.surfaces.map((s) => s.id !== tab ? s : {
      ...s, blocks: s.blocks.map((b) => b.id === bid ? { ...b, ...patch } : b),
    }),
  }))

  const saveSurface = async () => {
    setSaving(true)
    try {
      await api.put(`/traffic-catalog/surface/${surface.id}`, {
        ms_publisher_id: surface.ms_publisher_id || null,
        default_ms_block_id: surface.default_ms_block_id || null,
      }, auth())
      await reloadDetail()
    } finally { setSaving(false) }
  }

  const saveBlock = async (b) => {
    await api.put(`/traffic-catalog/block/${b.id}`, {
      ms_block_id: b.ms_block_id || null, name: b.name || null,
      page_type: b.page_type || null, network: b.network || null,
      is_active: b.is_active,
    }, auth())
    loadPubs()
  }
  const applyType = async (blockId, v) => {
    patchBlock(blockId, { page_type: v })
    if (v && !types.includes(v)) setTypes((x) => [...x, v])
    const b = surface?.blocks.find((x) => x.id === blockId)
    if (b) await saveBlock({ ...b, page_type: v })
  }

  const addBlock = async () => {
    const r = await api.post(`/traffic-catalog/surface/${surface.id}/block`,
      { name: '', page_type: '', network: NETWORKS[surface.kind === 'app' ? 1 : 0], is_active: true }, auth())
    setDetail((d) => ({
      ...d, surfaces: d.surfaces.map((s) => s.id === tab ? { ...s, blocks: [...s.blocks, r.data] } : s),
    }))
    loadPubs()
  }
  const delBlock = async (id) => {
    await api.delete(`/traffic-catalog/block/${id}`, auth())
    setDetail((d) => ({
      ...d, surfaces: d.surfaces.map((s) => s.id === tab ? { ...s, blocks: s.blocks.filter((b) => b.id !== id) } : s),
    }))
    loadPubs()
  }
  const addSurface = async (kind) => {
    await api.post(`/traffic-catalog/publisher/${selId}/surface`, { kind }, auth())
    await reloadDetail()
  }

  const shown = pubs.filter((p) => {
    const s = q.trim().toLowerCase()
    return !s || (p.name || '').toLowerCase().includes(s) || (p.code || '').toLowerCase().includes(s)
      || (p.domain || '').toLowerCase().includes(s)
  })
  const missingKinds = ['web', 'app'].filter((k) => !detail?.surfaces?.some((s) => s.kind === k))

  const kInCatalog = pubs.filter((p) => p.ms_surfaces > 0).length
  const kSurfaces = pubs.reduce((a, p) => a + (p.ms_surfaces || 0), 0)
  const kBlocks = pubs.reduce((a, p) => a + (p.blocks || 0), 0)
  // Площадки без буквенного кода. Считаем и показываем отдельной плиткой: код —
  // средняя часть кода пары размещения, и без него отправка материала упирается в
  // справочник на последнем шаге. Красным, потому что это долг, а не статистика.
  const noCode = pubs.filter(p => !(p.code || '').trim())

  const KPI = [
    ['Площадок в каталоге', kInCatalog], ['Поверхностей с МС', kSurfaces],
    ['Рекламных блоков', kBlocks], ['Без кода', noCode.length, !!noCode.length],
  ]

  return (
    <>
      <Head><title>Каталог площадок · Трафики</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '18px 24px 60px', fontFamily: UI }}>
        {/* шапка: пиктограмма + заголовок */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 16 }}>
          <span style={{
            width: 40, height: 40, borderRadius: 12, flex: '0 0 auto',
            background: 'var(--accent-tint, #e6eeff)', color: 'var(--accent)',
            display: 'grid', placeItems: 'center',
          }}><CatalogIcon size={21} /></span>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
              Админка трафика</h1>
            <div style={{ ...CAP, marginBottom: 0, marginTop: 2 }}>
              Трафики · площадки, блоки и балансировка</div>
          </div>
        </div>

        {/* вкладки админки */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 18,
          borderBottom: '1px solid var(--border-card)' }}>
          {[['blocks', 'Настройка блоков'], ['balancer', 'Балансировщик'], ['script', 'Скрипт']].map(([k, l]) => (
            <div key={k} onClick={() => setAdminTab(k)} style={{
              padding: '9px 16px', cursor: 'pointer', fontWeight: 700, fontSize: 13.5,
              color: adminTab === k ? 'var(--text-primary)' : 'var(--text-faint)',
              borderBottom: adminTab === k ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1,
            }}>{l}</div>
          ))}
        </div>

        {adminTab === 'balancer' && <Balancer mayEdit={mayEdit} />}
        {adminTab === 'script' && <SiteScript mayEdit={mayEdit} />}

        {adminTab === 'blocks' && (<>
        {/* виджеты */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 18 }}>
          {KPI.map(([label, n, alarm]) => (
            <div key={label} style={{ ...card, padding: '13px 16px',
              ...(alarm ? { borderColor: 'var(--danger-border)', background: 'var(--danger-tint)' } : null) }}>
              <div style={{ fontSize: 25, fontWeight: 800, letterSpacing: '-.02em',
                color: alarm ? 'var(--danger)' : 'var(--text-primary)' }}>{n}</div>
              <div style={{ ...CAP, marginBottom: 0, marginTop: 2 }}>{label}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, alignItems: 'start' }}>
          {/* левая колонка — площадки */}
          <div style={{ ...card, padding: 12 }}>
            <input style={{ ...inp, width: '100%', marginBottom: 10 }} placeholder="Поиск площадки…"
              value={q} onChange={(e) => setQ(e.target.value)} />
            <div style={{ maxHeight: 560, overflow: 'auto' }}>
              {shown.map((p) => (
                <div key={p.id} onClick={() => openPub(p.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 9, padding: '8px 9px', borderRadius: 10,
                    cursor: 'pointer', background: p.id === selId ? 'var(--accent-tint, #eef3ff)' : 'transparent',
                  }}>
                  <span title={p.code ? '' : 'Код не задан'} style={{
                    fontFamily: MONO, fontSize: 11, fontWeight: 700, minWidth: 32,
                    color: p.code ? 'var(--accent)' : 'var(--danger)',
                  }}>{p.code || '—'}</span>
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.name}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
                    {p.ms_surfaces}·{p.blocks}</span>
                </div>
              ))}
              {!shown.length && <div style={{ padding: 12, color: 'var(--text-faint)', fontSize: 13 }}>Ничего не найдено</div>}
            </div>
          </div>

          {/* правая колонка — площадка */}
          <div style={{ ...card, padding: 0, minHeight: 400 }}>
            {!detail && (
              <div style={{ padding: 40, color: 'var(--text-faint)', fontSize: 14, textAlign: 'center' }}>
                Выберите площадку слева</div>
            )}
            {detail && (
              <>
                <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border-card)',
                  display: 'flex', alignItems: 'center', gap: 13 }}>
                  <span style={{
                    width: 42, height: 42, borderRadius: 12, flex: '0 0 auto',
                    background: 'var(--accent-tint, #e6eeff)', color: 'var(--accent)',
                    display: 'grid', placeItems: 'center', fontFamily: MONO, fontWeight: 800, fontSize: 14,
                  }}>{(detail.code || detail.domain || '?').slice(0, 3).toUpperCase()}</span>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 800 }}>{detail.name}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3,
                      fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>
                      <span>код:</span>
                      {!editCode ? (
                        <>
                          <span style={{
                            fontWeight: 700,
                            color: detail.code ? 'var(--text-secondary)' : 'var(--danger)',
                          }}>{detail.code || 'НЕ ЗАДАН'}</span>
                          {mayEdit && (
                            <span title="Изменить код площадки" onClick={() => { setCodeVal(detail.code || ''); setEditCode(true) }}
                              style={{ cursor: 'pointer', color: 'var(--text-faint)', display: 'inline-flex' }}>
                              <PencilIcon /></span>
                          )}
                        </>
                      ) : (
                        <>
                          <input autoFocus value={codeVal} maxLength={8}
                            onChange={(e) => { setCodeVal(e.target.value.toUpperCase()); setCodeErr('') }}
                            onKeyDown={(e) => { if (e.key === 'Enter') saveCode(); if (e.key === 'Escape') { setEditCode(false); setCodeErr('') } }}
                            style={{ ...inp, width: 96, padding: '3px 7px', fontFamily: MONO, fontWeight: 700,
                              borderColor: codeDup(codeVal) ? 'var(--danger)' : 'var(--border-card)' }} />
                          <span title="Сохранить" onClick={saveCode}
                            style={{ cursor: 'pointer', fontWeight: 800,
                              color: codeDup(codeVal) ? 'var(--text-disabled)' : 'var(--income)' }}>✓</span>
                          <span title="Отмена" onClick={() => { setEditCode(false); setCodeErr('') }}
                            style={{ cursor: 'pointer', color: 'var(--text-faint)', fontWeight: 800 }}>✕</span>
                          {!!codeDup(codeVal) && (
                            <span style={{ fontFamily: UI, fontSize: 11.5, color: 'var(--danger)' }}>
                              занят: {codeDup(codeVal).name}
                            </span>
                          )}
                        </>
                      )}
                      <span>· {detail.domain}</span>
                    </div>
                    {!!codeErr && (
                      <div style={{ marginTop: 5, fontSize: 12, color: 'var(--danger)' }}>{codeErr}</div>
                    )}
                  </div>
                </div>

                {/* Отсутствие кода — не мелкая пометка, а препятствие: пара размещения
                    собирается как «сделка-КОД-номер», и без кода отправка материала
                    упирается в справочник на последнем шаге, когда всё уже собрано.
                    Поэтому плашкой, а не красным словом в строке. */}
                {!detail.code && (
                  <div style={{ margin: '0 18px', padding: '9px 12px', borderRadius: 10,
                    background: 'var(--danger-tint)', border: '1px solid var(--danger-border)',
                    fontSize: 12.5, color: 'var(--danger-fg)', lineHeight: 1.45 }}>
                    <b>Буквенный код не задан.</b> Он входит в код пары размещения, и пока
                    его нет, материал на эту площадку отправить нельзя.
                    {mayEdit && ' Задайте его карандашом у названия.'}
                  </div>
                )}

                {/* вкладки поверхностей */}
                <div style={{ display: 'flex', gap: 6, padding: '12px 18px 0', flexWrap: 'wrap' }}>
                  {detail.surfaces.map((s) => (
                    <div key={s.id} onClick={() => setTab(s.id)}
                      style={{
                        padding: '7px 13px', borderRadius: '10px 10px 0 0', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                        color: s.id === tab ? 'var(--text-primary)' : 'var(--text-faint)',
                        background: s.id === tab ? 'var(--bg-soft, #f6f8fc)' : 'transparent',
                        border: s.id === tab ? '1px solid var(--border-card)' : '1px solid transparent', borderBottom: 'none',
                      }}>
                      {SURFACE_LABEL[s.kind] || s.kind}
                      <span style={{ fontFamily: MONO, fontSize: 10, marginLeft: 6, color: 'var(--text-faint)' }}>
                        {s.blocks.length}</span>
                    </div>
                  ))}
                  {mayCreate && missingKinds.map((k) => (
                    <div key={k} onClick={() => addSurface(k)}
                      style={{ padding: '7px 12px', fontSize: 12, cursor: 'pointer', color: 'var(--text-faint)' }}>
                      + {SURFACE_LABEL[k]}</div>
                  ))}
                </div>

                {surface && (
                  <div style={{ background: 'var(--bg-soft, #f6f8fc)', border: '1px solid var(--border-card)', borderTop: 'none', padding: '14px 18px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 16, alignItems: 'end' }}>
                      <label style={{ fontSize: 12 }}>
                        <div style={{ ...CAP, marginBottom: 4 }}>ID паблишера в МС</div>
                        <input style={{ ...inp, width: '100%', fontFamily: MONO }} disabled={!mayEdit}
                          value={surface.ms_publisher_id || ''} onChange={(e) => patchSurface({ ms_publisher_id: e.target.value })} />
                      </label>
                      <label style={{ fontSize: 12 }}>
                        <div style={{ ...CAP, marginBottom: 4 }}>Блок по умолчанию · «кукуха2»</div>
                        <input style={{ ...inp, width: '100%', fontFamily: MONO }} disabled={!mayEdit}
                          value={surface.default_ms_block_id || ''} onChange={(e) => patchSurface({ default_ms_block_id: e.target.value })} />
                      </label>
                      {mayEdit && <button style={btn(true)} disabled={saving} onClick={saveSurface}>Сохранить</button>}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>
                      Блок по умолчанию авто-цепляется к креативу, но статистика по нему в кабинете площадки не показывается.
                    </div>
                  </div>
                )}

                {/* таблица блоков */}
                {surface && (
                  <div style={{ padding: '14px 18px 18px', overflowX: 'auto' }}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10, alignItems: 'center' }}>
                      <span style={{ ...CAP, marginBottom: 0 }}>Типовые разделы:</span>
                      {PAGE_TYPES.map((t) => <span key={t} style={chip('var(--bg-soft,#eef1f6)', 'var(--text-secondary)', 'var(--border-card)')}>{t}</span>)}
                      <span style={{ flex: 1 }} />
                      <button style={btnSm(false)} onClick={exportBlocks}>Выгрузить в Excel</button>
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                      <thead><tr>
                        <th style={{ ...th, width: 100 }}>ID блока</th>
                        <th style={th}>Название (xoalt)</th>
                        <th style={{ ...th, width: 170 }}>Раздел</th>
                        <th style={{ ...th, width: 150 }}>Сеть</th>
                        <th style={{ ...th, width: 60 }}>Актив.</th>
                        <th style={{ ...th, width: 34 }}></th>
                      </tr></thead>
                      <tbody>
                        {surface.blocks.map((b) => (
                          <tr key={b.id}>
                            <td style={{ ...td, fontFamily: MONO, fontWeight: 600, color: 'var(--text-secondary)' }}>
                              <input style={{ ...inp, width: 88, fontFamily: MONO, padding: '5px 7px' }} disabled={!mayEdit}
                                value={b.ms_block_id || ''} onChange={(e) => patchBlock(b.id, { ms_block_id: e.target.value })}
                                onBlur={() => mayEdit && saveBlock(b)} />
                            </td>
                            <td style={td}>
                              <input style={{ ...inp, width: '100%', padding: '5px 8px' }} disabled={!mayEdit}
                                value={b.name || ''} onChange={(e) => patchBlock(b.id, { name: e.target.value })}
                                onBlur={() => mayEdit && saveBlock(b)} />
                            </td>
                            <td style={td}>
                              {mayEdit ? (
                                <span data-pop-root onClick={(e) => setVpop({
                                  rect: e.currentTarget.getBoundingClientRect(), blockId: b.id, value: b.page_type || '',
                                })} style={{
                                  display: 'inline-block', minWidth: 120, padding: '4px 8px', cursor: 'pointer',
                                  borderBottom: '1px dashed var(--border-card)',
                                  color: b.page_type ? 'var(--text-primary)' : 'var(--text-faint)',
                                }}>{b.page_type || '— не задан —'}</span>
                              ) : (
                                <span style={{ padding: '4px 2px' }}>{b.page_type || '—'}</span>
                              )}
                            </td>
                            <td style={td}>
                              <select style={{ ...sel, width: '100%', padding: '5px 8px', fontFamily: MONO, fontSize: 12 }} disabled={!mayEdit}
                                value={b.network || ''} onChange={(e) => { patchBlock(b.id, { network: e.target.value }); }}
                                onBlur={() => mayEdit && saveBlock(b)}>
                                <option value=""></option>
                                {NETWORKS.map((n) => <option key={n} value={n}>{n}</option>)}
                              </select>
                            </td>
                            <td style={{ ...td, textAlign: 'center' }}>
                              <input type="checkbox" checked={!!b.is_active} disabled={!mayEdit}
                                onChange={(e) => { patchBlock(b.id, { is_active: e.target.checked }); saveBlock({ ...b, is_active: e.target.checked }) }} />
                            </td>
                            <td style={{ ...td, textAlign: 'center' }}>
                              {mayDelete && <span onClick={() => delBlock(b.id)}
                                style={{ cursor: 'pointer', color: 'var(--text-faint)', fontWeight: 700 }} title="Удалить">✕</span>}
                            </td>
                          </tr>
                        ))}
                        {!surface.blocks.length && (
                          <tr><td style={{ ...td, color: 'var(--text-faint)' }} colSpan={6}>Блоков пока нет</td></tr>
                        )}
                      </tbody>
                    </table>
                    {mayCreate && <button style={{ ...btnSm(false), marginTop: 10 }} onClick={addBlock}>+ Добавить блок</button>}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        </>)}

        {vpop && (
          <ValuePopover anchor={vpop.rect} title="Раздел" clearLabel="— не задан —"
            value={vpop.value}
            options={types.map((t) => ({ value: t, label: t }))}
            onPick={(v) => { applyType(vpop.blockId, v); setVpop(null) }}
            onAddNew={(name) => { const t = (name || '').trim(); if (t) applyType(vpop.blockId, t); setVpop(null) }}
            onClose={() => setVpop(null)} />
        )}
      </div>
    </>
  )
}
