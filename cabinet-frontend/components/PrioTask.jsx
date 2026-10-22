/**
 * Кабинет площадки · запрос на приоритезацию в «Требует вашего решения» (владелец 19.10.2026; хендофф
 * `docs/приоритезацияZ.zip`, правки аккаунтов по живому процессу). Раскладка — как у карточки креатива (`Task` в Dashboard):
 * строка 1 — чья кампания, старт, статус; строка 2 — запрос и кнопки (слева «посмотреть», справа решение); полоса SKU снизу.
 * Посадочную даём МЫ (кнопка «↗ посадочная»), от площадки — только SKU: без него «Согласовать» серая.
 * Длинные тексты — в окне «Подробнее», целиком, чипами с «копировать». Денег нет.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '../lib/http'
import { overlayClose } from '../lib/overlay'
import safeHref from '../lib/safeHref'
import { C, CAP, MONO, UI, btn, btnSm, chip, dm, inp, soft } from '../lib/ui'
import { startNote, urgency } from '../lib/urgency'

const SKU_RE = /^\d{4,}$/
const ELL = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c }
const fmtN = (n) => (n == null ? '—' : Number(n).toLocaleString('ru-RU'))
const fullDate = (iso) => (iso ? `${dm(iso)}.${String(iso).slice(0, 4)}` : '—')

function Ico() {
  return (
    <span style={{ width: 34, height: 34, borderRadius: 9, flex: '0 0 34px', background: C.subtle, border: `1px solid ${C.border}`,
      color: C.muted, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h10M4 18h6" /></svg>
    </span>
  )
}

function Landing({ url }) {
  if (!url) return null
  return (
    <a href={safeHref(url)} target="_blank" rel="noreferrer" title={url}
      style={{ ...btnSm(false), textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><path d="M15 3h6v6M10 14L21 3" /></svg>
      посадочная
    </a>
  )
}

function Approve({ ok, busy, onClick }) {
  return (
    <button disabled={busy || !ok} onClick={onClick} title={ok ? undefined : 'Сначала укажите SKU товара — без него согласовать нельзя'}
      style={{ ...btnSm(true), background: ok ? C.incomeFg : C.subtle, color: ok ? C.onFill : C.faint,
        border: `1px solid ${ok ? 'transparent' : C.border}`, cursor: ok ? 'pointer' : 'not-allowed',
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 13px' }}>
      <span style={{ fontSize: 12 }}>✓</span> Согласовать
    </button>
  )
}

// Список в окне — модульный уровень; «копировать» на 1,4 с становится «скопировано».
function ListBlock({ title, items }) {
  const [done, setDone] = useState(false)
  const copy = () => { navigator.clipboard?.writeText(items.join(', ')); setDone(true); setTimeout(() => setDone(false), 1400) }
  return (
    <div style={{ borderTop: `1px solid ${C.row}`, padding: '12px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ ...CAP, marginBottom: 0 }}>{title}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: C.faint }}>{items.length}</span>
        <button onClick={copy} disabled={!items.length}
          style={{ ...btnSm(false), marginLeft: 'auto', ...(done ? { background: C.incomeTint, color: C.incomeFg, borderColor: C.incomeBorder } : {}) }}>
          {done ? 'скопировано' : 'копировать'}</button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {items.length ? items.map((x, i) => (
          <span key={i} style={{ padding: '4px 9px', borderRadius: 8, background: C.subtle, border: `1px solid ${C.border}`,
            fontSize: 12.5, lineHeight: 1.4, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{x}</span>
        )) : <span style={{ fontSize: 12.5, color: C.faint }}>не указано</span>}
      </div>
    </div>
  )
}

function Details({ t, stTone, stLabel, busy, canApprove, onApprove, onAsk, onClose }) {
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  const cell = { display: 'flex', flexDirection: 'column', gap: 4, padding: '12px 14px', minWidth: 0 }
  const val = { fontSize: 13.5, fontWeight: 600, textWrap: 'pretty', overflowWrap: 'anywhere' }
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'var(--overlay)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '6vh 16px', overflowY: 'auto' }}>
      <div style={{ width: '100%', maxWidth: 760, background: C.card, borderRadius: 18, boxShadow: 'var(--shadow-float)',
        padding: '20px 24px', fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
            <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span style={chip(...stTone)}>{stLabel}</span>
              <span style={chip(C.subtle, C.secondary, C.border)}>{t.site}</span>
            </span>
            <b style={{ fontSize: 19, fontWeight: 800 }}>Запрос на приоритезацию · {t.product}</b>
          </div>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <Landing url={t.landing} />
            <button onClick={onClose} aria-label="Закрыть" style={{ border: 0, background: 'none', fontSize: 20, color: C.faint, cursor: 'pointer' }}>×</button>
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1.3fr 1fr 1fr', border: `1px solid ${C.row}`, borderRadius: 12, margin: '8px 0' }}>
          <span style={cell}><span style={{ ...CAP, marginBottom: 0 }}>рекламодатель · бренд</span><span style={val}>{[t.advertiser, t.brand].filter(Boolean).join(' · ') || '—'}</span></span>
          <span style={{ ...cell, borderLeft: `1px solid ${C.row}` }}><span style={{ ...CAP, marginBottom: 0 }}>период</span>
            <span style={{ ...val, fontFamily: MONO }}>{fullDate(t.period.from)} — {fullDate(t.period.to)}</span></span>
          <span style={{ ...cell, borderLeft: `1px solid ${C.row}` }}><span style={{ ...CAP, marginBottom: 0 }}>целевые показы</span>
            <span style={{ ...val, fontFamily: MONO }}>{fmtN(t.target_impressions)}</span></span>
          <span style={{ ...cell, borderLeft: `1px solid ${C.row}` }}><span style={{ ...CAP, marginBottom: 0 }}>ЕРИД</span>
            <span style={{ ...val, fontFamily: MONO }}>{t.erid || '—'}</span></span>
        </div>
        <ListBlock title="Конкуренты" items={t.competitors} />
        <ListBlock title="МНН" items={t.inn} />
        <ListBlock title="Ключевые слова и симптомы" items={t.keywords} />
        <div style={{ borderTop: `1px solid ${C.row}`, paddingTop: 12, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11.5, color: C.faint, flex: '1 1 300px' }}>
            Текст запроса правит аккаунт: если что-то не так — «Вернуть» с замечанием. Деньги в кабинете площадки не показываются.</span>
          {canApprove && <>
            <button style={soft(C.warningFg, C.warningBorder)} disabled={busy} onClick={() => { onClose(); onAsk('вернуть') }}>Вернуть</button>
            <Approve ok={SKU_RE.test(t.sku || '')} busy={busy} onClick={() => { onClose(); onApprove() }} />
          </>}
        </div>
      </div>
    </div>
  )
}

export default function PrioTask({ t, today, canApprove, onDone, onErr }) {
  const [busy, setBusy] = useState(false)
  const [show, setShow] = useState(false)
  const [editSku, setEditSku] = useState(!t.sku)
  const [sku, setSku] = useState(t.sku || '')
  const [ask, setAsk] = useState(null)
  const [reason, setReason] = useState('')
  const level = urgency(t.start, today)
  const late = level === 'overdue'
  const soon = level === 'soon'
  const stTone = late ? [C.dangerTint, C.danger, C.dangerBorder] : soon ? [C.warningTint, C.warningFg, C.warningBorder] : [C.subtle, C.secondary, C.border]
  const stLabel = late ? 'просрочено' : soon ? 'срочно' : 'ждёт решения'
  const skuOk = SKU_RE.test(sku.trim())
  const hasSku = SKU_RE.test(t.sku || '')
  const n = (a, w) => `${a.length} ${w(a.length)}`

  const run = async (fn, msg) => {
    setBusy(true)
    try { await fn(); onDone(); return true } catch (e) { onErr(e.response?.data?.detail || msg); return false } finally { setBusy(false) }
  }
  const saveSku = () => run(() => api.put(`/prio/${t.id}/sku`, { sku: sku.trim() }, auth()), 'Не удалось сохранить SKU')
  const answer = (verdict, why) => run(() => api.post(`/prio/${t.id}/verdict`, { verdict, reason: why || null }, auth()), 'Не удалось отправить ответ')

  const meta = [hasSku ? `SKU ${t.sku}` : null, `${fullDate(t.period.from)} — ${fullDate(t.period.to)}`,
    `цель ${fmtN(t.target_impressions)} показов`,
    n(t.competitors, (k) => plural(k, 'конкурент', 'конкурента', 'конкурентов')), `${t.inn.length} МНН`,
    n(t.keywords, (k) => plural(k, 'ключевое слово', 'ключевых слова', 'ключевых слов')),
    t.waiting_days != null ? `ждёт ${t.waiting_days} ${plural(t.waiting_days, 'день', 'дня', 'дней')}` : null].filter(Boolean).join(' · ')

  return (
    <div className="rise" style={{ padding: '12px 14px', borderRadius: 12, display: 'flex', flexDirection: 'column', gap: 10,
      background: late ? C.dangerBg : soon ? C.warnBg : C.card, border: `1px solid ${late ? C.dangerBorder : soon ? C.warningBorder : C.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: late ? C.danger : soon ? C.warning : C.accent }} />
        <span style={{ fontSize: 15, fontWeight: 700 }}>{[t.advertiser, t.brand].filter(Boolean).join(' · ') || t.product}</span>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: C.faint }}>Приоритезация</span>
        <span style={{ ...chip(C.subtle, C.secondary, C.border), fontSize: 11 }}>{t.site}</span>
        <span style={{ flex: 1 }} />
        <span style={{ ...chip(...stTone), fontFamily: MONO, gap: 8 }}>
          <span style={{ color: C.muted }}>старт рк</span><b>{dm(t.start)}</b>
          <span style={{ borderLeft: `1px solid ${stTone[2]}`, paddingLeft: 8 }}>{startNote(t.start, today)}</span>
        </span>
        <span style={chip(...stTone)}>{stLabel}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Ico />
        <span style={{ display: 'flex', flexDirection: 'column', flex: '1 1 260px', minWidth: 0 }}>
          <span style={{ fontSize: 14, fontWeight: 600, ...ELL }} title={`Приоритезация в поиске и каталоге · ${t.product}`}>
            Приоритезация в поиске и каталоге · {t.product}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, ...ELL }} title={meta}>{meta}</span>
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Landing url={t.landing} />
          <button style={btnSm(false)} onClick={() => setShow(true)}>Подробнее</button>
          {canApprove && hasSku && !editSku && <button style={btnSm(false)} onClick={() => setEditSku(true)}>изменить SKU</button>}
          {canApprove && !ask && <>
            <span style={{ width: 1, height: 22, background: C.inner, flex: '0 0 1px', margin: '0 2px' }} />
            <button style={soft(C.warningFg, C.warningBorder)} disabled={busy} onClick={() => setAsk('вернуть')}>Вернуть</button>
            <button style={soft(C.danger, C.dangerBorder)} disabled={busy} onClick={() => setAsk('отказ')}>Отказать</button>
            <Approve ok={hasSku} busy={busy} onClick={() => answer('ок')} />
          </>}
          {!canApprove && <span style={{ fontSize: 11.5, color: C.faint }}>у вас доступ только на просмотр</span>}
        </span>
      </div>

      {canApprove && editSku && !ask && (
        <div style={{ background: C.accentTint, border: `1px solid ${C.accentBorder}`, borderRadius: 12, padding: '10px 12px',
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: '0 0 auto' }}>
            <span style={{ ...CAP, marginBottom: 0, color: C.accent }}>SKU товара у вас</span>
            <span style={{ fontSize: 10.5, color: C.muted }}>без него согласовать нельзя · посадочную даём мы — она по кнопке выше</span>
          </span>
          <input value={sku} onChange={e => setSku(e.target.value)} placeholder="SKU, например 1234567" inputMode="numeric"
            style={{ ...inp, background: C.card, width: 220, fontFamily: MONO, fontSize: 12.5,
              borderColor: sku.trim() && !skuOk ? C.dangerBorder : C.border }} />
          {sku.trim() && !skuOk && <span style={{ fontSize: 11.5, color: C.danger }}>только цифры, от 4 знаков</span>}
          <span style={{ flex: 1 }} />
          {hasSku && <button style={btn(false)} onClick={() => { setSku(t.sku); setEditSku(false) }}>Отмена</button>}
          <button style={{ ...btn(true), opacity: busy || !skuOk ? 0.5 : 1 }} disabled={busy || !skuOk}
            onClick={async () => { if (await saveSku()) setEditSku(false) }}>Сохранить</button>
        </div>
      )}

      {ask && (
        <div style={{ background: C.subtle, border: `1px solid ${C.border}`, borderRadius: 11, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 12.5, color: C.secondary }}>
            {ask === 'отказ' ? 'Почему не берёте приоритезацию? Кампания уйдёт в архив.' : 'Что не так в запросе? Аккаунт поправит и пришлёт снова.'}</div>
          <textarea autoFocus value={reason} onChange={e => setReason(e.target.value)} style={{ ...inp, minHeight: 80, resize: 'vertical' }}
            placeholder="Своими словами — что именно не так" />
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={btn(false)} onClick={() => { setAsk(null); setReason('') }}>Отмена</button>
            <span style={{ flex: 1 }} />
            <button style={btn(true)} disabled={busy || !reason.trim()}
              onClick={async () => { if (await answer(ask, reason.trim())) { setAsk(null); setReason('') } }}>
              {ask === 'отказ' ? 'Отказаться' : 'Вернуть аккаунту'}</button>
          </div>
        </div>
      )}

      {show && <Details t={t} stTone={stTone} stLabel={stLabel} busy={busy} canApprove={canApprove}
        onApprove={() => answer('ок')} onAsk={setAsk} onClose={() => setShow(false)} />}
    </div>
  )
}
