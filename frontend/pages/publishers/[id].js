import { useState, useEffect } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, btn } from '@/components/salesTableKit'
import PublisherCard from '@/components/publishers/PublisherCard'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { downloadFile } from '@/lib/download'

// Страница карточки площадки: загрузка, режим правки и сохранение. Вся вёрстка — в
// components/publishers/PublisherCard. Режим правки включается и ссылкой ?edit=1 —
// из реестра кнопка ✎ ведёт сюда, а не разворачивает форму в строке.

export default function PublisherCardPage() {
  const router = useRouter()
  const { id, edit } = router.query
  const [data, setData] = useState(null)
  const [meta, setMeta] = useState({ statuses: [], kinds: [], deal_types: [], services: [] })
  const [finance, setFinance] = useState(null)
  const [form, setForm] = useState({})
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [perms, setPerms] = useState({})
  const [saving, setSaving] = useState(false)

  const canEdit = can(perms, 'dir_publishers', 'edit')
  const flash = (m) => { setOk(m); setTimeout(() => setOk(''), 2500) }
  // 422 проверки полей приходит СПИСКОМ объектов, а не строкой: нарисованный как есть,
  // он ронял экран в белый («Objects are not valid as a React child»). Список —
  // сообщениями через точку с запятой.
  const fail = (e, fallback) => {
    const d = e.response?.data?.detail
    setError(Array.isArray(d) ? d.map(x => x?.msg || String(x)).join('; ')
      : (typeof d === 'string' ? d : fallback))
  }

  const load = async () => {
    if (!id) return
    try {
      const [r, m, f] = await Promise.all([
        api.get(`/publishers/${id}`, auth()),
        api.get('/publishers/meta', auth()),
        api.get(`/publishers/${id}/finance`, auth()).catch(() => ({ data: null })),
      ])
      setData(r.data); setMeta(m.data); setFinance(f.data)
      return r.data
    } catch (e) { fail(e, 'Не удалось загрузить площадку') }
  }

  useRefreshOnReturn(() => load(), { enabled: !editing })
  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load()
  }, [id])

  useEffect(() => { if (edit === '1' && canEdit && data && !editing) startEdit(data) }, [edit, canEdit, data])

  const startEdit = (d) => {
    setForm({
      name: d.name || '', domain: d.domain || '', code: d.code || '',
      kind: d.kind || '', status: d.status || '',
      network: d.network || '', deal_type: d.deal_type || '', cpm_contract: d.cpm_contract ?? '',
      timezone_offset: d.timezone_offset ?? 0, our_code: d.our_code, is_exclusive: d.is_exclusive,
      has_dsp: d.has_dsp, shares_data: d.shares_data, self_promo: d.self_promo || 'НЕТ',
      self_promo_note: d.self_promo_note || '', basket_note: d.basket_note || '',
      tech_requirements: d.tech_requirements || '', note: d.note || '',
      chat_title: d.chat_title || '', chat_url: d.chat_url || '',
      chat_url_max: d.chat_url_max || '', messenger_note: d.messenger_note || '',
      // Вложенные сущности копируются в черновик целиком: правка идёт по копии,
      // сохранённое состояние не трогается до «Сохранить».
      surfaces: JSON.parse(JSON.stringify(d.surfaces || {})),
      services: (d.services || []).map(x => ({ surface_kind: x.surface_kind, service_id: x.service_id })),
      traffic: JSON.parse(JSON.stringify(d.traffic || {})),
    })
    setEditing(true)
  }

  // Всё, что правится в карточке, уходит одним PATCH деревом: площадка, поверхности,
  // платформы, услуги и замеры трафика. Так «Отмена» действительно отменяет — раньше
  // галочки сохранялись сразу и откатить их было нечем.
  // Контакты, документы и договоры остаются отдельными действиями: у них своё
  // подтверждение (модалка, выбор файла, confirm), и они применяются сразу.
  const save = async () => {
    setSaving(true); setError('')
    try {
      const num = (v) => {
        if (v === '' || v == null) return null
        const n = parseFloat(String(v).replace(/\s/g, '').replace(',', '.'))
        return isNaN(n) ? null : n
      }
      const surfaces = {}
      for (const [kind, s0] of Object.entries(form.surfaces || {})) {
        surfaces[kind] = { ...s0, exists: true, coverage_percent: num(s0.coverage_percent) }
      }
      // Поверхность, снятая в черновике, должна быть удалена и на сервере — иначе
      // «снял галочку и сохранил» ничего не изменит.
      for (const kind of Object.keys(data.surfaces || {})) {
        if (!surfaces[kind]) surfaces[kind] = { exists: false }
      }
      // Отправляем только изменённые замеры. Иначе сохранение карточки штампует
      // декабрьские цифры текущим месяцем: замер привязан к месяцу, а в черновике
      // лежит последний известный, каким бы старым он ни был.
      const traffic = {}
      for (const [scope, t] of Object.entries(form.traffic || {})) {
        const was = data.traffic?.[scope] || {}
        const value = num(t.value)
        const depth = num(t.depth)
        if (value !== (was.value ?? null) || depth !== (was.depth ?? null)) {
          traffic[scope] = { value, depth }
        }
      }
      await api.patch(`/publishers/${id}`, {
        ...form,
        cpm_contract: num(form.cpm_contract),
        surfaces, traffic, services: form.services || [],
      }, auth())
      setEditing(false)
      await load()
      flash('Сохранено')
    } catch (e) { fail(e, 'Не удалось сохранить') }
    finally { setSaving(false) }
  }

  const cardApi = {
    saveSurface: async (kind, body) => {
      const payload = { ...body }
      if (typeof payload.coverage_percent === 'string') {
        const v = parseFloat(payload.coverage_percent.replace(',', '.'))
        payload.coverage_percent = isNaN(v) ? null : v
      }
      try { await api.put(`/publishers/${id}/surfaces/${kind}`, payload, auth()); await load() }
      catch (e) { fail(e, 'Не удалось сохранить поверхность') }
    },
    addSurface: async (kind) => {
      try {
        await api.put(`/publishers/${id}/surfaces/${kind}`,
          { integration_status: 'НЕТ', we_work: false }, auth())
        await load()
      } catch (e) { fail(e, 'Не удалось завести поверхность') }
    },
    dropSurface: async (kind) => {
      if (!window.confirm(`Убрать поверхность ${kind.toUpperCase()}?\nВместе с ней снимутся отмеченные на ней услуги.`)) return
      try { await api.delete(`/publishers/${id}/surfaces/${kind}`, auth()); await load() }
      catch (e) { fail(e, 'Не удалось убрать поверхность') }
    },
    savePlatform: async (kind, body) => {
      try { await api.put(`/publishers/${id}/surfaces/app/platforms/${kind}`, body, auth()); await load() }
      catch (e) { fail(e, 'Не удалось сохранить платформу') }
    },
    toggleService: async (kind, serviceId, active) => {
      try {
        await api.put(`/publishers/${id}/services`,
          { surface_kind: kind, service_id: serviceId, is_active: active }, auth())
        await load()
      } catch (e) { fail(e, 'Не удалось сохранить услугу') }
    },
    saveTraffic: async (scope, { value, depth }) => {
      const num = (v) => {
        if (v === '' || v == null) return null
        const n = parseFloat(String(v).replace(/\s/g, '').replace(',', '.'))
        return isNaN(n) ? null : n
      }
      try {
        await api.put(`/publishers/${id}/traffic`,
          { scope, value: num(value), depth: scope === 'ad_requests' ? null : num(depth) }, auth())
        await load()
      } catch (e) { fail(e, 'Не удалось сохранить замер') }
    },
    // Точечное сохранение одного поля — для правки текста по двойному клику
    // вне режима правки.
    patchField: async (key, value) => {
      try { await api.patch(`/publishers/${id}`, { [key]: value }, auth()); await load(); flash('Сохранено') }
      catch (e) { fail(e, 'Не удалось сохранить') }
    },
    addKind: async (name) => {
      try {
        const r = await api.post('/publishers/kinds', { name }, auth())
        setMeta(m => ({ ...m, kinds: [...(m.kinds || []), { id: r.data.id, name: r.data.name }] }))
        return r.data.name
      } catch (e) { fail(e, 'Не удалось добавить вид'); return name }
    },
    addDocType: async (name) => {
      try {
        const r = await api.post('/publishers/doc-types', { name }, auth())
        setMeta(m => ({ ...m, doc_types: [...(m.doc_types || []), { id: r.data.id, name: r.data.name }] }))
        return r.data.name
      } catch (e) { fail(e, 'Не удалось добавить тип'); return name }
    },
    uploadDocument: async (docType, file) => {
      const fd = new FormData(); fd.append('file', file)
      try {
        await api.post(`/publishers/${id}/documents?doc_type=${encodeURIComponent(docType)}`, fd, auth())
        await load(); flash('Документ загружен')
        return true
      } catch (e) { fail(e, 'Не удалось загрузить документ'); return false }
    },
    downloadDocument: async (docId, filename) => {
      await downloadFile(`/publishers/${id}/documents/${docId}`, filename, setError)
    },
    deleteDocument: async (docId) => {
      if (!window.confirm('Удалить документ?')) return
      try { await api.delete(`/publishers/${id}/documents/${docId}`, auth()); await load() }
      catch (e) { fail(e, 'Не удалось удалить документ') }
    },
    // Ссылка на договор в ЭДО. Схемы кроме http(s) отклоняет сервер: javascript:
    // и data: — это XSS, а не адрес документа.
    setContractEdo: async (linkId, current) => {
      const url = window.prompt('Ссылка на договор в ЭДО', current || '')
      if (url === null) return
      try {
        await api.put(`/publishers/${id}/contracts/${linkId}/document-url`, { document_url: url }, auth())
        await load()
      } catch (e) { fail(e, 'Не удалось сохранить ссылку') }
    },
    archivedContracts: async () => {
      try { const r = await api.get(`/publishers/${id}/contracts/archived`, auth()); return r.data.items }
      catch (e) { fail(e, 'Не удалось загрузить архив'); return [] }
    },
    restoreContract: async (linkId) => {
      try {
        await api.post(`/publishers/${id}/contracts/${linkId}/archive?restore=true`, {}, auth())
        await load()
      } catch (e) { fail(e, 'Не удалось вернуть договор') }
    },
    archiveContract: async (linkId) => {
      if (!window.confirm('Убрать договор в архив?\nЗапись сохранится, из карточки исчезнет.')) return
      try { await api.post(`/publishers/${id}/contracts/${linkId}/archive`, {}, auth()); await load() }
      catch (e) { fail(e, 'Не удалось убрать в архив') }
    },
    uploadContractDoc: async (linkId, file) => {
      const fd = new FormData(); fd.append('file', file)
      try { await api.post(`/publishers/${id}/contracts/${linkId}/document`, fd, auth()); await load() }
      catch (e) { fail(e, 'Не удалось приложить документ') }
    },
    // Имя файла не выдумываем: своего нет — берём из Content-Disposition. Заглушка
    // 'contract' клала документ на диск без расширения.
    downloadContractDoc: async (linkId) => {
      await downloadFile(`/publishers/${id}/contracts/${linkId}/document`, null, setError)
    },
    // Поиск идёт на сервере: контрагентов больше, чем отдаёт одна страница реестра.
    searchCounterparties: async (q) => {
      try {
        const r = await api.get('/counterparties/', { params: { search: q, limit: 30 }, ...auth() })
        const list = Array.isArray(r.data) ? r.data : (r.data.items || [])
        return list.map(x => ({ id: x.id, name: x.name })).filter(x => x.name)
      } catch (e) { return [] }
    },
    attachCounterparty: async (cpId) => {
      try { await api.post(`/publishers/${id}/counterparties`, { counterparty_id: cpId }, auth()); await load() }
      catch (e) { fail(e, 'Не удалось прикрепить юрлицо') }
    },
    // Договоры выбранного юрлица из реестра: номер выбирается, а не вводится руками.
    contractsByCounterparty: async (cpId) => {
      try {
        const r = await api.get('/publishers/contracts-by-counterparty',
          { params: { counterparty_id: cpId }, ...auth() })
        return r.data.items
      } catch (e) { return [] }
    },
    attachContract: async (contractId, role) => {
      try { await api.post(`/publishers/${id}/contracts`, { contract_id: contractId, role }, auth()); await load() }
      catch (e) { fail(e, 'Не удалось привязать договор') }
    },
    detachContract: async (linkId) => {
      try { await api.delete(`/publishers/${id}/contracts/${linkId}`, auth()); await load() }
      catch (e) { fail(e, 'Не удалось отвязать договор') }
    },
    detachCounterparty: async (cpId) => {
      try { await api.delete(`/publishers/${id}/counterparties/${cpId}`, auth()); await load() }
      catch (e) { fail(e, 'Не удалось открепить юрлицо') }
    },
    // Новая должность уходит в общий каталог и дальше предлагается всем.
    addPosition: async (name) => {
      try {
        const r = await api.post('/publishers/positions', { name }, auth())
        setMeta(m => ({ ...m, positions: [...(m.positions || []), { id: r.data.id, name: r.data.name }] }))
        return r.data.name
      } catch (e) { fail(e, 'Не удалось добавить должность'); return name }
    },
    saveContact: async (draft) => {
      try {
        if (draft.id) await api.put(`/publishers/${id}/contacts/${draft.id}`, draft, auth())
        else await api.post(`/publishers/${id}/contacts`, draft, auth())
        await load()
        flash('Контакт сохранён')
        return true
      } catch (e) { fail(e, 'Не удалось сохранить контакт'); return false }
    },
    deleteContact: async (cid) => {
      try { await api.delete(`/publishers/${id}/contacts/${cid}`, auth()); await load() }
      catch (e) { fail(e, 'Не удалось удалить контакт') }
    },
  }

  return (
    <>
      <Head><title>{data?.name ? data.name + ' · площадка' : 'Площадка'} | SIMB-AD ERP</title></Head>
      <Navbar active="publishers" />
      {/* Полотно карточки ограничено по ширине, как в хендоффе: на широком мониторе
          строка в 2500 px читается хуже, а правая колонка уезжает от левой. */}
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh',
        fontFamily: UI, display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '100%', maxWidth: 1500 }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
          <Link href="/publishers" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', textDecoration: 'none' }}>← Паблишеры</Link>
          <span style={{ color: 'var(--border-inner)' }}>/</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{data?.domain}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
            {data?.domain && (
              <a href={`https://${data.domain}`} target="_blank" rel="noreferrer" style={btn(false)}>Открыть сайт</a>
            )}
            {canEdit && (editing
              ? (<>
                  <button style={btn(false)} onClick={() => { setEditing(false); router.replace(`/publishers/${id}`, undefined, { shallow: true }) }}>Отмена</button>
                  <button style={btn(true)} disabled={saving} onClick={save}>{saving ? 'Сохраняю…' : 'Сохранить'}</button>
                </>)
              : <button style={btn(true)} onClick={() => startEdit(data)}>Редактировать</button>)}
          </span>
        </div>

        {error && <div style={{ background: 'var(--danger-tint)', border: '1px solid var(--danger)',
          color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{error}</div>}
        {ok && <div style={{ background: 'var(--accent-tint)', color: 'var(--accent)',
          padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 12, fontSize: 13 }}>{ok}</div>}

        {!data && <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>}

        {data && (
          <PublisherCard data={data} meta={meta} finance={finance} editing={editing}
            canEdit={canEdit} form={form} setForm={setForm} api={cardApi} />
        )}
        </div>
      </div>
    </>
  )
}
