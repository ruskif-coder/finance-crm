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
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import Head from 'next/head'
import api, { auth, signOut, TOKEN_KEY } from '../lib/http'
import { PreviewModal } from '../lib/preview'
import { overlayClose } from '../lib/overlay'
import { Header, Side, Demo, WRAP } from './Shell'
import { C, CAP, MONO, UI, arrowBtn, btn, btnSm, card, chip, dm, inp, num, periodLabel,
  rub, soft }
  from '../lib/ui'
import { daysTo, startNote, urgency } from '../lib/urgency'
import { NEED, PAY_STATE, RK_STATE, SERVICE_DOT,
  SHOW_MONEY, billBlocked, blocking, camp, inBill, inPace, sum, useDemoNow } from '../lib/demo'




/* ─────────────────────────── очередь ─────────────────────────── */

/* Дни до старта — не украшение: у площадки в работе несколько кампаний, и очерёдность
   разбора она выбирает по тому, что стартует раньше. Считается от даты, переданной
   снаружи: `Date` внутри компонента дал бы расхождение сервера и клиента на границе
   суток и ошибку гидрации. */
// `daysTo`, `urgency`, `startNote` — в lib/urgency.js: правило было в двух местах
// и разошлось (см. шапку модуля).

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
  const level = urgency(t.period_from, today)
  const late = level === 'overdue'
  const soon = level === 'soon'
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
        {/* Чья это площадка. У учётки сети сайтов несколько, и одинаковый баннер
            приходит по каждому отдельно: без метки две строки выглядят дублем одной. */}
        {!!t.publisher && (
          <span style={{ ...chip(C.subtle, C.secondary, C.border), fontSize: 11 }}>
            {t.publisher}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {/* Плашка старта: дата и сколько до неё осталось. Одна дата без остатка
            заставляет считать в уме, а решение принимают по остатку. */}
        <span style={{ ...chip(stChipBg, stChipFg, stChipBd), fontFamily: MONO, gap: 8 }}>
          <span style={{ color: C.muted }}>старт рк</span>
          <b>{dm(t.period_from)}</b>
          {toStart !== null && (
            <span style={{ borderLeft: `1px solid ${stChipBd}`, paddingLeft: 8 }}>
              {startNote(t.period_from, today)}
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
              color: urlPending ? C.faint : C.onFill,
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
                      color: reason === r ? C.onFill : C.secondary,
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

const GRID = 'minmax(190px,1.3fr) minmax(110px,0.7fr) 88px 118px minmax(150px,0.95fr) 118px 196px'

/** Соседний месяц. `2026-08` → `2026-07` / `2026-09`.
 *
 * Через `Date` считать нельзя: `new Date()` на сервере и в браузере даёт разное, а
 * арифметика по строке — чистая функция и одинакова везде. */
const shiftMonth = (p, d) => {
  const [y, m] = p.split('-').map(Number)
  const t = (y * 12 + (m - 1)) + d
  return `${Math.floor(t / 12)}-${String(t % 12 + 1).padStart(2, '0')}`
}

function Campaigns({ period: initial, publisher, sites }) {
  const [open, setOpen] = useState({})
  /* Витрина считается от СЕГОДНЯШНЕГО месяца, а не от зашитой даты. */
  const { NOW_MONTH, CAMPS, GROUP_PAY, isClosed } = useDemoNow()

  /* Срез держит САМА таблица, а не страница: сводка сверху говорит про текущий месяц —
     «сколько должны сейчас», — и уезжать в июль вместе с таблицей ей незачем. */
  const [period, setPeriod] = useState(initial)
  /* Настоящий месяц приезжает после монтирования, и срез обязан за ним последовать:
     иначе таблица навсегда осталась бы на опорном месяце первой отрисовки. Пользователь,
     уже переключившийся руками, не сбрасывается — сравнение идёт с ПРЕЖНИМ `initial`. */
  const prevInitial = useRef(initial)
  useEffect(() => {
    if (prevInitial.current !== initial) {
      setPeriod(p => (p === prevInitial.current ? initial : p))
      prevInitial.current = initial
    }
  }, [initial])
  /* Год целиком — не «ещё один период», а другой вопрос: месяц отвечает «что сейчас»,
     год — «сколько всего было». Поэтому отдельный переключатель, а не тринадцатое
     значение в той же ленте месяцев. */
  const [wholeYear, setWholeYear] = useState(false)
  const year = period.slice(0, 4)
  /* Выбор площадки приходит СВЕРХУ, тем же, что сужает очередь: иначе шапка говорит
     про одну площадку, а деньги под ней — про все, и два числа на экране спорят. */
  /* Площадка приписывается кампании ИЗ КАБИНЕТА, а не из демо-строки: у кабинета одной
     площадки все кампании её, у сети — раскладываются по её сайтам по кругу. Зашитое в
     данные имя показывало бы чужой сайт тому, у кого его нет. */
  const own = (sites || []).map(s => s.name).filter(Boolean)
  const rows = CAMPS.map((c, i) => ({ ...camp(c),
    publisher: own.length ? own[i % own.length] : null })).filter(
    c => (wholeYear ? c.period.startsWith(`${year}-`) : c.period === period)
      && (!publisher || c.publisher === publisher))

  /* Пороги открутки зависят от того, ЗАКРЫТ ли месяц. Красить 63 % красным 28-го числа
     при флайте до 31-го — самая частая ошибка такого экрана. */
  const paceTone = (v, forPeriod = period) => {
    if (!isClosed(forPeriod)) return C.accent
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
          {/* Год — кнопка, а не подпись: по ней смотрят весь год сразу. Подсвечена,
              когда включена, иначе непонятно, что показано — месяц или всё. */}
          <button title={wholeYear ? 'Вернуться к месяцу' : 'Показать весь год'}
            onClick={() => setWholeYear(v => !v)}
            style={{ ...CAP, marginBottom: 0, padding: '4px 9px', border: 0,
              borderRadius: 8, cursor: 'pointer', fontFamily: MONO,
              background: wholeYear ? C.accentTint : 'transparent',
              color: wholeYear ? C.accent : C.secondary }}>{year} год</button>
          {/* Стрелки и месяц гасятся в годовом срезе, но остаются рабочими: выбрать
              месяц — значит захотеть месяц, поэтому клик сам возвращает к нему. */}
          <button aria-label="Предыдущий месяц" style={arrowBtn(true)}
            onClick={() => { setWholeYear(false); setPeriod(p => shiftMonth(p, -1)) }}>‹</button>
          <span onClick={() => setWholeYear(false)}
            style={{ ...chip(wholeYear ? C.subtle : C.accentTint,
              wholeYear ? C.muted : C.accent, wholeYear ? C.border : C.accentBorder),
              fontFamily: MONO, fontSize: 12, padding: '4px 12px',
              cursor: wholeYear ? 'pointer' : 'default' }}>{period}</span>
          <button aria-label="Следующий месяц" disabled={!wholeYear && period >= NOW_MONTH}
            style={arrowBtn(wholeYear || period < NOW_MONTH)}
            onClick={() => { setWholeYear(false); setPeriod(p => shiftMonth(p, 1)) }}>›</button>
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 1020 }}>
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12,
            padding: '0 4px 8px', borderBottom: `1px solid ${C.border}`, ...CAP }}>
            <span>Услуга и РК</span><span>Площадка</span><span>Период</span>
            <span>Факт показов</span>
            <span>Открутка</span><span>К оплате</span><span>Состояние и что нужно</span>
          </div>

          {Object.entries(groups).map(([service, list]) => {
            const gFact = list.filter(inPace).reduce((a, c) => a + c.fact, 0)
            const gPlan = list.filter(inPace).reduce((a, c) => a + c.plan, 0)
            const gSum = list.filter(inBill).reduce((a, c) => a + sum(c), 0)
            const pace = gPlan ? gFact / gPlan * 100 : 0
            const blocked = billBlocked(list)
            /* Состояние счёта — факт КОНКРЕТНОГО месяца. В годовом срезе группа
               охватывает несколько, и одно состояние на все было бы неправдой:
               берём последний месяц, по которому в группе есть строки, и
               подписываем его — иначе «оплачен» читалось бы как «за весь год». */
            const gPubs = [...new Set(list.map(c => c.publisher).filter(Boolean))]
            const gMonth = wholeYear
              ? list.map(c => c.period).sort().slice(-1)[0] || period
              : period
            const pay = blocked ? 'счёт не выставлен'
              : (GROUP_PAY[`${service}|${gMonth}`] || 'счёт не выставлен')
            const [pb, pf, pd] = PAY_STATE[pay]
            /* Число берётся тем же предикатом, что и сама блокировка. Раньше здесь было
               второе условие со своим именем состояния, и подпись говорила «0 РК ещё
               идут» под заблокированным счётом — то есть отрицала собственную причину. */
            const why = !blocked ? ''
              : list.every(c => c.state === 'ждёт запуска')
                ? 'период ещё не начался — открутка и счёт появятся после старта'
                : `месяц не закрыт · ${blocking(list).length} РК ещё идут — `
                  + 'счёт выставим после закрытия периода' 
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
                  {/* Группа — это услуга, а идти она может на нескольких сайтах: тогда
                      вместо имени показываем их число, иначе строка врала бы про один. */}
                  <span style={{ fontSize: 12, color: C.muted, overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {gPubs.length === 1 ? gPubs[0]
                      : gPubs.length ? `${gPubs.length} площадки` : '—'}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.muted }}>
                    {wholeYear ? `весь ${year}` : period}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{num(gFact)}</span>
                  <Bar value={pace} tone={paceTone(pace)} />
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{rub(gSum)}</span>
                  <span><span style={chip(pb, pf, pd)} title={why}>{pay}</span></span>
                </div>

                {/* Причина блокировки видна ВНУТРИ раскрытой группы, а не строкой под
                    свёрнутой: там она висела между чужими заголовками и читалась как
                    подпись к соседней услуге. У свёрнутой она осталась подсказкой на
                    самом чипе — объяснение никуда не делось, просто не мозолит глаза. */}
                {blocked && shown && (
                  <div style={{ fontSize: 11.5, color: C.muted,
                    padding: '8px 4px 2px 30px' }}>{why}</div>
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
                      <span style={{ fontSize: 12, color: C.secondary, overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={c.publisher || ''}>{c.publisher || '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.muted }}>{c.period}</span>
                      <span style={{ fontFamily: MONO, fontSize: 12 }}>{inPace(c) ? num(c.fact) : '—'}</span>
                      {inPace(c) ? <Bar value={p} tone={paceTone(p, c.period)} />
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
            <span /><span />
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

/** Что присылать. Профиль рассылки задан нами, площадка только выключает лишнее.
 *
 * Переключатель, а не набор галочек с кнопкой «сохранить»: пунктов четыре, каждый
 * независим, и промежуточное состояние «выбрал, но не сохранил» здесь нечему служить.
 * Отправляем сразу, при отказе возвращаем как было — иначе экран покажет решение,
 * которого в системе нет.
 */
/** Плашка юрлица: реквизиты сверху, его договоры списком.
 *
 * Форма взята у плашки «Услуги от» в карточке сделки — там ровно то же самое с нашей
 * стороны, и две разные формы для одного факта заставляли бы сверять их глазами.
 */
function LegalCard({ legal }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6,
      background: C.subtle, border: `1px solid ${C.border}`, borderRadius: 12,
      padding: '10px 12px' }}>
      {/* Площадка в подписи: у сети сайтов юрлиц несколько, и одно название компании
          не говорит, чьё оно. У кабинета с одной площадкой строка та же — лишней не
          выглядит, потому что это и есть ответ на «чьё юрлицо». */}
      <span style={{ ...CAP, marginBottom: 0 }}>
        юрлицо{legal.publisher ? ` · ${legal.publisher}` : ''}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
        lineHeight: 1.3 }}>{legal.name}</span>
      <span style={{ ...CAP, marginBottom: 0, color: C.muted }}>
        ИНН {legal.inn || '—'}
        {legal.vat_rate != null ? ` · НДС ${Math.round(legal.vat_rate)} %` : ' · НДС не задан'}
      </span>
      {legal.contracts.length ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 2 }}>
          {legal.contracts.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 7,
              opacity: c.is_archived ? .5 : 1 }}>
              <span style={{ fontSize: 12, fontWeight: 600, minWidth: 0,
                overflow: 'hidden', textOverflow: 'ellipsis',
                whiteSpace: 'nowrap' }} title={c.number}>{c.number}</span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint,
                whiteSpace: 'nowrap' }}>
                {c.role}{c.signed_at ? ` · ${dm(c.signed_at)}` : ''}
                {c.is_archived ? ' · архив' : ''}
              </span>
            </div>
          ))}
        </div>
      ) : (
        /* «Договоров нет» пишется прямо, а не пустотой: пустая плашка читается как
           «данные не загрузились», и площадка приходит спрашивать. */
        <span style={{ fontSize: 11.5, color: C.faint }}>Договоров нет</span>
      )}
    </div>
  )
}

function NotifySwitches({ onErr, onClose }) {
  const [kinds, setKinds] = useState(null)
  const [busy, setBusy] = useState(null)

  useEffect(() => {
    api.get('/notify-settings', auth())
      .then(r => setKinds(r.data.kinds || [])).catch(() => setKinds([]))
  }, [])

  const toggle = async (k) => {
    if (!k.can_mute || busy) return
    const next = !k.muted
    setBusy(k.key)
    setKinds(list => list.map(x => (x.key === k.key ? { ...x, muted: next } : x)))
    try {
      await api.put('/notify-settings', { kind: k.key, muted: next }, auth())
    } catch (e) {
      // Возвращаем как было: экран не должен показывать решение, которого нет в системе.
      setKinds(list => list.map(x => (x.key === k.key ? { ...x, muted: !next } : x)))
      onErr?.(e.response?.data?.detail || 'Не удалось сохранить')
    }
    setBusy(null)
  }

  /* Модалкой, а не панелью в колонке: за шестерёнкой есть место показать ПОДСКАЗКУ к
     каждому виду, а в узкой колонке она умещалась только в тултип — то есть была видна
     тому, кто и так знает, куда навести. Портал в `body` обязателен: карточки колонки
     анимируются `riseIn`, а `transform` у предка переопределяет отсчёт `position: fixed`,
     и окно уезжает под соседей — эта ошибка здесь уже случалась. */
  return createPortal(
    <div style={{ position: 'fixed', inset: 0, background: 'var(--overlay)', zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
      {...overlayClose(onClose)}>
      <div style={{ ...card, width: 'min(520px, 96vw)', maxHeight: '86vh', overflowY: 'auto',
        padding: '20px 22px', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Что присылать</span>
          <span style={{ flex: 1 }} />
          <button style={btn(false)} onClick={onClose}>Закрыть</button>
        </div>
        <div style={{ fontSize: 12.5, color: C.muted, marginBottom: 16, lineHeight: 1.5 }}>
          Набор задаём мы — вы выключаете лишнее. Выключенное не придёт ни в бот, ни на
          почту.
        </div>

        {!kinds && <div style={{ fontSize: 12.5, color: C.faint }}>загрузка…</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {(kinds || []).map(k => (
        <div key={k.key} onClick={() => toggle(k)}
          style={{ display: 'flex', alignItems: 'flex-start', gap: 11,
            padding: '11px 2px', borderTop: `1px solid ${C.row}`,
            cursor: k.can_mute ? 'pointer' : 'default', opacity: busy === k.key ? .5 : 1 }}>
          {/* Рубильник, а не галочка: галочка отвечает на вопрос «выбрано ли», а здесь
              вопрос «включено ли» — состояние, а не выбор. */}
          <span style={{ width: 30, height: 17, borderRadius: 999, flex: '0 0 30px',
            marginTop: 1, position: 'relative',
            background: k.muted ? C.subtle : (k.can_mute ? C.income : C.incomeTint),
            border: `1px solid ${k.muted ? C.border : (k.can_mute ? C.income : C.incomeBorder)}`,
            transition: 'background 140ms ease' }}>
            <span style={{ position: 'absolute', top: 2, left: k.muted ? 2 : 14,
              width: 11, height: 11, borderRadius: 999,
              background: k.muted ? C.faint : (k.can_mute ? C.onFill : C.income),
              transition: 'left 140ms ease' }} />
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, gap: 3 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700,
              color: k.muted ? C.muted : C.text }}>{k.label}</span>
            {/* Подсказка ТЕКСТОМ, а не тултипом: она объясняет, чего лишится площадка,
                выключив пункт, — и читать её должен тот, кто ещё не знает. */}
            <span style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.45 }}>{k.hint}</span>
            {!k.can_mute && (
              <span style={{ ...CAP, marginBottom: 0, color: C.income }}>всегда включено</span>
            )}
          </span>
        </div>
      ))}
        </div>
      </div>
    </div>,
    document.body)
}

/* ─────────────────────────── страница ─────────────────────────── */

/* Тон значения несёт смысл, а не украшает: деньги в пути жёлтые, работа зелёная,
   несделанное красное. Одинаковый цвет у всех четырёх превращает сводку в таблицу. */
const KPI_TONE = ['var(--text-primary)', 'var(--warning)', 'var(--income)', 'var(--danger)']

/* Только «Дашборд» (владелец, 30.08.2026): «Креативы» и «Кампании» пока не делаем.
   Убраны из МЕНЮ, а не спрятаны условием — пункт, который никуда не ведёт, хуже
   отсутствующего: по нему кликают и решают, что сломалось. Вернуть — дописать строку. */
const NAV = [
  { key: 'queue', label: 'Дашборд' },
]

/** Заголовок вкладки. Формат собран В ОДНОМ месте: разделов три, и написанный руками
 *  трижды он разойдётся на первом же переименовании — а видно это только во вкладке. */
const pageTitle = (section) => `SIMB-AD | Кабинет паблишера | ${section}`


export default function Dashboard({ name, onSignOut }) {
  /* Витрина считается от СЕГОДНЯШНЕГО месяца. Хук стоит здесь, а не рядом с местом
     использования: ниже в теле есть условные `return`, и порядок хуков должен быть
     одинаковым при каждой отрисовке. */
  const { NOW_MONTH, CAMPS, GROUP_PAY } = useDemoNow()
  const [tasks, setTasks] = useState(null)
  const [dash, setDash] = useState(null)
  const [reasons, setReasons] = useState(null)
  const [me, setMe] = useState(null)
  const [err, setErr] = useState('')
  const [active, setActive] = useState('queue')
  const [openDone, setOpenDone] = useState(false)
  // Пусто = все площадки. Выбор живёт на СТРАНИЦЕ, а не в каждом списке: от него
  // пересчитывается и очередь, и обработанное, и счётчик в шапке.
  const [pubFilter, setPubFilter] = useState('')
  const [legalsAll, setLegalsAll] = useState(false)
  const [notifyOpen, setNotifyOpen] = useState(false)
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
        onSignOut(); return
      }
      setErr(e.response?.data?.detail || 'Не удалось загрузить кабинет')
    }
  }, [])

  // Дашборд монтируется только после входа (привратник в pages/index.js), поэтому
  // `authed`/`ready` здесь не нужны. «Сегодня» берётся один раз после монтирования:
  // `new Date()` при рендере разошёлся бы между сервером и клиентом на границе суток.
  useEffect(() => {
    setToday(new Date(new Date().toDateString()))
  }, [])

  useEffect(() => {
    load()
    api.get('/reasons', auth()).then(r => setReasons(r.data)).catch(() => {})
  }, [load])

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

  // Площадка приклеивается к КАЖДОМУ заданию при разворачивании групп: дальше список
  // фильтруется и сортируется целиком, и без неё строка не говорит, о чьём инвентаре
  // речь — а у учётки сети сайтов несколько.
  const allTasks = useMemo(
    () => (dash && tasks
      ? (tasks.publishers || []).flatMap(g => (g.tasks || []).map(
        t => ({ ...t, publisher: g.name, publisher_id: g.publisher_id })))
      : []),
    [tasks, dash])

  /* Список площадок для выбора строится ИЗ ДАННЫХ, а не из всех подключённых: у
     служебной учётки их сорок одна, и выпадающий список из сорока пустых строк — это
     не выбор, а поиск. Показываем те, по которым сейчас есть работа или решения. */
  const pubOptions = useMemo(() => {
    const m = new Map()
    ;(tasks?.publishers || []).forEach(g => m.set(g.publisher_id, g.name))
    ;(dash?.done || []).forEach(d => d.publisher_id && m.set(d.publisher_id, d.publisher))
    return [...m.entries()].map(([id, name]) => ({ id, name }))
      .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'))
  }, [tasks, dash])

  /* Услуги, закреплённые за площадками. Считаются от ВЫБОРА: показывать «еФарм» при
     выбранном сайте, где его нет, — врать про его подключение. */
  const shownServices = useMemo(() => {
    const rows = (dash?.services || []).filter(
      x => !pubFilter || x.publisher_id === pubFilter)
    const m = new Map()
    rows.forEach(r => {
      const set = m.get(r.service) || new Set()
      ;(r.surfaces || []).forEach(x => set.add(x))
      m.set(r.service, set)
    })
    return [...m.entries()].map(([name, set]) => ({ name, surfaces: [...set].sort() }))
  }, [dash, pubFilter])

  /* Юрлица и «ничейные» договоры сужаются тем же выбором площадки: иначе виджет
     показывал бы реквизиты соседнего сайта под выбранным. */
  const shownLegals = useMemo(() => (dash?.legals || []).filter(
    l => !pubFilter || l.publisher_id === pubFilter), [dash, pubFilter])
  // Неразложенные договоры приходят ЧИСЛОМ: перечислять их площадке нечем помочь.
  const unassigned = dash?.contracts_unassigned || 0

  const shownTasks = useMemo(() => {
    const list = pubFilter ? allTasks.filter(t => t.publisher_id === pubFilter) : allTasks
    // Сортировка по площадке, потом по сроку: сначала понятно, чей это инвентарь, и
    // только внутри него — что горит.
    return [...list].sort((a, b) =>
      (a.publisher || '').localeCompare(b.publisher || '', 'ru')
      || String(a.period_from || '').localeCompare(String(b.period_from || '')))
  }, [allTasks, pubFilter])

  // ВСЕ хуки объявлены ВЫШЕ ранних выходов: React сверяет их число между рендерами, а
  // `if (!ready) return null` на первом проходе обрывал бы список. Ошибка приходит не в
  // виде «забыл хук», а минифицированной ошибкой 310 из недр рантайма — и роняет весь
  // экран, а не тот кусок, где хук объявлен.
  // «Сегодня» ставится в mount-эффекте после первого рендера — до него не рисуем, чтобы
  // расчёты срочности не считались от пустой даты. Все хуки объявлены ВЫШЕ (ошибка 310).
  if (!today) return null

  const profile = dash?.profile
  const done = (dash?.done || []).filter(
    d => !pubFilter || d.publisher_id === pubFilter)
  const period = NOW_MONTH
  const money = CAMPS.map(camp).filter(c => c.period === period && inBill(c))
  const accrued = money.reduce((a, c) => a + sum(c), 0)
  const awaiting = CAMPS.map(camp).filter(
    c => ['ждёт акта', 'акт подписан'].includes(GROUP_PAY[`${c.service}|${c.period}`]) && inBill(c)
  ).reduce((a, c) => a + sum(c), 0)
  const activeCount = money.filter(c => c.state === 'в размещении').length

  const services = new Set(money.map(c => c.service)).size
  /* Тем же правилом, что и карточки. Здесь стоял `waiting_days >= 3` — счёт от времени
     ожидания, от которого карточки увели ещё 29.08, а сводку забыли: экран сообщал
     «2 просрочено» над списком, где ни одно задание просроченным не значилось. */
  const late = shownTasks.filter(t => urgency(t.period_from, today) === 'overdue').length

  /* Значения по формулам эталона (README, 1.8). «Ожидает оплаты» считается по ВСЕМ
     периодам, а не по выбранному: иначе кабинет заявляет «оплачено 0 ₽» при подписанных
     актах прошлого месяца. Это подписано в хинте — иначе цифра выглядит ошибкой. */
  // Три первые плитки считаются из ТЕХ ЖЕ выдуманных строк, что и таблица кампаний, —
  // поэтому уходят вместе с ней. Оставить их значило бы оставить на экране те же
  // придуманные деньги, только уже без пометки «демо» рядом.
  const KPI = [
    ...(SHOW_MONEY ? [
      ['начислено за период', rub(accrued), '', '', null,
       `до НДС · ${services} ${services === 1 ? 'услуга' : 'услуги'} в срезе`],
      ['ожидает оплаты', rub(awaiting), '', awaiting ? '1 счёт' : '',
       [C.warningTint, C.warningFg, C.warningBorder], 'по всем периодам'],
      ['активных кампаний', String(activeCount), 'РК', '', null, 'все запущены'],
    ] : []),
    // Считается по ВЫБРАННОЙ площадке: иначе выбор меняет список, а шапка продолжает
    // говорить про всё сразу — и два числа на экране противоречат друг другу.
    ['требует решения', String(shownTasks.length), 'запросов',
     late ? `${late} просрочен${late === 1 ? '' : 'о'}` : '',
     [C.dangerTint, C.danger, C.dangerBorder], 'креативы, пролонгации, сверки'],
  ]

  return (
    <>
      <Head>
        <title>
          {pageTitle((NAV.find(n => n.key === active) || {}).label || 'Дашборд')}
        </title>
      </Head>
      <Header profile={profile} name={name}
        nav={NAV.map(n => (n.key === 'queue'
          ? { ...n, badge: shownTasks.length } : n))}
        active={active} onNav={setActive} count={(dash?.publishers || []).length}
        onExit={onSignOut} />

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
              {/* Что за площадками закреплено. Чипы те же, что у нас на экране
                  настройки кабинетов: это одна и та же запись, а не вторая её версия.
                  Поверхности внутри чипа, а не отдельными — у площадки это одна услуга
                  на двух экранах, и два чипа читались бы как две разные. */}
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1,
                paddingLeft: 18 }}>
                {shownServices.map(sv => (
                  <span key={sv.name} style={{ ...chip(C.accentTint, C.accent,
                    C.accentBorder), display: 'inline-flex', alignItems: 'center',
                    gap: 5 }}>
                    {sv.name}
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em',
                      textTransform: 'uppercase', opacity: .75 }}>
                      {sv.surfaces.join(' · ')}
                    </span>
                  </span>
                ))}
              </span>
              {/* Выбор площадки стоит В ШАПКЕ, а не над очередью: он сужает ВЕСЬ лист —
                  показатели, очередь, обработанное и деньги. Над очередью он говорил бы,
                  что относится только к ней, а таблицы ниже продолжали бы показывать всё.
                  У кабинета с одной площадкой элемента нет вовсе: выбирать не из чего, а
                  пустой выпадающий список читается как недоступная функция. */}
              {pubOptions.length > 1 && (
                <select value={pubFilter}
                  onChange={e => setPubFilter(e.target.value ? Number(e.target.value) : '')}
                  style={{ ...soft(C.secondary, C.border), padding: '8px 12px',
                    fontSize: 13, cursor: 'pointer' }}>
                  <option value="">Все площадки · {allTasks.length}</option>
                  {pubOptions.map(o => (
                    <option key={o.id} value={o.id}>
                      {o.name} · {allTasks.filter(t => t.publisher_id === o.id).length}
                    </option>
                  ))}
                </select>
              )}
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
              {shownTasks.map(t => (
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
                  gridTemplateColumns: '118px minmax(140px,0.8fr) minmax(120px,0.7fr) minmax(150px,0.85fr) minmax(260px,2fr)',
                  gap: 12, padding: '0 4px 8px', borderBottom: `1px solid ${C.border}`, ...CAP }}>
                  <span>Статус</span><span>Кампания</span><span>Площадка</span>
                  <span>Креатив</span><span>Комментарий</span>
                </div>
                {done.map(d => (
                  <div key={d.task_id} style={{ display: 'grid',
                    gridTemplateColumns: '118px minmax(140px,0.8fr) minmax(120px,0.7fr) minmax(150px,0.85fr) minmax(260px,2fr)',
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
                    <span style={{ fontSize: 12.5, color: C.secondary }}>{d.publisher || '—'}</span>
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

          {SHOW_MONEY && (
            <Campaigns period={period} sites={dash?.publishers || []}
              publisher={pubOptions.find(o => o.id === pubFilter)?.name || ''} />
          )}
        </div>

        {/* правая колонка */}
        <div style={{ width: 280, flex: '0 0 280px', display: 'flex',
          flexDirection: 'column', gap: 14 }}>

          <Side title="бот в телеграме" accent>
            <div style={{ fontSize: 12.5, color: C.secondary, lineHeight: 1.5 }}>
              Уведомления о новых креативах, дедлайнах и сверке.
            </div>
            <span style={{ ...chip(C.subtle, C.muted, C.border) }}>не подключён</span>
            {/* Шестерёнка стоит РЯДОМ С КНОПКОЙ, а не в заголовке блока: настройка
                относится к тому, что бот присылает, и читается вместе с ним одной
                строкой. Кнопка подключения пока выключена — бота нет, — а настройка
                работает уже сейчас: набор уведомлений существует независимо от канала. */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button style={{ ...btn(false), flex: 1 }} disabled
                title="Отдельный бот кабинета ещё не поднят">Подключить бота</button>
              <button title="Что присылать" onClick={() => setNotifyOpen(true)}
                style={{ width: 34, height: 34, borderRadius: 9, padding: 0, flex: '0 0 34px',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', background: C.card,
                  border: `1px solid ${C.border}`, color: C.secondary }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </button>
            </div>
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
                Контакты появятся, когда мы их назначим.
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
            {/* Доп. каналы связи — последним: это запасной путь на случай блокировок,
                а не основной. Текст выводится КАК ТЕКСТ, ссылки в нём не разбираются:
                поле свободное, и превращать чужой ввод в разметку во внешнем контуре
                значит открывать ровно тот вектор, ради которого схемы ссылок в этом
                проекте проверяются вручную. */}
            {!!profile?.messenger_note && (
              <div style={{ borderTop: `1px solid ${C.row}`, paddingTop: 10,
                display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>доп. каналы связи</span>
                <span style={{ fontSize: 12, color: C.secondary, lineHeight: 1.5,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {profile.messenger_note}
                </span>
              </div>
            )}
          </Side>

          <Side title="договора">
            {/* Одна плашка на юрлицо — как и просили. Список сужается выбором площадки
                наверху: у служебной учётки юрлиц под сорок, и без выбора виджет был бы
                справочником, а не карточкой. */}
            {shownLegals.slice(0, legalsAll ? undefined : 4).map(l => (
              <LegalCard key={`${l.publisher_id}-${l.counterparty_id}`} legal={l} />
            ))}
            {shownLegals.length > 4 && !legalsAll && (
              <button style={{ ...soft(C.secondary, C.border), fontSize: 11.5 }}
                onClick={() => setLegalsAll(true)}>
                Показать все {shownLegals.length}
              </button>
            )}
            {!shownLegals.length && (
              <span style={{ fontSize: 12, color: C.faint }}>
                Юрлицо не заведено — напишите нам в рабочий чат.
              </span>
            )}
            {/* Не список, а строка. Раньше здесь висели два десятка одинаковых
                номеров: договор заведён на КАЖДОЙ площадке отдельно, а список показывал
                их без площадки — и выглядел как размноженный дубль. Теперь такие
                договоры разложены по юрлицу своей же площадки, а сюда попадает только
                то, что разложить не по чему. */}
            {!!unassigned && (
              <span style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.45 }}>
                Ещё {unassigned}{' '}
                {unassigned === 1 ? 'договор' : unassigned < 5 ? 'договора' : 'договоров'}
                {' '}у нас не привязан{unassigned === 1 ? '' : 'ы'} к юрлицу — напишите в
                рабочий чат, если нужны реквизиты по ним.
              </span>
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

      {/* Модалка рисуется порталом в `body` из самого компонента, поэтому место вызова
          здесь не влияет на её положение — но держим её рядом с остальными окнами. */}
      {notifyOpen && (
        <NotifySwitches onErr={setErr} onClose={() => setNotifyOpen(false)} />
      )}
    </>
  )
}
