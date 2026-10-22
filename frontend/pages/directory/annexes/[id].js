/**
 * Сборка приложения к договору (ДС) — экран, на котором аккаунт ПРОВЕРЯЕТ документ до
 * выгрузки, а не после подписания.
 *
 * Числа и стороны берутся с сервера собранными (`GET /annexes/:id` → `doc`) — тем же
 * расчётом, который печатает PDF. Считать здесь заново нельзя: аккаунт проверял бы одни
 * числа, а в бумагу уходили другие, и расходились бы они молча.
 *
 * Реквизиты подписанта правятся ПРЯМО ЗДЕСЬ и сохраняются в карточку контрагента
 * (решение владельца 05.09.2026): к моменту сборки документа выясняется, что должности
 * или основания полномочий нет, и уходить за ними в справочник — терять место.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, getPermissions } from '../../../components/Navbar'
import { card, inp, btn, primaryBtn, th, td, MONO, UI } from '../../../components/salesTableKit'
import { grp, fmtFull } from '../../../lib/salesFormat'
// Токен НЕ вшит в синглтон — он передаётся `auth()` на каждый запрос
// (lib/http.js). Без него ответ 401, а перехватчик уводит на логин, и
// выглядит это как «страница требует входа», а не как забытый заголовок.
import api, { auth } from '../../../lib/api'
import { saveBlob, filenameFromResponse } from '@/lib/download'
import { fmtDate as fmtCalendarDate } from '@/lib/dates'
import AnnexModelPanel from '@/components/annex/AnnexModelPanel'
import AnnexQuickEdit from '@/components/annex/AnnexQuickEdit'
import AnnexDateField from '@/components/annex/AnnexDateField'
import AnnexLegalButton from '@/components/annex/AnnexLegalButton'

const dm = (d) => fmtCalendarDate(d)

const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const SECTION = { ...card, padding: '18px 20px', marginBottom: 16 }

/** Поле подписанта. Объявлено на модульном уровне: компонент, созданный внутри рендера,
 *  пересоздаётся на каждый ввод, и фокус слетает после каждого символа.
 *
 *  Незаполненное подсвечивается рамкой и подписью: все три поля обязательны для печати,
 *  и человек должен видеть, чего не хватает, ДО отказа выгрузки, а не после. */
function Field({ label, value, onChange, placeholder, hint, warn, presets }) {
  const empty = !String(value || '').trim()
  const bad = empty || !!warn
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ ...LBL, marginBottom: 4, color: bad ? 'var(--warning-text)' : 'var(--text-faint)' }}>
        {label}{empty ? ' · не заполнено' : ''}
      </div>
      <input value={value || ''} onChange={e => onChange(e.target.value)}
             placeholder={placeholder}
             style={{ ...inp, width: '100%',
                      borderColor: bad ? 'var(--warning)' : 'var(--border-card)',
                      background: bad ? 'var(--warning-tint)' : 'var(--bg-card)' }} />
      {/* Быстрые подстановки частых значений: ввод идёт в одно нажатие, а в именительном падеже, как хранит карточка. */}
      {!!presets && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
          {presets.map(p => (
            <span key={p} onClick={() => onChange(p)} title={`Подставить «${p}»`}
                  style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 9px', borderRadius: 7, border: '1px solid var(--border-card)', background: String(value || '').trim() === p ? 'var(--accent-tint)' : 'var(--bg-subtle)', color: String(value || '').trim() === p ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 11.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
              {p}
            </span>
          ))}
        </div>
      )}
      {(warn || hint) && (
        <div style={{ fontSize: 11, lineHeight: 1.4, marginTop: 4,
                      color: warn ? 'var(--warning-text)' : 'var(--text-faint)' }}>
          {warn || hint}
        </div>
      )}
    </div>
  )
}

// Частые значения для подстановки одним нажатием. Должность — в именительном (карточка хранит так, склоняет сервер); основание — в
// родительном, как оно стоит в «действующего на основании …». У доверенности подставляется заготовка: номер и дата вписываются руками.
const POSITION_PRESETS = ['Генеральный директор', 'Директор']
const BASIS_PRESETS = ['Устава', 'Доверенности № ___ от ___']

// Доверенность без номера и даты в документе не значит ничего: «действующего на основании
// Доверенности» не отсылает ни к какому документу, и подписант формально не подтверждён.
const BASIS_HINT = 'Устава — для директора. Для доверенности пишите её номер и дату: «Доверенности № 5 от 01.01.2026»'
const basisWarn = (v) => (/доверенност/i.test(v || '') && !/\d/.test(v || '')
  ? 'У доверенности обязательны номер и дата — без них ссылка в документе ни на что не указывает'
  : '')

/** Сторона документа: реквизиты сверху, правка подписанта снизу. */
function Party({ title, p, onSave, saving, canEdit }) {
  const [form, setForm] = useState(null)
  // Падежные формы для строки «в лице …» по ТОМУ, ЧТО НАБРАНО. Считает сервер
  // (`POST /annexes/party/phrase`): правила склонения живут в одном месте, и вторая
  // реализация на клиенте разошлась бы с той, что печатает документ.
  const [gen, setGen] = useState(null)
  useEffect(() => {
    setForm({ director_name: p?.director || '', signer_position: p?.position || '',
              signer_basis: p?.basis || '' })
  }, [p?.id, p?.director, p?.position, p?.basis])
  useEffect(() => {
    if (!form) return
    // Пауза, чтобы не звать сервер на каждую букву; ответ устаревшего запроса
    // отбрасывается флагом — иначе строка мигала бы предыдущим вводом.
    let alive = true
    const t = setTimeout(async () => {
      try {
        const r = await api.post('/annexes/party/phrase', form, auth())
        if (alive) setGen(r.data)
      } catch (_) { /* предпросмотр не критичен: строка просто останется прежней */ }
    }, 350)
    return () => { alive = false; clearTimeout(t) }
  }, [form])
  if (!p || !form) return null
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const g = gen || p
  const dirty = form.director_name !== (p.director || '')
    || form.signer_position !== (p.position || '')
    || form.signer_basis !== (p.basis || '')
  return (
    <div style={{ ...SECTION, marginBottom: 0 }}>
      <div style={{ ...LBL, marginBottom: 10 }}>{title}</div>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>{p.name || '—'}</div>
      <div style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14 }}>
        ИНН {p.inn || '—'}{p.kpp ? ` · КПП ${p.kpp}` : ''}
      </div>
      <div style={{ display: 'grid', gap: 10 }}>
        <Field label="ФИО подписанта" value={form.director_name}
               onChange={v => set('director_name', v)} placeholder="Иванов Иван Иванович" />
        {/* Вертикальный разделитель между полями: две подписи с рамками и подсказками
            иначе читаются как одно поле в две колонки. */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1px 1fr', gap: 14,
                      alignItems: 'start' }}>
          <Field label="Должность" value={form.signer_position}
                 onChange={v => set('signer_position', v)} placeholder="Генеральный директор"
                 presets={POSITION_PRESETS} />
          <div style={{ alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <Field label="Основание полномочий" value={form.signer_basis}
                 onChange={v => set('signer_basis', v)} placeholder="Устава"
                 presets={BASIS_PRESETS}
                 hint={BASIS_HINT} warn={basisWarn(form.signer_basis)} />
        </div>
      </div>
      {/* Падежи в документе считает сервер: показываем то, что реально напечатается,
          чтобы аккаунт видел строку целиком, а не догадывался о ней по полям. */}
      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        В документе: «в лице {g.position_gen || '___________'} {g.director_gen || '___________'},
        {' '}{g.acting || 'действующего'} на основании {g.basis_gen || '___________'}»
      </div>
      {dirty && canEdit && (
        <button onClick={() => onSave(p.id, form)} disabled={saving || /_{3}/.test(form.signer_basis || '')}
                title={/_{3}/.test(form.signer_basis || '') ? 'Впишите номер и дату доверенности вместо подчёркиваний' : ''}
                style={{ ...primaryBtn, marginTop: 12, opacity: /_{3}/.test(form.signer_basis || '') ? .5 : 1 }}>
          {saving ? 'Сохраняю…' : 'Сохранить в карточку контрагента'}
        </button>
      )}
    </div>
  )
}

export default function AnnexAssembly() {
  const router = useRouter()
  const { id } = router.query
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  // Номер и дата — редактируемые. Предзаполняются посчитанными: следующим свободным
  // номером внутри договора и последним днём предыдущего месяца.
  const [no, setNo] = useState('')
  const [docDate, setDocDate] = useState('')
  // Право читается на клиенте ТОЛЬКО чтобы не показывать кнопку, которой всё равно
  // откажут: решение принимает сервер (`require_permission('annexes','edit')`).
  // `can` сам пропускает админа — второй раз этого делать нельзя.
  const [mayEdit, setMayEdit] = useState(false)
  // Файл договора отдаёт ручка договоров под своим правом. Кнопку без этого права не
  // показываем: она всё равно вернула бы 403, а мёртвая кнопка тратит время каждый раз.
  const [mayViewContracts, setMayViewContracts] = useState(false)
  useEffect(() => {
    const perms = getPermissions()
    setMayEdit(can(perms, 'annexes', 'edit'))
    setMayViewContracts(can(perms, 'contracts', 'view'))
  }, [])

  const [legal, setLegal] = useState([])
  const legalOpen = legal.filter(x => x.status === 'открыта' || x.status === 'в работе')
  const load = useCallback(async () => {
    if (!id) return
    try {
      const r = await api.get(`/annexes/${id}`, auth())
      setA(r.data)
      // Заявки юристу этого ДС: открытая красит шапку и держит подтверждение и чистовик (владелец 14.10.2026).
      api.get(`/legal-requests/annex/${id}`, auth()).then(x => setLegal(x.data)).catch(e => { setLegal([]); setErr(e?.response?.data?.detail || 'Не удалось загрузить заявки юристу — блокировка ДС не проверена') })
      setNo(String(r.data.no ?? r.data.next_no ?? ''))
      setDocDate(r.data.date ? String(r.data.date).slice(0, 10) : '')
      setErr('')
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить приложение') }
  }, [id])

  useEffect(() => { load() }, [load])

  const saveSigner = async (cpId, form) => {
    setBusy('signer')
    try {
      await api.put(`/annexes/party/${cpId}/signer`, form, auth())
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить реквизиты') }
    finally { setBusy('') }
  }

  const confirm = async () => {
    setBusy('confirm')
    try {
      await api.post(`/annexes/${id}/confirm`,
                     { no: no === '' ? null : Number(no), doc_date: docDate || null }, auth())
      await load()
    }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось подтвердить номер') }
    finally { setBusy('') }
  }

  // PDF уходит на подпись, .docx — юристу клиента, который правит документ до
  // подписания. Ручка одна на оба формата, отличается только хвост адреса.
  /** Файл договора — существующей ручкой договоров, чтобы правила доступа к нему были
   *  одни, а не двое. */
  const grabContract = async () => {
    setBusy('contract')
    setErr('')
    try {
      const r = await api.get(`/contracts/${d.contract.id}/download`,
                              { ...auth(), responseType: 'blob' })
      saveBlob(r.data, filenameFromResponse(r) || 'Договор.pdf')
    } catch (e) {
      let msg = 'Не удалось скачать договор'
      try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch (_) { /* не JSON */ }
      setErr(msg)
    } finally { setBusy('') }
  }

  /** Пересоздать подтверждённое приложение на актуальном шаблоне (до отправки в 1С). */
  const rebuild = async () => {
    if (!window.confirm('Пересоздать документ по актуальной версии шаблона договора? Номер и дата сохранятся, прежний текст документа будет заменён.')) return
    setBusy('rebuild')
    setErr('')
    try {
      await api.post(`/annexes/${id}/rebuild`, {}, auth())
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось пересоздать документ') }
    finally { setBusy('') }
  }

  /** Сохранить правку блока (зона аккаунта) или основания закрывающих; `text = null` — вернуть по шаблону. */
  const saveDate = async (docDate) => {
    await api.put(`/annexes/${id}/date`, { doc_date: docDate }, auth())
    await load()
  }
  const saveEdit = async (key, text) => {
    await api.put(`/annexes/${id}/edits`, { key, text }, auth())
    await load()
  }

  const download = async (kind = 'pdf', withBasis = false) => {
    setBusy(withBasis ? `${kind}+` : kind)
    setErr('')
    try {
      const r = await api.get(`/annexes/${id}/${kind}${withBasis ? '?with_basis=1' : ''}`, { ...auth(), responseType: 'blob' })
      saveBlob(r.data, filenameFromResponse(r) || `ДС.${kind}`)
    } catch (e) {
      // Отказ приходит блобом, а не JSON: тело надо прочитать, иначе на экране
      // окажется «[object Blob]» вместо перечня недостающего.
      let msg = 'Не удалось выгрузить документ'
      try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch (_) { /* тело не JSON */ }
      setErr(msg)
    } finally { setBusy('') }
  }

  const d = a?.doc
  const rows = d?.rows || []
  const miss = d?.missing || []

  return (
    <div style={{ fontFamily: UI, minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Head><title>{a?.number ? a.number + ' · приложение' : 'Приложение к договору'} | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '22px 20px 60px' }}>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
          <button onClick={() => router.push('/directory/annexes')} style={btn(false)}>← К реестру</button>
          {/* ДС мастер-сделки — назад к раскладке; номер займёт подтверждение (из раскладки), а не «следующий по договору». */}
          {!!a?.master && (
            <>
              <button onClick={() => router.push(`/accounts/master/${a.master.code}`)} style={btn(false)}>← Раскладка {a.master.code}</button>
              {!!a.master.will_be && !a.no && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>при подтверждении — {a.master.will_be}</span>}
              {(a.master.siblings || []).length > 1 && (
                <span style={{ display: 'inline-flex', gap: 6, marginLeft: 8 }}>
                  {a.master.siblings.map(x => (
                    <button key={x.id} type="button" onClick={() => x.id !== a.id && router.push(`/directory/annexes/${x.id}`)}
                      style={{ ...btn(x.id === a.id), cursor: x.id === a.id ? 'default' : 'pointer' }}>
                      {x.number}{x.confirmed ? ' ✓' : ''}</button>
                  ))}
                </span>
              )}
            </>
          )}
        </span>

        {!!err && (
          <div style={{ ...SECTION, borderColor: 'var(--danger)', color: 'var(--danger)' }}>{err}</div>
        )}

        {a && (
          <>
            <div style={{ ...SECTION, display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
                          ...(legalOpen.length ? { background: 'var(--warning-bg)', border: '1px solid var(--warning-border)' } : {}) }}>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-.02em' }}>
                  {a.number || 'Черновик — номер не занят'}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                  от {dm(a.date)} · договор № {d?.contract?.number || '—'} от {dm(d?.contract?.date)}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                  период размещения {dm(a.period_from)} — {dm(a.period_to)}
                </div>
                {!!legalOpen.length && (
                  <div style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 8, padding: '4px 10px', borderRadius: 8,
                                background: 'var(--warning-tint)', color: 'var(--warning-fg)', fontSize: 12.5, fontWeight: 700 }}>
                    Ждёт юриста · {legalOpen.map(x => `${x.status}${x.taken_by ? ` (${x.taken_by})` : ''}`).join(', ')} — подтверждение и чистовые недоступны
                  </div>
                )}
                {/* Сумма документа не сходится с суммой его сделок — говорим ДО подписания.
                    Текст считает сервер (routers/annexes._mismatch, аудит 23.09.2026, 3.H1). */}
                {!!a.mismatch && (
                  <div role="alert" style={{ marginTop: 10, padding: '9px 12px', borderRadius: 10,
                    background: 'var(--warning-tint)', border: '1px solid var(--warning-border)',
                    color: 'var(--text-primary)', fontSize: 13, lineHeight: 1.45 }}>
                    <b style={{ color: 'var(--warning-fg)' }}>!</b> {a.mismatch}
                  </div>
                )}
                {/* Из документа надо уметь вернуться к тому, из чего он собран: метки
                    сделок кликабельные. Приложение может закрывать несколько — поэтому
                    список, а не одна ссылка, и рядом разнесённая на сделку сумма. */}
                {!!(a.deals || []).length && (
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8,
                                flexWrap: 'wrap', marginTop: 8 }}>
                    <span style={{ ...LBL, color: 'var(--text-faint)' }}>Сделки</span>
                    {a.deals.map(x => (
                      <a key={x.id} href={`/sales/deals/${x.code || x.id}`}
                         title={x.title || ''}
                         style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700,
                                  color: 'var(--accent)', textDecoration: 'none',
                                  borderBottom: '1px dashed var(--accent)' }}>
                        {x.code || x.id}
                      </a>
                    ))}
                    <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                      {a.deals.length > 1
                        ? `· сумма разнесена на ${a.deals.length}`
                        : ''}
                    </span>
                  </div>
                )}
                {a.is_draft && mayEdit && (
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 6 }}>
                    {a.annex_start_no
                      ? `Нумерация по этому договору начинается с ${a.annex_start_no + 1}: приложения по ${a.annex_start_no} выданы вне системы`
                      : 'Стартовый номер по договору не задан — нумерация с 1'}
                  </div>
                )}
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'flex-end' }}>
                {/* Номер и дата правятся ДО подтверждения и уходят вместе с ним: пока
                    номер не занят, менять его безопасно, после — приложение заморожено.
                    Одно действие вместо «сохранить, потом подтвердить» — иначе появилось
                    бы состояние «дата новая, номер старый», которого нет на бумаге. */}
                {a.is_draft && (
                  <>
                    <div>
                      <div style={{ ...LBL, marginBottom: 4 }}>Номер</div>
                      <input type="number" min={(a.annex_start_no || 0) + 1} value={no}
                             onChange={e => setNo(e.target.value)}
                             style={{ ...inp, width: 110, fontFamily: MONO }} />
                    </div>
                    <div>
                      <div style={{ ...LBL, marginBottom: 4 }}>Дата документа</div>
                      <input type="date" value={docDate} onChange={e => setDocDate(e.target.value)}
                             style={{ ...inp, width: 160, fontFamily: MONO }} />
                    </div>
                    <button onClick={confirm} disabled={!!busy || !!legalOpen.length} title={legalOpen.length ? 'Ждёт ответа юриста' : undefined}
                            style={{ ...btn(false), height: 36, opacity: legalOpen.length ? .45 : 1, cursor: legalOpen.length ? 'not-allowed' : 'pointer' }}>
                      {busy === 'confirm' ? 'Занимаю номер…' : 'Подтвердить номер'}
                    </button>
                  </>
                )}
                {/* Выгрузка в одну строку (владелец 14.10.2026): «Клиентские на согласование» — ДС и основание закрывающих одним файлом,
                    затем разделитель, затем чистовые — только ДС, на подпись. */}
                <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', alignSelf: 'center', whiteSpace: 'nowrap' }}>Клиентские на согласование</span>
                <button onClick={() => download('docx', true)} disabled={!!busy || !!miss.length}
                        title={miss.length ? 'Сначала заполните недостающее' : 'ДС и основание для закрывающих документов — одним редактируемым файлом на согласование'}
                        style={{ ...btn(false), height: 36, opacity: miss.length ? .45 : 1, cursor: miss.length ? 'not-allowed' : 'pointer' }}>
                  {busy === 'docx+' ? 'Собираю…' : 'DOCX'}
                </button>
                <button onClick={() => download('pdf', true)} disabled={!!busy || !!miss.length}
                        title={miss.length ? 'Сначала заполните недостающее' : 'ДС и основание для закрывающих документов — одним PDF на согласование'}
                        style={{ ...btn(false), height: 36, opacity: miss.length ? .45 : 1, cursor: miss.length ? 'not-allowed' : 'pointer' }}>
                  {busy === 'pdf+' ? 'Собираю…' : 'PDF'}
                </button>
                <span style={{ alignSelf: 'stretch', width: 1, background: 'var(--border-card)', margin: '0 4px' }} />
                <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', alignSelf: 'center', whiteSpace: 'nowrap' }}>Чистовые</span>
                <button onClick={() => download('docx')} disabled={!!busy || !!miss.length || !!legalOpen.length}
                        title={miss.length ? 'Сначала заполните недостающее' : legalOpen.length ? 'Ждёт ответа юриста' : 'Чистовой ДС — редактируемый файл'}
                        style={{ ...btn(false), height: 36, opacity: miss.length || legalOpen.length ? .45 : 1, cursor: miss.length || legalOpen.length ? 'not-allowed' : 'pointer' }}>
                  {busy === 'docx' ? 'Собираю…' : 'DOCX'}
                </button>
                <button onClick={() => download('pdf')} disabled={!!busy || !!miss.length || !!legalOpen.length}
                        title={miss.length ? 'Сначала заполните недостающее' : legalOpen.length ? 'Ждёт ответа юриста' : 'Чистовой ДС на подпись'}
                        style={{ ...primaryBtn, height: 36, opacity: miss.length || legalOpen.length ? .45 : 1, cursor: miss.length || legalOpen.length ? 'not-allowed' : 'pointer' }}>
                  {busy === 'pdf' ? 'Собираю…' : 'PDF'}
                </button>
              </div>
            </div>

            {/* Недостающее названо поимённо и до кнопки: отказ выгрузки без списка
                означал бы «сходи поищи». */}
            {!!miss.length && (
              <div style={{ ...SECTION, background: 'var(--bg-subtle)' }}>
                <div style={{ ...LBL, marginBottom: 8 }}>Документ ещё нельзя выгрузить</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
                  {miss.map((m, i) => <li key={i}>{m}</li>)}
                </ul>
              </div>
            )}

            {/* Правка пунктов зоны аккаунта (до таблицы МП) — конструктор над самим документом, такой же, как у основания закрывающих. У черновика
                и у подтверждённого, пока оно не ушло в 1С (сервер откажет, если ушло). Пункты после таблицы правит юрист. */}
            {a.model && a.model.blocks && !a.model_legacy && (
              <div style={SECTION}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                  {a.model.blocks.filter(b => !b.sys && b.zone === 'acc').map((b, i) => (
                    <AnnexQuickEdit key={b.id} title={`Пункт ${b.num} ${b.title || ''}`} hint="до таблицы медиаплана — правит аккаунт"
                                    source={b.source_text != null ? b.source_text : (b.template_text || '')} defaultText={b.template_text} edited={!!b.edited} inheritedFrom={b.inherited_from} values={a.model.values}
                                    canEdit={mayEdit} onSave={(txt) => saveEdit(b.id, txt)}
                                    aside={i === 0 ? <AnnexDateField value={a.date} periodFrom={a.period_from} canEdit={mayEdit} onSave={saveDate} /> : null} />
                  ))}
                </div>
              </div>
            )}

            {/* Документ по шаблону ДС (спринт 2): тексты пунктов, таблица «бренд → услуги → допы», стороны. Собранные до конструктора
                показываются прежним расчётом ниже. */}
            <div style={SECTION}>
              <AnnexModelPanel state={{ model: a.model, frozen: a.model_frozen, legacy: a.model_legacy, reason: a.model_reason, template_state: a.template_state }}
                               onRebuild={mayEdit && !a.is_draft ? rebuild : undefined} rebuildBusy={busy === 'rebuild'}
                               actions={a.model && a.model.blocks && !a.model_legacy
                                 ? <AnnexLegalButton annexId={a.id} canEdit={mayEdit} onChange={load} lawBlocks={a.model.blocks.filter(b => !b.sys && b.zone === 'law')} />
                                 : null} />
            </div>

            {/* Основание для закрывающих документов (УПД и счёт — один текст). Генерируется по образцу и правится здесь; у подтверждённого
                правится тоже — это не текст подписанного ДС. */}
            {a.model && a.model.closing_basis && (
              <div style={SECTION}>
                <AnnexQuickEdit title="Основание для закрывающих документов" hint="попадёт в УПД и счёт; можно скопировать"
                                source={a.model.closing_basis.template}
                                edited={a.model.closing_basis.edited} inheritedFrom={a.model.closing_basis.inherited_from} values={a.model.values} canEdit={mayEdit} copy
                                onSave={(t) => saveEdit('closing_basis', t)} />
              </div>
            )}

            {!a.model && <div style={SECTION}>
              <div style={{ ...LBL, marginBottom: 10 }}>Медиаплан в документе</div>
              {rows.length ? (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead><tr>
                      <th style={th}>Позиция</th><th style={th}>Гео</th><th style={th}>Формат</th>
                      <th style={th}>Девайс</th><th style={th}>Ротация</th><th style={th}>Модель</th>
                      <th style={{ ...th, textAlign: 'right' }}>Объём</th>
                      <th style={{ ...th, textAlign: 'right' }}>Цена/ед</th>
                      <th style={{ ...th, textAlign: 'right' }}>Стоимость</th>
                    </tr></thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i}>
                          <td style={td}>{r.position || '—'}</td>
                          <td style={td}>{r.geo || '—'}</td>
                          <td style={td}>{r.format || '—'}</td>
                          <td style={td}>{r.device || '—'}</td>
                          <td style={td}>{r.rotation || '—'}</td>
                          <td style={td}>{r.model || '—'}</td>
                          <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{grp(r.volume)}</td>
                          <td style={{ ...td, textAlign: 'right', fontFamily: MONO }}>{r.bonus ? '—' : grp(r.unit_price)}</td>
                          <td style={{ ...td, textAlign: 'right', fontFamily: MONO, fontWeight: 700 }}>{r.bonus ? '—' : grp(r.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  К приложению не привязана ни одна сделка — таблица размещения в документе будет пустой.
                </div>
              )}
            </div>}
            <div style={SECTION}>
              <div style={{ ...LBL, marginBottom: 10 }}>Суммы</div>
              {/* Разделители вертикальные: без них три величины разной природы — деньги,
                  налог и имя бренда — читаются одной строкой. */}
              <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'stretch' }}>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Стоимость с НДС</div>
                  <div style={{ fontSize: 20, fontWeight: 800 }}>{fmtFull(d?.amount)}</div>
                </div>
                <div style={{ width: 1, background: 'var(--border-card)' }} />
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>в том числе НДС {d?.vat_rate}%</div>
                  <div style={{ fontSize: 20, fontWeight: 800 }}>{fmtFull(d?.vat)}</div>
                </div>
                <div style={{ width: 1, background: 'var(--border-card)' }} />
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Бренд</div>
                  <div style={{ fontSize: 15, fontWeight: 700, paddingTop: 3 }}>{d?.brand || '—'}</div>
                </div>
                {/* Сам договор — отсюда, а не поиском по реестру: приложение проверяют
                    рядом с ним. Ссылка ведёт в ЭДО (сегодня это Диадок), файл отдаёт
                    РУЧКА ДОГОВОРОВ — вторая точка выдачи того же файла означала бы
                    вторые правила доступа к нему. */}
                <div style={{ width: 1, background: 'var(--border-card)' }} />
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Договор</div>
                  {(d?.contract?.link || d?.contract?.has_file) ? (
                      <div style={{ display: 'flex', gap: 8, paddingTop: 5 }}>
                        {!!d?.contract?.link && (
                          <a href={d.contract.link} target="_blank" rel="noopener noreferrer"
                             style={{ ...btn(false), height: 30, display: 'inline-flex',
                                      alignItems: 'center', textDecoration: 'none' }}>
                            {/^https?:\/\/[^/]*diadoc/i.test(d.contract.link) ? 'Открыть в Диадоке' : 'Открыть в ЭДО'} ↗
                          </a>
                        )}
                        {!!d?.contract?.has_file && mayViewContracts && (
                          <button onClick={grabContract} disabled={busy === 'contract'}
                                  style={{ ...btn(false), height: 30 }}>
                            {busy === 'contract' ? 'Скачиваю…' : 'Скачать договор'}
                          </button>
                        )}
                      </div>
                  ) : (
                    /* Пустое место не отличить от неработающей кнопки. Поэтому дыра
                       названа вслух и рядом стоит вход туда, где её закрывают. */
                    <div style={{ paddingTop: 5, fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.5 }}>
                      ссылка в ЭДО не задана, файл не приложен<br />
                      <a href={`/directory/contracts?q=${encodeURIComponent(d?.contract?.number || '')}`}
                         style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
                        Открыть договор в реестре →
                      </a>
                    </div>
                  )}
                </div>
              </div>
              <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
                Прописью: {d?.amount_words || '—'}
              </div>
            </div>

            {/* Порядок блоков (владелец 05.09.2026): шапка → медиаплан → суммы →
                подписанты. Сначала ЧТО размещаем, потом за сколько, и только затем
                кто подписывает — как читается сам документ. */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Party title="Исполнитель" p={d?.executor} onSave={saveSigner} saving={busy === 'signer'} canEdit={mayEdit} />
              <Party title="Заказчик" p={d?.customer} onSave={saveSigner} saving={busy === 'signer'} canEdit={mayEdit} />
            </div>

          </>
        )}
      </div>
    </div>
  )
}
