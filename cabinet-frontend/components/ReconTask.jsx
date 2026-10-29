/**
 * Кабинет площадки · сверка месяца в «Требует вашего решения» (26.10.2026; хендофф `docs/карточка сверки.zip`, план
 * `docs/ПЛАН_сверка_паблишера.md` §5). Обычная карточка очереди — без левой полосы и без отдельного блока.
 *
 * Чип статуса = чей ход: «ждёт вашего ответа · до ДД.ММ» → «SIMB-AD ответил» (мы предложили цифру — «Согласен с N»
 * прямо с карточки) → «ответ у SIMB-AD». «Согласен» без спора — это итог (владелец 29.10.2026): карточка уходит из
 * очереди, и окно предлагает скачать разаллокацию. Расхождение фиксирует менеджер паблишеров.
 * Сумма показывается (владелец 26.10): это биллинг площадки по CPM её договора, как в «Кампаниях».
 */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import api, { auth } from '../lib/http'
import { overlayClose } from '../lib/overlay'
import { downloadFile, downloadRazaloc } from '../lib/download'
import { C, CAP, MONO, UI, btn, chip, dm, num, rub, soft } from '../lib/ui'

const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const monthOf = (p) => `${MONTHS[Number(p.slice(5, 7)) - 1]} ${p.slice(0, 4)}`
const monthIn = (p) => MONTHS[Number(p.slice(5, 7)) - 1]   // «за октябрь» — винительный совпадает с именительным
const at = (iso) => (iso ? `${dm(iso)} ${iso.slice(11, 16)}` : '')
const parseShows = (s) => { const v = parseInt(String(s ?? '').replace(/\D/g, ''), 10); return Number.isNaN(v) ? null : v }
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c }

/** Состояние карточки по переписке. «Просрочено» — признак сервера (`late`), то же правило, что у менеджера. */
export function reconState(r) {
  if (r.last_side === 'площадка') return 'answer'
  if (r.last_side === 'мы') return 'reply'
  return r.late ? 'late' : 'wait'
}

const TONE = {
  wait: [C.accentTint, C.accent, C.accentBorder],
  reply: [C.warningTint, C.warningFg, C.warningBorder],
  late: [C.dangerTint, C.danger, C.dangerBorder],
  answer: [C.violetTint, C.violetFg, C.accentBorder],
}

function totals(r) {
  const plan = r.campaigns.reduce((a, c) => a + c.plan, 0)
  const web = r.campaigns.filter(c => c.surface !== 'app').length
  return { plan, web, app: r.campaigns.length - web }
}

const Chart = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 18h16" /><path d="M7 14l3-4 3 3 4-6" /></svg>
)

export default function ReconTask({ r, canApprove, onDone, onAgreed, onErr }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const st = reconState(r)
  const [bg, fg, bd] = TONE[st]
  const label = st === 'answer' ? 'ответ у SIMB-AD' : st === 'reply' ? `SIMB-AD ответил · до ${dm(r.due_at)}`
    : st === 'late' ? `просрочено · срок был ${dm(r.due_at)}` : `ждёт вашего ответа · до ${dm(r.due_at)}`
  const theirs = r.their_volume
  const diff = theirs != null && r.our_volume != null ? theirs - r.our_volume : null
  const pay = r.cpm ? (r.our_volume || 0) * r.cpm / 1000 : null
  const t = totals(r)
  const offer = st === 'reply' ? r.offer : null

  const agreeOffer = async () => {
    setBusy(true)
    try {
      const res = await api.post(`/recons/${r.id}/answer`, { kind: 'согласен' }, auth())
      if (res.data?.agreed) onAgreed?.(r)
      onDone?.()
    } catch (e) { onErr?.(e.response?.data?.detail || 'Не удалось ответить') } finally { setBusy(false) }
  }
  const openThread = () => {
    setOpen(true)
    if (r.unread) api.post(`/recons/${r.id}/seen`, {}, auth()).catch(() => {})
  }
  const note = st === 'answer' ? 'Ответ отправлен — ход за SIMB-AD, итог зафиксирует менеджер паблишеров.'
    : offer != null ? `SIMB-AD предложил итог ${num(offer)}${theirs != null ? ` (${offer - theirs >= 0 ? '+' : '−'}${num(Math.abs(offer - theirs))} к вашей цифре)` : ''}. Согласитесь или ответьте в переписке.`
      : st === 'reply' ? 'SIMB-AD ответил в переписке — посмотрите и ответьте.'
        : 'Все РК периода окончены. Подтвердите цифру или пришлите свою статистику — «Есть расхождение» в сверке.'

  const nums = [
    ['РК в срезе', String(r.campaigns.length), C.text], ['План по МП', num(t.plan), C.text], ['Наш факт', num(r.our_volume), C.text],
    ['Ваша статистика', theirs != null ? num(theirs) : '—', theirs != null ? C.text : C.faint],
    ['Расхождение', diff == null ? '—' : diff === 0 ? '0' : `${diff > 0 ? '+' : '−'}${num(Math.abs(diff))}`, diff ? C.warningFg : C.faint],
    ['К оплате до НДС', pay != null ? rub(pay) : 'нет CPM', C.text],
  ]

  return (
    <div className="rise" style={{ padding: '12px 14px', borderRadius: 12, display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0,
      background: st === 'late' ? C.dangerBg : C.warnBg, border: `1px solid ${st === 'late' ? C.dangerBorder : C.warningBorder}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: st === 'late' ? C.danger : C.warning, flex: '0 0 8px' }} />
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: C.warning, color: C.onFill, borderRadius: 7, padding: '3px 9px',
          fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}><Chart />сверка месяца</span>
        <span style={{ fontSize: 13.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{r.site} · {monthOf(r.period)}</span>
        <span style={{ ...CAP, marginBottom: 0, color: C.muted }}>сверка за закрытый месяц</span>
        <span style={{ marginLeft: 'auto', ...chip(bg, fg, bd) }}>{label}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, flex: '1 1 220px' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, background: C.warningTint, color: C.warningFg, flex: '0 0 26px' }}><Chart /></span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Подтвердите показы за {monthIn(r.period)}</span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap' }}>
              {r.campaigns.length} РК в срезе · решение до {dm(r.due_at)} · <span style={{ color: st === 'late' ? C.danger : C.muted }}>
                {st === 'answer' ? 'ход за SIMB-AD' : st === 'reply' ? 'срок продлён' : st === 'late' ? 'срок прошёл' : '2 раб. дн.'}</span></span>
          </span>
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginLeft: 'auto', flex: '0 0 auto' }}>
          <button onClick={openThread} style={{ ...soft(C.secondary, C.border), fontWeight: 600, display: 'inline-flex', alignItems: 'center' }}>
            {st === 'wait' || st === 'late' ? 'Открыть сверку' : 'Открыть переписку'}
            {!!r.unread && <span title="Новый ответ SIMB-AD" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 16, height: 16, marginLeft: 6, padding: '0 4px', borderRadius: 8, background: C.danger, color: C.onFill, fontFamily: MONO, fontSize: 9.5, fontWeight: 700 }}>{r.unread}</span>}
          </button>
          {canApprove && offer != null && (
            <button disabled={busy} onClick={agreeOffer} style={{ ...soft(C.onFill, 'transparent'), background: C.incomeFg, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              ✓ Согласен с {num(offer)}</button>)}
        </span>
      </div>

      <span style={{ display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap', padding: '9px 11px', background: C.tint, borderRadius: 11 }}>
        {nums.map(([k, v, c]) => (
          <span key={k} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.muted, whiteSpace: 'nowrap' }}>{k}</span>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, letterSpacing: '-0.02em', color: c, whiteSpace: 'nowrap' }}>{v}</span>
          </span>))}
      </span>
      <span style={{ display: 'flex', alignItems: 'flex-start', gap: 8, paddingTop: 8, borderTop: `1px solid ${C.warningBorder}` }}>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.muted, flex: '0 0 66px', paddingTop: 1 }}>Вывод</span>
        <span style={{ fontSize: 11.5, color: C.secondary, lineHeight: 1.45 }}>{note}</span>
      </span>

      {open && <ReconModal r={r} st={st} label={label} tone={TONE[st]} canApprove={canApprove} totals={t}
        onClose={() => setOpen(false)} onDone={(agreed) => { setOpen(false); if (agreed) onAgreed?.(r); onDone?.() }} />}
    </div>
  )
}

const COLS = 'minmax(0,1.6fr) minmax(0,0.9fr) 54px 106px 104px 96px 96px'

function ReconModal({ r, st, label, tone, canApprove, totals: t, onClose, onDone }) {
  const [diffOpen, setDiffOpen] = useState(false)
  const [val, setVal] = useState('')
  const [note, setNote] = useState('')
  const [file, setFile] = useState(null)
  const [msg, setMsg] = useState('')
  const [msgFile, setMsgFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Ответ ушёл, а файл нет (ревью 27.10.2026): повтор слал ответ заново — второе сообщение. Помним, к чему досылать файл.
  const [pending, setPending] = useState(null)
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])
  const ours = r.our_volume || 0
  const theirs = parseShows(val)
  const diff = theirs == null ? null : theirs - ours
  const canAct = canApprove && (st === 'wait' || st === 'late' || st === 'reply')
  const agreeWith = st === 'reply' && r.offer != null ? r.offer : ours
  const thread = r.thread || []
  const n = thread.filter(m => m.side !== 'система').length

  const send = async (kind, body, volume, f) => {
    setBusy(true); setErr('')
    let mid = pending?.messageId || null
    // Согласие могло пройти в первой попытке, а файл — нет: повтор шлёт только файл, и окно разаллокации не должно потеряться.
    let agreed = !!pending?.agreed
    try {
      if (!mid) {
        const res = (await api.post(`/recons/${r.id}/answer`, { kind, body: body || null, volume }, auth())).data
        mid = res.message_id
        agreed = !!res.agreed
      }
      if (f) {
        const fd = new FormData()
        fd.append('file', f)
        await api.post(`/recons/${r.id}/file?message_id=${mid}`, fd, auth())
      }
      setPending(null)
      onDone(agreed)
    } catch (e) {
      const d = e.response?.data?.detail
      if (mid && f) {
        setPending({ messageId: mid, file: f, agreed })
        setErr(`Ответ отправлен, а файл не прикрепился${d ? `: ${d}` : ''} — прикрепите его ещё раз`)
      } else setErr(d || 'Не удалось отправить')
    } finally { setBusy(false) }
  }
  const main = () => {
    if (diffOpen) {
      if (theirs == null) { setErr('Укажите показы по вашим данным за месяц'); return }
      send('расхождение', note, theirs, file)
    } else send('согласен', null, null, null)
  }

  if (!mounted) return null
  // Порталом в `body`: карточка очереди анимирована (`rise`) и становится опорой для `position: fixed` —
  // без портала окно открывалось внутри карточки сверки (владелец 26.10.2026). Так же сделаны lib/sheet и lib/preview.
  return createPortal(
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'var(--overlay)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', overflow: 'hidden', fontFamily: UI }}>
      <div style={{ width: '100%', maxWidth: 1280, maxHeight: 'calc(100vh - 48px)', background: C.card, borderRadius: 18, boxShadow: 'var(--shadow-float)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'flex-start', gap: 12, padding: '16px 22px 12px', borderBottom: `1px solid ${C.inner}` }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 17, fontWeight: 700 }}>Сверка за {monthOf(r.period)}</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 22, padding: '0 8px', borderRadius: 8, background: tone[0], color: tone[1], fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: tone[1] }} />{label}</span>
            </span>
            <span style={{ fontFamily: MONO, fontSize: 10, color: C.muted }}>
              {r.site} · {st === 'answer' ? 'ответ отправлен' : `ответить до ${dm(r.due_at)}.${r.due_at?.slice(0, 4)} (2 раб. дн.)`}</span>
          </span>
          <span onClick={onClose} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 9, color: C.muted, fontSize: 18, cursor: 'pointer' }}>×</span>
        </div>

        <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '14px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', gap: 10 }}>
            {[['Показов по нашим данным', num(ours), `${r.campaigns.length} РК периода`],
              ['Сумма до НДС', r.cpm ? rub(ours * r.cpm / 1000) : 'нет CPM', r.cpm ? `CPM договора ${r.cpm} ₽` : 'CPM договора не задан'],
              ['Кампаний', String(r.campaigns.length), `web ${t.web} · app ${t.app}`],
              ['План периода', num(t.plan), t.plan ? `выполнено ${(ours / t.plan * 100).toFixed(1).replace('.', ',')} %` : '—']].map(([k, v, s]) => (
              <span key={k} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '11px 13px', background: C.subtle, border: `1px solid ${C.inner}`, borderRadius: 14, minWidth: 0 }}>
                <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.muted, whiteSpace: 'nowrap' }}>{k}</span>
                <span style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, whiteSpace: 'nowrap' }}>{v}</span>
                <span style={{ fontSize: 11, color: C.muted, whiteSpace: 'nowrap' }}>{s}</span>
              </span>))}
          </div>

          {/* Переписка — справа от таблицы, как в макете; на узком окне уходит под неё (владелец 26.10.2026). */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 640px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 6 }}>
              <span style={{ fontSize: 13.5, fontWeight: 700, whiteSpace: 'nowrap' }}>Кампании периода</span>
              <span style={{ fontSize: 11.5, color: C.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.campaigns.length} · подтверждается только итог месяца</span>
            </div>
            <div style={{ overflowX: 'auto' }}><div style={{ minWidth: 720 }}>
              <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '0 4px 6px', borderBottom: `1px solid ${C.border}`, fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.muted }}>
                <span>Рекламодатель · бренд</span><span>Услуга</span><span>Пов.</span><span>Флайт</span><span>ЕРИД</span><span style={{ textAlign: 'right' }}>Показы</span><span style={{ textAlign: 'right' }}>Сумма, ₽</span>
              </div>
              {r.campaigns.map((c, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', padding: '6px 4px', borderBottom: `1px solid ${C.row}` }}>
                  <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.brand}</span>
                  <span style={{ fontSize: 11.5, color: C.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.service || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, textTransform: 'uppercase', color: C.muted }}>{c.surface || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.secondary }}>{dm(c.date_from)} — {dm(c.date_to)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.secondary, overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.erid || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right' }}>{num(c.fact)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right' }}>{r.cpm ? num(c.fact * r.cpm / 1000) : '—'}</span>
                </div>))}
              <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '8px 4px 0', fontFamily: MONO, fontWeight: 700 }}>
                <span style={{ fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.muted }}>Итого · {r.campaigns.length}</span><span /><span /><span /><span />
                <span style={{ fontSize: 12, textAlign: 'right' }}>{num(ours)}</span>
                <span style={{ fontSize: 12, textAlign: 'right' }}>{r.cpm ? num(ours * r.cpm / 1000) : '—'}</span>
              </div>
            </div></div>
          </div>

          {diffOpen && (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 14, padding: '12px 14px', background: C.warningTint, border: `1px solid ${C.warningBorder}`, borderRadius: 14 }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.warningFg }}>Показов по вашим данным за {monthIn(r.period)}</span>
                <input value={val} onChange={e => setVal(e.target.value)} inputMode="numeric" placeholder={num(ours)}
                  style={{ height: 36, padding: '0 11px', border: `1px solid ${C.warningBorder}`, borderRadius: 12, fontFamily: MONO, fontSize: 16, fontWeight: 700, background: C.card, outline: 'none', color: C.text }} />
                <span style={{ fontFamily: MONO, fontSize: 11, color: C.warningFg }}>
                  {diff == null ? 'разница с нашими данными посчитается сразу'
                    : `${diff >= 0 ? '+' : '−'}${num(Math.abs(diff))} · ${diff >= 0 ? '+' : '−'}${ours ? Math.abs(diff / ours * 100).toFixed(1).replace('.', ',') : '0'} % к нашим данным`}</span>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 48, border: `1px dashed ${C.warningBorder}`, borderRadius: 12, background: C.card, fontSize: 11.5, color: C.secondary, cursor: 'pointer', padding: '0 10px', textAlign: 'center' }}>
                  {file ? `прикреплено: ${file.name}` : 'Выгрузка вашей статистики (xlsx, csv, pdf) — выберите файл'}
                  <input type="file" onChange={e => setFile(e.target.files?.[0] || null)} style={{ display: 'none' }} /></label>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.warningFg }}>Комментарий — что и где расходится</span>
                <textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Например: по нашей статистике Adfox за 01–15 число показов больше, выгрузку прикрепили"
                  style={{ flex: 1, minHeight: 96, padding: '8px 11px', border: `1px solid ${C.warningBorder}`, borderRadius: 12, fontSize: 12, resize: 'vertical', background: C.card, outline: 'none', fontFamily: UI, color: C.text }} />
              </span>
            </div>)}
          </div>

          <div style={{ flex: '0 1 340px', minWidth: 280, display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 16, borderLeft: `1px solid ${C.inner}` }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13.5, fontWeight: 700 }}>Переписка</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint }}>{n} {plural(n, 'сообщение', 'сообщения', 'сообщений')}</span>
            </div>
            <span style={{ fontSize: 11, color: C.muted, marginTop: -4 }}>идёт до согласования, кругов без лимита</span>
            {thread.map(m => m.side === 'система' ? (
              <span key={m.id} style={{ alignSelf: 'center', display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.04em', color: C.faint }}>
                <span style={{ width: 24, height: 1, background: C.inner }} />{m.body}<span style={{ width: 24, height: 1, background: C.inner }} /></span>
            ) : (
              <span key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '9px 12px', borderRadius: 14, maxWidth: '90%',
                alignSelf: m.side === 'площадка' ? 'flex-end' : 'flex-start',
                background: m.side === 'площадка' ? C.violetTint : C.tint, border: `1px solid ${C.accentBorder}` }}>
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: m.side === 'площадка' ? C.violetFg : C.accent }}>
                    {m.side === 'площадка' ? `Вы${m.author_name ? ' · ' + m.author_name : ''}` : 'SIMB-AD'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{at(m.created_at)}</span>
                </span>
                {m.body && <span style={{ fontSize: 12.5, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{m.body}</span>}
                {m.volume != null && (
                  <span style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '3px 9px', borderRadius: 8, background: C.card, border: `1px solid ${C.accentBorder}` }}>
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.muted }}>предлагает</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{num(m.volume)}</span>
                  </span>)}
                {m.files.map(f => (
                  <span key={f.id} onClick={() => downloadFile(`/recons/${r.id}/files/${f.id}`, f.name, setErr)}
                    style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6, height: 24, padding: '0 9px', borderRadius: 8, background: C.card, border: `1px solid ${C.border}`, fontFamily: MONO, fontSize: 10.5, color: C.accent, cursor: 'pointer' }}>↓ {f.name}</span>))}
              </span>
            ))}
            {canApprove && (
              <span style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', paddingTop: 4 }}>
                <textarea value={msg} onChange={e => setMsg(e.target.value)} placeholder="Написать SIMB-AD — вопрос или уточнение"
                  style={{ flex: '1 1 100%', minHeight: 64, padding: '9px 11px', border: `1px solid ${C.border}`, borderRadius: 12, fontSize: 12, resize: 'vertical', background: C.card, outline: 'none', fontFamily: UI, color: C.text }} />
                <label title={msgFile ? msgFile.name : 'Приложить файл'} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, boxSizing: 'border-box', border: `1px solid ${msgFile ? C.accent : C.border}`, borderRadius: 10, color: msgFile ? C.accent : C.secondary, cursor: 'pointer' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.5l-8.5 8.5a4.5 4.5 0 0 1-6.4-6.4l8.9-8.9a3 3 0 0 1 4.3 4.3l-8.9 8.9a1.5 1.5 0 0 1-2.1-2.1l7.8-7.8" /></svg>
                  <input type="file" onChange={e => setMsgFile(e.target.files?.[0] || null)} style={{ display: 'none' }} /></label>
                <button disabled={busy || !msg.trim()} onClick={() => send('сообщение', msg, null, msgFile)}
                  style={{ height: 36, padding: '0 14px', borderRadius: 10, border: 0, background: msg.trim() ? C.accent : C.subtle, color: msg.trim() ? C.onFill : C.faint, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: msg.trim() ? 'pointer' : 'default', fontFamily: UI }}>Отправить</button>
              </span>)}
          </div>
          </div>
        </div>

        <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '12px 22px 14px', borderTop: `1px solid ${C.inner}` }}>
          <span style={{ fontSize: 11.5, color: err ? C.danger : C.muted, lineHeight: 1.45, flex: '1 1 280px' }}>
            {err || '«Согласен» — ваш ответ; итог фиксирует SIMB-AD, после этого цифра без возврата идёт в акт и себестоимость.'}</span>
          {!!pending && (
            <button disabled={busy} onClick={() => send(null, null, null, pending.file)} style={{ height: 34, padding: '0 16px', borderRadius: 10, border: 0, background: C.warning, color: C.onFill, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: UI }}>
              Прикрепить файл ещё раз</button>)}
          {canAct && !pending && (<>
            <button onClick={() => { setDiffOpen(!diffOpen); setErr('') }} style={{ height: 34, padding: '0 15px', borderRadius: 10, border: `1px solid ${C.warningBorder}`, background: C.card, color: C.warningFg, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: UI }}>
              {diffOpen ? 'Отмена' : 'Есть расхождение'}</button>
            <button disabled={busy} onClick={main} style={{ height: 34, padding: '0 16px', borderRadius: 10, border: 0, background: diffOpen ? C.warning : C.income, color: C.onFill, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: UI }}>
              {diffOpen ? 'Отправить правки' : `Согласен с ${num(agreeWith)}`}</button>
          </>)}
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** Окно после согласия со сверкой (владелец 29.10.2026): итог зафиксирован — разаллокацию можно скачать сразу, и она
 *  всегда лежит в «Кампаниях» в шапке закрытого месяца. */
export function RazalocReady({ r, onClose, onErr }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])
  if (!mounted) return null
  return createPortal(
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'var(--overlay)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', fontFamily: UI }}>
      <div style={{ width: '100%', maxWidth: 460, background: C.card, borderRadius: 18, boxShadow: 'var(--shadow-float)', padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>Сверка за {monthOf(r.period)} согласована</span>
        <span style={{ fontSize: 13, color: C.secondary, lineHeight: 1.5 }}>
          По итогу сверки собрана разаллокация {r.site} — по ней сдаётся акт в ОРД.
          Разаллокация всегда доступна в «Кампаниях» по закрытым месяцам.</span>
        <span style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 6 }}>
          <button type="button" onClick={onClose} style={btn(false)}>Закрыть</button>
          <button type="button" onClick={() => downloadRazaloc([{ request_id: r.id }], onErr).then(ok => ok && onClose())} style={btn(true)}>
            ↓ Скачать разаллокацию</button>
        </span>
      </div>
    </div>,
    document.body,
  )
}
