/**
 * Справочник ОРД — зеркало кабинета МедиаСкаута.
 *
 * Живёт в контуре «Аккаунты», а не в Справочниках: обвязка ОРД — часть работы
 * аккаунта, а не самостоятельный справочник первичных данных (решение владельца
 * 2026-08-25). Подвкладку контура рисует Nav.js из карты, свой компонент не нужен.
 *
 * Две вкладки. Изначальные договоры — своя сущность, первое звено чужой цепочки, у нас
 * ей места в основных справочниках нет. Наши договоры показываются только те, где есть
 * отметка ОРД: две трети реестра к ОРД отношения не имеют, и показывать их здесь было
 * бы шумом.
 *
 * Юрлиц отдельной вкладкой нет — они живут в Контрагентах с колонкой ord_client_id.
 *
 * Третья вкладка — «Зависшие отправки» (11.09.2026, решение владельца: вкладкой, а не
 * отдельным экраном). Журнал отправок пишется и коммитится ДО запроса в ОРД, потому что
 * запись в ЕРИР необратима. Если ответ не вернулся, строка остаётся с пустым
 * `finished_at`, и это означает «создалась запись или нет — НЕИЗВЕСТНО»: повтор по этой
 * сущности сервер закрывает, иначе в реестре появится дубль.
 *
 * Снять блокировку может только человек, сходивший в кабинет ОРД и посмотревший глазами.
 * Ручки для этого были с самого начала, а вызвать их было неоткуда — выйти из тупика
 * удавалось только curl'ом мимо интерфейса. Тупик появляется в худший момент (маркер
 * нужен, а нельзя), и у человека остаются два пути: ждать разработчика или обойти
 * журнал. Второе опаснее исходной беды: журнал — единственное, что стоит между нами и
 * дублем в ЕРИР.
 */
import { useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import { UI, MONO, card, inp, primaryBtn, btnSm, btn, th, td, Modal, LoadError } from '../../components/salesTableKit'
import { errText } from '../../lib/loadError'
import { fmtDateFull } from '../../lib/salesFormat'
import api, { auth } from '../../lib/http'
import { can, getPermissions } from '../../lib/auth'

const TABS = [
  { key: 'initial', label: 'Изначальные договоры' },
  { key: 'contracts', label: 'Наши договоры в ОРД' },
  { key: 'pending', label: 'Зависшие отправки' },
]

// Человеческие имена видов отправки. Ключ приходит с сервера как есть.
const KIND_LABEL = {
  contract: 'договор', creative: 'креатив', invoice: 'акт',
  platform: 'площадка', client: 'юрлицо',
}

export default function OrdDirectory() {
  const [tab, setTab] = useState('initial')
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [stat, setStat] = useState(null)
  const [mayEdit, setMayEdit] = useState(false)
  // Зависшие тянем ВСЕГДА, а не только на своей вкладке: число в заголовке — это и есть
  // сообщение «есть тупик». Спрятать его за переключением вкладок значит показывать
  // проблему только тому, кто уже знает, куда смотреть.
  const [stuck, setStuck] = useState([])
  const [resolving, setResolving] = useState(null)   // строка, по которой отвечаем
  const [foundId, setFoundId] = useState('')
  const [stuckErr, setStuckErr] = useState('')   // отдельно от `err`: у вкладок разные запросы

  // localStorage не существует на сервере — читаем право только после монтирования.
  useEffect(() => { setMayEdit(can(getPermissions(), 'ord', 'edit')) }, [])

  // СБОЙ ≠ ПУСТОТА, и здесь это дороже, чем где-либо на экране. «Зависших отправок нет»
  // читается как «повторной отправки не будет, дубля в ЕРИР не случится». Упавший запрос
  // давал ровно эту надпись — молча, потому что ошибка глоталась ради того, чтобы не
  // ронять соседние вкладки справочника. Не ронять — верно; притворяться чистым журналом
  // — нет. Поэтому ошибку ЗАПОМИНАЕМ отдельно от `err` соседних вкладок и показываем
  // вместо пустого состояния.
  const loadStuck = async () => {
    try {
      const r = await api.get('/ord/submissions/pending', auth())
      setStuck(r.data?.rows || [])
      setStuckErr('')
    } catch (e) {
      setStuck([])
      setStuckErr(errText(e))
    }
  }
  useEffect(() => { loadStuck() }, [])

  const load = async () => {
    setErr('')
    if (tab === 'pending') { await loadStuck(); return }
    try {
      const url = tab === 'initial' ? '/ord/initial' : '/ord/contracts'
      const r = await api.get(url, { ...auth(), params: tab === 'initial' && q ? { q } : {} })
      setRows(r.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить') }
  }
  useEffect(() => { load() }, [tab])

  /* Закрыть зависшую попытку СО СЛОВ человека, сходившего в кабинет.
     Два исхода несимметричны, и это не наша выдумка, а правило сервера:
     · записи НЕТ — попытка закрывается как неудачная, повтор открывается. Безопасно:
       дублировать нечего;
     · запись ЕСТЬ — попытка закрывается с найденным идентификатором, но повтор
       ОСТАЁТСЯ закрытым: отправить ещё раз значило бы завести второй объект в ЕРИР. */
  const resolve = async (row, found, ordId) => {
    setErr('')
    try {
      const r = await api.post(`/ord/submissions/${row.id}/resolve`,
        { found, ord_id: ordId || null }, auth())
      setResolving(null); setFoundId('')
      await loadStuck()
      setErr('')
      setStat(null)
      alert(r.data?.retry_allowed
        ? 'Попытка закрыта, повтор разрешён.'
        : 'Попытка закрыта. Повтор остаётся запрещённым — запись в кабинете уже есть.')
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось закрыть попытку') }
  }

  const upload = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    // Кабинет отдаёт три файла с говорящими именами — раскладываем по полям сами,
    // чтобы не заставлять человека выбирать трижды.
    const fd = new FormData()
    for (const f of files) {
      const n = f.name.toLowerCase()
      if (n.includes('изначальн')) fd.append('initial', f)
      else if (n.includes('доходн')) fd.append('final', f)
      else if (n.includes('расходн')) fd.append('outer', f)
    }
    setBusy(true); setErr(''); setStat(null)
    try {
      const r = await api.post('/ord/import', fd, auth())
      setStat(r.data); load()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось загрузить файл') }
    finally { setBusy(false); e.target.value = '' }
  }

  return (
    <>
      <Head><title>ОРД · Справочник</title></Head>
      <Navbar />
      <div style={{ padding: '18px 22px', fontFamily: UI }}>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={btnSm(tab === t.key)}>
              {t.label}
              {/* Число рядом с ярлыком — само сообщение. Пока зависших нет, значка нет
                  тоже: пустая «0» приучает не смотреть. */}
              {t.key === 'pending' && stuck.length > 0 && (
                <span style={{ marginLeft: 6, padding: '1px 6px', borderRadius: 7,
                  background: 'var(--danger)', color: '#fff', fontSize: 11, fontWeight: 700 }}>
                  {stuck.length}
                </span>
              )}
              {/* Запрос не дошёл — значок «?», а не отсутствие значка. Пустой ярлык
                  здесь означал бы «тупиков нет», то есть утверждение, которого мы
                  сделать не можем. */}
              {t.key === 'pending' && !!stuckErr && (
                <span title="Список не загрузился" style={{ marginLeft: 6, padding: '1px 6px',
                  borderRadius: 7, background: 'var(--warning-tint)', color: 'var(--danger)',
                  fontSize: 11, fontWeight: 700 }}>?</span>
              )}
            </button>
          ))}
          {tab === 'initial' && (
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load()}
              placeholder="рекламодатель, исполнитель, номер или ИНН"
              style={{ ...inp, width: 300, marginLeft: 8 }} />
          )}
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
            строк: {tab === 'pending' ? stuck.length : rows.length}
          </span>
          {mayEdit && (
            <label style={{ ...primaryBtn, cursor: busy ? 'default' : 'pointer' }}>
              {busy ? 'Загрузка…' : 'Загрузить выгрузку'}
              <input type="file" accept=".xlsx" multiple onChange={upload}
                style={{ display: 'none' }} disabled={busy} />
            </label>
          )}
        </div>

        {!!err && (
          <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--dot-overdue)' }}>
            {err}
          </div>
        )}

        {!!stat && (
          <div style={{ ...card, padding: 12, marginBottom: 12, fontSize: 13 }}>
            <div style={{ color: 'var(--text-muted)' }}>
              Прочитано строк: изначальных {stat.read_initial ?? 0},
              доходных {stat.read_final ?? 0}, расходных {stat.read_outer ?? 0}.
            </div>
            <div style={{ marginTop: 4 }}>
              Заведено: изначальных {stat.initial}, связей {stat.links},
              договоров помечено {stat.contracts}, контрагентов сопоставлено по ИНН {stat.clients}.
            </div>
            {/* «Заведено» по нулям на повторной загрузке — норма: импорт
                идемпотентен. «Прочитано» по нулям при непустом файле — нет: значит
                приложен не тот файл, или кабинет переименовал колонку (см.
                предупреждение ниже) — по одним «заведено 0» эти два случая было не
                различить. */}
            {!!stat.warnings?.length && (
              <div style={{ marginTop: 8, color: 'var(--dot-current-dz)', fontSize: 12 }}>
                предупреждений {stat.warnings.length} — договоры ОРД, которых нет
                в нашем реестре, незнакомые значения справочников, и листы, где
                прочитанные строки не распознаны ни разу
              </div>
            )}
          </div>
        )}

        {tab === 'pending' && (
          <div style={{ ...card, padding: 14, marginBottom: 12, fontSize: 12.5,
            lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Строка попадает сюда, когда запрос в ОРД ушёл, а ответ не вернулся: создалась
            запись у оператора или нет — <b>неизвестно</b>. Пока она здесь, повтор по этой
            сущности закрыт, и это защита: слепой повтор завёл бы <b>дубль в ЕРИР</b>,
            а удалить его оттуда нельзя.
            <div style={{ marginTop: 6 }}>
              Снять блокировку можно только сходив в кабинет ОРД и посмотрев, есть ли там
              запись. Отвечать наугад нельзя — ответ «записи нет» открывает повтор.
            </div>
          </div>
        )}

        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
            {tab === 'pending' ? (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={th}>Что отправляли</th><th style={th}>Наш id</th>
                    <th style={th}>Контур</th><th style={th}>Ушло</th>
                    <th style={th}>След</th><th style={th}></th>
                  </tr>
                </thead>
                <tbody>
                  {stuck.length === 0 && !stuckErr && (
                    <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>
                      Зависших отправок нет — все попытки завершились ответом.
                    </td></tr>
                  )}
                  {!!stuckErr && (
                    <tr><td colSpan={6} style={{ ...td, padding: 0 }}>
                      <LoadError text={stuckErr} onRetry={loadStuck} />
                    </td></tr>
                  )}
                  {stuck.map(r => (
                    <tr key={r.id}>
                      <td style={{ ...td, fontWeight: 600 }}>{KIND_LABEL[r.kind] || r.kind}</td>
                      <td style={{ ...td, fontFamily: MONO }}>{r.local_id ?? '—'}</td>
                      <td style={td}>
                        <span style={{ padding: '1px 7px', borderRadius: 7, fontSize: 11.5,
                          background: r.env === 'prod' ? 'var(--danger-tint)' : 'var(--warning-tint)',
                          color: r.env === 'prod' ? 'var(--danger)' : 'var(--warning-text)' }}>
                          {r.env}
                        </span>
                      </td>
                      <td style={{ ...td, fontFamily: MONO }}>
                        {r.started_at ? fmtDateFull(r.started_at) : '—'}</td>
                      <td style={{ ...td, fontSize: 12, color: 'var(--text-muted)' }}>
                        {r.error || 'ответа не было'}</td>
                      <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {mayEdit ? (
                          <>
                            <button style={{ ...btn(false), padding: '4px 10px', fontSize: 12 }}
                              onClick={() => { if (window.confirm('Вы проверили кабинет ОРД и записи там НЕТ? Повтор будет разрешён.')) resolve(r, false) }}>
                              записи нет
                            </button>
                            <button style={{ ...btn(false), padding: '4px 10px', fontSize: 12, marginLeft: 6 }}
                              onClick={() => { setResolving(r); setFoundId('') }}>
                              запись нашлась
                            </button>
                          </>
                        ) : <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>нужно право на правку</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                {tab === 'initial' ? (
                  <tr>
                    <th style={th}>Рекламодатель</th><th style={th}>Исполнитель</th>
                    <th style={th}>Номер</th><th style={th}>Дата</th>
                    <th style={th}>Вид</th><th style={th}>Статус</th>
                  </tr>
                ) : (
                  <tr>
                    <th style={th}>Номер</th><th style={th}>Дата</th>
                    <th style={th}>Контрагент</th><th style={th}>Вид</th>
                    <th style={th}>Статус в ОРД</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>
                    {tab === 'initial'
                      ? 'Пусто. Загрузите выгрузку изначальных договоров из кабинета ОРД.'
                      : 'Ни у одного договора нет отметки ОРД.'}
                  </td></tr>
                )}
                {rows.map(r => tab === 'initial' ? (
                  <tr key={r.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.advertiser?.name || '—'}</td>
                    <td style={td}>{r.contractor?.name || '—'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.number || 'б/н'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.date ? fmtDateFull(r.date) : '—'}</td>
                    <td style={td}>{r.subject_type || '—'}</td>
                    <td style={td}>{r.status || '—'}</td>
                  </tr>
                ) : (
                  <tr key={r.id}>
                    <td style={{ ...td, fontFamily: MONO }}>{r.number || 'б/н'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.date ? fmtDateFull(r.date) : '—'}</td>
                    <td style={td}>{r.counterparty || '—'}</td>
                    <td style={td}>{r.ord_kind === 'outer' ? 'расходный' : 'доходный'}</td>
                    <td style={td}>{r.ord_status || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}
          </div>
        </div>
      </div>

      {/* Идентификатор набирает человек, глядя в чужой кабинет, поэтому окно, а не
          `prompt`: нужно место для объяснения, чем этот ответ отличается от «записи
          нет». После него повтор ОСТАЁТСЯ закрытым. */}
      {!!resolving && (
        <Modal width={520} title="Запись в кабинете ОРД нашлась"
          summary={`${KIND_LABEL[resolving.kind] || resolving.kind} · наш id ${resolving.local_id ?? '—'} · контур ${resolving.env}`}
          onClose={() => { setResolving(null); setFoundId('') }}
          footer={(
            <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button style={btn(false)} onClick={() => { setResolving(null); setFoundId('') }}>Отмена</button>
              <button style={{ ...btn(true), opacity: foundId.trim() ? 1 : 0.5,
                cursor: foundId.trim() ? 'pointer' : 'not-allowed' }}
                disabled={!foundId.trim()}
                onClick={() => resolve(resolving, true, foundId.trim())}>
                Закрыть попытку
              </button>
            </span>
          )}>
          <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
            <div>Введите идентификатор записи, которую вы видите в кабинете ОРД.</div>
            <input value={foundId} onChange={e => setFoundId(e.target.value)}
              placeholder="идентификатор из кабинета" style={{ ...inp, width: '100%' }} />
            <div style={{ color: 'var(--text-muted)' }}>
              Повторная отправка останется <b>запрещённой</b>: объект в реестре уже есть,
              и вторая попытка создала бы дубль. Привязку идентификатора к нашей записи
              сделает обычная сверка — она сопоставляет по ИНН и номеру и не полагается
              на то, что здесь не ошиблись строкой.
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
