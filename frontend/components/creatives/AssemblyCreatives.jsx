/**
 * Сбор креативов на карточке сделки.
 *
 * КРЕАТИВ ПЕРВИЧЕН (решение владельца 27.08.2026). Точка входа — «Прикрепить креатив»;
 * площадки выбираются уже внутри него, а не отдельным списком сверху. Порядок повторяет
 * жизнь: сначала приходит материал от клиента, потом решают, кому он уходит. Второй
 * креатив — та же кнопка внизу, тот же цикл.
 *
 * Площадки под услугу подставляются сами: строки приходят с сервера уже отмеченными,
 * аккаунт снимает лишние галочки. Разметка справочника покрывает не все услуги, поэтому
 * пустой список объясняется текстом, а не выглядит поломкой.
 *
 * Все вспомогательные компоненты объявлены на модульном уровне: объявленный внутри
 * рендера компонент, оборачивающий input, пересоздаётся на каждый ввод, и фокус слетает
 * после каждого символа.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, UI, inp, btn, PickValue, EXT_TONE, ExtChip, Modal } from '@/components/salesTableKit'
import BrandMarkingDialog, { saveBrandMarking } from '../ord/BrandMarking'
import ValuePopover from '@/components/ValuePopover'
import { overlayClose } from '@/lib/overlay'
import { can, getPermissions } from '@/lib/auth'
import { downloadFile } from '@/lib/download'

const CAP = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const BOX = { border: '1px solid var(--border-card)', borderRadius: 14, padding: '14px 16px', background: 'var(--bg-card)' }
const SHEET = { background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', padding: '20px 22px', width: 'min(680px, 96vw)', maxHeight: '86vh', overflowY: 'auto', boxShadow: 'var(--shadow-card)' }
const OVERLAY = { position: 'fixed', inset: 0, background: 'rgba(16,20,30,.45)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }

/* Форма распространения — значения ОРД. На экране они читаются как есть, кроме одного:
   «BannerHtml5» слипается в одно слово, а это две вещи — баннер и его формат. */
export const FORM_LABEL = { BannerHtml5: 'Banner Html5' }

/* Состояние комплекта — плашкой, а не подписью: это состояние, и его ищут глазом.
   Цвет и подложка идут парой, иначе зелёный текст на белом читается как ссылка. */
export const SET_TONE = {
  'черновик':         ['var(--text-muted)', 'var(--bg-subtle)'],
  'готов к отправке': ['var(--income)', 'var(--income-tint)'],
  // «У трафика» и «отправлен» — разные ступени, и разными их сделал разворот цепочки
  // 28.08.2026. Цвет ожидания у первой, рабочий синий у второй.
  'у трафика':        ['var(--dot-current-dz)', 'var(--warning-tint)'],
  'отправлен':        ['var(--accent)', 'var(--accent-tint)'],
  'на доработку':     ['var(--dot-overdue)', 'var(--danger-tint)'],
  'маркирован':       ['var(--income)', 'var(--income-tint)'],
}

/* Маркер стоит В САМОЙ плашке, а не рядом: «маркирован» без номера — это половина
   новости, а номер без слова «маркирован» не говорит, что запись в реестре уже есть. */
export function SetStateBadge({ state, erid }) {
  const [fg, bg] = SET_TONE[state] || ['var(--text-muted)', 'var(--bg-subtle)']
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '3px 11px', borderRadius: 100, background: bg, color: fg,
      fontFamily: MONO, fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em',
      textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
      {state}
      {!!erid && (
        <>
          <span style={{ opacity: 0.45 }}>|</span>
          <span onClick={() => navigator.clipboard?.writeText(erid)} title="Скопировать ЕРИД"
            style={{ cursor: 'pointer', letterSpacing: 0 }}>ERID {erid}</span>
        </>
      )}
    </span>
  )
}
/* Статус строки получателя — ОДНА лестница от черновика до размещения.
   Считается, а не хранится: до отправки его задаёт материал (есть ли файлы, прошёл ли
   первичную проверку), после отправки — вердикт площадки, а после маркера — состояние
   получателя. Три источника, один столбец: человеку нужен ответ «где эта площадка», а не
   три частичных признака, которые он будет складывать в голове сам. */
const ROW_STATUS = {
  'черновик':      'var(--text-faint)',
  'у трафика':     'var(--dot-current-dz)',
  'у площадки':    'var(--accent)',
  'согласовано':   'var(--income)',
  'правки':        'var(--dot-current-dz)',
  'отказ':         'var(--dot-overdue)',
  'ерид получен':  'var(--income)',
  'ожидает старта': 'var(--dot-current-dz)',
  'в размещении':  'var(--income)',
}

function rowStatus(r, set) {
  // Отказ — боковой выход, и он старше всех прочих признаков: площадка выпала из
  // кампании, и новая версия ей не поможет.
  if (r.state === 'отказ площадки' || r.verdict === 'отказ') return 'отказ'
  if (r.state === 'в размещении') return 'в размещении'
  if (r.state === 'заведён в DSP') return 'ожидает старта'
  if (r.state === 'ерид получен') return 'ерид получен'
  if (r.verdict === 'на доработку') return 'правки'
  if (r.verdict === 'ок') return 'согласовано'
  // Трафик завернул материал — площадка о нём даже не узнала. Для аккаунта это то же
  // действие, что и правки от площадки: собрать новую версию.
  if (r.traffic_verdict === 'на переделку') return 'правки'
  // Колонка отвечает на вопрос «У КОГО СЕЙЧАС МЯЧ», и после разворота цепочки ответов
  // стало два. Прежнее «отправлено» их не различало, и владелец прочитал его ровно так,
  // как оно написано: «ушло в площадку», — хотя материал лежал у трафика (28.08.2026).
  // Поэтому не «на проверке» (у кого — непонятно), а прямо: у трафика / у площадки.
  if (r.pair_id && !r.traffic_verdict) return 'у трафика'
  if (r.pair_id) return 'у площадки'
  // Дальше — только «черновик». Первичная проверка СЮДА НЕ ВХОДИТ, хотя раньше входила
  // (владелец, 27.08.2026): она про материал, а колонка — про площадку. Подтвердив
  // баннер в предпросмотре, аккаунт видел «готов» разом у девяти площадок, которым
  // ничего не отправляли и которые ни о чём не спрашивали. Проверка разблокирует кнопку
  // отправки — и только; её результат виден в плашке состояния комплекта.
  //
  // «На проверке» здесь тоже НЕТ: такое состояние означало бы «материал ушёл и ждёт
  // ответа», а ждать пока некого — конвейера проверки у трафиков не существует. Слово
  // вернётся вместе с ним, тогда у него появится предмет.
  return 'черновик'
}

const fileSize = (n) => !n ? '' : n > 1048576 ? `${(n / 1048576).toFixed(1)} МБ` : `${Math.round(n / 1024)} КБ`

/* ── требования площадки: текст, а не документ ──────────────────────────── */
function TechRequirements({ target, onClose }) {
  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={SHEET}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Требования · {target.name}</div>
        <div style={{ ...CAP, marginTop: 4 }}>техрегламент · критерии к креативам</div>
        <div style={{ marginTop: 12, fontSize: 13.5, lineHeight: 1.6, whiteSpace: 'pre-wrap',
          color: target.tech_requirements ? 'var(--text-primary)' : 'var(--text-faint)' }}>
          {target.tech_requirements
            || 'Требования не заполнены. Их вносят в карточке площадки — до тех пор первичная проверка остаётся подтверждением «сверил», а не сверкой по документу.'}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button style={btn(false)} onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  )
}

/* ── запрос ссылки у площадки ───────────────────────────────────────────── */
function UrlRequestDialog({ target, onDone, onClose }) {
  const [text, setText] = useState(target.url_request_text || '')
  const [phrases, setPhrases] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/launch-prep/url-request-phrases', auth())
      .then(r => setPhrases(r.data.items || [])).catch(() => {})
  }, [])

  /* Пины дописывают текст, а не заменяют его: готовая фраза — заготовка, нюансы всегда
     свои. Тот же приём, что с чипами таргетинга в брифе. */
  const addPhrase = (p) => setText(t => (t.trim() ? `${t.trim()}\n${p}` : p))

  const savePhrase = async () => {
    const last = text.trim().split('\n').pop().trim()
    if (!last || phrases.some(p => p.text === last)) return
    try {
      const r = await api.post('/launch-prep/url-request-phrases', { text: last }, auth())
      setPhrases(list => [...list, r.data])
    } catch { /* накопитель — удобство, его отказ не должен ломать запрос */ }
  }

  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.post(`/launch-prep/target/${target.target_id}/url-request`, { text }, auth())
      onDone()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить'); setBusy(false) }
  }

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={SHEET}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Запрос ссылки · {target.name}</div>
        {/* Честно про то, что делает кнопка: своего канала до площадки у системы нет.
            Делать вид, что письмо ушло, хуже, чем не отправлять его вовсе. */}
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.55 }}>
          Текст запишется в карточку, и площадка попадёт в напоминания как ждущая ответа.
          Отправить его почтой или в чат нужно самому — своего канала до площадки у системы
          пока нет.
        </div>

        <div style={{ ...CAP, marginTop: 16, marginBottom: 7 }}>готовые фразы</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {phrases.map(p => (
            <span key={p.id} onClick={() => addPhrase(p.text)} title="Дописать в текст"
              style={{ cursor: 'pointer', padding: '4px 9px', borderRadius: 8, fontSize: 12,
                background: 'var(--bg-subtle)', border: '1px solid var(--border-card)' }}>
              {p.text.length > 46 ? p.text.slice(0, 44) + '…' : p.text}
            </span>
          ))}
          {!phrases.length && (
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>список пуст</span>
          )}
        </div>

        <div style={{ ...CAP, marginTop: 16, marginBottom: 6 }}>текст запроса</div>
        <textarea rows={5} value={text} onChange={e => setText(e.target.value)}
          placeholder="что именно нужно от площадки — страница товара, подборка, метки"
          style={{ ...inp, width: '100%', resize: 'vertical', fontFamily: UI, lineHeight: 1.55 }} />
        <div style={{ marginTop: 6 }}>
          <span onClick={savePhrase} title="Сохранить последнюю строку как готовую фразу"
            style={{ cursor: 'pointer', fontSize: 11.5, color: 'var(--accent)' }}>
            + сохранить последнюю строку в готовые фразы
          </span>
        </div>

        {!!err && <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={btn(true)} disabled={busy || !text.trim()} onClick={send}>
            Записать запрос
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── добавить площадок вручную ──────────────────────────────────────────── */
function PickTargets({ dealId, setId, onDone, onClose }) {
  const [opts, setOpts] = useState(null)
  const [picked, setPicked] = useState({})
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get(`/launch-prep/deal/${dealId}/target-options?set_id=${setId}`, auth())
      .then(r => setOpts(r.data)).catch(e => setErr(e.response?.data?.detail || 'Не удалось загрузить'))
  }, [dealId, setId])

  const toggle = (id, surface) => setPicked(p => {
    const next = { ...p }
    if (next[id] === surface) delete next[id]; else next[id] = surface
    return next
  })

  const save = async () => {
    const items = Object.entries(picked).map(([id, s]) => ({ publisher_id: Number(id), surface_kind: s }))
    if (!items.length) return onClose()
    setBusy(true); setErr('')
    try {
      await api.post(`/launch-prep/deal/${dealId}/targets`, { items, set_id: setId }, auth())
      onDone()
    }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить'); setBusy(false) }
  }

  const defaultSurface = (opts?.surfaces || [])[0] || 'web'

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={SHEET}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Добавить площадки</div>
        {!!opts && (
          <div style={{ ...CAP, marginTop: 4 }}>
            услуга: {opts.service?.name || 'не определена'} · {opts.service_reason}
          </div>
        )}
        {!opts && <div style={{ marginTop: 14, fontSize: 13, color: 'var(--text-muted)' }}>загрузка…</div>}

        {!!opts && (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10,
              marginTop: 16, marginBottom: 8 }}>
              <span style={CAP}>по услуге ({opts.proposed.length})</span>
              {/* «Добавить всех» — обычный случай: состав по услуге аккаунт знает
                  наизусть и берёт целиком, а вычёркивает уже в строке креатива. */}
              {!!opts.proposed.length && (
                <span onClick={() => setPicked(p => {
                  const next = { ...p }
                  opts.proposed.forEach(c => { next[c.publisher_id] = c.surface_kind })
                  return next
                })}
                  style={{ cursor: 'pointer', fontSize: 11.5, color: 'var(--accent)' }}>
                  добавить всех
                </span>
              )}
            </div>
            {!opts.proposed.length && (
              <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
                {opts.service
                  ? 'Свободных площадок по этой услуге нет — либо все уже добавлены, либо услуга не отмечена ни у одной. Разметка ведётся на экране «Заполнение».'
                  : 'Услуга не определена, поэтому предлагать нечего — выберите вручную ниже.'}
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
              {opts.proposed.map(c => (
                <PubChip key={`${c.publisher_id}-${c.surface_kind}`} name={c.name} code={c.code}
                  surface={c.surface_kind} on={picked[c.publisher_id] === c.surface_kind}
                  status={c.status} warn={c.status_warn}
                  onClick={() => toggle(c.publisher_id, c.surface_kind)} />
              ))}
            </div>

            <div style={{ ...CAP, marginTop: 18, marginBottom: 8 }}>весь справочник</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
              {opts.all.filter(p => !p.already).map(p => (
                <PubChip key={p.publisher_id} name={p.name} code={p.code}
                  surface={picked[p.publisher_id] || defaultSurface}
                  on={!!picked[p.publisher_id]} status={p.status} warn={p.status_warn}
                  onClick={() => toggle(p.publisher_id, picked[p.publisher_id] === 'web' ? 'app' : 'web')}
                  hint="клик переключает веб / приложение" />
              ))}
            </div>
          </>
        )}

        {!!err && <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={btn(true)} disabled={busy} onClick={save}>
            Добавить{Object.keys(picked).length ? ` (${Object.keys(picked).length})` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}

function PubChip({ name, code, surface, on, onClick, hint, status, warn }) {
  /* Статус площадки виден ПРИ ВЫБОРЕ, а не после (владелец 30.08.2026). Архивные сюда
     не приезжают вовсе — их отсеивает бэкенд; паузовые и переговорные приезжают
     помеченными: пауза временная, кампания могла начаться до неё, и запрет заблокировал
     бы законный случай. До этого фильтра не было никакого, и площадка «НА ПАУЗЕ» тихо
     прошла всю цепочку до выпуска ЕРИД. */
  return (
    <span onClick={onClick} title={warn ? `${name} · статус: ${status}` : (hint || name)}
      style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '5px 10px', borderRadius: 9, fontSize: 12.5,
        border: on ? '1px solid var(--accent)'
          : warn ? '1px solid var(--warning-border)' : '1px solid var(--border-card)',
        background: on ? 'var(--accent-tint)'
          : warn ? 'var(--warning-tint)' : 'var(--bg-subtle)' }}>
      {name}
      {!!warn && (
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.05em',
          color: 'var(--warning-text)', whiteSpace: 'nowrap' }}>{status}</span>
      )}
      {!!code && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{code}</span>}
      <span style={{ fontFamily: MONO, fontSize: 10, color: on ? 'var(--accent)' : 'var(--text-faint)' }}>
        {surface === 'app' ? 'APP' : 'WEB'}
      </span>
    </span>
  )
}

/* ── первичная проверка ─────────────────────────────────────────────────── */
function PrimaryReviewDialog({ set, onDone, onClose }) {
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const send = async (verdict) => {
    setBusy(true); setErr('')
    try {
      await api.post(`/launch-prep/set/${set.id}/primary-review`, { verdict, reason }, auth())
      onDone()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить'); setBusy(false) }
  }

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={{ ...SHEET, width: 'min(520px, 96vw)' }}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Первичная проверка · креатив №{set.no}</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.55 }}>
          Материал сверяется с требованиями площадок до отправки. Вердикт неизменяем:
          доработка — это новая версия, а не правка этой.
        </div>
        <div style={{ ...CAP, marginTop: 16, marginBottom: 6 }}>причина доработки</div>
        <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)}
          placeholder="обязательна, если отправляем на доработку"
          style={{ ...inp, width: '100%', resize: 'vertical', fontFamily: UI, lineHeight: 1.5 }} />
        {!!err && <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={{ ...btn(false), color: 'var(--dot-overdue)', borderColor: 'var(--dot-overdue)' }}
            disabled={busy} onClick={() => send('на доработку')}>На доработку</button>
          <button style={btn(true)} disabled={busy} onClick={() => send('ок')}>Материал годен</button>
        </div>
      </div>
    </div>
  )
}

/* ── вердикт площадки ───────────────────────────────────────────────────── */
function PairVerdictDialog({ rec, onDone, onClose }) {
  /* Три исхода, а не два. «Правки» просят новую версию и оставляют площадку в кампании;
     «отказ» закрывает её для этой кампании совсем — нет товара, ограничения по бренду.
     Списки причин у них разные: смесь «тяжёлый файл» и «товара нет в наличии» заставляла
     бы выбирать из несравнимого. */
  const OUTCOMES = [
    { key: 'ок', label: 'Согласовано', tone: 'var(--income)', src: null },
    { key: 'на доработку', label: 'Правки', tone: 'var(--dot-current-dz)', src: 'rework-reasons' },
    { key: 'отказ', label: 'Отказ', tone: 'var(--dot-overdue)', src: 'refusal-reasons' },
  ]
  const [verdict, setVerdict] = useState('ок')
  const [reason, setReason] = useState('')
  const [lists, setLists] = useState({})
  const [vpop, setVpop] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const cur = OUTCOMES.find(o => o.key === verdict)

  /* Согласовать при висящем запросе посадочной нельзя — ядро такой «ок» отклоняет
     (`apply_platform_verdict`). Запрет повторён здесь не для надёжности, а чтобы
     причина была видна ДО нажатия: иначе аккаунт узнаёт о ней из красной строки,
     набрав вердикт со слов площадки. Отрицательных исходов запрет не касается. */
  const urlHeld = rec.url_state === 'запрошена' && verdict === 'ок'

  useEffect(() => {
    if (!cur.src || lists[cur.src]) return
    api.get(`/launch-prep/${cur.src}`, auth())
      .then(r => setLists(l => ({ ...l, [cur.src]: r.data.items || [] })))
      .catch(() => {})
  }, [cur.src, lists])

  const send = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/launch-prep/pair/${rec.pair_id}/verdict`,
        { verdict, reason }, auth())
      onDone(r.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить'); setBusy(false) }
  }

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={{ ...SHEET, width: 'min(540px, 96vw)' }}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Ответ площадки · {rec.name}</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.55 }}>
          {urlHeld
            ? 'Мы ждём от этой площадки посадочную страницу. Пока ссылки нет, «ок» '
              + 'запрещён: пара сразу получила бы код в DSP, а вести рекламу некуда. '
              + 'Ссылка вписывается в строке площадки — колонка «посадочная».'
            : verdict === 'ок'
            ? 'Пара срастается и получает код для DSP. Вердикт неизменяем.'
            : verdict === 'на доработку'
              ? 'Площадка остаётся в кампании и ждёт новую версию — она соберётся отдельно и уйдёт только ей.'
              : 'Площадка выпадает из кампании: новая версия ей не поможет, и следующие креативы к ней не пойдут.'}
        </div>

        <div style={{ display: 'flex', gap: 7, marginTop: 15 }}>
          {OUTCOMES.map(o => (
            <span key={o.key} onClick={() => { setVerdict(o.key); setReason('') }}
              style={{ cursor: 'pointer', flex: 1, textAlign: 'center', padding: '7px 0',
                borderRadius: 9, fontSize: 12.5, fontWeight: 700,
                border: `1px solid ${verdict === o.key ? o.tone : 'var(--border-card)'}`,
                background: verdict === o.key ? 'var(--bg-subtle)' : 'transparent',
                color: verdict === o.key ? o.tone : 'var(--text-muted)' }}>
              {o.label}
            </span>
          ))}
        </div>

        {!!cur.src && (
          <>
            <div style={{ ...CAP, marginTop: 16, marginBottom: 6 }}>
              причина {verdict === 'отказ' ? 'отказа' : 'доработки'}
            </div>
            <PickValue value={reason} placeholder="выбрать или добавить" size={13}
              onOpen={e => setVpop({
                rect: e.currentTarget.getBoundingClientRect(),
                title: verdict === 'отказ' ? 'Причина отказа' : 'Причина доработки',
                value: reason, clearLabel: '— не указана —',
                options: (lists[cur.src] || []).map(r => ({ value: r.name, label: r.name })),
              })} />
          </>
        )}

        {!!err && <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={btn(true)} onClick={send}
            disabled={busy || urlHeld || (!!cur.src && !reason.trim())}>
            Сохранить ответ
          </button>
        </div>

        {/* Поповер — потомок модалки, иначе уходит под неё по z-index. */}
        {!!vpop && (
          <ValuePopover {...vpop}
            onPick={v => { setReason(v || ''); setVpop(null) }}
            onAddNew={async (name) => {
              const r = await api.post(`/launch-prep/${cur.src}`, { name }, auth())
              setLists(l => ({ ...l, [cur.src]: [...(l[cur.src] || []), r.data] }))
              setReason(r.data.name)
              setVpop(null)
            }}
            onClose={() => setVpop(null)} />
        )}
      </div>
    </div>
  )
}

/* Кнопка-пиктограмма «заявка на пиксели Weborama».

   Объявлена на модульном уровне, как и остальные помощники этого файла: компонент,
   созданный внутри рендера, пересоздаётся на каждый ввод.

   Отказ показывается ТЕКСТОМ рядом, а не alert'ом: причины у этого файла бытовые — нет
   бренда у сделки, нет домена у площадки, — и чинятся за минуту, если сказать, какая
   именно. */
function WeboramaRequestButton({ set }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  if (!set?.recipients?.length) return null
  return (
    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      {!!err && (
        <span style={{ fontSize: 11.5, color: 'var(--dot-overdue)', maxWidth: 420 }}>{err}</span>
      )}
      <button title="Скачать заявку на пиксели Weborama (Excel для менеджера)"
        disabled={busy} onClick={async () => {
          setBusy(true); setErr('')
          await downloadFile(`/launch-prep/set/${set.id}/weborama-request`, null, setErr)
          setBusy(false)
        }}
        style={{ ...btn(false), padding: '5px 10px', display: 'inline-flex',
          alignItems: 'center', gap: 6, fontSize: 12 }}>
        <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 11 }}>WB</span>
        <span aria-hidden="true">⤓</span>
      </button>
    </span>
  )
}

/* ── предпросмотр креатива ──────────────────────────────────────────────── */
/* Взято с демо-стенда (docs/Стенд_согласования_креативов.html), но с настоящими файлами.
   Там баннер был вшит в страницу строкой — потому и крутился без сервера.

   ЧТО МОЖНО ПОКАЗАТЬ ПРЯМО ЗДЕСЬ, А ЧТО НЕТ:
     · картинка — можно и безопасно: разметка её не исполняет. Тянем с авторизацией и
       отдаём в img через blob (наш CSP это разрешает: img-src 'self' data: blob:);
     · ОДИН самодостаточный .html — можно: текст уходит в srcDoc изолированной рамки
       с sandbox="allow-scripts" и БЕЗ allow-same-origin, то есть в чужой origin,
       откуда не достать ни куки, ни хранилище страницы;
     · .zip — нельзя без распаковки: баннер внутри ссылается на свои файлы
       относительными путями, а blob-ссылки такие пути не разрешают. Предпросмотр
       архива приедет вместе с песочницей на отдельном домене — там же, где баннер
       будет раздаваться паблишеру. */
/* Пять типовых пропорций — те же, что на демо-стенде. Адаптивный баннер (а таких
   большинство: `ad.size` у них «0,0») смотрят именно так — прикладывая к местам, куда он
   поедет. Баннер с ОБЪЯВЛЕННЫМ размером показывается только в своём: класть фикс в чужую
   рамку — значит смотреть на то, чего в размещении не будет. */
/* ВТОРАЯ КОПИЯ ЭТОГО СПИСКА — `cabinet-frontend/lib/preview.js`, и она обязана
   совпадать. Кабинет отдельный пакет и отдельный контейнер, общего сборщика с нами у
   него нет по построению внешнего контура: свести списки в один модуль нельзя, а
   сверить автоматически негде — контейнер нашего фронта кабинета не видит.
   Расхождение выглядит как спор «у нас всё ровно / у вас баннер обрезан», в котором
   обе стороны правы. Правя список — правь оба файла одним заходом.
   Сверено 30.08.2026: совпадают. */
const STOCK_SIZES = [[300, 600], [240, 400], [640, 100], [970, 250],
  [1000, 150], [1200, 150], [320, 50]]

const RATIO_PX = (ratio) => {
  const m = /^(\d{2,4})\s*[x×]\s*(\d{2,4})$/i.exec((ratio || '').trim())
  return m ? [Number(m[1]), Number(m[2])] : null
}

/** `htmlSource` — готовая разметка вместо файла из хранилища.
 *
 *  Понадобилось демо-стенду DSP (06.09.2026): там баннер ещё не файл в нашей базе, а
 *  строка, только что вернувшаяся от загрузчика DSP. Компонент один на все
 *  места: вторая реализация предпросмотра означала бы, что проверяющий и трафик смотрят
 *  на баннер по-разному, а спор «у меня всё ровно» разрешить нечем. Отличается только
 *  источник разметки — не показ. */
export function CreativePreview({ files, startId, set, canApprove, onReviewed, onClose,
                                  htmlSource = null, sandboxUrl = null,
                                  title = 'Предпросмотр креатива' }) {
  const [curId, setCurId] = useState(startId)
  /* СВЕЖИЙ ДОКУМЕНТ НА КАЖДЫЙ ПОКАЗ. Баннер играет свою анимацию ОДИН раз
     (`animation: … 1` + `animation-fill-mode: forwards`) и застывает на последнем
     кадре — это его собственное устройство, не наше. Пока адрес рамки не менялся,
     браузер переиспользовал уже отработавший документ, и со второго-третьего открытия
     человек видел застывшую картинку. Выглядит это как «предпросмотр сломался».
     Метка времени берётся на КАЖДОЕ открытие и на каждое переключение файла. */
  const [nonce] = useState(() => Date.now())
  const fresh = (u) => (u ? u + (u.includes('?') ? '&' : '?') + 'v=' + nonce + '-' + curId : u)
  const [blob, setBlob] = useState(null)
  const [html, setHtml] = useState(null)
  const [err, setErr] = useState('')
  const stageRef = useRef(null)
  const [avail, setAvail] = useState(720)
  const [sizeIdx, setSizeIdx] = useState(0)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewErr, setReviewErr] = useState('')

  const review = async (verdict) => {
    if (verdict === 'на доработку') { onReviewed(verdict); return }   // причина обязательна — спросим в форме
    setReviewBusy(true); setReviewErr('')
    try {
      await api.post(`/launch-prep/set/${set.id}/primary-review`, { verdict, reason: '' }, auth())
      onReviewed(verdict)
    } catch (e) { setReviewErr(e.response?.data?.detail || 'Не удалось сохранить'); setReviewBusy(false) }
  }

  const cur = (files || []).find(f => f.id === curId) || (files || [])[0]
  const ext = (cur?.name || '').toLowerCase().split('.').pop()
  const isImg = !htmlSource && ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
  const isHtml = !!htmlSource || ext === 'html'

  useEffect(() => {
    let alive = true
    let url = null
    setBlob(null); setHtml(null); setErr('')
    // Разметку передали прямо — тянуть нечего.
    if (htmlSource) { setHtml(htmlSource); return }
    if (!cur || (!isImg && !isHtml)) return
    api.get(`/launch-prep/file/${cur.id}`, { ...auth(), responseType: 'blob' })
      .then(async r => {
        if (!alive) return
        if (isHtml) setHtml(await r.data.text())
        else { url = URL.createObjectURL(r.data); setBlob(url) }
      })
      .catch(() => { if (alive) setErr('Не удалось загрузить файл') })
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [cur, isImg, isHtml, htmlSource])

  useEffect(() => {
    const el = stageRef.current
    if (el) setAvail(Math.max(240, el.clientWidth - 28))
  }, [curId, sizeIdx])

  const own = RATIO_PX(cur?.ratio)
  const sizes = own ? [own] : STOCK_SIZES
  const wh = sizes[Math.min(sizeIdx, sizes.length - 1)]
  const k = wh ? Math.min(1, avail / wh[0]) : 1
  /* Сцена держит высоту САМОГО ВЫСОКОГО из доступных размеров и не меняется при
     переключении: иначе окно прыгает на сотни пикселей между 300×600 и 320×50, кнопки
     проверки уезжают из-под курсора, и сравнить два размера подряд невозможно —
     страница под ними ходит. */
  const stageH = Math.max(160, ...sizes.map(([w, h]) => Math.round(Math.min(1, avail / w) * h)))

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={{ ...SHEET, width: 'min(1000px, 96vw)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>{title}</span>
          <button style={{ ...btn(false), marginLeft: 'auto' }} onClick={onClose}>Закрыть</button>
        </div>

        {/* Вкладки — ПРОПОРЦИИ, как на стенде, а не файлы: у креатива файл один, а
            посмотреть его надо в тех местах, куда он поедет. */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12,
          alignItems: 'center' }}>
          {sizes.map(([w, h], i) => {
            const on = i === Math.min(sizeIdx, sizes.length - 1)
            return (
              <span key={`${w}x${h}`} onClick={() => setSizeIdx(i)}
                style={{ cursor: 'pointer', fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
                  padding: '5px 12px', borderRadius: 100,
                  border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
                  background: on ? 'var(--accent)' : 'var(--bg-subtle)',
                  color: on ? 'var(--bg-card)' : 'var(--text-secondary)' }}>
                {w}×{h}
              </span>
            )
          })}
          <span style={{ ...CAP, marginLeft: 6 }}>
            {own ? 'размер объявлен в баннере' : 'баннер адаптивный'}
          </span>
          {files.length > 1 && (
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
              {files.map(f => (
                <span key={f.id} onClick={() => setCurId(f.id)}
                  title={f.name}
                  style={{ cursor: 'pointer', fontSize: 10.5, padding: '4px 9px',
                    borderRadius: 8, border: '1px solid var(--border-card)',
                    background: f.id === cur?.id ? 'var(--bg-subtle)' : 'transparent',
                    color: f.id === cur?.id ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                  {f.name.length > 18 ? f.name.slice(0, 17) + '…' : f.name}
                </span>
              ))}
            </span>
          )}
        </div>

        <div ref={stageRef} style={{ marginTop: 14, padding: 14, borderRadius: 12,
          background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          overflowX: 'auto', height: stageH + 28, boxSizing: 'border-box' }}>
          {!!err && <span style={{ fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</span>}

          {!err && isImg && !blob && (
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>загрузка…</span>
          )}
          {!err && isImg && !!blob && (
            <img src={blob} alt={cur?.name || 'креатив'} style={{ maxWidth: '100%', display: 'block', background: 'var(--bg-card)' }} />
          )}

          {!err && isHtml && html === null && (
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>загрузка…</span>
          )}
          {!err && isHtml && html !== null && (
            <div style={{ width: wh ? Math.round(wh[0] * k) : '100%',
              height: wh ? Math.round(wh[1] * k) : 420, overflow: 'hidden' }}>
              {/* Чужой исполняемый код — только в изолированной рамке и без
                  allow-same-origin: тогда у неё свой origin, и до нашей сессии не дотянуться.

                  Если разметка положена в ПЕСОЧНИЦУ — берём её оттуда, а не через srcdoc.
                  Разница не косметическая: srcdoc наследует НАШ CSP, а баннер после
                  загрузчика DSP ссылается на его CDN, и `base-uri 'self'` вместе с
                  `img-src 'self'` показали бы пустую рамку. У домена песочницы таких
                  ограничений нет — она ровно для чужого кода и заведена. */}
              <iframe {...(sandboxUrl ? { src: fresh(sandboxUrl) } : { srcDoc: html })}
                sandbox="allow-scripts" title={'Креатив ' + (cur?.ratio || '')}
                style={{ border: 0, display: 'block', background: 'var(--bg-card)',
                  width: wh ? wh[0] : '100%', height: wh ? wh[1] : 420,
                  transform: `scale(${k})`, transformOrigin: 'top left' }} />
            </div>
          )}

          {/* Архив крутится ИЗ ПЕСОЧНИЦЫ — с отдельного домена, где нет ни нашей
              сессии, ни нашего API. Через blob он бы не заработал: внутри баннер
              ссылается на свои файлы относительными путями. */}
          {!err && !isImg && !isHtml && !!cur?.sandbox_url && (
            <div style={{ width: wh ? Math.round(wh[0] * k) : '100%',
              height: wh ? Math.round(wh[1] * k) : 420, overflow: 'hidden' }}>
              <iframe key={curId} src={fresh(cur.sandbox_url)} title={'Креатив ' + (cur?.ratio || '')}
                style={{ border: 0, display: 'block', background: 'var(--bg-card)',
                  width: wh ? wh[0] : '100%', height: wh ? wh[1] : 420,
                  transform: `scale(${k})`, transformOrigin: 'top left' }} />
            </div>
          )}

          {!err && !isImg && !isHtml && !cur?.sandbox_url && (
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)', maxWidth: 520, textAlign: 'center', lineHeight: 1.55 }}>
              {ext === 'zip'
                ? 'Архив не распакован в песочницу. Так бывает у файлов, загруженных до её появления: перезалейте архив — распаковка идёт при загрузке, и негодный архив отклоняется сразу.'
                : 'Для этого типа файла предпросмотра пока нет — скачайте его, чтобы посмотреть.'}
            </span>
          )}
        </div>

        {/* АДРЕС РАМКИ — ССЫЛКОЙ. Белая рамка выглядит одинаково при трёх разных
            причинах: баннер не загрузился, загрузился и ничего не рисует, или его не
            пустил браузер. Различает их один клик — открыть ровно то же в отдельной
            вкладке, — но до 18.09.2026 адрес был спрятан внутри iframe, и добыть его
            можно было только через инструменты разработчика. */}
        {!err && !!(cur?.sandbox_url || sandboxUrl) && (
          <div style={{ marginTop: 8, fontSize: 11, fontFamily: MONO }}>
            <a href={fresh(cur?.sandbox_url || sandboxUrl)} target="_blank" rel="noreferrer"
              style={{ color: 'var(--accent)', textDecoration: 'none' }}>
              открыть баннер в отдельной вкладке ↗
            </a>
            <span style={{ color: 'var(--text-faint)', marginLeft: 8 }}>
              рисуется там, а здесь пусто — дело в рамке, а не в баннере
            </span>
          </div>
        )}

        <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {isHtml
            ? 'Баннер крутится в изолированной рамке без доступа к странице.'
              + (k < 1 ? ` Масштаб ${Math.round(k * 100)} % — размер ${wh[0]}×${wh[1]} не помещается в окно.` : '')
            : cur?.sandbox_url
              ? 'Баннер запущен в тестовой среде.'
              : 'Файл тянется с авторизацией и живёт только в этой вкладке.'}
          {/* Блокировщик принимает баннер типового размера за рекламу и режет его
              картинки: остаётся пустой фон, и выглядит это как поломка у нас (владелец
              25.09.2026 — поймал на своём браузере). Та же подпись в кабинете площадки. */}
          {(isHtml || !!cur?.sandbox_url) && (
            <><br />Если баннер не отображается, проверьте блокировщики рекламы или VPN.</>
          )}
        </div>

        {/* Первичная проверка стоит ЗДЕСЬ, а не отдельной кнопкой в блоке (владелец,
            27.08.2026): подтверждать материал, не посмотрев на него, слишком легко, и
            так в отправку уезжает не тот архив. Кнопка «Всё работает» доступна ровно
            там, где на креатив только что посмотрели.

            Честная граница: у архива предпросмотр пока показывает лишь то, что это
            архив, — до песочницы «работает» подтверждается глазами вне системы. */}
        {!!(canApprove && set && !set.primary_review) && (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14,
            paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
            {!!reviewErr && (
              <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--dot-overdue)' }}>{reviewErr}</span>
            )}
            <button style={{ ...btn(false), color: 'var(--dot-overdue)', borderColor: 'var(--dot-overdue)' }}
              disabled={reviewBusy} onClick={() => review('на доработку')}>На доработку</button>
            <button style={btn(true)} disabled={reviewBusy}
              onClick={() => review('ок')}>Всё работает</button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── подтверждение удаления ─────────────────────────────────────────────── */
function ConfirmDelete({ set, onYes, onClose }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={{ ...SHEET, width: 'min(440px, 96vw)' }}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Точно удалить креатив №{set.no}?</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.55 }}>
          Это обнулит заполненные данные: файлы, первичную проверку и выбор площадок.
          Отменить будет нечем.
        </div>
        {!!err && <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={{ ...btn(false), borderColor: 'var(--dot-current-dz)', color: 'var(--dot-current-dz)', fontWeight: 700 }}
            disabled={busy}
            onClick={async () => {
              setBusy(true); setErr('')
              try { await onYes() } catch (e) {
                setErr(e.response?.data?.detail || 'Не удалось удалить'); setBusy(false)
              }
            }}>Удалить</button>
        </div>
      </div>
    </div>
  )
}

/* ── маркер ─────────────────────────────────────────────────────────────── */
function EridBlock({ set, onChanged }) {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [foreign, setForeign] = useState('')
  const [marking, setMarking] = useState(null)
  // Подтверждение выпуска маркера. Держим состоянием, а не window.confirm: в окне
  // надо показать КОНТУР и слово «необратимо», а системный диалог этого не умеет.
  const [askErid, setAskErid] = useState(false)
  // Право на отправку в ОРД. Самое необратимое действие в системе не имело клиентской
  // проверки вовсе: кнопка была видна и нажималась всеми, кто видит комплект, а отказ
  // приходил ответом 403 уже ПОСЛЕ подтверждения с контуром и словом «необратимо».
  // Сервер гейтит ручку под `ord_submit:create` (routers/launch_prep.py), здесь тот же
  // ключ. `null` — «ещё не знаю»: снимок прав живёт в localStorage и на сервере его нет,
  // а `false` с первого кадра прятал бы кнопку у того, кому она положена.
  const [maySubmit, setMaySubmit] = useState(null)
  useEffect(() => { setMaySubmit(can(getPermissions(), 'ord_submit', 'create')) }, [])

  const reload = useCallback(() => {
    api.get(`/launch-prep/set/${set.id}/erid-readiness`, auth())
      .then(r => setSt(r.data)).catch(() => {})
  }, [set.id])
  useEffect(() => { reload() }, [reload, set.erid])

  const call = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); onChanged() } catch (e) {
      setErr(e.response?.data?.detail || 'Не получилось')
    }
    setBusy(false)
  }

  if (!st) return null
  const own = set.erid_source !== 'площадки'

  return (
    <div style={{ marginTop: 12, padding: '11px 13px', borderRadius: 11,
      background: set.erid ? 'var(--income-tint)' : 'var(--bg-subtle)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={CAP}>маркер</span>
        {!!set.erid && (
          <span style={{ fontFamily: MONO, fontSize: 12.5, color: 'var(--income)' }}>{set.erid}</span>
        )}
        {!!set.erid && !own && (
          <span style={{ ...CAP, color: 'var(--text-faint)' }}>выпущен площадкой</span>
        )}
        {!!set.ord_status && (
          <span style={{ fontFamily: MONO, fontSize: 10.5,
            color: /Error/.test(set.ord_status) ? 'var(--dot-overdue)' : 'var(--text-muted)' }}>
            {set.ord_status}
          </span>
        )}
        {/* Справка, а не условие: порог согласовавших снят 31.08.2026, и «нужно N»
            отсюда ушло вместе с ним. Само число ответов осталось — оно отвечает на
            «сколько площадок уже высказалось», и это по-прежнему спрашивают. */}
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>
          согласовали {st.agreed} из {st.sent}
        </span>
      </div>

      {/* Две ветки отказа реестра лечатся по-разному, поэтому текст показывается как есть:
          ошибка регистрации — материалом или полями, ошибка скачивания — перезаливкой. */}
      {!!set.ord_error && (
        <div style={{ marginTop: 7, fontSize: 12, color: 'var(--dot-overdue)' }}>{set.ord_error}</div>
      )}

      {/* Блокер, который можно починить не уходя, — нажимаемый. Раньше «не заполнен
          код ККТУ» был просто текстом, и правился он в справочнике: шесть шагов туда
          и обратно из места, где нехватку и видно. Опознаём по КОДУ, а не по фразе. */}
      {!set.erid && !!st.blockers?.length && (
        <div style={{ marginTop: 7, fontSize: 12, color: 'var(--text-muted)' }}>
          не хватает:{' '}
          {st.blockers.map((b, i) => (
            <span key={b.code || i}>
              {i > 0 && ' · '}
              {b.code === 'kktu' && st.brand?.id ? (
                <span onClick={() => setMarking(st.brand)}
                  title="Открыть маркировку бренда — код уйдёт в каждый креатив этой сделки"
                  style={{ cursor: 'pointer', color: 'var(--accent)',
                    borderBottom: '1px dashed var(--accent)' }}>
                  {b.text}
                </span>
              ) : b.text}
            </span>
          ))}
        </div>
      )}

      {/* Строки «ккту … · изменить» здесь больше нет (31.08.2026). Код принадлежит
          БРЕНДУ, а не комплекту, и задаётся один раз в блоке сборки ОРД на карточке
          сделки — там же, где видно, маркирован ли каждый креатив. Здесь она рисовалась
          в каждом комплекте (у сделки их бывает десяток), повторяла одно и то же и
          выглядела настройкой креатива, хотя правила бренд целиком.

          Причина нехватки осталась выше блокером: он появляется только когда кода нет,
          то есть это не шум, а объяснение, почему маркер не выпускается. */}

      {/* Выпуск маркера НЕОБРАТИМ: боевую запись в ЕРИР не отозвать, а на демо-контуре
          остаётся мусор, который потом путает сверку. До 11.09.2026 это был один клик
          без вопроса, и контур на экране не показывался вовсе. */}
      {askErid && (() => {
        const prod = (st.ord_env || '').toLowerCase() === 'prod'
        return (
          <Modal width={520} title="Выпустить ЕРИД" onClose={() => setAskErid(false)}
            summary={`Комплект №${set.no ?? set.id} · площадок в отправке: ${st.sent ?? 0}`}
            footer={(
              <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button style={btn(false)} onClick={() => setAskErid(false)}>Отмена</button>
                <button style={btn(true)} disabled={busy}
                  onClick={() => { setAskErid(false); call(() => api.post(`/launch-prep/set/${set.id}/erid`, {}, auth())) }}>
                  {prod ? 'Выпустить в БОЕВОЙ реестр' : 'Выпустить на демо-контуре'}
                </button>
              </span>
            )}>
            <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
              <div style={{ padding: '9px 12px', borderRadius: 9, fontSize: 12.5,
                background: prod ? 'var(--danger-tint)' : 'var(--warning-tint)',
                color: prod ? 'var(--danger)' : 'var(--warning-text)' }}>
                Контур ОРД: <b>{st.ord_env || 'неизвестен'}</b>.{' '}
                {prod
                  ? 'Запись уходит в реестр НАВСЕГДА — отозвать её нельзя.'
                  : 'Это тренировочный контур: объект создастся у оператора и останется там мусором.'}
              </div>
              <div>Маркер выпускается на весь комплект сразу и проставляется всем площадкам,
                которые его получили. Повторный выпуск сервер отклонит.</div>
              <div style={{ color: 'var(--text-faint)', fontSize: 11.5 }}>
                Маркер приходит сразу, а регистрация в реестре идёт асинхронно — статус
                подтянется кнопкой «Обновить статус».</div>
            </div>
          </Modal>
        )
      })()}

      {!!marking && (
        <BrandMarkingDialog brand={marking} onClose={() => setMarking(null)}
          onSave={async (payload) => {
            await saveBrandMarking(marking.id, payload)
            setMarking(null)
            reload()
          }} />
      )}

      {!!err && <div style={{ marginTop: 7, fontSize: 12, color: 'var(--dot-overdue)' }}>{err}</div>}

      <div style={{ display: 'flex', gap: 7, marginTop: 9, flexWrap: 'wrap', alignItems: 'center' }}>
        {!set.erid && !st.blockers?.length && maySubmit !== false && (
          <button style={{ ...btn(true), padding: '4px 11px', fontSize: 12 }}
            disabled={busy || maySubmit !== true}
            onClick={() => setAskErid(true)}>
            Выпустить ЕРИД
          </button>
        )}
        {!set.erid && !st.blockers?.length && maySubmit === false && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Комплект готов к выпуску ЕРИД — права на отправку в ОРД у вас нет
          </span>
        )}
        {!!set.erid && own && (
          <button style={{ ...btn(false), padding: '4px 11px', fontSize: 12 }} disabled={busy}
            title="Маркер приходит сразу, а регистрация в реестре идёт асинхронно"
            onClick={() => call(() => api.post(`/launch-prep/set/${set.id}/erid/refresh`, {}, auth()))}>
            Обновить статус
          </button>
        )}
        {!set.erid && (
          <>
            <input style={{ ...inp, width: 190, fontFamily: MONO, fontSize: 12, padding: '5px 9px' }}
              placeholder="чужой ЕРИД" value={foreign} onChange={e => setForeign(e.target.value)} />
            <button style={{ ...btn(false), padding: '4px 11px', fontSize: 12 }}
              disabled={busy || !foreign.trim()}
              title="У саморекламы маркер выпускает площадка — он вводится руками"
              onClick={() => call(() => api.put(`/launch-prep/set/${set.id}/erid`,
                { erid: foreign.trim() }, auth()))}>
              Внести
            </button>
          </>
        )}
      </div>
    </div>
  )
}

/* ── строка площадки внутри креатива ────────────────────────────────────── */
/* Раскладка по референсу демостенда: строка на площадку, колонки справа. До отправки
   слева галочка выбора, после — она уступает место точке-маркеру состояния. */
/* Состояние во внешней системе одной буквой. Цвет — значение, подсказка — подробности.

   «—» и «нет» РАЗНЫЕ: «нет» зовёт нажать кнопку, «—» говорит, что делать нечего
   (площадка из тех 10%, что крутят сами). Серый и пунктир различают их без слов. */
/* Плашки внешних систем (`EXT_TONE`, `ExtChip`) переехали в общий кит 09.09.2026:
   те же буквы нужны дашборду трафика, а вторая копия стилей разошлась бы с первой. */

/* Колонки строки получателя. ЕРИД стоит СРАЗУ за статусом: как только строка доходит
   до «ерид получен», маркер — следующее, что от неё нужно, и берёт его тот, кто
   заводит кампанию в DSP, а не тот, кто согласовывал.

   Все доли — `minmax(0,…fr)`, а не фиксированные минимумы. Минимум в колонке означает
   «не сжимай меня», и семь таких колонок в сумме перерастали блок: таблица уезжала
   в горизонтальную прокрутку внутри карточки. Ноль слева разрешает колонке сжиматься
   меньше собственного содержимого — при условии, что содержимое обрезается само
   (`minWidth: 0` + `ellipsis` внутри). Посадочная страница от сжатия не страдает:
   она раскрывается на всю строку по клику. */
/* Статус и ЕРИД — ФИКСИРОВАННЫЕ: в них короткое содержимое известной длины, и на
   широком экране доля растягивала бы пустоту вокруг плашки. Растут те две колонки,
   которым ширина действительно нужна, — имя площадки и посадочная страница. */
const R_COLS = '20px minmax(0,1fr) 30px minmax(0,1.6fr) 116px 84px 88px'

/* Тестовая ссылка нацеливания. По ней трафик открывает сайт до старта и видит рекламу,
   которой в обычном браузере ещё нет.

   ДВА ПУТИ, И ГЛАВНЫЙ — КНОПКА. Нацеливание заводится на ТЕСТОВОГО КЛИЕНТА (владелец
   12.09.2026), а не на наш креатив, поэтому ссылку можно выпустить когда угодно, в том
   числе на согласовании. Кнопка просит у сервера свежую и открывает её.

   Выпущенную ссылку НЕ ХРАНИМ: замер 12.09.2026 — она живёт ровно 48 часов, а
   согласование идёт днями. Сохранённая показала бы «время действия истекло» вместо
   баннера. Поле ниже остаётся для ручного случая и правится после отправки: в
   согласованный материал ссылка не входит. */
function TargetingUrl({ set, canEdit, onSave }) {
  const [v, setV] = useState(set.test_targeting_url || '')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { setV(set.test_targeting_url || '') }, [set.test_targeting_url])

  // Вкладку открываем СИНХРОННО по клику, а адрес подставляем после ответа: окно,
  // открытое из `await`, блокировщик всплывающих окон считает непрошеным и режет.
  const aim = async () => {
    setErr('')
    const tab = window.open('', '_blank')
    setBusy(true)
    try {
      const r = await api.post(`/launch-prep/set/${set.id}/targeting-link`, {}, auth())
      if (tab) tab.location = r.data.url
      else window.location.href = r.data.url
    } catch (e) {
      if (tab) tab.close()
      setErr(e?.response?.data?.detail || 'Не удалось выпустить ссылку нацеливания')
    } finally { setBusy(false) }
  }

  if (!editing) {
    return (
      <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', gap: 8,
        flexWrap: 'wrap' }}>
        <span style={{ ...CAP }}>ссылка нацеливания</span>
        {canEdit && (
          <button onClick={aim} disabled={busy}
            style={{ ...btn(false), padding: '4px 10px', fontSize: 12,
              cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1 }}
            title="Откроет страницу DSP: нажмите «Включить» и увидите баннер на сайте площадки. Ссылка живёт двое суток, поэтому выпускается заново при каждом нажатии">
            {busy ? 'выпускаю…' : 'нацелить на себя'}
          </button>
        )}
        {!!err && <span style={{ fontSize: 12, color: 'var(--expense)' }}>{err}</span>}
        {/* Пустое поле НЕ рисуем словом «не задана»: пока есть кнопка, пустота здесь
            означает «ручная ссылка не понадобилась», а не пробел в данных. */}
        {!!set.test_targeting_url && (
          <a href={set.test_targeting_url} target="_blank" rel="noreferrer"
            style={{ fontSize: 12.5, color: 'var(--accent)', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380 }}>
            {set.test_targeting_url}
          </a>
        )}
        {canEdit && (
          <span onClick={() => setEditing(true)}
            style={{ cursor: 'pointer', fontSize: 10.5, color: 'var(--text-muted)',
              borderBottom: '1px dashed var(--border-card)' }}>
            {set.test_targeting_url ? 'изменить свою' : 'задать свою'}
          </span>
        )}
      </div>
    )
  }
  return (
    <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ ...CAP }}>ссылка нацеливания</span>
      <input autoFocus value={v} onChange={e => setV(e.target.value)}
        placeholder="https://…"
        style={{ ...inp, flex: 1, fontSize: 12.5, padding: '5px 8px' }} />
      <span onClick={() => { onSave(set, v.trim()); setEditing(false) }}
        style={{ cursor: 'pointer', fontSize: 10.5, color: 'var(--income)' }}>сохранить</span>
      <span onClick={() => { setV(set.test_targeting_url || ''); setEditing(false) }}
        style={{ cursor: 'pointer', fontSize: 10.5, color: 'var(--text-faint)' }}>отмена</span>
    </div>
  )
}


// Иконка «есть текст»: три строки. Рисуем сами, а не берём эмодзи — она встаёт в ряд с
// моноширинными плашками и не прыгает по высоте между платформами.
const NoteIcon = () => (
  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor"
    strokeWidth="1.4" strokeLinecap="round">
    <path d="M2.5 3.5h7M2.5 6h7M2.5 8.5h4" />
  </svg>
)


function RecipientRow({ r, set, canEdit, canApprove, isAdmin, sent, onDrop, onTt, onUrl, onRequest, onVerdict, onRework, onMove, onShots }) {
  const [url, setUrl] = useState(r.advertiser_url || '')
  const [editing, setEditing] = useState(false)
  const [urlErr, setUrlErr] = useState('')
  // Причина правок раскрывается КЛИКОМ, а не подсказкой при наведении: это единственная
  // фраза, которая говорит, что именно чинить, и в hover её никто не находит (31.08.2026).
  const [noteOpen, setNoteOpen] = useState(false)
  // Площадка ушла в доработку — работает она теперь в другом комплекте, здесь остаётся
  // только следом. Гасим строку и убираем действия: иначе список показывает работу,
  // которой тут больше нет. Пара при этом жива, в ней вердикт с причиной.
  const gone = r.moved_to_no || null
  const note = r.reason || r.traffic_reason || ''
  const noteWho = r.reason ? (r.decided_by || 'площадка') : (r.traffic_reason ? 'трафик' : '')
  useEffect(() => { setUrl(r.advertiser_url || '') }, [r.advertiser_url])
  const status = rowStatus(r, set)
  const tone = ROW_STATUS[status] || 'var(--text-muted)'
  // Маркер у строки есть, когда она прошла его ступень, — а не когда он есть у комплекта.
  const hasErid = !!set.erid && ['ерид получен', 'ожидает старта', 'в размещении'].includes(status)

  /* Ссылку почти всегда КОПИРУЮТ, и копируют по-разному: из адресной строки — со
     схемой, из письма или таблицы — без неё («apteka.ru/product/1»). Сервер схему
     требует (это защита от «javascript:», а не придирка), поэтому дописываем её здесь,
     до отправки. Иначе обычная вставка отвечала отказом, поле сбрасывалось перезагрузкой,
     а причина оставалась внизу карточки — со стороны это ровно «ссылка не сохраняется».
     Строку со схемой не трогаем: подставлять https поверх http значило бы менять адрес. */
  const normalize = (v) => {
    const t = v.trim()
    if (!t || /^https?:\/\//i.test(t)) return t
    if (/^[a-z][a-z0-9+.-]*:/i.test(t)) return t      // иная схема — пусть откажет сервер
    return `https://${t}`
  }

  const commit = async () => {
    const next = normalize(url)
    if (next === (r.advertiser_url || '')) { setEditing(false); return }
    setUrl(next)
    // Ввод закрываем ТОЛЬКО после успеха: отказ с закрытым полем стирает набранное, и
    // человек не понимает, что произошло — надо переписывать заново вслепую.
    const ok = await onUrl(r, next)
    if (ok) { setUrlErr(''); setEditing(false) } else setUrlErr('не сохранилось')
  }

  return (
    <>
    <div style={{ display: 'grid', gridTemplateColumns: R_COLS, gap: 9, alignItems: 'center',
      padding: '7px 8px', borderBottom: noteOpen ? 'none' : '1px solid var(--border-row)',
      opacity: gone ? 0.5 : 1 }}>

      {sent || !canEdit ? (
        <span title={status} style={{ width: 7, height: 7, borderRadius: 2, background: tone, justifySelf: 'center' }} />
      ) : (
        <span onClick={() => onDrop(r.target_id)} title="Убрать площадку из списка"
          style={{ cursor: 'pointer', justifySelf: 'center', lineHeight: 1, fontSize: 13,
            fontWeight: 700, color: 'var(--text-faint)' }}>×</span>
      )}

      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>
            {r.surface_kind === 'app' ? 'APP' : 'WEB'}
          </span>
        </span>
        {/* Код размещения — под именем: он появляется только у сросшейся пары и уезжает
            в DSP, поэтому должен быть виден, но не занимать колонку до схождения. */}
        {!!r.pair_code && (
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--income)' }}>{r.pair_code}</span>
        )}
      </span>

      <span onClick={() => onTt(r)} title="Технические требования площадки"
        style={{ cursor: 'pointer', textAlign: 'center', fontFamily: MONO, fontSize: 10,
          padding: '3px 0', borderRadius: 7, border: '1px dashed var(--border-card)',
          color: r.tech_requirements ? 'var(--accent)' : 'var(--text-faint)' }}>ТТ</span>

      {/* Посадочная страница: своя у каждой площадки — карточка товара или подборка.

          В обычном виде это ТЕКСТ в узкой колонке, а ввод раскрывается по клику на всю
          оставшуюся ширину строки — `gridColumn: '4 / -1'`, то есть от своей колонки до
          конца сетки. Так сделано, потому что ссылка длинная, а колонка под неё,
          достаточная для чтения, распирала таблицу за края блока. Раскрытие через грид,
          а не через вычисленную ширину: пиксельная арифметика разъедется при первом же
          изменении соседней колонки.

          Заполненное правится ДВОЙНЫМ кликом (решение владельца 27.08.2026): одиночный
          по готовой ссылке слишком легко случается при прокрутке и выделении. Пустая
          открывается с одного — там портить нечего. */}
      {editing ? (
        <span style={{ gridColumn: '4 / -1', display: 'inline-flex', alignItems: 'center',
          gap: 6, minWidth: 0 }}>
          <input autoFocus
            style={{ ...inp, flex: 1, minWidth: 0, padding: '4px 8px', fontSize: 11.5, fontFamily: MONO }}
            placeholder={r.url_state === 'запрошена' ? 'ждём ответа площадки' : 'https://…'}
            value={url}
            onChange={e => { setUrl(e.target.value); if (urlErr) setUrlErr('') }}
            onBlur={commit}
            onKeyDown={e => {
              if (e.key === 'Enter') e.currentTarget.blur()
              // Escape возвращает прежнее значение: набранное сохраняется по выходу из
              // поля, и без отмены опечатка уезжала бы в базу вместе с кликом мимо.
              if (e.key === 'Escape') { setUrl(r.advertiser_url || ''); setUrlErr(''); setEditing(false) }
            }} />
          {/* Отказ — рядом с полем, а не внизу карточки: там его не видно, и отказ
              читается как «нажатие не сработало». */}
          {!!urlErr && (
            <span style={{ fontSize: 10.5, color: 'var(--dot-overdue)', whiteSpace: 'nowrap' }}>
              {urlErr}
            </span>
          )}
        </span>
      ) : (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0 }}
          onClick={() => { if (canEdit && !r.advertiser_url) setEditing(true) }}
          onDoubleClick={() => { if (canEdit) setEditing(true) }}
          title={r.advertiser_url || ''}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 11.5,
            cursor: canEdit ? 'text' : 'default',
            color: r.advertiser_url ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
            {r.advertiser_url
              || (r.url_state === 'запрошена' ? 'ждём ответа площадки' : 'ссылки нет')}
          </span>
          {canEdit && !r.advertiser_url && (
            <span onClick={e => { e.stopPropagation(); onRequest(r) }}
              title={r.url_state === 'запрошена' ? 'Запрос уже записан — открыть текст' : 'Запросить ссылку у площадки'}
              style={{ cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 10, padding: '3px 6px',
                borderRadius: 7, border: '1px solid var(--border-card)',
                color: r.url_state === 'запрошена' ? 'var(--dot-current-dz)' : 'var(--accent)' }}>
              {r.url_state === 'запрошена' ? 'ждём' : 'запросить'}
            </span>
          )}
        </span>
      )}

      {/* Остальные колонки при раскрытом вводе не рисуются: их место занял ввод. */}
      {!editing && (<>

      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        gap: 5, minWidth: 0 }}>
        <span title={status === 'у трафика'
                       ? 'Материал на проверке у трафика — площадке он ещё не уходил'
                       : status === 'у площадки' ? 'Трафик проверил, ждём ответа площадки' : ''}
          style={{ display: 'inline-flex', alignItems: 'center', flex: '1 1 auto',
          justifyContent: 'center', fontFamily: MONO, fontSize: 10, fontWeight: 700,
          padding: '3px 0', borderRadius: 7, minWidth: 0,
          color: gone ? 'var(--text-faint)' : tone,
          border: `1px solid ${gone ? 'var(--border-card)' : tone}`, whiteSpace: 'nowrap' }}>
          {gone ? `ушла в №${gone}` : status}
        </span>
        {/* Текст ответа — по клику. Иконка появляется только когда есть что показать. */}
        {!!note && (
          <span onClick={() => setNoteOpen(o => !o)}
            title={noteOpen ? 'Свернуть' : 'Показать текст ответа'}
            style={{ cursor: 'pointer', flex: '0 0 auto', display: 'inline-flex',
              alignItems: 'center', padding: 2, borderRadius: 5,
              color: noteOpen ? 'var(--accent)' : 'var(--text-muted)' }}>
            <NoteIcon />
          </span>
        )}
      </span>

      {/* Три внешние системы одной колонкой: маркировка, верификатор, закупка.
          Раньше здесь была строка ЕРИДа целиком — она занимала ширину, а читалась как
          «есть/нет» (владелец 09.09.2026: «ерид можно тоже показывать статусом»).
          Три плашки вместо одной строки и двух новых колонок: семь колонок уже
          перерастали блок, ещё две загнали бы таблицу в горизонтальную прокрутку.

          Значение несёт ЦВЕТ, подпись — букву системы, подсказка — подробности.
          Маркер по-прежнему копируется нажатием: им пользуются при заведении кампании. */}
      <span style={{ display: 'inline-flex', justifyContent: 'center', gap: 4, minWidth: 0 }}>
        <ExtChip letter="Е" tone={hasErid ? 'ok' : 'none'}
                 title={hasErid ? `ЕРИД ${set.erid} — нажмите, чтобы скопировать` : 'ЕРИД не выпущен'}
                 onClick={hasErid ? () => navigator.clipboard?.writeText(set.erid) : null} />
        <ExtChip letter="W" tone={EXT_TONE[r.external?.weborama?.state] || 'none'}
                 title={`Weborama: ${r.external?.weborama?.state || 'нет данных'}` +
                        (r.external?.weborama?.why ? ` — ${r.external.weborama.why}` : '')} />
        <ExtChip letter="D" tone={EXT_TONE[r.external?.dsp?.state] || 'none'}
                 title={`DSP: ${r.external?.dsp?.state || 'нет данных'}` +
                        (r.external?.dsp?.why ? ` — ${r.external.dsp.why}` : '')} />
      </span>

      <span style={{ display: 'inline-flex', justifyContent: 'flex-end', gap: 5 }}>
        {/* Ответ площадки записывается только после отмашки трафика: до неё материал ей
            не уходил, и сервер такой вердикт отклоняет. Кнопка не «спрятана» — она
            появляется тогда же, когда появляется предмет разговора. */}
        {/* Ответ за площадку и отметка «в эфир» доступны ТОЛЬКО администратору
            (решение владельца 31.08.2026): обе подменяют чужую зону ответственности —
            площадка отвечает в своём кабинете, факт запуска знает трафик. Оставлены как
            аварийный ход для площадок без кабинета, а не как обычный путь. */}
        {isAdmin && canApprove && sent && !r.verdict && r.traffic_verdict === 'ок' && !gone && (
          <span onClick={() => onVerdict(r)}
            style={{ cursor: 'pointer', fontSize: 10.5, padding: '3px 8px', borderRadius: 7,
              border: '1px solid var(--border-card)', color: 'var(--accent)' }}>Ответ</span>
        )}
        {!!r.files_count && (
          <span title={`Скриншотов: ${r.files_count} — скачать архивом`}
            onClick={() => onShots(r)}
            style={{ cursor: 'pointer', fontSize: 10.5, padding: '3px 8px', borderRadius: 7,
              border: '1px solid var(--income)', color: 'var(--income)', whiteSpace: 'nowrap' }}>
            скрины · {r.files_count}
          </span>
        )}
        {/* Новую версию собирают и после правок площадки, и после переделки от трафика:
            для аккаунта это одно и то же действие. Разница только в том, кто попросил, —
            она в подсказке. */}
        {canEdit && !gone
          && (r.verdict === 'на доработку' || r.traffic_verdict === 'на переделку')
          && r.state !== 'отказ площадки' && (
          <span onClick={() => onRework(r)}
            title={r.reason || (r.traffic_reason ? `Трафик: ${r.traffic_reason}` : null)
                   || 'Собрать новую версию для этой площадки'}
            style={{ cursor: 'pointer', fontSize: 10.5, padding: '3px 8px', borderRadius: 7,
              border: '1px solid var(--dot-overdue)', color: 'var(--dot-overdue)', whiteSpace: 'nowrap' }}>
            Доработка
          </span>
        )}
        {/* Отказ — тоже ответ, и у него тоже есть формулировка. Кнопка та же по месту и
            размеру, что «Доработка», но не зовёт к действию: делать с отказом нечего,
            читать — есть что. Без неё строка отказа выглядела пустой, а причина
            («Товара нет в наличии») была доступна только наведением на иконку.
            Раскрывает ту же строку с текстом, что и иконка примечания. */}
        {r.state === 'отказ площадки' && !!note && (
          <span onClick={() => setNoteOpen(o => !o)}
            title={noteOpen ? 'Свернуть причину' : 'Показать причину отказа'}
            style={{ cursor: 'pointer', fontSize: 10.5, padding: '3px 8px', borderRadius: 7,
              border: `1px solid ${noteOpen ? 'var(--danger-fg)' : 'var(--border-card)'}`,
              color: 'var(--danger-fg)', whiteSpace: 'nowrap' }}>
            Причина отказа
          </span>
        )}
        {isAdmin && canEdit && r.state === 'ерид получен' && !gone && (
          <span onClick={() => onMove(r.target_id, 'в размещении')} title="Кампания заведена и запущена"
            style={{ cursor: 'pointer', fontSize: 10.5, padding: '3px 8px', borderRadius: 7,
              border: '1px solid var(--income)', color: 'var(--income)' }}>в эфир</span>
        )}
      </span>
      </>)}
    </div>
    {noteOpen && !!note && (
      <div style={{ padding: '2px 8px 9px 26px', borderBottom: '1px solid var(--border-row)',
        display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)',
          whiteSpace: 'nowrap' }}>{noteWho}</span>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
          {note}
        </span>
      </div>
    )}
    </>
  )
}

/* ── креатив ────────────────────────────────────────────────────────────── */
function CreativeSet({ set, canEdit, canApprove, isAdmin, autoUpload, onUploaded, handlers }) {
  const fileRef = useRef(null)
  const letterRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [previewId, setPreviewId] = useState(null)
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState(set.title || '')
  useEffect(() => { setName(set.title || '') }, [set.title])

  const saveName = async () => {
    setNaming(false)
    if (name.trim() === (set.title || '')) return
    try {
      await api.put(`/launch-prep/set/${set.id}/title`, { title: name.trim() }, auth())
      handlers.reload()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось переименовать') }
  }

  const sent = !!set.sent_at

  /* «Прикрепить креатив» создаёт версию и сразу открывает выбор файла: кнопка называется
     действием, и между ней и файлом не должно быть лишнего шага. */
  useEffect(() => {
    if (autoUpload && !set.files.length) { fileRef.current?.click(); onUploaded() }
  }, [autoUpload, set.files.length, onUploaded])

  /** Письмо о правах на изображения — ОДНО на креатив.
   *
   *  Отдельная ручка, а не общий список файлов: там лежит материал, из состава которого
   *  выводится форма креатива для ОРД, и документ бы её испортил.
   *
   *  Прикрепить можно и после отправки (площадка спрашивает письмо как раз в ходе
   *  проверки), заменить и снять — нельзя: иначе не докажешь, при каком письме
   *  согласовали. Отказ приходит с сервера. */
  const uploadLetter = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setErr('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api.post(`/launch-prep/set/${set.id}/rights-letter`, form,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      handlers.reload()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось загрузить письмо') }
    setBusy(false)
  }

  const dropLetter = async () => {
    if (!window.confirm('Снять письмо о правах?')) return
    setBusy(true); setErr('')
    try {
      await api.delete(`/launch-prep/set/${set.id}/rights-letter`, auth())
      handlers.reload()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось снять письмо') }
    setBusy(false)
  }

  const upload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setErr('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api.post(`/launch-prep/set/${set.id}/files`, form,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      handlers.reload()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось загрузить') }
    setBusy(false)
  }

  const removeFile = async (id) => {
    setErr('')
    try { await api.delete(`/launch-prep/file/${id}`, auth()); handlers.reload() }
    catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось удалить') }
  }

  /* НАЗВАНИЕ СПРАШИВАЕМ ПЕРЕД ОТПРАВКОЙ, НО НЕ ТРЕБУЕМ (владелец 18.09.2026).

     Площадка видит креатив в своём кабинете как «Креатив №3 — <название>». Когда в одной
     кампании их несколько, без названия они различаются только номером, и человек на той
     стороне согласовывает вслепую. Спросить в момент отправки — единственный момент,
     когда это ещё дёшево: потом материал уже у неё.

     Принуждения нет намеренно: название — удобство, а не условие. Отказ («отправить
     так») уходит сразу, без второго нажатия. */
  const [askName, setAskName] = useState(null)   // {value} — открытый вопрос

  const doSend = async () => {
    setAskName(null)
    setBusy(true); setErr('')
    try {
      // Отправляем ВСЕМ, кто в списке: галочек больше нет — список и есть выбор
      // (владелец, 27.08.2026). Лишнюю площадку убирают крестиком до отправки.
      await api.post(`/launch-prep/set/${set.id}/send`,
        { target_ids: set.recipients.map(r => r.target_id) }, auth())
      handlers.reload()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось отправить') }
    setBusy(false)
  }

  const send = () => {
    if (!(set.title || '').trim()) { setAskName({ value: '' }); return }
    doSend()
  }

  const sendWithName = async () => {
    const v = (askName?.value || '').trim()
    if (!v) { doSend(); return }
    setBusy(true); setErr('')
    try {
      await api.put(`/launch-prep/set/${set.id}/title`, { title: v }, auth())
    } catch (e) { setErr(e.response?.data?.detail || 'Название не сохранилось') }
    setBusy(false)
    doSend()
  }

  /* Крестик СНИМАЕТ площадку из списка, а не снимает галочку: два разных смысла у
     одного места раньше путались — «не в этот раз» и «вообще не сюда». Снять можно
     только до отправки; после у получателя есть пары и вердикты, и сервер откажет. */
  const dropTarget = async (id) => {
    setErr('')
    try { await api.delete(`/launch-prep/set/${set.id}/target/${id}`, auth()); handlers.reload() }
    catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось убрать площадку') }
  }

  const ready = set.primary_review?.verdict === 'ок'

  return (
    <div style={BOX}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        {/* Номер статичен: он присвоен по порядку, на него ссылаются журнал и код пары.
            Название — подпись человека, правится двойным кликом. Одиночный по заголовку
            слишком легко случается при выделении текста. */}
        <span style={{ fontSize: 15, fontWeight: 700 }}>Креатив №{set.no}</span>
        {naming ? (
          <input autoFocus value={name} onChange={e => setName(e.target.value)}
            placeholder="название креатива"
            style={{ ...inp, width: 260, fontSize: 13, padding: '3px 8px' }}
            onBlur={saveName}
            onKeyDown={e => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') { setName(set.title || ''); setNaming(false) }
            }} />
        ) : (
          <span onDoubleClick={() => canEdit && setNaming(true)}
            title={canEdit
              ? (set.title ? 'Двойной клик — переименовать'
                : 'Двойной клик — назвать. Название видит площадка в своём кабинете и '
                  + 'по нему отличает креативы одной кампании друг от друга')
              : ''}
            /* ПУСТОЕ НАЗВАНИЕ ПОДСВЕЧЕНО. Не ошибка — недоделка, и цвет у неё
               предупреждающий, а не красный: отправить можно и так. */
            style={{ fontSize: 13.5, cursor: canEdit ? 'text' : 'default',
              color: set.title ? 'var(--text-secondary)' : 'var(--warning-text)',
              background: set.title ? 'transparent' : 'var(--warning-tint)',
              borderRadius: 7, padding: set.title ? 0 : '1px 8px' }}>
            {set.title || 'без названия'}
          </span>
        )}
        <span style={CAP}>{set.scope}{set.origin !== 'первичный' ? ` · ${set.origin}` : ''}</span>
        {!!set.form && <span style={CAP}>{FORM_LABEL[set.form] || set.form}</span>}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 9 }}>
          {/* Удаление оранжевым, а не красным: это не «сорвалось», а «переделываю с нуля».
              Отправленный креатив не удаляется — у него уже есть вердикты площадок, а у
              маркированного и запись в реестре, которую не отозвать; кнопка тогда гаснет
              и объясняет причину, а не исчезает. */}
          {canEdit && (
            <button
              style={{ ...btn(false), padding: '3px 9px', fontSize: 11,
                borderColor: sent ? 'var(--border-card)' : 'var(--dot-current-dz)',
                color: sent ? 'var(--text-faint)' : 'var(--dot-current-dz)',
                cursor: sent ? 'not-allowed' : 'pointer' }}
              disabled={sent}
              title={sent ? 'Отправленный креатив не удаляется — доработка это новая версия'
                : 'Удалить креатив вместе с файлами и выбором площадок'}
              onClick={() => handlers.confirmDelete(set)}>
              Удалить
            </button>
          )}
          <SetStateBadge state={set.state} erid={set.state === 'маркирован' ? set.erid : null} />
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 10 }}>
        {set.files.map(f => (
          <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', minWidth: 62 }}>
              {f.ratio || (f.is_archive ? 'архив' : '—')}
            </span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
              whiteSpace: 'nowrap' }}>{f.name}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{fileSize(f.size_bytes)}</span>
            {/* Кнопка, а не кликабельное имя: имя файла не выглядит действием, и по нему
                не догадаться, что откроется просмотр, — особенно у архива. */}
            <span onClick={() => setPreviewId(f.id)}
              style={{ cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 10.5,
                padding: '3px 8px', borderRadius: 7, border: '1px solid var(--border-card)',
                color: 'var(--accent)' }}>предпросмотр</span>
            {canEdit && !sent && (
              <span onClick={() => removeFile(f.id)} title="Удалить файл"
                style={{ cursor: 'pointer', color: 'var(--dot-overdue)', fontWeight: 700 }}>×</span>
            )}
          </div>
        ))}
        {!set.files.length && (
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>файлов пока нет</div>
        )}
      </div>

      <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', gap: 10 }}>
        {!!set.primary_review && (
          <div style={{ fontSize: 12.5,
            color: set.primary_review.verdict === 'ок' ? 'var(--income)' : 'var(--dot-overdue)' }}>
            Первичная проверка: {set.primary_review.verdict}
            {!!set.primary_review.decided_by && ` · ${set.primary_review.decided_by}`}
            {!!set.primary_review.reason && ` — ${set.primary_review.reason}`}
          </div>
        )}
        {/* ЗАЯВКА НА ПИКСЕЛИ — пиктограммой, справа в этой же строке (владелец
            18.09.2026). Файл тот же `Mediaplan_template`, который заполняли руками:
            ручной путь остался запасным после появления API и никуда не делся. */}
        <WeboramaRequestButton set={set} />
      </div>

      <TargetingUrl set={set} canEdit={canEdit} onSave={handlers.targetingUrl} />

      {/* Площадки — внутри креатива: сначала материал, потом кому он уходит. */}
      <div style={{ marginTop: 13 }}>
        <div style={{ ...CAP, marginBottom: 6 }}>
          {/* Куда именно ушло — считаем по строкам, а не по факту отправки: комплект
              уходит одним нажатием, но дальше площадки идут своим темпом, и «отправлено»
              без адресата читалось как «ушло в площадку», когда материал был у трафика. */}
          площадки · {set.recipients.length}
          {sent && (set.recipients.some(r => r.pair_id && !r.traffic_verdict)
            ? ' · на проверке у трафика'
            : ' · отправлено площадкам')}
        </div>
        {!set.recipients.length && (
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
            площадок нет — добавьте их кнопкой ниже
          </div>
        )}
        {/* Прокрутка с порогом НИЖЕ ширины блока (≈742 px в карточке): на десктопе полоса
            не появляется — таблица и так помещается, — а на узком экране строка уезжает
            вбок вместо того, чтобы сплющить статус и маркер в нечитаемые обрубки.
            Мобильная карточка переиспользует этот же блок. */}
        {!!set.recipients.length && (
          <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 700 }}>
              <div style={{ display: 'grid', gridTemplateColumns: R_COLS, gap: 9,
                padding: '0 8px 6px', borderBottom: '1px solid var(--border-card)', ...CAP }}>
                <span /><span>Площадка</span><span style={{ textAlign: 'center' }}>ТТ</span>
                <span>Посадочная страница</span>
                <span style={{ textAlign: 'center' }}>Статус</span>
                <span style={{ textAlign: 'center' }} title="Маркировка · Weborama · DSP">Внешние</span><span />
              </div>
              {set.recipients.map(r => (
                <RecipientRow key={r.target_id} r={r} set={set} canEdit={canEdit} canApprove={canApprove}
                  isAdmin={isAdmin} sent={sent} onDrop={dropTarget}
                  onTt={handlers.tt} onUrl={handlers.url} onRequest={handlers.request}
                  onVerdict={handlers.verdict}
                  onRework={(rec) => handlers.rework(set, rec)} onMove={handlers.move}
                  onShots={handlers.shots} />
              ))}
            </div>
          </div>
        )}
      </div>

      {!!err && <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        {canEdit && !sent && (
          <>
            {/* Поле остаётся — его открывает «Прикрепить креатив» сразу после создания
                версии. Отдельной кнопки «+ Файл» здесь НЕТ намеренно (владелец,
                27.08.2026): она ломала порядок — креатив это один материал, а второй
                материал это второй креатив, со своей кнопкой внизу блока. */}
            <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={upload} />
            <button style={btn(false)} onClick={() => handlers.addTargets(set.id)}>+ Площадки</button>
          </>
        )}
        {/* Правая группа — по раскладке хендоффа (README, раздел 5): слева добавление
            площадок, справа «Удалить креатив» и ОСНОВНОЕ действие. Основное всегда в
            одном месте, у правого края: сегодня это «Проверить креатив», завтра, после
            проверки, — «Отправить трафику», и глаз не должен искать его заново. */}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Письмо о правах на изображения — слева от основного действия (место указано
              владельцем 07.09.2026). Прикреплённое показывается ссылкой на скачивание:
              кнопка «загрузить» на месте документа заставляла бы гадать, есть он или нет. */}
          <input ref={letterRef} type="file" style={{ display: 'none' }}
                 accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" onChange={uploadLetter} />
          {set.rights_letter ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <a href={`/api/launch-prep/set/${set.id}/rights-letter`}
                 style={{ fontSize: 12.5, color: 'var(--accent)', textDecoration: 'none' }}
                 title={set.rights_letter.name}>📎 Письмо о правах</a>
              {canEdit && !sent && (
                <button onClick={dropLetter} disabled={busy} title="Снять письмо"
                        style={{ border: 'none', background: 'none', cursor: 'pointer',
                                 color: 'var(--text-faint)', fontSize: 15, lineHeight: 1 }}>×</button>
              )}
            </span>
          ) : canEdit && (
            <button style={btn(false)} disabled={busy} onClick={() => letterRef.current?.click()}>
              📎 Письмо о правах
            </button>
          )}
          {/* «Удалить креатив» уехала в ШАПКУ, перед статусом (31.08.2026). Внизу
              она стояла в одном ряду с основным действием — «Проверить креатив»,
              «Отправить трафику», — то есть разрушение и продвижение оказывались
              соседями и по раскладке, и по размеру. В шапке она рядом с именем
              креатива, которое и удаляют, и подальше от кнопки, нажимаемой каждый день. */}
          {canApprove && !set.primary_review && !!set.files.length && (
            <button style={btn(true)} onClick={() => setPreviewId(set.files[0].id)}>
              Проверить креатив
            </button>
          )}
          {/* Кнопка называется по СВОЕЙ ступени, а не по конечной цели маршрута. После
              разворота цепочки (28.08.2026) это нажатие отправляет материал ТРАФИКУ;
              площадкам он уходит его отмашкой. Прежняя подпись «Отправить площадкам»
              осталась от старого порядка и прямо врала: владелец прочитал её как
              «ушло в площадку», когда пары лежали в очереди трафика. */}
          {canEdit && ready && !sent && (
            <button style={btn(true)} disabled={busy || !set.recipients.length} onClick={send}
              title={`Материал уйдёт на проверку трафику — пар ${set.recipients.length}. `
                     + 'Площадкам он отправится после его отмашки.'}>
              {busy ? 'Отправка…' : `Отправить трафику (${set.recipients.length})`}
            </button>
          )}
        </span>
      </div>

      {/* Вопрос о названии — перед самой отправкой. Ровно один экран, две кнопки, и
          «отправить так» стоит слева: отказ должен быть так же дёшев, как согласие. */}
      {!!askName && (
        <Modal width={520} title={`Назвать креатив №${set.no}?`}
          onClose={() => setAskName(null)}
          footer={(
            <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button style={btn(false)} disabled={busy} onClick={doSend}>
                Отправить без названия
              </button>
              <button style={btn(true)} disabled={busy} onClick={sendWithName}>
                {busy ? 'Отправка…' : 'Назвать и отправить'}
              </button>
            </span>
          )}>
          <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
            <div style={{ color: 'var(--text-secondary)' }}>
              Название увидит площадка в своём кабинете — «Креатив №{set.no} — …». Когда
              в кампании их несколько, без названия она различает их только номером.
            </div>
            <input autoFocus value={askName.value} placeholder="например: баннер с пачкой"
              onChange={e => setAskName({ value: e.target.value })}
              onKeyDown={e => { if (e.key === 'Enter') sendWithName() }}
              style={{ ...inp, width: '100%', boxSizing: 'border-box' }} />
            <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
              Необязательно: назвать можно и позже, двойным кликом по заголовку.
            </div>
          </div>
        </Modal>
      )}

      {sent && <EridBlock set={set} onChanged={handlers.reload} />}

      {!!previewId && <CreativePreview files={set.files} startId={previewId}
        set={set} canApprove={canApprove}
        onReviewed={(verdict) => {
          setPreviewId(null)
          // «Ок» уже записан. «На доработку» требует причину — открываем форму, где её
          // спрашивают: вердикт неизменяем, и записать его без причины нельзя.
          if (verdict === 'ок') handlers.reload(); else handlers.review(set)
        }}
        onClose={() => setPreviewId(null)} />}
    </div>
  )
}

/* ── экран ──────────────────────────────────────────────────────────────── */
export default function AssemblyCreatives({ dealId, canEdit, canApprove, isAdmin = false, onChanged }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [picking, setPicking] = useState(false)
  const [ttFor, setTtFor] = useState(null)
  const [urlFor, setUrlFor] = useState(null)
  const [reviewFor, setReviewFor] = useState(null)
  const [verdictFor, setVerdictFor] = useState(null)
  const [autoUploadFor, setAutoUploadFor] = useState(null)
  const [deleteFor, setDeleteFor] = useState(null)

  /* Уведомление владельца карточки держим в ref и НЕ включаем в зависимости `load`.
     Иначе личность пропа входит в личность загрузки: вызывающий передаёт стрелку прямо
     в JSX — она новая на каждом рендере — эффект перезапускается, грузит, дёргает
     владельца, тот рендерится, и круг замыкается. 27.08.2026 это дало 1353 запроса за
     сеанс. Вызывающая сторона теперь тоже мемоизирует, но защита нужна с обеих: пропом
     когда-нибудь снова передадут стрелку. */
  const changedRef = useRef(onChanged)
  useEffect(() => { changedRef.current = onChanged }, [onChanged])

  const load = useCallback(() => (
    api.get(`/launch-prep/deal/${dealId}`, auth())
      .then(r => {
        setData(r.data); setErr('')
        // Свёрнутый вид и ступень ОРД держит владелец карточки: он грузит их сам,
        // потому что тело секции не монтируется, пока она свёрнута. Сообщаем ему о
        // каждом изменении — иначе он показывал бы вчерашнее до перезагрузки страницы.
        if (changedRef.current) changedRef.current()
        return r.data
      })
      .catch(e => { setErr(e.response?.data?.detail || 'Не удалось загрузить'); return null })
  ), [dealId])

  /* Площадки по услуге подставляются сами при первом открытии. Ограничитель на клиенте —
     только от повторного вызова в одном сеансе; настоящая защита на сервере: он смотрит
     след в журнале, поэтому снятая вручную площадка не вернётся при следующем открытии. */
  const autoTried = useRef(null)
  useEffect(() => {
    let alive = true
    load().then(d => {
      if (!alive || !d || !canEdit) return
      // Подставляем в ПЕРВЫЙ креатив сделки и только пока он пуст. Второй открывается
      // пустым — сервер это же и проверяет, здесь ограничитель только от повторного
      // вызова в одном сеансе.
      const first = (d.sets || [])[0]
      if (!first || first.recipients.length || autoTried.current === first.id) return
      autoTried.current = first.id
      api.post(`/launch-prep/deal/${dealId}/targets/auto`, { set_id: first.id }, auth())
        .then(r => { if (alive && r.data.added) load() })
        .catch(() => {})
    })
    return () => { alive = false }
  }, [load, dealId, canEdit])

  /* «Прикрепить креатив»: создаёт версию и сразу просит файл. Вторая и последующие —
     ПАРАЛЛЕЛЬНЫЕ креативы, а не доработки: доработка рождается только из отказа, и
     смешать их значит потерять ответ на вопрос «почему этот материал появился». */
  const attach = async () => {
    setErr('')
    try {
      const r = await api.post(`/launch-prep/deal/${dealId}/sets`,
        { origin: (data?.sets?.length ? 'параллельный' : 'первичный') }, auth())
      setAutoUploadFor(r.data.id)
      load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось создать креатив') }
  }

  /* Доработка адресуется ТОЛЬКО возразившему: площадка уходит на свою версию и дальше
     живёт отдельно, а согласовавшие ничего не пересматривают. */
  const rework = async (set, rec) => {
    setErr('')
    try {
      const r = await api.post(`/launch-prep/deal/${dealId}/sets`,
        { publisher_id: rec.publisher_id, origin: 'доработка', replaces_set_id: set.id }, auth())
      setAutoUploadFor(r.data.id)
      load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось собрать новую версию') }
  }

  // Кандидаты в трафики тянем один раз и лениво — только когда открыли выбор: список
  // короткий, но и он не нужен, пока никто не назначает.
  const [tmOpen, setTmOpen] = useState(false)
  const [tmList, setTmList] = useState(null)
  const openTm = async () => {
    setTmOpen(true)
    if (tmList) return
    try {
      const r = await api.get('/launch-prep/traffic-managers', auth())
      setTmList(r.data.items || [])
    } catch { setTmList([]) }
  }
  const setTrafficManager = async (id) => {
    setErr(''); setTmOpen(false)
    try {
      // Шлём УЧЁТКУ: профиль ответственного под ней заводится на сервере
      // (app/sales/reps.py). До 03.09.2026 сюда уходил id из справочника, а его у
      // трафиков нет ни у кого — список кандидатов приходил пустым.
      await api.put(`/launch-prep/deal/${dealId}/traffic-manager`,
        { user_id: id ? Number(id) : null }, auth())
      load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось назначить трафика') }
  }

  const handlers = {
    reload: load,
    tt: setTtFor,
    request: setUrlFor,
    review: setReviewFor,
    verdict: setVerdictFor,
    rework,
    addTargets: (setId) => setPicking(setId),
    confirmDelete: setDeleteFor,
    move: async (id, state) => {
      setErr('')
      try { await api.put(`/launch-prep/target/${id}/state`, { state }, auth()); load() }
      catch (e) { setErr(e.response?.data?.detail || 'Не удалось сменить состояние') }
    },
    /* Возвращает УСПЕХ: строка держит ввод открытым, пока ссылка не легла. И при отказе
       НЕ перезагружаем — перезагрузка стирала набранное вместе с ошибкой. */
    url: async (rec, url) => {
      setErr('')
      try {
        await api.put(`/launch-prep/target/${rec.target_id}/url`, { url }, auth())
        load()
        return true
      } catch (e) {
        setErr(e.response?.data?.detail || 'Не удалось сохранить ссылку')
        return false
      }
    },
    /* Скриншоты размещения снимает трафик, а нужны они аккаунту — как доказательство
       клиенту. Поэтому кнопка стоит здесь, а не только в очереди трафика; ручка одна
       и та же, права на неё — «очередь трафика ИЛИ креативы». */
    targetingUrl: async (set, url) => {
      setErr('')
      try { await api.put(`/launch-prep/set/${set.id}/targeting-url`, { url }, auth()); load() }
      catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить ссылку'); load() }
    },
    shots: async (rec) => {
      setErr('')
      try {
        const r = await api.get(`/traffic/pair/${rec.pair_id}/files/archive`,
          { ...auth(), responseType: 'blob' })
        const href = URL.createObjectURL(r.data)
        const a = document.createElement('a')
        a.href = href
        a.download = `${rec.pair_code || rec.code || 'screens'}.zip`
        document.body.appendChild(a); a.click(); a.remove()
        URL.revokeObjectURL(href)
      } catch (e) { setErr(e.response?.data?.detail || 'Не удалось скачать скриншоты') }
    },
  }

  if (!data) {
    return <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{err || 'загрузка…'}</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <span style={{ ...CAP, marginBottom: 0 }}>
          услуга: {data.service?.name || 'не определена'} · {data.service_reason}
        </span>

        {/* Ответственный трафик. Отправку он больше НЕ блокирует (владелец 03.09.2026):
            очередь согласования общая, разбирают по наличию времени. Отметка осталась —
            её ставят и меняют вручную до старта, — и тот же контрол стоит на карточке
            сделки: назначают и оттуда тоже. */}
        <span style={{ ...CAP, marginBottom: 0, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          трафик:
          {tmOpen ? (
            <select autoFocus defaultValue={data.deal?.traffic_manager_user_id || ''}
              onChange={e => setTrafficManager(e.target.value)}
              onBlur={() => setTmOpen(false)}
              style={{ fontFamily: UI, fontSize: 11.5, padding: '2px 6px', borderRadius: 7,
                border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                color: 'var(--text-primary)' }}>
              <option value="">— не назначен —</option>
              {(tmList || []).map(t => (
                <option key={t.user_id} value={t.user_id}>{t.name}</option>
              ))}
            </select>
          ) : (
            <span onClick={canEdit ? openTm : undefined}
              title={canEdit ? 'Назначить ответственного за проверку материала' : ''}
              style={{ cursor: canEdit ? 'pointer' : 'default',
                color: data.deal?.traffic_manager ? 'var(--text-secondary)' : 'var(--dot-current-dz)',
                borderBottom: canEdit ? '1px dashed var(--border-card)' : 'none' }}>
              {data.deal?.traffic_manager || 'не назначен'}
            </span>
          )}
          {/* Пустой список — не молчание: без сотрудников с рабочей группой «трафик»
              назначать некого, и это чинится в настройках пользователей, а не здесь. */}
          {tmOpen && tmList && !tmList.length && (
            <span style={{ color: 'var(--dot-overdue)' }}>нет сотрудников с ролью трафика</span>
          )}
        </span>
      </div>

      {!data.sets.length && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 9,
          padding: '30px 20px', borderRadius: 14, border: '1px dashed var(--border-card)',
          background: 'var(--bg-subtle)' }}>
          <span style={{ fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', maxWidth: 420 }}>
            Креативов пока нет. Площадки выбираются после того, как материал прикреплён.
          </span>
          {canEdit && <button style={btn(true)} onClick={attach}>Прикрепить креатив</button>}
        </div>
      )}

      {data.sets.map(s => (
        <CreativeSet key={s.id} set={s} canEdit={canEdit} canApprove={canApprove} isAdmin={isAdmin}
          autoUpload={autoUploadFor === s.id} onUploaded={() => setAutoUploadFor(null)}
          handlers={handlers} />
      ))}

      {!!data.sets.length && canEdit && (
        <div>
          <button style={btn(false)} onClick={attach}>+ Прикрепить креатив</button>
        </div>
      )}

      {!!err && <div style={{ fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

      {!!picking && <PickTargets dealId={dealId} setId={picking}
        onClose={() => setPicking(false)}
        onDone={() => { setPicking(false); load() }} />}
      {!!ttFor && <TechRequirements target={ttFor} onClose={() => setTtFor(null)} />}
      {!!urlFor && <UrlRequestDialog target={urlFor} onClose={() => setUrlFor(null)}
        onDone={() => { setUrlFor(null); load() }} />}
      {!!reviewFor && <PrimaryReviewDialog set={reviewFor} onClose={() => setReviewFor(null)}
        onDone={() => { setReviewFor(null); load() }} />}
      {!!verdictFor && <PairVerdictDialog rec={verdictFor} onClose={() => setVerdictFor(null)}
        onDone={() => { setVerdictFor(null); load() }} />}
      {!!deleteFor && <ConfirmDelete set={deleteFor} onClose={() => setDeleteFor(null)}
        onYes={async () => {
          await api.delete(`/launch-prep/set/${deleteFor.id}`, auth())
          setDeleteFor(null); load()
        }} />}
    </div>
  )
}
