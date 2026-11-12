/**
 * Отправка в ЭДО по каждому документу (хендофф реестра v3, §2, 12.11.2026). Статус — плашка у номера без клика: «к отправке»
 * (пунктир, часы) → «отправлен · 12.11 15:30» → на «ждём оплату» «ждём подпись» → «подписан». Действие — справа, перед файлами:
 * «✓ отметить отправку», после отметки «отменить» (пока пакет на «выставлении»). Отметки ставит `POST /master-deals/{код}/sent`.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { fmtDateTimeShort } from '@/lib/dates'
import { SignBadge } from '@/components/master/docParts'

const ISSUE = 'выставление'
const WAIT = new Set(['ждём оплату', 'ждём сканы'])
const CLOCK = 'M12 6v6l4 2'
const OK = 'M5 12.5l4.5 4.5L19 7.5'

/** Режим документа в расхлопе: send — ЭДО на «выставлении», wait — ЭДО после него, null — прежние отметки подписи. */
export const sendMode = (m) => (m.docs?.paper ? null : m.status === ISSUE ? 'send' : WAIT.has(m.status) ? 'wait' : null)

/** Полоса комплекта в режиме отправки: к отправке — жёлтая, отправлен — синяя, подписан — зелёная. */
export const sendFrame = (state) => (state === 'подписан' ? 'var(--income)' : state === 'выставлен' ? 'var(--accent)' : 'var(--warning)')

function Pill({ text, bg, fg, border, dashed, icon, title }) {
  return (
    <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, height: 18, padding: '0 7px', borderRadius: 6, background: bg, color: fg,
      border: `1px ${dashed ? 'dashed' : 'solid'} ${border}`, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap' }}>
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={icon} /></svg>
      {text}
    </span>
  )
}

export function SendBadge({ sign, mode }) {
  const s = sign?.state
  if (mode === 'send' && s === 'выставлен') {
    return <Pill text={`отправлен · ${fmtDateTimeShort(sign.sent_at)}`} bg="var(--accent-tint)" fg="var(--accent-fg)" border="var(--accent-border)" icon={OK}
      title={`Отмечено: отправлен клиенту в Диадок ${fmtDateTimeShort(sign.sent_at)}${sign.sent_by ? ` · ${sign.sent_by}` : ''}`} />
  }
  if (mode === 'send' && s !== 'подписан' && s !== 'отклонён') {
    return <Pill text="к отправке" bg="var(--warning-bg)" fg="var(--warning-fg)" border="var(--warning-border)" dashed icon={CLOCK} title="Ещё не отправлен клиенту" />
  }
  if (mode === 'wait' && s === 'выставлен') {
    return <Pill text="ждём подпись" bg="var(--warning-tint)" fg="var(--warning-fg)" border="var(--warning-border)" icon={CLOCK}
      title={`Отправлен ${fmtDateTimeShort(sign.sent_at)} — подпись клиента не пришла`} />
  }
  return <SignBadge s={s || 'none'} small />
}

/** «✓ отметить отправку» / «отменить» — только в режиме send и с правом на правку. */
export function SendButton({ code, target, sign, label, onDone, setErr }) {
  const [busy, setBusy] = useState(false)
  const s = sign?.state
  if (s === 'подписан') return null
  const on = s !== 'выставлен'
  const run = async (e) => {
    e.stopPropagation()
    setBusy(true); setErr('')
    try { onDone((await api.post(`/master-deals/${code}/sent`, { items: [target], on, state: 'выставлен' }, auth())).data) }
    catch (er) { setErr(er?.response?.data?.detail || 'Не удалось отметить') } finally { setBusy(false) }
  }
  return on ? (
    <button type="button" data-noexp disabled={busy} onClick={run} title={`Загрузили ${label} в Диадок и отправили клиенту — отметить`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 24, padding: '0 9px', boxSizing: 'border-box', borderRadius: 7, border: '1px solid var(--accent)',
        background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1 }}>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={OK} /></svg>
      отметить отправку</button>
  ) : (
    <span data-noexp onClick={busy ? undefined : run} title="Отметили по ошибке — вернуть «к отправке»"
      style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 4px', fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', cursor: busy ? 'default' : 'pointer' }}>
      отменить</span>
  )
}
