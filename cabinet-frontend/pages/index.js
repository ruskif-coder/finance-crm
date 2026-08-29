/**
 * Кабинет паблишера. Воспроизведение эталона хендоффа
 * (`docs/кабинет паблишера.zip` → «Кабинет паблишера.dc.html»).
 *
 * Одна страница на два состояния (вход / кабинет), а не две с редиректом: редирект по
 * наличию токена читает `localStorage`, которого на сервере нет, — страница успевает
 * отрисоваться неавторизованной и мигнуть.
 *
 * **Что здесь живое, а что демо.** Живое: очередь решений, ответы по креативу,
 * предпросмотр, посадочная ссылка, обработанное за неделю, команда, профиль, рабочая
 * группа и медиакит — его площадка загружает сама. Демо (источника в системе нет):
 * кампании и суммы; факт показов заводится на сверке, и до неё у кампании есть только
 * состояние «запущен» (владелец 28.08.2026).
 *
 * Демо помечено на экране и лежит отдельным файлом `lib/demo.js` — смешать выдумку с
 * живыми данными значит однажды показать площадке сумму, которой мы ей не должны.
 *
 * Блока документов НЕТ намеренно: актов и УПД в системе не существует, а блок,
 * показывающий несуществующее, площадка читает как факт.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import Head from 'next/head'
import api, { auth, signOut, TOKEN_KEY } from '../lib/http'
import { PreviewModal } from '../lib/preview'
import { Header, Side, Demo, WRAP } from '../components/Shell'
import { C, CAP, MONO, UI, arrowBtn, btn, btnSm, card, chip, dm, inp, num, periodLabel,
  rub, soft }
  from '../lib/ui'
import { CAMPS, GROUP_PAY, NEED, NOW_MONTH, PAY_STATE, RK_STATE, SERVICE_DOT,
  billBlocked, camp, inBill, inPace, isClosed, sum } from '../lib/demo'

/* ─────────────────────────── вход ─────────────────────────── */

function Login({ onDone }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const r = await api.post('/login', { email: email.trim(), password })
      localStorage.setItem(TOKEN_KEY, r.data.token)
      localStorage.setItem('cabinet_name', r.data.name || '')
      onDone()
    } catch (e2) {
      setErr(e2.response?.data?.detail || 'Не удалось войти')
      setBusy(false)
    }
  }

  return (
    <div style={{ minHeight: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: 18 }}>
      <form onSubmit={submit} className="rise"
        style={{ ...card, padding: '30px 28px', width: 'min(400px, 100%)',
          display: 'flex', flexDirection: 'column', gap: 14 }}>
        <img className="logo-light" src="/assets/logo-mediaplan.svg" alt="SIMB-AD" height="26"
          style={{ alignSelf: 'flex-start' }} />
        <img className="logo-dark" src="/assets/logo-mediaplan-dark.svg" alt="SIMB-AD" height="26"
          style={{ alignSelf: 'flex-start' }} />
        <div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Кабинет площадки</div>
          <div style={{ fontSize: 12.5, color: C.muted, marginTop: 4 }}>
            Согласование креативов и кампании
          </div>
        </div>
        <input style={inp} type="email" autoComplete="username" placeholder="Почта"
          value={email} onChange={e => setEmail(e.target.value)} required />
        <input style={inp} type="password" autoComplete="current-password" placeholder="Пароль"
          value={password} onChange={e => setPassword(e.target.value)} required />
        {!!err && <div style={{ fontSize: 12.5, color: C.danger }}>{err}</div>}
        <button style={btn(true)} disabled={busy} type="submit">
          {busy ? 'Входим…' : 'Войти'}
        </button>
        {/* Честно о том, чего нет: восстановления по почте не будет, и человек должен
            знать, куда идти, а не искать несуществующую ссылку. */}
        <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.5 }}>
          Забыли пароль — напишите вашему менеджеру: восстановление по почте
          в кабинете не предусмотрено.
        </div>
      </form>
    </div>
  )
}

/* ─────────────────────────── очередь ─────────────────────────── */

/* Дни до старта — не украшение: у площадки в работе несколько кампаний, и очерёдность
   разбора она выбирает по тому, что стартует раньше. Считается от даты, переданной
   снаружи: `Date` внутри компонента дал бы расхождение сервера и клиента на границе
   суток и ошибку гидрации. */
const daysTo = (iso, today) => {
  if (!iso) return null
  return Math.round((new Date(iso + 'T00:00:00') - today) / 86400000)
}

function Task({ t, reasons, canApprove, today, onDone, onErr }) {
  const [busy, setBusy] = useState(false)
  const [ask, setAsk] = useState(null)
  const [reason, setReason] = useState('')
  const [url, setUrl] = useState('')
  const [show, setShow] = useState(false)
  const [files, setFiles] = useState([])     // приложения к доработке
  const [drag, setDrag] = useState(false)
  const [upBusy, setUpBusy] = useState(false)

  /* Файлы уходят СРАЗУ, а не вместе с вердиктом: вердикт неизменяем, и приложить к нему
     что-то после отправки уже нельзя. Грузим по очереди — параллельные запросы получили
     бы один порядковый номер в имени. */
  const addFiles = async (list) => {
    const all = Array.from(list || [])
    if (!all.length) return
    setUpBusy(true)
    for (const f of all.slice(0, 5 - files.length)) {
      const form = new FormData()
      form.append('file', f)
      try {
        const r = await api.post(`/tasks/${t.task_id}/rework-file`, form,
          { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
        setFiles(prev => [...prev, r.data])
      } catch (e) {
        onErr(e.response?.data?.detail || 'Не удалось приложить файл')
        break
      }
    }
    setUpBusy(false)
  }
  const preview = (t.files || []).find(f => f.preview_url) || (t.files || [])[0]
  const toStart = daysTo(t.period_from, today)

  /* «Просрочено» — это ПРО СТАРТ, а не про то, сколько задание висит.
     Было наоборот: красный горел после трёх дней ожидания, и кампания со стартом через
     95 дней объявлялась просроченной — чего площадка справедливо не поняла. Ждать
     решения три месяца до старта совершенно нормально; ненормально — не ответить, когда
     размещение уже должно идти.

       старт прошёл          → просрочено (красный)
       до старта ≤ 3 дней    → срочно (жёлтый)
       иначе                 → ждёт решения (нейтральный)

     Сколько именно висит, видно отдельной подписью — это ориентир, а не приговор. */
  const late = toStart !== null && toStart < 0
  const soon = !late && toStart !== null && toStart <= 3
  const [stChipBg, stChipFg, stChipBd] = late
    ? [C.dangerTint, C.danger, C.dangerBorder]
    : soon ? [C.warningTint, C.warningFg, C.warningBorder]
      : [C.subtle, C.secondary, C.border]
  const stLabel = late ? 'просрочено' : soon ? 'срочно' : 'ждёт решения'

  /* Пока висит НАШ запрос посадочной, «Согласовать» заперто (владелец 29.08.2026).
     «Ок» без ссылки означал бы, что вопрос снят молча: пара срастается, уходит код в
     DSP, за ним ЕРИД — а вести рекламу некуда. Отрицательные ответы не запираем: они
     закрывают размещение вместе с вопросом. Правило продублировано в ядре — здесь оно
     объясняет, там держит. */
  const urlPending = t.url_state === 'запрошена'

  /* Порог — по тому, что подсказка поля физически не покажет: перевод строки она
     схлопывает, длину обрезает. 90 знаков — ширина поля на узком экране. */
  const askText = t.url_request_text || ''
  const longAsk = askText.includes('\n') || askText.length > 90

  const answer = async (verdict, why) => {
    setBusy(true)
    try {
      await api.post(`/tasks/${t.task_id}/verdict`, { verdict, reason: why || null }, auth())
      setAsk(null); setReason(''); onDone()
    } catch (e) { onErr(e.response?.data?.detail || 'Не удалось отправить ответ') }
    setBusy(false)
  }

  const sendUrl = async () => {
    setBusy(true)
    try {
      await api.put(`/tasks/${t.task_id}/url`, { url: url.trim() }, auth())
      setUrl(''); onDone()
    } catch (e) { onErr(e.response?.data?.detail || 'Не удалось сохранить ссылку') }
    setBusy(false)
  }

  /* Полоса-акцент слева ТОЛЬКО у сверки (эталон, 2.3): она одна отличается родом —
     это не креатив, а подтверждение месяца. У просроченного меняется фон и тон маркера,
     но не толщина рамки: если полосу получают все «важные», она перестаёт выделять
     что-либо. */
  return (
    <div className="rise" style={{ padding: '12px 14px', borderRadius: 12,
      background: late ? C.dangerBg : soon ? C.warnBg : C.card,
      border: `1px solid ${late ? C.dangerBorder : soon ? C.warningBorder : C.border}`,
      display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* строка 1 — чья кампания, когда старт, в каком она состоянии */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: 2,
          background: late ? C.danger : soon ? C.warning : C.accent }} />
        <span style={{ fontSize: 14.5, fontWeight: 700 }}>
          {[t.advertiser, t.brand].filter(Boolean).join(' · ') || 'Креатив'}
        </span>
        <span style={{ ...CAP, marginBottom: 0 }}>
          {[t.service, t.surface].filter(Boolean).join(' · ')}
        </span>
        <span style={{ flex: 1 }} />
        {/* Плашка старта: дата и сколько до неё осталось. Одна дата без остатка
            заставляет считать в уме, а решение принимают по остатку. */}
        <span style={{ ...chip(stChipBg, stChipFg, stChipBd), fontFamily: MONO, gap: 8 }}>
          <span style={{ color: C.muted }}>старт рк</span>
          <b>{dm(t.period_from)}</b>
          {toStart !== null && (
            <span style={{ borderLeft: `1px solid ${stChipBd}`, paddingLeft: 8 }}>
              {toStart < 0 ? `${-toStart} дн. назад` : toStart === 0 ? 'сегодня' : `через ${toStart} дн.`}
            </span>
          )}
        </span>
        <span style={chip(stChipBg, stChipFg, stChipBd)}>{stLabel}</span>
      </div>

      {/* строка 2 — что за материал и что с ним делать */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, flex: '0 0 30px',
          background: C.subtle, border: `1px solid ${C.border}`, color: C.muted,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" />
          </svg>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 200 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            Креатив №{t.creative_no}{t.creative_title ? ` — ${t.creative_title}` : ''}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint }}>
            {[t.form === 'BannerHtml5' ? 'banner html5' : t.form,
              preview?.size,
              `ждёт ${t.waiting_days} дн.`,
              late ? 'старт уже прошёл · эскалация менеджеру' : null,
             ].filter(Boolean).join(' · ')}
          </span>
        </span>
        <span style={{ flex: 1 }} />
        {t.url_state === 'есть' && (
          <a href={t.advertiser_url} target="_blank" rel="noreferrer"
            style={{ ...btnSm(false), textDecoration: 'none', display: 'inline-flex',
              alignItems: 'center', gap: 6 }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <path d="M15 3h6v6M10 14L21 3" />
            </svg>
            посадочная
          </a>
        )}
        <button style={btnSm(false)} disabled={!preview?.preview_url}
          onClick={() => setShow(true)}>предпросмотр</button>
        {/* Три исхода, слева направо от мягкого к необратимому. Смысл несёт текст, а
            заливка — только у главного действия: несколько цветных плашек подряд
            превращают строку в светофор. */}
        {canApprove && !ask && (
          <>
            <button style={soft(C.warningFg, C.warningBorder)} disabled={busy}
              onClick={() => setAsk('на доработку')}>Доработать</button>
            <button style={soft(C.danger, C.dangerBorder)}
              disabled={busy} onClick={() => setAsk('отказ')}
              title="Размещение не берём — новая версия баннера этого не изменит">
              Отказать
            </button>
            {/* Единственная залитая кнопка карточки — глубокий `--income-fg`, а не яркий
                `--income`: рядом с контурными соседями насыщенный тон читается кричащим,
                приглушённый — весомым. */}
            <button style={{ ...btnSm(true),
              background: urlPending ? C.subtle : C.incomeFg,
              color: urlPending ? C.faint : '#FFFFFF',
              border: `1px solid ${urlPending ? C.border : 'transparent'}`,
              cursor: urlPending ? 'not-allowed' : 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 13px' }}
              disabled={busy || urlPending}
              title={urlPending
                ? 'Сначала пришлите посадочную страницу — её у нас ещё нет'
                : undefined}
              onClick={() => answer('ок')}>
              <span style={{ fontSize: 12 }}>✓</span> Согласовать
            </button>
          </>
        )}
        {!canApprove && (
          <span style={{ fontSize: 11.5, color: C.faint }}>
            у вас доступ только на просмотр
          </span>
        )}
      </div>

      {show && (
        <PreviewModal file={preview} onClose={() => setShow(false)}
          title={[t.brand, t.creative_title].filter(Boolean).join(' · ')} />
      )}

      {/* Запрос посадочной — только когда её действительно просили: поле, висящее
          всегда, читается как обязательное. */}
      {t.url_state === 'запрошена' && (
        <div style={{ background: C.accentTint, border: `1px solid ${C.accentBorder}`,
          borderRadius: 12, padding: '7px 12px', display: 'flex',
          alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Причина запертой кнопки стоит ВТОРОЙ СТРОКОЙ ПОДПИСИ, а не отдельным рядом:
              высоту блока задаёт поле ввода, и две мелкие строки слева в неё умещаются
              бесплатно — тогда как собственный ряд добавил бы блоку ещё этаж. */}
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
            flex: '0 0 auto', color: C.accent }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.2" strokeLinecap="round">
              <path d="M4 6h16M4 12h10M4 18h6" />
            </svg>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ ...CAP, marginBottom: 0, color: C.accent }}>
                запрос на сбор посадочной
              </span>
              <span style={{ fontSize: 10, color: C.muted }}>
                без неё согласовать нельзя
              </span>
            </span>
          </span>
          {/* Короткий запрос стоит ПОДСКАЗКОЙ поля: он и есть указание, что вписать, и
              рядом с пустым полем читается как задание — своей строки не стоит.
              Длинный и многострочный так показать нельзя: подсказка однострочного поля
              схлопывает переводы строк и обрезается по ширине, а окно запроса у нас
              как раз склеивает пины переводом строки. Такой текст получает свою строку —
              высоту платит редкий случай, а не каждый. */}
          {longAsk && (
            <span style={{ flex: '1 0 100%', fontSize: 12, color: C.secondary,
              whiteSpace: 'pre-line', lineHeight: 1.45 }}>{t.url_request_text}</span>
          )}
          <input style={{ ...inp, flex: 1, minWidth: 260, background: C.card,
            padding: '6px 11px', fontFamily: MONO, fontSize: 12 }}
            title={t.url_request_text || undefined}
            placeholder={longAsk ? 'https://…' : (t.url_request_text
              || 'пришлите ссылку на посадочную — UTM подставим сами')}
            value={url} onChange={e => setUrl(e.target.value)} />
          <button style={{ ...btn(true), padding: '6px 14px' }}
            disabled={busy || !url.trim()} onClick={sendUrl}>Собрать</button>
        </div>
      )}

      {/* Технические требования площадки — её собственные, и на них она же и смотрит.
          Место под примечание в эталоне занимает «Причина отказа» / «ТТ» / «Вывод»;
          у нас пока есть только ТТ. */}
      {!!t.tech_requirements && (
        <div style={{ display: 'flex', gap: 14, alignItems: 'baseline',
          paddingTop: 9, borderTop: `1px solid ${C.row}` }}>
          <span style={{ ...CAP, marginBottom: 0, flex: '0 0 74px' }}>тт</span>
          <span style={{ fontSize: 12.5, color: C.secondary, textWrap: 'pretty' }}>
            {t.tech_requirements}
          </span>
        </div>
      )}

      {/* Форма ответа: слева текст, справа приложения. Восемь к двум, потому что
          объясняют словами, а картинка — подтверждение к сказанному; равные половины
          сделали бы из приложений обязательный шаг. */}
      {ask && (
        <div style={{ background: C.subtle, border: `1px solid ${C.border}`,
          borderRadius: 11, padding: '12px 14px', display: 'flex',
          flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 12.5, color: C.secondary }}>
            {ask === 'отказ'
              ? 'Почему не берём размещение? Новая версия баннера сюда уже не придёт.'
              : 'Что переделать в баннере?'}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '4fr 1fr', gap: 12,
            alignItems: 'stretch' }}>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(reasons?.[ask] || []).map(r => (
                  <span key={r} onClick={() => setReason(r)}
                    style={{ cursor: 'pointer', fontSize: 12, padding: '5px 10px',
                      borderRadius: 100, background: reason === r ? C.accent : C.card,
                      color: reason === r ? '#FFFFFF' : C.secondary,
                      border: `1px solid ${reason === r ? C.accent : C.border}` }}>{r}</span>
                ))}
              </div>
              <textarea autoFocus
                style={{ ...inp, flex: 1, minHeight: 96, fontFamily: UI, resize: 'vertical' }}
                placeholder="Своими словами — что именно не так и что поправить"
                value={reason} onChange={e => setReason(e.target.value)} />
            </div>

            {/* Зона приёма — весь правый столбец, а не кнопка в нём: файлы тащат в
                область, а не целятся в прямоугольник. `preventDefault` на dragOver
                обязателен — без него браузер не считает область принимающей и на drop
                ОТКРОЕТ файл вместо загрузки, потеряв всё несохранённое. */}
            <div
              onDragOver={e => { e.preventDefault(); if (!drag) setDrag(true) }}
              onDragLeave={e => { if (e.currentTarget === e.target) setDrag(false) }}
              onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer?.files) }}
              style={{ border: `1px dashed ${drag ? C.accent : C.border}`, borderRadius: 10,
                background: drag ? C.accentTint : C.card, padding: '10px 11px',
                display: 'flex', flexDirection: 'column', gap: 7, minWidth: 0,
                transition: 'background .12s, border-color .12s' }}>
              <span style={{ ...CAP, marginBottom: 0 }}>скриншоты</span>
              <span style={{ fontSize: 11, color: C.faint, lineHeight: 1.45 }}>
                {drag ? 'Отпустите — заберём'
                  : 'Перетащите сюда или выберите. PNG, JPG, WEBP, PDF · до 5 файлов'}
              </span>
              {files.map(f => (
                <span key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 6,
                  fontFamily: MONO, fontSize: 10.5, color: C.secondary }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap' }} title={f.name}>{f.name}</span>
                  <span style={{ color: C.faint }}>{Math.round((f.size_bytes || 0) / 1024)} КБ</span>
                </span>
              ))}
              {files.length < 5 && (
                <label style={{ ...btnSm(false), textAlign: 'center',
                  cursor: upBusy ? 'progress' : 'pointer' }}>
                  {upBusy ? 'Грузим…' : 'Выбрать'}
                  <input type="file" multiple accept=".png,.jpg,.jpeg,.webp,.pdf"
                    style={{ display: 'none' }}
                    onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
                </label>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button style={btn(false)}
              onClick={() => { setAsk(null); setReason(''); setFiles([]) }}>Отмена</button>
            <span style={{ flex: 1 }} />
            <button style={btn(true)} disabled={busy || !reason.trim()}
              onClick={() => answer(ask, reason)}>
              {ask === 'отказ' ? 'Отказаться' : 'Отправить на доработку'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ─────────────────────────── медиакит ─────────────────────────── */

function MediaKit({ profile, onDone, onErr }) {
  const [busy, setBusy] = useState(false)

  const upload = async (f) => {
    if (!f) return
    setBusy(true)
    const form = new FormData()
    form.append('file', f)
    try {
      await api.post('/media-kit', form,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      onDone()
    } catch (e) { onErr(e.response?.data?.detail || 'Не удалось загрузить медиакит') }
    setBusy(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ fontSize: 12.5, color: C.secondary, lineHeight: 1.5 }}>
        Презентация площадки — по ней мы отбираем инвентарь под кампании.
      </div>
      {profile?.media_kit ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, borderRadius: 10,
          padding: '8px 10px', border: `1px solid ${C.border}`, background: C.subtle }}>
          <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>Загружен</span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint,
              wordBreak: 'break-all' }}>{profile.media_kit}</span>
          </span>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: C.faint }}>Пока не загружен.</div>
      )}
      {/* Новый файл ЗАМЕЩАЕТ старый: у площадки медиакит один, и «версия от 03.07» —
          это дата загрузки, а не отдельная запись. */}
      <label style={{ ...btn(false), display: 'inline-block', textAlign: 'center',
        cursor: busy ? 'progress' : 'pointer' }}>
        {busy ? 'Загрузка…' : profile?.media_kit ? 'Обновить' : 'Прикрепить медиакит'}
        <input type="file" accept=".pdf,.pptx" style={{ display: 'none' }}
          onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
      </label>
      <span style={{ fontSize: 11, color: C.faint }}>PDF или PPTX, до 30 МБ</span>
    </div>
  )
}

/* ─────────────────────────── кампании (демо) ─────────────────────────── */

function Bar({ value, tone }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
      <span style={{ flex: 1, height: 6, borderRadius: 2, background: C.inner,
        overflow: 'hidden', minWidth: 40 }}>
        <span style={{ display: 'block', height: '100%', width: `${Math.min(100, value)}%`,
          background: tone, borderRadius: 2 }} />
      </span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: tone,
        width: 38, textAlign: 'right' }}>{Math.round(value)}%</span>
    </span>
  )
}

const GRID = 'minmax(190px,1.3fr) 88px 118px minmax(150px,0.95fr) 118px 196px'

/** Соседний месяц. `2026-08` → `2026-07` / `2026-09`.
 *
 * Через `Date` считать нельзя: `new Date()` на сервере и в браузере даёт разное, а
 * арифметика по строке — чистая функция и одинакова везде. */
const shiftMonth = (p, d) => {
  const [y, m] = p.split('-').map(Number)
  const t = (y * 12 + (m - 1)) + d
  return `${Math.floor(t / 12)}-${String(t % 12 + 1).padStart(2, '0')}`
}

function Campaigns({ period: initial }) {
  const [open, setOpen] = useState({})

  /* Срез держит САМА таблица, а не страница: сводка сверху говорит про текущий месяц —
     «сколько должны сейчас», — и уезжать в июль вместе с таблицей ей незачем. */
  const [period, setPeriod] = useState(initial)
  const rows = CAMPS.map(camp).filter(c => c.period === period)

  /* Пороги открутки зависят от того, ЗАКРЫТ ли месяц. Красить 63 % красным 28-го числа
     при флайте до 31-го — самая частая ошибка такого экрана. */
  const paceTone = (v) => {
    if (!isClosed(period)) return C.accent
    return v >= 97 ? C.income : v >= 90 ? C.warning : C.danger
  }

  const groups = {}
  rows.forEach(c => { (groups[c.service] = groups[c.service] || []).push(c) })

  const totalFact = rows.filter(inPace).reduce((a, c) => a + c.fact, 0)
  const totalPlan = rows.filter(inPace).reduce((a, c) => a + c.plan, 0)
  const totalSum = rows.filter(inBill).reduce((a, c) => a + sum(c), 0)

  return (
    <div style={{ ...card, padding: '16px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <span style={{ fontSize: 15, fontWeight: 800 }}>Кампании и деньги</span>
        <Demo what="Факт показов заводится на сверке — до неё у кампании есть только состояние «запущен»" />
        <span style={{ flex: 1 }} />

        {/* Переключатель: год как неподвижная опора, месяц как то, что двигают.
            Год отдельной подписью, а не в самой пилюле, потому что листают месяцами и
            за год выходят редко — иначе при каждом шаге меняется вся надпись, и глазу
            не за что зацепиться.
            Вперёд за текущий месяц не пускаем: будущих кампаний в отчёте не бывает, а
            живая стрелка в пустоту читается как поломка. */}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2,
          border: `1px solid ${C.border}`, borderRadius: 10, padding: 3,
          background: C.card }}>
          <span style={{ ...CAP, marginBottom: 0, padding: '0 9px 0 6px',
            color: C.secondary }}>{period.slice(0, 4)} год</span>
          <button aria-label="Предыдущий месяц" style={arrowBtn(true)}
            onClick={() => setPeriod(p => shiftMonth(p, -1))}>‹</button>
          <span style={{ ...chip(C.accentTint, C.accent, C.accentBorder),
            fontFamily: MONO, fontSize: 12, padding: '4px 12px' }}>{period}</span>
          <button aria-label="Следующий месяц" disabled={period >= NOW_MONTH}
            style={arrowBtn(period < NOW_MONTH)}
            onClick={() => setPeriod(p => shiftMonth(p, 1))}>›</button>
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 1020 }}>
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12,
            padding: '0 4px 8px', borderBottom: `1px solid ${C.border}`, ...CAP }}>
            <span>Услуга и РК</span><span>Период</span><span>Факт показов</span>
            <span>Открутка</span><span>К оплате</span><span>Состояние и что нужно</span>
          </div>

          {Object.entries(groups).map(([service, list]) => {
            const gFact = list.filter(inPace).reduce((a, c) => a + c.fact, 0)
            const gPlan = list.filter(inPace).reduce((a, c) => a + c.plan, 0)
            const gSum = list.filter(inBill).reduce((a, c) => a + sum(c), 0)
            const pace = gPlan ? gFact / gPlan * 100 : 0
            const blocked = billBlocked(list)
            const pay = blocked ? 'счёт не выставлен' : (GROUP_PAY[`${service}|${period}`] || 'счёт не выставлен')
            const [pb, pf, pd] = PAY_STATE[pay]
            const shown = open[service] !== false
            return (
              <div key={service}>
                <div onClick={() => setOpen({ ...open, [service]: !shown })}
                  style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12,
                    alignItems: 'center', padding: '10px 4px', cursor: 'pointer',
                    background: C.tint, borderRadius: 10,
                    border: `1px solid ${shown ? C.accentBorder : 'transparent'}` }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: C.faint, fontSize: 11 }}>{shown ? '▾' : '▸'}</span>
                    <span style={{ width: 7, height: 7, borderRadius: 2,
                      background: SERVICE_DOT[service] || C.accent }} />
                    <span style={{ fontSize: 13.5, fontWeight: 700 }}>{service}</span>
                    <span style={{ ...CAP, marginBottom: 0 }}>
                      {list.filter(inBill).length} РК в счёте
                      {list.length - list.filter(inBill).length
                        ? ` · ${list.length - list.filter(inBill).length} в архиве` : ''}
                    </span>
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.muted }}>{period}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{num(gFact)}</span>
                  <Bar value={pace} tone={paceTone(pace)} />
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{rub(gSum)}</span>
                  <span><span style={chip(pb, pf, pd)}>{pay}</span></span>
                </div>

                {/* Правило блокировки счёта объясняется ПОДПИСЬЮ, а не пустым статусом:
                    «счёт не выставлен» без причины читается как наша забывчивость. */}
                {blocked && (
                  <div style={{ fontSize: 11.5, color: C.muted, padding: '6px 4px 0 30px' }}>
                    {list.every(c => c.state === 'ждёт запуска')
                      ? 'период ещё не начался — открутка и счёт появятся после старта'
                      : `месяц не закрыт · ${list.filter(c => c.state === 'в размещении').length} РК ещё идут — счёт выставим после закрытия периода`}
                  </div>
                )}

                {shown && list.map((c, i) => {
                  const [sb, sf, sd] = RK_STATE[c.state] || RK_STATE['архив']
                  const need = NEED[c.state]
                  const p = c.plan ? c.fact / c.plan * 100 : 0
                  return (
                    <div key={i} className="row-hover" style={{ display: 'grid',
                      gridTemplateColumns: GRID, gap: 12, alignItems: 'center',
                      padding: '9px 4px 9px 22px', borderBottom: `1px solid ${C.row}` }}>
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ width: 7, height: 7, borderRadius: 2, background: sf }} />
                          <span style={{ fontSize: 13, fontWeight: 600 }}>{c.brand}</span>
                          {c.mark?.includes('продление') && (
                            <span style={{ ...chip(C.violetTint, C.violetFg), fontSize: 10 }}>продление</span>
                          )}
                          {c.mark?.includes('отказ') && (
                            <span style={{ ...chip(C.dangerTint, C.danger), fontSize: 10 }}>отказ</span>
                          )}
                        </span>
                        <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint }}>
                          {c.surface} · {c.flight}
                        </span>
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.muted }}>{c.period}</span>
                      <span style={{ fontFamily: MONO, fontSize: 12 }}>{inPace(c) ? num(c.fact) : '—'}</span>
                      {inPace(c) ? <Bar value={p} tone={paceTone(p)} />
                        : <span style={{ fontSize: 11.5, color: C.faint }}>не в открутке</span>}
                      <span style={{ fontFamily: MONO, fontSize: 12 }}>
                        {inBill(c) ? rub(sum(c))
                          : <span style={{ fontSize: 11.5, color: C.faint }}>не в счёте</span>}
                      </span>
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={chip(sb, sf, sd)}>{c.state}</span>
                        {!!need && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                            <span style={{ fontSize: 11, color: need[2] }}>{need[0]}</span>
                            <button style={{ ...btnSm(!!need[3]), fontSize: 10.5,
                              padding: '3px 8px' }}>{need[1]}</button>
                          </span>
                        )}
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })}

          {!rows.length && (
            <div style={{ padding: '26px 4px', fontSize: 12.5, color: C.faint }}>
              За {periodLabel(period)} кампаний не было.
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12,
            alignItems: 'center', padding: '12px 4px 0' }}>
            <span style={{ ...CAP, marginBottom: 0, color: C.muted }}>Итого</span>
            <span />
            <span style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700 }}>{num(totalFact)}</span>
            <span style={{ fontFamily: MONO, fontSize: 12, color: C.muted }}>
              {totalPlan ? `${Math.round(totalFact / totalPlan * 100)} % по показам` : '—'}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700 }}>{rub(totalSum)}</span>
            <span />
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12,
        paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
        <span style={{ fontSize: 11.5, color: C.faint }}>
          суммы до НДС · сверка по факту закрытия периода
        </span>
        <span style={{ flex: 1 }} />
        <button style={btnSm(false)} disabled title="Актов в системе пока нет">Акты и УПД</button>
        <button style={btnSm(false)} disabled title="Появится вместе с фактом показов">Excel</button>
      </div>
    </div>
  )
}

/* ─────────────────────────── страница ─────────────────────────── */

/* Тон значения несёт смысл, а не украшает: деньги в пути жёлтые, работа зелёная,
   несделанное красное. Одинаковый цвет у всех четырёх превращает сводку в таблицу. */
const KPI_TONE = ['var(--text-primary)', 'var(--warning)', 'var(--income)', 'var(--danger)']

const NAV = [
  { key: 'queue', label: 'Дашборд' },
  { key: 'creatives', label: 'Креативы' },
  { key: 'camps', label: 'Кампании' },
]

export default function Cabinet() {
  const [ready, setReady] = useState(false)
  const [authed, setAuthed] = useState(false)
  const [tasks, setTasks] = useState(null)
  const [dash, setDash] = useState(null)
  const [reasons, setReasons] = useState(null)
  const [me, setMe] = useState(null)
  const [err, setErr] = useState('')
  const [name, setName] = useState('')
  const [active, setActive] = useState('queue')
  const [openDone, setOpenDone] = useState(false)
  const [bulk, setBulk] = useState(false)
  /* Сегодня берётся один раз после монтирования: `new Date()` при рендере даёт на
     сервере и клиенте разные значения на границе суток и ошибку гидрации. */
  const [today, setToday] = useState(null)

  const load = useCallback(async () => {
    setErr('')
    try {
      const [t, d, m] = await Promise.all([
        api.get('/tasks', auth()), api.get('/dashboard', auth()), api.get('/me', auth()),
      ])
      setTasks(t.data); setDash(d.data); setMe(m.data)
    } catch (e) {
      if (e.response?.status === 401 || e.response?.status === 403) {
        signOut(); setAuthed(false); return
      }
      setErr(e.response?.data?.detail || 'Не удалось загрузить кабинет')
    }
  }, [])

  useEffect(() => {
    try {
      setAuthed(!!localStorage.getItem(TOKEN_KEY))
      setName(localStorage.getItem('cabinet_name') || '')
    } catch { /* приватный режим */ }
    setToday(new Date(new Date().toDateString()))
    setReady(true)
  }, [])

  useEffect(() => {
    if (!authed) return
    load()
    api.get('/reasons', auth()).then(r => setReasons(r.data)).catch(() => {})
  }, [authed, load])

  /* Последовательно, а не пачкой: каждый ответ ядро пишет своей транзакцией и выдаёт
     код пары по схождению. Параллельные вызовы получили бы один и тот же номер. */
  const approveAll = async () => {
    /* Задания с висящим запросом ссылки в пачку не идут: ядро отклонит такой «ок», а
       цикл рвётся на первой ошибке — одна заблокированная площадка оставила бы
       несогласованным весь хвост очереди. Их число называется вслух, иначе «согласовать
       все» согласует не все и промолчит об этом. */
    const list = allTasks.filter(t => t.url_state !== 'запрошена')
    const held = allTasks.length - list.length
    if (!list.length) {
      setErr('Все задания ждут посадочные страницы — согласовывать пока нечего')
      return
    }
    if (!window.confirm(`Согласовать ${list.length}?`
      + (held ? ` ${held} — ждут посадочную и останутся в очереди.` : '')
      + ' Отменить ответ нельзя.')) return
    setBulk(true); setErr('')
    let done = 0
    for (const t of list) {
      try {
        await api.post(`/tasks/${t.task_id}/verdict`, { verdict: 'ок' }, auth())
        done++
      } catch (e) {
        setErr(`${e.response?.data?.detail || 'Не удалось'} — согласовано ${done} из ${list.length}`)
        break
      }
    }
    await load()
    setBulk(false)
  }

  const allTasks = useMemo(
    () => (dash && tasks ? (tasks.publishers || []).flatMap(g => g.tasks) : []),
    [tasks, dash])

  if (!ready) return null
  if (!authed) {
    return (
      <>
        <Head><title>Кабинет площадки</title></Head>
        <Login onDone={() => {
          setAuthed(true)
          setName(localStorage.getItem('cabinet_name') || '')
        }} />
      </>
    )
  }

  const profile = dash?.profile
  const done = dash?.done || []
  const period = NOW_MONTH
  const money = CAMPS.map(camp).filter(c => c.period === period && inBill(c))
  const accrued = money.reduce((a, c) => a + sum(c), 0)
  const awaiting = CAMPS.map(camp).filter(
    c => ['ждёт акта', 'акт подписан'].includes(GROUP_PAY[`${c.service}|${c.period}`]) && inBill(c)
  ).reduce((a, c) => a + sum(c), 0)
  const activeCount = money.filter(c => c.state === 'в размещении').length

  const services = new Set(money.map(c => c.service)).size
  const late = allTasks.filter(t => (t.waiting_days || 0) >= 3).length

  /* Значения по формулам эталона (README, 1.8). «Ожидает оплаты» считается по ВСЕМ
     периодам, а не по выбранному: иначе кабинет заявляет «оплачено 0 ₽» при подписанных
     актах прошлого месяца. Это подписано в хинте — иначе цифра выглядит ошибкой. */
  const KPI = [
    ['начислено за период', rub(accrued), '', '', null,
     `до НДС · ${services} ${services === 1 ? 'услуга' : 'услуги'} в срезе`],
    ['ожидает оплаты', rub(awaiting), '', awaiting ? '1 счёт' : '',
     [C.warningTint, C.warningFg, C.warningBorder], 'по всем периодам'],
    ['активных кампаний', String(activeCount), 'РК', '', null, 'все запущены'],
    ['требует решения', String(tasks?.total ?? 0), 'запросов',
     late ? `${late} просрочен${late === 1 ? '' : 'о'}` : '',
     [C.dangerTint, C.danger, C.dangerBorder], 'креативы, пролонгации, сверки'],
  ]

  return (
    <>
      <Head><title>Кабинет площадки</title></Head>
      <Header profile={profile} name={name} nav={NAV.map(n => n.key === 'creatives'
        ? { ...n, badge: tasks?.total || 0 } : n)}
        active={active} onNav={setActive} count={(dash?.publishers || []).length}
        onExit={() => { signOut(); setAuthed(false) }} />

      <div style={{ ...WRAP, display: 'flex', gap: 14, alignItems: 'flex-start',
        padding: '20px 20px 60px' }}>

        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {!!err && (
            <div style={{ ...card, padding: '12px 16px', color: C.danger,
              borderColor: C.dangerBorder, background: C.dangerBg }}>{err}</div>
          )}

          {/* Мой период */}
          <div className="rise" style={{ ...card, padding: '18px 22px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 26, fontWeight: 800 }}>Мой период</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.faint,
                letterSpacing: '.06em', textTransform: 'uppercase' }}>
                {(profile?.domain || '—')} · {period}
              </span>
              <span style={{ flex: 1 }} />
              <button style={btn(false)} disabled
                title="Появится вместе с фактом показов — сейчас выгружать нечего">
                Выгрузить отчёт
              </button>
            </div>

            {/* Разделители, а не плитки: четыре значения читаются как один ряд, и рамка
                вокруг каждого превращает сводку в четыре независимые карточки. */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
              marginTop: 18 }}>
              {KPI.map(([label, value, unit, chipText, chipTone, hint], i) => (
                <div key={label} style={{ padding: i ? '0 0 0 26px' : 0,
                  borderLeft: i ? `1px solid ${C.row}` : 'none', marginLeft: i ? 26 : 0 }}>
                  <div style={{ ...CAP, marginBottom: 0 }}>{label}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 7,
                    marginTop: 7 }}>
                    <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700,
                      letterSpacing: '-0.02em', color: KPI_TONE[i] }}>{value}</span>
                    {!!unit && (
                      <span style={{ fontSize: 13, color: C.muted }}>{unit}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6,
                    flexWrap: 'wrap' }}>
                    {!!chipText && (
                      <span style={{ ...chip(...chipTone), fontSize: 10.5,
                        padding: '2px 8px' }}>{chipText}</span>
                    )}
                    <span style={{ fontSize: 11.5, color: C.faint }}>{hint}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Очередь */}
          <div className="rise" style={{ ...card, padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14,
              flexWrap: 'wrap' }}>
              <span style={{ fontSize: 17, fontWeight: 800 }}>Требует вашего решения</span>
              <span style={{ ...chip(C.dangerTint, C.danger, C.dangerBorder),
                fontFamily: MONO }}>{tasks?.total ?? 0}</span>
              <span style={{ ...CAP, marginBottom: 0 }}>
                креативы, пролонгации, сверки · дедлайн решения
              </span>
              <span style={{ flex: 1 }} />
              {me && !me.can_approve
                ? <span style={{ fontSize: 11.5, color: C.faint }}>
                    у вас доступ только на просмотр
                  </span>
                : !!allTasks.length && (
                  <>
                    {/* «Согласовать все» — не украшение: один баннер уходит на несколько
                        сайтов, и площадка отвечает по каждому отдельно. Подтверждение
                        спрашивается, потому что действие необратимо. */}
                    <button style={{ ...soft(C.accent, C.accentBorder),
                      padding: '7px 14px', fontSize: 12.5 }} disabled={bulk}
                      onClick={approveAll}>
                      {bulk ? 'Согласуем…' : 'Согласовать все'}
                    </button>
                  </>
                )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {allTasks.map(t => (
                <Task key={t.task_id} t={t} reasons={reasons} today={today}
                  canApprove={!!me?.can_approve} onDone={load} onErr={setErr} />
              ))}
              {!allTasks.length && (
                <div style={{ padding: '22px 0', textAlign: 'center', color: C.muted,
                  fontSize: 13 }}>
                  Новых креативов на согласование нет.
                </div>
              )}
            </div>
          </div>

          {/* Обработано за неделю */}
          <div className="rise" style={{ ...card, padding: '16px 18px' }}>
            <div onClick={() => setOpenDone(!openDone)}
              style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
              <span style={{ color: C.faint, fontSize: 11 }}>{openDone ? '▾' : '▸'}</span>
              <span style={{ fontSize: 15, fontWeight: 800 }}>Обработано за неделю</span>
              <span style={{ ...chip(C.subtle, C.secondary, C.border), fontFamily: MONO }}>
                {done.length}
              </span>
            </div>
            {openDone && (
              <div className="pop" style={{ marginTop: 12 }}>
                <div style={{ display: 'grid',
                  gridTemplateColumns: '118px minmax(140px,0.8fr) minmax(150px,0.85fr) minmax(300px,2.2fr)',
                  gap: 12, padding: '0 4px 8px', borderBottom: `1px solid ${C.border}`, ...CAP }}>
                  <span>Статус</span><span>Кампания</span><span>Креатив</span><span>Комментарий</span>
                </div>
                {done.map(d => (
                  <div key={d.task_id} style={{ display: 'grid',
                    gridTemplateColumns: '118px minmax(140px,0.8fr) minmax(150px,0.85fr) minmax(300px,2.2fr)',
                    gap: 12, alignItems: 'start', padding: '9px 4px',
                    borderBottom: `1px solid ${C.row}` }}>
                    <span>
                      <span style={chip(
                        d.verdict === 'ок' ? C.incomeTint : C.dangerTint,
                        d.verdict === 'ок' ? C.incomeFg : C.danger,
                        d.verdict === 'ок' ? C.incomeBorder : C.dangerBorder)}>
                        {d.verdict === 'ок' ? 'согласовано' : d.verdict}
                      </span>
                    </span>
                    <span style={{ fontSize: 12.5 }}>{d.brand || d.advertiser || '—'}</span>
                    <span style={{ fontSize: 12.5, color: C.secondary }}>
                      Креатив №{d.creative_no}{d.creative_title ? ` — ${d.creative_title}` : ''}
                    </span>
                    {/* Комментарий целиком, без эллипсиса: обрезанная причина доработки
                        бесполезна, а места здесь достаточно. */}
                    <span style={{ fontSize: 12.5, color: C.muted, textWrap: 'pretty' }}>
                      {d.reason || '—'}
                    </span>
                  </div>
                ))}
                {!done.length && (
                  <div style={{ padding: '14px 4px', fontSize: 12.5, color: C.faint }}>
                    За неделю решений не было.
                  </div>
                )}
              </div>
            )}
          </div>

          <Campaigns period={period} />
        </div>

        {/* правая колонка */}
        <div style={{ width: 280, flex: '0 0 280px', display: 'flex',
          flexDirection: 'column', gap: 14 }}>

          <Side title="бот в телеграме" accent>
            <div style={{ fontSize: 12.5, color: C.secondary, lineHeight: 1.5 }}>
              Уведомления о новых креативах, дедлайнах и сверке.
            </div>
            <span style={{ ...chip(C.subtle, C.muted, C.border) }}>не подключён</span>
            <button style={btn(false)} disabled
              title="Отдельный бот кабинета ещё не поднят">Подключить бота</button>
            <Demo what="Бота площадки в системе пока нет — это отдельный бот, не наш внутренний" />
          </Side>

          <Side title="ваша команда">
            {(dash?.team || []).map((m, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span style={{ width: 32, height: 32, borderRadius: 10, flex: '0 0 32px',
                  background: C.accentTint, color: C.accent, display: 'inline-flex',
                  alignItems: 'center', justifyContent: 'center', fontWeight: 800,
                  fontSize: 11 }}>
                  {(m.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{m.name}</span>
                  <span style={{ ...CAP, marginBottom: 0 }}>{m.role}</span>
                  {/* Почта текстом — её копируют. Телефонов в системе нет вовсе, и
                      выдумывать их неоткуда. */}
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.secondary,
                    wordBreak: 'break-all' }}>{m.email || 'почта не указана'}</span>
                </span>
              </div>
            ))}
            {!(dash?.team || []).length && (
              <div style={{ fontSize: 12, color: C.faint }}>
                Команда появится, когда у площадки будет активная кампания.
              </div>
            )}
            {(profile?.chat_url || profile?.chat_url_max || profile?.chat_title) && (
              <div style={{ borderTop: `1px solid ${C.row}`, paddingTop: 10,
                display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>рабочая группа</span>
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>
                  {profile.chat_title || 'рабочий чат'}
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <a href={profile.chat_url || '#'} target="_blank" rel="noreferrer"
                    style={{ ...btnSm(false), flex: 1, textAlign: 'center',
                      textDecoration: 'none',
                      opacity: profile.chat_url ? 1 : .45,
                      pointerEvents: profile.chat_url ? 'auto' : 'none' }}>Телеграм</a>
                  <a href={profile.chat_url_max || '#'} target="_blank" rel="noreferrer"
                    style={{ ...btnSm(false), flex: 1, textAlign: 'center',
                      textDecoration: 'none',
                      opacity: profile.chat_url_max ? 1 : .45,
                      pointerEvents: profile.chat_url_max ? 'auto' : 'none' }}>MAX</a>
                </div>
              </div>
            )}
          </Side>

          <Side title="медиакит">
            {/* Документов здесь больше нет (владелец 28.08.2026): актов и УПД в системе
                не существует, а блок, показывающий несуществующее, площадка читает как
                факт. Остался медиакит — единственное, что площадка действительно даёт
                нам сама. */}
            <MediaKit profile={profile} onDone={load} onErr={setErr} />
          </Side>
        </div>
      </div>
    </>
  )
}
