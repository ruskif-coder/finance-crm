/**
 * Демо-стенд DSP — отработка цепочки креатива на ДЕМО-клиенте DSP.
 *
 * Зачем: коннектор собран, но живьём не проверен, а проверять его впервые на боевой РК
 * значит платить за ошибку деньгами.
 *
 * Отдельного демо-клиента у нас НЕТ (09.09.2026), поэтому экран ходит в БОЕВОЙ кабинет и
 * говорит об этом красной плашкой. Тренировочные кампании отличает приставка в названии,
 * статус STOPPED и запрет трогать заведённые не отсюда. Каждый вызов уходит в журнал с
 * пометкой контура `demo` — при любых ключах.
 *
 * Шаги отдельные и НЕ автоматические: смысл стенда в том, чтобы видеть ответ каждого
 * шага. Обёртка (шаг 3) вообще не ходит в сеть — её видно до отправки.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { MONO, UI, Modal, card, inp, btn, primaryBtn, th, td } from '@/components/salesTableKit'
import api, { auth } from '@/lib/http'
// Предпросмотр — ТОТ ЖЕ компонент, что на карточке сделки и в очереди трафика.
// Вторая реализация означала бы, что проверяющий и трафик смотрят на баннер
// по-разному, а спор «у меня всё ровно» разрешить было бы нечем.
import { CreativePreview } from '@/components/creatives/AssemblyCreatives'

const SECTION = { ...card, padding: '16px 20px', marginBottom: 14 }
const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const CODE = { fontFamily: MONO, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 12px', maxHeight: 240, overflow: 'auto' }
const HASH = { fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--income-fg)' }

const ts = (v) => (v ? new Date(v).toLocaleString('ru-RU') : '—')

/** Поле формы. На уровне модуля: компонент внутри компонента теряет фокус на каждом
 *  символе, и это ловит гейт check-inline. */
function F({ label, value, onChange, placeholder, width, type = 'text' }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ ...LBL, marginBottom: 4 }}>{label}</div>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
             placeholder={placeholder}
             style={{ ...inp, width: width || '100%', fontFamily: MONO, fontSize: 12 }} />
    </div>
  )
}

/** «Важная информация» — правила стенда для тех, кто открыл его впервые.
 *
 *  Экраном пользуется не только владелец, а половина правил здесь неочевидна и стоит
 *  денег: вызовы уходят в БОЕВОЙ кабинет. Поэтому текст лежит на самом экране, а не в
 *  документе, который надо знать где искать.
 *
 *  Объявлена на уровне модуля — компонент внутри компонента пересоздаётся на каждый
 *  рендер (гейт check-inline).
 */
function ImportantInfo({ live, prefix, onClose }) {
  const P = { fontSize: 13.5, lineHeight: 1.65, margin: '0 0 12px' }
  const H = { fontSize: 13.5, fontWeight: 700, margin: '18px 0 6px', color: 'var(--text-primary)' }
  return (
    <Modal title="Важная информация о стенде" width={720} onClose={onClose}
           summary={live
             ? 'Отдельного демо-клиента у нас нет. Всё, что вы здесь делаете, уходит в боевой кабинет DSP.'
             : 'Работает демо-клиент: вызовы уходят в его кабинет, боевые кампании не затрагиваются.'}
           footer={<button onClick={onClose} style={primaryBtn}>Понятно</button>}>
      {live && (
        <p style={{ ...P, color: 'var(--danger)', fontWeight: 600 }}>
          Кампании и креативы создаются настоящие. Не «как будто» — их видно в кабинете,
          и убрать их оттуда после тренировки нужно руками.
        </p>
      )}

      <div style={H}>Что вас защищает</div>
      <p style={P}>
        <b>Приставка «{prefix || 'ТЕСТ · '}» в названии.</b> Её ставит сервер, а не человек:
        «допишу сам» забывают на второй раз. По ней тренировочные кампании видно в кабинете
        — и по ней же система пропускает их, когда ищет, не заведена ли РК сделки раньше.
        Без приставки тренировка с тем же названием была бы принята за боевую кампанию, и
        сделка привязалась бы к ней молча и «успешно».
      </p>
      <p style={P}>
        <b>Статус STOPPED у всего, что заводится.</b> Тренировка не крутит и денег не тратит.
      </p>
      <p style={P}>
        <b>Замок на чужое.</b> Остановить, заархивировать или изменить план можно только у
        кампаний, заведённых с этого экрана — принадлежность сверяется по журналу. Чужой
        хеш, вставленный из буфера, получит отказ, а не остановленную кампанию. Если журнал
        недоступен, экран тоже откажет: без него проверить нечем.
      </p>
      <p style={P}>
        <b>Журнал.</b> Каждый вызов пишется с пометкой «demo» — при любых ключах. Благодаря
        этому боевое заведение РК никогда не примет тренировочные вызовы за свои. Токен в
        журнал не попадает.
      </p>

      <div style={H}>Про ключи</div>
      <p style={P}>
        Сначала берутся ключи демо-клиента, и только если их нет — боевые. Появятся
        демо-ключи в <code style={{ fontFamily: MONO }}>.env</code> — экран переключится
        сам, ничего править не нужно.
      </p>

      <div style={H}>Что нужно помнить перед отправкой</div>
      <p style={P}>
        Лимит <code style={{ fontFamily: MONO }}>total</code> — это объём за ВЕСЬ срок, а не
        остаток. Если прислать остаток, DSP засчитает уже открученное и остановит кампанию
        раньше срока. Поэтому в шаге с планом вводится остаток, а полный объём считает
        сервер — и показывает его до отправки.
      </p>
      <p style={{ ...P, marginBottom: 4 }}>
        Обёртку креатива видно ДО отправки, сети она не касается. Прочитайте её глазами:
        в ней должны быть наш счётчик, скрипт видимости, ЕРИД и целые макросы.
      </p>
    </Modal>
  )
}

/** Шаг цепочки: заголовок, тело, результат. */
function Step({ n, title, note, children, result, error, blocked }) {
  return (
    <div style={SECTION}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
        <span style={{ ...HASH, color: 'var(--accent)' }}>{n}</span>
        <span style={{ fontSize: 15, fontWeight: 700 }}>{title}</span>
      </div>
      {!!note && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>{note}</div>}
      {/* Почему кнопка не нажимается — сказано словами. Отключённая кнопка молчит, и
          человек считает, что сломался экран, а не что не пройден предыдущий шаг. */}
      {!!blocked && (
        <div style={{ fontSize: 12.5, color: 'var(--warning-text)', marginBottom: 10 }}>{blocked}</div>
      )}
      {children}
      {!!error && (
        <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 10,
          border: '1px solid var(--danger)', background: 'var(--danger-tint)',
          color: 'var(--danger)', fontSize: 12.5, lineHeight: 1.5 }}>{error}</div>
      )}
      {!!result && <div style={{ marginTop: 12 }}>{result}</div>}
    </div>
  )
}

export default function DspDemo() {
  const [state, setState] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')

  // Шаг 1 — кампания
  const [camp, setCamp] = useState({ title: 'стенд · ' + new Date().toISOString().slice(0, 7), date_start: '', date_end: '', total_shows: '', total_budget: '' })
  const [campOut, setCampOut] = useState(null)
  // Шаг 2 — архив
  const fileRef = useRef(null)
  const [upOut, setUpOut] = useState(null)
  // Шаг 3 — обёртка
  const [erid, setErid] = useState('')
  // Какой наш счётчик вшить — зависит от площадки: стоит ли на её сайте наш код.
  // null = не вшивать вовсе (проверка одной обёртки).
  const [ourCode, setOurCode] = useState(null)
  const [wrapOut, setWrapOut] = useState(null)
  // Шаг 4 — креатив
  const [crv, setCrv] = useState({ title: 'DEMO-cr1', link: 'https://example.ru', self_inn: '', self_name: '', adomain: '', total_shows: '' })
  const [crvOut, setCrvOut] = useState(null)
  // Шаг 5 — таргетинг
  const [srcKey, setSrcKey] = useState('')
  const [bid, setBid] = useState('50')
  const [tgtOut, setTgtOut] = useState(null)
  // Шаг 6 — управление кампанией. Остаток, а не полный объём: человек думает «сколько
  // ещё открутить до конца», а полный total считает сервер (ловушка DSP).
  const [plan, setPlan] = useState({ delivered_show: '', remaining_show: '', date_end: '' })
  const [planOut, setPlanOut] = useState(null)
  const [info, setInfo] = useState(null)
  // Предпросмотр: {html, sandbox_url}. Через песочницу, а не srcdoc — баннер после
  // загрузчика ссылается на чужой CDN, и наш CSP на своём домене его не покажет.
  const [preview, setPreview] = useState(null)
  const [showInfo, setShowInfo] = useState(false)
  const [stepErr, setStepErr] = useState({})   // отказ рядом с кнопкой, которую нажали

  // Зависимостей нет намеренно: `srcKey` в них давал бы `load` новую идентичность после
  // первой же загрузки, а `useEffect([load])` — второй запрос состояния при каждом
  // открытии страницы. Начальное значение ставится функциональным сеттером, который сам
  // видит предыдущее и не затирает выбранное человеком.
  const load = useCallback(async () => {
    try {
      const r = await api.get('/dsp-demo/state', auth())
      setState(r.data)
      setSrcKey(prev => prev || r.data?.source_keys?.web || '')
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось прочитать состояние стенда') }
  }, [])

  useEffect(() => { load() }, [load])

  // Ошибка запоминает, НА КАКОМ шаге случилась: полоса ошибки живёт в шапке, а шаги
  // уходят на два экрана вниз — 09.09.2026 отказ шага 4 выглядел как «кнопка молчит».
  const run = async (key, fn) => {
    setBusy(key); setErr(''); setStepErr(s => ({ ...s, [key]: '' }))
    try { await fn() } catch (e) {
      const msg = e.response?.data?.detail || `Шаг «${key}» не прошёл`
      setErr(msg); setStepErr(s => ({ ...s, [key]: msg }))
    } finally { setBusy(''); load() }
  }

  /* Право на ЗАПИСЬ. Сервер его проверяет на каждой пишущей ручке (`dsp_demo:edit`), а
     экран не проверял вовсе: кнопки были видны всем, у кого есть просмотр, и отвечали
     403 при нажатии (F5-19 аудита 11.09.2026). Кнопка, которая гарантированно не
     сработает, — это не «защита на сервере», а ловушка времени.

     Читаем после монтирования: снимок прав живёт в localStorage, на сервере его нет. */
  // Начальное значение `null` — «ещё не знаю», а не «прав нет». `false` с первого кадра
  // означал, что админ на КАЖДОЙ загрузке видел вспышку плашки «Только просмотр»: SSR и
  // первый клиентский кадр рисуют её, а снимок прав приходит только после монтирования.
  // Третье состояние сделано так же, как в lib/pageGuard.js, — там оно есть с рождения.
  const [mayEdit, setMayEdit] = useState(null)
  useEffect(() => { setMayEdit(can(getPermissions(), 'dsp_demo', 'edit')) }, [])

  const doCampaign = () => run('campaign', async () => {
    const r = await api.post('/dsp-demo/campaign', {
      title: camp.title, date_start: camp.date_start, date_end: camp.date_end,
      total_shows: camp.total_shows ? Number(camp.total_shows) : null,
      total_budget: camp.total_budget ? Number(camp.total_budget) : null,
    }, auth())
    setCampOut(r.data)
  })

  const doUpload = () => run('upload', async () => {
    const f = fileRef.current?.files?.[0]
    if (!f) throw { response: { data: { detail: 'Выберите zip-архив баннера' } } }
    const fd = new FormData()
    fd.append('file', f)
    const r = await api.post('/dsp-demo/upload', fd,
      { ...auth(), headers: { ...(auth().headers || {}), 'Content-Type': 'multipart/form-data' } })
    setUpOut(r.data)
    setWrapOut(null)
  })

  const doWrap = () => run('wrap', async () => {
    const r = await api.post('/dsp-demo/wrap',
      { html: upOut?.html || '', erid: erid || null, our_code: ourCode }, auth())
    setWrapOut(r.data)
  })

  const doCreative = () => run('creative', async () => {
    const r = await api.post('/dsp-demo/creative', {
      campaign_xxhash: campOut?.xxhash, title: crv.title, link: crv.link,
      html_code: wrapOut?.html || upOut?.html || '', erid: erid || null,
      // Размер — тот, что объявил САМ баннер и подтвердил загрузчик на шаге 2.
      // Своего мнения о нём у экрана нет и быть не должно.
      size: upOut?.size || null,
      self_inn: crv.self_inn || null, self_name: crv.self_name || null,
      adomain: crv.adomain || null,
      total_shows: crv.total_shows ? Number(crv.total_shows) : null,
    }, auth())
    setCrvOut(r.data)
  })

  const doTargeting = () => run('targeting', async () => {
    const r = await api.post('/dsp-demo/targeting', {
      xxhash: crvOut?.xxhash || campOut?.xxhash,
      target_key: 'source',
      items: { [srcKey]: { is_checked: true, bid_start: Number(bid) || 0, name: srcKey } },
    }, auth())
    setTgtOut(r.data)
  })

  const xx = crvOut?.campaign_xxhash || campOut?.xxhash || ''

  const doInfo = () => run('info', async () => {
    const r = await api.get(`/dsp-demo/campaign/${xx}`, auth())
    setInfo(r.data.info)
  })

  const doStatus = (action) => run(action, async () => {
    const r = await api.post(`/dsp-demo/campaign/${xx}/status`, { action }, auth())
    setInfo(null)
    setPlanOut({ status: r.data.status })
  })

  const doPlan = (dry) => run(dry ? 'plan-dry' : 'plan', async () => {
    const r = await api.post(`/dsp-demo/campaign/${xx}/plan`, {
      delivered_show: Number(plan.delivered_show) || 0,
      remaining_show: plan.remaining_show === '' ? null : Number(plan.remaining_show),
      date_end: plan.date_end || null,
      dry_run: dry,
    }, auth())
    setPlanOut(r.data)
  })

  const ready = state?.configured
  // Ключей демо-клиента нет — экран ходит в БОЕВОЙ кабинет. Это первое, что должно быть
  // видно на странице: дальше каждая кнопка создаёт или меняет настоящие объекты.
  const live = state?.cabinet === 'prod'
  const log = state?.log || []

  return (
    <>
      <Head><title>DSP демо</title></Head>
      <Navbar active="traffic" />
      {/* В контуре Трафиков нет сквозного ряда вкладок (владелец 06.09.2026): в раздел
          заходят верхним меню. Ряд `SectionTabs` — канон СПРАВОЧНИКОВ, и переносить его
          сюда было ошибкой. Ширина 1200: экран читают сверху вниз шаг за шагом, и длинная строка тут мешает. */}
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '20px 26px 60px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>

        {!!err && (
          <div style={{ ...SECTION, borderColor: 'var(--danger)', color: 'var(--danger)' }}>{err}</div>
        )}

        {/* Состояние контура: без него любой шаг ответит отказом, и лучше сказать это
            сразу, чем на первой кнопке. */}
        <div style={{ ...SECTION, display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={LBL}>Контур</div>
            <div style={{ ...HASH, color: !ready ? 'var(--warning-text)' : (live ? 'var(--danger)' : 'var(--income-fg)') }}>
              {!ready ? 'не настроен' : (live ? 'БОЕВОЙ КАБИНЕТ' : 'ДЕМО · настроен')}
            </div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <div>
            <div style={LBL}>Партнёр</div>
            <div style={{ fontFamily: MONO, fontSize: 13 }}>{state?.partner || '—'}</div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <div>
            <div style={LBL}>Адрес API</div>
            <div style={{ fontFamily: MONO, fontSize: 12 }}>{state?.url || '—'}</div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <div>
            <div style={LBL}>Ключи источников</div>
            <div style={{ fontFamily: MONO, fontSize: 12 }}>
              web {state?.source_keys?.web || '—'} · app {state?.source_keys?.app || '—'}
            </div>
          </div>
          {/* Экраном пользуется не только владелец: правила должны открываться отсюда,
              а не находиться в документе, о котором надо знать. */}
          <button onClick={() => setShowInfo(true)}
                  style={{ ...btn(false), marginLeft: 'auto',
                           borderColor: live ? 'var(--danger)' : 'var(--border-card)',
                           color: live ? 'var(--danger)' : 'var(--text-secondary)' }}>
            Важная информация
          </button>
        </div>

        {/* Говорим вслух, а не просто гасим кнопки: серая кнопка без объяснения читается
            как «сломалось», и человек идёт выяснять, что случилось. */}
        {mayEdit === false && (
          <div style={{ ...SECTION, borderColor: 'var(--warning)', background: 'var(--warning-tint)' }}>
            <div style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--warning-text)' }}>
              <b>Только просмотр.</b> Права на запись в этом разделе у вас нет, поэтому
              шаги, которые что-то создают в кабинете DSP, отключены. Разбирать ответы и
              смотреть журнал можно.
            </div>
          </div>
        )}

        {live && (
          <div style={{ ...SECTION, borderColor: 'var(--danger)', background: 'var(--danger-tint)' }}>
            <div style={{ ...LBL, marginBottom: 8, color: 'var(--danger)' }}>
              Отдельного демо-клиента нет — всё уходит в боевой кабинет
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>
              Кампании создаются <b>настоящие</b>: в статусе STOPPED, с приставкой{' '}
              <code style={{ fontFamily: MONO }}>{state?.title_prefix}</code> в названии —
              по ней их видно в кабинете и по ней же боевое заведение РК их пропускает.
              После тренировки уберите их в кабинете руками.
              Трогать можно только те кампании, что заведены с этого экрана.
            </div>
            <button onClick={() => setShowInfo(true)}
                    style={{ ...btn(false), marginTop: 10, borderColor: 'var(--danger)', color: 'var(--danger)' }}>
              Читать целиком
            </button>
          </div>
        )}

        {!ready && (
          <div style={{ ...SECTION, background: 'var(--bg-subtle)' }}>
            <div style={{ ...LBL, marginBottom: 8 }}>Стенд ещё не включён</div>
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>
              Нет ни боевых ключей (<code style={{ fontFamily: MONO }}>DSP_ACCESS_TOKEN</code>,{' '}
              <code style={{ fontFamily: MONO }}>DSP_PARTNER_XXHASH</code>), ни демо-ключей
              (<code style={{ fontFamily: MONO }}>{state?.env?.token}</code>,{' '}
              <code style={{ fontFamily: MONO }}>{state?.env?.partner}</code>).
              Демо-ключи, если они появятся, имеют приоритет. Значения кладёт владелец
              в <code style={{ fontFamily: MONO }}>.env</code> — из переписки они не переносятся.
            </div>
          </div>
        )}

        <Step n="1" title="Мастер-кампания" error={stepErr.campaign}
              blocked={!ready ? 'Ключей DSP нет — заводить кампанию нечем.' : ''}
              note="Заводится СТОЯЩЕЙ (STOPPED) и с явным uniform_pro: умолчание у API — accelerated, а не то, что стоит в кабинете. Лимит total — за весь срок, не остаток."
              result={campOut && (
                <>
                  <div style={LBL}>xxhash кампании</div>
                  <div style={HASH}>{campOut.xxhash}</div>
                  <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(campOut.request, null, 2)}</div>
                </>
              )}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, alignItems: 'end' }}>
            <F label="Название" value={camp.title} onChange={v => setCamp(c => ({ ...c, title: v }))} />
            <F label="Начало" type="date" value={camp.date_start} onChange={v => setCamp(c => ({ ...c, date_start: v }))} />
            <F label="Конец" type="date" value={camp.date_end} onChange={v => setCamp(c => ({ ...c, date_end: v }))} />
            <F label="Показов, total" value={camp.total_shows} onChange={v => setCamp(c => ({ ...c, total_shows: v }))} placeholder="100000" />
            <F label="Бюджет, total" value={camp.total_budget} onChange={v => setCamp(c => ({ ...c, total_budget: v }))} placeholder="1000" />
          </div>
          <button onClick={doCampaign} disabled={!mayEdit || !ready || !!busy} style={{ ...primaryBtn, marginTop: 12 }}>
            {busy === 'campaign' ? 'Завожу…' : 'Завести кампанию'}
          </button>
        </Step>

        <Step n="2" title="Архив баннера" error={stepErr.upload}
              blocked={!ready ? 'Ключей DSP нет.' : ''}
              note="Upload.getUploadFileUrl(type=zip) → multipart-POST архива на выданный URL. В index.html баннера ОБЯЗАН быть тег ad.size с размером — без него DSP архив не принимает, и мы говорим об этом до отправки. В ответ приходит разметка с проставленным загрузчиком base href на его CDN. Единственный вызов мимо JSON-RPC, в журнале отдельной строкой."
              result={upOut && (
                <>
                  <div style={LBL}>Размер, как его понял загрузчик</div>
                  <div style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                    {upOut.size || '— не сообщён'}
                  </div>
                  <div style={LBL}>Макросы в ответе загрузчика</div>
                  <div style={{ fontFamily: MONO, fontSize: 12, marginBottom: 8 }}>
                    {upOut.macros?.length ? upOut.macros.join(' ') : '— ни одного, это подозрительно'}
                  </div>
                  <div style={CODE}>{upOut.html}</div>
                </>
              )}>
          <input ref={fileRef} type="file" accept=".zip,application/zip" style={{ fontSize: 13 }} />
          <button onClick={doUpload} disabled={!mayEdit || !ready || !!busy} style={{ ...primaryBtn, marginLeft: 10 }}>
            {busy === 'upload' ? 'Загружаю…' : 'Загрузить архив'}
          </button>
        </Step>

        <Step n="3" title="Обёртка" error={stepErr.wrap}
              blocked={!upOut ? 'Сначала шаг 2: оборачивать нечего, пока загрузчик не вернул разметку.' : ''}
              note="Вшивает НАШ СЧЁТЧИК (свой для площадок с нашим кодом и без него), viewability-скрипт и метку ЕРИД — внутрь head креатива. Сети не касается: результат видно до отправки. Макросы DSP раскрывает сам, у себя мы их не трогаем."
              result={wrapOut && (
                <>
                  <div style={{ fontFamily: MONO, fontSize: 12, marginBottom: 8 }}>
                    viewability: {wrapOut.viewability ? 'есть' : 'НЕТ'} · макросы: {wrapOut.macros?.join(' ') || '—'}
                  </div>
                  {/* Молчать об этом нельзя: креатив уедет без счётчика, и выяснится это
                      только по отсутствию данных. */}
                  {wrapOut.script_missing && (
                    <div style={{ fontSize: 12, color: 'var(--warning-text)', marginBottom: 8 }}>
                      Для этой колонки скрипт не задан — креатив уйдёт без счётчика.
                      Задаётся в Админке → «Скрипт».
                    </div>
                  )}
                  {wrapOut.viewability_missing && (
                    <div style={{ fontSize: 12, color: 'var(--warning-text)', marginBottom: 8 }}>
                      Адрес скрипта видимости не задан — креатив уйдёт без него.
                      Задаётся там же, в Админке → «Скрипт».
                    </div>
                  )}
                  <div style={CODE}>{wrapOut.html}</div>
                </>
              )}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="ЕРИД" value={erid} onChange={setErid} placeholder="необязателен на демо" width={240} />
            <div>
              <div style={{ ...LBL, marginBottom: 4 }}>Площадка</div>
              <select value={ourCode === null ? '' : String(ourCode)}
                      onChange={e => setOurCode(e.target.value === '' ? null : e.target.value === 'true')}
                      style={{ ...inp, width: 260, fontSize: 12.5 }}>
                <option value="">без нашего счётчика</option>
                <option value="true">наш код на сайте стоит</option>
                <option value="false">нашего кода на сайте нет</option>
              </select>
            </div>
            <button onClick={doWrap} disabled={!upOut || !!busy} style={btn(false)}>
              {busy === 'wrap' ? 'Оборачиваю…' : 'Обернуть'}
            </button>
            {/* Смотрим ИМЕННО обёрнутую разметку — ту, что уедет в DSP, а не исходную:
                счётчик и viewability могут её сломать, и увидеть это надо здесь. */}
            <button onClick={() => setPreview(wrapOut || upOut)}
                    disabled={!wrapOut && !upOut} style={btn(false)}>
              Предпросмотр
            </button>
          </div>
        </Step>

        <Step n="4" title="Креатив в кампании" error={stepErr.creative}
              blocked={!campOut ? 'Сначала шаг 1: креатив заводится ВНУТРИ кампании.'
                       : (!wrapOut && !upOut) ? 'Сначала шаг 2: нет разметки, которую класть в креатив.' : ''}
              note="Creative.add возвращает xxhash, затем Creative.edit кладёт разметку. Это и есть связка площадка×креатив: у нас ей соответствует строка ad_campaign_creative со своим ms_creative_xxhash. description не трогаем — ломается."
              result={crvOut && (
                <>
                  <div style={LBL}>xxhash креатива</div>
                  <div style={HASH}>{crvOut.xxhash}</div>
                  {/* Два вызова, и разметка уходит ВТОРЫМ. Без этой строки экран
                      показывал тело add — где html-кода нет по определению. */}
                  <div style={{ fontSize: 12.5, marginTop: 8 }}>
                    Разметка отправлена вторым вызовом{' '}
                    <code style={{ fontFamily: MONO }}>{crvOut.edit?.method}</code> в поле{' '}
                    <code style={{ fontFamily: MONO }}>{crvOut.edit?.field}</code>:{' '}
                    <b>{crvOut.html_bytes} байт</b>, ответ{' '}
                    <code style={{ fontFamily: MONO }}>{JSON.stringify(crvOut.edit?.result)}</code>
                  </div>
                  <div style={{ ...LBL, marginTop: 10 }}>Тело Creative.add</div>
                  <div style={{ ...CODE, marginTop: 4 }}>{JSON.stringify(crvOut.request, null, 2)}</div>
                </>
              )}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            <F label="Имя креатива" value={crv.title} onChange={v => setCrv(c => ({ ...c, title: v }))} />
            <F label="Посадочная ссылка" value={crv.link} onChange={v => setCrv(c => ({ ...c, link: v }))} />
            <F label="Показов, total" value={crv.total_shows} onChange={v => setCrv(c => ({ ...c, total_shows: v }))} placeholder="без дня и часа" />
            <F label="ИНН рекламодателя" value={crv.self_inn} onChange={v => setCrv(c => ({ ...c, self_inn: v }))} />
            <F label="Название рекламодателя" value={crv.self_name} onChange={v => setCrv(c => ({ ...c, self_name: v }))} />
            <F label="adomain" value={crv.adomain} onChange={v => setCrv(c => ({ ...c, adomain: v }))} placeholder="https://example.ru/" />
            <div>
              <div style={{ ...LBL, marginBottom: 4 }}>Размер (из шага 2)</div>
              <div style={{ ...inp, fontFamily: MONO, fontSize: 12,
                background: 'var(--bg-subtle)', color: upOut?.size ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                {upOut?.size || 'будет после загрузки архива'}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
            <button onClick={doCreative} disabled={!mayEdit || !campOut || (!wrapOut && !upOut) || !!busy}
                    style={primaryBtn}>
              {busy === 'creative' ? 'Завожу…' : 'Завести креатив'}
            </button>
            <button onClick={() => setPreview(wrapOut || upOut)}
                    disabled={!wrapOut && !upOut} style={btn(false)}>
              Предпросмотр
            </button>
          </div>
        </Step>

        <Step n="5" title="Таргетинг на источник" error={stepErr.targeting}
              blocked={!campOut && !crvOut ? 'Сначала шаги 1 и 4.' : ''}
              note="У источника в DSP есть только включённость и ставка — лимита нет. Поэтому суточный лимит на площадку у нас ОРИЕНТИР по определению, а рычаги — ставка и вкл/выкл."
              result={tgtOut && <div style={CODE}>{JSON.stringify(tgtOut.result, null, 2)}</div>}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end' }}>
            <F label="Ключ источника" value={srcKey} onChange={setSrcKey} width={220} />
            <F label="Ставка" value={bid} onChange={setBid} width={120} />
            <button onClick={doTargeting} disabled={!mayEdit || (!crvOut && !campOut) || !!busy} style={btn(false)}>
              {busy === 'targeting' ? 'Ставлю…' : 'Поставить таргетинг'}
            </button>
          </div>
        </Step>

        <Step n="6" title="Управление кампанией"
              note="У DSP нет отдельной паузы: выдачу останавливает один статус STOPPED. «Стоп» отличается тем, что убирает кампанию из работы совсем (ARCHIVE) — обратно это уже не включается."
              result={(planOut || info) && (
                <>
                  {!!planOut?.explain?.show && (
                    <div style={{ fontFamily: MONO, fontSize: 12.5, marginBottom: 8 }}>
                      откручено {planOut.explain.show.delivered} + остаток {planOut.explain.show.remaining}
                      {' = '}<b>total {planOut.explain.show.total}</b>
                      {planOut.sent === false && ' · не отправлено'}
                    </div>
                  )}
                  {!!planOut?.status && (
                    <div style={{ ...HASH, marginBottom: 8 }}>статус → {planOut.status}</div>
                  )}
                  {!!planOut?.request && <div style={CODE}>{JSON.stringify(planOut.request, null, 2)}</div>}
                  {!!info && <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(info, null, 2)}</div>}
                </>
              )}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            <button onClick={() => doStatus('start')} disabled={!mayEdit || !xx || !!busy} style={primaryBtn}>
              {busy === 'start' ? '…' : 'Запустить'}
            </button>
            <button onClick={() => doStatus('pause')} disabled={!mayEdit || !xx || !!busy} style={btn(false)}>
              {busy === 'pause' ? '…' : 'Пауза'}
            </button>
            <button onClick={() => doStatus('stop')} disabled={!mayEdit || !xx || !!busy} style={btn(false)}>
              {busy === 'stop' ? '…' : 'Стоп (в архив)'}
            </button>
            <button onClick={doInfo} disabled={!xx || !!busy} style={{ ...btn(false), marginLeft: 'auto' }}>
              {busy === 'info' ? '…' : 'Что сейчас в DSP'}
            </button>
          </div>

          {/* Ловушка DSP: total — за весь срок, а не остаток. Человек вводит остаток,
              полный total считает сервер, и обе величины показаны до отправки. */}
          <div style={{ ...LBL, marginBottom: 6 }}>План до конца кампании</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>
            Суточный темп DSP считает сам: (total − открутили) ÷ оставшиеся дни.
            Значит сутки меняются изменением ОСТАТКА. В API при этом уходит полный новый
            total за весь срок — прислать остаток напрямую значит остановить кампанию раньше.
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="Уже откручено, показов" value={plan.delivered_show}
               onChange={v => setPlan(p => ({ ...p, delivered_show: v }))} width={200} />
            <F label="Осталось открутить" value={plan.remaining_show}
               onChange={v => setPlan(p => ({ ...p, remaining_show: v }))} width={200} />
            <F label="Новая дата конца" type="date" value={plan.date_end}
               onChange={v => setPlan(p => ({ ...p, date_end: v }))} width={170} />
            <button onClick={() => doPlan(true)} disabled={!mayEdit || !xx || !!busy} style={btn(false)}>
              {busy === 'plan-dry' ? '…' : 'Посчитать'}
            </button>
            <button onClick={() => doPlan(false)} disabled={!mayEdit || !xx || !!busy} style={primaryBtn}>
              {busy === 'plan' ? 'Отправляю…' : 'Отправить план'}
            </button>
          </div>
        </Step>

        {/* Журнал — единственное место, где видно, что именно ответил DSP. */}
        <div style={SECTION}>
          <div style={{ ...LBL, marginBottom: 10 }}>Журнал обмена · только демо-контур</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>
                <th style={th}>Время</th><th style={th}>Метод</th><th style={th}>Объект</th>
                <th style={th}>Наш id</th><th style={th}>xxhash</th><th style={th}>Итог</th>
              </tr></thead>
              <tbody>
                {log.map((r, i) => (
                  <tr key={i}>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 11 }}>{ts(r.ts)}</td>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{r.method || '—'}</td>
                    <td style={td}>{r.entity_type || '—'}</td>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 11 }}>{r.local_ref || '—'}</td>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 11 }}>{r.ms_xxhash || '—'}</td>
                    <td style={{ ...td, color: r.ok ? 'var(--income-fg)' : 'var(--danger)' }}>
                      {r.ok ? 'ок' : (r.error || 'ошибка')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!log.length && (
              <div style={{ padding: '16px 0', fontSize: 13, color: 'var(--text-secondary)' }}>
                Обмена ещё не было.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Тот же компонент, что в очереди трафика: сетка типовых пропорций и изолированная
          рамка без allow-same-origin — чужой код не дотянется до нашей сессии. */}
      {!!preview && (
        <CreativePreview htmlSource={preview.html} sandboxUrl={preview.sandbox_url}
                         title="Предпросмотр креатива для DSP"
                         onClose={() => setPreview(null)} />
      )}

      {showInfo && (
        <ImportantInfo live={live} prefix={state?.title_prefix}
                       onClose={() => setShowInfo(false)} />
      )}
    </>
  )
}
