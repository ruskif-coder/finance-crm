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
import { MONO, UI, inp, btn, PickValue, EXT_TONE, ExtChip, Modal, PortalPopover } from '@/components/salesTableKit'
import BrandMarkingDialog, { saveBrandMarking, BRAND_MARKING_SAVED } from '../ord/BrandMarking'
import ValuePopover from '@/components/ValuePopover'
import { overlayClose } from '@/lib/overlay'
import { can, getPermissions } from '@/lib/auth'
import { downloadFile } from '@/lib/download'
import safeHref from '@/lib/safeHref'
import { fmtDayOfMoment } from '@/lib/dates'
import { openAimTab, aimTabGo, aimTabFail, aimTone, aimNotLive, RESTART_NOTE } from '@/lib/aimTab'

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
      // Запрос — у ЭТОГО креатива: посадочные разных креативов одной площадки бывают
      // разными (владелец 25.09.2026).
      await api.post(`/launch-prep/set/${target.set_id}/target/${target.target_id}/url-request`,
        { text }, auth())
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
const STOCK_SIZES = [[240, 400], [300, 600], [640, 100], [970, 250],
  [1000, 150], [1200, 150]]
// Порядок (владелец 25.09.2026): сначала вертикальные, потом горизонтальные, в каждой
// группе по возрастанию ширины; 320×50 убран. Правя список — правь оба файла.

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
     переключении: иначе окно прыгает на сотни пикселей между 300×600 и 1200×150, кнопки
     проверки уезжают из-под курсора, и сравнить два размера подряд невозможно —
     страница под ними ходит. */
  const stageH = Math.max(160, ...sizes.map(([w, h]) => Math.round(Math.min(1, avail / w) * h)))

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      {/* Ширина — под самый широкий типовой размер 1:1 (владелец 25.09.2026): 1200 баннера +
          74 полей окна и сцены + 16 на полосу прокрутки. Уже экрана — вписывается, как раньше. */}
      <div style={{ ...SHEET, width: 'min(1290px, 96vw)' }}>
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
                sandbox="allow-scripts"
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
/* ══ БЛОК КРЕАТИВА — по хендоффу «статус креатива блок карточки» (владелец 25.09.2026) ══

   Раскладка, сетка таблицы, кнопки и плашки — из `design_handoff_creative_block`
   (docs/статус креатива блок карточки.zip). Функционал — прежний, целиком: хендофф
   «просто структурировал данные». Цвета — нашими CSS-переменными, а не хексами макета:
   иначе блок выпадал бы из тёмной темы.

   Главное правило раскладки хендоффа: всё, что уходит площадке (файл, письмо, отправка),
   — в левом блоке; всё внутреннее (нацеливание, ЕРИД, пиксели, удаление) — в правом. */
const CB = {
  card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)',
  tintBorder: 'var(--accent-border)', border: 'var(--border-card)', row: 'var(--border-row)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)',
  t4: 'var(--text-faint)', t5: 'var(--text-disabled)',
  accent: 'var(--accent)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)',
  income: 'var(--income)', incomeFg: 'var(--income-fg)', incomeTint: 'var(--income-tint)',
  incomeBorder: 'var(--income-border)',
  warn: 'var(--dot-current-dz)', warnFg: 'var(--warning-fg)', warnTint: 'var(--warning-tint)',
  warnBorder: 'var(--warning-border)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)', dangerBorder: 'var(--danger-border)',
  shadow: 'var(--shadow-card)',
}

/* Кнопка хендоффа: высота 30, радиус 9. Настоящий <button>, а не span: у действия
   должен быть фокус с клавиатуры и честное «недоступно». */
const CbBtn = ({ children, primary, danger, onClick, title, disabled, style }) => (
  <button type="button" onClick={onClick} title={title} disabled={disabled} style={{
    display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 12px',
    background: primary ? CB.accent : CB.card,
    border: `1px solid ${primary ? CB.accent : danger ? CB.dangerBorder : CB.border}`,
    color: primary ? 'var(--on-accent)' : danger ? CB.danger : CB.t2,
    borderRadius: 9, fontSize: 12, fontWeight: primary ? 700 : 600, whiteSpace: 'nowrap',
    fontFamily: UI, cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.55 : 1,
    ...style,
  }}>{children}</button>
)
const CbCap = ({ children, style }) => (
  <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.1em',
    textTransform: 'uppercase', color: CB.t3, ...style }}>{children}</span>
)
const cbLabel = { fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
  textTransform: 'uppercase', color: CB.t3 }
const fmtInt = n => (n ? Number(n).toLocaleString('ru-RU') : '')

/* Статус строки → вид. Статусы — прежняя лестница `rowStatus` (черновик… в размещении),
   тона — хендоффа: правки жёлтые, ожидание синее, согласованное зелёное. */
const ROW_LOOK = {
  'правки':        { bg: CB.warnTint, border: CB.warnBorder, fg: CB.warnFg, dot: CB.warn },
  'у трафика':     { bg: CB.subtle, border: CB.warnBorder, fg: CB.warnFg, dot: CB.warn },
  'у площадки':    { bg: CB.accentTint, border: CB.accentBorder, fg: CB.accent, dot: CB.accent },
  'черновик':      { bg: CB.subtle, border: CB.border, fg: CB.t3, dot: CB.t5 },
  'согласовано':   { bg: CB.incomeTint, border: CB.incomeBorder, fg: CB.incomeFg, dot: CB.income },
  'ерид получен':  { bg: CB.incomeTint, border: CB.incomeBorder, fg: CB.incomeFg, dot: CB.income },
  'ожидает старта': { bg: CB.incomeTint, border: CB.incomeBorder, fg: CB.incomeFg, dot: CB.income },
  'в размещении':  { bg: CB.incomeTint, border: CB.incomeBorder, fg: CB.incomeFg, dot: CB.income },
  'отказ':         { bg: CB.dangerTint, border: CB.dangerBorder, fg: CB.danger, dot: CB.danger },
}
/* Группы фильтра и порядок строк: сверху то, что требует действия (хендофф). */
const ROW_GROUP = {
  'правки': 'fix', 'у трафика': 'traffic', 'у площадки': 'wait', 'черновик': 'draft',
  'согласовано': 'ok', 'ерид получен': 'ok', 'ожидает старта': 'ok', 'в размещении': 'ok',
  'отказ': 'refused',
}
const GROUP_ORDER = { fix: 0, traffic: 1, wait: 2, draft: 3, ok: 4, refused: 5 }
const FILTERS = [
  ['all', 'Все', CB.t4], ['fix', 'Правки', CB.warn], ['traffic', 'У трафика', CB.warn],
  ['wait', 'У площадки', CB.accent], ['draft', 'Черновик', CB.t5],
  ['ok', 'Согласовано', CB.income], ['refused', 'Отказ', CB.danger],
]
/* Сетка таблицы хендоффа: одна на шапку и строки; статус и действие фиксированной
   ширины — плашки и кнопки стоят ровно в столбик во всех строках. */
const CB_COLS = 'minmax(160px,1.1fr) 104px 40px minmax(190px,2.2fr) 124px 84px 60px 136px'

/* ── маркировка: строка «Маркировка» блока настроек ────────────────────── */
function EridRow({ set, sent, onChanged }) {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [foreign, setForeign] = useState('')
  const [marking, setMarking] = useState(null)
  const [copied, setCopied] = useState(false)
  // Подтверждение выпуска маркера — окном, а не window.confirm: надо показать КОНТУР и
  // слово «необратимо» (боевую запись в ЕРИР не отозвать).
  const [askErid, setAskErid] = useState(false)
  // Право на отправку в ОРД — тот же ключ, что гейтит ручку на сервере. `null` — «ещё не
  // знаю»: снимок прав живёт в localStorage, и `false` с первого кадра прятал бы кнопку.
  const [maySubmit, setMaySubmit] = useState(null)
  useEffect(() => { setMaySubmit(can(getPermissions(), 'ord_submit', 'create')) }, [])

  const reload = useCallback(() => {
    if (!sent) return
    api.get(`/launch-prep/set/${set.id}/erid-readiness`, auth())
      .then(r => setSt(r.data)).catch(() => {})
  }, [set.id, sent])
  useEffect(() => { reload() }, [reload, set.erid])
  // Код ККТУ ввели в другом креативе или в блоке ОРД — он общий для бренда, перечитать.
  useEffect(() => {
    window.addEventListener(BRAND_MARKING_SAVED, reload)
    return () => window.removeEventListener(BRAND_MARKING_SAVED, reload)
  }, [reload])

  const call = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); onChanged() } catch (e) {
      setErr(e.response?.data?.detail || 'Не получилось')
    }
    setBusy(false)
  }
  const copy = () => {
    navigator.clipboard?.writeText(set.erid)
    setCopied(true); setTimeout(() => setCopied(false), 1400)
  }

  // Маркер выпускается на отправленный комплект: до отправки в ОРД уходить нечему.
  if (!sent) {
    return <span style={{ fontSize: 12, color: CB.t4 }}>после отправки трафику</span>
  }
  const own = set.erid_source !== 'площадки'

  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      {set.erid ? (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 30,
            padding: '0 11px', background: CB.incomeTint, border: `1px solid ${CB.incomeBorder}`,
            borderRadius: 9 }}>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: CB.incomeFg }}>{set.erid}</span>
            <span style={{ fontFamily: MONO, fontSize: 9, textTransform: 'uppercase', color: CB.incomeFg,
              opacity: 0.7 }}>{own ? 'наш' : 'внесён вручную'}</span>
          </span>
          <CbBtn onClick={copy}>{copied ? 'Скопировано' : 'Скопировать'}</CbBtn>
          {own && (
            <CbBtn disabled={busy} title="Маркер приходит сразу, а регистрация в реестре идёт асинхронно"
              onClick={() => call(() => api.post(`/launch-prep/set/${set.id}/erid/refresh`, {}, auth()))}>
              Обновить статус
            </CbBtn>
          )}
        </span>
      ) : (
        <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {!!st && !st.blockers?.length && maySubmit !== false && (
            <CbBtn primary disabled={busy || maySubmit !== true} onClick={() => setAskErid(true)}>
              Выпустить ЕРИД
            </CbBtn>
          )}
          <input value={foreign} onChange={e => setForeign(e.target.value)} placeholder="или чужой ЕРИД"
            style={{ flex: '1 1 140px', minWidth: 140, height: 30, boxSizing: 'border-box',
              padding: '0 10px', border: `1px solid ${CB.border}`, borderRadius: 9,
              background: CB.card, color: CB.t1, fontFamily: MONO, fontSize: 11.5, outline: 'none' }} />
          <CbBtn disabled={busy || !foreign.trim()}
            title="У саморекламы маркер выпускает площадка — он вводится руками"
            onClick={() => call(() => api.put(`/launch-prep/set/${set.id}/erid`, { erid: foreign.trim() }, auth()))}>
            Внести
          </CbBtn>
        </span>
      )}
      {!!set.ord_status && (
        <span style={{ fontFamily: MONO, fontSize: 10.5,
          color: /Error/.test(set.ord_status) ? CB.danger : CB.t3 }}>ОРД: {set.ord_status}</span>
      )}
      {/* Две ветки отказа реестра лечатся по-разному — текст показывается как есть. */}
      {!!set.ord_error && <span style={{ fontSize: 12, color: CB.danger }}>{set.ord_error}</span>}
      {!set.erid && !!st && !st.blockers?.length && maySubmit === false && (
        <span style={{ fontSize: 12, color: CB.t3 }}>Готов к выпуску ЕРИД — права на отправку в ОРД у вас нет</span>
      )}
      {/* Блокер, который чинится не уходя, — нажимаемый: нехватка кода ККТУ открывает
          маркировку бренда. Опознаём по КОДУ блокера, а не по фразе. */}
      {!set.erid && !!st?.blockers?.length && (
        <span style={{ fontSize: 12, color: CB.t3 }}>
          не хватает:{' '}
          {st.blockers.map((b, i) => (
            <span key={b.code || i}>
              {i > 0 && ' · '}
              {b.code === 'kktu' && st.brand?.id ? (
                <span onClick={() => setMarking(st.brand)}
                  title="Открыть маркировку бренда — код уйдёт в каждый креатив этой сделки"
                  style={{ cursor: 'pointer', color: CB.accent, borderBottom: `1px dashed ${CB.accent}` }}>
                  {b.text}
                </span>
              ) : b.text}
            </span>
          ))}
        </span>
      )}
      {!!err && <span style={{ fontSize: 12, color: CB.danger }}>{err}</span>}

      {askErid && (() => {
        const prod = (st?.ord_env || '').toLowerCase() === 'prod'
        return (
          <Modal width={520} title="Выпустить ЕРИД" onClose={() => setAskErid(false)}
            summary={`Креатив №${set.no ?? set.id} · площадок в отправке: ${st?.sent ?? 0}`}
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
                Контур ОРД: <b>{st?.ord_env || 'неизвестен'}</b>.{' '}
                {prod
                  ? 'Запись уходит в реестр НАВСЕГДА — отозвать её нельзя.'
                  : 'Это тренировочный контур: объект создастся у оператора и останется там мусором.'}
              </div>
              <div>Маркер выпускается на весь креатив сразу и проставляется всем площадкам,
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
            await saveBrandMarking(marking.id, payload)   // перечитает событие — у всех
            setMarking(null)
          }} />
      )}
    </span>
  )
}

/* ── нацеливание: строка «Нацеливание» блока настроек ─────────────────── */
/* Два пути, главный — кнопка: ссылка выпускается по нажатию и НЕ хранится (живёт 48
   часов). «Задать свою» — ручная ссылка для исключительного случая. */
function TargetingRow({ set, canEdit, onSave }) {
  const [v, setV] = useState(set.test_targeting_url || '')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [live, setLive] = useState(undefined)   // крутится ли — по ответу последнего нажатия
  const [aimNote, setAimNote] = useState('')    // «перезапущено — через 10 минут»
  useEffect(() => { setV(set.test_targeting_url || '') }, [set.test_targeting_url])

  // Вкладку открываем СИНХРОННО по клику, адрес подставляем после ответа: окно из
  // `await` блокировщик всплывающих окон считает непрошеным и режет.
  const aim = async () => {
    setErr('')
    const tab = openAimTab()
    setBusy(true)
    try {
      const r = await api.post(`/launch-prep/set/${set.id}/targeting-link`, {}, auth())
      aimTabGo(tab, r.data.url)
      setLive(!!r.data.active)
      setErr(aimNotLive(r.data))
      setAimNote(r.data.restarted ? RESTART_NOTE : '')
    } catch (e) {
      const why = e?.response?.data?.detail || 'Не удалось выпустить ссылку нацеливания'
      aimTabFail(tab, why)
      setErr(why)
    } finally { setBusy(false) }
  }

  const seg = (on) => ({
    height: 24, padding: '0 12px', display: 'inline-flex', alignItems: 'center',
    borderRadius: 8, border: 'none', fontFamily: UI, fontSize: 12, whiteSpace: 'nowrap',
    background: on ? CB.accentTint : 'transparent', color: on ? CB.accent : CB.t2,
    fontWeight: on ? 700 : 600, cursor: canEdit ? 'pointer' : 'default',
  })

  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span style={{ display: 'inline-flex', justifySelf: 'start', alignSelf: 'flex-start',
        padding: 3, background: CB.subtle, border: `1px solid ${CB.border}`, borderRadius: 10 }}>
        <button type="button" disabled={!canEdit || busy} onClick={aim}
          title="Откроет страницу DSP: нажмите «Включить» и увидите баннер на сайте площадки. Ссылка живёт двое суток, поэтому выпускается заново при каждом нажатии"
          style={{ ...seg(!editing), ...(!editing ? aimTone(live) : {}) }}>
          {busy ? 'выпускаю…' : 'Нацелить на себя'}
        </button>
        <button type="button" disabled={!canEdit} onClick={() => setEditing(e => !e)}
          title="Ручная ссылка нацеливания — для исключительного случая" style={seg(editing)}>
          Задать свою
        </button>
      </span>
      {editing && (
        <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input autoFocus value={v} onChange={e => setV(e.target.value)} placeholder="https://…"
            style={{ flex: 1, minWidth: 0, height: 30, boxSizing: 'border-box', padding: '0 10px',
              border: `1px solid ${CB.border}`, borderRadius: 9, background: CB.card, color: CB.t1,
              fontSize: 12, outline: 'none' }} />
          <CbBtn onClick={() => { onSave(set, v.trim()); setEditing(false) }}>Сохранить</CbBtn>
        </span>
      )}
      {!editing && !!set.test_targeting_url && (
        <a href={safeHref(set.test_targeting_url)} target="_blank" rel="noreferrer"
          title={set.test_targeting_url}
          style={{ fontSize: 11.5, fontFamily: MONO, color: CB.accent, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>
          своя: {set.test_targeting_url.replace(/^https?:\/\//, '')}
        </a>
      )}
      {!!err && <span style={{ fontSize: 12, color: CB.danger }}>{err}</span>}
      {!!aimNote && !err && <span style={{ fontSize: 12, color: CB.t2 }}>{aimNote}</span>}
    </span>
  )
}

/* ── комментарий правки: наведение — всплывает окном, клик — копирует текст ── */
/* Владелец 25.09.2026: текст правки берут в работу дизайнеру — копировать его должно
   быть одним нажатием, а прочитать — наведением, не разворачивая строку. */
function NotePeek({ who, text }) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(text)
    setCopied(true); setTimeout(() => setCopied(false), 1400)
  }
  return (
    <span onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onClick={copy} role="button" tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter') copy() }}
      style={{ width: 26, height: 26, display: 'inline-flex', alignItems: 'center',
        justifyContent: 'center', borderRadius: 7, background: CB.warnTint, color: CB.warnFg,
        cursor: 'copy', flex: '0 0 26px' }}>
      ≡
      <PortalPopover open={open} minWidth={300} align="right">
        <div style={{ padding: '10px 12px', display: 'grid', gap: 6, maxWidth: 380 }}>
          <span style={{ ...cbLabel, color: CB.warnFg }}>
            {who ? `правка · ${who}` : 'правка'}
          </span>
          <span style={{ fontSize: 12.5, lineHeight: 1.5, color: CB.t1, whiteSpace: 'pre-wrap' }}>{text}</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: copied ? CB.incomeFg : CB.t4 }}>
            {copied ? 'скопировано' : 'клик — скопировать текст'}
          </span>
        </div>
      </PortalPopover>
    </span>
  )
}

/* ── строка площадки ───────────────────────────────────────────────────── */
function RecipientRow({ r, set, canEdit, canApprove, isAdmin, sent, onDrop, onTt, onUrl, onRequest,
                        onVerdict, onRework, onMove, onShots, onPlan }) {
  const [url, setUrl] = useState(r.advertiser_url || '')
  const [editing, setEditing] = useState(false)
  const [urlErr, setUrlErr] = useState('')
  const [plan, setPlan] = useState(r.plan_show || 0)
  const [planErr, setPlanErr] = useState('')
  useEffect(() => { setUrl(r.advertiser_url || '') }, [r.advertiser_url])
  useEffect(() => { setPlan(r.plan_show || 0) }, [r.plan_show])
  // Площадка ушла в доработку — работает теперь в другом креативе, здесь только след.
  const gone = r.moved_to_no || null
  const note = r.reason || r.traffic_reason || ''
  const noteWho = r.reason ? (r.decided_by || 'площадка') : (r.traffic_reason ? 'трафик' : '')
  const status = rowStatus(r, set)
  const look = ROW_LOOK[status] || ROW_LOOK['черновик']
  // Маркер у строки есть, когда она прошла его ступень, — а не когда он есть у креатива.
  const hasErid = !!set.erid && ['ерид получен', 'ожидает старта', 'в размещении'].includes(status)

  /* Ссылку копируют по-разному: со схемой и без («apteka.ru/product/1»). Сервер схему
     требует (защита от «javascript:»), поэтому дописываем её здесь. */
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
    // Ввод закрываем ТОЛЬКО после успеха: отказ с закрытым полем стирает набранное.
    const ok = await onUrl(r, next, set.id)
    if (ok) { setUrlErr(''); setEditing(false) } else setUrlErr('не сохранилось')
  }
  const commitPlan = async () => {
    const n = plan || null
    if ((n || 0) === (r.plan_show || 0)) return
    const why = await onPlan(set, r, n)
    if (why) { setPlanErr(why); setPlan(r.plan_show || 0) } else setPlanErr('')
  }

  const reworkable = canEdit && !gone && (r.verdict === 'на доработку' || r.traffic_verdict === 'на переделку')
    && r.state !== 'отказ площадки'
  const answerable = isAdmin && canApprove && sent && !r.verdict && r.traffic_verdict === 'ок' && !gone
  const done = ROW_GROUP[status] === 'ok'

  return (
    <div style={{ display: 'grid', gridTemplateColumns: CB_COLS, gap: 12, alignItems: 'center',
      minHeight: 44, padding: '6px 8px', borderBottom: `1px solid ${CB.row}`, opacity: gone ? 0.5 : 1 }}>

      {/* Площадка: квадратный маркер статуса (до отправки — крестик «убрать»), домен,
          поверхность; код площадки второй строкой, если выдан. */}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
        {!sent && canEdit ? (
          <span onClick={() => onDrop(r.target_id)} title="Убрать площадку из креатива"
            style={{ cursor: 'pointer', width: 10, textAlign: 'center', fontSize: 13, fontWeight: 700,
              color: CB.t4, flex: '0 0 10px' }}>×</span>
        ) : (
          <span title={status} style={{ width: 7, height: 7, borderRadius: 2, background: look.dot, flex: '0 0 7px' }} />
        )}
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {r.name}{' '}
            <span style={{ fontFamily: MONO, fontSize: 8.5, textTransform: 'uppercase', color: CB.t4 }}>
              {r.surface_kind === 'app' ? 'app' : 'web'}
            </span>
          </span>
          {!!r.pair_code && (
            <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, color: CB.income }}>{r.pair_code}</span>
          )}
        </span>
      </span>

      {/* План показов — поле в строке (п. 6). Пустое — жёлтая рамка: без плана нет
          процента выполнения. Сервер сверяет с планом РК и отказывает словами. */}
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <input value={fmtInt(plan)} placeholder="—" disabled={!canEdit || !!gone}
          title={planErr || 'Плановый объём показов площадки по этому креативу'}
          onChange={e => { setPlan(parseInt(e.target.value.replace(/\D/g, ''), 10) || 0); if (planErr) setPlanErr('') }}
          onBlur={commitPlan}
          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}
          style={{ width: '100%', boxSizing: 'border-box', height: 28, padding: '0 9px',
            border: `1px solid ${planErr ? CB.dangerBorder : plan ? CB.border : CB.warnBorder}`,
            borderRadius: 8, background: CB.card, color: CB.t1, fontFamily: MONO, fontSize: 11.5,
            fontWeight: 700, textAlign: 'right', outline: 'none' }} />
      </span>

      <span style={{ display: 'flex', justifyContent: 'center' }}>
        <span onClick={() => onTt(r)} title={r.tech_requirements ? 'Технические требования площадки' : 'Технических требований нет'}
          style={{ width: 28, height: 22, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 6, background: r.tech_requirements ? CB.accentTint : CB.card,
            border: `1px solid ${r.tech_requirements ? CB.accentBorder : CB.border}`,
            color: r.tech_requirements ? CB.accent : CB.t5, fontFamily: MONO, fontSize: 9.5,
            fontWeight: 700, cursor: 'pointer' }}>ТТ</span>
      </span>

      {/* Посадочная ЭТОГО креатива: ссылкой в новую вкладку, полный адрес в подсказке.
          Правка — карандашом (у пустой — кликом по полю); ввод раскрывается на весь
          остаток строки `gridColumn: '4 / -1'`. */}
      {editing ? (
        <span style={{ gridColumn: '4 / -1', display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <input autoFocus value={url}
            placeholder={r.url_state === 'запрошена' ? 'ждём ответа площадки' : 'https://…'}
            onChange={e => { setUrl(e.target.value); if (urlErr) setUrlErr('') }}
            onBlur={commit}
            onKeyDown={e => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') { setUrl(r.advertiser_url || ''); setUrlErr(''); setEditing(false) }
            }}
            style={{ flex: 1, minWidth: 0, height: 28, boxSizing: 'border-box', padding: '0 9px',
              border: `1px solid ${CB.border}`, borderRadius: 8, background: CB.card, color: CB.t1,
              fontFamily: MONO, fontSize: 11.5, outline: 'none' }} />
          {!!urlErr && <span style={{ fontSize: 10.5, color: CB.danger, whiteSpace: 'nowrap' }}>{urlErr}</span>}
        </span>
      ) : (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          {r.advertiser_url ? (
            <a href={safeHref(r.advertiser_url)} target="_blank" rel="noreferrer" title={r.advertiser_url}
              style={{ fontFamily: MONO, fontSize: 11, color: CB.t2, minWidth: 0, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: 'none' }}>
              {r.advertiser_url.replace(/^https?:\/\//, '')}
            </a>
          ) : (
            <span onClick={() => { if (canEdit) setEditing(true) }}
              style={{ fontFamily: MONO, fontSize: 11, color: CB.t4, cursor: canEdit ? 'text' : 'default',
                whiteSpace: 'nowrap' }}>
              {r.url_state === 'запрошена' ? 'ждём ответа площадки' : 'ссылки нет'}
            </span>
          )}
          {canEdit && !!r.advertiser_url && !gone && (
            <span onClick={() => setEditing(true)} title="Изменить посадочную"
              style={{ cursor: 'pointer', color: CB.t4, fontSize: 11, flex: '0 0 auto' }}>✎</span>
          )}
          {canEdit && !r.advertiser_url && (
            <span onClick={e => { e.stopPropagation(); onRequest({ ...r, set_id: set.id }) }}
              title={r.url_state === 'запрошена' ? 'Запрос уже записан — открыть текст' : 'Запросить ссылку у площадки'}
              style={{ cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 10.5, padding: '3px 7px',
                borderRadius: 7, border: `1px solid ${CB.border}`,
                color: r.url_state === 'запрошена' ? CB.warnFg : CB.accent }}>
              {r.url_state === 'запрошена' ? 'ждём' : 'запросить'}
            </span>
          )}
        </span>
      )}

      {!editing && (<>
        <span title={status === 'у трафика' ? 'Материал на проверке у трафика — площадке он ещё не уходил'
                     : status === 'у площадки' ? 'Трафик проверил, ждём ответа площадки' : ''}
          style={{ height: 26, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: gone ? CB.subtle : look.bg, border: `1px solid ${gone ? CB.border : look.border}`,
            color: gone ? CB.t4 : look.fg, borderRadius: 8, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
          {gone ? `ушла в №${gone}` : status}
        </span>

        {/* Внешние системы: E — ЕРИД, W — Weborama, D — DSP. Цвет — значение. */}
        <span style={{ display: 'flex', justifyContent: 'center', gap: 3 }}>
          <ExtChip letter="E" tone={hasErid ? 'ok' : 'none'}
            title={hasErid ? `ЕРИД ${set.erid} — нажмите, чтобы скопировать` : 'ЕРИД не выпущен'}
            onClick={hasErid ? () => navigator.clipboard?.writeText(set.erid) : null} />
          <ExtChip letter="W" tone={EXT_TONE[r.external?.weborama?.state] || 'none'}
            title={`Weborama: ${r.external?.weborama?.state || 'нет данных'}` +
                   (r.external?.weborama?.why ? ` — ${r.external.weborama.why}` : '')} />
          <ExtChip letter="D" tone={EXT_TONE[r.external?.dsp?.state] || 'none'}
            title={`DSP: ${r.external?.dsp?.state || 'нет данных'}` +
                   (r.external?.dsp?.why ? ` — ${r.external.dsp.why}` : '')} />
        </span>

        <span style={{ display: 'flex', justifyContent: 'center' }}>
          <span onClick={() => r.files_count && onShots(r)}
            title={r.files_count ? `Скриншотов: ${r.files_count} — скачать архивом` : 'Скриншотов нет'}
            style={{ height: 22, padding: '0 8px', display: 'inline-flex', alignItems: 'center', borderRadius: 6,
              background: r.files_count ? CB.accentTint : 'transparent', color: r.files_count ? CB.accent : CB.t5,
              fontFamily: MONO, fontSize: 10, fontWeight: 700, cursor: r.files_count ? 'pointer' : 'default' }}>
            {r.files_count ? '▣ ' + r.files_count : '—'}
          </span>
        </span>

        <span style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6 }}>
          {!!note && <NotePeek who={noteWho} text={note} />}
          {reworkable ? (
            <CbBtn danger onClick={() => onRework(r)} style={{ width: 98, justifyContent: 'center', height: 28 }}
              title="Собрать новую версию для этой площадки">Доработка</CbBtn>
          ) : answerable ? (
            // Ответ за площадку — только администратор (владелец 31.08.2026): аварийный
            // ход для площадок без кабинета, а не обычный путь.
            <CbBtn onClick={() => onVerdict(r)} style={{ width: 98, justifyContent: 'center', height: 28,
              color: CB.accent, borderColor: CB.accentBorder }}>Ответ</CbBtn>
          ) : isAdmin && canEdit && r.state === 'ерид получен' && !gone ? (
            <CbBtn onClick={() => onMove(r.target_id, 'в размещении')} title="Кампания заведена и запущена"
              style={{ width: 98, justifyContent: 'center', height: 28, color: CB.incomeFg,
                borderColor: CB.incomeBorder }}>В эфир</CbBtn>
          ) : (
            <span style={{ width: 98, textAlign: 'center', fontFamily: MONO, fontSize: 9,
              textTransform: 'uppercase', color: CB.t4 }}>
              {done ? 'готово' : status === 'отказ' ? 'отказ' : ''}
            </span>
          )}
        </span>
      </>)}
    </div>
  )
}

/* ── креатив ────────────────────────────────────────────────────────────── */

/* Что сервер поправил в баннере при загрузке (`prepared`, владелец 25.09.2026): правка
   делается сама, но ВИДИМО — аккаунт должен знать, что лежит не байт в байт то, что
   прислал клиент. */
const PREPARED_SAID = {
  'ad.size': 'в баннере не был объявлен размер — вшили адаптивный (ad.size 0×0), без него DSP архив не принимает',
  'link': 'ссылка клика была под другую рекламную систему — заменили на макрос нашей DSP {LINK_UNESC}',
  'root': 'баннер лежал во вложенной папке — разложили в корень архива, иначе DSP не находит HTML',
  'mac': 'убрали служебные файлы Mac (__MACOSX, .DS_Store)',
}
const preparedNote = (list) => {
  const parts = (list || []).map(k => PREPARED_SAID[k]).filter(Boolean)
  return parts.length ? 'Баннер подготовлен для DSP: ' + parts.join('; ') + '.' : null
}

function CreativeSet({ set, canEdit, canApprove, isAdmin, autoUpload, onUploaded, handlers, rkPlan }) {
  const fileRef = useRef(null)
  const letterRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [prepNote, setPrepNote] = useState(null)
  const [previewId, setPreviewId] = useState(null)
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState(set.title || '')
  const [filter, setFilter] = useState('all')
  const [pixErr, setPixErr] = useState('')
  const [copied, setCopied] = useState(false)
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

  /* «Прикрепить креатив» создаёт версию и сразу открывает выбор файла. */
  useEffect(() => {
    if (autoUpload && !set.files.length) { fileRef.current?.click(); onUploaded() }
  }, [autoUpload, set.files.length, onUploaded])

  /** Письмо о правах — ОДНО на креатив, своей ручкой: в общем списке файлов оно
   *  испортило бы вывод формы креатива для ОРД. Прикрепить можно и после отправки,
   *  заменить и снять — нельзя (не докажешь, при каком письме согласовали). */
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

  /* «Новая версия» до отправки — ЗАМЕНА материала: креатив это один материал, прежний
     файл снимается, новый загружается. После отправки новая версия — доработка
     отдельным креативом (кнопка «Доработка» в строке площадки). */
  const upload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setErr(''); setPrepNote(null)
    try {
      for (const f of set.files) await api.delete(`/launch-prep/file/${f.id}`, auth())
      const form = new FormData()
      form.append('file', file)
      const r = await api.post(`/launch-prep/set/${set.id}/files`, form,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      setPrepNote(preparedNote(r.data?.prepared))
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось загрузить') }
    handlers.reload()
    setBusy(false)
  }

  /* НАЗВАНИЕ СПРАШИВАЕМ ПЕРЕД ОТПРАВКОЙ, НО НЕ ТРЕБУЕМ (владелец 18.09.2026): площадка
     различает креативы одной кампании по названию. Отказ («отправить так») — сразу. */
  const [askName, setAskName] = useState(null)
  const doSend = async () => {
    setAskName(null)
    setBusy(true); setErr('')
    try {
      // Отправляем ВСЕМ, кто в списке: список и есть выбор (владелец, 27.08.2026).
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

  /* Крестик СНИМАЕТ площадку из креатива — только до отправки. */
  const dropTarget = async (id) => {
    setErr('')
    try { await api.delete(`/launch-prep/set/${set.id}/target/${id}`, auth()); handlers.reload() }
    catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось убрать площадку') }
  }

  const ready = set.primary_review?.verdict === 'ок'
  const copyErid = () => {
    navigator.clipboard?.writeText(set.erid)
    setCopied(true); setTimeout(() => setCopied(false), 1400)
  }

  // Статусы, счётчики фильтра и порядок строк — из данных, а не задаются.
  const rowsAll = set.recipients.map(r => ({ r, st: rowStatus(r, set) }))
  const counts = { all: rowsAll.length }
  rowsAll.forEach(({ st }) => { const g = ROW_GROUP[st] || 'draft'; counts[g] = (counts[g] || 0) + 1 })
  const rows = rowsAll
    .filter(({ st }) => filter === 'all' || (ROW_GROUP[st] || 'draft') === filter)
    .sort((a, b) => (GROUP_ORDER[ROW_GROUP[a.st]] ?? 9) - (GROUP_ORDER[ROW_GROUP[b.st]] ?? 9)
      || (a.r.moved_to_no ? 1 : 0) - (b.r.moved_to_no ? 1 : 0))
  const planTotal = set.recipients.reduce((a, r) => a + (r.plan_show || 0), 0)
  const planFilled = set.recipients.filter(r => r.plan_show).length
  const agreed = set.recipients.filter(r => ['ok'].includes(ROW_GROUP[rowStatus(r, set)])).length
  const tags = [set.scope, set.origin !== 'первичный' ? set.origin : null,
    set.form ? (FORM_LABEL[set.form] || set.form) : null].filter(Boolean).join(' · ')
  const file = set.files[0]

  return (
    <section style={{ background: CB.card, border: `1px solid ${CB.border}`, boxShadow: CB.shadow,
      borderRadius: 18, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16,
      color: CB.t1, marginTop: 14 }}>

      {/* ── шапка: номер · название · теги · ЕРИД · этап ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: '-0.02em' }}>Креатив №{set.no}</span>
        {naming ? (
          <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="название креатива"
            style={{ ...inp, width: 260, fontSize: 13, padding: '3px 8px' }}
            onBlur={saveName}
            onKeyDown={e => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') { setName(set.title || ''); setNaming(false) }
            }} />
        ) : (
          /* Пустое название подсвечено: не ошибка, а недоделка — отправить можно и так.
             Правится двойным кликом: одиночный слишком легко случается при выделении. */
          <span onDoubleClick={() => canEdit && setNaming(true)}
            title={canEdit ? (set.title ? 'Двойной клик — переименовать'
              : 'Двойной клик — назвать. Название видит площадка и по нему отличает креативы кампании') : ''}
            style={{ fontSize: 15, fontWeight: 600, cursor: canEdit ? 'text' : 'default',
              color: set.title ? CB.accent : CB.warnFg,
              background: set.title ? 'transparent' : CB.warnTint,
              borderRadius: 7, padding: set.title ? 0 : '1px 8px' }}>
            {set.title || 'без названия'}
          </span>
        )}
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: CB.t3 }}>{tags}</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {set.erid ? (
            <span onClick={copyErid} title={`ЕРИД ${set.erid} — нажмите, чтобы скопировать`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: CB.incomeTint,
                border: `1px solid ${CB.incomeBorder}`, color: CB.incomeFg, borderRadius: 9, padding: '5px 11px',
                fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase',
                whiteSpace: 'nowrap', cursor: 'pointer' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: CB.income }} />
              {copied ? 'скопировано' : 'ЕРИД выпущен'}
              <span style={{ opacity: 0.5 }}>|</span>
              <span style={{ textTransform: 'none', letterSpacing: '.02em' }}>{set.erid}</span>
            </span>
          ) : (
            <span title="Креатив без ЕРИД нельзя ставить в эфир"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: CB.subtle,
                border: `1px solid ${CB.border}`, color: CB.t3, borderRadius: 9, padding: '5px 11px',
                fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.06em',
                textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: CB.t5 }} />ЕРИД не выпущен
            </span>
          )}
          <SetStateBadge state={set.state} />
        </span>
      </div>

      {/* ── два блока управления: переносятся на узком экране ── */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' }}>

        {/* файлы и письма — всё, что уходит площадке */}
        <div style={{ flex: '1.25 1 520px', minWidth: 0, background: CB.tint, border: `1px solid ${CB.tintBorder}`,
          borderRadius: 14, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CbCap>Файлы и письма</CbCap>
          <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={upload} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px 12px', flexWrap: 'wrap', padding: '9px 11px',
            background: CB.card, border: `1px solid ${CB.border}`, borderRadius: 11 }}>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 200, flex: '1 1 200px' }}>
              <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis',
                whiteSpace: 'nowrap', color: file ? CB.t1 : CB.t4 }}>
                {file ? file.name : 'файла пока нет'}
              </span>
              {!!file && (
                <span style={{ fontFamily: MONO, fontSize: 9.5, color: CB.t4, whiteSpace: 'nowrap' }}>
                  {file.is_archive ? 'архив' : 'файл'} · {fileSize(file.size_bytes)}
                  {file.ratio ? ` · ${file.ratio}` : ''}
                  {file.uploaded_at ? ` · ${fmtDayOfMoment(file.uploaded_at)}` : ''}
                </span>
              )}
            </span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
              {!!file && <CbBtn onClick={() => setPreviewId(file.id)}>Предпросмотр</CbBtn>}
              {!!file && (
                <CbBtn title="Скачать файл"
                  onClick={() => downloadFile(`/launch-prep/file/${file.id}`, file.name, setErr)}>↓</CbBtn>
              )}
              {canEdit && !sent && (
                <CbBtn disabled={busy} onClick={() => fileRef.current?.click()}
                  title={file ? 'Заменить материал: прежний файл снимется' : 'Загрузить материал креатива'}>
                  {file ? 'Новая версия' : 'Загрузить'}
                </CbBtn>
              )}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {set.primary_review ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, borderRadius: 8, padding: '5px 10px',
                fontSize: 12, fontWeight: 600,
                background: set.primary_review.verdict === 'ок' ? CB.incomeTint : CB.dangerTint,
                color: set.primary_review.verdict === 'ок' ? CB.incomeFg : CB.danger }}>
                <span style={{ width: 6, height: 6, borderRadius: 2,
                  background: set.primary_review.verdict === 'ок' ? CB.income : CB.danger }} />
                {set.primary_review.verdict === 'ок' ? 'Первичная проверка пройдена' : 'Первичная проверка: на доработку'}
                {!!set.primary_review.decided_by && ` · ${set.primary_review.decided_by}`}
                {!!set.primary_review.reason && ` — ${set.primary_review.reason}`}
              </span>
            ) : (
              <span style={{ fontSize: 12, color: CB.t4 }}>первичная проверка не пройдена</span>
            )}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <input ref={letterRef} type="file" style={{ display: 'none' }}
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" onChange={uploadLetter} />
              {set.rights_letter ? (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <CbBtn title={set.rights_letter.name}
                    onClick={() => downloadFile(`/launch-prep/set/${set.id}/rights-letter`, set.rights_letter.name, setErr)}>
                    📎 Письмо о правах
                  </CbBtn>
                  {canEdit && !sent && (
                    <button onClick={dropLetter} disabled={busy} title="Снять письмо"
                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: CB.t4,
                        fontSize: 15, lineHeight: 1 }}>×</button>
                  )}
                </span>
              ) : canEdit && (
                <CbBtn disabled={busy} onClick={() => letterRef.current?.click()}>📎 Письмо о правах</CbBtn>
              )}
              {canApprove && !set.primary_review && !!set.files.length && (
                <CbBtn primary onClick={() => setPreviewId(set.files[0].id)}>Проверить креатив</CbBtn>
              )}
              {/* Кнопка названа по СВОЕЙ ступени: материал уходит трафику, площадкам — его
                  отмашкой (разворот цепочки 28.08.2026). */}
              {canEdit && ready && !sent && (
                <CbBtn primary disabled={busy || !set.recipients.length} onClick={send}
                  title={`Материал уйдёт на проверку трафику — площадок ${set.recipients.length}. Площадкам он отправится после его отмашки.`}>
                  {busy ? 'Отправка…' : `Отправить трафику (${set.recipients.length})`}
                </CbBtn>
              )}
            </span>
          </div>
          {!!prepNote && (
            <div style={{ padding: '7px 10px', borderRadius: 8, fontSize: 12, lineHeight: 1.45, display: 'flex',
              gap: 8, alignItems: 'flex-start', background: CB.accentTint, border: `1px solid ${CB.accentBorder}`,
              color: CB.t2 }}>
              <span style={{ flex: 1 }}>{prepNote}</span>
              <button onClick={() => setPrepNote(null)} title="Понятно, скрыть"
                style={{ border: 0, background: 'transparent', cursor: 'pointer', padding: 0, color: CB.t3,
                  fontSize: 14, lineHeight: 1 }}>×</button>
            </div>
          )}
          {!!err && <div style={{ fontSize: 12.5, color: CB.danger }}>{err}</div>}
        </div>

        {/* настройки и маркировка — внутренние действия */}
        <div style={{ flex: '1 1 440px', minWidth: 0, background: CB.card, border: `1px solid ${CB.border}`,
          borderRadius: 14, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CbCap>Настройки и маркировка</CbCap>
          <div style={{ display: 'grid', gridTemplateColumns: '118px minmax(0,1fr)', gap: 10, alignItems: 'center' }}>
            <span style={cbLabel}>Нацеливание</span>
            <TargetingRow set={set} canEdit={canEdit} onSave={handlers.targetingUrl} />
            <span style={{ ...cbLabel, alignSelf: 'start', paddingTop: 9 }}>Маркировка</span>
            <EridRow set={set} sent={sent} onChanged={handlers.reload} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 10, marginTop: 'auto',
            borderTop: `1px solid ${CB.row}`, flexWrap: 'wrap' }}>
            <span style={{ ...cbLabel, color: CB.t4 }}>согласовали {agreed} из {set.recipients.length} площадок</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
              {!!set.recipients.length && (
                <CbBtn title="Скачать заявку на пиксели Weborama (Excel для менеджера)"
                  onClick={async () => { setPixErr(''); await downloadFile(`/launch-prep/set/${set.id}/weborama-request`, null, setPixErr) }}>
                  ↓ Пиксели Weborama
                </CbBtn>
              )}
              {canEdit && (
                /* Отправленный креатив не удаляется — у него вердикты площадок, у
                   маркированного и запись в реестре; кнопка гаснет и объясняет почему. */
                <CbBtn danger disabled={sent} onClick={() => handlers.confirmDelete(set)}
                  title={sent ? 'Отправленный креатив не удаляется — доработка это новая версия'
                    : 'Удалить креатив вместе с файлами и выбором площадок'}>
                  Удалить креатив
                </CbBtn>
              )}
            </span>
          </div>
          {!!pixErr && <span style={{ fontSize: 12, color: CB.danger }}>{pixErr}</span>}
        </div>
      </div>

      {/* ── фильтр и итог плана ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <CbCap>Площадки</CbCap>
        {FILTERS.filter(([k]) => k === 'all' || counts[k]).map(([k, l, dot]) => (
          <span key={k} onClick={() => setFilter(k)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
            height: 28, padding: '0 11px', background: filter === k ? CB.accentTint : CB.card,
            border: `1px solid ${filter === k ? CB.accentBorder : CB.border}`, borderRadius: 8,
            color: filter === k ? CB.accent : CB.t2, fontSize: 12, fontWeight: filter === k ? 700 : 600,
            whiteSpace: 'nowrap', cursor: 'pointer' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{l}
            <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>{counts[k] || 0}</span>
          </span>
        ))}
        {canEdit && !sent && (
          <CbBtn onClick={() => handlers.addTargets(set.id)} style={{ height: 28 }}>+ Площадки</CbBtn>
        )}
        <span style={{ marginLeft: 'auto', ...cbLabel }}>
          план показов <b style={{ fontSize: 12, color: CB.t1, letterSpacing: 0 }}>{fmtInt(planTotal) || '0'}</b>
          {!!rkPlan && <span style={{ color: CB.t4 }}> из РК {fmtInt(rkPlan)}</span>}
          <span style={{ color: CB.t4 }}> · заполнено {planFilled} из {set.recipients.length}</span>
        </span>
      </div>

      {/* ── таблица: скроллится внутри блока, страница не едет ──
          Минимум 1000, а не 1300 из хендоффа: на экране 1500 таблица внутри карточки
          ~1060 px, и при 1080 кнопка «Доработать» уезжала за край (замер 25.09). Ради
          этого сужены колонки площадки, плана и ссылки; остальные — хендоффа. */}
      {!set.recipients.length ? (
        <div style={{ fontSize: 12.5, color: CB.t4 }}>площадок нет — добавьте их кнопкой «+ Площадки»</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 1000 }}>
            <div style={{ display: 'grid', gridTemplateColumns: CB_COLS, gap: 12, padding: '0 8px 8px',
              borderBottom: `1px solid ${CB.border}`, fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
              textTransform: 'uppercase', color: CB.t4 }}>
              <span>Площадка</span><span style={{ textAlign: 'right' }}>План показов</span>
              <span style={{ textAlign: 'center' }}>ТТ</span><span>Посадочная страница</span>
              <span style={{ textAlign: 'center' }}>Статус</span><span style={{ textAlign: 'center' }}>Внешние</span>
              <span style={{ textAlign: 'center' }}>Скрины</span><span style={{ textAlign: 'right' }}>Действие</span>
            </div>
            {rows.map(({ r }) => (
              <RecipientRow key={r.target_id} r={r} set={set} canEdit={canEdit} canApprove={canApprove}
                isAdmin={isAdmin} sent={sent} onDrop={dropTarget}
                onTt={handlers.tt} onUrl={handlers.url} onRequest={handlers.request}
                onVerdict={handlers.verdict} onRework={(rec) => handlers.rework(set, rec)}
                onMove={handlers.move} onShots={handlers.shots} onPlan={handlers.plan} />
            ))}
          </div>
        </div>
      )}

      {/* Вопрос о названии — перед самой отправкой; «отправить так» слева. */}
      {!!askName && (
        <Modal width={520} title={`Назвать креатив №${set.no}?`} onClose={() => setAskName(null)}
          footer={(
            <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button style={btn(false)} disabled={busy} onClick={doSend}>Отправить без названия</button>
              <button style={btn(true)} disabled={busy} onClick={sendWithName}>
                {busy ? 'Отправка…' : 'Назвать и отправить'}
              </button>
            </span>
          )}>
          <div style={{ fontSize: 13, lineHeight: 1.6, display: 'grid', gap: 10 }}>
            <div style={{ color: 'var(--text-secondary)' }}>
              Название увидит площадка в своём кабинете — «Креатив №{set.no} — …». Когда в кампании
              их несколько, без названия она различает их только номером.
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

      {!!previewId && <CreativePreview files={set.files} startId={previewId}
        set={set} canApprove={canApprove}
        onReviewed={(verdict) => {
          setPreviewId(null)
          // «Ок» записан. «На доработку» требует причину — открываем форму с ней.
          if (verdict === 'ок') handlers.reload(); else handlers.review(set)
        }}
        onClose={() => setPreviewId(null)} />}
    </section>
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
    url: async (rec, url, setId) => {
      setErr('')
      try {
        // Посадочная — у пары «креатив × площадка» (владелец 25.09.2026).
        await api.put(`/launch-prep/set/${setId}/target/${rec.target_id}/url`, { url }, auth())
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
    /* Плановый объём показов площадки по креативу (п. 6). Возвращает ТЕКСТ ОТКАЗА или
       пусто: строка показывает отказ у самого поля (объём больше плана РК) и возвращает
       прежнее значение. */
    plan: async (set, rec, value) => {
      try {
        await api.put(`/launch-prep/set/${set.id}/target/${rec.target_id}/plan`,
          { plan_show: value }, auth())
        load()
        return ''
      } catch (e) { return e.response?.data?.detail || 'Объём не сохранился' }
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
          handlers={handlers} rkPlan={data.rk_plan_show} />
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
