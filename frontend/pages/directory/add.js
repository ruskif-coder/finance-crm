/**
 * Справочники → «Добавить данные» — окно контрагента (владелец 04.11.2026: замена прежней страницы).
 *
 * Две вкладки: «Заведение» (новый контрагент: что мы должны получить) и «Проверка» (по существующему — что горит
 * и где). Адрес вкладки — `?tab=new` / `?tab=check&cp=<id>`, чтобы ссылкой «открыть проверку» можно было поделиться.
 *
 * Экран рисует компонент `components/counterparty/readiness` по ответу сервера: проверки, видимые блоки и права
 * считает `GET /api/directory-add/readiness/{id}` — в браузере своей копии правил нет. Сохраняют существующие ручки
 * разделов (`lib/readinessApi.mjs`, заведение — `lib/directoryAddCreate.mjs`), своих писателей у экрана нет.
 *
 * Кнопки второго шага спецификации (подтверждение счёта, сканы, «принять осознанно», «запросить у клиента») не
 * подключены: компонент рисует их только при переданном колбэке.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar from '@/components/Navbar'
import SectionTabs from '@/components/SectionTabs'
import CounterpartyReadiness from '@/components/counterparty/readiness/CounterpartyReadiness'
import { MONO, UI, card, inp } from '@/components/salesTableKit'
import { createReadinessApi } from '@/lib/readinessApi.mjs'
import { createFromWizard, validateNew } from '@/lib/directoryAddCreate.mjs'
import { resolveLegacy } from '@/lib/nav'
import { grp0 } from '@/lib/salesFormat'
import safeHref from '@/lib/safeHref'

const http = {
  get: (u) => api.get(u, auth()).then(r => r.data),
  post: (u, b) => api.post(u, b, auth()).then(r => r.data),
  put: (u, b) => api.put(u, b, auth()).then(r => r.data),
}
// Поиск юрлица — та же ручка, что выбор контрагента во вкладке «Проверка» (по названию и ИНН)
const searchCp = (q) => http.get(`/directory-add/counterparties?q=${encodeURIComponent(q)}&limit=12`).then(r => r.items || [])
const NEW_DATA = { mode: 'new', kinds: [], checks: [], options: { signers: [], ourSigners: [] } }

/** Выбор контрагента во вкладке «Проверка»: по имени и ИНН, та же ручка, что прикрепление на прежнем экране. */
function CounterpartyPicker({ current, onPick }) {
  const [q, setQ] = useState('')
  const [items, setItems] = useState([])
  const [fail, setFail] = useState('')
  useEffect(() => {
    const text = q.trim()
    setFail('')
    if (text.length < 2) { setItems([]); return undefined }
    const t = setTimeout(() => {
      http.get(`/directory-add/counterparties?q=${encodeURIComponent(text)}&limit=12`)
        .then(r => setItems(r.items || [])).catch(() => setFail('Поиск не ответил — попробуйте ещё раз'))
    }, 250)
    return () => clearTimeout(t)
  }, [q])
  return (
    <div style={{ ...card, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)', whiteSpace: 'nowrap' }}>
          проверка контрагента
        </span>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder={current ? `сейчас: ${current} — найти другого по названию или ИНН` : 'название или ИНН контрагента'}
          style={{ ...inp, flex: '1 1 auto', maxWidth: 520 }} autoFocus={!current} />
      </div>
      {fail && <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger-fg)' }}>{fail}</span>}
      {items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {items.map(c => (
            <button key={c.id} type="button" onClick={() => { setQ(''); setItems([]); onPick(c.id) }}
              style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '6px 8px', border: 'none', borderRadius: 8, background: 'transparent', cursor: 'pointer', textAlign: 'left', fontFamily: UI }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{c.name}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>ИНН {c.inn || '—'} · договоров {c.contracts}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Отчёт о заведении по шагам: что создалось, на каком шаге остановилось. */
function CreateReport({ steps }) {
  if (!steps.length) return null
  const failed = steps.some(s => s.ok === false)
  return (
    <div style={{ ...card, padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 4, borderColor: failed ? 'var(--danger-border)' : 'var(--border-card)' }}>
      {steps.map((s, i) => (
        <span key={i} style={{ fontSize: 12.5, fontWeight: 600, color: s.ok === false ? 'var(--danger-fg)' : s.ok ? 'var(--text-primary)' : 'var(--text-muted)' }}>
          {s.ok === false ? '✕' : s.ok ? '✓' : '·'} {s.label}
          {s.link && <a href={s.link} style={{ marginLeft: 8, fontWeight: 700, color: 'var(--accent-fg)' }}>открыть →</a>}
        </span>
      ))}
      {failed && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Сохранение прервалось. Что успело создаться — выше, по ссылкам; дозаполните это там или во вкладке «Проверка» — повторное заведение упрётся в уже созданного контрагента.</span>}
    </div>
  )
}

export default function DirectoryAdd() {
  const router = useRouter()
  const { tab, cp } = router.query
  const mode = tab === 'check' ? 'check' : 'new'
  const cpId = cp ? Number(cp) : null
  const rapi = useMemo(() => createReadinessApi(http, { money: grp0 }), [])
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [steps, setSteps] = useState([])
  const [rights, setRights] = useState(null)      // что роли можно завести — считает сервер (`/directory-add/context`)

  // Право на экран — `directory_add`: без него 403, и это не ошибка сети, а отсутствие раздела у роли.
  useEffect(() => {
    if (!router.isReady) return
    http.get('/directory-add/context').then(r => setRights(r.blocks || {})).catch(e => setErr(e?.response?.status === 403
      ? 'Нет права «Добавить данные» — попросите администратора выдать раздел роли.'
      : 'Не удалось открыть экран. Обновите страницу.'))
  }, [router.isReady])

  useEffect(() => {
    if (mode !== 'check' || !cpId) { setData(null); return undefined }
    let alive = true
    setData(null)
    rapi.load(cpId).then(d => { if (alive) setData(d) }).catch(e => {
      if (alive) setErr(e?.response?.status === 404 ? 'Контрагент не найден.' : 'Не удалось загрузить проверку контрагента.')
    })
    return () => { alive = false }
  }, [mode, cpId, rapi])

  const go = useCallback((query) => router.replace({ pathname: '/directory/add', query }, undefined, { shallow: true }), [router])
  const open = useCallback((url) => {
    if (!url) return
    if (String(url).startsWith('/')) router.push(resolveLegacy(url))
    else { const href = safeHref(url); if (href) window.open(href, '_blank', 'noopener') }
  }, [router])

  const saveBlock = (block, patch) => rapi.saveBlock(cpId, block, patch).then(r => { if (r.data) setData(r.data); return r })
  const upload = async (contractId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    await http.post(`/contracts/${contractId}/upload`, fd)
    setData(await rapi.load(cpId))
    return { name: file.name, size: `${Math.round(file.size / 1024)} КБ`, uploaded_at: 'сейчас', url: `/directory/contracts/${contractId}` }
  }
  const create = async (kind, values) => {
    const r = await createFromWizard(http, kind, values, rights)
    setSteps(r.steps)
    if (r.cpId && !r.failed) go({ tab: 'check', cp: r.cpId })
    return r
  }

  const shown = mode === 'new' ? NEW_DATA : data
  return (
    <>
      <Head><title>Добавить данные · Справочники | SIMB-AD ERP</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 0', background: 'var(--bg-canvas)', fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <SectionTabs section="directory" />
        {err && <div style={{ ...card, padding: '12px 18px', fontSize: 13, fontWeight: 600, color: 'var(--danger-fg)' }}>{err}</div>}
        <CreateReport steps={steps} />
        {mode === 'check' && <CounterpartyPicker current={data?.counterparty?.name} onPick={id => { setSteps([]); go({ tab: 'check', cp: id }) }} />}
        {mode === 'check' && !cpId && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
            Выберите контрагента — или
            <button type="button" onClick={() => go({ tab: 'new' })} style={{ border: 'none', background: 'none', padding: 0, color: 'var(--accent-fg)', fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>заведите нового</button>
          </div>
        )}
      </div>
      {shown && !err && (
        <CounterpartyReadiness data={shown} onSaveBlock={saveBlock} onUploadDocument={upload} onOpen={open} onCreate={create}
          onLookupInn={(inn, kpp) => rapi.lookup(inn, kpp)}
          onValidateNew={(kind, values) => (rights ? validateNew(kind, values, rights) : ['Права на экран ещё загружаются'])}
          onSearchCounterparty={searchCp}
          onModeChange={m => go(m === 'check' ? { tab: 'check', ...(cpId ? { cp: cpId } : {}) } : { tab: 'new' })} />
      )}
    </>
  )
}
