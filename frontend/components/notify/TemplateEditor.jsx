/**
 * Редактор шаблонов писем — вкладка «Шаблоны» экрана «Настройки → Почта».
 *
 * Настраивает ОБА контура рассылки: письма сотрудникам и письма площадкам. Живёт внутри
 * экрана почты, а не отдельной страницей (владелец 16.09.2026): вопрос «что написано в
 * письме» возникает там же, где смотрят, дошло ли оно.
 *
 * Логика правок взята из хендоффа `docs/шаблонизатор.zip`, перечень событий и данные —
 * наши. Подстановки показываются на НАСТОЯЩЕЙ сделке и настоящей площадке: на выдуманной
 * «Ромашке» не видно ни длины реальных названий, ни того, как ложится настоящий период.
 *
 * ЧТО ЗДЕСЬ НЕ НАСТРАИВАЕТСЯ: тон события, набор событий, получатели и пороги повторов.
 * Они приходят из реестра, экран их только показывает. Разреши мы менять тон текстом —
 * письмо и панель разошлись бы по важности одного и того же события.
 *
 * ПИСЬМО СПРАВА РИСУЕТ СЕРВЕР тем же кодом, что отправляет. Своей вёрстки письма здесь
 * нет намеренно: разошлись бы они молча, а узнали бы мы об этом от получателя.
 *
 * Бэкенд: backend/app/mail/editor.py, право settings_mail (view/edit).
 */
import { useCallback, useEffect, useState } from 'react'
import { UI, MONO, CAP, card, inp, btn } from '../salesTableKit'
import { msg, segBtn, STATUS, TONE_UI, Chip } from './kit'
import api, { auth } from '../../lib/http'

const CONTOURS = [
  ['staff', 'Сотрудникам', 'письма нашим людям: очередь сделок, документы, деньги'],
  ['pub', 'Площадкам', 'письма наружу, в кабинет паблишера'],
]

export default function TemplateEditor({ mayEdit, onErr }) {
  const ready = true
  const [contour, setContour] = useState('staff')
  const [state, setState] = useState(null)      // ответ /mail/editor/<contour>
  const [html, setHtml] = useState('')
  const [open, setOpen] = useState('')          // раскрытая карточка
  const [note, setNote] = useState('')
  // Ошибку отдаём НАВЕРХ: на экране почты одно место для сообщений, и два независимых
  // «что-то пошло не так» в разных углах читаются как две разные поломки.
  const setErr = onErr

  /* Состав письма — ЛОКАЛЬНЫЙ, для проверки вида: настоящий состав определяет рассылка.
     Держим по контурам отдельно, иначе переключение теряло бы набор. */
  const [inLetter, setInLetter] = useState({ staff: [], pub: [] })
  const keys = inLetter[contour] || []


  const load = useCallback(async () => {
    if (!ready) return
    const q = encodeURIComponent(keys.join('|'))
    try {
      const [s, p] = await Promise.all([
        api.get(`/mail/editor/${contour}?keys=${q}`, auth()),
        api.get(`/mail/editor/${contour}/preview?keys=${q}`, auth()),
      ])
      setState(s.data); setHtml(p.data); setErr('')
    } catch (e) { setErr(msg(e)) }
  }, [ready, contour, keys])

  useEffect(() => { load() }, [load])

  /* Первый заход: в письмо кладём построенные карточки, чтобы экран открывался
     непустым. Пустой предпросмотр не отвечает ни на один вопрос, ради которого
     сюда пришли. */
  useEffect(() => {
    if (!state || (inLetter[contour] || []).length) return
    const first = state.cards.filter(c => c.built).slice(0, 4).map(c => c.key)
    if (first.length) setInLetter(s => ({ ...s, [contour]: first }))
  }, [state, contour, inLetter])

  const toggle = key => setInLetter(s => {
    const cur = s[contour] || []
    return { ...s, [contour]: cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key] }
  })

  const saveShell = async patch => {
    try {
      const r = await api.put(`/mail/editor/${contour}/shell`, { patch }, auth())
      setState(s => ({ ...s, shell: r.data.shell })); setNote('Сохранено'); load()
    } catch (e) { setErr(msg(e)) }
  }
  const saveCard = async (key, patch) => {
    try {
      const r = await api.put(`/mail/editor/${contour}/card/${encodeURIComponent(key)}`,
        { patch }, auth())
      setState(s => ({ ...s, cards: r.data.cards })); setNote('Сохранено'); load()
    } catch (e) { setErr(msg(e)) }
  }

  useEffect(() => { if (!note) return undefined
    const t = setTimeout(() => setNote(''), 2000); return () => clearTimeout(t) }, [note])

  /* Пробное письмо уходит ТОЛЬКО на свой адрес — как и проверка канала. Кнопка с
     произвольным адресом превратила бы систему в отправщик писем кому угодно от имени
     компании. И проверять надо именно в почте: клиенты режут разметку по-разному, и
     «в браузере выглядит хорошо» про письмо не значит ничего. */
  const [sending, setSending] = useState(false)
  const sendTest = async () => {
    setSending(true); setErr('')
    try {
      const r = await api.post(
        `/mail/editor/${contour}/test?keys=${encodeURIComponent(keys.join('|'))}`, {}, auth())
      setNote(`Письмо ушло на ${r.data.to}`)
    } catch (e) { setErr(msg(e)) } finally { setSending(false) }
  }

  /* Высота письма РАСТЁТ ВМЕСТЕ С СОСТАВОМ. Фиксированные 640 означали пустое поле
     под одной карточкой и обрезанное письмо под шестью — а смотрят на него именно
     чтобы увидеть письмо целиком.

     Меряем по содержимому рамки: `srcDoc` наследует наш источник, поэтому документ
     внутри читается. Если вдруг не прочёлся (жёсткая политика в браузере) — остаётся
     прежняя высота, а не ноль: пустая рамка хуже неточной. */
  const [hgt, setHgt] = useState(640)
  const fit = (e) => {
    try {
      const d = e.target.contentDocument
      const h = d?.body?.scrollHeight
      if (h) setHgt(Math.max(320, h + 24))
    } catch { /* другой источник — оставляем как есть */ }
  }

  const checks = state?.checks || []
  const bad = checks.filter(c => !c.ok).length

  return (
    <div style={{ fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          marginBottom: 12 }}>
          <div style={{ display: 'flex', background: 'var(--bg-subtle)', borderRadius: 10, padding: 3 }}>
            {CONTOURS.map(([k, label]) => (
              // `segBtn` из набора модуля, а не `btn` с подменённым фоном: у активной
              // кнопки `btn(true)` текст БЕЛЫЙ под цвет акцента, и подмена фона на
              // светлый оставляла белое по белому. Ровно тот случай, ради которого
              // заведено правило «цвет смысла отдельно от цвета текста».
              <button key={k} onClick={() => { setContour(k); setOpen('') }}
                style={{ ...segBtn(contour === k), fontSize: 12.5 }}>
                {label}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            {CONTOURS.find(c => c[0] === contour)[2]}
          </span>
          {note && <span style={{ ...CAP, marginBottom: 0, color: 'var(--income-fg)' }}>{note}</span>}
        </div>

        {/* Письмо — ФИКСИРОВАННЫЕ 700 (владелец 16.09.2026): само оно 600 пикселей, как
            у получателя, и растягивать полосу под ним бессмысленно. Вся остальная
            ширина уходит влево, карточкам: их тексты правят здесь, и лишнее место
            тратится именно на них. */}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(420px, 1fr) 700px',
          gap: 14, alignItems: 'start' }}>
          <div style={{ minWidth: 0 }}>
            {state && <Shell shell={state.shell} values={state.values} fields={state.fields}
              mayEdit={mayEdit} onSave={saveShell} />}
            {state && (
              <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
                  display: 'flex', alignItems: 'center', gap: 10 }}>
                  <b style={{ fontSize: 14 }}>Карточки уведомлений</b>
                  <span style={{ ...CAP, marginBottom: 0 }}>
                    {state.cards.length} · в письме {keys.length}
                  </span>
                </div>
                {state.cards.map(c => (
                  <Card key={c.key} c={c} contour={contour} open={open === c.key}
                    onOpen={() => setOpen(open === c.key ? '' : c.key)}
                    inLetter={keys.includes(c.key)} onToggle={() => toggle(c.key)}
                    mayEdit={mayEdit} onSave={patch => saveCard(c.key, patch)} />
                ))}
              </div>
            )}
          </div>

          {/* Полоса письма ЕДЕТ ЗА ПРОКРУТКОЙ: карточек два десятка, и правка нижней
              без этого делалась вслепую — письмо оставалось наверху. Высота ограничена
              окном, внутри прокрутка: липкий блок выше экрана перестаёт липнуть и
              уезжает вместе со страницей. */}
          <div style={{ position: 'sticky', top: 12, maxHeight: 'calc(100vh - 24px)',
            overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ ...card, padding: 12 }}>
              <div style={{ ...CAP }}>письмо целиком · 600 px, как у получателя</div>
              {keys.length === 0
                ? <div style={{ padding: 28, textAlign: 'center', fontSize: 12.5,
                    color: 'var(--text-muted)', border: '1px dashed var(--border-card)',
                    borderRadius: 10 }}>
                    Ни одна карточка не добавлена в предпросмотр
                  </div>
                : <iframe title="Письмо целиком" srcDoc={html} onLoad={fit}
                    /* скриптов в письме нет; доступ к документу нужен подгонке высоты */
                    sandbox="allow-same-origin"
                    style={{ width: '100%', height: hgt, border: '1px solid var(--border-card)',
                      borderRadius: 11, background: '#fff', display: 'block' }} />}
            </div>
            <div style={{ ...card, padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>
                  проверка · {bad ? `не выполнено ${bad}` : 'всё в порядке'}
                </span>
                {mayEdit && (
                  <button onClick={sendTest} disabled={sending || keys.length === 0}
                    title="Придёт на адрес вашей учётки"
                    style={{ ...btn(false), marginLeft: 'auto', fontSize: 12,
                      padding: '4px 10px',
                      opacity: (sending || keys.length === 0) ? 0.5 : 1 }}>
                    {sending ? 'Отправляю…' : 'Отправить себе'}
                  </button>
                )}
              </div>
              {checks.map(ch => (
                <div key={ch.key} style={{ display: 'flex', gap: 8, padding: '6px 0',
                  fontSize: 12.5, alignItems: 'flex-start' }}>
                  <span style={{ width: 18, height: 18, borderRadius: 6, flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 800,
                    background: ch.ok ? 'var(--income-tint)' : 'var(--warning-tint)',
                    color: ch.ok ? 'var(--income-fg)' : 'var(--warning-fg)' }}>
                    {ch.ok ? '✓' : '!'}
                  </span>
                  <span>
                    <span style={{ color: 'var(--text-primary)' }}>{ch.text}</span>
                    <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 11.5 }}>
                      {ch.hint}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
    </div>
  )
}

/**
 * Оболочка письма. Главное правило блока: прехедер и подзаголовок — НЕ фиксированный
 * текст. Письмо про одну сверку и письмо про четыре срочных события обещают получателю
 * разное, поэтому по умолчанию они собраны из подстановок и считаются из состава.
 *
 * Под каждым полем виден результат подстановки и источник: «по правилу» или «задано
 * вручную». Вписал свой текст — поле перестало следовать за содержимым, и рядом
 * появляется «вернуть правило».
 */
function Shell({ shell, values, fields, mayEdit, onSave }) {
  const [draft, setDraft] = useState({})
  useEffect(() => { setDraft({}) }, [shell])

  // Подстановка теми же правилами, что на сервере: незаполненное поле становится
  // пустотой, а не скобками — скобки в письме читаются как неисправность системы.
  const subst = s => (s || '').replace(/\{([^{}]+)\}/g, (_, k) => values[k.trim()] ?? '')

  return (
    <div style={{ ...card, padding: 0, marginBottom: 12, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <b style={{ fontSize: 14 }}>Оболочка письма</b>
        <span style={{ ...CAP, marginBottom: 0 }}>одна на контур</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {Object.entries(fields || {}).map(([k, hint]) => (
            <span key={k} title={hint} style={{ fontFamily: MONO, fontSize: 10,
              padding: '2px 6px', borderRadius: 6, background: 'var(--bg-subtle)',
              color: 'var(--text-secondary)' }}>{'{' + k + '}'}</span>
          ))}
        </span>
      </div>
      <div style={{ padding: 14, display: 'grid', gap: 12 }}>
        {Object.entries(shell).map(([f, v]) => {
          const val = draft[f] ?? v.value
          return (
            <div key={f}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>{v.label}</span>
                <span style={{ fontSize: 10.5, fontWeight: 700, padding: '1px 7px',
                  borderRadius: 6,
                  background: v.manual ? 'var(--warning-tint)' : 'var(--bg-subtle)',
                  color: v.manual ? 'var(--warning-fg)' : 'var(--text-muted)' }}>
                  {v.manual ? 'задано вручную' : 'по правилу'}
                </span>
                {v.manual && mayEdit && (
                  <button onClick={() => onSave({ [f]: null })}
                    style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer',
                      fontSize: 11.5, color: 'var(--accent)', fontFamily: UI }}>
                    вернуть правило
                  </button>
                )}
              </div>
              {/* Ввод на onChange в состояние черновика, запись — на blur: сохранять на
                  каждый символ значит слать запрос на каждую букву. */}
              <textarea value={val} readOnly={!mayEdit} rows={f === 'footer' ? 2 : 1}
                onChange={e => setDraft(d => ({ ...d, [f]: e.target.value }))}
                onBlur={() => { if (draft[f] !== undefined && draft[f] !== v.value) onSave({ [f]: draft[f] }) }}
                style={{ ...inp, width: '100%', fontFamily: UI, fontSize: 13, resize: 'vertical' }} />
              <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--text-secondary)' }}>
                → {subst(val) || <span style={{ color: 'var(--text-muted)' }}>пусто</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Одна карточка события: строка списка, в раскрытом виде — редактор текста. */
function Card({ c, contour, open, onOpen, inLetter, onToggle, mayEdit, onSave }) {
  const [draft, setDraft] = useState({})
  useEffect(() => { setDraft({}) }, [c])
  const val = f => draft[f] ?? c[f] ?? ''
  const put = f => { if (draft[f] !== undefined && draft[f] !== c[f]) onSave({ [f]: draft[f] }) }

  /* Вид, уходящий ПРОСТЫМ ТЕКСТОМ («Запрос посадочной»), карточки не имеет: его пишет
     человек, выбирая формулировку, а ответ площадки приходит ему же. Показываем сам
     текст — рисовать ему конверт значило бы показать письмо, которого не существует. */
  const [plain, setPlain] = useState(null)
  useEffect(() => {
    if (!open || !c.plain) return
    api.get(`/mail/cards/text?contour=${contour}&key=${encodeURIComponent(c.key)}`, auth())
      .then(r => setPlain(r.data)).catch(() => setPlain(null))
  }, [open, c.plain, c.key, contour])

  const FIELDS = [
    ['title', 'Заголовок', 'одна фраза, без точки в конце'],
    ['body', 'Текст', 'зачем письмо и что делать; пусто — карточка идёт без текста'],
    ['action', 'Кнопка', 'глагол действия: «Собрать МП», «Подтвердить факт»'],
  ]

  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div style={{ padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 8,
        flexWrap: 'wrap', cursor: 'pointer', opacity: c.built ? 1 : 0.6 }} onClick={onOpen}>
        <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 10 }}>
          {open ? '▾' : '▸'}
        </span>
        <Chip pair={TONE_UI[c.tone] || TONE_UI.info}
          text={(TONE_UI[c.tone] || TONE_UI.info)[2]} />
        <span style={{ fontSize: 13, fontWeight: open ? 700 : 500 }}>{c.title}</span>
        <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>{c.tag}</span>
        {c.edited?.length > 0 && (
          <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 6,
            background: 'var(--warning-tint)', color: 'var(--warning-fg)' }}>правка</span>
        )}
        {c.locked && <span style={{ ...CAP, marginBottom: 0 }}>нельзя отключить</span>}

        {/* СТОЛБЕЦ состояния: плашки одной ширины и текст по центру (владелец
            16.09.2026). Вразнобой по строке они читались как продолжение названия
            события, а не как ответ на вопрос «а это вообще работает». */}
        <span style={{ marginLeft: 'auto', flex: '0 0 130px', display: 'flex',
          justifyContent: 'center' }}>
          <Chip pair={c.built ? STATUS.sent : STATUS.queued}
            text={c.built ? 'подключено' : 'не подключено'}
            style={{ width: '100%', textAlign: 'center', padding: '3px 0' }} />
        </span>
        {/* Кнопка «в письмо» — состав предпросмотра, а не подписка. */}
        <button onClick={e => { e.stopPropagation(); onToggle() }}
          style={{ flex: '0 0 auto', fontSize: 11.5, fontWeight: 700, padding: '3px 10px',
            borderRadius: 8, cursor: 'pointer', fontFamily: UI,
            border: `1px solid ${inLetter ? 'var(--accent-border)' : 'var(--border-card)'}`,
            background: inLetter ? 'var(--accent-tint)' : 'var(--bg-card)',
            color: inLetter ? 'var(--accent)' : 'var(--text-secondary)' }}>
          {inLetter ? '✓ в письме' : '+ в письмо'}
        </button>
      </div>

      {open && (
        <div style={{ padding: '4px 14px 14px 32px', display: 'grid', gap: 10 }}>
          {FIELDS.map(([f, label, hint]) => (
            <div key={f}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                <span style={{ ...CAP, marginBottom: 0 }}>{label}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{hint}</span>
                {c.edited?.includes(f) && mayEdit && (
                  <button onClick={() => onSave({ [f]: null })}
                    style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer',
                      fontSize: 11.5, color: 'var(--accent)', fontFamily: UI }}>
                    вернуть из реестра
                  </button>
                )}
              </div>
              <textarea value={val(f)} readOnly={!mayEdit} rows={f === 'body' ? 2 : 1}
                onChange={e => setDraft(d => ({ ...d, [f]: e.target.value }))}
                onBlur={() => put(f)}
                style={{ ...inp, width: '100%', fontFamily: UI, fontSize: 13, resize: 'vertical' }} />
            </div>
          ))}
          {/* Кнопка нужна не каждому письму: подтверждению («ЕРИД выпущен», «оплата
              отправлена») идти некуда, а синий прямоугольник требует действия. */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
            cursor: mayEdit ? 'pointer' : 'default' }}>
            <input type="checkbox" checked={c.show_button !== false} disabled={!mayEdit}
              onChange={e => onSave({ show_button: e.target.checked })} />
            Показывать кнопку
            <span style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>
              {c.show_button === false
                ? 'сейчас карточка без кнопки — письмо только сообщает'
                : `подпись: «${c.action || 'Открыть'}»`}
            </span>
          </label>

          {c.plain && (
            <div style={{ border: '1px dashed var(--border-card)', borderRadius: 10,
              padding: 12, fontSize: 12.5, color: 'var(--text-secondary)' }}>
              Это письмо уходит <b>простым текстом</b> и своим шаблоном: его пишет человек,
              а ответ площадки приходит ему же. В общее письмо оно не собирается.
              {plain && <>
                <div style={{ marginTop: 8 }}><b>Тема:</b> {plain.subject}</div>
                <pre style={{ margin: '6px 0 0', fontFamily: UI, fontSize: 12,
                  whiteSpace: 'pre-wrap' }}>{plain.body}</pre>
              </>}
            </div>
          )}
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
            Тон и тема события приходят из реестра и здесь не правятся: письмо и панель
            должны говорить об одном событии одинаково.
            {contour === 'pub' && ' Нашего кода сделки в этом письме быть не может.'}
          </div>
        </div>
      )}
    </div>
  )
}
