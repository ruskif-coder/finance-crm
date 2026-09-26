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
import dynamic from 'next/dynamic'
import api, { auth, signOut, TOKEN_KEY } from '../lib/http'
import { PreviewModal } from '../lib/preview'
import { overlayClose } from '../lib/overlay'
import { Header, MobileHeader, Side, Demo, WRAP, Toast } from './Shell'
import ActiveCampaigns, { billing } from './ActiveCampaigns'
import CampaignsScreen from './CampaignsScreen'
import CampaignsMobile from './CampaignsMobile'
import useIsMobile from '../lib/useIsMobile'
import Sheet, { SHEET_BTN } from '../lib/sheet'
import { C, CAP, KPI_SIZE, MONO, UI, arrowBtn, btn, btnSm, card, chip, dm, inp, num, periodLabel,
  rub, soft }
  from '../lib/ui'
import { daysTo, startNote, urgency } from '../lib/urgency'
import { NEED, PAY_STATE, RK_STATE, SERVICE_DOT,
  SHOW_MONEY, billBlocked, blocking, camp, inBill, inPace, sum, useDemoNow } from '../lib/demo'
import safeHref from '../lib/safeHref'
import { downloadFile } from '../lib/download'
import { guideSeen, markGuideSeen } from './guide/seen'

// Руководство — отдельным чанком: слайды нужны только тому, кто открыл окно.
const Guide = dynamic(() => import('./guide/Guide'), { ssr: false, loading: () => null })




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
  const mobile = useIsMobile()

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

  const download = () => downloadFile(`/tasks/${t.task_id}/files/${preview.id}`, preview.name)
  const closeAsk = () => { setAsk(null); setReason(''); setFiles([]) }

  if (mobile) {
    return (
      <TaskMobile t={t} late={late} soon={soon} stLabel={stLabel} toStart={toStart}
        stTone={[stChipBg, stChipFg, stChipBd]} today={today} preview={preview}
        canApprove={canApprove} busy={busy} urlPending={urlPending}
        url={url} setUrl={setUrl} sendUrl={sendUrl} onErr={onErr}
        show={show} setShow={setShow} download={download}
        ask={ask} setAsk={setAsk} closeAsk={closeAsk} reason={reason} setReason={setReason}
        reasons={reasons} files={files} addFiles={addFiles} upBusy={upBusy} answer={answer} />
    )
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
          <a href={safeHref(t.advertiser_url)} target="_blank" rel="noreferrer"
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
        {/* Письмо о правах на изображения — рядом с креативом, а не в отдельном разделе:
            смотрят его, отвечая по этому же материалу. Показываем только когда оно
            есть — пустая кнопка «письма нет» заставляла бы гадать, спросить его или так
            и задумано. */}
        {!!t.rights_letter && (
          <button onClick={() => downloadFile(`/tasks/${t.task_id}/rights-letter`, t.rights_letter.name)}
            style={{ ...btnSm(false), display: 'inline-flex',
              alignItems: 'center', gap: 6 }} title={t.rights_letter.name}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.4 11.05 12.25 20.2a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 1 1 4.95 4.95l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
            письмо о правах
          </button>
        )}
        <button style={btnSm(false)} disabled={!preview?.preview_url}
          onClick={() => setShow(true)}>предпросмотр</button>
        {/* Скачать баннер — пиктограммой рядом с предпросмотром (владелец 25.09.2026):
            тот же баннер, что открывает предпросмотр, но ИСХОДНЫЙ — без наших вставок
            под DSP. Отдаёт ядро через кабинет, не песочница: она открыта без входа. */}
        {!!preview?.id && (
          <button onClick={() => downloadFile(`/tasks/${t.task_id}/files/${preview.id}`, preview.name)}
            title={`Скачать ${preview.name || 'креатив'}`} aria-label="Скачать креатив"
            style={{ ...btnSm(false), display: 'inline-flex',
              alignItems: 'center', justifyContent: 'center', padding: '5px 8px' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <path d="M7 10l5 5 5-5M12 15V3" />
            </svg>
          </button>
        )}
        {/* Три исхода, слева направо от мягкого к необратимому. Смысл несёт текст, а
            заливка — только у главного действия: несколько цветных плашек подряд
            превращают строку в светофор. */}
        {canApprove && !ask && (
          <>
            {/* Разделитель между «посмотреть» и «решить» (владелец 07.09.2026). Слева
                кнопки, которые ничего не меняют, справа — вердикт, который необратим.
                Стоит ВНУТРИ этого условия, а не перед ним: у учётки без права ответа
                кнопок справа нет, и полоса висела бы в воздухе, отделяя пустоту. */}
            <span style={{ width: 1, height: 18, background: C.inner, flex: '0 0 1px',
                           margin: '0 2px' }} />
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
          onDownload={preview?.id ? download : undefined}
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
          {/* Посадочную присылает тот, у кого есть право ответа (владелец 24.09.2026):
              «только просмотр» видит запрос, но поле ему не даётся — сервер всё равно
              откажет, и поле, которое нельзя сохранить, хуже его отсутствия. */}
          {canApprove ? (
            <>
              <input style={{ ...inp, flex: 1, minWidth: 260, background: C.card,
                padding: '6px 11px', fontFamily: MONO, fontSize: 12 }}
                title={t.url_request_text || undefined}
                placeholder={longAsk ? 'https://…' : (t.url_request_text
                  || 'пришлите ссылку на посадочную — UTM подставим сами')}
                value={url} onChange={e => setUrl(e.target.value)} />
              <button style={{ ...btn(true), padding: '6px 14px' }}
                disabled={busy || !url.trim()} onClick={sendUrl}>Собрать</button>
            </>
          ) : (
            <span style={{ fontSize: 11.5, color: C.faint }}>
              ссылку присылает коллега с правом ответа
            </span>
          )}
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

/* ─────────────────── карточка задания · телефон ─────────────────── */

/* Раскладка по хендоффу «моб версия кп» (п. 2): сверху вниз — чья кампания и статус,
   плашка старта, строка креатива, материалы в ряд, запрос посадочной, ТТ, решение.
   Состояние и все действия живут в `Task`: здесь только раскладка, иначе ответ по
   креативу считался бы в двух местах и однажды разошёлся. */
const M_BTN = { minHeight: 40, borderRadius: 10, fontSize: 13, display: 'inline-flex',
  alignItems: 'center', justifyContent: 'center', gap: 6 }

function TaskMobile({ t, late, soon, stLabel, toStart, stTone, today, preview, canApprove,
  busy, urlPending, url, setUrl, sendUrl, onErr, show, setShow, download, ask, setAsk,
  closeAsk, reason, setReason, reasons, files, addFiles, upBusy, answer }) {
  const [stBg, stFg, stBd] = stTone
  return (
    <div className="rise" style={{ padding: '13px 14px', borderRadius: 16,
      background: late ? C.dangerBg : soon ? C.warnBg : C.card,
      border: `1px solid ${late ? C.dangerBorder : soon ? C.warningBorder : C.border}`,
      display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* 1 — чья кампания; статус справа */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, marginTop: 7, flex: '0 0 7px',
          background: late ? C.danger : soon ? C.warning : C.accent }} />
        <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>
            {[t.advertiser, t.brand].filter(Boolean).join(' · ') || 'Креатив'}
          </span>
          <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ ...CAP, marginBottom: 0 }}>
              {[t.service, t.surface].filter(Boolean).join(' · ')}
            </span>
            {!!t.publisher && (
              <span style={{ ...chip(C.subtle, C.secondary, C.border), fontSize: 10.5 }}>
                {t.publisher}
              </span>
            )}
          </span>
        </span>
        <span style={{ ...chip(stBg, stFg, stBd), flex: '0 0 auto' }}>{stLabel}</span>
      </div>

      {/* 2 — старт РК: дата и сколько до неё */}
      <div style={{ ...chip(stBg, stFg, stBd), fontFamily: MONO, gap: 8,
        justifyContent: 'flex-start', padding: '7px 10px', fontSize: 11.5 }}>
        <span style={{ color: C.muted }}>старт рк</span>
        <b>{dm(t.period_from)}</b>
        {toStart !== null && (
          <span style={{ borderLeft: `1px solid ${stBd}`, paddingLeft: 8 }}>
            {startNote(t.period_from, today)}
          </span>
        )}
      </div>

      {/* 3 — креатив */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, flex: '0 0 30px',
          background: C.subtle, border: `1px solid ${C.border}`, color: C.muted,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" />
          </svg>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            Креатив №{t.creative_no}{t.creative_title ? ` — ${t.creative_title}` : ''}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint }}>
            {[t.form === 'BannerHtml5' ? 'banner html5' : t.form, preview?.size,
              `ждёт ${t.waiting_days} дн.`,
              late ? 'старт уже прошёл · эскалация менеджеру' : null,
            ].filter(Boolean).join(' · ')}
          </span>
        </span>
      </div>

      {/* 4 — материалы в ряд: посадочная · предпросмотр · скачать; письмо о правах ниже */}
      <div style={{ display: 'flex', gap: 8 }}>
        {t.url_state === 'есть' && (
          <a href={safeHref(t.advertiser_url)} target="_blank" rel="noreferrer"
            style={{ ...btn(false), ...M_BTN, flex: '1 1 0', textDecoration: 'none' }}>
            посадочная
          </a>
        )}
        <button style={{ ...btn(false), ...M_BTN, flex: '1 1 0' }}
          disabled={!preview?.preview_url} onClick={() => setShow(true)}>предпросмотр</button>
        {!!preview?.id && (
          <button onClick={download} aria-label="Скачать креатив"
            style={{ ...btn(false), ...M_BTN, width: 40, flex: '0 0 40px', padding: 0 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4v10" /><path d="M8 11l4 4 4-4" /><path d="M5 19h14" />
            </svg>
          </button>
        )}
      </div>
      {!!t.rights_letter && (
        <button onClick={() => downloadFile(`/tasks/${t.task_id}/rights-letter`, t.rights_letter.name)}
          style={{ ...btn(false), ...M_BTN }}>
          письмо о правах
        </button>
      )}

      {/* 5 — запрос посадочной */}
      {urlPending && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px',
          background: C.accentTint, border: `1px solid ${C.accentBorder}`, borderRadius: 11 }}>
          <span style={{ ...CAP, marginBottom: 0, color: C.accent }}>
            запрос на сбор посадочной · без неё согласовать нельзя
          </span>
          {!!t.url_request_text && (
            <span style={{ fontSize: 12.5, color: C.secondary, whiteSpace: 'pre-line',
              lineHeight: 1.45 }}>{t.url_request_text}</span>
          )}
          {canApprove ? (
            <>
              <input style={{ ...inp, background: C.card, minHeight: 40, fontFamily: MONO,
                fontSize: 13 }} inputMode="url" placeholder="https://…"
                value={url} onChange={e => setUrl(e.target.value)} />
              <button style={{ ...btn(true), ...M_BTN }} disabled={busy || !url.trim()}
                onClick={sendUrl}>Собрать</button>
            </>
          ) : (
            <span style={{ fontSize: 12, color: C.faint }}>
              ссылку присылает коллега с правом ответа
            </span>
          )}
        </div>
      )}

      {/* 6 — ТТ */}
      {!!t.tech_requirements && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 9,
          borderTop: `1px solid ${C.row}` }}>
          <span style={{ ...CAP, marginBottom: 0 }}>тт</span>
          <span style={{ fontSize: 12.5, color: C.secondary }}>{t.tech_requirements}</span>
        </div>
      )}

      {/* 7 — решение. «Согласовать» без посадочной не заперто кнопкой, а объясняет себя:
          на телефоне подсказки по наведению нет, и серая кнопка молчала бы о причине. */}
      {canApprove ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button disabled={busy}
            onClick={() => (urlPending
              ? onErr('Без посадочной согласовать нельзя — пришлите ссылку в блоке выше')
              : answer('ок'))}
            style={{ ...btn(true), ...M_BTN, minHeight: 44, fontSize: 14,
              background: urlPending ? C.subtle : C.incomeFg,
              color: urlPending ? C.faint : C.onFill,
              border: `1px solid ${urlPending ? C.border : 'transparent'}`,
              cursor: urlPending ? 'not-allowed' : 'pointer' }}>
            ✓ Согласовать
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{ ...soft(C.warningFg, C.warningBorder), ...M_BTN, flex: 1 }}
              disabled={busy} onClick={() => setAsk('на доработку')}>Доработать</button>
            <button style={{ ...soft(C.danger, C.dangerBorder), ...M_BTN, flex: 1 }}
              disabled={busy} onClick={() => setAsk('отказ')}>Отказать</button>
          </div>
        </div>
      ) : (
        <span style={{ fontSize: 12, color: C.faint }}>у вас доступ только на просмотр</span>
      )}

      {show && (
        <PreviewModal file={preview} onClose={() => setShow(false)}
          onDownload={preview?.id ? download : undefined}
          title={[t.brand, t.creative_title].filter(Boolean).join(' · ')} />
      )}

      {/* Доработка и отказ — только с комментарием, в нижнем листе. */}
      {!!ask && (
        <Sheet title={ask === 'отказ' ? 'Отказать в размещении' : 'На доработку'}
          meta={[t.brand, t.publisher].filter(Boolean).join(' · ')} onClose={closeAsk}
          footer={(
            <>
              <button style={{ ...btn(false), ...SHEET_BTN }} onClick={closeAsk}>Отмена</button>
              <button style={{ ...btn(true), ...(ask === 'отказ' ? { background: C.danger } : {}),
                ...SHEET_BTN, flex: 1 }}
                disabled={busy || !reason.trim()} onClick={() => answer(ask, reason)}>
                {ask === 'отказ' ? 'Отказать' : 'Отправить на доработку'}
              </button>
            </>
          )}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ fontSize: 12.5, color: C.secondary }}>
              {ask === 'отказ'
                ? 'Отказ закрывает кампанию на этой площадке — она уйдёт в архив. Новая версия баннера сюда уже не придёт.'
                : 'Комментарий уйдёт агентству и появится в «Обработано за неделю».'}
            </span>
            {!!(reasons?.[ask] || []).length && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(reasons?.[ask] || []).map(r => (
                  <span key={r} onClick={() => setReason(r)}
                    style={{ cursor: 'pointer', fontSize: 12.5, padding: '8px 12px',
                      borderRadius: 100, background: reason === r ? C.accent : C.card,
                      color: reason === r ? C.onFill : C.secondary,
                      border: `1px solid ${reason === r ? C.accent : C.border}` }}>{r}</span>
                ))}
              </div>
            )}
            <textarea style={{ ...inp, minHeight: 110, fontFamily: UI, fontSize: 14,
              resize: 'vertical' }} placeholder="Своими словами — что именно не так"
              value={reason} onChange={e => setReason(e.target.value)} />
            {ask !== 'отказ' && (
              <>
                {files.map(f => (
                  <span key={f.id} style={{ fontFamily: MONO, fontSize: 11,
                    color: C.secondary, wordBreak: 'break-all' }}>▣ {f.name}</span>
                ))}
                {files.length < 5 && (
                  <label style={{ ...btn(false), ...M_BTN,
                    cursor: upBusy ? 'progress' : 'pointer' }}>
                    {upBusy ? 'Грузим…' : 'Приложить скриншоты'}
                    <input type="file" multiple accept=".png,.jpg,.jpeg,.webp,.pdf"
                      style={{ display: 'none' }}
                      onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
                  </label>
                )}
              </>
            )}
          </div>
        </Sheet>
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

/* Тон строки ленты — он же цвет квадратного маркера. Значение приходит СО СТРОКОЙ
   журнала: оно задано событием в момент записи, и правка словаря не перекрашивает
   прошлое. */
const TONE_DOT = { ok: C.income, warn: C.warning, bad: C.danger, info: C.accent }

function Feed({ onErr }) {
  const [items, setItems] = useState(null)

  useEffect(() => {
    api.get('/feed', auth())
      .then(r => setItems(r.data.items || []))
      .catch(e => { setItems([]); onErr?.(e.response?.data?.detail || 'Лента недоступна') })
  }, [onErr])

  return (
    <Side title="лента событий">
      {!items && <span style={{ fontSize: 12, color: C.faint }}>загрузка…</span>}
      {items && !items.length && (
        /* Пустое говорится словами: пустая карточка читается как «не загрузилось». */
        <span style={{ fontSize: 12, color: C.faint }}>Событий пока нет.</span>
      )}
      <div style={{ display: 'flex', flexDirection: 'column',
        maxHeight: 290, overflowY: 'auto', paddingRight: 8 }}>
        {(items || []).map(it => (
          <div key={it.id} style={{ display: 'flex', gap: 9, padding: '9px 0',
            borderTop: `1px solid ${C.row}`, alignItems: 'flex-start' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, marginTop: 5,
              flex: '0 0 6px', background: TONE_DOT[it.tone] || C.faint }} />
            <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, gap: 2 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{it.label}</span>
              {it.subject && (
                <span style={{ fontSize: 11.5, color: C.secondary, textWrap: 'pretty' }}>
                  {it.subject}
                </span>
              )}
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.faint }}>
                {dm(it.at)} · {it.actor}
              </span>
            </span>
          </div>
        ))}
      </div>
    </Side>
  )
}

function TgBlock({ onErr, onChange }) {
  const [st, setSt] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.get('/telegram', auth())
    .then(r => { setSt(r.data); return r.data })
    .catch(() => { setSt({ configured: false }); return null }), [])

  useEffect(() => { load() }, [load])

  /* Пока ждём код — переспрашиваем состояние. Человек отвечает боту В ДРУГОМ ОКНЕ, и
     узнать об этом экран может только сам: события с той стороны к нам не приходят.
     Опрос идёт, ТОЛЬКО пока код висит, — иначе он бы шёл всегда и впустую. */
  const pending = st?.pending
  useEffect(() => {
    if (!pending) return undefined
    const t = setInterval(() => {
      load().then(d => { if (d?.linked) { clearInterval(t); onChange?.() } })
    }, 4000)
    return () => clearInterval(t)
  }, [pending, load, onChange])

  const call = async (fn) => {
    setBusy(true)
    try { setSt(await fn()); onChange?.() }
    catch (e) { onErr?.(e.response?.data?.detail || 'Не получилось') }
    setBusy(false)
  }
  const link = () => call(() => api.post('/telegram/link', {}, auth()).then(r => r.data))
  const unlink = () => call(() => api.delete('/telegram', auth()).then(r => r.data))

  return (
    <div style={{ border: `1px solid ${C.inner}`, borderRadius: 12, padding: '12px 13px',
      display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
        <span style={{ fontSize: 13.5, fontWeight: 700 }}>Бот в телеграме</span>
        <span style={{ ...CAP, marginBottom: 0,
          color: st?.linked ? C.income : C.faint }}>
          {st?.linked ? 'подключён' : 'не подключён'}
        </span>
      </div>
      <div style={{ fontSize: 12, color: C.secondary, lineHeight: 1.5 }}>
        Событие приходит сразу — креатив на согласование, дедлайн, сверка.
      </div>

      {!st && <span style={{ fontSize: 12, color: C.faint }}>загрузка…</span>}

      {/* Бот не настроен у НАС. Говорим прямо, а не «подключите»: кнопка, которая не
          может сработать, тратит время каждый раз заново. */}
      {st && !st.configured && (
        <span style={{ ...chip(C.subtle, C.muted, C.border) }}>пока недоступен</span>
      )}

      {st?.configured && st.linked && (
        <button style={btn(false)} disabled={busy} onClick={unlink}>Отключить</button>
      )}

      {st?.configured && !st.linked && !st.pending && (
        <button style={btn(true)} disabled={busy} onClick={link}>Подключить бота</button>
      )}

      {st?.configured && !st.linked && st.pending && (
        <>
          <div style={{ fontSize: 11.5, color: C.secondary, lineHeight: 1.45 }}>
            Откройте бота и нажмите «Начать». Если чат с ним уже открывали, кнопки не
            будет — отправьте ему этот код сообщением.
          </div>
          <div style={{ ...inp, fontFamily: MONO, fontSize: 16, letterSpacing: 2,
            textAlign: 'center', padding: '9px 0', color: C.text }}>{st.pending.code}</div>
          {/* Диплинк, а не имя бота текстом: по нему Телеграм сам подставит код в
              кнопку «Начать», и вводить его руками не придётся. */}
          {st.pending.link && (
            <a href={st.pending.link} target="_blank" rel="noreferrer"
              style={{ ...btn(true), textAlign: 'center', textDecoration: 'none' }}>
              Открыть бота
            </a>
          )}
          <button style={btn(false)} disabled={busy} onClick={link}>Другой код</button>
        </>
      )}
    </div>
  )
}

/* ── Матрица «событие × способ доставки» ────────────────────────────────────

   ТРИ СПОСОБА, и два из них — почта: письмом сразу или в утренней пачке. Выбор делается
   У КАЖДОГО СОБЫТИЯ (владелец 15.09.2026): про креатив человек хочет знать немедленно, а
   про старт кампании прочтёт утром — общего ответа тут нет.

   ПАНЕЛИ СРЕДИ НИХ НЕТ. Первая редакция экрана рисовала её колонкой «всегда», но у
   паблишера панели уведомлений не существует: лента кабинета — журнал наших с ним
   действий, а не канал доставки, и выключателя у неё нет по той же причине, по какой
   его нет у истории переписки.

   Колонка выключенного канала гаснет: галочка в ней правдива (решение сохранится), но
   сегодня ничего не доставляет, и показывать её наравне с рабочей значит обещать
   доставку, которой не будет. */
const CHANNELS = [
  { key: 'бот', label: 'Бот', on: (d) => !!d?.bot?.linked },
  { key: 'почта', label: 'Почта', note: 'срочное', on: (d) => !!d?.mail?.enabled },
  { key: 'дайджест', label: 'Дайджест', on: (d) => !!d?.mail?.enabled },
]

function Cell({ on, locked, dim, onClick, big }) {
  /* Галочка, а не рубильник: здесь вопрос «выбрано ли», а рубильник отвечает на вопрос
     «включено ли» — им сделаны каналы целиком, строкой выше. */
  return (
    <span onClick={locked ? undefined : onClick}
      style={{ width: big ? 34 : 20, height: big ? 34 : 20, borderRadius: big ? 9 : 6,
        display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center', margin: '0 auto',
        cursor: locked ? 'default' : 'pointer',
        opacity: dim ? 0.45 : 1,
        background: on ? (locked ? C.accentTint : C.accent) : C.card,
        border: `1px solid ${on ? (locked ? C.accentBorder : C.accent) : C.border}`,
        transition: 'background 120ms ease' }}>
      {on && (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke={locked ? C.accent : C.onFill} strokeWidth="3.4"
          strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
      )}
    </span>
  )
}

function EventMatrix({ data, onSave, onReset, onClose, busy }) {
  const kinds = data?.kinds || []
  const chOn = Object.fromEntries(CHANNELS.map(c => [c.key, c.on(data)]))
  // Телефон — нижний лист во всю ширину (хендофф «моб версия кп», п. 5).
  const mobile = useIsMobile()

  return createPortal(
    <div style={{ position: 'fixed', inset: 0, background: 'var(--overlay)', zIndex: 10000,
      display: 'flex', alignItems: mobile ? 'flex-end' : 'center', justifyContent: 'center',
      padding: mobile ? 0 : 20 }}
      {...overlayClose(onClose)}>
      <div style={{ ...card, width: mobile ? '100%' : 'min(620px, 96vw)',
        maxHeight: mobile ? '90vh' : '88vh', overflowY: 'auto',
        borderRadius: mobile ? '18px 18px 0 0' : card.borderRadius,
        padding: mobile ? '16px 14px calc(16px + env(safe-area-inset-bottom))' : '20px 22px',
        fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Какие события присылать</span>
          <span style={{ flex: 1 }} />
          <button style={btnSm(false)} onClick={onClose}>✕</button>
        </div>
        <div style={{ ...CAP, marginTop: 4, marginBottom: 14 }}>
          {kinds.length} {kinds.length === 1 ? 'событие' : 'события'} · бот и почта
        </div>

        {!kinds.length && (
          /* Пустое говорится словами. Каталог показывает только ПОСТРОЕННЫЕ виды, и
             пустая таблица здесь — честное «пока ничего», а не сбой загрузки. */
          <div style={{ fontSize: 12.5, color: C.faint, padding: '18px 0' }}>
            Пока нечего настраивать — включённых видов уведомлений нет.
          </div>
        )}

        {!!kinds.length && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ ...CAP, marginBottom: 0, textAlign: 'left', padding: '0 0 8px' }}>
                  Событие
                </th>
                {CHANNELS.map(c => (
                  <th key={c.key} style={{ width: mobile ? 62 : 84, padding: '0 0 8px' }}>
                    <div style={{ fontSize: 12, fontWeight: 700,
                      color: chOn[c.key] ? C.text : C.faint }}>{c.label}</div>
                    <div style={{ ...CAP, marginBottom: 0,
                      color: chOn[c.key] ? C.income : C.faint }}>
                      {/* У почты подпись говорит не про состояние канала, а про СПОСОБ:
                          две её колонки различаются только этим словом. */}
                      {c.note || (chOn[c.key] ? 'включён' : 'выключен')}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {kinds.map(k => (
                <tr key={k.key} style={{ borderTop: `1px solid ${C.row}` }}>
                  <td style={{ padding: '10px 10px 10px 0' }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{k.label}</div>
                    <div style={{ ...CAP, marginBottom: 0,
                      color: k.can_mute ? C.faint : C.warningFg }}>
                      {k.can_mute ? 'по выбору' : 'обязательное'}
                    </div>
                    {/* Срочность объясняется СЛОВАМИ рядом с событием, а не молчанием:
                        иначе выбранный дайджест выглядел бы неработающим. */}
                    {k.urgent && (
                      <div style={{ ...CAP, marginBottom: 0, color: C.warningFg }}>
                        письмом сразу, мимо дайджеста
                      </div>
                    )}
                  </td>
                  {CHANNELS.map(c => (
                    <td key={c.key} style={{ textAlign: 'center', padding: '10px 0' }}>
                      {/* Срочный вид в пачку не уводится — «наше сразу не понижается».
                          Клетка дайджеста у него не нажимается, а причина написана
                          словами в строке слева, а не оставлена в виде молчания. */}
                      <Cell on={!!k[c.key]} big={mobile}
                        locked={busy || !k.can_mute || (c.key === 'дайджест' && k.urgent)}
                        dim={!chOn[c.key]}
                        onClick={() => onSave(k.key, c.key, !k[c.key])} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.5, margin: '14px 0 16px' }}>
          Почта приходит либо сразу, либо дайджестом — одно из двух. Обязательные
          события снять нельзя. Колонка выключенного канала гаснет: включить его можно в
          блоке уведомлений.
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button style={{ ...btn(true), ...(mobile ? { ...SHEET_BTN, flex: 1 } : {}) }}
            onClick={onClose}>Готово</button>
          <button style={{ ...btn(false), ...(mobile ? SHEET_BTN : {}) }} disabled={busy}
            onClick={onReset}>
            Вернуть по умолчанию
          </button>
        </div>
      </div>
    </div>,
    document.body)
}

function MailCard({ data, onMail, busy }) {
  const m = data?.mail || {}
  // Тумблер на телефоне — 44×26 (хендофф «моб версия кп», п. 4): 34×19 пальцем не попасть.
  const big = useIsMobile()
  const [tw, th, knob] = big ? [44, 26, 20] : [34, 19, 13]

  return (
    <div style={{ border: `1px solid ${C.inner}`, borderRadius: 12, padding: '12px 13px',
      display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
        <span style={{ fontSize: 13.5, fontWeight: 700 }}>Почта</span>
        <span style={{ ...CAP, marginBottom: 0, color: m.enabled ? C.income : C.faint }}>
          {m.enabled ? 'включено' : 'выключено'}
        </span>
        <span style={{ flex: 1 }} />
        {/* Рубильник канала целиком. Недоступен, когда управлять нечем: у учётки нет
            связанного контакта или в карточке нет адреса — тогда и включать некуда. */}
        <span onClick={() => (m.address && !busy) ? onMail({ enabled: !m.enabled }) : null}
          title={m.why || ''}
          style={{ width: tw, height: th, borderRadius: 999, position: 'relative',
            flex: `0 0 ${tw}px`, cursor: m.address ? 'pointer' : 'not-allowed',
            opacity: m.address ? 1 : 0.5,
            background: m.enabled ? C.income : C.subtle,
            border: `1px solid ${m.enabled ? C.income : C.border}`,
            transition: 'background 140ms ease' }}>
          <span style={{ position: 'absolute', top: 2, left: m.enabled ? tw - knob - 4 : 2,
            width: knob, height: knob, borderRadius: 999,
            background: m.enabled ? C.onFill : C.faint, transition: 'left 140ms ease' }} />
        </span>
      </div>

      <div style={{ fontSize: 12, color: C.secondary, lineHeight: 1.5 }}>
        Адрес берётся из вашей карточки контакта. Что приходит сразу, а что
        дайджестом — в списке событий.
      </div>

      {/* Адрес ПОКАЗЫВАЕТСЯ, но не правится: он же адрес, по которому мы пишем площадке
          по всем делам, и менять его из кабинета — отдельное решение с проверкой. */}
      <div style={{ ...inp, fontSize: 12, color: m.address ? C.text : C.faint,
        background: C.subtle, cursor: 'default' }}>
        {m.address || m.why || 'адреса нет'}
      </div>

    </div>
  )
}

/** Расчёт биллинга — ТОТ ЖЕ, что внутри компонента хендоффа.

    Импортируется из него, а не повторяется здесь: «факт ÷ 1000 × CPM» в двух местах
    разойдётся на первом же округлении, и шапка начнёт спорить с итогом таблицы под ней.
    Это прямое требование ТЗ: «литеральных значений в KPI быть не должно — расхождение с
    итогом таблицы ловится сразу». */
function campaignKpi(rows) {
  const withFact = rows.filter(c => c.fact)
  return {
    // Расчётный биллинг — по строкам С ФАКТОМ. Размещение без открутки денег не
    // приносит, и включать его нулём значило бы делать вид, что оно посчитано.
    billing: withFact.reduce((a, c) => a + billing(c.fact, c.cpm), 0),
    // Завершённые: флайт закончился, дальше сверка за период. Поле названо `awaiting`
    // исторически — переименовывать не стал, чтобы не плодить правку ради слова; на
    // экране подпись честная.
    awaiting: rows.filter(c => c.status === 'завершён')
      .reduce((a, c) => a + (c.fact ? billing(c.fact, c.cpm) : 0), 0),
    live: rows.filter(c => c.status === 'в размещении').length,
    soon: rows.filter(c => c.status === 'ждёт старта').length,
  }
}

function NotifyBlock({ onErr }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)

  const load = useCallback(() => api.get('/notify-settings', auth())
    .then(r => { setData(r.data); return r.data })
    .catch(e => { onErr?.(e.response?.data?.detail || 'Настройки недоступны'); return null }),
  [onErr])

  useEffect(() => { load() }, [load])

  const call = async (fn) => {
    setBusy(true)
    try { setData((await fn()).data) }
    catch (e) { onErr?.(e.response?.data?.detail || 'Не удалось сохранить') }
    setBusy(false)
  }
  const saveCell = (kind, channel, enabled) =>
    call(() => api.put('/notify-settings', { kind, channel, enabled }, auth()))
  const reset = () => call(() => api.delete('/notify-settings', auth()))
  const saveMail = (patch) => call(() => api.put('/mail-settings', patch, auth()))

  const m = data?.mail || {}
  const on = (m.enabled ? 1 : 0) + (data?.bot?.linked ? 1 : 0)
  /* Час пачки площадка НЕ ВЫБИРАЕТ (владелец 15.09.2026) — его задаём мы. Но знать,
     когда она придёт, полезно, поэтому час остаётся ФАКТОМ в шапке и исчез только как
     настройка: бездействующий выбор читается как поломка, а молчание про время — как
     «неизвестно когда». */
  const anyDigest = (data?.kinds || []).some(k => k['дайджест'])

  /* СЖАТЫЙ ВИД, КОГДА УЖЕ НАСТРОЕНО (владелец 15.09.2026).

     Пока каналы не подключены, блок — это дело: две карточки, кнопка, объяснения. Как
     только человек настроил доставку, всё это превращается в мебель на треть колонки, а
     нужен ему один ответ: «мне придёт и куда». Поэтому настроенный блок сворачивается в
     строку состояния, и разворачивается по нажатию.

     «Настроено» — это ХОТЯ БЫ ОДИН внешний канал: почта включена или бот привязан. Ноль
     каналов сворачивать нельзя — тогда блок молчал бы ровно о том, что человек ещё не
     сделал. */
  const set0 = !!m.enabled || !!data?.bot?.linked
  const [full, setFull] = useState(false)
  const short = set0 && !full

  /* Состояние почты ОДНОЙ ПОДПИСЬЮ. «Включено» само по себе не отвечает на вопрос,
     который человек задаёт этому блоку, — «когда мне придёт»; поэтому при выбранном
     дайджесте состояние называет час, а иначе говорит «сразу». */
  const digestNote = anyDigest
    ? `включено · дайджест в ${String(m.digest_hour || 9).padStart(2, '0')}:00`
    : 'включено · сразу'

  if (short) {
    return (
      <Side title="уведомления" accent>
        {/* Строка состояния — ТЕМ ЖЕ приёмом, что в развёрнутой карточке: имя канала
            жирным, состояние капсом цветом смысла (владелец 15.09.2026). Человек видит
            одно и то же написание в свёрнутом и развёрнутом виде, и ему не приходится
            заново разбираться, что перед ним.

            Цветом здесь говорит СОСТОЯНИЕ, а не текст: включено — зелёным, выключено —
            приглушённым. Для этого и заведено семейство «-fg», иначе на плашке получится
            2.81:1 контраста, как уже было на главной кнопке. */}
        {[['Почта', m.enabled, m.enabled ? digestNote : 'выключено'],
          ['Бот', !!data?.bot?.linked, data?.bot?.linked ? 'подключён' : 'не подключён']]
          .map(([label, on, note]) => (
            <div key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 8,
              minWidth: 0 }}>
              <span style={{ fontSize: 13.5, fontWeight: 700, flex: '0 0 auto' }}>
                {label}
              </span>
              <span style={{ ...CAP, marginBottom: 0, minWidth: 0, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                color: on ? C.income : C.faint }}>
                {note}
              </span>
            </div>
          ))}
        {/* «Настроить», а не «развернуть»: человек идёт сюда менять доставку, а не
            любоваться карточками. */}
        <button style={{ ...btnSm(false), width: '100%' }}
          onClick={() => setFull(true)}>Настроить</button>
      </Side>
    )
  }

  return (
    <Side title="уведомления" accent
      footer={(
        <button onClick={() => setOpen(true)} style={{ ...btn(false), width: '100%' }}>
          Какие события присылать
        </button>
      )}>
      {/* Шапка отвечает на вопрос «а что у меня сейчас» одной строкой — иначе за ответом
          надо открывать модалку, то есть шапка бесполезна. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ ...CAP, marginBottom: 0 }}>
          {on} из 2 каналов
          {m.enabled && anyDigest
            ? ` · дайджест в ${String(m.digest_hour || 9).padStart(2, '0')}:00` : ''}
        </span>
        <span style={{ flex: 1 }} />
        {set0 && (
          <button style={btnSm(false)} onClick={() => setFull(false)}>Свернуть</button>
        )}
      </div>

      <TgBlock onErr={onErr} onChange={load} />
      <MailCard data={data} onMail={saveMail} busy={busy} />

      {open && (
        <EventMatrix data={data} busy={busy} onSave={saveCell} onReset={reset}
          onClose={() => setOpen(false)} />
      )}
    </Side>
  )
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
  // Второй раздел (владелец 15.09.2026). На дашборде — только то, что в работе; здесь
  // вся история по месяцам, включая сверенные периоды.
  { key: 'campaigns', label: 'Кампании' },
]
/* На телефоне правая колонка десктопа уходит в третью вкладку (хендофф «моб версия кп»,
   п. 1): уведомления, команда, договоры. Лента событий остаётся на дашборде. */
const NAV_MOBILE = [...NAV, { key: 'contact', label: 'Связь' }]

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
  // Руководство открывается само ОДИН раз — при первом входе в этом браузере (владелец,
  // 24.09.2026); дальше — пиктограммой «i» в шапке.
  const [guide, setGuide] = useState(false)
  useEffect(() => { if (!guideSeen()) setGuide(true) }, [])
  const closeGuide = useCallback(() => { markGuideSeen(); setGuide(false) }, [])
  /* Кампании грузятся ЗДЕСЬ, а не внутри блока: из этого же массива считаются плитки
     шапки. Держи их два компонента по отдельности — шапка и таблица однажды показали бы
     разные деньги по одним размещениям, и спорить с экраном пришлось бы человеку. */
  const [camps, setCamps] = useState(null)
  const [active, setActive] = useState('queue')
  const [openDone, setOpenDone] = useState(false)
  // Пусто = все площадки. Выбор живёт на СТРАНИЦЕ, а не в каждом списке: от него
  // пересчитывается и очередь, и обработанное, и счётчик в шапке.
  const [pubFilter, setPubFilter] = useState('')
  const [legalsAll, setLegalsAll] = useState(false)
  const [bulk, setBulk] = useState(false)
  /* Сегодня берётся один раз после монтирования: `new Date()` при рендере даёт на
     сервере и клиенте разные значения на границе суток и ошибку гидрации. */
  const [today, setToday] = useState(null)
  const mobile = useIsMobile()

  /* Кампании грузятся ОТДЕЛЬНЫМ вызовом и один раз: от периода и выбранной площадки
     они не зависят, а от общего `load` их отделяет то, что блок должен появиться даже
     если очередь заданий пуста.

     Первая редакция этой загрузки НЕ ПОПАЛА В ФАЙЛ: замена в скрипте правки была без
     проверки совпадения и промолчала. На экране это выглядело так, будто блок «пропал»,
     хотя ручка отдавала пятнадцать строк — `camps` просто навсегда оставался `null`.
     Отсюда правило, которое я нарушил: у каждой замены должна быть проверка. */
  const loadCamps = useCallback(() => {
    api.get('/campaigns', auth())
      .then(r => setCamps(r.data.campaigns || []))
      .catch(() => setCamps([]))     // блок и плитки просто не появятся
  }, [])
  useEffect(() => { loadCamps() }, [loadCamps])

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
       все» согласует не все и промолчит об этом.
       Берётся ВИДИМЫЙ список, а не весь: при выбранной площадке «все» означает «все,
       что на экране». До 23.09.2026 кнопка согласовывала и скрытые фильтром — необратимо
       и с числом в подтверждении, не совпадавшим с экраном (аудит, 7.H2). */
    const list = shownTasks.filter(t => t.url_state !== 'запрошена')
    const held = shownTasks.length - list.length
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

  // «Связь» есть только на телефоне: вкладка, оставшаяся после поворота экрана, на
  // десктопе означает дашборд, а не пустую страницу.
  const tab = !mobile && active === 'contact' ? 'queue' : active
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
  // ТРИ ДЕНЕЖНЫЕ ПЛИТКИ ВЕРНУЛИСЬ 15.09.2026 вместе с настоящими данными. Они уходили
  // не потому, что не нужны, а потому что считались из выдуманных строк `lib/demo.js`:
  // придуманные деньги на экране — хуже, чем их отсутствие. Теперь источник тот же
  // массив, что у таблицы ниже, и разойтись им нечем.
  // Плитки считаются по ВЫБРАННОЙ площадке, как и «требует решения» ниже: иначе выбор
  // меняет список, а деньги в шапке продолжают говорить про все сайты (аудит, 7.L5).
  const k = campaignKpi((camps || []).filter(c => !pubFilter || c.publisher_id === pubFilter))
  const KPI = [
    ...((camps && camps.length) ? [
      ['расчётный биллинг', rub(k.billing), '', '', null,
       'до НДС · по размещениям с фактом показов — суммы из таблицы ниже'],
      // НЕ «ожидает оплаты» (владелец 15.09.2026). За такой подписью стояло бы обещание,
      // которого система не держит: операций в контуре площадок нет, счетов и актов в
      // кабинете нет — их блок убрали 28.08 ровно по этой причине. Площадка прочитала бы
      // «мне поставлено в очередь на выплату», и спорить пришлось бы живому человеку.
      //
      // Число честно означает одно: сколько насчитано по размещениям, чей флайт
      // закончился. Дальше по нашему же порядку — сверка за период, и только потом
      // деньги. Так и подписано.
      ['закрыто за период', rub(k.awaiting), '', '',
       [C.warningTint, C.warningFg, C.warningBorder],
       'флайт завершён · сумма уточняется на сверке'],
      // «Ждёт старта» — ПОДСКАЗКА, а не чип (так и в ТЗ). Первая редакция дала сюда
      // текст чипа без цвета, и `chip(...null)` уронил весь кабинет: страница белая,
      // в консоли «s is not iterable». Цена промаха в необязательном поле не должна
      // быть равна цене падения экрана — об этом ниже, в самом рендере.
      ['в размещении', String(k.live), 'РК', '', null,
       k.soon ? `идут сейчас · ${k.soon} ждёт старта`
              : 'идут сейчас; после сверки за период уходят в архив'],
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
          {pageTitle((NAV_MOBILE.find(n => n.key === tab) || {}).label || 'Дашборд')}
        </title>
      </Head>
      {/* Плашка сообщения — ПЕРЕД шапкой и вне потока: она крепится к окну, а не к
          месту в разметке. В потоке она стояла первой строкой колонки, и человек,
          работающий внизу списка, отказа не видел вовсе. */}
      <Toast text={err} onClose={() => setErr('')} />

      {mobile ? (
        <MobileHeader profile={profile} name={name} account={me}
          nav={NAV_MOBILE.map(n => (n.key === 'queue'
            ? { ...n, badge: shownTasks.length } : n))}
          active={tab} onNav={setActive} onExit={onSignOut} onGuide={() => setGuide(true)} />
      ) : (
        <Header profile={profile} name={name} account={me}
          nav={NAV.map(n => (n.key === 'queue'
            ? { ...n, badge: shownTasks.length } : n))}
          active={tab} onNav={setActive} count={(dash?.publishers || []).length}
          onExit={onSignOut} onGuide={() => setGuide(true)} />
      )}
      {guide && <Guide onClose={closeGuide} />}

      <div style={{ ...WRAP, display: 'flex', gap: mobile ? 12 : 14,
        flexDirection: mobile ? 'column' : 'row', alignItems: mobile ? 'stretch' : 'flex-start',
        padding: mobile ? '12px 12px 40px' : '20px 20px 60px' }}>

        {!(mobile && tab === 'contact') && (
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column',
          gap: mobile ? 12 : 14 }}>

          {/* РАЗДЕЛ «КАМПАНИИ» занимает всю левую колонку и заканчивает рендер.

              Правая колонка (уведомления, команда, договор, лента) при этом остаётся:
              она про кабинет целиком, а не про дашборд, и прятать её при переходе
              означало бы, что связь с нами пропадает вместе со сменой вкладки.

              Проп называется `campaigns` — так в компоненте хендоффа. Пока я звал его
              `rows`, экран молча рисовал СВОИ демо-данные из умолчания: июнь и июль,
              которых у площадки нет. Выглядело правдоподобно, и поймал я это только
              потому, что сверил месяцы с настоящими. */}
          {tab === 'campaigns' ? (
            mobile ? <CampaignsMobile campaigns={camps || []} />
              : <CampaignsScreen campaigns={camps || []} />
          ) : (
          <>

          {/* Мой период */}
          {/* РАЗМЕРЫ ГЛАВНОГО ВИДЖЕТА СВЕРЕНЫ С ЭКРАНОМ «КАМПАНИИ» (владелец 15.09.2026).

              Эталон — карточка из хендоффа: она нарисована дизайнером, а здешние плитки я
              восстанавливал руками и взял размеры на глаз. Плавало всё сразу — отступы
              карточки, кегль заголовка, кегль числа и подписи, — и при переходе между
              разделами виджет «прыгал».

              Числа держатся в общем ките (`lib/ui.js::KPI_SIZE`), а не вписаны по месту:
              вторая копия размеров разъедется на первой же правке — ровно так это и
              случилось. */}
          <div className="rise" style={{ ...card,
            padding: mobile ? '14px 14px 12px' : '18px 24px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: mobile ? 8 : 12,
              flexWrap: mobile ? 'wrap' : 'nowrap' }}>
              <span style={{ fontSize: mobile ? 20 : 24, fontWeight: 800,
                letterSpacing: '-0.025em' }}>Мой период</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: C.faint,
                letterSpacing: '.06em', textTransform: 'uppercase' }}>
                {(profile?.domain || '—')} · {period}
              </span>
              {/* Что за площадками закреплено. Чипы те же, что у нас на экране
                  настройки кабинетов: это одна и та же запись, а не вторая её версия.
                  Поверхности внутри чипа, а не отдельными — у площадки это одна услуга
                  на двух экранах, и два чипа читались бы как две разные. */}
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1,
                paddingLeft: mobile ? 0 : 18, flexBasis: mobile ? '100%' : 'auto',
                order: mobile ? 3 : 0 }}>
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
                    fontSize: 13, cursor: 'pointer',
                    ...(mobile ? { flexBasis: '100%', minHeight: 40, order: 2 } : {}) }}>
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
            {/* Телефон — сетка 2×2 с разделителями (хендофф «моб версия кп», п. 2). */}
            <div style={{ display: 'grid',
              gridTemplateColumns: mobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)',
              marginTop: mobile ? 14 : 18, rowGap: mobile ? 14 : 0 }}>
              {KPI.map(([label, value, unit, chipText, chipTone, hint], i) => (
                <div key={label} style={mobile ? {
                  padding: i % 2 ? '0 0 0 12px' : '0 12px 0 0',
                  borderLeft: i % 2 ? `1px solid ${C.row}` : 'none', minWidth: 0,
                } : { padding: i ? '0 0 0 26px' : 0,
                  borderLeft: i ? `1px solid ${C.row}` : 'none', marginLeft: i ? 26 : 0 }}>
                  <div style={{ ...CAP, marginBottom: 0,
                    fontSize: KPI_SIZE.label, color: C.muted }}>{label}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 7,
                    marginTop: 8 }}>
                    <span style={{ fontFamily: MONO, fontSize: mobile ? 19 : KPI_SIZE.value,
                      fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1,
                      whiteSpace: 'nowrap', color: KPI_TONE[i] }}>{value}</span>
                    {!!unit && (
                      <span style={{ fontSize: KPI_SIZE.unit, fontWeight: 600,
                        color: C.muted }}>{unit}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6,
                    flexWrap: 'wrap' }}>
                    {/* Цвет чипа берётся С ЗАПАСНЫМ ЗНАЧЕНИЕМ. Раньше здесь стоял голый
                        `chip(...chipTone)`, и плитка с текстом, но без цвета обрушивала
                        ВЕСЬ кабинет: `...null` бросает TypeError прямо в рендере, React
                        снимает дерево, человек видит белый экран. Несоразмерно: пропущен
                        необязательный цвет, а цена — недоступный кабинет.
                        Нейтральная плашка вместо падения. */}
                    {!!chipText && (
                      <span style={{ ...chip(...(chipTone
                        || [C.subtle, C.muted, C.border])), fontSize: 10.5,
                        padding: '2px 8px' }}>{chipText}</span>
                    )}
                    <span style={{ fontSize: KPI_SIZE.hint, color: C.faint }}>{hint}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Очередь */}
          <div className="rise" style={{ ...card,
            padding: mobile ? '14px 12px' : '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14,
              flexWrap: 'wrap' }}>
              <span style={{ fontSize: 17, fontWeight: 800 }}>Требует вашего решения</span>
              <span style={{ ...chip(C.dangerTint, C.danger, C.dangerBorder),
                fontFamily: MONO }}>{tasks?.total ?? 0}</span>
              {!mobile && (
                <span style={{ ...CAP, marginBottom: 0 }}>
                  креативы, пролонгации, сверки · дедлайн решения
                </span>
              )}
              <span style={{ flex: 1 }} />
              {me && !me.can_approve
                ? <span style={{ fontSize: 11.5, color: C.faint }}>
                    у вас доступ только на просмотр
                  </span>
                : !!shownTasks.length && (
                  <>
                    {/* «Согласовать все» — не украшение: один баннер уходит на несколько
                        сайтов, и площадка отвечает по каждому отдельно. Подтверждение
                        спрашивается, потому что действие необратимо. */}
                    <button style={{ ...soft(C.accent, C.accentBorder),
                      padding: '7px 14px', fontSize: 12.5,
                      ...(mobile ? { flexBasis: '100%', minHeight: 44, fontSize: 14 } : {}) }}
                      disabled={bulk}
                      onClick={approveAll}>
                      {/* Число — то же, что в подтверждении: без заданий, ждущих ссылку. */}
                      {bulk ? 'Согласуем…'
                        : `Согласовать все · ${shownTasks.filter(t => t.url_state !== 'запрошена').length}`}
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
            {openDone && mobile && (
              /* Телефон — строками без таблицы; комментарий целиком (хендофф, п. 2). */
              <div className="pop" style={{ marginTop: 10, display: 'flex',
                flexDirection: 'column' }}>
                {done.map(d => (
                  <div key={d.task_id} style={{ padding: '10px 0',
                    borderTop: `1px solid ${C.row}`, display: 'flex', flexDirection: 'column',
                    gap: 4 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={chip(
                        d.verdict === 'ок' ? C.incomeTint : C.dangerTint,
                        d.verdict === 'ок' ? C.incomeFg : C.danger,
                        d.verdict === 'ок' ? C.incomeBorder : C.dangerBorder)}>
                        {d.verdict === 'ок' ? 'согласовано' : d.verdict}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>
                        {d.brand || d.advertiser || '—'}
                      </span>
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 11, color: C.secondary }}>
                      {d.publisher || '—'} · Креатив №{d.creative_no}
                      {d.creative_title ? ` — ${d.creative_title}` : ''}
                    </span>
                    {!!d.reason && (
                      <span style={{ fontSize: 12.5, color: C.muted }}>{d.reason}</span>
                    )}
                  </div>
                ))}
                {!done.length && (
                  <div style={{ padding: '12px 0', fontSize: 12.5, color: C.faint }}>
                    За неделю решений не было.
                  </div>
                )}
              </div>
            )}
            {openDone && !mobile && (
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

          {/* Актуальные кампании — компонент из хендоффа, ВСТАВЛЕН ДОСЛОВНО
              (`components/ActiveCampaigns.jsx`), данные подключены сбоку. Прежний
              `Campaigns` собирался из `lib/demo.js` и был выключен флагом SHOW_MONEY:
              выключенная выдумка вместо блока. Теперь строки приходят из витрины
              `pub.campaign_v1` — настоящие размещения этой площадки. */}
          {/* На дашборде — только то, что ЕЩЁ В РАБОТЕ: размещение висит здесь до сверки
              за период, после неё уходит в раздел «Кампании». Отбор делает экран, а
              признак считает витрина — определение одно на оба раздела. */}
          {/* Телефон: вместо таблицы кампаний — лента событий под очередью (хендофф,
              п. 1); кампании целиком во вкладке «Кампании». */}
          {mobile ? <Feed onErr={setErr} /> : (() => {
            const live = (camps || []).filter(c => !c.reconciled)
            return !!live.length && <ActiveCampaigns campaigns={live} />
          })()}

          </>
          )}
        </div>
        )}

        {/* правая колонка; на телефоне — вкладка «Связь» */}
        {(!mobile || tab === 'contact') && (
        <div style={{ width: mobile ? 'auto' : 280, flex: mobile ? '1 1 auto' : '0 0 280px',
          display: 'flex', flexDirection: 'column', gap: mobile ? 12 : 14 }}>

          {/* ПОРЯДОК КОЛОНКИ ЗАДАН ВЛАДЕЛЬЦЕМ 15.09.2026: уведомления · команда ·
              договор · лента. Это не вкусовщина — порядок читается как убывание
              срочности: сначала то, что человек настраивает под себя, потом к кому
              идти с вопросом, потом на каком основании работаем, и последней история.

              МЕДИАКИТ УБРАН (тогда же). Блок остаётся в коде компонентом `MediaKit` и
              вернётся, когда понадобится: удалять его насовсем значило бы выбросить
              единственный путь, которым площадка что-то даёт нам сама. */}
          <NotifyBlock onErr={setErr} />

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
                {/* Телефон: письмо одним касанием (хендофф «моб версия кп», п. 4). */}
                {mobile && !!m.email && (
                  <a href={`mailto:${m.email}`} aria-label={`Написать ${m.name || ''}`}
                    style={{ ...btn(false), marginLeft: 'auto', minHeight: 40, minWidth: 40,
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      textDecoration: 'none', padding: '0 12px' }}>✉</a>
                )}
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
                  <a href={safeHref(profile.chat_url) || '#'} target="_blank" rel="noreferrer"
                    style={{ ...btnSm(false), flex: 1, textAlign: 'center',
                      textDecoration: 'none',
                      opacity: profile.chat_url ? 1 : .45,
                      pointerEvents: profile.chat_url ? 'auto' : 'none' }}>Телеграм</a>
                  <a href={safeHref(profile.chat_url_max) || '#'} target="_blank" rel="noreferrer"
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

          <Side title="договоры">
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

          {!mobile && <Feed onErr={setErr} />}
        </div>
        )}
      </div>

      {/* Версия кабинета — внизу слева, отдельным контуром от финмодуля.

          Показывается ВСЕМ, а не только админу, как в финмодуле: здесь по ту сторону
          экрана внешний человек, и на вопрос «у меня всё ещё старая версия?» отвечать
          должен сам экран, а не переписка. Значение инлайнится при СБОРКЕ, поэтому
          старый номер в подвале означает «фронт не пересобрали», а не «правка не
          доехала», — сегодня это ровно та ошибка, которая стоила часа. */}
      <div style={{ ...WRAP, paddingTop: 18, paddingBottom: 22 }}>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.04em',
          color: C.faint }}>
          кабинет паблишера · v{process.env.NEXT_PUBLIC_CABINET_VERSION}
        </span>
      </div>
    </>
  )
}
