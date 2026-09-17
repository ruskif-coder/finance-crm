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
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { Cube } from '../../components/LogoLoader'

// Согласование числительного: «удалить 2 договоров» читается как машинный текст,
// а подтверждение сноса — ровно то место, где человек должен читать внимательно.
const plural = (n) => {
  const d = n % 10, dd = n % 100
  if (d === 1 && dd !== 11) return 'договор'
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return 'договора'
  return 'договоров'
}

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
  // Сверка с ОРД: состояние подключения, ход прогона и его отчёт.
  const [conn, setConn] = useState(null)         // {configured, env, base_url}
  const [syncing, setSyncing] = useState('')     // текущий этап словами, '' — не идёт
  const [report, setReport] = useState(null)     // {clients, contracts} — отчёт последнего прогона
  // Чистка зеркала перед сменой контура: отбор по источнику и выбор строк.
  const [src, setSrc] = useState('')             // '' — все
  const [picked, setPicked] = useState(() => new Set())
  const [dropMsg, setDropMsg] = useState(null)

  // localStorage не существует на сервере — читаем право только после монтирования.
  useRefreshOnReturn(() => load())
  useEffect(() => { setMayEdit(can(getPermissions(), 'ord', 'edit')) }, [])
  // Состояние подключения — чтобы экран не предлагал кнопку в пустоту и, главное, ВСЕГДА
  // называл контур: демо и прод это разные кабинеты с разными идентификаторами, и
  // «синхронизировано» без контура через месяц не прочитать.
  useEffect(() => { api.get('/ord/connection', auth()).then(r => setConn(r.data)).catch(() => setConn(null)) }, [])

  /* Сверка зеркала: сначала юрлица, потом договоры. Порядок не переставить — разметка
     договора опирается на `ord_client_id`, который проставляют юрлица.

     В ОРД НИЧЕГО НЕ ПИШЕТ: оба прогона только читают кабинет и заполняют наши колонки.
     Поэтому подтверждение спрашивает не «вы уверены», а называет КОНТУР: опасно здесь
     не действие, а сверка не с тем кабинетом. */
  const syncOrd = async () => {
    const env = (conn && conn.env) || '—'
    if (!window.confirm(
      `Сверить зеркало с кабинетом ОРД, контур «${env}»?\n\n` +
      'Читаются юрлица и договоры, в ОРД ничего не отправляется. ' +
      'Записи, размеченные другим контуром, будут перепроверены.')) return
    setErr(''); setReport(null)
    try {
      setSyncing('юрлица')
      const cl = await api.post('/ord/sync/clients', {}, auth())
      setSyncing('договоры')
      const co = await api.post('/ord/sync/contracts', {}, auth())
      setReport({ clients: cl.data, contracts: co.data })
      await load()
    } catch (e) {
      setErr(e.response?.data?.detail || errText(e))
    } finally { setSyncing('') }
  }

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
      const params = {}
      if (tab === 'initial' && q) params.q = q
      if (tab === 'initial' && src) params.source = src
      const r = await api.get(url, { ...auth(), params })
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

  /* Удаление пачкой — чистка ЗЕРКАЛА, не ОРД: строка вернётся следующим синком, если в
     кабинете она есть. Связанные защищены на сервере и называются поимённо: снести
     изначальный договор, на котором держится сборка доходного, — отдельное решение. */
  const dropPicked = async (withLinks = false) => {
    const ids = [...picked]
    if (!ids.length) return
    if (!window.confirm(
      `Удалить ${ids.length} изнач. ${plural(ids.length)} из нашего зеркала?\n\n` +
      'В ОРД ничего не удаляется — строка вернётся следующим синком, если она есть ' +
      'в кабинете.' + (withLinks ? '\n\nВМЕСТЕ СО СВЯЗЯМИ с нашими доходными договорами.' : ''))) return
    setBusy(true); setErr(''); setDropMsg(null)
    try {
      const r = await api.post('/ord/initial/delete', { ids, with_links: withLinks }, auth())
      setDropMsg(r.data)
      setPicked(new Set())
      await load()
    } catch (e) { setErr(e.response?.data?.detail || errText(e)) }
    finally { setBusy(false) }
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
      <Head><title>ОРД · Аккаунты | SIMB-AD ERP</title></Head>
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
                  background: 'var(--danger)', color: 'var(--on-accent)', fontSize: 11, fontWeight: 700 }}>
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
            <select value={src} onChange={e => { setSrc(e.target.value); setPicked(new Set()) }}
              title="Откуда строка: файл выгрузки, синк с демо или с боевого кабинета"
              style={{ ...inp, width: 190, marginLeft: 8 }}>
              <option value="">источник: любой</option>
              <option value="файл">из файла выгрузки</option>
              <option value="demo">синк · демо</option>
              <option value="prod">синк · ПРОД</option>
              <option value="ручная">заведён руками</option>
            </select>
          )}
          {tab === 'initial' && (
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load()}
              placeholder="рекламодатель, исполнитель, номер или ИНН"
              style={{ ...inp, width: 300, marginLeft: 8 }} />
          )}
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
            строк: {tab === 'pending' ? stuck.length : rows.length}
          </span>
          {/* Контур — ВСЕГДА рядом с кнопкой, а не в настройках: демо и прод это разные
              кабинеты, и «сверено» без контура ничего не значит. Демо у нас ушёл дальше
              прода, так что перепутать их — значит разметить зеркало чужими id. */}
          {conn && (
            <span title={conn.base_url || ''} style={{
              padding: '3px 9px', borderRadius: 8, fontFamily: MONO, fontSize: 11, fontWeight: 700,
              background: conn.env === 'prod' ? 'var(--danger-tint)' : 'var(--accent-tint)',
              color: conn.env === 'prod' ? 'var(--danger)' : 'var(--accent)',
            }}>ОРД · {conn.env === 'prod' ? 'ПРОД' : 'демо'}</span>
          )}
          {mayEdit && conn && conn.configured && (
            <button onClick={syncOrd} disabled={!!syncing}
              title="Прочитать юрлица и договоры из кабинета ОРД в наше зеркало. В ОРД ничего не пишет"
              style={{ ...btnSm(false), display: 'inline-flex', alignItems: 'center', gap: 7,
                cursor: syncing ? 'default' : 'pointer' }}>
              {/* Пока идёт — фирменный кубик и НАЗВАНИЕ ЭТАПА. Прогон ходит в чужой
                  кабинет по каждому юрлицу отдельно и занимает минуты; погасшая кнопка
                  без признака работы читается как «не нажалось». */}
              {syncing ? (<><Cube variant="spinner" size={14} /> сверяю {syncing}…</>) : 'Сверить с ОРД'}
            </button>
          )}
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

        {/* Отчёт сверки. Показываем НЕ «готово», а числа: «нет в ОРД» и «неоднозначных» —
            это список работы человека, и ради него прогон запускают повторно. */}
        {!!report && (
          <div style={{ ...card, padding: 12, marginBottom: 12, fontSize: 13 }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>
              Сверено с ОРД · контур {report.clients.env}
            </div>
            <div style={{ color: 'var(--text-muted)' }}>
              Юрлица: проверено {report.clients.looked}, проставлено {report.clients.matched},
              нет в ОРД {report.clients.not_in_ord.length},
              неоднозначных {report.clients.ambiguous.length},
              отказов {report.clients.failed.length}
              {!!report.clients.requeued && `, перепроверено после смены контура ${report.clients.requeued}`}
              {!!report.clients.cleared && `, снято чужих идентификаторов ${report.clients.cleared}`}.
            </div>
            <div style={{ marginTop: 4, color: 'var(--text-muted)' }}>
              Договоры: прочитано доходных {report.contracts.read?.final ?? 0},
              расходных {report.contracts.read?.outer ?? 0},
              изначальных {report.contracts.read?.initial ?? 0};
              размечено {report.contracts.written?.contracts ?? 0},
              изначальных {report.contracts.written?.initial ?? 0},
              связей {report.contracts.written?.links ?? 0}.
            </div>
            {/* Неоднозначные называем поимённо: выбирать за человека из нескольких
                юрлиц мы отказались сознательно — подставленный не тот id уедет в ЕРИР. */}
            {report.clients.ambiguous.length > 0 && (
              <div style={{ marginTop: 6 }}>
                Разобрать руками:{' '}
                {report.clients.ambiguous.slice(0, 8).map(a => `${a.name} (${a.count})`).join('; ')}
                {report.clients.ambiguous.length > 8 && ' …'}
              </div>
            )}
            {report.contracts.failed?.length > 0 && (
              <div style={{ marginTop: 6, color: 'var(--dot-overdue)' }}>
                Не прочиталось: {report.contracts.failed.map(f => `${f.kind} — ${f.why}`).join('; ')}
              </div>
            )}
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

        {/* Панель чистки появляется ТОЛЬКО когда что-то выбрано: висящая всегда кнопка
            сноса рядом со справочником — приглашение нажать её случайно. */}
        {tab === 'initial' && mayEdit && picked.size > 0 && (
          <div style={{ ...card, padding: '10px 12px', marginBottom: 12, fontSize: 13,
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span>Выбрано {picked.size} {plural(picked.size)}</span>
            <button style={btn} onClick={() => setPicked(new Set())}>Снять выбор</button>
            <button style={{ ...btn, color: 'var(--danger)', borderColor: 'var(--danger)' }}
              disabled={busy} onClick={() => dropPicked(false)}>
              {busy ? 'Удаляю…' : 'Удалить из зеркала'}
            </button>
            <span style={{ color: 'var(--text-faint)', fontSize: 11.5 }}>
              удаляется только у нас — в ОРД ничего не трогаем; связанные со сборкой
              пропускаются и будут названы
            </span>
          </div>
        )}

        {/* Итог чистки: сколько снесли и что пропустили. «Пропущено» — не ошибка, а
            список решений, которые человек должен принять глазами. */}
        {!!dropMsg && (
          <div style={{ ...card, padding: 12, marginBottom: 12, fontSize: 13 }}>
            Удалено {dropMsg.deleted} {plural(dropMsg.deleted)}
            {dropMsg.links_deleted > 0 && `, вместе с ними связей ${dropMsg.links_deleted}`}.
            {dropMsg.kept?.length > 0 && (
              <div style={{ marginTop: 6 }}>
                Пропущены — на них держится сборка наших доходных договоров:{' '}
                {dropMsg.kept.slice(0, 8).map(k => `${k.advertiser || '—'} ${k.number || 'б/н'} (связей ${k.links})`).join('; ')}
                {dropMsg.kept.length > 8 && ' …'}
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
                    {mayEdit && (
                      <th style={{ ...th, width: 30 }}>
                        <input type="checkbox"
                          checked={rows.length > 0 && picked.size === rows.length}
                          onChange={e => setPicked(e.target.checked ? new Set(rows.map(r => r.id)) : new Set())} />
                      </th>
                    )}
                    <th style={th}>Рекламодатель</th><th style={th}>Исполнитель</th>
                    <th style={th}>Номер</th><th style={th}>Дата</th>
                    <th style={th}>Вид</th><th style={th}>Статус</th>
                    <th style={th}>Источник</th>
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
                    {mayEdit && (
                      <td style={td}>
                        <input type="checkbox" checked={picked.has(r.id)}
                          onChange={e => setPicked(p => {
                            const n = new Set(p)
                            if (e.target.checked) n.add(r.id); else n.delete(r.id)
                            return n
                          })} />
                      </td>
                    )}
                    <td style={{ ...td, fontWeight: 600 }}>{r.advertiser?.name || '—'}</td>
                    <td style={td}>{r.contractor?.name || '—'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.number || 'б/н'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.date ? fmtDateFull(r.date) : '—'}</td>
                    <td style={td}>{r.subject_type || '—'}</td>
                    <td style={td}>{r.status || '—'}</td>
                    {/* Источник и число связей рядом: связь — то, из-за чего строку нельзя
                        снести молча, и видно это должно быть ДО выбора. */}
                    <td style={{ ...td, fontFamily: MONO, fontSize: 11.5 }}>
                      <span style={{
                        padding: '1px 7px', borderRadius: 7, fontWeight: 700,
                        background: r.source === 'prod' ? 'var(--danger-tint)'
                          : r.source === 'demo' ? 'var(--accent-tint)' : 'var(--bg-subtle)',
                        color: r.source === 'prod' ? 'var(--danger)'
                          : r.source === 'demo' ? 'var(--accent)' : 'var(--text-muted)',
                      }}>{r.source === 'prod' ? 'ПРОД' : r.source}</span>
                      {r.links > 0 && (
                        <span title="Связан с нашим доходным договором — на нём держится сборка"
                          style={{ marginLeft: 6, color: 'var(--text-faint)' }}>связей {r.links}</span>
                      )}
                    </td>
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
