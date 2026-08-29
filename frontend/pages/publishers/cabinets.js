/**
 * Кабинеты паблишеров — настройка со стороны ядра.
 *
 * Порядок работы (владелец, 28.08.2026): пустой кабинет → площадки → доступы людям →
 * рабочие чаты. Экран повторяет его сверху вниз, а не раскладывает по вкладкам: это
 * последовательность, и каждый следующий шаг бессмысленен без предыдущего.
 *
 * Три вещи, которые экран обязан показывать сам, без вопросов:
 *
 *  · **готовность площадки.** Без кода пара не получит имени, и согласование упрётся в
 *    ошибку уже после того, как человек вошёл. Проблемы видно ДО выдачи доступа;
 *  · **чья площадка.** Она живёт ровно в одном кабинете, поэтому список выбора
 *    показывает только свободные — запрет при выборе, а не ошибка при сохранении;
 *  · **как передать пароль.** Почтового канала у внешнего контура нет: рядом с выдачей
 *    стоит ссылка на рабочий чат площадки.
 */
import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, card, CAP, btn, btnSm, inp, ROW_TONE, Modal, PickValue }
  from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import api, { auth } from '@/lib/api'

const STATE_TONE = {
  'активен': ['var(--income-tint)', 'var(--income)'],
  'черновик': ['var(--bg-subtle)', 'var(--text-muted)'],
  'приостановлен': ['var(--danger-tint)', 'var(--danger)'],
  'работает': ['var(--income-tint)', 'var(--income)'],
  'нет пароля': ['var(--warning-tint)', 'var(--warning-text)'],
  'отключён': ['var(--bg-subtle)', 'var(--text-faint)'],
}

const Chip = ({ text, tone }) => {
  const [bg, fg] = STATE_TONE[tone || text] || STATE_TONE['отключён']
  return <span style={{ background: bg, color: fg, borderRadius: 999, padding: '2px 9px',
    fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{text}</span>
}

/* Компоненты выбора — на модульном уровне: объявленный внутри рендера родителя
   пересоздаётся на каждый ввод, и фокус в поле поиска слетает после каждого символа. */
function FreePublishers({ options, selected, onToggle }) {
  const [q, setQ] = useState('')
  const list = options.filter(p => !q
    || (p.name || '').toLowerCase().includes(q.toLowerCase())
    || (p.domain || '').toLowerCase().includes(q.toLowerCase()))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <input style={{ ...inp, flex: 1 }} placeholder="Поиск площадки"
          value={q} onChange={e => setQ(e.target.value)} />
        <span style={{ ...CAP, marginBottom: 0 }}>выбрано {selected.length}</span>
      </div>
      <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--border-card)',
        borderRadius: 10 }}>
        {list.map(p => (
          <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 9,
            padding: '7px 10px', borderBottom: '1px solid var(--border-row)', cursor: 'pointer' }}>
            <input type="checkbox" checked={selected.includes(p.id)}
              onChange={() => onToggle(p.id)} />
            <span style={{ fontSize: 13 }}>{p.name}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
              {p.domain}
            </span>
            <span style={{ flex: 1 }} />
            {/* Проблемы видно ДО прикрепления: площадка без кода доведёт человека до
                ошибки только на кнопке «Согласовать», когда он уже вошёл. */}
            {p.problems?.length
              ? <span style={{ fontSize: 11, color: 'var(--warning-text)' }}
                  title={p.problems.join('; ')}>⚠ {p.problems.length}</span>
              : <span style={{ ...CAP, marginBottom: 0 }}>готова</span>}
          </label>
        ))}
        {!list.length && (
          <div style={{ padding: '12px 10px', fontSize: 12.5, color: 'var(--text-faint)' }}>
            Свободных площадок нет — все уже в кабинетах
          </div>
        )}
      </div>
    </div>
  )
}

export default function Cabinets() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [newCab, setNewCab] = useState(null)     // { name, manager_id, note }
  const [attach, setAttach] = useState(null)     // { cabinet, ids }
  const [access, setAccess] = useState(null)     // { cabinet, publisher, contacts }
  const [chats, setChats] = useState(null)       // { publisher, ...поля }
  const [shown, setShown] = useState(null)       // { email, password, chat }
  const [showAll, setShowAll] = useState({})     // какие кабинеты раскрыты целиком
  const [newC, setNewC] = useState(null)         // форма нового контактного лица
  const [pos, setPos] = useState(null)           // поповер должности

  const mayEdit = can('dir_publishers_cabinets', 'edit')

  const load = useCallback(async () => {
    setErr('')
    try { setData((await api.get('/cabinets/', auth())).data) }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить кабинеты') }
  }, [])

  useEffect(() => { load() }, [load])

  const run = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); await load() }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось выполнить') }
    setBusy(false)
  }

  const openAccess = async (cabinet, publisher) => {
    setErr('')
    try {
      const r = await api.get(`/cabinets/publisher/${publisher.id}/contacts`, auth())
      setAccess({ cabinet, publisher, contacts: r.data.contacts || [] })
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось открыть контакты') }
  }

  const grant = async (contact, canApprove) => {
    setBusy(true); setErr('')
    try {
      await api.post(`/cabinets/${access.cabinet.id}/accounts`,
        { contact_id: contact.id, can_approve: canApprove }, auth())
      await openAccess(access.cabinet, access.publisher)
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось выдать доступ') }
    setBusy(false)
  }

  const issuePassword = async (acc, cabinet) => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/cabinets/accounts/${acc.id}/password`, {}, auth())
      const pub = (cabinet.publishers || []).find(p => p.chat_url || p.chat_url_max)
      setShown({ email: acc.email, password: r.data.password,
        chat: pub ? { url: pub.chat_url || pub.chat_url_max, name: pub.name } : null })
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось выдать пароль') }
    setBusy(false)
  }

  const cabinets = data?.cabinets || []

  return (
    <>
      <Head><title>Кабинеты паблишеров</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '22px 20px 60px', fontFamily: UI }}>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 6 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>Кабинеты паблишеров</h1>
          <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>
            {data ? `${cabinets.length} кабинетов · свободных площадок ${data.free_publishers.length}`
                  : 'загрузка…'}
          </span>
          <span style={{ flex: 1 }} />
          {mayEdit && (
            <button style={btn(true)} onClick={() => setNewCab({ name: '', manager_id: '', note: '' })}>
              + Кабинет
            </button>
          )}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 16,
          lineHeight: 1.5, maxWidth: 780 }}>
          Кабинет — это организация: сеть или одиночная площадка. Порядок такой: завести
          пустой → прикрепить площадки → выдать доступ их контактам → настроить чаты.
          <b> Площадка живёт ровно в одном кабинете</b>, поэтому к выбору предлагаются
          только свободные.
        </div>

        {!!err && (
          <div style={{ ...card, padding: '10px 14px', marginBottom: 14, color: 'var(--danger)',
            borderColor: ROW_TONE.overdue.border, background: ROW_TONE.overdue.bg }}>{err}</div>
        )}

        {cabinets.map(c => (
          <div key={c.id} style={{ ...card, padding: '16px 18px', marginBottom: 14 }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 16, fontWeight: 800 }}>{c.name}</span>
              {c.kind === 'служебный' && <Chip text="служебный" tone="черновик" />}
              <Chip text={c.state} />
              {!!c.manager && (
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  ведёт {c.manager}
                </span>
              )}
              <span style={{ flex: 1 }} />
              {mayEdit && c.kind !== 'служебный' && (
                <button style={btnSm(false)} disabled={busy}
                  onClick={() => setAttach({ cabinet: c, ids: [] })}>+ Площадки</button>
              )}
              {mayEdit && (
                <button style={btnSm(false)} disabled={busy}
                  title={c.state === 'активен'
                    ? 'Приостановить — люди кабинета сразу перестанут видеть задания'
                    : 'Активировать кабинет'}
                  onClick={() => run(() => api.put(`/cabinets/${c.id}`,
                    { state: c.state === 'активен' ? 'приостановлен' : 'активен' }, auth()))}>
                  {c.state === 'активен' ? 'Приостановить' : 'Активировать'}
                </button>
              )}
            </div>

            {/* площадки */}
            <div style={{ marginTop: 12 }}>
              <div style={{ ...CAP, marginBottom: 6 }}>
                площадки · {c.publishers.length}
                {c.kind === 'служебный' && ' · видит все, связей не хранит'}
              </div>
              {!c.publishers.length && (
                <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
                  Пусто — прикрепите площадки, иначе людям нечего будет показать
                </div>
              )}
              {/* Колонки ФИКСИРОВАНЫ по ширине, а не долевые. При 1600 доля 1.2fr
                  растягивала имя площадки на семьсот пикселей, и домен уезжал в середину
                  экрана — читалось как разъехавшаяся таблица. Имя и домен относятся к
                  одному объекту и должны стоять рядом.
                  Комментарий стоит НАД `map`, а не внутри: JSX-комментарий первым
                  выражением в `(` — синтаксическая ошибка, и сборка падает без указания
                  на причину. */}
              {(showAll[c.id] ? c.publishers : c.publishers.slice(0, 8)).map(p => (
                <div key={p.id} style={{ display: 'grid',
                  gridTemplateColumns: 'minmax(0,240px) minmax(0,170px) minmax(0,1fr) auto',
                  gap: 12, alignItems: 'center', padding: '7px 0',
                  borderBottom: '1px solid var(--border-row)' }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
                    {p.domain}
                  </span>
                  <span style={{ fontSize: 11.5, color: p.problems.length
                    ? 'var(--warning-text)' : 'var(--text-faint)' }}>
                    {p.problems.length ? `⚠ ${p.problems.join(' · ')}` : 'готова к работе'}
                  </span>
                  <span style={{ display: 'inline-flex', gap: 6 }}>
                    {!!(p.chat_url || p.chat_url_max) && (
                      <a href={p.chat_url || p.chat_url_max} target="_blank" rel="noreferrer"
                        style={{ ...btnSm(false), textDecoration: 'none', fontSize: 11 }}>
                        Чат ↗
                      </a>
                    )}
                    {mayEdit && (
                      <>
                        <button style={{ ...btnSm(false), fontSize: 11 }}
                          onClick={() => setChats({ publisher: p, chat_title: p.chat_title || '',
                            chat_url: p.chat_url || '', chat_url_max: p.chat_url_max || '' })}>
                          Чаты
                        </button>
                        <button style={{ ...btnSm(false), fontSize: 11 }}
                          onClick={() => openAccess(c, p)}>Доступы</button>
                        {c.kind !== 'служебный' && (
                          <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy}
                            onClick={() => run(() => api.delete(
                              `/cabinets/${c.id}/publishers/${p.id}`, auth()))}>×</button>
                        )}
                      </>
                    )}
                  </span>
                </div>
              ))}
              {/* Свёртка не косметика: у служебного кабинета 41 площадка, и без неё
                  список людей уезжает за экран, а именно он нужен чаще. */}
              {c.publishers.length > 8 && (
                <button style={{ ...btnSm(false), marginTop: 8, fontSize: 11 }}
                  onClick={() => setShowAll({ ...showAll, [c.id]: !showAll[c.id] })}>
                  {showAll[c.id] ? 'Свернуть' : `Показать все ${c.publishers.length}`}
                </button>
              )}
            </div>

            {/* люди */}
            <div style={{ marginTop: 14 }}>
              <div style={{ ...CAP, marginBottom: 6 }}>люди · {c.accounts.length}</div>
              {!c.accounts.length && (
                <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
                  Доступов нет — выдайте их контактам площадки кнопкой «Доступы»
                </div>
              )}
              {c.accounts.map(a => (
                <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 10,
                  padding: '7px 0', borderBottom: '1px solid var(--border-row)',
                  flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{a.name}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>
                    {a.email}
                  </span>
                  <Chip text={a.state} />
                  <Chip text={a.can_approve ? 'согласует' : 'только просмотр'}
                    tone={a.can_approve ? 'активен' : 'черновик'} />
                  <span style={{ flex: 1 }} />
                  {mayEdit && (
                    <>
                      <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy}
                        onClick={() => issuePassword(a, c)}>Выдать пароль</button>
                      <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy}
                        onClick={() => run(() => api.put(`/cabinets/accounts/${a.id}`,
                          { can_approve: !a.can_approve }, auth()))}>
                        {a.can_approve ? 'Снять согласование' : 'Разрешить согласование'}
                      </button>
                      <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy}
                        onClick={() => run(() => api.put(`/cabinets/accounts/${a.id}`,
                          { is_active: !a.is_active }, auth()))}>
                        {a.is_active ? 'Отключить' : 'Включить'}
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {newCab && (
        <Modal title="Новый кабинет" width={560} onClose={() => setNewCab(null)}
          summary="Кабинет заводится пустым: площадки и люди добавляются следом. Пустой кабинет — не ошибка, а первый шаг."
          footer={<>
            <button style={btn(false)} onClick={() => setNewCab(null)}>Отмена</button>
            <button style={btn(true)} disabled={busy || !newCab.name.trim()}
              onClick={() => run(async () => {
                await api.post('/cabinets/', { name: newCab.name,
                  manager_id: newCab.manager_id || null, note: newCab.note }, auth())
                setNewCab(null)
              })}>Создать</button>
          </>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input style={inp} placeholder="Название — сеть или площадка"
              value={newCab.name} onChange={e => setNewCab({ ...newCab, name: e.target.value })} />
            <select style={inp} value={newCab.manager_id}
              onChange={e => setNewCab({ ...newCab, manager_id: e.target.value })}>
              <option value="">Наш ответственный — не выбран</option>
              {(data?.managers || []).map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            <textarea style={{ ...inp, minHeight: 60, fontFamily: UI, resize: 'vertical' }}
              placeholder="Заметка" value={newCab.note}
              onChange={e => setNewCab({ ...newCab, note: e.target.value })} />
          </div>
        </Modal>
      )}

      {attach && (
        <Modal title={`Площадки · ${attach.cabinet.name}`} width={680}
          onClose={() => setAttach(null)}
          summary="Предлагаются только свободные: площадка живёт ровно в одном кабинете, иначе задание появилось бы у двоих и второй ответ был бы отклонён."
          footer={<>
            <button style={btn(false)} onClick={() => setAttach(null)}>Отмена</button>
            <button style={btn(true)} disabled={busy || !attach.ids.length}
              onClick={() => run(async () => {
                await api.post(`/cabinets/${attach.cabinet.id}/publishers`,
                  { publisher_ids: attach.ids }, auth())
                setAttach(null)
              })}>Прикрепить</button>
          </>}>
          <FreePublishers options={data?.free_publishers || []} selected={attach.ids}
            onToggle={(id) => setAttach({ ...attach,
              ids: attach.ids.includes(id) ? attach.ids.filter(x => x !== id)
                : [...attach.ids, id] })} />
        </Modal>
      )}

      {access && (
        <Modal title={`Доступы · ${access.publisher.name}`} width={640}
          onClose={() => setAccess(null)}
          summary="Доступ выдаётся КОНТАКТУ площадки, а не заводится новым человеком: контакты уже в реестре, и вторая запись означала бы две точки правки."
          footer={<button style={btn(true)} onClick={() => setAccess(null)}>Готово</button>}>
          {access.contacts.map(k => (
            <div key={k.id} style={{ display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 0', borderBottom: '1px solid var(--border-row)', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{k.name}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>
                {k.email || 'без почты'}
              </span>
              {!!k.role && <span style={{ ...CAP, marginBottom: 0 }}>{k.role}</span>}
              <span style={{ flex: 1 }} />
              {k.account_id
                ? <Chip text={k.is_active ? 'доступ выдан' : 'отключён'}
                    tone={k.is_active ? 'активен' : 'отключён'} />
                : mayEdit && (
                  <span style={{ display: 'inline-flex', gap: 6 }}>
                    <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy || !k.email}
                      title={k.email ? 'Может смотреть и отвечать' : 'У контакта нет почты — по ней он входит'}
                      onClick={() => grant(k, true)}>Создать учётку</button>
                    <button style={{ ...btnSm(false), fontSize: 11 }} disabled={busy || !k.email}
                      onClick={() => grant(k, false)}>Учётка · только просмотр</button>
                  </span>
                )}
            </div>
          ))}
          {!access.contacts.length && (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '10px 0' }}>
              Контактных лиц пока нет — добавьте первое.
            </div>
          )}

          {/* Контактное лицо заводится ЗДЕСЬ, а не в карточке площадки: доступ выдаётся
              контакту, и уходить за ним на другой экран посреди настройки кабинета —
              верный способ забыть, на чём остановился. Запись одна и та же
              (`sales_publisher_contacts`), второго списка людей не появляется. */}
          {mayEdit && (newC ? (
            <div style={{ marginTop: 12, background: 'var(--bg-subtle)',
              border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px 14px',
              display: 'flex', flexDirection: 'column', gap: 9 }}>
              <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
                <input style={{ ...inp, flex: '1 1 220px' }} placeholder="Имя и фамилия"
                  value={newC.name} onChange={e => setNewC({ ...newC, name: e.target.value })} />
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  <PickValue value={newC.role} placeholder="должность"
                    onOpen={e => setPos({ rect: e.currentTarget.getBoundingClientRect() })} />
                </span>
              </div>
              <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
                <input style={{ ...inp, flex: '1 1 200px' }} placeholder="Почта — по ней вход"
                  value={newC.email} onChange={e => setNewC({ ...newC, email: e.target.value })} />
                <input style={{ ...inp, flex: '1 1 150px' }} placeholder="Телефон"
                  value={newC.phone} onChange={e => setNewC({ ...newC, phone: e.target.value })} />
                <input style={{ ...inp, flex: '1 1 150px' }} placeholder="Телеграм"
                  value={newC.telegram} onChange={e => setNewC({ ...newC, telegram: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={btn(false)} onClick={() => setNewC(null)}>Отмена</button>
                <span style={{ flex: 1 }} />
                <button style={btn(true)} disabled={busy || !newC.name.trim()}
                  onClick={async () => {
                    setBusy(true); setErr('')
                    try {
                      await api.post(`/publishers/${access.publisher.id}/contacts`, {
                        name: newC.name, role: newC.role || null, email: newC.email || null,
                        phone: newC.phone || null, telegram: newC.telegram || null }, auth())
                      setNewC(null)
                      await openAccess(access.cabinet, access.publisher)
                    } catch (e2) {
                      setErr(e2.response?.data?.detail || 'Не удалось добавить контакт')
                    }
                    setBusy(false)
                  }}>Добавить</button>
              </div>
            </div>
          ) : (
            <button style={{ ...btn(false), marginTop: 12 }}
              onClick={() => setNewC({ name: '', role: '', email: '', phone: '', telegram: '' })}>
              + Контактное лицо
            </button>
          ))}

          {/* Поповер должности — потомок модалки, иначе уходит под неё по z-index. */}
          {pos && (
            <ValuePopover anchor={pos.rect} title="Должность" value={newC?.role}
              clearLabel="— не указана —"
              options={(data?.positions || []).map(x => ({ value: x.name, label: x.name }))}
              onAddNew={async (name) => {
                try {
                  await api.post('/publishers/positions', { name }, auth())
                  setNewC({ ...newC, role: name })
                  setPos(null)
                  await load()
                } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось добавить') }
              }}
              onPick={(v) => { setNewC({ ...newC, role: v || '' }); setPos(null) }}
              onClose={() => setPos(null)} />
          )}
        </Modal>
      )}

      {chats && (
        <Modal title={`Рабочие чаты · ${chats.publisher.name}`} width={560}
          onClose={() => setChats(null)}
          summary="Наш канал связи с площадкой — Телеграм и MAX. Площадке они не показываются: внутри кабинета остаётся только переписка по конкретному заданию."
          footer={<>
            <button style={btn(false)} onClick={() => setChats(null)}>Отмена</button>
            <button style={btn(true)} disabled={busy}
              onClick={() => run(async () => {
                await api.put(`/cabinets/publisher/${chats.publisher.id}/chats`, {
                  chat_title: chats.chat_title, chat_url: chats.chat_url,
                  chat_url_max: chats.chat_url_max }, auth())
                setChats(null)
              })}>Сохранить</button>
          </>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input style={inp} placeholder="Название чата" value={chats.chat_title}
              onChange={e => setChats({ ...chats, chat_title: e.target.value })} />
            <input style={{ ...inp, fontFamily: MONO, fontSize: 12.5 }}
              placeholder="Телеграм — https://t.me/…" value={chats.chat_url}
              onChange={e => setChats({ ...chats, chat_url: e.target.value })} />
            <input style={{ ...inp, fontFamily: MONO, fontSize: 12.5 }}
              placeholder="MAX — https://…" value={chats.chat_url_max}
              onChange={e => setChats({ ...chats, chat_url_max: e.target.value })} />
          </div>
        </Modal>
      )}

      {shown && (
        <Modal title="Пароль выдан" width={540} onClose={() => setShown(null)}
          summary="Показывается один раз — в базе только хеш. Почтового канала у кабинета нет, передайте пароль рабочим чатом."
          footer={<button style={btn(true)} onClick={() => setShown(null)}>Готово</button>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{shown.email}</div>
            <div onClick={() => navigator.clipboard?.writeText(shown.password)}
              title="Скопировать"
              style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, cursor: 'pointer',
                background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
                borderRadius: 10, padding: '12px 14px', wordBreak: 'break-all' }}>
              {shown.password}
            </div>
            {shown.chat
              ? <a href={shown.chat.url} target="_blank" rel="noreferrer"
                  style={{ ...btn(false), textDecoration: 'none', textAlign: 'center' }}>
                  Написать в чат · {shown.chat.name}
                </a>
              : <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                  У площадок кабинета не заведён чат — передать пароль нечем.
                  Заполните его кнопкой «Чаты».
                </div>}
          </div>
        </Modal>
      )}
    </>
  )
}
